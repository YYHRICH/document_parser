"""面向真实模型失败模式的质量硬检测。"""

from __future__ import annotations

import re

from document_parser.domain.model.contracts import (
    BlockKind,
    IssueSeverity,
    IssueStatus,
    QualityCapabilityState,
)

from ..evidence.context import EvidenceContext
from ..evidence.requirements import EvidenceRequirement
from ..models_internal import (
    CapabilityObservation,
    EvidenceRef,
    IssueDraft,
    RepairProposal,
    RuleResult,
)
from ..renderers.table_markdown import render_anchor_copy_table
from ..repairs.table_html import table_needs_html_conversion
from .base import QualityRule


class QL_CONT_004_EmptyNormalizedContent(QualityRule):
    """成功解析但规范正文为空时阻止入库。"""

    rule_id = "QL-CONT-004"
    required_evidence = (EvidenceRequirement(kind="blocks", required_state="available"),)

    def execute(self, context: EvidenceContext) -> RuleResult:
        parsed = context.parsed
        if parsed.blocks and not parsed.markdown.strip():
            return RuleResult(
                issues=(
                    IssueDraft(
                        severity=IssueSeverity.CRITICAL,
                        category="content_completeness",
                        message="解析状态有结果但规范正文为空，禁止交给 Wiki。",
                        affected_block_ids=[str(block.id) for block in parsed.blocks],
                        evidence_refs=[
                            EvidenceRef(
                                object_type="document",
                                object_id=str(parsed.document_id),
                                field_path="markdown",
                            )
                        ],
                    ),
                )
            )
        return RuleResult()


class QL_FMT_001_MojibakeDetected(QualityRule):
    """检测系统性乱码、替换字符和不可打印控制字符。"""

    rule_id = "QL-FMT-001"
    required_evidence = (EvidenceRequirement(kind="blocks", required_state="available"),)
    _MARKERS = ("Ã", "Â", "â€", "ðŸ", "ï¿½")

    def execute(self, context: EvidenceContext) -> RuleResult:
        text = context.parsed.markdown
        replacement_count = text.count("\ufffd")
        marker_count = sum(text.count(marker) for marker in self._MARKERS)
        control_count = sum(
            1
            for char in text
            if ord(char) < 32 and char not in {"\n", "\r", "\t"}
        )
        if replacement_count < 2 and marker_count < 2 and control_count == 0:
            return RuleResult()
        reason = []
        if replacement_count:
            reason.append(f"替换字符 {replacement_count} 个")
        if marker_count:
            reason.append(f"疑似编码标记 {marker_count} 个")
        if control_count:
            reason.append(f"不可打印控制字符 {control_count} 个")
        affected = [
            str(block.id)
            for block in context.parsed.blocks
            if any(marker in block.markdown for marker in self._MARKERS)
            or "\ufffd" in block.markdown
        ]
        return RuleResult(
            issues=(
                IssueDraft(
                    severity=IssueSeverity.CRITICAL,
                    category="content_readability",
                    message="正文存在系统性乱码或不可打印字符（" + "、".join(reason) + "），不得静默修复。",
                    affected_block_ids=affected,
                    evidence_refs=[
                        EvidenceRef(
                            object_type="document",
                            object_id=str(context.parsed.document_id),
                            field_path="markdown",
                        )
                    ],
                ),
            )
        )


class QL_ASSET_001_DataUriRemains(QualityRule):
    """统一结果不得残留 Base64 data URI。"""

    rule_id = "QL-ASSET-001"
    required_evidence = (EvidenceRequirement(kind="blocks", required_state="available"),)

    def execute(self, context: EvidenceContext) -> RuleResult:
        pattern = re.compile(r"data:image/[^,\s]+,", re.IGNORECASE)
        matches = list(pattern.finditer(context.parsed.markdown))
        if not matches:
            return RuleResult()
        affected = [
            str(block.id)
            for block in context.parsed.blocks
            if "data:image/" in block.markdown.lower()
        ]
        return RuleResult(
            issues=(
                IssueDraft(
                    severity=IssueSeverity.CRITICAL,
                    category="asset_integrity",
                    message=f"规范 Markdown 仍包含 {len(matches)} 个 data URI，必须先资源化。",
                    affected_block_ids=affected,
                ),
            )
        )


class QL_ASSET_002_LocalReferenceIntegrity(QualityRule):
    """Markdown 图片引用必须能在 assets 中闭合。"""

    rule_id = "QL-ASSET-002"
    required_evidence = (EvidenceRequirement(kind="blocks", required_state="available"),)

    def execute(self, context: EvidenceContext) -> RuleResult:
        references = re.findall(r"!\[[^\]]*\]\(([^)\s]+)", context.parsed.markdown)
        if not references:
            return RuleResult()
        asset_paths = {asset.path.replace("\\", "/") for asset in context.parsed.assets}
        missing = [
            reference
            for reference in references
            if not reference.lower().startswith(("http://", "https://", "data:"))
            and reference.replace("\\", "/") not in asset_paths
        ]
        if not missing:
            return RuleResult()
        return RuleResult(
            issues=(
                IssueDraft(
                    severity=IssueSeverity.WARNING,
                    category="asset_integrity",
                    message=f"{len(missing)} 个图片引用没有对应 assets 文件。",
                    evidence={"missing_paths": sorted(set(missing))[:50]},
                ),
            )
        )


class QL_TBL_003_EmptyTableStructure(QualityRule):
    """表格存在但没有有效非空单元格时阻止入库。"""

    rule_id = "QL-TBL-003"
    required_evidence = (EvidenceRequirement(kind="tables", required_state="available"),)

    def execute(self, context: EvidenceContext) -> RuleResult:
        issues: list[IssueDraft] = []
        for table in context.parsed.tables:
            if table.cells and any(cell.text.strip() for cell in table.cells):
                continue
            issues.append(
                IssueDraft(
                    severity=IssueSeverity.CRITICAL,
                    category="table_structure",
                    message=f"table {table.table_id} 没有有效非空单元格，禁止绑定字段。",
                    affected_block_ids=[str(table.block_id)],
                    evidence_refs=[
                        EvidenceRef(
                            object_type="table",
                            object_id=table.table_id,
                            field_path="cells",
                        )
                    ],
                )
            )
        return RuleResult(issues=tuple(issues))


class QL_TBL_009_HtmlTableRepresentation(QualityRule):
    """HTML、table block 和 Markdown 表示不一致时生成修复提案。"""

    rule_id = "QL-TBL-009"
    required_evidence = (EvidenceRequirement(kind="tables", required_state="available"),)

    def execute(self, context: EvidenceContext) -> RuleResult:
        issues: list[IssueDraft] = []
        proposals: list[RepairProposal] = []
        evidence_refs: list[EvidenceRef] = []
        representation_valid = True
        for table in context.parsed.tables:
            block = context.block(str(table.block_id))
            evidence_refs.extend(
                [
                    EvidenceRef(
                        object_type="table",
                        object_id=table.table_id,
                        field_path="markdown",
                    ),
                    EvidenceRef(
                        object_type="table",
                        object_id=table.table_id,
                        field_path="grid" if table.grid else "cells",
                    ),
                ]
            )
            document_contains_html = bool(table.html and table.html in context.parsed.markdown)
            if table_needs_html_conversion(table) or document_contains_html:
                representation_valid = False
                issues.append(
                    IssueDraft(
                        severity=IssueSeverity.WARNING,
                        category="table_representation",
                        message=f"table {table.table_id} 的 Markdown 表示仍是 HTML 或为空。",
                        affected_block_ids=[str(table.block_id)],
                        evidence_refs=[
                            EvidenceRef(object_type="table", object_id=table.table_id, field_path="html"),
                            EvidenceRef(object_type="table", object_id=table.table_id, field_path="markdown"),
                        ],
                    )
                )
                if block is not None and block.kind == BlockKind.TABLE:
                    proposals.append(
                        RepairProposal(
                            rule_id="QL-RPR-003",
                            description=f"将 table {table.table_id} 的 HTML 转为 Markdown。",
                            affected_block_ids=[str(table.block_id)],
                            evidence_refs=[
                                EvidenceRef(object_type="table", object_id=table.table_id, field_path="html")
                            ],
                        )
                    )
                continue

            if block is None or block.kind != BlockKind.TABLE:
                representation_valid = False
                issues.append(
                    IssueDraft(
                        severity=IssueSeverity.WARNING,
                        category="table_representation",
                        status=IssueStatus.MANUAL_REVIEW_REQUIRED,
                        message=f"table {table.table_id} 没有唯一对应的表格 block。",
                        affected_block_ids=[str(table.block_id)],
                    )
                )
                continue

            table_markdown = (table.markdown or "").strip()
            block_markdown = block.markdown.strip()
            if table_markdown != block_markdown:
                representation_valid = False
                issues.append(
                    IssueDraft(
                        severity=IssueSeverity.WARNING,
                        category="table_representation",
                        status=IssueStatus.MANUAL_REVIEW_REQUIRED,
                        message=f"table {table.table_id} 的 table.markdown 与表格 block 不一致。",
                        affected_block_ids=[str(table.block_id)],
                    )
                )
            if block_markdown and block_markdown not in context.parsed.markdown:
                representation_valid = False
                issues.append(
                    IssueDraft(
                        severity=IssueSeverity.WARNING,
                        category="table_representation",
                        status=IssueStatus.MANUAL_REVIEW_REQUIRED,
                        message=f"table {table.table_id} 的表格 block 未出现在文档 Markdown 中。",
                        affected_block_ids=[str(table.block_id)],
                    )
                )

            if table.metadata.get("markdown_rendering") == "anchor_copy" and table.grid:
                expected = render_anchor_copy_table(table).strip()
                if expected != table_markdown:
                    representation_valid = False
                    issues.append(
                        IssueDraft(
                            severity=IssueSeverity.WARNING,
                            category="table_representation",
                            status=IssueStatus.MANUAL_REVIEW_REQUIRED,
                            message=f"table {table.table_id} 的 anchor-copy Markdown 与逻辑网格不一致。",
                            affected_block_ids=[str(table.block_id)],
                            evidence_refs=[
                                EvidenceRef(
                                    object_type="table",
                                    object_id=table.table_id,
                                    field_path="grid",
                                )
                            ],
                        )
                    )

            mismatched_source_cells = [
                cell
                for cell in table.cells
                if cell.value_type == "string"
                and isinstance(cell.raw_value, str)
                and "\n" in cell.raw_value.replace("\r\n", "\n").replace("\r", "\n")
                and cell.raw_value.replace("\r\n", "\n").replace("\r", "\n").strip()
                != cell.text.replace("\r\n", "\n").replace("\r", "\n").strip()
            ]
            if mismatched_source_cells:
                representation_valid = False
                issues.append(
                    IssueDraft(
                        severity=IssueSeverity.WARNING,
                        category="table_representation",
                        status=IssueStatus.MANUAL_REVIEW_REQUIRED,
                        message=(
                            f"table {table.table_id} 有 {len(mismatched_source_cells)} 个"
                            "源单元格换行与结构文本不一致。"
                        ),
                        affected_block_ids=[str(table.block_id)],
                        evidence={
                            "table_id": table.table_id,
                            "cell_ids": [
                                cell.cell_id for cell in mismatched_source_cells[:50]
                            ],
                        },
                    )
                )

        observations = (
            CapabilityObservation(
                capability_name="table_representation_reliable",
                observed_state=(
                    QualityCapabilityState.VERIFIED
                    if representation_valid
                    else QualityCapabilityState.MANUAL_REVIEW_REQUIRED
                ),
                evidence_refs=evidence_refs,
            ),
        ) if context.parsed.tables else ()
        return RuleResult(
            issues=tuple(issues),
            repair_proposals=tuple(proposals),
            capability_observations=observations,
        )
