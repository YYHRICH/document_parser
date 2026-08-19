"""Routing settings."""

from __future__ import annotations

import os
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, SecretStr


class RouteProfile(StrEnum):
    LOCAL_FIRST = "local_first"
    QUALITY_FIRST = "quality_first"


class RoutingSettings(BaseModel):
    profile: RouteProfile = RouteProfile.LOCAL_FIRST
    allow_cloud: bool = True
    libreoffice_available: bool = False
    mineru_api_token: SecretStr | None = Field(default=None, exclude=True, repr=False)
    mineru_api_base_url: str = "https://mineru.net/api/v4"
    docling_executable: str | None = None
    anydoc_executable: str | None = None

    @classmethod
    def from_environment(cls, **overrides: Any) -> "RoutingSettings":
        values: dict[str, Any] = {
            "profile": os.getenv("DOCUMENT_PARSER_ROUTE_PROFILE", RouteProfile.LOCAL_FIRST.value),
            "allow_cloud": _environment_bool("DOCUMENT_PARSER_ALLOW_CLOUD", default=True),
            "libreoffice_available": _environment_bool(
                "DOCUMENT_PARSER_LIBREOFFICE_AVAILABLE", default=False
            ),
            "mineru_api_token": os.getenv("MINERU_API_TOKEN") or None,
            "mineru_api_base_url": os.getenv("MINERU_API_BASE_URL", "https://mineru.net/api/v4"),
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
    raise ValueError(f"Environment variable {name} must be true/false or 1/0.")
