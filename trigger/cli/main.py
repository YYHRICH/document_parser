"""CLI 触发入口：与 HTTP 共用同一套 app 用例（阶段 4 多入口）。

用法示例（仓库根目录下）：:

    .venv\\Scripts\\python.exe -m trigger.cli.main ./examples/contracts/parsed_document.json
    .venv\\Scripts\\python.exe -m trigger.cli.main report.docx --parser docling --options-json "{\"allow_cloud\": false}"
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from pathlib import Path

# 仓库统一以 document_parser.* 命名空间组织；python -m 运行时把父目录放进 sys.path。
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
if str(_PACKAGE_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT.parent))

from document_parser.app.bootstrap import build_application  # noqa: E402
from document_parser.domain.model.contracts import ParseRequest  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="document-parser",
        description="文档解析 CLI：复用与 HTTP 相同的 ParseDocumentUseCase。",
    )
    parser.add_argument("file", type=Path, help="待解析的源文件")
    parser.add_argument("--parser", default=None, help="指定解析器 ID（默认由路由决策自动选择）")
    parser.add_argument(
        "--options-json",
        default=None,
        help='解析选项 JSON，例如 {"allow_cloud": false, "route_profile": "quality_first"}',
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/api",
        help="解析产物存储根目录（默认 outputs/api）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.file.is_file():
        print(f"错误：文件不存在 {args.file}", file=sys.stderr)
        return 2

    try:
        options = json.loads(args.options_json) if args.options_json else {}
    except json.JSONDecodeError as error:
        print(f"错误：options_json 必须是合法 JSON：{error}", file=sys.stderr)
        return 2
    if not isinstance(options, dict):
        print("错误：options_json 必须是 JSON 对象", file=sys.stderr)
        return 2

    request = ParseRequest(
        filename=args.file.name,
        file_type=mimetypes.guess_type(args.file.name)[0] or "application/octet-stream",
        content=args.file.read_bytes(),
        parser_id=args.parser,
        options=options,
    )
    application = build_application(storage_root=args.output_dir)
    result = application.parse_document.execute(request)

    document = result.document
    print(f"parse_id:         {result.parse_id}")
    print(f"package:          {result.package_root}")
    print(f"document_id:      {document.document_id}")
    print(f"parser:           {document.provenance.parser_id}")
    print(f"routing_mode:     {document.provenance.routing_mode}")
    print(f"native_artifacts: {len(document.native_artifacts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
