"""质量层内部稳定哈希工具。

哈希只用于稳定 ID 和内部证据引用，不进入 Wiki 交付 JSON。
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
