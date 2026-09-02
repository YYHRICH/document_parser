"""Build a per-source capability matrix from source-output-fidelity records.

The input is the read-only audit JSONL produced by
``audit_source_output_fidelity.py``.  This tool deliberately stays in the
trigger/reporting layer: it does not alter parser results or quality decisions.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


MODELS = ("anydoc", "docling", "markitdown", "mineru")
MODEL_LABELS = {
    "anydoc": "AnyDoc",
    "docling": "Docling",
    "markitdown": "MarkItDown",
    "mineru": "MinerU",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--audit-jsonl", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--jsonl-output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path, required=True)
    return parser.parse_args()


def read_records(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def output_status(output: dict[str, Any]) -> str:
    if output.get("parser_success") and output.get("markdown_chars", 0) > 0:
        return "成功"
    if output.get("parser_success"):
        return "空输出"
    return "失败"


def status_detail(output: dict[str, Any]) -> str:
    status = output_status(output)
    if status == "失败":
        return f"失败({output.get('error_code') or 'parser_error'})"
    if status == "空输出":
        return "空输出(empty_markdown)"
    return "成功"


def build_rows(records: list[dict[str, Any]], source_root: Path) -> list[dict[str, Any]]:
    audit_by_key = {
        str(record["document_key"]).casefold(): record for record in records
    }
    rows: list[dict[str, Any]] = []
    source_files = [
        (category_dir.name, path)
        for category_dir in sorted(
            (item for item in source_root.iterdir() if item.is_dir()),
            key=lambda item: item.name.casefold(),
        )
        for path in sorted(
            (item for item in category_dir.iterdir() if item.is_file()),
            key=lambda item: item.name.casefold(),
        )
    ]
    for index, (category, source_path) in enumerate(source_files, start=1):
        document_key = f"{category}/{source_path.name}"
        record = audit_by_key.get(document_key.casefold())
        if record is None:
            statuses = {model: "未解析" for model in MODELS}
            details = {model: "未解析(结果目录不存在)" for model in MODELS}
        else:
            statuses = {
                model: output_status(record["outputs"][model]) for model in MODELS
            }
            details = {
                model: status_detail(record["outputs"][model]) for model in MODELS
            }
        rows.append(
            {
                "index": index,
                "category": category,
                "filename": source_path.name,
                "extension": source_path.suffix.lower(),
                "document_key": document_key,
                "statuses": statuses,
                "details": details,
                "success_count": sum(status == "成功" for status in statuses.values()),
                "nonempty_all_models": all(status == "成功" for status in statuses.values()),
                "has_capability_difference": len(set(statuses.values())) > 1,
                "is_unparsed": record is None,
                "combination": "/".join(statuses[model] for model in MODELS),
            }
        )
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "index",
        "category",
        "filename",
        "extension",
        "document_key",
        *MODELS,
        "success_count",
        "nonempty_all_models",
        "has_capability_difference",
        "is_unparsed",
        "combination",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "index": row["index"],
                    "category": row["category"],
                    "filename": row["filename"],
                    "extension": row["extension"],
                    "document_key": row["document_key"],
                    **row["details"],
                    "success_count": row["success_count"],
                    "nonempty_all_models": row["nonempty_all_models"],
                    "has_capability_difference": row["has_capability_difference"],
                    "is_unparsed": row["is_unparsed"],
                    "combination": row["combination"],
                }
            )


def escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def write_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    aligned_rows = [row for row in rows if not row["is_unparsed"]]
    unparsed_rows = [row for row in rows if row["is_unparsed"]]
    status_counts = {
        model: Counter(row["statuses"][model] for row in aligned_rows) for model in MODELS
    }
    combinations = Counter(row["combination"] for row in aligned_rows)
    format_counts = {
        model: Counter(
            (row["extension"], row["statuses"][model]) for row in aligned_rows
        )
        for model in MODELS
    }
    mismatches = [row for row in aligned_rows if row["has_capability_difference"]]

    lines = [
        "# 原始源文件与四模型解析能力逐文件对比",
        "",
        "> 主键是“数据集类别 + 原始文件名”。每一行对应原始全量数据集中的一个文档记录；源文件和模型结果均只读。",
        "> `成功` 表示存在非空 Markdown，`空输出` 表示解析状态成功但 Markdown 为空，`失败` 表示解析状态不是成功。",
        "> `未解析` 表示该源文件没有出现在四个模型结果目录中，不等同于解析失败。",
        "",
        "## 总体结论",
        "",
        f"- 原始文档记录：{len(rows)} 条。",
        f"- 已与四模型结果目录对齐：{len(aligned_rows)} 条。",
        f"- 未进入四模型结果集：{len(unparsed_rows)} 条。",
        f"- 在已对齐记录中四模型均有非空 Markdown：{sum(row['nonempty_all_models'] for row in aligned_rows)} 条。",
        f"- 在已对齐记录中存在至少一个模型失败或空输出：{len(mismatches)} 条。",
        f"- 在已对齐记录中四模型都没有非空 Markdown：{sum(row['success_count'] == 0 for row in aligned_rows)} 条。",
        "",
        "## 模型状态统计",
        "",
        "| 模型 | 成功（非空） | 空输出 | 失败 | 合计 |",
        "|---|---:|---:|---:|---:|",
    ]
    for model in MODELS:
        counts = status_counts[model]
        lines.append(
            f"| {MODEL_LABELS[model]} | {counts['成功']} | {counts['空输出']} | "
            f"{counts['失败']} | {len(aligned_rows)} |"
        )
    lines += [
        "",
        "## 四模型状态组合",
        "",
        "组合顺序固定为 AnyDoc / Docling / MarkItDown / MinerU。",
        "",
        "| AnyDoc | Docling | MarkItDown | MinerU | 文件数 |",
        "|---|---|---|---|---:|",
    ]
    for combination, count in combinations.most_common():
        values = combination.split("/")
        lines.append(f"| {' | '.join(values)} | {count} |")
    lines += [
        "",
        "## 按文件格式统计",
        "",
        "以下数量只统计已与结果目录对齐的记录；分母是该扩展名的已对齐源文件记录数，每个模型分别统计。",
        "",
        "| 扩展名 | 模型 | 成功 | 空输出 | 失败 |",
        "|---|---|---:|---:|---:|",
    ]
    for extension in sorted({row["extension"] for row in aligned_rows}):
        for model in MODELS:
            lines.append(
                f"| {extension} | {MODEL_LABELS[model]} | "
                f"{format_counts[model][(extension, '成功')]} | "
                f"{format_counts[model][(extension, '空输出')]} | "
                f"{format_counts[model][(extension, '失败')]} |"
            )
    lines += [
        "",
        f"## 存在能力差异的逐文件清单（{len(mismatches)} 条）",
        "",
        "这些文件至少有一个模型不是非空成功；状态后的括号给出失败/空输出的机器可读原因。",
        "",
        "| 序号 | 数据集类别 | 原始文件 | AnyDoc | Docling | MarkItDown | MinerU | 成功模型数 |",
        "|---:|---|---|---|---|---|---|---:|",
    ]
    for row in mismatches:
        lines.append(
            f"| {row['index']} | {escape_cell(row['category'])} | "
            f"{escape_cell(row['filename'])} | "
            f"{row['details']['anydoc']} | {row['details']['docling']} | "
            f"{row['details']['markitdown']} | {row['details']['mineru']} | "
            f"{row['success_count']} |"
        )
    lines += [
        "",
        f"## 未进入四模型结果集的源文件（{len(unparsed_rows)} 条）",
        "",
        "这些源文件存在于原始全量目录，但四个模型结果目录均没有对应的结果目录或 Markdown。它们不能被归因于某一个模型失败。",
        "",
        "| 序号 | 数据集类别 | 原始文件 | AnyDoc | Docling | MarkItDown | MinerU |",
        "|---:|---|---|---|---|---|---|",
    ]
    for row in unparsed_rows:
        lines.append(
            f"| {row['index']} | {escape_cell(row['category'])} | "
            f"{escape_cell(row['filename'])} | 未解析 | 未解析 | 未解析 | 未解析 |"
        )
    lines += [
        "",
        f"## 全部源文件四模型矩阵（{len(rows)} 条）",
        "",
        "本表保留所有源文件，包括四模型均成功的记录，便于按同一个源文件核对。",
        "",
        "| 序号 | 数据集类别 | 原始文件 | AnyDoc | Docling | MarkItDown | MinerU |",
        "|---:|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['index']} | {escape_cell(row['category'])} | "
            f"{escape_cell(row['filename'])} | {row['details']['anydoc']} | "
            f"{row['details']['docling']} | {row['details']['markitdown']} | "
            f"{row['details']['mineru']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    rows = build_rows(read_records(args.audit_jsonl), args.source_root)
    write_jsonl(args.jsonl_output, rows)
    write_csv(args.csv_output, rows)
    write_markdown(args.markdown_output, rows)
    print(
        json.dumps(
            {
                "source_records": len(rows),
                "aligned_records": sum(not row["is_unparsed"] for row in rows),
                "unparsed_records": sum(row["is_unparsed"] for row in rows),
                "mismatch_records": sum(row["has_capability_difference"] for row in rows),
                "all_models_nonempty": sum(row["nonempty_all_models"] for row in rows),
                "markdown_output": str(args.markdown_output),
                "jsonl_output": str(args.jsonl_output),
                "csv_output": str(args.csv_output),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
