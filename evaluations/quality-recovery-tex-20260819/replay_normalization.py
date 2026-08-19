"""对已有真实解析产物执行归一层回放，不调用外部模型或解析服务。"""

from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT.parent))

from document_parser.core.contracts import ParsedDocument
from document_parser.parsers.normalization import normalize_parsed_document


EVAL_ROOT = Path(__file__).resolve().parent


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def replay(path: Path) -> dict[str, object]:
    original = ParsedDocument.model_validate_json(path.read_text(encoding="utf-8"))
    parser_label = path.parent.name
    normalized = normalize_parsed_document(original, parser_label=parser_label)
    repeated = normalize_parsed_document(original, parser_label=parser_label)

    output_dir = path.parent
    normalized_path = output_dir / "normalized_document.json"
    normalized_path.write_text(
        normalized.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    stable_ids_repeatable = [block.id for block in normalized.blocks] == [
        block.id for block in repeated.blocks
    ]
    return {
        "document": path.parent.parent.name,
        "parser": parser_label,
        "blocks_before": len(original.blocks),
        "blocks_after": len(normalized.blocks),
        "tables_before": len(original.tables),
        "tables_after": len(normalized.tables),
        "warnings_before": len(original.warnings),
        "warnings_after": len(normalized.warnings),
        "markdown_changed": normalized.markdown != original.markdown,
        "stable_ids_repeatable": stable_ids_repeatable,
        "normalization": normalized.provenance.parameters.get("normalization", {}),
        "warnings": normalized.warnings,
    }


def main() -> None:
    parse_root = EVAL_ROOT / "parses"
    paths = sorted(
        list(parse_root.glob("*/mineru/parsed_document.json"))
        + list(parse_root.glob("*/docling/parsed_document.json"))
    )
    summaries = [replay(path) for path in paths]
    _write_json(EVAL_ROOT / "normalization_summary.json", {"results": summaries})
    for summary in summaries:
        print(
            "{document}/{parser}: blocks {blocks_before}->{blocks_after}, "
            "tables {tables_before}->{tables_after}, warnings "
            "{warnings_before}->{warnings_after}, markdown_changed={markdown_changed}, "
            "stable_ids_repeatable={stable_ids_repeatable}".format(**summary)
        )


if __name__ == "__main__":
    main()
