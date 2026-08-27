"""Server-owned MinerU cloud configuration and outbound URL policy."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from ..ports import ParserBoundaryError

from ...common.url_security import (
    TrustedUrlError,
    normalize_trusted_hosts,
    resolve_trusted_redirect_url,
    validate_trusted_https_url,
)


DEFAULT_MINERU_API_BASE_URL = "https://mineru.net/api/v4"
DEFAULT_MINERU_TRUSTED_HOSTS = ("mineru.net",)
DEFAULT_TASK_TIMEOUT_SECONDS = 900.0
DEFAULT_DOWNLOAD_TIMEOUT_SECONDS = 600.0
DEFAULT_MAX_REDIRECTS = 3

# These options can affect credential use or cause the service to make an outbound
# request to a caller-controlled destination.  They are never valid request inputs.
SENSITIVE_REQUEST_OPTION_KEYS = frozenset(
    {
        "api_base_url",
        "api_token",
        "authorization",
        "bearer_token",
        "mineru_api_base_url",
        "mineru_api_token",
        "mineru_server_url",
        "server_url",
        "native_output_dir",
    }
)


class MinerUSecurityError(ParserBoundaryError):
    """Base class for rejected MinerU security boundaries."""


class MinerUConfigurationError(MinerUSecurityError):
    """Raised when server-owned MinerU configuration is unsafe or invalid."""


class MinerURequestOptionError(MinerUSecurityError):
    """Raised when an untrusted request attempts to override service configuration."""


class MinerUUntrustedUrlError(MinerUSecurityError):
    """Raised before an outbound URL fails the configured trust policy."""


@dataclass(frozen=True)
class MinerUServiceConfig:
    """Configuration resolved exclusively from the server environment."""

    api_base_url: str
    trusted_hosts: frozenset[str]
    api_token: str | None
    allow_cloud: bool
    task_timeout_seconds: float
    download_timeout_seconds: float
    max_redirects: int

    @classmethod
    def from_environment(cls) -> "MinerUServiceConfig":
        try:
            trusted_hosts = normalize_trusted_hosts(
                _environment_csv("MINERU_API_TRUSTED_HOSTS", DEFAULT_MINERU_TRUSTED_HOSTS)
            )
            api_base_url = validate_trusted_https_url(
                os.getenv("MINERU_API_BASE_URL", DEFAULT_MINERU_API_BASE_URL),
                trusted_hosts=trusted_hosts,
                allow_query=False,
            ).rstrip("/")
        except TrustedUrlError as error:
            raise MinerUConfigurationError(f"Invalid MinerU endpoint policy: {error}") from error

        token = _nonempty_environment("MINERU_API_TOKEN")
        return cls(
            api_base_url=api_base_url,
            trusted_hosts=trusted_hosts,
            api_token=token,
            allow_cloud=_environment_bool("DOCUMENT_PARSER_ALLOW_CLOUD", default=False),
            task_timeout_seconds=_environment_positive_float(
                "MINERU_TASK_TIMEOUT_SECONDS",
                default=DEFAULT_TASK_TIMEOUT_SECONDS,
                maximum=3600.0,
            ),
            download_timeout_seconds=_environment_positive_float(
                "MINERU_DOWNLOAD_TIMEOUT_SECONDS",
                default=DEFAULT_DOWNLOAD_TIMEOUT_SECONDS,
                maximum=1800.0,
            ),
            max_redirects=_environment_positive_int(
                "MINERU_MAX_REDIRECTS",
                default=DEFAULT_MAX_REDIRECTS,
                maximum=10,
            ),
        )

    def validate_callback_url(self, value: str, *, kind: str) -> str:
        try:
            return validate_trusted_https_url(
                value,
                trusted_hosts=self.trusted_hosts,
            )
        except TrustedUrlError as error:
            raise MinerUUntrustedUrlError(f"Untrusted MinerU {kind} URL: {error}") from error

    def resolve_redirect_url(self, current_url: str, location: str) -> str:
        try:
            return resolve_trusted_redirect_url(
                current_url,
                location,
                trusted_hosts=self.trusted_hosts,
            )
        except TrustedUrlError as error:
            raise MinerUUntrustedUrlError(f"Untrusted MinerU redirect URL: {error}") from error


def reject_sensitive_request_options(options: dict[str, Any]) -> None:
    """Reject request-level values that would bypass server execution policy."""

    present = sorted(key for key in SENSITIVE_REQUEST_OPTION_KEYS if key in options)
    if present:
        raise MinerURequestOptionError(
            "MinerU request options cannot override server-managed settings: "
            + ", ".join(present)
        )


def _environment_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise MinerUConfigurationError(
        f"Environment variable {name} must be true/false or 1/0."
    )


def _environment_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if value is None:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _nonempty_environment(name: str) -> str | None:
    value = os.getenv(name)
    if not value:
        return None
    normalized = value.strip()
    return normalized or None


def _environment_positive_float(name: str, *, default: float, maximum: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError as error:
        raise MinerUConfigurationError(
            f"Environment variable {name} must be a positive number."
        ) from error
    if not 0 < parsed <= maximum:
        raise MinerUConfigurationError(
            f"Environment variable {name} must be between 0 and {maximum}."
        )
    return parsed


def _environment_positive_int(name: str, *, default: int, maximum: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as error:
        raise MinerUConfigurationError(
            f"Environment variable {name} must be a positive integer."
        ) from error
    if not 0 < parsed <= maximum:
        raise MinerUConfigurationError(
            f"Environment variable {name} must be between 1 and {maximum}."
        )
    return parsed
