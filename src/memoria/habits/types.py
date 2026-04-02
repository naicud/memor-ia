"""Data types for the Habit & Routine Intelligence module."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class HabitStrength(Enum):
    """Strength of a detected habit based on occurrence count."""

    EMERGING = "emerging"  # seen 3-5 times
    FORMING = "forming"  # seen 6-15 times
    ESTABLISHED = "established"  # seen 16-50 times
    INGRAINED = "ingrained"  # seen 50+ times


class RoutineStatus(Enum):
    """Current status of a routine."""

    ACTIVE = "active"
    PAUSED = "paused"
    BROKEN = "broken"
    EVOLVING = "evolving"


class DisruptionSeverity(Enum):
    """Severity level of a routine disruption."""

    MINOR = "minor"  # slight timing deviation
    MODERATE = "moderate"  # skipped step or different order
    MAJOR = "major"  # routine not followed for extended period
    CRITICAL = "critical"  # complete abandonment of established routine


class AnchorType(Enum):
    """Type of anchor behaviour trigger."""

    TEMPORAL = "temporal"  # triggered by time of day
    SEQUENTIAL = "sequential"  # triggered by previous action
    CONTEXTUAL = "contextual"  # triggered by context/situation
    EMOTIONAL = "emotional"  # triggered by emotional state


@dataclass
class Habit:
    """A detected recurring user habit."""

    habit_id: str
    name: str
    actions: List[str]  # sequence of actions
    frequency_per_week: float
    strength: HabitStrength
    typical_time: str = ""  # "morning", "afternoon", "evening", "night"
    typical_day: str = ""  # "weekday", "weekend", "daily"
    products_involved: List[str] = field(default_factory=list)
    occurrence_count: int = 0
    first_seen: float = 0.0
    last_seen: float = 0.0
    avg_duration_seconds: float = 0.0
    consistency_score: float = 0.0  # 0.0-1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "habit_id": self.habit_id,
            "name": self.name,
            "actions": list(self.actions),
            "frequency_per_week": self.frequency_per_week,
            "strength": self.strength.value,
            "typical_time": self.typical_time,
            "typical_day": self.typical_day,
            "products_involved": list(self.products_involved),
            "occurrence_count": self.occurrence_count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "avg_duration_seconds": self.avg_duration_seconds,
            "consistency_score": self.consistency_score,
        }


@dataclass
class Routine:
    """A named routine composed of ordered habits."""

    routine_id: str
    name: str
    habits: List[str] = field(default_factory=list)  # habit_ids in order
    status: RoutineStatus = RoutineStatus.ACTIVE
    expected_frequency: str = "daily"  # "daily", "weekly", "monthly"
    adherence_rate: float = 0.0  # 0.0-1.0
    last_completed: float = 0.0
    total_completions: int = 0
    avg_completion_time: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "routine_id": self.routine_id,
            "name": self.name,
            "habits": list(self.habits),
            "status": self.status.value,
            "expected_frequency": self.expected_frequency,
            "adherence_rate": self.adherence_rate,
            "last_completed": self.last_completed,
            "total_completions": self.total_completions,
            "avg_completion_time": self.avg_completion_time,
        }


@dataclass
class AnchorBehavior:
    """An anchor behaviour that triggers a predictable chain of actions."""

    anchor_id: str
    trigger_action: str
    anchor_type: AnchorType
    triggered_chain: List[str]  # actions that follow
    trigger_probability: float  # 0.0-1.0
    avg_delay_seconds: float  # time between trigger and chain start
    occurrence_count: int = 0
    products_involved: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "trigger_action": self.trigger_action,
            "anchor_type": self.anchor_type.value,
            "triggered_chain": list(self.triggered_chain),
            "trigger_probability": self.trigger_probability,
            "avg_delay_seconds": self.avg_delay_seconds,
            "occurrence_count": self.occurrence_count,
            "products_involved": list(self.products_involved),
        }


@dataclass
class DisruptionEvent:
    """A detected deviation from an established routine."""

    disruption_id: str
    routine_id: str
    severity: DisruptionSeverity
    expected_action: str
    actual_action: str  # what user did instead (or "none")
    timestamp: float
    possible_reasons: List[str] = field(default_factory=list)
    auto_resolved: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "disruption_id": self.disruption_id,
            "routine_id": self.routine_id,
            "severity": self.severity.value,
            "expected_action": self.expected_action,
            "actual_action": self.actual_action,
            "timestamp": self.timestamp,
            "possible_reasons": list(self.possible_reasons),
            "auto_resolved": self.auto_resolved,
        }
