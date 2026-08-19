"""TeX -> PDF -> 单解析器 -> 归一 -> 真实质量 Agent 的可重复评测。"""

from __future__ import annotations

import argparse
from difflib import unified_diff
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

EVAL_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EVAL_ROOT.parents[1]
sys.path = [entry for entry in sys.path if entry not in {"", str(EVAL_ROOT)}]
sys.path[:0] = [str(REPO_ROOT), str(REPO_ROOT.parent)]


def _load_spec() -> dict[str, Any]:
    return json.loads((EVAL_ROOT / "evaluation_spec.json").read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_for_match(text: str) -> str:
    for source, target in {
        "−": "-", "–": "--", "≤": "<=", "≥": ">=", "≠": "!=",
        r"\leq": "<=", r"\geq": ">=", r"\neq": "!=",
        "α": "alpha", "β": "beta", "²": "^2"
    }.items():
        text = text.replace(source, target)
    return "".join(text.split())


def _recall(expected: list[str], text: str) -> dict[str, Any]:
    normalized = _normalize_for_match(text)
    found = [item for item in expected if _normalize_for_match(item) in normalized]
    return {
        "found": len(found),
        "total": len(expected),
        "rate": round(len(found) / len(expected), 4) if expected else 1.0,
        "missing": [item for item in expected if item not in found],
    }


def compile_documents() -> None:
    xelatex = shutil.which("xelatex") or r"S:\LATEX\texlive\2025\bin\windows\xelatex.exe"
    pdftotext = shutil.which("pdftotext") or r"S:\LATEX\texlive\2025\bin\windows\pdftotext.exe"
    pdf_dir = EVAL_ROOT / "pdfs"
    text_dir = EVAL_ROOT / "pdf_text"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)
    for source in sorted((EVAL_ROOT / "sources").glob("*.tex")):
        subprocess.run(
            [xelatex, "-interaction=nonstopmode", "-halt-on-error", "-file-line-error", f"-output-directory={pdf_dir}", str(source)],
            check=True,
            cwd=REPO_ROOT,
        )
        subprocess.run(
            [pdftotext, "-layout", str(pdf_dir / f"{source.stem}.pdf"), str(text_dir / f"{source.stem}.txt")],
            check=True,
        )


def build_manifest() -> None:
    spec = _load_spec()
    entries = []
    for document, truth in spec["documents"].items():
        tex = EVAL_ROOT / "sources" / f"{document}.tex"
        pdf = EVAL_ROOT / "pdfs" / f"{document}.pdf"
        text_path = EVAL_ROOT / "pdf_text" / f"{document}.txt"
        text = text_path.read_text(encoding="utf-8", errors="replace")
        entries.append(
            {
                "document": document,
                "source_id": truth["source_id"],
                "tex": {"path": str(tex.relative_to(EVAL_ROOT)), "sha256": _sha256(tex)},
                "pdf": {"path": str(pdf.relative_to(EVAL_ROOT)), "sha256": _sha256(pdf), "size_bytes": pdf.stat().st_size},
                "pdf_text": {"path": str(text_path.relative_to(EVAL_ROOT)), "sha256": _sha256(text_path), "marker_recall": _recall(truth["markers"], text), "fact_recall": _recall(truth["critical_facts"], text)},
            }
        )
    _write_json(EVAL_ROOT / "manifest.json", {"schema_version": "1.0", "evaluation_id": spec["evaluation_id"], "documents": entries})


def parse_document(parser_name: str, document: str) -> None:
    from document_parser.core.contracts import ParsedDocument

    source = EVAL_ROOT / "pdfs" / f"{document}.pdf"
    output_dir = EVAL_ROOT / "parses" / document / parser_name
    output_dir.mkdir(parents=True, exist_ok=True)
    if parser_name == "mineru":
        from tools.mineru_cloud import parse_pdf

        parsed = parse_pdf(source, is_ocr=False, file_type="application/pdf", work_dir=output_dir / "raw")
    else:
        from tools.docling_parser import parse_pdf

        parsed = parse_pdf(source, file_type="application/pdf")
    payload = parsed.model_dump_json(indent=2)
    (output_dir / "parsed_document.json").write_text(payload + "\n", encoding="utf-8")
    (output_dir / "parsed.md").write_text(parsed.markdown, encoding="utf-8")
    ParsedDocument.model_validate_json(payload)
    _write_json(output_dir / "parser_summary.json", {"document": document, "parser": parser_name, "source_sha256": parsed.source_sha256, "blocks": len(parsed.blocks), "tables": len(parsed.tables), "warnings": parsed.warnings})


def repair_all(
    parser_name: str,
    documents: list[str],
    *,
    max_rounds: int = 2,
    max_pages: int | None = None,
) -> None:
    from document_parser.core.contracts import ParsedDocument
    from quality import build_wiki_handoff, run_quality, run_quality_repair_detailed, write_quality_package, write_wiki_handoff
    from quality.agent import RepairAgentConfig, build_deepseek_model, build_quality_repair_agent

    spec = _load_spec()
    model = build_deepseek_model()
    results: list[dict[str, Any]] = []
    for document in documents:
        truth = spec["documents"][document]
        parsed_path = EVAL_ROOT / "parses" / document / parser_name / "parsed_document.json"
        parsed = ParsedDocument.model_validate_json(parsed_path.read_text(encoding="utf-8"))
        output_dir = EVAL_ROOT / "quality" / document / parser_name
        session_id = f"{spec['evaluation_id']}:{document}:{parser_name}"
        baseline = run_quality(parsed)
        print(f"[AGENT] start {document}/{parser_name}", flush=True)
        try:
            execution = run_quality_repair_detailed(
                parsed,
                # The production design repairs one page at a time. Keep the
                # evaluation harness on the same path; document mode is useful
                # only for dedicated runtime tests, not end-to-end evaluation.
                agent_config=RepairAgentConfig(
                    max_rounds=max_rounds,
                    max_pages=max_pages,
                    max_context_chars=30000,
                    mode="paged",
                    session_id=session_id,
                ),
                agent_factory=lambda toolbox, selected=model, sid=session_id: build_quality_repair_agent(selected, toolbox, session_id=sid),
            )
            write_quality_package(execution.package, output_dir, replace_existing=True)
            _write_json(output_dir / "execution.json", {"session_id": execution.session_id, "accepted": execution.accepted, "final_revision_id": execution.final_revision_id, "attempts": [attempt.model_dump(mode="json") for attempt in execution.attempts]})
            before = parsed.markdown.splitlines(keepends=True)
            after = execution.package.optimized_markdown.splitlines(keepends=True)
            (output_dir / "markdown.diff").write_text("".join(unified_diff(before, after, fromfile="parsed.md", tofile="optimized.md")), encoding="utf-8")
            handoff = build_wiki_handoff(execution.package)
            write_wiki_handoff(handoff, output_dir / "wiki_handoff", replace_existing=True)
            accepted = [attempt for attempt in execution.attempts if attempt.accepted]
            changed_blocks = sorted({item for attempt in accepted for item in attempt.changed_block_ids})
            changed_tables = sorted({item for attempt in accepted for item in attempt.changed_table_ids})
            result = {
                "document": document, "parser": parser_name, "accepted": execution.accepted,
                "changed": bool(execution.package.optimized_markdown != parsed.markdown or changed_blocks or changed_tables),
                "changed_block_ids": changed_blocks, "changed_table_ids": changed_tables,
                "baseline_state": baseline.quality_report.state.value, "baseline_issues": len(baseline.quality_report.issues),
                "final_state": execution.package.quality_report.state.value, "final_issues": len(execution.package.quality_report.issues),
                "parsed_marker_recall": _recall(truth["markers"], parsed.markdown), "optimized_marker_recall": _recall(truth["markers"], execution.package.optimized_markdown),
                "parsed_fact_recall": _recall(truth["critical_facts"], parsed.markdown), "optimized_fact_recall": _recall(truth["critical_facts"], execution.package.optimized_markdown),
            }
        except Exception as exc:
            result = {"document": document, "parser": parser_name, "accepted": False, "fatal_error": f"{type(exc).__name__}: {exc}", "baseline_state": baseline.quality_report.state.value, "baseline_issues": len(baseline.quality_report.issues), "parsed_marker_recall": _recall(truth["markers"], parsed.markdown), "parsed_fact_recall": _recall(truth["critical_facts"], parsed.markdown)}
            _write_json(output_dir / "fatal_error.json", result)
        results.append(result)
        _write_json(EVAL_ROOT / f"summary-{parser_name}.json", {"results": results})
        print(f"[AGENT] done {document}/{parser_name} accepted={result.get('accepted')}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-root", type=Path, help="使用另一组独立评测目录")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("compile")
    sub.add_parser("manifest")
    parse = sub.add_parser("parse")
    parse.add_argument("--parser", choices=["mineru", "docling"], required=True)
    parse.add_argument("--document", required=True)
    repair = sub.add_parser("repair-all")
    repair.add_argument("--parser", choices=["mineru", "docling"], required=True)
    repair.add_argument("--document", action="append")
    repair.add_argument("--max-rounds", type=int, default=2)
    repair.add_argument("--max-pages", type=int)
    args = parser.parse_args()
    global EVAL_ROOT
    if args.eval_root:
        EVAL_ROOT = args.eval_root.resolve()
    if args.command == "compile":
        compile_documents()
    elif args.command == "manifest":
        build_manifest()
    elif args.command == "parse":
        parse_document(args.parser, args.document)
    else:
        names = args.document or list(_load_spec()["documents"])
        repair_all(
            args.parser,
            names,
            max_rounds=args.max_rounds,
            max_pages=args.max_pages,
        )


if __name__ == "__main__":
    main()
