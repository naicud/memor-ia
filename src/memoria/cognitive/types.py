"""Cognitive Load Management — data types."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class LoadLevel(Enum):
    MINIMAL = "minimal"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    OVERLOADED = "overloaded"


class ComplexityLevel(Enum):
    TRIVIAL = "trivial"
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    EXPERT = "expert"


class FocusState(Enum):
    DEEP_FOCUS = "deep_focus"
    FOCUSED = "focused"
    LIGHT_FOCUS = "light_focus"
    DISTRACTED = "distracted"
    SCATTERED = "scattered"


class OverloadSignal(Enum):
    RAPID_SWITCHING = "rapid_switching"
    INFO_VOLUME = "info_volume"
    COMPLEXITY_SPIKE = "complexity_spike"
    ERROR_RATE = "error_rate"
    REPETITION = "repetition"
    FATIGUE = "fatigue"


@dataclass
class CognitiveSnapshot:
    load_level: LoadLevel
    load_score: float
    focus_state: FocusState
    active_topics: int = 0
    context_switches: int = 0
    session_duration_minutes: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def _to_dict(self) -> Dict[str, Any]:
        return {
            "load_level": self.load_level.value,
            "load_score": self.load_score,
            "focus_state": self.focus_state.value,
            "active_topics": self.active_topics,
            "context_switches": self.context_switches,
            "session_duration_minutes": self.session_duration_minutes,
            "timestamp": self.timestamp,
        }

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> CognitiveSnapshot:
        return cls(
            load_level=LoadLevel(data["load_level"]),
            load_score=data["load_score"],
            focus_state=FocusState(data["focus_state"]),
            active_topics=data.get("active_topics", 0),
            context_switches=data.get("context_switches", 0),
            session_duration_minutes=data.get("session_duration_minutes", 0.0),
            timestamp=data.get("timestamp", 0.0),
        )


@dataclass
class OverloadAlert:
    is_overloaded: bool
    signals: List[OverloadSignal] = field(default_factory=list)
    severity: float = 0.0
    recommendation: str = ""
    cooldown_minutes: int = 0
    timestamp: float = field(default_factory=time.time)

    def _to_dict(self) -> Dict[str, Any]:
        return {
            "is_overloaded": self.is_overloaded,
            "signals": [s.value for s in self.signals],
            "severity": self.severity,
            "recommendation": self.recommendation,
            "cooldown_minutes": self.cooldown_minutes,
            "timestamp": self.timestamp,
        }

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> OverloadAlert:
        return cls(
            is_overloaded=data["is_overloaded"],
            signals=[OverloadSignal(s) for s in data.get("signals", [])],
            severity=data.get("severity", 0.0),
            recommendation=data.get("recommendation", ""),
            cooldown_minutes=data.get("cooldown_minutes", 0),
            timestamp=data.get("timestamp", 0.0),
        )


@dataclass
class ComplexityAssessment:
    level: ComplexityLevel
    score: float
    factors: Dict[str, float] = field(default_factory=dict)
    adapted_level: Optional[ComplexityLevel] = None
    timestamp: float = field(default_factory=time.time)

    def _to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.value,
            "score": self.score,
            "factors": dict(self.factors),
            "adapted_level": self.adapted_level.value if self.adapted_level else None,
            "timestamp": self.timestamp,
        }

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> ComplexityAssessment:
        adapted = data.get("adapted_level")
        return cls(
            level=ComplexityLevel(data["level"]),
            score=data["score"],
            factors=dict(data.get("factors", {})),
            adapted_level=ComplexityLevel(adapted) if adapted else None,
            timestamp=data.get("timestamp", 0.0),
        )


@dataclass
class FocusSession:
    session_id: str
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    focus_scores: List[float] = field(default_factory=list)
    context_switches: int = 0
    topics: List[str] = field(default_factory=list)
    peak_focus: float = 0.0
    average_focus: float = 0.0

    def _to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "focus_scores": list(self.focus_scores),
            "context_switches": self.context_switches,
            "topics": list(self.topics),
            "peak_focus": self.peak_focus,
            "average_focus": self.average_focus,
        }

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> FocusSession:
        return cls(
            session_id=data["session_id"],
            started_at=data.get("started_at", 0.0),
            ended_at=data.get("ended_at"),
            focus_scores=list(data.get("focus_scores", [])),
            context_switches=data.get("context_switches", 0),
            topics=list(data.get("topics", [])),
            peak_focus=data.get("peak_focus", 0.0),
            average_focus=data.get("average_focus", 0.0),
        )
