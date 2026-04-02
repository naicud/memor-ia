"""Business Intelligence Memory — revenue signals, segmentation, lifecycle, and value scoring."""

from .lifecycle import LifecycleTracker
from .segmentation import SegmentClassifier
from .signals import RevenueSignals
from .types import (
    LifecyclePosition,
    LifecycleStage,
    RevenueSignal,
    RevenueSignalType,
    SegmentType,
    UserSegment,
    ValueScore,
    ValueTier,
)
from .value import ValueScorer

__all__ = [
    # Classes
    "RevenueSignals",
    "SegmentClassifier",
    "LifecycleTracker",
    "ValueScorer",
    # Types
    "RevenueSignalType",
    "SegmentType",
    "LifecycleStage",
    "ValueTier",
    "RevenueSignal",
    "UserSegment",
    "LifecyclePosition",
    "ValueScore",
]
