"""Quality layer's only boundary to the shared data contract.

The public protocol remains owned by ``core/contracts.py``.  A standalone
quality import prefers the lightweight ``core.contracts`` module so it does not
initialize the application package (and therefore does not load Gateway,
routing, parser, backend, or web modules).  If the application contract was
already imported, its exact model identities are preserved.  Installed layouts
without a top-level ``core`` package retain a compatibility fallback.
"""

from __future__ import annotations

from importlib import import_module
import sys

_EXPORTS = (
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
    "EvidenceAvailability",
    "EvidenceCapability",
    "FallbackAttempt",
    "GateSummary",
    "IssueSeverity",
    "IssueStatus",
    "NativeArtifact",
    "OcrSpan",
    "PackageManifest",
    "ParseConfidence",
    "ParsedDocument",
    "ParsedTable",
    "ParserProvenance",
    "QualityCapabilityState",
    "QualityIssue",
    "QualityPackage",
    "QualityReport",
    "QualityState",
    "ReparseRecommendation",
    "SourceAnchor",
    "TableCell",
    "TableFieldBinding",
)

if "document_parser.core.contracts" in sys.modules:
    _contracts = sys.modules["document_parser.core.contracts"]
else:
    try:
        _contracts = import_module("core.contracts")
    except ModuleNotFoundError as error:
        if error.name not in {"core", "core.contracts"}:
            raise
        _contracts = import_module("document_parser.core.contracts")

# Source-tree standalone imports use ``core.contracts``.  Register its exact
# module under the application-qualified name before an application import can
# occur, preventing two incompatible Pydantic model class families later in
# the same process.  No application package is initialized by this alias.
if getattr(_contracts, "__name__", None) == "core.contracts":
    sys.modules.setdefault("document_parser.core.contracts", _contracts)

for _name in _EXPORTS:
    globals()[_name] = getattr(_contracts, _name)

del _name

__all__ = list(_EXPORTS)
