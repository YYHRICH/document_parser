"""Compatibility imports for legacy repair callers.

HTML table parsing now belongs to ``quality.representations.table_html`` so the
representation resolver and legacy repair rule share exactly one parser.
"""

from quality.representations.table_html import convert_html_tables, html_table_to_markdown

__all__ = ["convert_html_tables", "html_table_to_markdown"]
