"""把解析器输出的 Markdown 转换为统一文档块的内部工具。

本文件不是解析器，不声明 ``ParserCapability``，也不会被网关注册。MarkItDown
输出 Markdown 后调用这里获得标题、段落与章节路径。

维护边界：这里只处理两个解析器共同需要的基础切块。它不是完整 CommonMark
实现；如果以后需要代码块、嵌套列表或原生表格语义，应扩展统一块构建能力，
不要把内部工具注册为独立解析器。
"""

from ...core.contracts import (
    BlockKind,
    DocumentBlock,
    SourceAnchor,
)


def blocks_from_markdown(text: str) -> list[DocumentBlock]:
    """把 Markdown 标题和段落切分为统一块，供 MarkItDown 解析器复用。

    切分规则刻意保持简单且稳定：
    - 空行结束当前段落；
    - 以 ``#`` 开头的非空行生成标题块；
    - 其余连续行合并成一个段落，保留内部换行；
    - 标题层级写入 ``section_path``，供检索结果回溯章节。
    """

    # 最终输出顺序必须与原文顺序一致，下游阅读顺序依赖这一不变量。
    blocks: list[DocumentBlock] = []
    # 当前标题栈，例如 ["第一章", "1.1 范围"]；新标题会按级别截断旧分支。
    section_path: list[str] = []
    # 暂存连续的非标题行，遇到空行、标题或 EOF 时一次性写入段落块。
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        """把当前累计的连续文本写入一个段落块。"""

        if not paragraph_lines:
            return
        # 先计算一次，避免 markdown 与 original_text 因未来修改出现差异。
        paragraph = "\n".join(paragraph_lines).strip()
        blocks.append(
            DocumentBlock(
                kind=BlockKind.PARAGRAPH,
                markdown=paragraph,
                anchor=SourceAnchor(
                    section_path=section_path.copy(),
                    original_text=paragraph,
                ),
            )
        )
        # clear() 保留列表对象，供闭包后续继续累计下一段。
        paragraph_lines.clear()

    for raw_line in text.splitlines():
        # 当前基线忽略行首/尾空白；若未来要保留代码块缩进，不能直接修改这里，
        # 应先引入真正的 Markdown 语法解析器。
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue
        if line.startswith("#"):
            flush_paragraph()
            # 连续 # 数量决定标题级别；section_path 仅保存层级，不保存 #。
            level = len(line) - len(line.lstrip("#"))
            title = line[level:].strip()
            # 同级标题替换当前层，低级标题保留父级，高级标题截断子级。
            section_path[:] = section_path[: max(0, level - 1)]
            section_path.append(title)
            blocks.append(
                DocumentBlock(
                    kind=BlockKind.HEADING,
                    markdown=line,
                    anchor=SourceAnchor(
                        section_path=section_path.copy(),
                        original_text=title,
                    ),
                )
            )
        else:
            paragraph_lines.append(line)
    # 文件末尾通常没有空行，必须显式提交最后一个段落。
    flush_paragraph()

    return blocks
