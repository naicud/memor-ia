"""RoutineOptimizer — suggests optimisations to user routines."""

from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from .types import Routine, RoutineStatus


class RoutineOptimizer:
    """Suggests optimisations to user routines based on detected patterns.

    Tracks routine completions, computes adherence rates, and generates
    actionable suggestions to help users improve or simplify their workflows.
    """

    def __init__(self, max_routines: int = 50, max_completions: int = 10000) -> None:
        self._lock = threading.RLock()
        self._routines: Dict[str, Routine] = {}
        self._completion_log: List[Tuple[str, float]] = []  # (routine_id, timestamp)
        self._max_routines = max(1, max_routines)
        self._max_completions = max(1, max_completions)

    # ------------------------------------------------------------------
    # Routine management
    # ------------------------------------------------------------------

    def create_routine(
        self,
        name: str,
        habit_ids: List[str],
        expected_frequency: str = "daily",
    ) -> Routine:
        """Create a named routine from a list of habit IDs."""
        if not name:
            name = "Untitled Routine"
        if expected_frequency not in ("daily", "weekly", "monthly"):
            expected_frequency = "daily"

        with self._lock:
            if len(self._routines) >= self._max_routines:
                oldest = min(
                    self._routines.values(),
                    key=lambda r: r.last_completed,
                )
                del self._routines[oldest.routine_id]

            routine_id = uuid.uuid4().hex
            routine = Routine(
                routine_id=routine_id,
                name=name,
                habits=list(habit_ids),
                status=RoutineStatus.ACTIVE,
                expected_frequency=expected_frequency,
            )
            self._routines[routine_id] = routine

        return routine

    # ------------------------------------------------------------------
    # Completions
    # ------------------------------------------------------------------

    def record_completion(
        self,
        routine_id: str,
        timestamp: Optional[float] = None,
        completion_time: float = 0.0,
    ) -> bool:
        """Record that a routine was completed. Updates adherence_rate."""
        ts = timestamp if timestamp is not None else time.time()
        with self._lock:
            routine = self._routines.get(routine_id)
            if routine is None:
                return False
            routine.total_completions += 1
            routine.last_completed = ts
            if completion_time > 0:
                prev_total = routine.avg_completion_time * (
                    routine.total_completions - 1
                )
                routine.avg_completion_time = (prev_total + completion_time) / (
                    routine.total_completions
                )
            self._completion_log.append((routine_id, ts))
            if len(self._completion_log) > self._max_completions:
                self._completion_log = self._completion_log[-self._max_completions :]
            routine.adherence_rate = self._compute_adherence_locked(routine)
            return True

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_routine(self, routine_id: str) -> Optional[Routine]:
        """Return a routine by ID, or None."""
        with self._lock:
            return self._routines.get(routine_id)

    def get_routines(self, status: Optional[RoutineStatus] = None) -> List[Routine]:
        """Return all routines, optionally filtered by status."""
        with self._lock:
            routines = list(self._routines.values())
        if status is not None:
            routines = [r for r in routines if r.status == status]
        return routines

    # ------------------------------------------------------------------
    # Adherence
    # ------------------------------------------------------------------

    def compute_adherence(self, routine_id: str) -> float:
        """Compute adherence rate based on expected vs actual completions.

        daily  : expected = days since first completion
        weekly : expected = weeks since first completion
        monthly: expected = months since first completion
        adherence = actual / expected, clamped to [0, 1]
        """
        with self._lock:
            routine = self._routines.get(routine_id)
            if routine is None:
                return 0.0
            return self._compute_adherence_locked(routine)

    def _compute_adherence_locked(self, routine: Routine) -> float:
        """Internal adherence computation (caller must hold lock)."""
        completions = [
            ts for rid, ts in self._completion_log if rid == routine.routine_id
        ]
        if len(completions) < 1:
            return 0.0

        first_ts = min(completions)
        elapsed = time.time() - first_ts
        if elapsed <= 0:
            return 1.0

        if routine.expected_frequency == "daily":
            expected = max(1, elapsed / 86400)
        elif routine.expected_frequency == "weekly":
            expected = max(1, elapsed / (7 * 86400))
        elif routine.expected_frequency == "monthly":
            expected = max(1, elapsed / (30 * 86400))
        else:
            expected = max(1, elapsed / 86400)

        return max(0.0, min(1.0, len(completions) / expected))

    # ------------------------------------------------------------------
    # Optimisation suggestions
    # ------------------------------------------------------------------

    def suggest_optimizations(self, routine_id: str) -> List[str]:
        """Suggest optimisations based on routine performance."""
        with self._lock:
            routine = self._routines.get(routine_id)
        if routine is None:
            return []

        suggestions: List[str] = []

        if routine.adherence_rate < 0.5:
            suggestions.append("Consider simplifying this routine")

        if routine.avg_completion_time > 0 and len(routine.habits) > 0:
            avg_per_habit = routine.avg_completion_time / len(routine.habits)
            if avg_per_habit > 300:  # > 5 min per step is suspicious
                suggestions.append("Some steps may be taking too long")

        if len(routine.habits) > 5:
            suggestions.append("Consider splitting into smaller routines")

        if routine.status == RoutineStatus.BROKEN:
            suggestions.append("This routine may no longer fit your workflow")

        return suggestions

    # ------------------------------------------------------------------
    # Drift detection
    # ------------------------------------------------------------------

    def detect_routine_drift(self, routine_id: str) -> Optional[str]:
        """Detect if a routine is evolving. Returns description or None."""
        with self._lock:
            routine = self._routines.get(routine_id)
            if routine is None:
                return None

            completions = [
                ts for rid, ts in self._completion_log if rid == routine_id
            ]

            if len(completions) < 4:
                return None

            completions.sort()
            mid = len(completions) // 2
            first_half = completions[:mid]
            second_half = completions[mid:]

            avg_gap_first = (first_half[-1] - first_half[0]) / max(len(first_half) - 1, 1)
            avg_gap_second = (second_half[-1] - second_half[0]) / max(
                len(second_half) - 1, 1
            )

            if avg_gap_first <= 0:
                return None

            ratio = avg_gap_second / avg_gap_first

            if ratio > 1.5:
                routine.status = RoutineStatus.EVOLVING
                return "Routine is becoming less frequent over time"
            if ratio < 0.67:
                routine.status = RoutineStatus.EVOLVING
                return "Routine is becoming more frequent over time"

            return None
