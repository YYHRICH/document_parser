"""稳定哈希：四件套的 SHA-256 绑定（spec §10.3，M1 内存版，M5 加落盘）。

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
    """Pydantic 模型的确定性 JSON 序列化（固定缩进与末尾换行）。"""
    payload = model.model_dump_json(indent=2)
    return (payload + "\n").encode("utf-8")


def markdown_bytes(markdown: str) -> bytes:
    return markdown.encode("utf-8")
