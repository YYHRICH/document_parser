"""给单文档 Agent 的分层只读上下文。"""

from __future__ import annotations

from dataclasses import dataclass

from quality.agent.index import DocumentIndex
from quality.agent.models import CandidateValidation
from quality.agent.prompts import render_repair_prompt
from quality.agent.revision import DocumentRevision


@dataclass(frozen=True)
class DocumentAgentContext:
    """一次 Agent run 使用的摘要和局部文档上下文。"""

    revision_id: str
    document_id: str
    filename: str
    markdown: str
    block_summaries: tuple[str, ...]
    feedback: CandidateValidation | None = None
    max_context_chars: int = 12000
    document_index: DocumentIndex | None = None
    focus_page: int | None = None

    def to_prompt(self, max_chars: int | None = None) -> str:
        """通过集中式 Prompt 模板生成给 Agno 的用户输入。"""

        return render_repair_prompt(
            revision_id=self.revision_id,
            document_id=self.document_id,
            filename=self.filename,
            markdown=self.markdown,
            block_summaries=self.block_summaries,
            feedback=self.feedback,
            focus_page=self.focus_page,
            document_index=(
                self.document_index.to_prompt(max_chars=5000)
                if self.document_index is not None
                else ""
            ),
            max_chars=max_chars or self.max_context_chars,
        )



class DocumentContextBuilder:
    """从 revision 生成有限大小的上下文。"""

    def __init__(self, *, max_blocks: int = 80, block_chars: int = 500) -> None:
        self.max_blocks = max_blocks
        self.block_chars = block_chars

    def build(
        self,
        revision: DocumentRevision,
        feedback: CandidateValidation | None = None,
        max_context_chars: int = 12000,
    ) -> DocumentAgentContext:
        document_index = DocumentIndex.from_document(revision.document)
        summaries = tuple(
            f"{block.id} | {block.kind.value} | {block.markdown[:self.block_chars]}"
            for block in revision.document.blocks[: self.max_blocks]
        )
        return DocumentAgentContext(
            revision_id=revision.revision_id,
            document_id=str(revision.document.document_id),
            filename=revision.document.filename,
            markdown=revision.document.markdown,
            block_summaries=summaries,
            feedback=feedback,
            max_context_chars=max_context_chars,
            document_index=document_index,
        )

    def build_page(
        self,
        revision: DocumentRevision,
        page_number: int,
        feedback: CandidateValidation | None = None,
        max_context_chars: int = 12000,
    ) -> DocumentAgentContext:
        """只构建一个页面的上下文，索引仍保留为全篇结构地图。"""

        document_index = DocumentIndex.from_document(revision.document)
        entry = document_index.page(page_number)
        block_ids = set(entry.block_ids if entry is not None else ())
        blocks = [
            block for block in revision.document.blocks if str(block.id) in block_ids
        ]
        summaries = tuple(
            f"{block.id} | {block.kind.value} | {block.markdown[:self.block_chars]}"
            for block in blocks
        )
        page_markdown = "\n\n".join(block.markdown for block in blocks)
        return DocumentAgentContext(
            revision_id=revision.revision_id,
            document_id=str(revision.document.document_id),
            filename=revision.document.filename,
            markdown=page_markdown,
            block_summaries=summaries,
            feedback=feedback,
            max_context_chars=max_context_chars,
            document_index=document_index,
            focus_page=page_number,
        )
