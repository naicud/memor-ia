"""Emotional Intelligence Layer — type definitions.

Defines the core data structures for multi-signal emotion analysis,
sentiment scoring, emotional arc tracking, empathy triggers, and
fatigue detection.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class EmotionType(Enum):
    """Twelve-emotion taxonomy for nuanced affective classification."""

    JOY = "joy"
    SATISFACTION = "satisfaction"
    EXCITEMENT = "excitement"
    CONFIDENCE = "confidence"
    FRUSTRATION = "frustration"
    ANGER = "anger"
    CONFUSION = "confusion"
    ANXIETY = "anxiety"
    BOREDOM = "boredom"
    FATIGUE = "fatigue"
    CURIOSITY = "curiosity"
    NEUTRAL = "neutral"


class IntensityLevel(Enum):
    """Five-tier intensity scale mapped to 0.0–1.0 float ranges."""

    MINIMAL = "minimal"    # 0.0–0.2
    MILD = "mild"          # 0.2–0.4
    MODERATE = "moderate"  # 0.4–0.6
    STRONG = "strong"      # 0.6–0.8
    INTENSE = "intense"    # 0.8–1.0


class EmpathyAction(Enum):
    """Actions the empathy engine can recommend."""

    ACKNOWLEDGE = "acknowledge"
    ENCOURAGE = "encourage"
    SUGGEST_BREAK = "suggest_break"
    SIMPLIFY = "simplify"
    CELEBRATE = "celebrate"
    REDIRECT = "redirect"
    NONE = "none"


class TrendDirection(Enum):
    """Directional trend of an emotional arc."""

    IMPROVING = "improving"
    DECLINING = "declining"
    STABLE = "stable"
    VOLATILE = "volatile"


@dataclass
class EmotionReading:
    """Single point-in-time emotion measurement."""

    emotion: EmotionType
    intensity: float  # 0.0–1.0
    confidence: float  # 0.0–1.0
    signals: List[str] = field(default_factory=list)
    context: str = ""
    timestamp: float = field(default_factory=time.time)

    def _to_dict(self) -> Dict[str, Any]:
        return {
            "emotion": self.emotion.value,
            "intensity": self.intensity,
            "confidence": self.confidence,
            "signals": list(self.signals),
            "context": self.context,
            "timestamp": self.timestamp,
        }


@dataclass
class SentimentScore:
    """Valence-Arousal-Dominance (VAD) sentiment representation."""

    valence: float    # -1.0 (negative) to 1.0 (positive)
    arousal: float    # 0.0 (calm) to 1.0 (excited/agitated)
    dominance: float  # 0.0 (submissive) to 1.0 (dominant/confident)

    def _to_dict(self) -> Dict[str, float]:
        return {
            "valence": self.valence,
            "arousal": self.arousal,
            "dominance": self.dominance,
        }


@dataclass
class EmotionalArc:
    """Trajectory of emotions across a session."""

    session_id: str
    readings: List[EmotionReading] = field(default_factory=list)
    trend: TrendDirection = TrendDirection.STABLE
    dominant_emotion: EmotionType = EmotionType.NEUTRAL
    average_valence: float = 0.0
    volatility: float = 0.0  # 0.0–1.0
    turning_points: List[Dict[str, Any]] = field(default_factory=list)

    def _to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "readings": [r._to_dict() for r in self.readings],
            "trend": self.trend.value,
            "dominant_emotion": self.dominant_emotion.value,
            "average_valence": self.average_valence,
            "volatility": self.volatility,
            "turning_points": list(self.turning_points),
        }


@dataclass
class EmpathyTrigger:
    """Rule that maps an emotion+intensity to an empathetic action."""

    trigger_emotion: EmotionType
    intensity_threshold: float
    action: EmpathyAction
    message_template: str
    priority: int = 5        # 1–10, higher = more urgent
    cooldown_seconds: float = 300.0

    def _to_dict(self) -> Dict[str, Any]:
        return {
            "trigger_emotion": self.trigger_emotion.value,
            "intensity_threshold": self.intensity_threshold,
            "action": self.action.value,
            "message_template": self.message_template,
            "priority": self.priority,
            "cooldown_seconds": self.cooldown_seconds,
        }


@dataclass
class FatigueScore:
    """Multi-factor fatigue and burnout risk assessment."""

    current_level: float  # 0.0–1.0
    session_duration_minutes: float = 0.0
    frustration_accumulation: float = 0.0
    recovery_estimate_minutes: float = 0.0
    burnout_risk: str = "low"  # low, medium, high, critical
    contributing_factors: List[str] = field(default_factory=list)

    def _to_dict(self) -> Dict[str, Any]:
        return {
            "current_level": self.current_level,
            "session_duration_minutes": self.session_duration_minutes,
            "frustration_accumulation": self.frustration_accumulation,
            "recovery_estimate_minutes": self.recovery_estimate_minutes,
            "burnout_risk": self.burnout_risk,
            "contributing_factors": list(self.contributing_factors),
        }


@dataclass
class EmotionalProfile:
    """Aggregate emotional profile built from session history."""

    user_id: str
    baseline_mood: EmotionType = EmotionType.NEUTRAL
    emotional_resilience: float = 0.5
    frustration_threshold: float = 0.6
    preferred_support_style: EmpathyAction = EmpathyAction.ENCOURAGE
    sessions_analyzed: int = 0
    last_updated: float = field(default_factory=time.time)

    def _to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "baseline_mood": self.baseline_mood.value,
            "emotional_resilience": self.emotional_resilience,
            "frustration_threshold": self.frustration_threshold,
            "preferred_support_style": self.preferred_support_style.value,
            "sessions_analyzed": self.sessions_analyzed,
            "last_updated": self.last_updated,
        }
