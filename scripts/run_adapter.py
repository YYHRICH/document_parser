"""Run one parser adapter and materialize a document package."""

from __future__ import annotations

import argparse
import mimetypes
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser.infra.packaging.document_package import write_document_package  # noqa: E402
from document_parser.domain.model.contracts import ParseRequest  # noqa: E402
from document_parser.domain.service.source_inspector import SimpleSourceInspector  # noqa: E402
from document_parser.infra.parsers.registry import get_parser  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a single parser adapter and build document_package/.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("package_root", type=Path)
    parser.add_argument(
        "--parser-id",
        default="docling",
        choices=["docling", "mineru", "ocr", "microsoft.markitdown"],
    )
    parser.add_argument(
        "--native-output-dir",
        type=Path,
        help="Optional directory already produced by the real parser.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    file_type = mimetypes.guess_type(args.source.name)[0] or "application/octet-stream"
    options = {}
    if args.native_output_dir is not None:
        options["native_output_dir"] = str(args.native_output_dir)
    request = ParseRequest(
        filename=args.source.name,
        file_type=file_type,
        content=args.source.read_bytes(),
        parser_id=args.parser_id,
        options=options,
    )
    signals = SimpleSourceInspector().inspect(request)
    parser = get_parser(args.parser_id)

    if hasattr(parser, "normalize"):
        bundle = parser.normalize(request, signals)
        document = bundle.to_parsed_document()
        native_files = bundle.native_files
    else:
        document = parser.parse(request, signals)
        native_files = {}

    write_document_package(
        document,
        args.package_root,
        source_path=args.source,
        native_files=native_files,
    )
    print(f"built package at: {args.package_root}")


if __name__ == "__main__":
    main()
