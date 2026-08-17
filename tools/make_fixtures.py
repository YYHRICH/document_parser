"""生成质量层开发用的 ParsedDocument fixtures。

用法：
    python -m tools.make_fixtures --parser fallback --samples sdp-004,sdp-006
    python -m tools.make_fixtures --parser mineru --samples sdp-004

解析器：
    fallback  -> tools/fallback_parser.py（pdfplumber，本地，无需网络）
    mineru    -> tools/mineru_cloud.py（MinerU 云 API，需 MINERU_API_KEY）

输出：tests/fixtures/parsed_documents/{sample_id}-{parser}.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 使包可被 import：仓库根目录即 document_parser 包（需要其父目录在 sys.path），
# tools 包本身在仓库根下（需要仓库根在 sys.path）
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT.parent))

from document_parser.core.contracts import ParsedDocument  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "datasets" / "shared-dev-v1" / "manifest.jsonl"
FILES_DIR = REPO_ROOT / "datasets" / "shared-dev-v1" / "files"
DEFAULT_OUT = REPO_ROOT / "tests" / "fixtures" / "parsed_documents"


def load_manifest() -> dict[str, dict]:
    """manifest.jsonl -> {sample_id: entry}"""
    entries: dict[str, dict] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        entries[entry["sample_id"]] = entry
    return entries


def resolve_source(sample_id: str, manifest: dict[str, dict]) -> Path:
    entry = manifest.get(sample_id)
    if entry is None:
        raise SystemExit(f"manifest 中不存在 sample_id: {sample_id}")
    source = FILES_DIR / entry["storage_uri"].split("/")[-1]
    if not source.exists():
        raise SystemExit(f"源文件不存在: {source}")
    return source


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 ParsedDocument fixtures")
    parser.add_argument(
        "--parser",
        choices=["fallback", "mineru"],
        default="fallback",
        help="解析器（默认 fallback 本地兜底）",
    )
    parser.add_argument(
        "--samples",
        required=True,
        help="逗号分隔的 sample_id，如 sdp-004,sdp-006",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="输出目录（默认 tests/fixtures/parsed_documents）",
    )
    args = parser.parse_args()

    manifest = load_manifest()
    sample_ids = [s.strip() for s in args.samples.split(",") if s.strip()]
    args.out.mkdir(parents=True, exist_ok=True)

    for sample_id in sample_ids:
        source = resolve_source(sample_id, manifest)
        if args.parser == "mineru":
            from tools.mineru_cloud import parse_pdf as mineru_parse

            parsed = mineru_parse(source)
        else:
            from tools.fallback_parser import parse_pdf as fallback_parse

            parsed = fallback_parse(source)

        out_path = args.out / f"{sample_id}-{args.parser}.json"
        payload = parsed.model_dump_json(indent=2)
        out_path.write_text(payload + "\n", encoding="utf-8")
        # 重新加载验证可逆
        ParsedDocument.model_validate_json(payload)
        print(
            f"[OK] {sample_id} -> {out_path.name} "
            f"(blocks={len(parsed.blocks)}, tables={len(parsed.tables)}, "
            f"parser={parsed.provenance.parser_id})"
        )


if __name__ == "__main__":
    main()
