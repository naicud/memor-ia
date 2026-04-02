"""HabitTracker — detects recurring user habits using Digital Twin modelling."""

from __future__ import annotations

import math
import statistics
import threading
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from .types import Habit, HabitStrength


class HabitTracker:
    """Detects recurring user habits and routines using Digital Twin modelling.

    Records a stream of user actions, finds repeated sub-sequences via
    sliding-window pattern matching, and classifies them into habits with
    strength, typical timing, and consistency scores.
    """

    def __init__(
        self,
        min_occurrences: int = 3,
        max_habits: int = 200,
        max_actions: int = 50000,
    ) -> None:
        self._lock = threading.RLock()
        self._action_log: List[Tuple[str, float, str]] = []  # (action, ts, product)
        self._habits: Dict[str, Habit] = {}
        self._min_occurrences = max(1, min_occurrences)
        self._max_habits = max(1, max_habits)
        self._max_actions = max(1, max_actions)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_action(
        self,
        action: str,
        product_id: str = "",
        timestamp: Optional[float] = None,
    ) -> None:
        """Record a user action for habit detection."""
        if not action:
            return
        ts = timestamp if timestamp is not None else time.time()
        with self._lock:
            if len(self._action_log) >= self._max_actions:
                self._action_log = self._action_log[-(self._max_actions // 2) :]
            self._action_log.append((action, ts, product_id))

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect_habits(
        self,
        min_frequency: float = 2.0,
        min_length: int = 2,
        max_length: int = 5,
    ) -> List[Habit]:
        """Detect habits from the action log using sliding-window pattern matching.

        A habit is a repeated sequence of actions with similar timing.

        1. Find all sub-sequences of length *min_length* .. *max_length*.
        2. Count occurrences of each unique sequence.
        3. Filter by *min_occurrences* and *min_frequency*.
        4. Compute strength, typical_time, and consistency.
        """
        min_length = max(1, min_length)
        max_length = max(min_length, max_length)

        with self._lock:
            log = list(self._action_log)

        if len(log) < min_length:
            return []

        # Collect sub-sequences with their timestamps
        seq_occurrences: Dict[Tuple[str, ...], List[Tuple[float, float, List[str]]]] = (
            defaultdict(list)
        )

        for win_len in range(min_length, max_length + 1):
            for i in range(len(log) - win_len + 1):
                window = log[i : i + win_len]
                key = tuple(a for a, _, _ in window)
                first_ts = window[0][1]
                last_ts = window[-1][1]
                products = list({p for _, _, p in window if p})
                seq_occurrences[key].append((first_ts, last_ts, products))

        detected: List[Habit] = []

        for seq, occurrences in seq_occurrences.items():
            count = len(occurrences)
            if count < self._min_occurrences:
                continue

            first_ts = min(o[0] for o in occurrences)
            last_ts = max(o[0] for o in occurrences)
            span_weeks = max((last_ts - first_ts) / (7 * 86400), 1e-6)
            freq = count / span_weeks

            if freq < min_frequency:
                continue

            # Strength
            strength = self._classify_strength(count)

            # Typical time from hour of first action
            hours = [datetime.fromtimestamp(o[0], tz=timezone.utc).hour for o in occurrences]
            typical_time = self._classify_time(
                statistics.mean(hours) if hours else 12
            )

            # Typical day
            days = [datetime.fromtimestamp(o[0], tz=timezone.utc).weekday() for o in occurrences]
            weekday_count = sum(1 for d in days if d < 5)
            weekend_count = len(days) - weekday_count
            if weekday_count > 0 and weekend_count > 0:
                typical_day = "daily"
            elif weekday_count > 0:
                typical_day = "weekday"
            else:
                typical_day = "weekend"

            # Consistency: 1 - (std / mean) of intervals, clamped
            intervals = [
                occurrences[j][0] - occurrences[j - 1][0]
                for j in range(1, len(occurrences))
            ]
            consistency = self._compute_consistency(intervals)

            # Duration
            durations = [o[1] - o[0] for o in occurrences]
            avg_duration = statistics.mean(durations) if durations else 0.0

            # Products
            all_products: set[str] = set()
            for _, _, prods in occurrences:
                all_products.update(prods)

            habit_id = uuid.uuid4().hex
            habit = Habit(
                habit_id=habit_id,
                name=" → ".join(seq),
                actions=list(seq),
                frequency_per_week=round(freq, 2),
                strength=strength,
                typical_time=typical_time,
                typical_day=typical_day,
                products_involved=sorted(all_products),
                occurrence_count=count,
                first_seen=first_ts,
                last_seen=last_ts,
                avg_duration_seconds=round(avg_duration, 2),
                consistency_score=round(consistency, 4),
            )
            detected.append(habit)

        # Sort by occurrence count descending; cap to max_habits
        detected.sort(key=lambda h: h.occurrence_count, reverse=True)
        detected = detected[: self._max_habits]

        with self._lock:
            self._habits = {h.habit_id: h for h in detected}

        return list(detected)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_habits(
        self,
        product_id: Optional[str] = None,
        min_strength: Optional[HabitStrength] = None,
    ) -> List[Habit]:
        """Get detected habits, optionally filtered by product or strength."""
        strength_order = {
            HabitStrength.EMERGING: 0,
            HabitStrength.FORMING: 1,
            HabitStrength.ESTABLISHED: 2,
            HabitStrength.INGRAINED: 3,
        }
        with self._lock:
            habits = list(self._habits.values())

        if product_id is not None:
            habits = [h for h in habits if product_id in h.products_involved]

        if min_strength is not None:
            threshold = strength_order.get(min_strength, 0)
            habits = [
                h for h in habits if strength_order.get(h.strength, 0) >= threshold
            ]

        return habits

    def get_habit(self, habit_id: str) -> Optional[Habit]:
        """Return a single habit by ID, or None."""
        with self._lock:
            return self._habits.get(habit_id)

    def is_habit_active(self, habit_id: str, staleness_days: int = 14) -> bool:
        """Check if a habit was seen within the staleness window."""
        with self._lock:
            habit = self._habits.get(habit_id)
        if habit is None:
            return False
        return (time.time() - habit.last_seen) < (staleness_days * 86400)

    def get_habit_summary(self) -> Dict:
        """Summary of detected habits."""
        with self._lock:
            habits = list(self._habits.values())

        by_strength: Dict[str, int] = defaultdict(int)
        products: set[str] = set()
        for h in habits:
            by_strength[h.strength.value] += 1
            products.update(h.products_involved)

        strongest = sorted(habits, key=lambda h: h.occurrence_count, reverse=True)[:5]

        return {
            "total_habits": len(habits),
            "by_strength": dict(by_strength),
            "products_involved": sorted(products),
            "strongest_habits": [
                {"name": h.name, "occurrences": h.occurrence_count} for h in strongest
            ],
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_strength(count: int) -> HabitStrength:
        if count > 50:
            return HabitStrength.INGRAINED
        if count >= 16:
            return HabitStrength.ESTABLISHED
        if count >= 6:
            return HabitStrength.FORMING
        return HabitStrength.EMERGING

    @staticmethod
    def _classify_time(avg_hour: float) -> str:
        hour = int(avg_hour) % 24
        if 5 <= hour <= 11:
            return "morning"
        if 12 <= hour <= 16:
            return "afternoon"
        if 17 <= hour <= 20:
            return "evening"
        return "night"

    @staticmethod
    def _compute_consistency(intervals: List[float]) -> float:
        if len(intervals) < 2:
            return 1.0
        mean_iv = statistics.mean(intervals)
        if abs(mean_iv) < 1e-9:
            return 1.0
        std_iv = statistics.stdev(intervals)
        raw = 1.0 - (std_iv / mean_iv)
        return max(0.0, min(1.0, raw))
