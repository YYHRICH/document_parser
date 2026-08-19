"""公式和数学符号的保真归一化。

这里不把某个解析器当作另一个解析器的替代品。对 MinerU，PDF 原生文字层只
作为所选解析器结果的同源证据：只有当解析文本是原生文字的严格子序列，且
差异仅由通用数学运算符组成时，才允许恢复；其余情况必须留下不确定状态。
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from document_parser.core.contracts import BlockKind, DocumentBlock


FORMULA_UNAVAILABLE_MARKER = "<!-- formula-not-decoded -->"
FORMULA_PLACEHOLDER = "[[FORMULA_UNAVAILABLE]]"

# 通用数学 token 集，不针对 <=、某个文件或某个语言补丁。
_MATH_TOKENS = frozenset(
    {
        "<", ">", "=", "<=", ">=", "!=", "≤", "≥", "≠", "≈", "±",
        "×", "÷", "∈", "∉", "∞", "√", "∑", "∫", "∂", "Δ", "+", "-",
        "−", "*", "/", "^", "_",
    }
)
_TOKEN_RE = re.compile(
    r"(?:<=|>=|!=|\\[A-Za-z]+|[<>≤≥≠≈±×÷∈∉∞√∑∫∂Δ+\-−*/^_=]|"
    r"[A-Za-z]+(?:[-'][A-Za-z0-9]*)?|[0-9]+(?:[.,][0-9]+)?|"
    r"[\u3400-\u9fff]+|[^\s])"
)


@dataclass(frozen=True)
class PdfTextLine:
    page_number: int
    text: str
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class FormulaNormalizationResult:
    blocks: list[DocumentBlock]
    markdown: str
    warnings: list[str]
    recovered_count: int
    incomplete_count: int
    placeholder_count: int


def tokenize_math_text(value: str | None) -> list[str]:
    """用宽松、可解释的 token 化比较文本，不做语义猜测。"""

    return _TOKEN_RE.findall(value or "")


def _is_subsequence_with_math_insertions(
    parsed_tokens: list[str], source_tokens: list[str]
) -> tuple[bool, list[str]]:
    """判断 source 是否只比 parsed 多了数学 token。"""

    matcher = difflib.SequenceMatcher(a=parsed_tokens, b=source_tokens, autojunk=False)
    inserted: list[str] = []
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            inserted.extend(source_tokens[j1:j2])
        elif tag != "equal":
            return False, []
    return bool(inserted) and all(token in _MATH_TOKENS for token in inserted), inserted


def recover_missing_math_tokens(parsed_text: str, source_text: str) -> tuple[str | None, list[str]]:
    """恢复同一行 PDF 原生文本中丢失的数学 token。

    返回 ``None`` 表示证据不满足严格条件；调用方不得在这种情况下猜测。
    """

    parsed_tokens = tokenize_math_text(parsed_text)
    source_tokens = tokenize_math_text(source_text)
    ok, inserted = _is_subsequence_with_math_insertions(parsed_tokens, source_tokens)
    if not ok:
        return None, []
    return source_text, inserted


def _load_pdf_text_lines(source_path: Path) -> list[PdfTextLine]:
    """按页和文字行读取 PDF 原生文字层；pdfplumber 是可选依赖。"""

    try:
        import pdfplumber
    except ImportError:
        return []

    lines: list[PdfTextLine] = []
    try:
        with pdfplumber.open(source_path) as pdf:
            for page in pdf.pages:
                words = page.extract_words(keep_blank_chars=False, use_text_flow=True)
                grouped: list[list[dict[str, Any]]] = []
                for word in words:
                    top = float(word.get("top", 0))
                    group = next(
                        (
                            candidate
                            for candidate in grouped
                            if abs(float(candidate[0].get("top", 0)) - top) <= 3
                        ),
                        None,
                    )
                    if group is None:
                        grouped.append([word])
                    else:
                        group.append(word)
                for group in grouped:
                    ordered = sorted(group, key=lambda word: float(word.get("x0", 0)))
                    text = " ".join(str(word.get("text", "")) for word in ordered).strip()
                    if not text:
                        continue
                    lines.append(
                        PdfTextLine(
                            page_number=page.page_number,
                            text=text,
                            bbox=(
                                min(float(word.get("x0", 0)) for word in ordered),
                                min(float(word.get("top", 0)) for word in ordered),
                                max(float(word.get("x1", 0)) for word in ordered),
                                max(float(word.get("bottom", 0)) for word in ordered),
                            ),
                        )
                    )
    except Exception:
        # 原生文字层只是补充证据，解析失败不能影响主解析结果。
        return []
    return lines


def _bbox_overlap_ratio(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    if right <= left or bottom <= top:
        return 0.0
    intersection = (right - left) * (bottom - top)
    area = max((first[2] - first[0]) * (first[3] - first[1]), 1.0)
    return intersection / area


def _candidate_lines_for_block(
    block: DocumentBlock, lines: list[PdfTextLine]
) -> list[PdfTextLine]:
    if block.anchor.page_number is None or block.anchor.bbox is None:
        return []
    # MinerU 与 pdfplumber 的 PDF 坐标可能有缩放/偏移，不能因某一条无关行
    # 恰好 bbox 重叠就排除真正的行。保留同页全部候选，最终由严格 token
    # 子序列和“证据唯一”两道条件筛选。
    candidates = [line for line in lines if line.page_number == block.anchor.page_number]
    return sorted(
        candidates,
        key=lambda line: _bbox_overlap_ratio(block.anchor.bbox, line.bbox),
        reverse=True,
    )


def normalize_formula_evidence(
    blocks: list[DocumentBlock],
    markdown: str,
    *,
    parser_label: str,
    source_path: Path | None = None,
) -> FormulaNormalizationResult:
    """处理 Docling 占位符，并对 MinerU 做同源 PDF token 保真。"""

    warnings: list[str] = []
    recovered_count = 0
    incomplete_count = 0
    placeholder_count = 0
    result_blocks: list[DocumentBlock] = []
    pdf_lines = (
        _load_pdf_text_lines(source_path)
        if parser_label == "mineru-cloud" and source_path and source_path.exists()
        else []
    )

    for block in blocks:
        updated = block
        block_text = block.text or ""
        block_markdown = block.markdown or ""
        metadata = dict(block.metadata)

        if FORMULA_UNAVAILABLE_MARKER in block_text or FORMULA_UNAVAILABLE_MARKER in block_markdown:
            block_text = block_text.replace(FORMULA_UNAVAILABLE_MARKER, FORMULA_PLACEHOLDER)
            block_markdown = block_markdown.replace(FORMULA_UNAVAILABLE_MARKER, FORMULA_PLACEHOLDER)
            metadata.update(
                {
                    "formula_status": "incomplete",
                    "formula_reason": "formula_not_decoded",
                    "formula_placeholder": FORMULA_PLACEHOLDER,
                }
            )
            incomplete_count += 1
            placeholder_count += 1
            warnings.append(f"{parser_label}:{block.source_block_id}: 公式未解析，已保留占位符。")

        if (
            parser_label == "mineru-cloud"
            and block.kind in {BlockKind.FORMULA, BlockKind.PARAGRAPH, BlockKind.HEADING, BlockKind.LIST}
            and block_text
            and pdf_lines
        ):
            recoveries: list[tuple[str, list[str]]] = []
            for candidate in _candidate_lines_for_block(block, pdf_lines):
                recovered, inserted = recover_missing_math_tokens(block_text, candidate.text)
                if recovered is not None:
                    recoveries.append((recovered, inserted))
            # 多个同样成立的原生行说明证据不唯一，宁可交给质量层复核。
            if len(recoveries) != 1:
                if len(recoveries) > 1:
                    metadata["formula_status"] = "ambiguous_pdf_text_evidence"
                recoveries = []
            if recoveries:
                recovered, inserted = recoveries[0]
                block_text = recovered
                block_markdown = recovered if block_markdown == block.text else block_markdown
                if block.markdown and block.markdown in markdown:
                    markdown = markdown.replace(block.markdown, block_markdown, 1)
                metadata.update(
                    {
                        "formula_status": "recovered_from_pdf_text",
                        "formula_evidence_source": "pdf-native-text",
                        "formula_inserted_tokens": inserted,
                    }
                )
                recovered_count += 1

        if block_text != block.text or block_markdown != block.markdown or metadata != block.metadata:
            updated = block.model_copy(
                update={"text": block_text, "markdown": block_markdown, "metadata": metadata}
            )
        result_blocks.append(updated)

    if FORMULA_UNAVAILABLE_MARKER in markdown:
        occurrences = markdown.count(FORMULA_UNAVAILABLE_MARKER)
        markdown = markdown.replace(FORMULA_UNAVAILABLE_MARKER, FORMULA_PLACEHOLDER)
        placeholder_count = max(placeholder_count, occurrences)
        incomplete_count = max(incomplete_count, occurrences)
        warnings.append(f"{parser_label}: Markdown 中有 {occurrences} 个公式未解析，已保留占位符。")

    return FormulaNormalizationResult(
        blocks=result_blocks,
        markdown=markdown,
        warnings=warnings,
        recovered_count=recovered_count,
        incomplete_count=incomplete_count,
        placeholder_count=placeholder_count,
    )
