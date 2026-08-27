"""Public parser-plugin boundary.

Concrete adapters stay lazy so importing a port, a typed execution error, or a
capability snapshot does not initialize third-party parser SDKs.  The registry
is the explicit composition-root entry point that constructs built-in plugins.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "AnyDocParser": (".anydoc", "AnyDocParser"),
    "DoclingParser": (".docling", "DoclingParser"),
    "MarkItDownParser": (".markitdown", "MarkItDownParser"),
    "MinerUParser": (".mineru", "MinerUParser"),
    "OcrParser": (".ocr", "OcrParser"),
    "ParserBoundaryError": (".ports", "ParserBoundaryError"),
    "ParserDiagnosePort": (".ports", "ParserDiagnosePort"),
    "ParserExecutePort": (".ports", "ParserExecutePort"),
    "ParserExecutionError": (".ports", "ParserExecutionError"),
    "ParserFailureKind": (".ports", "ParserFailureKind"),
    "ParserNormalizePort": (".ports", "ParserNormalizePort"),
    "ParserPluginPort": (".ports", "ParserPluginPort"),
    "ParserProbePort": (".ports", "ParserProbePort"),
    "ParserProbeResult": (".ports", "ParserProbeResult"),
    "ParserRegistry": (".registry", "ParserRegistry"),
    "build_capability_snapshot": (".registry", "build_capability_snapshot"),
    "build_parser_registry": (".registry", "build_parser_registry"),
    "get_parser": (".registry", "get_parser"),
    "iter_parser_capabilities": (".registry", "iter_parser_capabilities"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as error:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from error
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


__all__ = sorted(_LAZY_EXPORTS)
