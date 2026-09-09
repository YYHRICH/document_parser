"""质量层配置（Gate 判定规则等）。

契约决策映射：
- D-08：info 不阻塞 pass，仅 warning 及以上未修复触发 pass_with_warnings；
- D-03：不适用能力不得成为 blocker（applicability 独立计算）；
- 质量 JSON 不保存产物哈希或清单。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GateConfig:
    """质量门判定参数（决定"什么时候不得通过"的边界）。"""

    # D-08：未修复的 info issue 是否阻塞 pass
    info_blocks_pass: bool = False
    # D-03：状态为 unavailable 且能力不适用时，是否计入 blocker
    unavailable_blocks_when_applicable_only: bool = True
    # 未解决 warning issue 是否触发 pass_with_warnings
    warnings_trigger_pass_with_warnings: bool = True
    # 未解决 critical issue 的最低状态（reparse_required 或 rejected）
    critical_issue_min_state: str = "rejected"


@dataclass(frozen=True)
class QualityConfig:
    """质量层整体配置。"""

    gate: GateConfig = field(default_factory=GateConfig)
    # 稳定 ID 命名空间校验开关
    enforce_stable_ids: bool = True
