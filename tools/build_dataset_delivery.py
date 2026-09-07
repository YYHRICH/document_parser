"""Build a source-oriented downstream delivery from multi-parser audit records.

The source parser outputs stay read-only.  This tool copies only the selected
Markdown and writes portable relative references to native/multimodal evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5


MODEL_DIRS = {
    "anydoc": "res_anydoc",
    "docling": "res_docling",
    "markitdown": "res_markitdown",
    "mineru": "res_minerU",
}
MODEL_PRIORITY = {"mineru": 4, "docling": 3, "anydoc": 2, "markitdown": 1}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--audit-records", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def source_key(record: dict[str, Any]) -> str:
    parts = Path(record["relative_output"]).parts
    if len(parts) < 2:
        raise ValueError(f"cannot derive source key: {record['relative_output']}")
    return "/".join(parts[:2])


def candidate_score(record: dict[str, Any], asset_count: int = 0) -> tuple[int, ...]:
    """Prefer deliverable evidence, then richer parser output deterministically."""

    usable = "replay_error" not in record and record.get("quality_state") != "rejected"
    nonempty = not record.get("empty_input", True)
    critical = int(record.get("issue_severities", {}).get("critical", 0))
    return (
        int(usable),
        int(nonempty),
        int(asset_count > 0),
        -critical,
        MODEL_PRIORITY.get(record["model"], 0),
        min(int(record.get("input_chars", 0)), 200_000),
    )


def image_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        path for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )


def enrich(record: dict[str, Any], results_root: Path) -> dict[str, Any]:
    model_root = results_root / MODEL_DIRS[record["model"]]
    output_path = model_root / Path(record["relative_output"])
    native_root = output_path.parent
    images = image_files(native_root / "images")
    result = dict(record)
    result["output_path"] = output_path
    result["native_root"] = native_root
    result["asset_count"] = len(images)
    result["asset_bytes"] = sum(path.stat().st_size for path in images)
    result["asset_root"] = native_root / "images" if images else None
    return result


def portable(path: Path, base: Path) -> str:
    return Path("..").joinpath(path.resolve().relative_to(base.resolve())).as_posix()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    records = [json.loads(line) for line in args.audit_records.read_text(encoding="utf-8").splitlines() if line.strip()]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[source_key(record)].append(enrich(record, args.results_root))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    documents_root = args.output_dir / "documents"
    manifest: list[dict[str, Any]] = []
    selected_models: Counter[str] = Counter()
    fallback_cases: list[dict[str, Any]] = []
    for key, candidates in sorted(grouped.items()):
        ranked = sorted(candidates, key=lambda item: candidate_score(item, item["asset_count"]), reverse=True)
        selected = ranked[0]
        source_id = f"src_{uuid5(NAMESPACE_URL, 'document-parser/allin6/' + key).hex[:16]}"
        package_root = documents_root / source_id
        package_root.mkdir(parents=True, exist_ok=True)
        selected_path: Path = selected["output_path"]
        selected_markdown = selected_path.read_bytes()
        (package_root / "selected.md").write_bytes(selected_markdown)
        selected_models[selected["model"]] += 1
        candidate_rows = []
        for candidate in ranked:
            candidate_rows.append({
                "model": candidate["model"],
                "relative_output": (Path(MODEL_DIRS[candidate["model"]]) / Path(candidate["relative_output"])).as_posix(),
                "quality_state": candidate.get("quality_state", "replay_error"),
                "empty": candidate.get("empty_input", False),
                "input_chars": candidate.get("input_chars", 0),
                "issue_categories": candidate.get("issue_categories", {}),
                "repair_rules": candidate.get("repair_rules", {}),
                "asset_count": candidate["asset_count"],
                "asset_root": (Path(MODEL_DIRS[candidate["model"]]) / Path(candidate["relative_output"]).parent / "images").as_posix() if candidate["asset_root"] else None,
                "selected": candidate is selected,
            })
        rejected_models = [item["model"] for item in ranked if item.get("quality_state") == "rejected"]
        if rejected_models:
            fallback_cases.append({"source_id": source_id, "source_key": key, "selected_model": selected["model"], "rejected_models": rejected_models})
        delivery = {
            "schema_name": "DatasetDeliveryRecord",
            "schema_version": "1.0",
            "source_id": source_id,
            "source_key": key,
            "selected_parser_id": selected["model"],
            "selected_markdown": f"documents/{source_id}/selected.md",
            "selected_sha256": hashlib.sha256(selected_markdown).hexdigest(),
            "selection_policy": "quality_then_multimodal_then_model_priority_v1",
            "quality_scope": "markdown_only_replay",
            "quality_state": selected.get("quality_state", "replay_error"),
            "asset_count": selected["asset_count"],
            "assets_reference": (Path("allin6") / MODEL_DIRS[selected["model"]] / Path(selected["relative_output"]).parent / "images").as_posix() if selected["asset_root"] else None,
            "candidates": candidate_rows,
        }
        write_json(package_root / "delivery-record.json", delivery)
        manifest.append(delivery)

    with (args.output_dir / "dataset-manifest.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for item in manifest:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    summary = {
        "schema_name": "DatasetDeliverySummary",
        "schema_version": "1.0",
        "source_count": len(manifest),
        "selected_models": dict(sorted(selected_models.items())),
        "selected_rejected_count": sum(item["quality_state"] == "rejected" for item in manifest),
        "selected_with_assets": sum(item["asset_count"] > 0 for item in manifest),
        "fallback_case_count": len(fallback_cases),
        "quality_scope": "markdown_only_replay",
        "native_assets_copied": False,
    }
    write_json(args.output_dir / "summary.json", summary)
    write_json(args.output_dir / "fallback-cases.json", fallback_cases)
    lines = [
        "# allin6 下游选优与 case 分析",
        "",
        f"- Source 数：{summary['source_count']}",
        f"- 选中结果仍为 rejected：{summary['selected_rejected_count']}",
        f"- 选中结果含独立图片：{summary['selected_with_assets']}",
        f"- 至少一个候选被拒绝并已 fallback：{summary['fallback_case_count']}",
        f"- 模型选择分布：{summary['selected_models']}",
        "",
        "## 选优方法",
        "",
        "1. 排除质量回放错误和 `rejected` 候选；",
        "2. 排除空 Markdown；",
        "3. 优先保留带独立图片资源的候选；",
        "4. 同等情况下按 MinerU、Docling、AnyDoc、MarkItDown 的证据丰富度排序；",
        "5. 字符数只作末级比较，避免把超长 data URI 当成高质量正文。",
        "",
        "## 边界",
        "",
        "- 本交付是 Markdown-only 质量回放后的轻量包；图片仍引用 `allin6` 原生目录，没有重复复制数 GB 文件。",
        "- 正式发布前需用统一 `ParsedDocument` 再验证 page/bbox/cell/OCR/source-map，并生成正式 `quality_package.json`。",
    ]
    (args.output_dir / "case-analysis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
