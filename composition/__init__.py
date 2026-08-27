"""Application composition adapters and production wiring boundaries."""

from .gateway import DocumentParserGateway, GatewayParseError, GatewayParseResult
from .reparse_recommendations import (
    recommend_reparse_for_job,
    reparse_context_for_job,
    reparse_signals_for_job,
)

__all__ = [
    "DocumentParserGateway",
    "GatewayParseError",
    "GatewayParseResult",
    "recommend_reparse_for_job",
    "reparse_context_for_job",
    "reparse_signals_for_job",
]
