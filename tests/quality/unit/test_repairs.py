"""白名单修复单元测试：等价变换、幂等、no-op 不记录。"""

from __future__ import annotations

from pathlib import Path

from document_parser.core.contracts import ParsedDocument

from quality import run_quality
from quality.repairs.registry import WHITELIST_REPAIRS, apply_repairs, replay_repair, rollback_repair
from quality.repairs.whitelist import (
    QL_RPR_001_TrailingWhitespace,
    QL_RPR_002_TableSeparator,
)

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "quality" / "fixtures" / "parsed_documents"

DOC_KEY = "test-doc-key"


def test_trailing_whitespace_fixed():
    outcome = QL_RPR_001_TrailingWhitespace().apply("# 标题  \n\n正文  \n")
    assert outcome.applied
    assert outcome.after == "# 标题\n\n正文\n"
    assert "2 行" in outcome.description


def test_trailing_whitespace_idempotent():
    rule = QL_RPR_001_TrailingWhitespace()
    first = rule.apply("a  \nb\t\n")
    second = rule.apply(first.after)
    assert first.applied
    assert not second.applied
    assert first.after == second.after


def test_trailing_whitespace_noop_not_applied():
    outcome = QL_RPR_001_TrailingWhitespace().apply("干净文本\n无空白\n")
    assert not outcome.applied


def test_table_separator_column_alignment():
    md = "| 供应商 | 型号 |\n|---|---|---|\n| A | B |\n"
    outcome = QL_RPR_002_TableSeparator().apply(md)
    assert outcome.applied
    assert "|---|---|" in outcome.after  # 分隔行对齐到 2 列
    assert "| 供应商 | 型号 |" in outcome.after  # 表头不变


def test_table_separator_keeps_cell_text():
    md = "| A | B | C |\n|---|--|\n| 1 | 2 | 3 |\n"
    outcome = QL_RPR_002_TableSeparator().apply(md)
    assert outcome.applied
    assert "| 1 | 2 | 3 |" in outcome.after  # 单元格文字不变


def test_table_separator_idempotent():
    rule = QL_RPR_002_TableSeparator()
    md = "| A | B |\n|---|---|---|\n| 1 | 2 |\n"
    first = rule.apply(md)
    second = rule.apply(first.after)
    assert first.applied
    assert not second.applied


def test_table_separator_noop():
    md = "| A | B |\n|---|---|\n| 1 | 2 |\n"
    outcome = QL_RPR_002_TableSeparator().apply(md)
    assert not outcome.applied


def test_apply_repairs_records_only_real_changes():
    md = "正文  \n| A | B |\n|---|---|\n| 1 | 2 |\n"
    result = apply_repairs(md, document_key=DOC_KEY)
    assert result.markdown == "正文\n| A | B |\n|---|---|\n| 1 | 2 |\n"
    assert len(result.applied) == 1
    assert result.applied[0].rule_id == "QL-RPR-001"
    assert result.applied[0].replayable is True
    assert result.applied[0].evidence["before"] != result.applied[0].evidence["after"]


def test_apply_repairs_clean_markdown_noop():
    md = "干净文本\n没有可修复点\n"
    result = apply_repairs(md, document_key=DOC_KEY)
    assert result.markdown == md
    assert result.applied == ()


def test_repair_ids_are_stable():
    md = "正文  \n"
    r1 = apply_repairs(md, document_key=DOC_KEY)
    r2 = apply_repairs(md, document_key=DOC_KEY)
    assert r1.applied[0].repair_id == r2.applied[0].repair_id


def test_whitelist_rules_declared():
    assert {r.rule_id for r in (c() for c in WHITELIST_REPAIRS)} == {
        "QL-RPR-001",
        "QL-RPR-002",
    }


def test_pipeline_repair_idempotent_on_real_fixture():
    """同一 fixture 跑两次：第二次不再产生相同的修复（已修复）。"""
    doc = ParsedDocument.model_validate_json(
        (FIXTURES / "sdp-004-mineru.json").read_text(encoding="utf-8")
    )
    pkg = run_quality(doc)
    # 对已修复的 markdown 再跑修复：无变化
    result = apply_repairs(pkg.optimized_markdown, document_key="doc")
    assert result.markdown == pkg.optimized_markdown


def test_repair_replay_and_rollback_are_safe():
    md = "正文  \n"
    result = apply_repairs(md, document_key=DOC_KEY, affected_block_ids_by_rule={"QL-RPR-001": ["block-1"]})
    repair = result.applied[0]
    assert repair.affected_block_ids == ["block-1"]
    assert replay_repair(repair.evidence["before"], repair) == repair.evidence["after"]
    assert rollback_repair(repair.evidence["after"], repair) == repair.evidence["before"]
    assert "parameters" in repair.evidence and "rollback" in repair.evidence


def test_trailing_whitespace_preserves_crlf():
    outcome = QL_RPR_001_TrailingWhitespace().apply("a  \r\nb\r\n")
    assert outcome.after == "a\r\nb\r\n"


def test_table_separator_does_not_modify_fenced_code():
    md = "```\n| A | B |\n|---|---|---|\n```"
    outcome = QL_RPR_002_TableSeparator().apply(md)
    assert not outcome.applied


def test_repair_id_uses_full_input_identity():
    prefix = "x" * 70
    first = apply_repairs(prefix + "A  \n", document_key=DOC_KEY).applied[0].repair_id
    second = apply_repairs(prefix + "B  \n", document_key=DOC_KEY).applied[0].repair_id
    assert first != second
