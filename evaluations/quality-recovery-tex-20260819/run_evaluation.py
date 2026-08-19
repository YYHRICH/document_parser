"""可重复执行的 TeX/PDF 双解析器与真实质量 Agent 评测编排。"""

from __future__ import annotations

import argparse
from difflib import unified_diff
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


EVAL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EVAL_ROOT.parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT.parent))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_manifest() -> None:
    spec = json.loads((EVAL_ROOT / "evaluation_spec.json").read_text(encoding="utf-8"))
    entries = []
    for document_name, truth in spec["documents"].items():
        tex = EVAL_ROOT / "sources" / f"{document_name}.tex"
        pdf = EVAL_ROOT / "pdfs" / f"{document_name}.pdf"
        text = EVAL_ROOT / "pdf_text" / f"{document_name}.txt"
        if not tex.exists() or not pdf.exists() or not text.exists():
            raise FileNotFoundError(f"缺少编译或文本基线产物: {document_name}")
        baseline = text.read_text(encoding="utf-8", errors="replace")
        entries.append(
            {
                "document": document_name,
                "source_id": truth["source_id"],
                "tex": {"path": str(tex.relative_to(EVAL_ROOT)), "sha256": _sha256(tex)},
                "pdf": {
                    "path": str(pdf.relative_to(EVAL_ROOT)),
                    "sha256": _sha256(pdf),
                    "size_bytes": pdf.stat().st_size,
                },
                "pdf_text": {
                    "path": str(text.relative_to(EVAL_ROOT)),
                    "sha256": _sha256(text),
                    "marker_recall": _recall(truth["markers"], baseline),
                    "fact_recall": _recall(truth["critical_facts"], baseline),
                },
            }
        )
    _write_json(
        EVAL_ROOT / "manifest.json",
        {
            "schema_version": "1.0",
            "evaluation_id": spec["evaluation_id"],
            "documents": entries,
        },
    )


def parse_document(parser_name: str, document_name: str) -> None:
    from document_parser.core.contracts import ParsedDocument

    source = EVAL_ROOT / "pdfs" / f"{document_name}.pdf"
    output_dir = EVAL_ROOT / "parses" / document_name / parser_name
    output_dir.mkdir(parents=True, exist_ok=True)
    if parser_name == "mineru":
        from tools.mineru_cloud import parse_pdf

        parsed = parse_pdf(
            source,
            is_ocr=False,
            file_type="application/pdf",
            work_dir=output_dir / "raw",
        )
    elif parser_name == "docling":
        from tools.docling_parser import parse_pdf

        parsed = parse_pdf(source, file_type="application/pdf")
    else:
        raise ValueError(f"未知解析器: {parser_name}")

    payload = parsed.model_dump_json(indent=2)
    (output_dir / "parsed_document.json").write_text(payload + "\n", encoding="utf-8")
    (output_dir / "parsed.md").write_text(parsed.markdown, encoding="utf-8")
    ParsedDocument.model_validate_json(payload)
    _write_json(
        output_dir / "parser_summary.json",
        {
            "document": document_name,
            "parser": parser_name,
            "parser_id": parsed.provenance.parser_id,
            "source_sha256": parsed.source_sha256,
            "markdown_sha256": hashlib.sha256(parsed.markdown.encode("utf-8")).hexdigest(),
            "markdown_chars": len(parsed.markdown),
            "blocks": len(parsed.blocks),
            "headings": sum(block.kind.value == "heading" for block in parsed.blocks),
            "tables": len(parsed.tables),
            "warnings": parsed.warnings,
        },
    )


def repair_all() -> None:
    from document_parser.core.contracts import ParsedDocument
    from quality import (
        run_quality,
        run_quality_repair_detailed,
        write_quality_package,
    )
    from quality.agent import (
        RepairAgentConfig,
        build_deepseek_model,
        build_quality_repair_agent,
    )

    spec = json.loads((EVAL_ROOT / "evaluation_spec.json").read_text(encoding="utf-8"))
    model = build_deepseek_model()
    results: list[dict[str, Any]] = []
    for document_name, truth in spec["documents"].items():
        for parser_name in ("mineru", "docling"):
            parsed_path = (
                EVAL_ROOT
                / "parses"
                / document_name
                / parser_name
                / "parsed_document.json"
            )
            normalized_path = parsed_path.with_name("normalized_document.json")
            input_path = normalized_path if normalized_path.exists() else parsed_path
            parsed = ParsedDocument.model_validate_json(
                input_path.read_text(encoding="utf-8")
            )
            output_dir = EVAL_ROOT / "quality" / document_name / parser_name
            session_id = f"{spec['evaluation_id']}:{document_name}:{parser_name}"
            baseline = run_quality(parsed)
            print(f"[AGENT] start {document_name}/{parser_name} session={session_id}", flush=True)
            try:
                execution = run_quality_repair_detailed(
                    parsed,
                    agent_config=RepairAgentConfig(
                        max_rounds=2,
                        max_context_chars=30000,
                        mode="document",
                        session_id=session_id,
                    ),
                    agent_factory=lambda toolbox, selected=model, sid=session_id: (
                        build_quality_repair_agent(selected, toolbox, session_id=sid)
                    ),
                )
                write_quality_package(
                    execution.package,
                    output_dir,
                    replace_existing=True,
                )
                execution_payload = {
                    "session_id": execution.session_id,
                    "accepted": execution.accepted,
                    "final_revision_id": execution.final_revision_id,
                    "attempts": [
                        attempt.model_dump(mode="json") for attempt in execution.attempts
                    ],
                }
                _write_json(output_dir / "execution.json", execution_payload)
                before_lines = parsed.markdown.splitlines(keepends=True)
                after_lines = execution.package.optimized_markdown.splitlines(keepends=True)
                (output_dir / "markdown.diff").write_text(
                    "".join(
                        unified_diff(
                            before_lines,
                            after_lines,
                            fromfile="parsed.md",
                            tofile="optimized.md",
                        )
                    ),
                    encoding="utf-8",
                )
                changed_attempts = [
                    attempt
                    for attempt in execution.attempts
                    if attempt.accepted
                ]
                changed_block_ids = sorted(
                    {
                        block_id
                        for attempt in changed_attempts
                        for block_id in attempt.changed_block_ids
                    }
                )
                changed_table_ids = sorted(
                    {
                        table_id
                        for attempt in changed_attempts
                        for table_id in attempt.changed_table_ids
                    }
                )
                changed_relation_keys = sorted(
                    {
                        relation_key
                        for attempt in changed_attempts
                        for relation_key in attempt.changed_relation_keys
                    }
                )
                changed_asset_paths = sorted(
                    {
                        asset_path
                        for attempt in changed_attempts
                        for asset_path in attempt.changed_asset_paths
                    }
                )
                result = {
                    "document": document_name,
                    "parser": parser_name,
                    "session_id": session_id,
                    "agent_accepted": execution.accepted,
                    "attempt_codes": [attempt.code for attempt in execution.attempts],
                    "attempt_no_progress": [attempt.no_progress for attempt in execution.attempts],
                    # 表格/关系/资源 Patch 可能不改变根 Markdown；
                    # changed 必须同时覆盖所有可提交对象。
                    "changed": bool(
                        execution.package.optimized_markdown != parsed.markdown
                        or changed_block_ids
                        or changed_table_ids
                        or changed_relation_keys
                        or changed_asset_paths
                    ),
                    "changed_block_ids": changed_block_ids,
                    "changed_table_ids": changed_table_ids,
                    "changed_relation_keys": changed_relation_keys,
                    "changed_asset_paths": changed_asset_paths,
                    "baseline_state": baseline.quality_report.state.value,
                    "baseline_issues": len(baseline.quality_report.issues),
                    "final_state": execution.package.quality_report.state.value,
                    "final_issues": len(execution.package.quality_report.issues),
                    "blocks": len(parsed.blocks),
                    "tables": len(parsed.tables),
                    "parsed_marker_recall": _recall(truth["markers"], parsed.markdown),
                    "optimized_marker_recall": _recall(
                        truth["markers"], execution.package.optimized_markdown
                    ),
                    "parsed_fact_recall": _recall(
                        truth["critical_facts"], parsed.markdown
                    ),
                    "optimized_fact_recall": _recall(
                        truth["critical_facts"], execution.package.optimized_markdown
                    ),
                }
            except Exception as exc:
                output_dir.mkdir(parents=True, exist_ok=True)
                result = {
                    "document": document_name,
                    "parser": parser_name,
                    "session_id": session_id,
                    "agent_accepted": False,
                    "fatal_error_type": f"{type(exc).__module__}.{type(exc).__name__}",
                    "fatal_error": str(exc)[:1000],
                    "baseline_state": baseline.quality_report.state.value,
                    "baseline_issues": len(baseline.quality_report.issues),
                    "parsed_marker_recall": _recall(truth["markers"], parsed.markdown),
                    "parsed_fact_recall": _recall(truth["critical_facts"], parsed.markdown),
                }
                _write_json(output_dir / "fatal_error.json", result)
            results.append(result)
            _write_json(EVAL_ROOT / "summary.json", {"results": results})
            _write_summary_markdown(results)
            print(
                f"[AGENT] done {document_name}/{parser_name} "
                f"accepted={result.get('agent_accepted')} "
                f"codes={result.get('attempt_codes', [result.get('fatal_error_type')])}",
                flush=True,
            )


def _recall(expected: list[str], text: str) -> dict[str, Any]:
    normalized_text = _normalize_for_match(text)
    found = [item for item in expected if _normalize_for_match(item) in normalized_text]
    missing = [item for item in expected if _normalize_for_match(item) not in normalized_text]
    return {
        "found": len(found),
        "total": len(expected),
        "rate": round(len(found) / len(expected), 4) if expected else 1.0,
        "missing": missing,
    }


def _normalize_for_match(text: str) -> str:
    replacements = {
        "−": "-",
        "–": "--",
        "≤": "<=",
        "≥": ">=",
        "α": "alpha",
        "β": "beta",
        "²": "^2",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return "".join(text.split())


def _write_summary_markdown(results: list[dict[str, Any]]) -> None:
    lines = [
        "# 真实双解析器质量恢复评测结果",
        "",
        "| 文档 | 解析器 | Agent | 变更 | 解析标记 | 恢复后标记 | 解析事实 | 恢复后事实 | 质量状态 |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in results:
        def rate(name: str) -> str:
            value = item.get(name)
            return "-" if not value else f"{value['found']}/{value['total']}"

        lines.append(
            "| {document} | {parser} | {agent} | {changed} | {pm} | {om} | {pf} | {of} | {state} |".format(
                document=item["document"],
                parser=item["parser"],
                agent="accepted" if item.get("agent_accepted") else "failed",
                changed=item.get("changed", "-"),
                pm=rate("parsed_marker_recall"),
                om=rate("optimized_marker_recall"),
                pf=rate("parsed_fact_recall"),
                of=rate("optimized_fact_recall"),
                state=item.get("final_state", item.get("baseline_state", "-")),
            )
        )
    lines.extend(
        [
            "",
            "说明：恢复后召回率不能高于解析阶段缺失事实的上限；质量 Agent 只允许修复格式/结构，",
            "不会猜测并补写解析器已经丢失的正文事实。详细 attempts、diff 和四件套见 `quality/`。",
            "",
        ]
    )
    (EVAL_ROOT / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("manifest")
    parse_parser = subparsers.add_parser("parse")
    parse_parser.add_argument("--parser", choices=["mineru", "docling"], required=True)
    parse_parser.add_argument("--document", required=True)
    subparsers.add_parser("repair-all")
    args = parser.parse_args()
    if args.command == "manifest":
        build_manifest()
    elif args.command == "parse":
        parse_document(args.parser, args.document)
    else:
        repair_all()


if __name__ == "__main__":
    main()
