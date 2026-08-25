"""Build a document package directory from a parsed document JSON file."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT.parent))

from document_parser.infra.packaging.document_package import load_document_package, write_document_package  # noqa: E402
from document_parser.domain.model.contracts import ParsedDocument  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build document_package/ from parsed_document.json",
    )
    parser.add_argument("parsed_document", type=Path)
    parser.add_argument("package_root", type=Path)
    parser.add_argument("--source", type=Path, help="Optional original source file")
    parser.add_argument(
        "--native-dir",
        type=Path,
        help="Optional directory containing native sidecar files",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    document = ParsedDocument.model_validate_json(
        args.parsed_document.read_text(encoding="utf-8")
    )

    if args.native_dir is not None:
        _copy_tree(args.native_dir, args.package_root / "native")

    if args.source is not None:
        args.package_root.mkdir(parents=True, exist_ok=True)

    write_document_package(
        document,
        args.package_root,
        source_path=args.source,
    )

    # 回读一次，确保目录真的可被统一校验。
    load_document_package(args.package_root)
    print(f"built package at: {args.package_root}")


def _copy_tree(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


if __name__ == "__main__":
    main()
