"""规则基类：所有质量规则的统一接口。

规则职责边界（spec §4.2）：
- 只读 EvidenceContext，产出 RuleResult；
- 不得直接修改文档、写文件、指定最终 Gate、调用解析器或路由器。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from quality.evidence.requirements import EvidenceRequirement
from quality.models_internal import RuleResult


class QualityRule(ABC):
    """质量规则协议。

    实现类必须：
    - 声明类属性 ``rule_id``（稳定，进入 golden/applied_repairs 后不可改名）；
    - 声明 ``required_evidence``；
    - 实现 ``execute(context) -> RuleResult``。
    """

    rule_id: str = ""
    required_evidence: tuple[EvidenceRequirement, ...] = ()

    @abstractmethod
    def execute(self, context: object) -> RuleResult:
        """在给定证据上下文上执行规则，返回 RuleResult。"""
        raise NotImplementedError
