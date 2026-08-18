"""稳定哈希：四件套的 SHA-256 绑定（spec §10.3，证据、完整性与质量门 内存版，质量产物与原子落盘 加落盘）。

哈希顺序：
1. optimized.md 字节；
2. canonical_document.json 字节；
3. quality_report.json 字节（其 artifacts 含 1/2 的哈希）；
4. package_manifest 记录 1/2/3 的哈希。
quality_report 与 manifest 不哈希自身（D-04）。
"""

from __future__ import annotations

import hashlib
import json


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def stable_json_bytes(model) -> bytes:
    """Serialize a Pydantic model/dict deterministically as UTF-8 JSON."""
    if hasattr(model, "model_dump"):
        payload = model.model_dump(mode="json")
    else:
        payload = model
    text = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        separators=(",", ": "),
    )
    return (text + "\n").encode("utf-8")


def markdown_bytes(markdown: str) -> bytes:
    """Encode optimized Markdown exactly as represented (UTF-8)."""
    return markdown.encode("utf-8")
