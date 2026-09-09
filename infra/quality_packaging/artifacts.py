"""质量包基础文件的确定性序列化与校验。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from document_parser.domain.model.contracts import QualityPackage
from document_parser.domain.quality.table_storage import TABLE_INDEX_NAME

from .table_index import external_tables, verify_table_index

OPTIMIZED_NAME = "optimized.md"
STRUCTURE_NAME = "structure.json"
ISSUES_NAME = "quality_issues.json"

# 表格修复能力是质量层的主评测对象。通用文档问题仍保留在
# quality_report 中，但不能混入表格修复统计，否则会把标题、引用、图片等
# 问题误算成表格修复能力。
TABLE_ISSUE_CATEGORIES = frozenset(
    {
        "table_structure",
        "table_grid",
        "table_header_structure",
        "table_field_binding",
        "table_representation",
        "table_view",
        "table_source_mapping",
        "table_pseudo_nested",
        "cross_page_table",
        "column_drift",
    }
)


def _contains_table_marker(value: Any) -> bool:
    """判断问题、修复或能力证据是否明确指向表格。"""

    if isinstance(value, Mapping):
        return any(_contains_table_marker(key) or _contains_table_marker(item) for key, item in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_contains_table_marker(item) for item in value)
    if not isinstance(value, str):
        return False
    text = value.lower()
    # non_table_relation 等能力明确表示“非表格”，不能因为包含 table
    # 子串而被误算入表格修复能力。
    table_text = text.replace("non_table", "").replace("non-table", "")
    return (
        "表格" in value
        or bool(re.search(r"(?<![a-z])table(?![a-z])", table_text))
        or bool(re.search(r"(?<![a-z])tbl(?![a-z])", table_text))
        or "column_drift" in table_text
        or "cross_page" in table_text
    )


def _is_table_issue(category: str, evidence: Mapping[str, Any] | None = None) -> bool:
    return category in TABLE_ISSUE_CATEGORIES or _contains_table_marker(evidence or {})


def _extract_table_ids(value: Any) -> list[str]:
    """从证据中提取可供 Wiki 定位的 table_id，不复制表格正文。"""

    found: list[str] = []

    def visit(item: Any, key: str | None = None) -> None:
        if isinstance(item, Mapping):
            for child_key, child in item.items():
                visit(child, str(child_key))
            return
        if isinstance(item, (list, tuple, set, frozenset)):
            for child in item:
                visit(child, key)
            return
        if key in {"table_id", "table_ids"} and item is not None:
            candidate = str(item)
            if candidate not in found:
                found.append(candidate)

    visit(value)
    return found


def _summarize_review_items(items: list[dict]) -> dict[str, int]:
    return {
        "item_count": len(items),
        "repaired_count": sum(item["status"] == "repaired" for item in items),
        "manual_review_required_count": sum(
            item["status"] == "manual_review_required" for item in items
        ),
        "uncertain_count": sum(item["status"] == "uncertain" for item in items),
        "unfixed_count": sum(item["status"] == "unfixed" for item in items),
        "reparse_required_count": sum(
            item["status"] == "reparse_required" for item in items
        ),
        "rejected_count": sum(item["status"] == "rejected" for item in items),
    }


@dataclass(frozen=True)
class PackageArtifacts:
    """待写入的基础质量产物；大表数据库由流式写入器负责。"""

    files: Mapping[str, bytes]


def build_structure_payload(
    package: QualityPackage,
    *,
    table_index: dict | None = None,
) -> dict:
    """生成只包含规范结构的 JSON 载荷。"""

    external_ids = {table.table_id for table in external_tables(package)}
    canonical = package.canonical_document.model_dump(
        mode="json",
        exclude={"tables", "table_bindings"},
    )
    canonical["tables"] = [
        table.model_dump(
            mode="json",
            exclude={"cells", "grid"} if table.table_id in external_ids else None,
        )
        for table in package.canonical_document.tables
    ]
    canonical["table_bindings"] = [
        binding.model_dump(mode="json")
        for binding in package.canonical_document.table_bindings
        if binding.table_id not in external_ids
    ]
    payload = {
        "schema_name": "DocumentStructure",
        "document_id": str(package.document_id),
        "canonical_document": canonical,
    }
    if external_ids:
        if table_index is None:
            table_index = {
                "mode": "sqlite",
                "file": TABLE_INDEX_NAME,
                "table_count": len(external_ids),
                "status": "requires_materialization",
            }
        payload["table_index"] = table_index
    return payload


def build_issues_payload(package: QualityPackage) -> dict:
    """生成只包含问题、修复和交付状态的 JSON 载荷。"""

    report = package.quality_report
    review_items: list[dict] = []

    def add_item(
        *,
        item_id: str,
        object_type: str,
        status: str,
        message: str,
        object_ids: list[str] | None = None,
        evidence: dict | None = None,
        scope: str = "document",
    ) -> None:
        labels = {
            "repaired": "已修复",
            "manual_review_required": "需要人工复核",
            "uncertain": "不确定",
            "reparse_required": "需要重新解析",
            "rejected": "拒绝交付",
            "unfixed": "尚未修复",
        }
        actions = {
            "repaired": "正常使用",
            "manual_review_required": "提交人工复核",
            "uncertain": "不建立高置信结构绑定",
            "reparse_required": "提交重新解析",
            "rejected": "禁止交付",
            "unfixed": "保留警告并按下游策略处理",
        }
        evidence_payload = evidence or {}
        review_items.append(
            {
                "item_id": item_id,
                "object_type": object_type,
                "scope": scope,
                "status": status,
                "status_label": labels[status],
                "message": message,
                "object_ids": object_ids or [],
                "table_ids": _extract_table_ids(evidence_payload),
                "wiki_action": actions[status],
                "evidence": evidence_payload,
            }
        )

    for issue in report.resolved_issues:
        scope = "table" if _is_table_issue(issue.category, issue.evidence) else "document"
        add_item(
            item_id=issue.issue_id,
            object_type="issue",
            status="repaired",
            message=issue.message,
            object_ids=list(issue.affected_block_ids),
            evidence=issue.evidence,
            scope=scope,
        )
    for repair in report.applied_repairs:
        scope = "table" if _contains_table_marker(
            {"rule_id": repair.rule_id, "description": repair.description, "evidence": repair.evidence}
        ) else "document"
        add_item(
            item_id=repair.repair_id,
            object_type="repair",
            status="repaired",
            message=repair.description,
            object_ids=list(repair.affected_block_ids),
            evidence=repair.evidence,
            scope=scope,
        )
    for issue in report.issues:
        raw_status = getattr(issue.status, "value", issue.status)
        status = raw_status
        evidence = {"original_status": raw_status, **issue.evidence}
        scope = "table" if _is_table_issue(issue.category, evidence) else "document"
        add_item(
            item_id=issue.issue_id,
            object_type="issue",
            status=status,
            message=issue.message,
            object_ids=list(issue.affected_block_ids),
            evidence=evidence,
            scope=scope,
        )
    for capability_name, assessment in report.capability_matrix.items():
        raw_state = getattr(assessment.state, "value", assessment.state)
        if raw_state == "manual_review_required":
            status = "manual_review_required"
        elif raw_state in {"inferred", "partial", "unavailable"}:
            status = "uncertain"
        elif raw_state in {"reparse_required", "rejected"}:
            status = raw_state
        else:
            continue
        scope = "table" if _contains_table_marker({"capability": capability_name, "evidence": assessment.evidence}) else "document"
        add_item(
            item_id=f"capability:{capability_name}",
            object_type="capability",
            status=status,
            message=f"能力“{capability_name}”的证据状态为 {raw_state}。",
            object_ids=[capability_name],
            evidence=assessment.evidence,
            scope=scope,
        )

    summary = _summarize_review_items(review_items)
    table_items = [item for item in review_items if item["scope"] == "table"]
    document_items = [item for item in review_items if item["scope"] == "document"]
    return {
        "schema_name": "QualityIssues",
        "document_id": str(package.document_id),
        # review_summary/review_items 保留完整质量审计；表格能力评测必须读取
        # table_repair，不能用完整文档问题数代替表格修复统计。
        "review_summary": summary,
        "review_items": review_items,
        "table_repair": {
            "summary": _summarize_review_items(table_items),
            "items": table_items,
        },
        "document_review": {
            "summary": _summarize_review_items(document_items),
            "items": document_items,
        },
        "quality_report": package.quality_report.model_dump(mode="json"),
    }


def build_package_artifacts(
    package: QualityPackage,
    *,
    table_index: dict | None = None,
) -> PackageArtifacts:
    """生成 Markdown 和两个 JSON；大表数据库由目录写入器流式生成。"""

    optimized = package.optimized_markdown.encode("utf-8")
    structure = json.dumps(
        build_structure_payload(package, table_index=table_index),
        ensure_ascii=False,
        indent=2,
    ).encode(
        "utf-8"
    )
    issues = json.dumps(build_issues_payload(package), ensure_ascii=False, indent=2).encode("utf-8")
    return PackageArtifacts(
        files={
            OPTIMIZED_NAME: optimized,
            STRUCTURE_NAME: structure,
            ISSUES_NAME: issues,
        }
    )


def _verify_canonical_references(package: QualityPackage) -> None:
    """确保 structure.json 内所有 ID 引用都能在同一文档内解析。"""

    document = package.canonical_document
    block_ids = [block.block_id for block in document.blocks]
    if len(block_ids) != len(set(block_ids)):
        raise ValueError("规范文档包含重复 block_id")
    known_blocks = set(block_ids)

    table_ids = [table.table_id for table in document.tables]
    if len(table_ids) != len(set(table_ids)):
        raise ValueError("规范文档包含重复 table_id")
    table_by_id = {table.table_id: table for table in document.tables}
    cells_by_table: dict[str, set[str]] = {}

    for table in document.tables:
        if table.block_id not in known_blocks:
            raise ValueError(f"表格 {table.table_id} 引用了不存在的 block_id")
        cell_ids = [cell.cell_id for cell in table.cells]
        if any(cell_id is None for cell_id in cell_ids):
            raise ValueError(f"表格 {table.table_id} 存在缺少 cell_id 的单元格")
        typed_cell_ids = {str(cell_id) for cell_id in cell_ids}
        if len(cell_ids) != len(typed_cell_ids):
            raise ValueError(f"表格 {table.table_id} 包含重复 cell_id")
        cells_by_table[table.table_id] = typed_cell_ids
        for row in table.grid:
            for slot in row:
                referenced_cell_id = slot.cell_id or slot.origin_cell_id
                if referenced_cell_id not in typed_cell_ids:
                    raise ValueError(
                        f"表格 {table.table_id} 的网格槽位引用了不存在的单元格"
                    )

    for table in document.tables:
        if table.parent_table_id is None:
            if table.parent_cell_id is not None:
                raise ValueError(f"表格 {table.table_id} 只有 parent_cell_id，没有父表")
            continue
        parent = table_by_id.get(table.parent_table_id)
        if parent is None:
            raise ValueError(f"表格 {table.table_id} 引用了不存在的父表")
        if table.parent_cell_id not in cells_by_table[parent.table_id]:
            raise ValueError(f"表格 {table.table_id} 引用了不存在的父单元格")

    for binding in document.table_bindings:
        table = table_by_id.get(binding.table_id)
        if table is None:
            raise ValueError(f"字段绑定 {binding.binding_id} 引用了不存在的表格")
        if binding.block_id not in known_blocks or binding.block_id != table.block_id:
            raise ValueError(f"字段绑定 {binding.binding_id} 的 block_id 与表格不一致")
        referenced_cell_ids = {
            *binding.row_cell_ids,
            *binding.column_cell_ids,
            *([binding.value_cell_id] if binding.value_cell_id else []),
        }
        if not referenced_cell_ids.issubset(cells_by_table[binding.table_id]):
            raise ValueError(f"字段绑定 {binding.binding_id} 引用了不存在的单元格")

    for relation in document.relations:
        if relation.from_id not in known_blocks or relation.to_id not in known_blocks:
            raise ValueError(f"关系 {relation.relation_id} 存在悬挂端点")


def verify_package_files(files: Mapping[str, bytes]) -> None:
    """校验三文件存在、身份一致且 JSON 结构合法。"""

    required = {OPTIMIZED_NAME, STRUCTURE_NAME, ISSUES_NAME}
    missing = required - set(files)
    if missing:
        raise ValueError(f"quality package 缺少文件: {sorted(missing)}")
    try:
        structure = json.loads(files[STRUCTURE_NAME].decode("utf-8"))
        issues = json.loads(files[ISSUES_NAME].decode("utf-8"))
        if not isinstance(structure, dict) or not isinstance(issues, dict):
            raise ValueError("JSON 根节点必须是对象")
        if "optimized_markdown" in structure or "optimized_markdown" in issues:
            raise ValueError("结构 JSON 和问题 JSON 不应重复正文")
        if "quality_report" in structure or "canonical_document" in issues:
            raise ValueError("结构 JSON 和问题 JSON 的职责不能混合")
        if "package_manifest" in structure or "package_manifest" in issues:
            raise ValueError("交付 JSON 不应包含 manifest")
        if structure.get("document_id") != issues.get("document_id"):
            raise ValueError("结构 JSON 与问题 JSON 的 document_id 不一致")
        table_index = structure.get("table_index")
        if table_index is not None:
            if (
                not isinstance(table_index, dict)
                or table_index.get("mode") != "sqlite"
                or table_index.get("file") != TABLE_INDEX_NAME
            ):
                raise ValueError("大表索引描述不合法")
        package = QualityPackage.model_validate(
            {
                "schema_name": "QualityPackage",
                "document_id": structure["document_id"],
                "canonical_document": structure["canonical_document"],
                "quality_report": issues["quality_report"],
                "optimized_markdown": "",
            }
        )
        _verify_canonical_references(package)
    except Exception as exc:
        raise ValueError("质量层三文件无法校验") from exc


def read_package_files(directory: Path) -> dict[str, bytes]:
    """读取基础交付文件，并在需要时校验外置大表索引。"""

    try:
        files = {
            name: (directory / name).read_bytes()
            for name in (OPTIMIZED_NAME, STRUCTURE_NAME, ISSUES_NAME)
        }
    except FileNotFoundError as exc:
        raise ValueError(f"quality package 缺少文件: {exc.filename}") from exc
    verify_package_files(files)
    structure = json.loads(files[STRUCTURE_NAME].decode("utf-8"))
    if structure.get("table_index"):
        verify_table_index(
            directory / TABLE_INDEX_NAME,
            str(structure["document_id"]),
        )
    return files
