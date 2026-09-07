"""Materialize selected dataset outputs as validated ParsedDocument/QualityPackage bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import re
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(_PACKAGE_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT.parent))

from document_parser.domain.model.contracts import AssetKind, DocumentAsset, ParseConfidence
from document_parser.domain.normalization.bundle import (
    ParserNormalizationBundle,
    available_capability,
    stable_uuid,
    unavailable_capability,
)
from document_parser.domain.quality.pipeline import run_pipeline
from document_parser.infra.packaging.document_package import (
    validate_parsed_document_integrity,
    write_document_package,
)
from document_parser.infra.quality_packaging.artifacts import build_package_artifacts
from tools.replay_quality_on_dataset import _stable_blocks_and_tables


MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+[\"'][^\"']*[\"'])?\)")
HTML_IMAGE = re.compile(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--selection-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def local_image_references(markdown: str) -> list[str]:
    values = [*MARKDOWN_IMAGE.findall(markdown), *HTML_IMAGE.findall(markdown)]
    result: list[str] = []
    for value in values:
        split = urlsplit(value.strip())
        if split.scheme or split.netloc or value.lower().startswith("data:"):
            continue
        normalized = unquote(split.path).replace("\\", "/").removeprefix("./")
        path = PurePosixPath(normalized)
        if not normalized or path.is_absolute() or ".." in path.parts:
            raise ValueError(f"unsafe image reference: {value}")
        if normalized not in result:
            result.append(normalized)
    return result


def selected_candidate(record: dict) -> dict:
    return next(candidate for candidate in record["candidates"] if candidate["selected"])


def materialize_one(record: dict, *, results_root: Path, output_root: Path) -> dict:
    candidate = selected_candidate(record)
    relative_output = Path(candidate["relative_output"])
    markdown_path = results_root / relative_output
    raw = markdown_path.read_bytes()
    markdown = raw.decode("utf-8", errors="replace")
    blocks, tables = _stable_blocks_and_tables(markdown, candidate["model"], relative_output.as_posix())
    references = local_image_references(markdown)
    assets: list[DocumentAsset] = []
    missing: list[str] = []
    for reference in references:
        source = (markdown_path.parent / Path(reference)).resolve()
        if markdown_path.parent.resolve() not in source.parents or not source.is_file():
            missing.append(reference)
            continue
        content = source.read_bytes()
        block_ids = [str(block.id) for block in blocks if reference in block.markdown or reference.replace("/", "\\") in block.markdown]
        assets.append(
            DocumentAsset(
                path=reference,
                kind=AssetKind.IMAGE,
                file_type=mimetypes.guess_type(source.name)[0] or "application/octet-stream",
                content=content,
                sha256=sha256(content),
                referenced_by_block_ids=block_ids,
                metadata={
                    "caption_source": "unavailable",
                    "evidence_status": "verified_file_only",
                    "imported_from": relative_output.as_posix(),
                },
            )
        )
    if missing:
        raise ValueError(f"{record['source_id']} has dangling image references: {missing[:10]}")

    output_sha = sha256(raw)
    document_id = stable_uuid("allin6-formal-import", record["source_id"], output_sha)
    capabilities = {
        "text": available_capability(granularity="markdown_block"),
        "assets": available_capability(granularity="file") if assets else unavailable_capability("selected Markdown has no local image references"),
        "page": unavailable_capability("saved Markdown output does not retain verified page evidence"),
        "bbox": unavailable_capability("saved Markdown output does not retain verified coordinates"),
        "ocr": unavailable_capability("saved Markdown output does not retain structured OCR spans"),
        "tables": unavailable_capability("only rendered Markdown/HTML tables are available; native cells were not fabricated"),
    }
    document = ParserNormalizationBundle.from_minimal_markdown(
        document_id=document_id,
        filename=markdown_path.name,
        file_type="text/markdown",
        markdown=markdown,
        parser_id=candidate["model"],
        parser_version="saved-dataset-output",
        parser_parameters={"selection_policy": record["selection_policy"], "quality_scope": "formal_import_from_saved_output"},
        source_size_bytes=len(raw),
        source_sha256=output_sha,
        blocks=blocks,
        assets=assets,
        tables=tables,
        confidence=ParseConfidence(text=0.5, layout=0.0, reading_order=0.5, table=0.0, overall=0.25),
        capabilities=capabilities,
        warnings=["Imported from saved parser output; missing native evidence was not fabricated."],
        alternatives=[{"model": item["model"], "quality_state": item["quality_state"], "selected": item["selected"]} for item in record["candidates"]],
    ).to_parsed_document()
    quality = run_pipeline(document)
    if quality.quality_report.state.value in {"rejected", "reparse_required"}:
        raise ValueError(f"{record['source_id']} formal quality gate returned {quality.quality_report.state.value}")

    parse_id = f"parse_{output_sha[:16]}"
    package_root = output_root / "documents" / record["source_id"]
    write_document_package(document, package_root)
    for name, content in build_package_artifacts(quality).files.items():
        (package_root / name).write_bytes(content)
    validate_parsed_document_integrity(document, package_root=package_root)
    package_record = {
        "source_id": record["source_id"],
        "parse_id": parse_id,
        "document_id": str(document_id),
        "parser_id": candidate["model"],
        "quality_state": quality.quality_report.state.value,
        "asset_count": len(assets),
        "source_key": record["source_key"],
        "package_path": f"documents/{record['source_id']}",
        "selected_output_sha256": output_sha,
    }
    (package_root / "package-record.json").write_text(json.dumps(package_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return package_record


def main() -> None:
    args = parse_args()
    records = [json.loads(line) for line in args.selection_manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    materialized = [materialize_one(record, results_root=args.results_root, output_root=args.output_dir) for record in records]
    with (args.output_dir / "dataset-manifest.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for record in materialized:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    summary = {
        "schema_name": "FormalDatasetPackageSummary",
        "schema_version": "1.0",
        "source_count": len(materialized),
        "package_count": len(materialized),
        "asset_count": sum(record["asset_count"] for record in materialized),
        "rejected_count": sum(record["quality_state"] in {"rejected", "reparse_required"} for record in materialized),
        "dangling_asset_reference_count": 0,
        "import_scope": "saved_parser_outputs_without_fabricated_native_evidence",
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
