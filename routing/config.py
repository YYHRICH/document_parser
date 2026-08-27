"""Routing settings owned by the server-side routing policy."""

from __future__ import annotations

import os
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

from ..common.url_security import (
    TrustedUrlError,
    normalize_trusted_hosts,
    validate_trusted_https_url,
)


DEFAULT_MINERU_API_BASE_URL = "https://mineru.net/api/v4"
DEFAULT_MINERU_TRUSTED_HOSTS = ("mineru.net",)


class RouteProfile(StrEnum):
    LOCAL_FIRST = "local_first"
    QUALITY_FIRST = "quality_first"


class RoutingSettings(BaseModel):
    """Server-owned knobs that constrain routing decisions.

    ``mineru_api_*`` values are retained for compatibility with existing deployment
    configuration, but they are never copied into a request or routing decision.
    The MinerU executor independently resolves the same server-side settings before
    it opens a network connection.
    """

    profile: RouteProfile = RouteProfile.LOCAL_FIRST
    allow_cloud: bool = False
    libreoffice_available: bool = False
    mineru_api_token: SecretStr | None = Field(default=None, exclude=True, repr=False)
    mineru_api_base_url: str = DEFAULT_MINERU_API_BASE_URL
    mineru_trusted_hosts: tuple[str, ...] = DEFAULT_MINERU_TRUSTED_HOSTS
    docling_executable: str | None = None
    anydoc_executable: str | None = None

    @field_validator("mineru_trusted_hosts", mode="before")
    @classmethod
    def normalize_mineru_trusted_hosts(cls, value: Any) -> tuple[str, ...]:
        if isinstance(value, str):
            value = _environment_csv_value(value)
        try:
            return tuple(sorted(normalize_trusted_hosts(value)))
        except (TypeError, TrustedUrlError) as error:
            raise ValueError(f"Invalid MinerU trusted host policy: {error}") from error

    @model_validator(mode="after")
    def validate_mineru_api_base_url(self) -> "RoutingSettings":
        try:
            self.mineru_api_base_url = validate_trusted_https_url(
                self.mineru_api_base_url,
                trusted_hosts=self.mineru_trusted_hosts,
                allow_query=False,
            ).rstrip("/")
        except TrustedUrlError as error:
            raise ValueError(f"Invalid MinerU API base URL: {error}") from error
        return self

    @classmethod
    def from_environment(cls, **overrides: Any) -> "RoutingSettings":
        values: dict[str, Any] = {
            "profile": os.getenv("DOCUMENT_PARSER_ROUTE_PROFILE", RouteProfile.LOCAL_FIRST.value),
            "allow_cloud": _environment_bool("DOCUMENT_PARSER_ALLOW_CLOUD", default=False),
            "libreoffice_available": _environment_bool(
                "DOCUMENT_PARSER_LIBREOFFICE_AVAILABLE", default=False
            ),
            "mineru_api_token": os.getenv("MINERU_API_TOKEN") or None,
            "mineru_api_base_url": os.getenv("MINERU_API_BASE_URL", DEFAULT_MINERU_API_BASE_URL),
            "mineru_trusted_hosts": _environment_csv(
                "MINERU_API_TRUSTED_HOSTS", DEFAULT_MINERU_TRUSTED_HOSTS
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
    raise ValueError(f"Environment variable {name} must be true/false or 1/0.")


def _environment_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    return _environment_csv_value(value) if value is not None else default


def _environment_csv_value(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())
