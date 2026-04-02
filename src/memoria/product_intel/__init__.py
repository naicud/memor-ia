"""Product Ecosystem Intelligence – traccia prodotti, profili d'uso, grafi e adozione."""

from .adoption import AdoptionAnalyzer
from .graph import ProductGraph
from .profiler import UsageProfiler
from .tracker import ProductTracker
from .types import (
    AdoptionCurve,
    AdoptionStage,
    FeatureStatus,
    ProductCategory,
    ProductInfo,
    ProductRelationship,
    ProductUsageEvent,
    UsageFrequency,
    UsageProfile,
)

__all__ = [
    "AdoptionAnalyzer",
    "AdoptionCurve",
    "AdoptionStage",
    "FeatureStatus",
    "ProductCategory",
    "ProductGraph",
    "ProductInfo",
    "ProductRelationship",
    "ProductTracker",
    "ProductUsageEvent",
    "UsageFrequency",
    "UsageProfile",
    "UsageProfiler",
]
