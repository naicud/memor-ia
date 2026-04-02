"""MEMORIA Emotional Intelligence Layer.

Provides multi-signal emotion analysis, emotional arc tracking,
empathy-driven response generation, and fatigue/burnout detection.
"""

from .analyzer import EmotionAnalyzer
from .empathy import EmpathyEngine
from .fatigue import FatigueDetector
from .tracker import EmotionalArcTracker
from .types import (
    EmpathyAction,
    EmpathyTrigger,
    EmotionalArc,
    EmotionalProfile,
    EmotionReading,
    EmotionType,
    FatigueScore,
    IntensityLevel,
    SentimentScore,
    TrendDirection,
)

__all__ = [
    "EmotionAnalyzer",
    "EmpathyEngine",
    "FatigueDetector",
    "EmotionalArcTracker",
    "EmpathyAction",
    "EmpathyTrigger",
    "EmotionalArc",
    "EmotionalProfile",
    "EmotionReading",
    "EmotionType",
    "FatigueScore",
    "IntensityLevel",
    "SentimentScore",
    "TrendDirection",
]
