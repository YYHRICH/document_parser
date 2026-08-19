"""Source-span projection between ParsedDocument blocks and root Markdown."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib

from markdown_it import MarkdownIt

from document_parser.core.contracts import ParsedDocument


_SOURCE_TOKEN_TYPES = {
    "paragraph_open",
    "heading_open",
    "fence",
    "code_block",
    "html_block",
    "table_open",
}


class MarkdownProjectionError(ValueError):
    """A block operation cannot be projected to root Markdown without guessing."""


@dataclass(frozen=True)
class MarkdownSpan:
    """Exact block content and its containing Markdown token source range."""

    block_id: str
    content_start: int
    content_end: int
    source_start: int
    source_end: int
    edit_start: int
    edit_end: int
    expected_sha256: str
    owns_source: bool


@dataclass(frozen=True)
class MarkdownProjection:
    """Deterministic block-to-source mapping for one ParsedDocument revision."""

    spans: dict[str, MarkdownSpan]
    unmapped_block_ids: tuple[str, ...]

    def require_content(self, block_id: str) -> MarkdownSpan:
        span = self.spans.get(block_id)
        if span is None:
            raise MarkdownProjectionError(
                f"block {block_id} 无法精确映射到根 Markdown。"
            )
        return span

    def require_source(self, block_id: str) -> MarkdownSpan:
        span = self.require_content(block_id)
        if not span.owns_source:
            raise MarkdownProjectionError(
                f"block {block_id} 不独占完整 Markdown token，不能安全移动或删除。"
            )
        return span


@dataclass(frozen=True)
class _SourceRange:
    start: int
    end: int


def build_markdown_projection(document: ParsedDocument) -> MarkdownProjection:
    """Map exact block Markdown occurrences into parser token source ranges.

    Repeated block text is accepted only when the number of source occurrences
    equals the number of blocks carrying that exact text. This lets document
    order disambiguate genuine duplicates without guessing among extra matches.
    """

    source_ranges = _source_ranges(document.markdown)
    blocks_by_markdown: dict[str, list] = defaultdict(list)
    for block in document.blocks:
        if block.markdown:
            blocks_by_markdown[block.markdown].append(block)

    assignments: dict[str, tuple[int, int, _SourceRange]] = {}
    for block_markdown, blocks in blocks_by_markdown.items():
        occurrences = [
            occurrence
            for occurrence in _find_occurrences(document.markdown, block_markdown)
            if _smallest_containing_range(source_ranges, occurrence) is not None
        ]
        if len(occurrences) != len(blocks):
            continue
        for block, occurrence in zip(blocks, occurrences):
            source_range = _smallest_containing_range(source_ranges, occurrence)
            if source_range is not None:
                assignments[str(block.id)] = (*occurrence, source_range)

    invalid_ids = _invalid_assignment_ids(document, assignments)
    for block_id in invalid_ids:
        assignments.pop(block_id, None)

    source_usage = Counter(
        (source_range.start, source_range.end)
        for _, _, source_range in assignments.values()
    )
    range_edit_ends = _range_edit_ends(document.markdown, source_ranges)
    spans: dict[str, MarkdownSpan] = {}
    for block in document.blocks:
        block_id = str(block.id)
        assignment = assignments.get(block_id)
        if assignment is None:
            continue
        content_start, content_end, source_range = assignment
        source_text = document.markdown[source_range.start : source_range.end]
        owns_source = (
            source_usage[(source_range.start, source_range.end)] == 1
            and source_text.strip() == block.markdown.strip()
        )
        spans[block_id] = MarkdownSpan(
            block_id=block_id,
            content_start=content_start,
            content_end=content_end,
            source_start=source_range.start,
            source_end=source_range.end,
            edit_start=source_range.start,
            edit_end=range_edit_ends[source_range],
            expected_sha256=_sha256(block.markdown),
            owns_source=owns_source,
        )

    unmapped = tuple(
        str(block.id) for block in document.blocks if str(block.id) not in spans
    )
    return MarkdownProjection(spans=spans, unmapped_block_ids=unmapped)


def replace_block_source(
    document: ParsedDocument,
    block_id: str,
    replacement: str,
) -> str:
    """Replace one exact block content span and preserve all surrounding source."""

    span = build_markdown_projection(document).require_content(block_id)
    current = document.markdown[span.content_start : span.content_end]
    if _sha256(current) != span.expected_sha256:
        raise MarkdownProjectionError(
            f"block {block_id} 的根 Markdown span 已过期。"
        )
    return (
        document.markdown[: span.content_start]
        + replacement
        + document.markdown[span.content_end :]
    )


def root_rewrite_preserves_block_sources(
    before: ParsedDocument,
    after: ParsedDocument,
) -> bool:
    """Allow root-only edits only in gaps between Markdown source tokens."""

    if before.markdown == after.markdown:
        return True
    before_sources = [
        _normalize_eol(before.markdown[item.start : item.end])
        for item in _source_ranges(before.markdown)
    ]
    after_sources = [
        _normalize_eol(after.markdown[item.start : item.end])
        for item in _source_ranges(after.markdown)
    ]
    return before_sources == after_sources


def _source_ranges(markdown: str) -> list[_SourceRange]:
    parser = MarkdownIt("commonmark", {"html": True}).enable("table")
    offsets = _line_offsets(markdown)
    ranges: set[tuple[int, int]] = set()
    for token in parser.parse(markdown):
        if token.type not in _SOURCE_TOKEN_TYPES or token.map is None:
            continue
        start_line, end_line = token.map
        if start_line >= len(offsets) or end_line >= len(offsets):
            continue
        ranges.add((offsets[start_line], offsets[end_line]))
    return [_SourceRange(start, end) for start, end in sorted(ranges)]


def _line_offsets(markdown: str) -> list[int]:
    offsets = [0]
    offsets.extend(
        index + 1 for index, character in enumerate(markdown) if character == "\n"
    )
    if offsets[-1] != len(markdown):
        offsets.append(len(markdown))
    return offsets


def _find_occurrences(markdown: str, needle: str) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    start = 0
    while True:
        index = markdown.find(needle, start)
        if index < 0:
            return result
        result.append((index, index + len(needle)))
        start = index + max(len(needle), 1)


def _smallest_containing_range(
    ranges: list[_SourceRange],
    occurrence: tuple[int, int],
) -> _SourceRange | None:
    start, end = occurrence
    candidates = [
        source_range
        for source_range in ranges
        if source_range.start <= start and end <= source_range.end
    ]
    return min(
        candidates,
        key=lambda source_range: (
            source_range.end - source_range.start,
            source_range.start,
        ),
        default=None,
    )


def _invalid_assignment_ids(document, assignments) -> set[str]:
    """Reject overlapping or non-monotonic content assignments."""

    invalid: set[str] = set()
    previous_id: str | None = None
    previous_end = -1
    for block in document.blocks:
        block_id = str(block.id)
        assignment = assignments.get(block_id)
        if assignment is None:
            continue
        start, end, _ = assignment
        if start < previous_end:
            invalid.add(block_id)
            if previous_id is not None:
                invalid.add(previous_id)
        else:
            previous_id = block_id
            previous_end = end
    return invalid


def _range_edit_ends(
    markdown: str,
    ranges: list[_SourceRange],
) -> dict[_SourceRange, int]:
    result: dict[_SourceRange, int] = {}
    for index, source_range in enumerate(ranges):
        next_start = (
            ranges[index + 1].start if index + 1 < len(ranges) else len(markdown)
        )
        gap = markdown[source_range.end : next_start]
        result[source_range] = next_start if not gap.strip() else source_range.end
    return result


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalize_eol(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")
