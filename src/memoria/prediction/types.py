"""Behavioral Prediction Engine — data types."""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Tuple


class PredictionType(Enum):
    """Types of behavioral predictions."""

    NEXT_ACTION = "next_action"
    NEXT_TOPIC = "next_topic"
    NEXT_TOOL = "next_tool"
    NEXT_FILE = "next_file"
    CONTEXT_SWITCH = "context_switch"
    SESSION_END = "session_end"
    DIFFICULTY_SPIKE = "difficulty_spike"
    HELP_NEEDED = "help_needed"


class AnomalyType(Enum):
    """Types of behavioral anomalies."""

    UNUSUAL_TIMING = "unusual_timing"
    BEHAVIOR_SHIFT = "behavior_shift"
    SKILL_REGRESSION = "skill_regression"
    PATTERN_BREAK = "pattern_break"
    TOPIC_DEVIATION = "topic_deviation"


class DifficultyLevel(Enum):
    """Task difficulty levels (ordered trivial → expert)."""

    TRIVIAL = "trivial"
    EASY = "easy"
    MODERATE = "moderate"
    HARD = "hard"
    EXPERT = "expert"


@dataclass
class Prediction:
    """A single behavioral prediction with confidence and alternatives."""

    prediction_type: PredictionType
    predicted_value: str
    confidence: float  # 0.0-1.0
    reasoning: str
    alternatives: List[Tuple[str, float]] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prediction_type": self.prediction_type.value,
            "predicted_value": self.predicted_value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "alternatives": [
                {"value": v, "confidence": c} for v, c in self.alternatives
            ],
            "context": self.context,
            "timestamp": self.timestamp,
        }


@dataclass
class ActionSequence:
    """A repeated sequence of user actions."""

    actions: List[str]
    frequency: int = 1
    avg_duration_seconds: float = 0.0
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "actions": list(self.actions),
            "frequency": self.frequency,
            "avg_duration_seconds": self.avg_duration_seconds,
            "last_seen": self.last_seen,
        }


@dataclass
class TransitionMatrix:
    """Markov chain transition probability matrix."""

    states: List[str] = field(default_factory=list)
    matrix: Dict[str, Dict[str, float]] = field(default_factory=dict)
    total_transitions: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "states": list(self.states),
            "matrix": {k: dict(v) for k, v in self.matrix.items()},
            "total_transitions": self.total_transitions,
        }


@dataclass
class AnomalyAlert:
    """Alert raised when anomalous behaviour is detected."""

    anomaly_type: AnomalyType
    severity: float  # 0.0-1.0
    description: str
    baseline_value: Any = None
    observed_value: Any = None
    timestamp: float = field(default_factory=time.time)
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anomaly_type": self.anomaly_type.value,
            "severity": self.severity,
            "description": self.description,
            "baseline_value": self.baseline_value,
            "observed_value": self.observed_value,
            "timestamp": self.timestamp,
            "context": self.context,
        }


@dataclass
class TimingRecommendation:
    """When to surface a suggestion to the user."""

    action: str
    optimal_time: str  # "now", "after_task_completion", "session_start", "wait"
    reasoning: str
    confidence: float = 0.5
    cooldown_remaining: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "optimal_time": self.optimal_time,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "cooldown_remaining": self.cooldown_remaining,
        }


@dataclass
class DifficultyEstimate:
    """Estimated difficulty of a task for this user."""

    task_description: str
    estimated_difficulty: DifficultyLevel
    user_competence: float  # 0.0-1.0
    struggle_probability: float  # 0.0-1.0
    estimated_time_minutes: float = 0.0
    reasoning: str = ""
    suggestions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_description": self.task_description,
            "estimated_difficulty": self.estimated_difficulty.value,
            "user_competence": self.user_competence,
            "struggle_probability": self.struggle_probability,
            "estimated_time_minutes": self.estimated_time_minutes,
            "reasoning": self.reasoning,
            "suggestions": list(self.suggestions),
        }
