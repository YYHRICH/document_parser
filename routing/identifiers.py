"""Stable parser identifiers owned by routing policy.

These values are protocol identifiers, not imports from parser implementations.
Keeping them here lets the routing package remain independently importable while
its policy still names the parser families it can prefer.
"""

from __future__ import annotations


MARKITDOWN_ID = "microsoft.markitdown"
ANYDOC_ID = "anydoc"
DOCLING_ID = "docling"
MINERU_ID = "mineru"
OCR_ID = "ocr"
