"""Routing-layer errors."""

from __future__ import annotations


class RoutingError(ValueError):
    """Base error for routing failures."""


class UnknownParserError(RoutingError):
    """Raised when a parser ID is not registered."""


class ParserUnavailableError(RoutingError):
    """Raised when a candidate parser cannot be used."""


class CloudParserForbiddenError(RoutingError):
    """Raised when cloud parsing is blocked by settings."""


class UnsupportedFormatError(RoutingError):
    """Raised when the requested parser cannot handle the file type."""


class ReparseRejectedError(RoutingError):
    """Raised when a reparse recommendation would repeat an attempt."""
