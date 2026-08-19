"""无需启动 Web 的路由调试入口。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..core.contracts import DocumentSignals
from .config import RouteProfile
from .router import ModelRouter


def main() -> int:
    parser = argparse.ArgumentParser(description="输出文档模型 RoutingDecision")
    parser.add_argument("source", type=Path)
    parser.add_argument("--profile", choices=[item.value for item in RouteProfile])
    parser.add_argument(
        "--allow-cloud", action=argparse.BooleanOptionalAction, default=None
    )
    parser.add_argument(
        "--libreoffice-available",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument("--parser-id")
    parser.add_argument("--page-count", type=int)
    parser.add_argument(
        "--has-text-layer", action=argparse.BooleanOptionalAction, default=None
    )
    parser.add_argument("--scanned-page-ratio", type=float)
    parser.add_argument("--language")
    args = parser.parse_args()

    source = args.source.resolve()
    signals = DocumentSignals(
        extension=source.suffix.lower() or ".bin",
        size_bytes=source.stat().st_size,
        page_count=args.page_count,
        has_text_layer=args.has_text_layer,
        scanned_page_ratio=args.scanned_page_ratio,
        language_hint=args.language,
    )
    decision = ModelRouter.from_environment().route(
        signals,
        requested_parser_id=args.parser_id,
        profile=args.profile,
        allow_cloud=args.allow_cloud,
        libreoffice_available=args.libreoffice_available,
    )
    print(json.dumps(decision.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0
