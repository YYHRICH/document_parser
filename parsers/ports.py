"""Stable ports for parser plugins.

This module deliberately depends only on the public document contracts.  It does
not import a concrete parser, routing, Gateway, quality, storage, or backend.
A composition root can therefore probe plugins, inject a capability snapshot
into routing, and execute/normalize a plugin without coupling those layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from ..core.contracts import DocumentSignals, ParseRequest, ParserCapability, ParserNativeResult

if TYPE_CHECKING:
    from ..normalizers import NormalizationContext, ParserNormalizationBundle


class ParserFailureKind(str, Enum):
    """Portable failure categories understood by fallback and orchestration."""

    TRANSIENT = "transient"
    POLICY = "policy"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"
    NORMALIZATION = "normalization"
    PARSER = "parser"


_FAILURE_KINDS = frozenset(item.value for item in ParserFailureKind)


def normalize_failure_kind(value: ParserFailureKind | Enum | str) -> str:
    """Return a stable wire value while accepting either the enum or a string.

    ``failure_kind`` is intentionally stored as a plain string on the exception:
    existing persistence and orchestration code can consume it without importing
    this parser-plugin module.
    """

    candidate = value.value if isinstance(value, Enum) else str(value)
    normalized = candidate.strip().lower()
    if normalized not in _FAILURE_KINDS:
        allowed = ", ".join(sorted(_FAILURE_KINDS))
        raise ValueError(f"Unknown parser failure kind {candidate!r}; expected one of: {allowed}.")
    return normalized


class ParserBoundaryError(ValueError):
    """Expected policy/configuration rejection that must retain its public type.

    This is intentionally separate from ``ParserExecutionError``: a caller
    attempted an invalid or forbidden operation, so it must not be silently
    converted into an execution failure or trigger a fallback parser.
    """


class ParserExecutionError(RuntimeError):
    """A safe, typed error emitted by a parser execution boundary.

    ``safe_message`` is the only message appropriate for an API response,
    provenance record, or job state.  Callers should retain the underlying
    exception through normal exception chaining for private logs rather than
    embedding raw command output, credentials, or service responses here.
    """

    def __init__(
        self,
        *,
        parser_id: str,
        failure_kind: ParserFailureKind | Enum | str = ParserFailureKind.PARSER,
        retryable: bool = False,
        safe_message: str,
    ) -> None:
        normalized_parser_id = str(parser_id).strip()
        normalized_message = " ".join(str(safe_message).split())
        if not normalized_parser_id:
            raise ValueError("ParserExecutionError requires parser_id.")
        if not normalized_message:
            raise ValueError("ParserExecutionError requires safe_message.")
        self.parser_id = normalized_parser_id
        self.failure_kind = normalize_failure_kind(failure_kind)
        self.retryable = bool(retryable)
        self.safe_message = normalized_message
        super().__init__(normalized_message)


def diagnose_parser_exception(
    error: Exception,
    *,
    parser_id: str,
    display_name: str,
) -> ParserExecutionError:
    """Map an unexpected backend exception to the portable safe error contract.

    This helper deliberately retains no raw exception text in its output.  A
    caller that needs private diagnostics must use normal exception chaining.
    Concrete adapters can still override the classification when their backend
    exposes a reliable, non-sensitive status code.
    """

    if isinstance(error, ParserExecutionError):
        return error

    detail = f"{type(error).__name__} {error}".lower()
    if isinstance(error, TimeoutError) or any(
        token in detail
        for token in ("timeout", "timed out", "temporar", "connection", "rate limit")
    ):
        return ParserExecutionError(
            parser_id=parser_id,
            failure_kind=ParserFailureKind.TRANSIENT,
            retryable=True,
            safe_message=f"{display_name} execution failed temporarily; retry may succeed.",
        )
    if isinstance(error, (ImportError, ModuleNotFoundError, FileNotFoundError)) or any(
        token in detail
        for token in ("not installed", "no module named", "executable not found", "backend unavailable")
    ):
        return ParserExecutionError(
            parser_id=parser_id,
            failure_kind=ParserFailureKind.UNAVAILABLE,
            safe_message=f"{display_name} backend is unavailable in this environment.",
        )
    if isinstance(error, PermissionError) or any(
        token in detail
        for token in ("forbidden", "policy", "untrusted", "not allowed", "permission denied")
    ):
        return ParserExecutionError(
            parser_id=parser_id,
            failure_kind=ParserFailureKind.POLICY,
            safe_message=f"{display_name} execution was rejected by policy.",
        )
    if any(token in detail for token in ("unsupported", "not support")):
        return ParserExecutionError(
            parser_id=parser_id,
            failure_kind=ParserFailureKind.UNSUPPORTED,
            safe_message=f"{display_name} does not support this input.",
        )
    if any(
        token in detail
        for token in ("normaliz", "schema", "contract", "jsondecode", "json decode", "invalid json")
    ):
        return ParserExecutionError(
            parser_id=parser_id,
            failure_kind=ParserFailureKind.NORMALIZATION,
            safe_message=f"{display_name} returned an invalid native result.",
        )
    return ParserExecutionError(
        parser_id=parser_id,
        failure_kind=ParserFailureKind.PARSER,
        safe_message=f"{display_name} execution failed.",
    )


@dataclass(frozen=True)
class ParserProbeResult:
    """A request-safe plugin probe result used to create a routing snapshot."""

    capability: ParserCapability
    supported: bool
    executable: bool
    reason: str | None = None

    @property
    def parser_id(self) -> str:
        """Expose the stable ID without leaking a concrete parser instance."""

        return self.capability.parser_id


@runtime_checkable
class ParserProbePort(Protocol):
    """Probe a plugin's format support and current runtime availability."""

    def probe(
        self,
        request: ParseRequest | None = None,
        signals: DocumentSignals | None = None,
    ) -> ParserProbeResult:
        """Return capability metadata and optional request-specific readiness."""


@runtime_checkable
class ParserExecutePort(Protocol):
    """Execute one plugin and return only parser-native evidence."""

    def execute(
        self,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> ParserNativeResult:
        """Run the native backend without producing quality conclusions."""


@runtime_checkable
class ParserNormalizePort(Protocol):
    """Normalize native evidence to the common document evidence bundle."""

    def normalize_native(
        self,
        native_result: ParserNativeResult,
        context: "NormalizationContext",
    ) -> "ParserNormalizationBundle":
        """Translate a native result through the standalone normalization API."""


@runtime_checkable
class ParserDiagnosePort(Protocol):
    """Convert backend failures to the safe platform error contract."""

    def diagnose(
        self,
        error: Exception,
        *,
        request: ParseRequest | None = None,
        signals: DocumentSignals | None = None,
    ) -> ParserExecutionError:
        """Return a typed error while callers retain the original cause privately."""


@runtime_checkable
class ParserPluginPort(
    ParserProbePort,
    ParserExecutePort,
    ParserNormalizePort,
    ParserDiagnosePort,
    Protocol,
):
    """The complete minimal parser plugin surface."""


__all__ = [
    "ParserBoundaryError",
    "ParserDiagnosePort",
    "ParserExecutePort",
    "ParserExecutionError",
    "ParserFailureKind",
    "ParserNormalizePort",
    "ParserPluginPort",
    "ParserProbePort",
    "ParserProbeResult",
    "diagnose_parser_exception",
    "normalize_failure_kind",
]
