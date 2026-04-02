"""Habit & Routine Intelligence for MEMORIA.

Provides Digital-Twin-inspired habit detection, routine optimisation,
anchor behaviour discovery, and disruption alerting.
"""

from .anchors import AnchorDetector
from .disruption import DisruptionAlert
from .optimizer import RoutineOptimizer
from .tracker import HabitTracker
from .types import (
    AnchorBehavior,
    AnchorType,
    DisruptionEvent,
    DisruptionSeverity,
    Habit,
    HabitStrength,
    Routine,
    RoutineStatus,
)

__all__ = [
    "AnchorBehavior",
    "AnchorDetector",
    "AnchorType",
    "DisruptionAlert",
    "DisruptionEvent",
    "DisruptionSeverity",
    "Habit",
    "HabitStrength",
    "HabitTracker",
    "Routine",
    "RoutineOptimizer",
    "RoutineStatus",
]
