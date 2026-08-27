"""Quality-internal representation inventory and exact repair targets."""

from quality.representations.inventory import QualityInputAdapter, RepresentationInventory
from quality.representations.models import (
    RepresentationDescriptor,
    RepresentationFidelity,
    RepresentationKind,
    RepresentationTarget,
)
from quality.representations.tables import (
    TableRepresentationComparison,
    TableRepresentationResolver,
    TableResolution,
    TableResolutionDecision,
    parse_markdown_table,
)

__all__ = [
    "QualityInputAdapter",
    "RepresentationInventory",
    "RepresentationDescriptor",
    "RepresentationFidelity",
    "RepresentationKind",
    "RepresentationTarget",
    "TableRepresentationComparison",
    "TableRepresentationResolver",
    "TableResolution",
    "TableResolutionDecision",
    "parse_markdown_table",
]
