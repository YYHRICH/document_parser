"""Standalone public boundary for native-result normalization.

This module depends only on the stable document contracts and the normalization
bundle.  It deliberately does not know about Gateway, routing implementations,
quality rules, storage, or any concrete parser adapter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from ..core.contracts import (
    DocumentSignals,
    ParseRequest,
    ParsedDocument,
    ParserNativeResult,
    RoutingDecision,
)
from .bundle import ParserNormalizationBundle


class NormalizationContext(BaseModel):
    """Stable, in-memory context supplied to a native-result normalizer.

    The context carries only contract data.  It intentionally contains no
    Gateway instance, filesystem path, parser implementation, quality config,
    or route policy.  A caller importing offline native artifacts can build it
    directly from ``ParserNativeResult`` without recreating the original
    ``ParseRequest``.
    """

    model_config = ConfigDict(frozen=True)

    signals: DocumentSignals
    requested_parser_id: str | None = None
    parser_options: dict[str, Any] = Field(default_factory=dict)
    routing_decision: RoutingDecision | None = None

    @classmethod
    def from_parse_request(
        cls,
        request: ParseRequest,
        signals: DocumentSignals,
    ) -> "NormalizationContext":
        """Adapt the legacy adapter inputs to the standalone context."""

        return cls(
            signals=signals,
            requested_parser_id=request.parser_id,
            parser_options=dict(request.options),
            routing_decision=_routing_decision_from_options(request.options),
        )

    @classmethod
    def for_native_result(
        cls,
        native_result: ParserNativeResult,
    ) -> "NormalizationContext":
        """Create the minimum context needed for an offline native fixture."""

        extension = Path(native_result.filename).suffix.lower() or ".bin"
        return cls(
            signals=DocumentSignals(
                extension=extension,
                size_bytes=native_result.source_size_bytes or 0,
            ),
            parser_options=dict(native_result.options),
        )


@runtime_checkable
class NativeResultNormalizer(Protocol):
    """Port implemented by an adapter-specific native-result normalizer."""

    def normalize_native(
        self,
        native_result: ParserNativeResult,
        context: NormalizationContext,
    ) -> ParserNormalizationBundle:
        """Map one parser-native result to the parser-agnostic evidence bundle."""


class NormalizationFacade:
    """Injectable standalone entry point from native result to common output."""

    def __init__(self, normalizer: NativeResultNormalizer) -> None:
        if not isinstance(normalizer, NativeResultNormalizer):
            raise TypeError(
                "normalizer must implement normalize_native(native_result, context)."
            )
        self._normalizer = normalizer

    def normalize(
        self,
        native_result: ParserNativeResult,
        context: NormalizationContext | None = None,
    ) -> ParserNormalizationBundle:
        """Return the full bundle, including package-only native sidecars."""

        resolved_context = context or NormalizationContext.for_native_result(
            native_result
        )
        bundle = self._normalizer.normalize_native(native_result, resolved_context)
        if not isinstance(bundle, ParserNormalizationBundle):
            raise TypeError(
                "normalize_native must return ParserNormalizationBundle, "
                f"got {type(bundle).__name__}."
            )
        return bundle

    def normalize_document(
        self,
        native_result: ParserNativeResult,
        context: NormalizationContext | None = None,
    ) -> ParsedDocument:
        """Return only the stable document protocol for in-memory consumers."""

        return self.normalize(native_result, context).to_parsed_document()


def normalize_native_result(
    native_result: ParserNativeResult,
    *,
    normalizer: NativeResultNormalizer,
    context: NormalizationContext | None = None,
) -> ParserNormalizationBundle:
    """Convenience function for offline native-result to bundle conversion."""

    return NormalizationFacade(normalizer).normalize(native_result, context)


def normalize_to_parsed_document(
    native_result: ParserNativeResult,
    *,
    normalizer: NativeResultNormalizer,
    context: NormalizationContext | None = None,
) -> ParsedDocument:
    """Convenience function for offline native-result to document conversion."""

    return NormalizationFacade(normalizer).normalize_document(native_result, context)


def _routing_decision_from_options(
    options: dict[str, Any],
) -> RoutingDecision | None:
    """Read the optional contract object without importing a routing module."""

    value = options.get("_routing_decision")
    if isinstance(value, RoutingDecision):
        return value
    if isinstance(value, dict):
        return RoutingDecision.model_validate(value)
    return None
