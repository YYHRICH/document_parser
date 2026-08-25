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
import os
import json
import sys
from pathlib import Path

# 使包可被 import：仓库根目录即 document_parser 包（需要其父目录在 sys.path），
# tools 包本身在仓库根下（需要仓库根在 sys.path）
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT.parent))

from document_parser.domain.model.contracts import ParsedDocument  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "datasets" / "shared-dev-v1" / "manifest.jsonl"
FILES_DIR = REPO_ROOT / "datasets" / "shared-dev-v1" / "files"
DEFAULT_OUT = REPO_ROOT / "tests" / "quality" / "fixtures" / "parsed_documents"


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


# 需要 OCR 的类别（扫描件/图片）
_OCR_CATEGORIES = {"scanned_pdf", "jpg_image", "jpeg_image", "png_image"}

# 扩展名 -> MIME（与 manifest 一致）
_MIME_BY_SUFFIX = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def needs_ocr(entry: dict) -> bool:
    """按 manifest 类别判断该样例是否走 OCR 路径。"""
    return bool(set(entry.get("categories") or []) & _OCR_CATEGORIES)


def mime_type(source: Path) -> str:
    return _MIME_BY_SUFFIX.get(source.suffix.lower(), "application/octet-stream")


def _check_docling_env() -> None:
    """docling 必须在英文路径解释器 + TORCH_COMPILE_DISABLE=1 下运行。"""
    import sys

    if any(ord(ch) > 127 for ch in sys.prefix):
        raise SystemExit(
            "docling 解析需要在英文路径解释器下运行（C++ 层限制）。\n"
            "请改用: TORCH_COMPILE_DISABLE=1 C:/dp_venv_link/Scripts/python.exe -m tools.make_fixtures --parser docling ..."
        )
    if not os.environ.get("TORCH_COMPILE_DISABLE"):
        raise SystemExit("docling 解析需要设置 TORCH_COMPILE_DISABLE=1（本机无 MSVC 编译器）。")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 ParsedDocument fixtures")
    parser.add_argument(
        "--parser",
        choices=["fallback", "mineru", "docling"],
        default="fallback",
        help="解析器（默认 fallback 本地兜底）",
    )
    parser.add_argument(
        "--samples",
        required=True,
        help="逗号分隔的 sample_id，如 sdp-004,sdp-006；或 all 解析全部 12 个",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="输出目录（默认 tests/fixtures/parsed_documents）",
    )
    args = parser.parse_args()

    manifest = load_manifest()
    if args.samples.strip().lower() == "all":
        sample_ids = sorted(manifest.keys())
    else:
        sample_ids = [s.strip() for s in args.samples.split(",") if s.strip()]
    args.out.mkdir(parents=True, exist_ok=True)

    for sample_id in sample_ids:
        entry = manifest[sample_id]
        source = resolve_source(sample_id, manifest)
        if args.parser == "mineru":
            from tools.mineru_cloud import parse_pdf as mineru_parse

            parsed = mineru_parse(
                source,
                is_ocr=needs_ocr(entry),
                file_type=mime_type(source),
            )
        elif args.parser == "docling":
            _check_docling_env()
            from tools.docling_parser import parse_pdf as docling_parse

            parsed = docling_parse(source, file_type=mime_type(source))
        else:
            if source.suffix.lower() != ".pdf":
                print(f"[SKIP] {sample_id} ({source.suffix}) fallback 仅支持 PDF，跳过")
                continue
            from tools.fallback_parser import parse_pdf as fallback_parse

            parsed = fallback_parse(source, file_type=mime_type(source))

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
