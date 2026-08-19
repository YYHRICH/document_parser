"""Markdown semantic signatures used by deterministic repair validation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token


_SEMANTIC_FINGERPRINT_VERSION = "sem-v2"
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class MarkdownSemanticSignature:
    """Content that formatting-only repairs are not allowed to change."""

    visible_text: str
    protected_tokens: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...]

    def fingerprint(self) -> str:
        payload = json.dumps(
            {
                "visible_text": self.visible_text,
                "protected_tokens": self.protected_tokens,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"{_SEMANTIC_FINGERPRINT_VERSION}:{digest}"


def markdown_semantic_signature(markdown: str) -> MarkdownSemanticSignature:
    """Parse Markdown and retain visible punctuation plus sensitive payloads.

    Markdown decoration and whitespace are intentionally ignored. Code, raw HTML,
    links, images, math-extension tokens, and unknown extension payloads are kept
    separately so that a formatting repair cannot silently alter them.
    """

    parser = MarkdownIt("commonmark", {"html": True}).enable("table")
    visible_parts: list[str] = []
    protected: list[tuple[str, str, tuple[tuple[str, str], ...]]] = []

    for token in parser.parse(markdown):
        if token.type == "inline":
            _collect_inline_tokens(token.children or [], visible_parts, protected)
        elif token.type in {"fence", "code_block", "html_block"}:
            protected.append(_protected_token(token))
            if token.type != "html_block":
                visible_parts.append(token.content)
        elif token.content:
            # Parser extensions such as front matter should fail closed until an
            # explicit semantic policy for their token type is added.
            protected.append(_protected_token(token))

    visible_text = _WHITESPACE_RE.sub(" ", "".join(visible_parts)).strip()
    return MarkdownSemanticSignature(visible_text, tuple(protected))


def semantic_content_fingerprint(markdown: str) -> str:
    """Return a versioned fingerprint for semantically protected Markdown data."""

    return markdown_semantic_signature(markdown).fingerprint()


def _collect_inline_tokens(
    tokens: list[Token],
    visible_parts: list[str],
    protected: list[tuple[str, str, tuple[tuple[str, str], ...]]],
) -> None:
    for token in tokens:
        if token.type == "text":
            visible_parts.append(token.content)
        elif token.type in {"softbreak", "hardbreak"}:
            visible_parts.append(" ")
        elif token.type == "code_inline":
            visible_parts.append(token.content)
            protected.append(_protected_token(token))
        elif token.type in {"html_inline", "link_open", "image"}:
            if token.type == "image":
                visible_parts.append(token.content)
            protected.append(_protected_token(token))
        elif "math" in token.type:
            visible_parts.append(token.content)
            protected.append(_protected_token(token))
        elif token.children:
            _collect_inline_tokens(token.children, visible_parts, protected)
        elif token.content:
            # Preserve payloads emitted by syntax plugins we do not yet know.
            visible_parts.append(token.content)
            protected.append(_protected_token(token))


def _protected_token(
    token: Token,
) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    attrs: dict[str, Any] = dict(token.attrs or {})
    canonical_attrs = tuple(
        sorted((str(key), str(value)) for key, value in attrs.items())
    )
    return token.type, token.content, canonical_attrs
