"""不调用真实模型的 Fake Agent，用于闭环测试。"""

from __future__ import annotations

from collections.abc import Iterable

from quality.agent.context import DocumentAgentContext
from quality.agent.models import CandidateValidation, RepairedDocumentCandidate


class FakeRepairAgent:
    """按顺序返回预先构造的候选；候选不足时重复最后一个。"""

    def __init__(self, candidates: Iterable[RepairedDocumentCandidate]) -> None:
        self._candidates = tuple(candidates)
        self.calls = 0

    def run(
        self,
        context: DocumentAgentContext,
        *,
        feedback: CandidateValidation | None = None,
    ) -> RepairedDocumentCandidate:
        if not self._candidates:
            raise RuntimeError("FakeRepairAgent 没有候选输出。")
        index = min(self.calls, len(self._candidates) - 1)
        self.calls += 1
        return self._candidates[index]
