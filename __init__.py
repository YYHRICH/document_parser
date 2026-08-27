"""Parser-agnostic public contracts and lazy composition conveniences."""

from .core.contracts import (
    AppliedRepair,
    AssetKind,
    BlockKind,
    CanonicalBlock,
    CanonicalDocument,
    CanonicalRelation,
    CanonicalSourceLocator,
    CapabilityAssessment,
    DocumentAsset,
    DocumentBlock,
    DocumentSignals,
    EvidenceAvailability,
    EvidenceCapability,
    FallbackAttempt,
    GateSummary,
    IssueSeverity,
    IssueStatus,
    NativeArtifact,
    OcrSpan,
    PackageManifest,
    ParseConfidence,
    ParsedDocument,
    ParsedTable,
    ParseRequest,
    ParserNativeResult,
    ParserCapability,
    ParserProvenance,
    QualityCapabilityState,
    QualityIssue,
    QualityPackage,
    QualityReport,
    QualityState,
    ReparseRecommendation,
    RoutingDecision,
    RoutingMode,
    SourceAnchor,
    TableCell,
    TableFieldBinding,
)
from importlib import import_module
from typing import Any

# Gateway and routing are composition-layer conveniences.  Keeping them lazy means
# importing the shared contracts, normalizer, or quality library does not initialize
# parser registries, cloud configuration, or the web/backend stack.
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "DocumentParserGateway": (".composition.gateway", "DocumentParserGateway"),
    "ModelRouter": (".routing", "ModelRouter"),
    "RouteProfile": (".routing", "RouteProfile"),
    "RoutingSettings": (".routing", "RoutingSettings"),
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

__all__ = [
    "AppliedRepair",
    "AssetKind",
    "BlockKind",
    "CanonicalBlock",
    "CanonicalDocument",
    "CanonicalRelation",
    "CanonicalSourceLocator",
    "CapabilityAssessment",
    "DocumentAsset",
    "DocumentBlock",
    "DocumentParserGateway",
    "DocumentSignals",
    "EvidenceAvailability",
    "EvidenceCapability",
    "FallbackAttempt",
    "GateSummary",
    "IssueSeverity",
    "IssueStatus",
    "ModelRouter",
    "NativeArtifact",
    "OcrSpan",
    "PackageManifest",
    "ParseConfidence",
    "ParsedDocument",
    "ParsedTable",
    "ParseRequest",
    "ParserNativeResult",
    "ParserCapability",
    "ParserProvenance",
    "QualityCapabilityState",
    "QualityIssue",
    "QualityPackage",
    "QualityReport",
    "QualityState",
    "ReparseRecommendation",
    "RouteProfile",
    "RoutingDecision",
    "RoutingMode",
    "RoutingSettings",
    "SourceAnchor",
    "TableCell",
    "TableFieldBinding",
]
