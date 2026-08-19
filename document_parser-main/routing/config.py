"""路由层配置。

配置可以由调用方显式传入，也可以从环境变量读取。敏感的 MinerU Token 只用于
能力可用性判断，不会写入 ``RoutingDecision``。
"""

from __future__ import annotations

import os
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, SecretStr


class RouteProfile(StrEnum):
    """当前冻结的两套路由策略。"""

    LOCAL_FIRST = "local_first"
    QUALITY_FIRST = "quality_first"


class RoutingSettings(BaseModel):
    """构造路由器所需的环境和策略配置。"""

    profile: RouteProfile = RouteProfile.LOCAL_FIRST
    allow_cloud: bool = True
    libreoffice_available: bool = False
    mineru_api_token: SecretStr | None = Field(default=None, exclude=True, repr=False)
    mineru_api_base_url: str = "https://mineru.net/api/v4"
    docling_executable: str | None = None
    anydoc_executable: str | None = None

    @classmethod
    def from_environment(cls, **overrides: Any) -> "RoutingSettings":
        """从环境变量加载配置，显式参数优先。"""

        values: dict[str, Any] = {
            "profile": os.getenv(
                "DOCUMENT_PARSER_ROUTE_PROFILE", RouteProfile.LOCAL_FIRST.value
            ),
            "allow_cloud": _environment_bool(
                "DOCUMENT_PARSER_ALLOW_CLOUD", default=True
            ),
            "libreoffice_available": _environment_bool(
                "DOCUMENT_PARSER_LIBREOFFICE_AVAILABLE", default=False
            ),
            "mineru_api_token": os.getenv("MINERU_API_TOKEN") or None,
            "mineru_api_base_url": os.getenv(
                "MINERU_API_BASE_URL", "https://mineru.net/api/v4"
            ),
            "docling_executable": os.getenv("DOCLING_EXECUTABLE") or None,
            "anydoc_executable": os.getenv("ANYDOC_EXECUTABLE") or None,
        }
        values.update(overrides)
        return cls.model_validate(values)


def _environment_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"环境变量 {name} 必须是 true/false、1/0、yes/no 或 on/off。")
