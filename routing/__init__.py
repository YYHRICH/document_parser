"""Routing utilities."""

from .config import RouteProfile, RoutingSettings
from .errors import (
    CloudParserForbiddenError,
    InvalidRoutingOptionError,
    ParserUnavailableError,
    ReparseRejectedError,
    RoutingError,
    UnsupportedFormatError,
    UnknownParserError,
)
from .identifiers import ANYDOC_ID, DOCLING_ID, MARKITDOWN_ID, MINERU_ID, OCR_ID
from .registry import CapabilityRegistry
from .policy import cloud_parser_forbidden_reason, resolve_cloud_permission
from .recommendations import (
    AutomaticReparseOption,
    ReparseCandidate,
    ReparseContext,
    ReparseRecommendationPolicy,
    ReparseRecommendations,
    ReparseSignal,
    ReparseSignalSource,
    recommend_reparse,
)
from .router import ModelRouter

__all__ = [
    "ANYDOC_ID",
    "AutomaticReparseOption",
    "CloudParserForbiddenError",
    "CapabilityRegistry",
    "DOCLING_ID",
    "InvalidRoutingOptionError",
    "MARKITDOWN_ID",
    "MINERU_ID",
    "ModelRouter",
    "OCR_ID",
    "ParserUnavailableError",
    "ReparseCandidate",
    "ReparseContext",
    "ReparseRecommendationPolicy",
    "ReparseRecommendations",
    "ReparseRejectedError",
    "ReparseSignal",
    "ReparseSignalSource",
    "RouteProfile",
    "RoutingError",
    "RoutingSettings",
    "UnsupportedFormatError",
    "cloud_parser_forbidden_reason",
    "resolve_cloud_permission",
    "recommend_reparse",
    "UnknownParserError",
]
