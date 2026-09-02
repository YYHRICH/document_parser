"""Read-only replay of the current quality layer on saved parser Markdown.

The supplied dataset contains raw parser results, not persisted ParsedDocument or
quality packages. This tool constructs a deliberately minimal ParsedDocument from
each saved Markdown file and records what the current quality rules would do.
Native tables, page anchors, assets, OCR spans and source maps are not fabricated;
the report labels this run as ``markdown_only_replay``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID

from document_parser.domain.model.contracts import (
    BlockKind,
    DocumentBlock,
    ParsedTable,
    ParseConfidence,
    SourceAnchor,
)
from document_parser.domain.normalization.bundle import (
    ParserNormalizationBundle,
    stable_uuid,
)
from document_parser.domain.quality.pipeline import run_pipeline
from document_parser.infra.parsers.markitdown.block_builder import blocks_from_markdown


MODEL_DIRS = {
    "anydoc": "res_anydoc",
    "docling": "res_docling",
    "markitdown": "res_markitdown",
    "mineru": "res_minerU",
}
REPORT_NAMES = {
    "解析耗时和成功与否的解析报告.md",
    "data_解析总报告.md",
    "data全部文件MinerU解析报告.md",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts") / "dataset-quality-replay",
    )
    return parser.parse_args()


def json_default(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=json_default) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, values: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for value in values:
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def markdown_files(model: str, root: Path) -> list[Path]:
    """Return one Markdown handoff per parser output unit."""

    model_root = root / MODEL_DIRS[model]
    files: list[Path] = []
    for path in model_root.rglob("*.md"):
        if path.name in REPORT_NAMES and path.parent == model_root:
            continue
        relative_parts = path.relative_to(model_root).parts
        if model == "mineru":
            if path.name != "full.md":
                continue
            if "parts" in relative_parts or "_oversized_work" in relative_parts:
                continue
        elif len(relative_parts) < 3:
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.as_posix().casefold())


def _stable_blocks_and_tables(markdown: str, model: str, relative: str):
    """在分析工具内从 Markdown HTML 片段构造最小 table 证据。"""

    table_pattern = re.compile(r"<table\b[^>]*>.*?</table>", re.IGNORECASE | re.DOTALL)
    matches = list(table_pattern.finditer(markdown))
    if not matches:
        blocks = blocks_from_markdown(markdown)
        return [
            block.model_copy(
                update={
                    "id": stable_uuid("replay-block", model, relative, str(index)),
                    "order_index": index,
                }
            )
            for index, block in enumerate(blocks)
        ], []
    pieces: list[DocumentBlock] = []
    tables: list[ParsedTable] = []
    cursor = 0
    order = 0
    for table_index, match in enumerate(matches):
        prefix = markdown[cursor : match.start()]
        for block in blocks_from_markdown(prefix):
            pieces.append(
                block.model_copy(
                    update={
                        "id": stable_uuid("replay-block", model, relative, str(order)),
                        "order_index": order,
                    }
                )
            )
            order += 1
        block_id = stable_uuid("replay-table-block", model, relative, str(table_index))
        html = match.group(0)
        pieces.append(
            DocumentBlock(
                id=block_id,
                order_index=order,
                kind=BlockKind.TABLE,
                markdown=html,
                anchor=SourceAnchor(original_text=html),
                metadata={"table_id": f"replay-table-{table_index:04d}"},
            )
        )
        tables.append(
            ParsedTable(
                table_id=f"replay-table-{table_index:04d}",
                block_id=block_id,
                html=html,
                markdown=html,
            )
        )
        order += 1
        cursor = match.end()
    for block in blocks_from_markdown(markdown[cursor:]):
        pieces.append(
            block.model_copy(
                update={
                    "id": stable_uuid("replay-block", model, relative, str(order)),
                    "order_index": order,
                }
            )
        )
        order += 1
    return pieces, tables


def replay_one(model: str, path: Path, model_root: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    markdown = raw.decode("utf-8", errors="replace")
    output_sha = sha256_bytes(raw)
    relative = path.relative_to(model_root).as_posix()
    blocks, tables = _stable_blocks_and_tables(markdown, model, relative)
    # This is an output identity, not the original source hash.
    document_id = stable_uuid("dataset-quality-replay", model, relative, output_sha)
    filename = path.name if model != "mineru" else path.parent.name
    bundle = ParserNormalizationBundle.from_minimal_markdown(
        document_id=document_id,
        filename=filename,
        file_type="text/markdown",
        markdown=markdown,
        parser_id=model,
        parser_version="saved-dataset-output",
        source_size_bytes=len(raw),
        source_sha256=output_sha,
        blocks=blocks,
        tables=tables,
        # Markdown-only replay deliberately marks layout/table evidence absent.
        confidence=ParseConfidence(
            text=0.5,
            layout=0.0,
            reading_order=0.5,
            table=0.0,
            overall=0.25,
        ),
        warnings=["markdown_only_replay: native evidence was not fabricated"],
    )
    try:
        package = run_pipeline(bundle.to_parsed_document())
        report = package.quality_report
        issue_categories = Counter(issue.category for issue in report.issues)
        issue_severities = Counter(issue.severity.value for issue in report.issues)
        repair_rules = Counter(repair.rule_id for repair in report.applied_repairs)
        repair_rejections = list(report.rejected_repairs)
        optimized = package.optimized_markdown
        return {
            "model": model,
            "relative_output": relative,
            "filename": filename,
            "document_id": str(document_id),
            "input_sha256": output_sha,
            "input_bytes": len(raw),
            "input_chars": len(markdown),
            "block_count": len(blocks),
            "table_count": len(tables),
            "html_table_count": len(tables),
            "heading_count": sum(1 for block in blocks if block.kind.value == "heading"),
            "pipe_table_line_count": sum(
                1 for line in markdown.splitlines() if line.strip().startswith("|")
            ),
            "data_uri_count": len(re.findall(r"data:image/[^,\s]+,", markdown, re.I)),
            "empty_input": not bool(markdown.strip()),
            "quality_state": report.state.value,
            "issue_count": len(report.issues),
            "issue_categories": dict(sorted(issue_categories.items())),
            "issue_severities": dict(sorted(issue_severities.items())),
            "repair_count": len(report.applied_repairs),
            "repair_rules": dict(sorted(repair_rules.items())),
            "resolved_issue_count": len(report.resolved_issues),
            "resolved_issue_categories": dict(
                sorted(Counter(issue.category for issue in report.resolved_issues).items())
            ),
            "repair_rejections": repair_rejections,
            "optimized_changed": optimized != markdown,
            "optimized_chars": len(optimized),
            "optimized_sha256": hashlib.sha256(optimized.encode("utf-8")).hexdigest(),
            "pipeline_version": report.metrics.get("quality_pipeline_version"),
            "replay_scope": "markdown_only",
        }
    except Exception as error:  # preserve a per-file record and continue the batch
        return {
            "model": model,
            "relative_output": relative,
            "filename": filename,
            "document_id": str(document_id),
            "input_sha256": output_sha,
            "input_bytes": len(raw),
            "input_chars": len(markdown),
            "block_count": len(blocks),
            "table_count": len(tables),
            "html_table_count": len(tables),
            "empty_input": not bool(markdown.strip()),
            "replay_error": f"{type(error).__name__}: {str(error)[:500]}",
            "replay_scope": "markdown_only",
        }


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_model[record["model"]].append(record)
    models: dict[str, Any] = {}
    for model, items in sorted(by_model.items()):
        states = Counter(item.get("quality_state", "replay_error") for item in items)
        issues = Counter()
        severities = Counter()
        repairs = Counter()
        resolved_categories = Counter()
        rejected_repairs: list[dict[str, Any]] = []
        for item in items:
            issues.update(item.get("issue_categories", {}))
            severities.update(item.get("issue_severities", {}))
            repairs.update(item.get("repair_rules", {}))
            resolved_categories.update(item.get("resolved_issue_categories", {}))
            rejected_repairs.extend(item.get("repair_rejections", []))
        models[model] = {
            "output_units": len(items),
            "nonempty_units": sum(not item.get("empty_input", False) for item in items),
            "empty_units": sum(item.get("empty_input", False) for item in items),
            "replay_errors": sum("replay_error" in item for item in items),
            "changed_units": sum(item.get("optimized_changed", False) for item in items),
            "total_input_chars": sum(item.get("input_chars", 0) for item in items),
            "total_blocks": sum(item.get("block_count", 0) for item in items),
            "total_issues": sum(item.get("issue_count", 0) for item in items),
            "total_repairs": sum(item.get("repair_count", 0) for item in items),
            "total_resolved_issues": sum(item.get("resolved_issue_count", 0) for item in items),
            "quality_states": dict(sorted(states.items())),
            "issue_categories": dict(sorted(issues.items())),
            "issue_severities": dict(sorted(severities.items())),
            "repair_rules": dict(sorted(repairs.items())),
            "resolved_issue_categories": dict(sorted(resolved_categories.items())),
            "total_rejected_repairs": len(rejected_repairs),
            "repair_rejections": rejected_repairs,
        }
    return {
        "replay_scope": "markdown_only",
        "source_is_read_only": True,
        "models": models,
        "total_output_units": len(records),
        "total_replay_errors": sum("replay_error" in item for item in records),
    }


def report_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# 数据集质量层回放结果",
        "",
        "> 这是对当前代码质量层的 `markdown_only_replay`，不是原始数据集上已持久化的正式质量包。",
        "> 输入目录只读；没有把任何结果写回 `S:\\桌面\\zyjt_sx\\data\\dataset`。",
        "",
        "## 汇总",
        "",
        "| 模型 | 输出单元 | 空 Markdown | 质量门状态 | 发生改写 | 表格修复 | 拒绝修复 | 问题数 | 修复数 | 回放错误 |",
        "|---|---:|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for model, data in summary["models"].items():
        states = ", ".join(f"{key}={value}" for key, value in data["quality_states"].items())
        lines.append(
            f"| {model} | {data['output_units']} | {data['empty_units']} | {states or '-'} | "
            f"{data['changed_units']} | {data['repair_rules'].get('QL-RPR-003', 0)} | "
            f"{data['total_rejected_repairs']} | {data['total_issues']} | {data['total_repairs']} | {data['replay_errors']} |"
        )
    lines += [
        "",
        "## 解释",
        "",
        "- 回放把保存的 Markdown 切成标题/段落块，并把其中的 HTML table 构造成分析用表格证据；没有注入页码、bbox、图片资产、OCR 或 source-map。",
        "- 因此 `evidence_availability`、来源追踪、表格绑定等问题会被报告为证据不可用；这不是模型输出本身一定错误。",
        "- 当前已接入尾随空白、Markdown 表格分隔线和可验证的 HTML 表格转 Markdown；空成功拦截、乱码、残留 data URI 与图片引用完整性已作为质量门规则接入，图片外链化和跨页续表仍需统一层提供完整证据。",
        "- 逐文件明细见 `document_quality_records.jsonl`；原始模型结构指标仍以 `artifacts/source-output-fidelity` 为准。",
        "",
        "## 各模型问题类别",
        "",
    ]
    for model, data in summary["models"].items():
        lines.append(f"### {model}")
        lines.append("")
        if data["issue_categories"]:
            for key, value in data["issue_categories"].items():
                lines.append(f"- `{key}`: {value}")
        else:
            lines.append("- 无")
        if data["repair_rules"]:
            lines.append("- 修复规则: " + ", ".join(f"`{k}`={v}" for k, v in data["repair_rules"].items()))
        else:
            lines.append("- 修复规则: 无")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for model in MODEL_DIRS:
        model_root = args.results_root / MODEL_DIRS[model]
        for path in markdown_files(model, args.results_root):
            records.append(replay_one(model, path, model_root))
    summary = aggregate(records)
    summary["results_root"] = str(args.results_root)
    summary["models_seen"] = list(MODEL_DIRS)
    write_jsonl(args.output_dir / "document_quality_records.jsonl", records)
    write_json(args.output_dir / "summary.json", summary)
    (args.output_dir / "report.md").write_text(report_markdown(summary), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
