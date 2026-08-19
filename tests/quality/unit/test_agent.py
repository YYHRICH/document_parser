"""单文档质量修复 Agent 的候选校验和事务闭环。"""

from pathlib import Path
from hashlib import sha256
from uuid import uuid4

import pytest

from document_parser.core.contracts import AssetKind, DocumentAsset, ParsedDocument, SourceAnchor
from quality import (
    RepairExecution,
    run_quality,
    run_quality_repair,
    run_quality_repair_detailed,
)
from quality.agent import (
    CandidateValidator,
    FakeRepairAgent,
    InMemoryRevisionStore,
    RepairAgentConfig,
    RepairOperation,
    RelationPatch,
    RepairedDocumentCandidate,
    TableCellLayoutPatch,
    TableCellPatch,
    content_fingerprint,
    QualityAgentNotConfigured,
    DocumentReadTools,
    QualityToolbox,
    available_skill_ids,
    load_skill,
    render_skills,
)
from quality.agent.context import DocumentContextBuilder
from quality.agent.agno_adapter import CandidateSchemaError
from quality.agent.index import DocumentIndex
from quality.agent.deepseek import (
    DeepSeekConfig,
    LLMConfigurationError,
    load_deepseek_config,
    build_deepseek_model,
)
from quality.agent.revision import materialize_candidate
from quality.agent.runtime import run_repair

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "quality" / "fixtures" / "parsed_documents"


def _load() -> ParsedDocument:
    return ParsedDocument.model_validate_json(
        (FIXTURES / "sdp-006-fallback.json").read_text(encoding="utf-8")
    )


def _candidate(document: ParsedDocument, *, markdown: str | None = None, blocks=None, base: str | None = None):
    revision = InMemoryRevisionStore().open(document)
    block_markdown = blocks or {}
    return revision, RepairedDocumentCandidate(
        base_revision=base or revision.revision_id,
        repaired_markdown=document.markdown if markdown is None else markdown,
        block_markdown=block_markdown,
        affected_ids=list(block_markdown),
        lineage=[base or revision.revision_id],
        reasoning="只调整 Markdown 格式，不改变事实内容。",
        source_content_fingerprint=content_fingerprint(document.markdown),
        change_kind="format",
        confidence=0.9,
    )


def test_candidate_validator_accepts_format_only_block_update():
    document = _load()
    store = InMemoryRevisionStore()
    revision = store.open(document)
    block = document.blocks[0]
    candidate = RepairedDocumentCandidate(
        base_revision=revision.revision_id,
        repaired_markdown=document.markdown,
        block_markdown={str(block.id): block.markdown + "  "},
        affected_ids=[str(block.id)],
        lineage=[revision.revision_id],
        reasoning="补充块级 Markdown 格式空白。",
        source_content_fingerprint=content_fingerprint(document.markdown),
    )

    result = CandidateValidator().validate(revision, candidate)

    assert result.accepted
    assert result.changed_block_ids == [str(block.id)]
    materialized = materialize_candidate(document, candidate)
    assert materialized.blocks[0].markdown.endswith("  ")
    assert block.markdown + "  " in materialized.markdown
    assert materialized.markdown == document.markdown.replace(
        block.markdown, block.markdown + "  ", 1
    )


@pytest.mark.parametrize(
    ("source", "changed"),
    [
        ("Date 2026-08-18", "Date 2026/08/18"),
        ("x = a+b", "x = a-b"),
        ("ratio >= 99%", "ratio <= 99%"),
        ("price $99", "price €99"),
        ("Use `x=a+b`", "Use `x=a-b`"),
        ("![](assets/chart-1.png)", "![](assets/chart-2.png)"),
        ("[site](https://example.test/?x=1)", "[site](https://example.test/?x=2)"),
        ('<span data-x="1">Text</span>', '<span data-x="2">Text</span>'),
        ("```python\nx=a+b\n```", "```python\nx=a-b\n```"),
        ("Formula $a+b$", "Formula $a-b$"),
    ],
)
def test_content_fingerprint_preserves_semantic_punctuation_and_payloads(
    source, changed
):
    assert content_fingerprint(source) != content_fingerprint(changed)


@pytest.mark.parametrize(
    ("source", "formatted"),
    [
        ("Important text", "**Important** text"),
        ("alpha  beta", "alpha\nbeta"),
        ("value\n", "value  \n"),
    ],
)
def test_content_fingerprint_allows_markdown_decoration_and_whitespace(
    source, formatted
):
    assert content_fingerprint(source) == content_fingerprint(formatted)


def test_candidate_validator_rejects_punctuation_only_block_change():
    document = _load()
    revision = InMemoryRevisionStore().open(document)
    block = document.blocks[0]
    assert "TR-2026-08" in block.markdown
    changed_markdown = block.markdown.replace("TR-2026-08", "TR/2026/08")
    candidate = RepairedDocumentCandidate(
        base_revision=revision.revision_id,
        repaired_markdown=document.markdown,
        block_markdown={str(block.id): changed_markdown},
        affected_ids=[str(block.id)],
        lineage=[revision.revision_id],
        reasoning="不应把日期和编号分隔符当作无关格式。",
        source_content_fingerprint=content_fingerprint(document.markdown),
    )

    result = CandidateValidator().validate(revision, candidate)

    assert not result.accepted
    assert any("block" in error and "事实词元" in error for error in result.errors)


def test_candidate_validator_rejects_fact_change():
    document = _load()
    revision, candidate = _candidate(document, markdown=document.markdown + "\n新增事实 999")

    result = CandidateValidator().validate(revision, candidate)

    assert not result.accepted
    assert "事实词元" in "".join(result.errors)


def test_candidate_validator_accepts_block_order_patch():
    document = _load()
    store = InMemoryRevisionStore()
    revision = store.open(document)
    first, second = document.blocks[:2]
    candidate = RepairedDocumentCandidate(
        base_revision=revision.revision_id,
        operations=[
            RepairOperation(
                operation="move_block",
                block_id=str(second.id),
                before_block_id=str(first.id),
            )
        ],
        affected_ids=[str(second.id), str(first.id)],
        lineage=[revision.revision_id],
        reasoning="根据页面证据恢复阅读顺序。",
        source_content_fingerprint=content_fingerprint(document.markdown),
        change_kind="structure",
    )

    result = CandidateValidator().validate(revision, candidate)

    assert result.accepted
    assert str(second.id) in result.changed_block_ids
    materialized = materialize_candidate(document, candidate)
    assert materialized.markdown.index(second.markdown) < materialized.markdown.index(
        first.markdown
    )


def test_candidate_validator_accepts_table_layout_patch_without_fact_change():
    document = ParsedDocument.model_validate_json(
        (FIXTURES / "sdp-004-docling.json").read_text(encoding="utf-8")
    )
    store = InMemoryRevisionStore()
    revision = store.open(document)
    table = document.tables[0]
    cells = [
        TableCellPatch(
            text=cell.text,
            start_row=cell.start_row,
            start_col=cell.start_col,
            row_span=cell.row_span,
            col_span=cell.col_span,
            column_header=not cell.column_header if cell.start_row == 0 else cell.column_header,
            row_header=cell.row_header,
        )
        for cell in table.cells
    ]
    candidate = RepairedDocumentCandidate(
        base_revision=revision.revision_id,
        operations=[
            RepairOperation(
                operation="replace_table_cells",
                table_id=table.table_id,
                cells=cells,
            )
        ],
        affected_ids=[table.table_id],
        lineage=[revision.revision_id],
        reasoning="修复表头标记但保留所有单元格事实文本。",
        source_content_fingerprint=content_fingerprint(document.markdown),
        change_kind="structure",
    )

    result = CandidateValidator().validate(revision, candidate)

    assert result.accepted
    assert result.changed_table_ids == [table.table_id]


def test_candidate_validator_rejects_table_fact_change():
    document = ParsedDocument.model_validate_json(
        (FIXTURES / "sdp-004-docling.json").read_text(encoding="utf-8")
    )
    store = InMemoryRevisionStore()
    revision = store.open(document)
    table = document.tables[0]
    cells = [
        TableCellPatch(
            text=("新增事实 999" if index == 0 else cell.text),
            start_row=cell.start_row,
            start_col=cell.start_col,
            row_span=cell.row_span,
            col_span=cell.col_span,
            column_header=cell.column_header,
            row_header=cell.row_header,
        )
        for index, cell in enumerate(table.cells)
    ]
    candidate = RepairedDocumentCandidate(
        base_revision=revision.revision_id,
        operations=[
            RepairOperation(
                operation="replace_table_cells",
                table_id=table.table_id,
                cells=cells,
            )
        ],
        affected_ids=[table.table_id],
        lineage=[revision.revision_id],
        reasoning="不应修改表格事实。",
        source_content_fingerprint=content_fingerprint(document.markdown),
        change_kind="structure",
    )

    result = CandidateValidator().validate(revision, candidate)

    assert not result.accepted
    assert any("单元格事实文本" in error for error in result.errors)


def test_candidate_validator_rejects_table_punctuation_only_change():
    document = ParsedDocument.model_validate_json(
        (FIXTURES / "sdp-004-docling.json").read_text(encoding="utf-8")
    )
    revision = InMemoryRevisionStore().open(document)
    table = document.tables[0]
    cells = [
        TableCellPatch(
            text=cell.text.replace("-20-70 C", "/20/70 C"),
            start_row=cell.start_row,
            start_col=cell.start_col,
            row_span=cell.row_span,
            col_span=cell.col_span,
            column_header=cell.column_header,
            row_header=cell.row_header,
        )
        for cell in table.cells
    ]
    assert any(before.text != after.text for before, after in zip(table.cells, cells))
    candidate = RepairedDocumentCandidate(
        base_revision=revision.revision_id,
        operations=[
            RepairOperation(
                operation="replace_table_cells",
                table_id=table.table_id,
                cells=cells,
            )
        ],
        affected_ids=[table.table_id],
        lineage=[revision.revision_id],
        reasoning="不应改变温度范围中的符号。",
        source_content_fingerprint=content_fingerprint(document.markdown),
        change_kind="structure",
    )

    result = CandidateValidator().validate(revision, candidate)

    assert not result.accepted
    assert any("单元格事实文本" in error for error in result.errors)


def test_candidate_validator_allows_removing_exact_duplicate_block():
    document = _load()
    duplicate = document.blocks[0].model_copy(
        update={"id": uuid4(), "order_index": len(document.blocks)}
    )
    document = document.model_copy(update={"blocks": [*document.blocks, duplicate]})
    revision = InMemoryRevisionStore().open(document)
    candidate = RepairedDocumentCandidate(
        base_revision=revision.revision_id,
        operations=[
            RepairOperation(operation="remove_block", block_id=str(duplicate.id))
        ],
        affected_ids=[str(duplicate.id)],
        lineage=[revision.revision_id],
        reasoning="删除有完全重复证据的解析 block。",
        source_content_fingerprint=content_fingerprint(document.markdown),
        change_kind="structure",
    )

    result = CandidateValidator().validate(revision, candidate)

    assert result.accepted
    assert result.changed_block_ids == [str(duplicate.id)]
    materialized = materialize_candidate(document, candidate)
    assert materialized.markdown == document.markdown
    assert len(materialized.blocks) == len(document.blocks) - 1


def test_incremental_table_layout_patch_preserves_source_cell_text():
    document = ParsedDocument.model_validate_json(
        (FIXTURES / "sdp-004-docling.json").read_text(encoding="utf-8")
    )
    toolbox = QualityToolbox.open(document)
    table = document.tables[0]
    cell = table.cells[0]
    patch = TableCellLayoutPatch(
        cell_index=0,
        start_row=cell.start_row,
        start_col=cell.start_col,
        row_span=cell.row_span,
        col_span=cell.col_span,
        column_header=not cell.column_header,
        row_header=cell.row_header,
        expected_text_sha256=sha256(
            cell.text.encode("utf-8")
        ).hexdigest(),
    )
    candidate = RepairedDocumentCandidate(
        base_revision=toolbox.current_revision.revision_id,
        operations=[
            RepairOperation(
                operation="update_table_cell_layout",
                table_id=table.table_id,
                cell_layout_patches=[patch],
            )
        ],
        affected_ids=[],
        lineage=[toolbox.current_revision.revision_id],
        reasoning="只调整已有单元格的表头角色，不重写正文。",
        change_kind="structure",
    )

    validation = toolbox.validate_candidate(candidate)
    materialized = materialize_candidate(document, candidate)

    assert validation["accepted"] is True
    assert validation["changed_table_ids"] == [table.table_id]
    assert materialized.tables[0].cells[0].text == cell.text
    assert materialized.tables[0].cells[0].column_header is (not cell.column_header)


def test_incremental_table_layout_patch_rejects_stale_text_fingerprint():
    document = ParsedDocument.model_validate_json(
        (FIXTURES / "sdp-004-docling.json").read_text(encoding="utf-8")
    )
    revision = InMemoryRevisionStore().open(document)
    table = document.tables[0]
    cell = table.cells[0]
    candidate = RepairedDocumentCandidate(
        base_revision=revision.revision_id,
        operations=[
            RepairOperation(
                operation="update_table_cell_layout",
                table_id=table.table_id,
                cell_layout_patches=[
                    TableCellLayoutPatch(
                        cell_index=0,
                        start_row=cell.start_row,
                        start_col=cell.start_col,
                        expected_text_sha256="0" * 64,
                    )
                ],
            )
        ],
        affected_ids=[table.table_id],
        lineage=[revision.revision_id],
        reasoning="过期候选不得覆盖当前表格。",
        change_kind="structure",
    )

    result = CandidateValidator().validate(revision, candidate)

    assert not result.accepted
    assert any("正文指纹" in error for error in result.errors)


def test_candidate_validator_rejects_root_only_block_format_change():
    document = _load()
    revision = InMemoryRevisionStore().open(document)
    block = document.blocks[0]
    repaired = document.markdown.replace(
        block.markdown, f"**{block.markdown}**", 1
    )
    candidate = RepairedDocumentCandidate(
        base_revision=revision.revision_id,
        repaired_markdown=repaired,
        lineage=[revision.revision_id],
        reasoning="不应绕过 block 投影直接修改块内格式。",
        source_content_fingerprint=content_fingerprint(document.markdown),
    )

    result = CandidateValidator().validate(revision, candidate)

    assert not result.accepted
    assert any("block token" in error for error in result.errors)


def test_candidate_validator_rejects_unmapped_block_update():
    document = ParsedDocument.model_validate_json(
        (FIXTURES / "sdp-004-docling.json").read_text(encoding="utf-8")
    )
    block = next(
        item
        for item in document.blocks
        if item.markdown and item.markdown not in document.markdown
    )
    revision = InMemoryRevisionStore().open(document)
    candidate = RepairedDocumentCandidate(
        base_revision=revision.revision_id,
        operations=[
            RepairOperation(
                operation="update_block_markdown",
                block_id=str(block.id),
                markdown=f"**{block.markdown}**",
            )
        ],
        affected_ids=[str(block.id)],
        lineage=[revision.revision_id],
        reasoning="无法映射的 block 不得猜测性回写根 Markdown。",
        source_content_fingerprint=content_fingerprint(document.markdown),
    )

    result = CandidateValidator().validate(revision, candidate)

    assert not result.accepted
    assert any("无法精确映射" in error for error in result.errors)


def test_heading_level_patch_updates_block_and_root_markdown():
    document = ParsedDocument.model_validate_json(
        (FIXTURES / "sdp-006-docling.json").read_text(encoding="utf-8")
    )
    heading = next(block for block in document.blocks if block.kind.value == "heading")
    revision = InMemoryRevisionStore().open(document)
    new_level = 2 if heading.heading_level != 2 else 3
    candidate = RepairedDocumentCandidate(
        base_revision=revision.revision_id,
        operations=[
            RepairOperation(
                operation="update_heading_level",
                block_id=str(heading.id),
                heading_level=new_level,
            )
        ],
        affected_ids=[str(heading.id)],
        lineage=[revision.revision_id],
        reasoning="同步修复标题层级字段和 Markdown 标记。",
        source_content_fingerprint=content_fingerprint(document.markdown),
        change_kind="structure",
    )

    result = CandidateValidator().validate(revision, candidate)
    materialized = materialize_candidate(document, candidate)
    updated = next(block for block in materialized.blocks if block.id == heading.id)

    assert result.accepted
    assert updated.heading_level == new_level
    assert updated.markdown.startswith("#" * new_level + " ")
    assert updated.markdown in materialized.markdown


def test_conflicting_root_markdown_and_block_operation_is_rejected():
    document = _load()
    block = document.blocks[0]
    revision = InMemoryRevisionStore().open(document)
    candidate = RepairedDocumentCandidate(
        base_revision=revision.revision_id,
        repaired_markdown=document.markdown + "\n",
        operations=[
            RepairOperation(
                operation="update_block_markdown",
                block_id=str(block.id),
                markdown=f"**{block.markdown}**",
            )
        ],
        affected_ids=[str(block.id)],
        lineage=[revision.revision_id],
        reasoning="冲突的双重 Markdown 来源必须被拒绝。",
        source_content_fingerprint=content_fingerprint(document.markdown),
    )

    result = CandidateValidator().validate(revision, candidate)

    assert not result.accepted
    assert any("冲突" in error for error in result.errors)


def test_committed_block_update_reaches_optimized_and_canonical_outputs():
    document = _load()
    toolbox = QualityToolbox.open(document)
    revision = toolbox.current_revision
    block = document.blocks[0]
    changed = f"**{block.markdown}**"
    candidate = RepairedDocumentCandidate(
        base_revision=revision.revision_id,
        operations=[
            RepairOperation(
                operation="update_block_markdown",
                block_id=str(block.id),
                markdown=changed,
            )
        ],
        affected_ids=[str(block.id)],
        lineage=[revision.revision_id],
        reasoning="同步修复 block 与根 Markdown。",
        source_content_fingerprint=content_fingerprint(document.markdown),
    )

    validation = toolbox.validate_candidate(candidate)
    toolbox.commit_revision(candidate)
    package = toolbox.build_quality_package()

    assert validation["accepted"] is True
    assert changed in package["optimized_markdown"]
    assert any(
        item["content"] == changed
        for item in package["canonical_document"]["blocks"]
    )


def test_candidate_validator_rejects_block_fact_change():
    document = _load()
    store = InMemoryRevisionStore()
    revision = store.open(document)
    block = document.blocks[0]
    candidate = RepairedDocumentCandidate(
        base_revision=revision.revision_id,
        repaired_markdown=document.markdown,
        block_markdown={str(block.id): block.markdown + " 新增事实 999"},
        affected_ids=[str(block.id)],
        lineage=[revision.revision_id],
        reasoning="错误地修改了块内容。",
        source_content_fingerprint=content_fingerprint(document.markdown),
    )

    result = CandidateValidator().validate(revision, candidate)

    assert not result.accepted
    assert any("block" in error and "事实词元" in error for error in result.errors)


def test_run_repair_commits_fake_candidate_and_preserves_hashes():
    document = _load()
    revision, candidate = _candidate(document, markdown=document.markdown.replace("\n", "\n\n", 1))
    execution = run_repair(
        document,
        agent=FakeRepairAgent([candidate]),
        agent_config=RepairAgentConfig(max_rounds=1),
    )

    assert execution.accepted
    assert execution.final_revision_id != revision.revision_id
    assert execution.attempts[0].accepted
    assert execution.package.quality_report.metrics["agent"]["accepted"] is True
    assert execution.package.package_manifest.artifacts["quality_report.json"]
    assert execution.package.quality_report.model_dump()


def test_run_repair_rejects_bad_candidate_and_falls_back():
    document = _load()
    _, candidate = _candidate(document, markdown=document.markdown + "\n新增事实 999")
    execution = run_repair(
        document,
        agent=FakeRepairAgent([candidate]),
        agent_config=RepairAgentConfig(max_rounds=1),
    )

    assert not execution.accepted
    assert execution.attempts[0].code == "rejected_candidate"
    assert execution.package.optimized_markdown == run_quality(document).optimized_markdown
    assert execution.package.quality_report.metrics["agent"]["accepted"] is False


def test_document_repair_accepts_no_op_without_committing_revision():
    document = _load()
    captured = []
    events = []

    def factory(toolbox):
        captured.append(toolbox)
        revision_id = toolbox.current_revision.revision_id
        candidate = RepairedDocumentCandidate(
            base_revision=revision_id,
            repaired_markdown=None,
            lineage=[revision_id],
            reasoning="整篇检查完成，无需修改。",
            change_kind="none",
        )
        return FakeRepairAgent([candidate])

    execution = run_repair(
        document,
        agent_factory=factory,
        agent_config=RepairAgentConfig(
            max_rounds=1,
            mode="document",
            progress_callback=events.append,
        ),
    )

    revision = captured[0].current_revision
    assert execution.accepted
    assert execution.attempts[0].accepted
    assert execution.attempts[0].no_progress
    assert execution.final_revision_id == revision.revision_id
    assert revision.parent_revision_id is None
    assert revision.attempt == 0
    assert len(captured[0].store._revisions) == 1
    assert execution.package.quality_report.metrics["agent"]["stop_reason"] == "no_progress"
    assert events[-1].status == "completed"
    assert events[-1].message == "整篇文档检查完成，无需修改"


def test_toolbox_no_op_commit_reports_unchanged_without_self_parent():
    document = _load()
    toolbox = QualityToolbox.open(document)
    revision = toolbox.current_revision
    candidate = RepairedDocumentCandidate(
        base_revision=revision.revision_id,
        repaired_markdown=None,
        lineage=[revision.revision_id],
        reasoning="整篇检查完成，无需修改。",
        change_kind="none",
    )

    result = toolbox.commit_revision(candidate)

    assert result == {
        "status": "unchanged",
        "revision_id": revision.revision_id,
        "parent_revision_id": None,
    }
    assert toolbox.current_revision is revision
    assert toolbox.current_revision.attempt == 0
    assert len(toolbox.store._revisions) == 1


def test_revision_store_refuses_same_digest_commit():
    document = _load()
    store = InMemoryRevisionStore()
    revision = store.open(document)
    candidate = RepairedDocumentCandidate(
        base_revision=revision.revision_id,
        repaired_markdown=None,
        lineage=[revision.revision_id],
        reasoning="整篇检查完成，无需修改。",
        change_kind="none",
    )

    committed = store.commit(revision, document, candidate)

    assert committed is revision
    assert committed.parent_revision_id is None
    assert committed.attempt == 0
    assert store._revisions[revision.revision_id] is revision


def test_run_repair_factory_receives_the_runtime_toolbox():
    document = _load()
    captured = []

    def factory(toolbox):
        captured.append(toolbox)
        revision = toolbox.current_revision
        candidate = RepairedDocumentCandidate(
            base_revision=revision.revision_id,
            repaired_markdown=document.markdown.replace("\n", "\n\n", 1),
            lineage=[revision.revision_id],
            reasoning="只调整格式。",
            source_content_fingerprint=content_fingerprint(document.markdown),
        )
        return FakeRepairAgent([candidate])

    execution = run_repair(
        document,
        agent_factory=factory,
        agent_config=RepairAgentConfig(max_rounds=1),
    )

    assert execution.accepted
    assert len(captured) == 1
    assert captured[0].current_revision.revision_id == execution.final_revision_id


def test_paged_repair_emits_page_progress_and_requires_page_scope():
    document = ParsedDocument.model_validate_json(
        (FIXTURES / "sdp-005-docling.json").read_text(encoding="utf-8")
    )
    events = []

    class PageNoOpAgent:
        def run(self, context, *, feedback=None):
            assert context.focus_page is not None
            return RepairedDocumentCandidate(
                base_revision=context.revision_id,
                scope="page",
                scope_pages=[context.focus_page],
                lineage=[context.revision_id],
                reasoning="本页没有需要安全修改的结构问题。",
                change_kind="none",
            )

    execution = run_repair(
        document,
        agent=PageNoOpAgent(),
        agent_config=RepairAgentConfig(
            max_rounds=1,
            mode="paged",
            progress_callback=events.append,
        ),
    )

    assert execution.accepted
    assert len(execution.attempts) == 5
    completed = [event for event in events if event.stage == "page" and event.status == "completed"]
    assert [event.page_number for event in completed] == [1, 2, 3, 4, 5]
    assert completed[-1].completed_pages == completed[-1].total_pages == 5


def test_run_quality_repair_requires_explicit_agent():
    document = _load()

    with pytest.raises(QualityAgentNotConfigured):
        run_quality_repair(document)

    assert run_quality(document).optimized_markdown


def test_public_detailed_repair_preserves_compatible_package_entrypoint():
    document = _load()
    _, candidate = _candidate(document)
    package = run_quality_repair(
        document,
        agent=FakeRepairAgent([candidate]),
        agent_config=RepairAgentConfig(max_rounds=1),
    )
    execution = run_quality_repair_detailed(
        document,
        agent=FakeRepairAgent([candidate]),
        agent_config=RepairAgentConfig(
            max_rounds=1,
            session_id="qa-observability-session",
        ),
    )

    assert package.document_id == execution.package.document_id
    assert isinstance(execution, RepairExecution)
    assert execution.accepted
    assert execution.session_id == "qa-observability-session"
    assert execution.attempts[0].no_progress
    assert (
        execution.package.quality_report.metrics["agent"]["session_id"]
        == execution.session_id
    )


@pytest.mark.parametrize(
    ("exception", "expected_code"),
    [
        (TimeoutError("secret provider response"), "agent_timeout"),
        (
            type("ProviderFailure", (RuntimeError,), {"__module__": "openai"})(
                "secret provider response"
            ),
            "provider_error",
        ),
        (RuntimeError("secret provider response"), "agent_error"),
    ],
)
def test_public_detailed_repair_classifies_and_redacts_agent_errors(
    exception, expected_code
):
    document = _load()

    class FailingAgent:
        def run(self, context, *, feedback=None):
            raise exception

    execution = run_quality_repair_detailed(
        document,
        agent=FailingAgent(),
        agent_config=RepairAgentConfig(
            max_rounds=1,
            session_id="qa-redaction-session",
        ),
    )

    assert not execution.accepted
    assert execution.attempts[0].code == expected_code
    assert "secret provider response" not in execution.attempts[0].model_dump_json()
    assert execution.package.quality_report.metrics["agent"]["last_code"] == expected_code


def test_public_detailed_repair_classifies_candidate_schema_errors():
    document = _load()

    class InvalidCandidateAgent:
        def run(self, context, *, feedback=None):
            return {}

    execution = run_quality_repair_detailed(
        document,
        agent=InvalidCandidateAgent(),
        agent_config=RepairAgentConfig(max_rounds=1),
    )

    assert not execution.accepted
    assert execution.attempts[0].code == "candidate_schema_error"
    assert execution.session_id


def test_schema_error_retries_with_feedback_and_can_recover():
    document = _load()

    class RetrySchemaAgent:
        calls = 0

        def run(self, context, *, feedback=None):
            self.calls += 1
            if self.calls == 1:
                raise CandidateSchemaError('{"base_revision":')
            assert feedback is not None
            assert feedback.code == "candidate_schema_error"
            return RepairedDocumentCandidate(
                base_revision=context.revision_id,
                lineage=[context.revision_id],
                reasoning="Schema 重试后确认无需修改。",
                change_kind="none",
            )

    agent = RetrySchemaAgent()
    execution = run_quality_repair_detailed(
        document,
        agent=agent,
        agent_config=RepairAgentConfig(max_rounds=2),
    )

    assert execution.accepted
    assert agent.calls == 2
    assert [attempt.code for attempt in execution.attempts] == [
        "candidate_schema_error",
        "accepted",
    ]
    assert execution.attempts[0].no_progress is False


def test_public_detailed_repair_contains_redacted_validator_failures():
    document = _load()

    class BrokenValidator:
        def validate(self, revision, candidate, *, expected_page=None):
            raise RuntimeError("secret document body")

    def factory(toolbox):
        toolbox.validator = BrokenValidator()
        revision_id = toolbox.current_revision.revision_id
        return FakeRepairAgent(
            [
                RepairedDocumentCandidate(
                    base_revision=revision_id,
                    repaired_markdown=None,
                    lineage=[revision_id],
                    reasoning="验证器异常测试。",
                    change_kind="none",
                )
            ]
        )

    execution = run_quality_repair_detailed(
        document,
        agent_factory=factory,
        agent_config=RepairAgentConfig(max_rounds=1),
    )

    assert not execution.accepted
    assert execution.attempts[0].code == "validator_error"
    assert "secret document body" not in execution.attempts[0].model_dump_json()


def test_document_index_groups_real_parser_results_by_page():
    docling = ParsedDocument.model_validate_json(
        (FIXTURES / "sdp-005-docling.json").read_text(encoding="utf-8")
    )
    mineru = ParsedDocument.model_validate_json(
        (FIXTURES / "sdp-005-mineru.json").read_text(encoding="utf-8")
    )

    for document in (docling, mineru):
        index = DocumentIndex.from_document(document)
        assert index.total_pages == 5
        assert index.page(1) is not None
        assert index.page(2) is not None
        assert index.page(1).table_ids
        assert index.page(2).table_ids
        assert "第 1 页" in index.to_prompt()


def test_document_index_records_missing_page_provenance():
    document = ParsedDocument.model_validate_json(
        (FIXTURES / "sdp-012-docling.json").read_text(encoding="utf-8")
    )

    index = DocumentIndex.from_document(document)

    assert index.total_pages == 0
    assert len(index.unknown_block_ids) == len(document.blocks)
    assert len(index.unknown_table_ids) == len(document.tables)


def test_context_is_bounded_and_contains_revision():
    document = _load()
    revision = InMemoryRevisionStore().open(document)
    context = DocumentContextBuilder(max_blocks=1, block_chars=20).build(revision)

    prompt = context.to_prompt(max_chars=500)

    assert revision.revision_id in prompt
    assert "json" in prompt
    assert "<document_index>" in context.to_prompt()
    assert len(context.block_summaries) == 1
    assert len(prompt) <= 500


def test_prompt_template_keeps_output_contract_when_context_is_truncated():
    document = _load()
    revision = InMemoryRevisionStore().open(document)
    context = DocumentContextBuilder(max_blocks=80, block_chars=500).build(
        revision,
        max_context_chars=5000,
    )

    prompt = context.to_prompt()

    assert len(prompt) <= 5000
    assert "<output>" in prompt
    assert "[context truncated]" in prompt


def test_context_builder_applies_configured_max_context_chars():
    document = _load()
    revision = InMemoryRevisionStore().open(document)
    context = DocumentContextBuilder(max_blocks=80, block_chars=500).build(
        revision,
        max_context_chars=100,
    )

    assert len(context.to_prompt()) <= 100


def test_read_tools_expose_only_bounded_read_context():
    document = _load()
    revision = InMemoryRevisionStore().open(document)
    tools = DocumentReadTools(revision, max_chars=40)

    summary = tools.get_document_summary()
    region = tools.get_region_context([str(document.blocks[0].id)])
    digest = tools.get_revision_digest()

    assert summary["revision_id"] == revision.revision_id
    assert region[0]["block_id"] == str(document.blocks[0].id)
    assert len(region[0]["markdown"]) <= 40
    assert digest["content_fingerprint"] == content_fingerprint(document.markdown)
    assert len(tools.as_agno_tools()) == 10


def test_skill_playbooks_follow_standard_contract():
    for skill_id in available_skill_ids():
        skill = load_skill(skill_id)
        assert skill.startswith("---\n")
        assert f"skill_id: {skill_id}" in skill
        for field in ("purpose:", "applies_to:", "priority:"):
            assert field in skill
        for section in ("## 1.", "## 2.", "## 4.", "## 5."):
            assert section in skill

    rendered = render_skills(("document_quality_repair", "table_structure"))
    assert '<quality_skill id="document_quality_repair">' in rendered
    assert '<quality_skill id="table_structure">' in rendered


def test_read_tools_expose_page_and_cross_page_context():
    document = ParsedDocument.model_validate_json(
        (FIXTURES / "sdp-005-mineru.json").read_text(encoding="utf-8")
    )
    revision = InMemoryRevisionStore().open(document)
    tools = DocumentReadTools(revision, max_chars=4000)

    page = tools.get_page_context(2, include_neighbors=True)
    assert page["found"] is True
    assert page["page_number"] == 2
    assert page["blocks"]
    assert page["tables"]
    assert page["neighbors"]

    table_ids = page["index"]["table_ids"]
    assert tools.get_cross_page_table_context(table_ids)


def test_relation_patch_is_validated_and_projected_to_canonical():
    document = _load()
    toolbox = QualityToolbox.open(document)
    revision = toolbox.current_revision
    block_ids = [str(block.id) for block in document.blocks[:2]]
    relation = RelationPatch(
        relation_type="reference_of",
        from_id=block_ids[0],
        to_id=block_ids[1],
    )
    candidate = RepairedDocumentCandidate(
        base_revision=revision.revision_id,
        operations=[RepairOperation(operation="upsert_relation", relation=relation)],
        affected_relation_keys=[relation.key()],
        lineage=[revision.revision_id],
        reasoning="依据正文 marker 与参考文献 block 的唯一证据建立关系。",
        source_content_fingerprint=content_fingerprint(document.markdown),
        change_kind="structure",
    )

    validation = toolbox.validate_candidate(candidate)
    assert validation["accepted"] is True
    toolbox.commit_revision(candidate)
    relations = toolbox.build_quality_package()["canonical_document"]["relations"]
    assert any(
        relation_item["relation_type"] == "reference_of"
        and relation_item["status"] == "inferred"
        for relation_item in relations
    )


def test_asset_reference_patch_preserves_asset_and_adds_relation():
    document = _load()
    block_id = str(document.blocks[0].id)
    asset = DocumentAsset(
        path="images/figure-1.png",
        kind=AssetKind.IMAGE,
        file_type="image/png",
        content=b"fixture",
        anchor=SourceAnchor(page_number=1),
    )
    document = document.model_copy(update={"assets": [asset]})
    toolbox = QualityToolbox.open(document)
    revision = toolbox.current_revision
    candidate = RepairedDocumentCandidate(
        base_revision=revision.revision_id,
        operations=[
            RepairOperation(
                operation="update_asset_references",
                asset_path=asset.path,
                referenced_by_block_ids=[block_id],
            )
        ],
        affected_asset_paths=[asset.path],
        lineage=[revision.revision_id],
        reasoning="依据图片与图注的同页 bbox 关系恢复已有资源归属。",
        source_content_fingerprint=content_fingerprint(document.markdown),
        change_kind="structure",
    )

    validation = toolbox.validate_candidate(candidate)
    assert validation["accepted"] is True
    toolbox.commit_revision(candidate)
    current_asset = toolbox.current_revision.document.assets[0]
    assert current_asset.referenced_by_block_ids == [block_id]
    relations = toolbox.build_quality_package()["canonical_document"]["relations"]
    assert any(item["relation_type"] == "asset_referenced_by" for item in relations)


def test_quality_toolbox_requires_validation_before_commit():
    document = _load()
    toolbox = QualityToolbox.open(document)
    revision = toolbox.current_revision
    candidate = RepairedDocumentCandidate(
        base_revision=revision.revision_id,
        repaired_markdown=document.markdown.replace("\n", "\n\n", 1),
        lineage=[revision.revision_id],
        reasoning="格式调整。",
        source_content_fingerprint=content_fingerprint(document.markdown),
    )

    result = toolbox.validate_candidate(candidate)
    committed = toolbox.commit_revision(candidate)

    assert result["accepted"] is True
    assert committed["status"] == "committed"
    assert committed["revision_id"] != revision.revision_id
    assert toolbox.build_quality_package()["document_id"] == str(document.document_id)

    agent_tool_names = {tool.__name__ for tool in toolbox.as_agno_tools()}
    assert len(agent_tool_names) == 14
    assert "get_quality_diagnostics" in agent_tool_names
    assert {"commit_revision", "rollback_revision", "build_quality_package"}.isdisjoint(agent_tool_names)


def test_toolbox_normalizes_model_affected_ids_from_materialized_patch():
    document = _load()
    toolbox = QualityToolbox.open(document)
    block = document.blocks[0]
    candidate = RepairedDocumentCandidate(
        base_revision=toolbox.current_revision.revision_id,
        operations=[
            RepairOperation(
                operation="update_block_markdown",
                block_id=str(block.id),
                markdown=f"**{block.markdown}**",
            )
        ],
        affected_ids=["model-declared-wrong-id"],
        lineage=[toolbox.current_revision.revision_id],
        reasoning="依据标题编号修复层级。",
        change_kind="structure",
    )

    validation = toolbox.validate_candidate(candidate)

    assert validation["accepted"] is True
    assert validation["changed_block_ids"] == [str(block.id)]
    assert toolbox.last_candidate is not None
    assert toolbox.last_candidate.affected_ids == [str(block.id)]


def test_quality_diagnostics_are_injected_into_agent_prompt():
    document = _load()
    toolbox = QualityToolbox.open(document)
    diagnostics = toolbox.get_quality_diagnostics()
    context = DocumentContextBuilder().build(
        toolbox.current_revision,
        quality_diagnostics=diagnostics,
    )

    prompt = context.to_prompt()

    assert "<quality_diagnostics>" in prompt
    assert diagnostics["quality_state"] in prompt
    assert diagnostics["issues"]
    assert diagnostics["issues"][0]["category"] in prompt


def test_deepseek_config_uses_project_env_names_without_printing_secret():
    config = load_deepseek_config(
        {
            "LLM_API_KEY": "secret-value",
            "LLM_API_BASE": "https://api.deepseek.com/",
            "LLM_MODEL": "deepseek-v4-flash",
        },
        load_dotenv_file=False,
    )
    assert config == DeepSeekConfig(
        api_key="secret-value",
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
    )


def test_deepseek_config_requires_key():
    with pytest.raises(LLMConfigurationError):
        load_deepseek_config({}, load_dotenv_file=False)


def test_deepseek_model_uses_compatible_roles_and_json_object():
    model = build_deepseek_model(
        DeepSeekConfig(api_key="secret-value", model="deepseek-v4-flash")
    )
    assert model.role_map["system"] == "system"
    assert model.role_map["user"] == "user"
    assert model.get_request_params(RepairedDocumentCandidate)["response_format"] == {
        "type": "json_object"
    }
    assert model.extra_body == {"thinking": {"type": "disabled"}}
    assert model.temperature == 0.0
    assert model.max_tokens == 4096
    assert model.max_retries == 2
    assert model.timeout == 60.0
