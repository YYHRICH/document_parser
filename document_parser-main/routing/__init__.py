"""模型能力注册与自动/手动路由。"""

from .config import RouteProfile, RoutingSettings
from .errors import (
    CloudParserForbiddenError,
    ParserUnavailableError,
    ReparseRejectedError,
    RoutingError,
    UnknownParserError,
    UnsupportedFormatError,
)
from .registry import (
    ANYDOC_ID,
    DOCLING_ID,
    MINERU_ID,
    PASSTHROUGH_ID,
    CapabilityRegistry,
)
from .router import ModelRouter

__all__ = [
    "ANYDOC_ID",
    "CapabilityRegistry",
    "CloudParserForbiddenError",
    "DOCLING_ID",
    "MINERU_ID",
    "ModelRouter",
    "PASSTHROUGH_ID",
    "ParserUnavailableError",
    "ReparseRejectedError",
    "RouteProfile",
    "RoutingError",
    "RoutingSettings",
    "UnknownParserError",
    "UnsupportedFormatError",
]
