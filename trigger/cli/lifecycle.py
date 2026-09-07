"""One-shot folder lifecycle scan CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
if str(_PACKAGE_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT.parent))

from document_parser.app.bootstrap import build_source_lifecycle  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="扫描 raw 目录并同步解析生命周期。")
    parser.add_argument("raw_root", type=Path)
    parser.add_argument("--parser", default=None)
    parser.add_argument("--options-json", default=None)
    parser.add_argument("--state-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--mobilework-root",
        type=Path,
        default=None,
        help="可选：把通过质量门的结果同步到该 mobilework 仓库的 raw/ 目录",
    )
    parser.add_argument(
        "--mmwiki-root",
        type=Path,
        default=None,
        help="可选：把 ParsedDocument 自动发布到杨组多模态交换目录",
    )
    args = parser.parse_args(argv)
    try:
        options = json.loads(args.options_json) if args.options_json else {}
        if not isinstance(options, dict):
            raise ValueError("options-json must be a JSON object")
        state_base = args.raw_root.parent if args.raw_root.name == "sources" else args.raw_root
        state = args.state_dir or state_base / ".llmwiki" / ".document_parser"
        output = args.output_dir or state / "packages"
        lifecycle = build_source_lifecycle(
            raw_root=args.raw_root,
            state_root=state,
            storage_root=output,
            mobilework_root=args.mobilework_root,
            mmwiki_root=args.mmwiki_root,
        )
        events = lifecycle.scan(parser_id=args.parser, options=options)
    except Exception as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2
    for event in events:
        print(json.dumps(event.as_dict(), ensure_ascii=False, sort_keys=True))
    return 1 if any(event.error for event in events) else 0


if __name__ == "__main__":
    raise SystemExit(main())
