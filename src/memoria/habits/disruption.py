"""DisruptionAlert — detects deviations from established routines."""

from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from .types import DisruptionEvent, DisruptionSeverity


class DisruptionAlert:
    """Detects deviations from established routines and habits.

    Maintains expected actions for each routine and compares incoming
    actual actions against those expectations, generating severity-graded
    disruption events when deviations occur.
    """

    def __init__(self, max_events: int = 1000) -> None:
        self._lock = threading.RLock()
        self._events: List[DisruptionEvent] = []
        # routine_id -> [(expected_action, expected_time)]
        self._routine_expectations: Dict[str, List[Tuple[str, float]]] = {}
        # routine_id -> index into expectations (current step)
        self._check_index: Dict[str, int] = {}
        # routine_id -> consecutive disruption counter
        self._consecutive_disruptions: Dict[str, int] = {}
        # routine_id -> total checks counter
        self._total_checks: Dict[str, int] = {}
        self._max_events = max(1, max_events)

    # ------------------------------------------------------------------
    # Expectations
    # ------------------------------------------------------------------

    def set_expectations(
        self,
        routine_id: str,
        expected_actions: List[str],
        expected_times: Optional[List[float]] = None,
    ) -> None:
        """Set expected actions (and optionally timing) for a routine."""
        if not routine_id or not expected_actions:
            return
        times = list(expected_times) if expected_times else [0.0] * len(expected_actions)
        # Pad or truncate times to match actions length
        while len(times) < len(expected_actions):
            times.append(0.0)
        times = times[: len(expected_actions)]

        with self._lock:
            self._routine_expectations[routine_id] = list(
                zip(expected_actions, times)
            )
            self._check_index[routine_id] = 0
            self._consecutive_disruptions[routine_id] = 0
            self._total_checks[routine_id] = 0

    # ------------------------------------------------------------------
    # Disruption checking
    # ------------------------------------------------------------------

    def check_disruption(
        self,
        routine_id: str,
        actual_action: str,
        timestamp: Optional[float] = None,
    ) -> Optional[DisruptionEvent]:
        """Check if the actual action matches expectations.

        Returns a DisruptionEvent if disrupted, else None.

        Severity:
        - MINOR   : correct action but timing off by > 30 %
        - MODERATE : different action or wrong order
        - MAJOR   : routine not followed for 3+ consecutive checks
        - CRITICAL : routine not followed for 7+ consecutive checks
        """
        ts = timestamp if timestamp is not None else time.time()

        with self._lock:
            expectations = self._routine_expectations.get(routine_id)
            if not expectations:
                return None

            idx = self._check_index.get(routine_id, 0)
            self._total_checks.setdefault(routine_id, 0)
            self._total_checks[routine_id] += 1

            expected_action, expected_time = expectations[idx % len(expectations)]

            # Advance the index for next call
            self._check_index[routine_id] = (idx + 1) % len(expectations)

            # Determine disruption
            if actual_action == expected_action:
                # Check timing
                if expected_time > 0 and ts > 0:
                    deviation = abs(ts - expected_time) / max(expected_time, 1e-6)
                    if deviation > 0.3:
                        self._consecutive_disruptions[routine_id] = (
                            self._consecutive_disruptions.get(routine_id, 0) + 1
                        )
                        severity = self._severity_from_consecutive(
                            self._consecutive_disruptions[routine_id]
                        )
                        if severity is None:
                            severity = DisruptionSeverity.MINOR
                        event = self._make_event(
                            routine_id,
                            severity,
                            expected_action,
                            actual_action,
                            ts,
                            ["Timing deviation detected"],
                        )
                        self._store_event(event)
                        return event
                # No disruption
                self._consecutive_disruptions[routine_id] = 0
                return None

            # Action mismatch
            self._consecutive_disruptions[routine_id] = (
                self._consecutive_disruptions.get(routine_id, 0) + 1
            )
            consec = self._consecutive_disruptions[routine_id]

            severity = self._severity_from_consecutive(consec)
            if severity is None:
                severity = DisruptionSeverity.MODERATE

            reasons = self._infer_reasons(consec, actual_action, expected_action)

            event = self._make_event(
                routine_id, severity, expected_action, actual_action, ts, reasons
            )
            self._store_event(event)
            return event

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_disruptions(
        self,
        routine_id: Optional[str] = None,
        severity: Optional[DisruptionSeverity] = None,
        limit: int = 50,
    ) -> List[DisruptionEvent]:
        """Return disruption events, optionally filtered."""
        with self._lock:
            events = list(self._events)
        if routine_id is not None:
            events = [e for e in events if e.routine_id == routine_id]
        if severity is not None:
            events = [e for e in events if e.severity == severity]
        return events[-limit:]

    def get_disruption_rate(self, routine_id: str) -> float:
        """Disruption rate = disruptions / total checks (0.0-1.0)."""
        with self._lock:
            total = self._total_checks.get(routine_id, 0)
            if total == 0:
                return 0.0
            disruptions = sum(
                1 for e in self._events if e.routine_id == routine_id
            )
        return max(0.0, min(1.0, disruptions / total))

    def get_stability_score(self, routine_id: str) -> float:
        """1.0 - disruption_rate. Higher = more stable routine."""
        return 1.0 - self.get_disruption_rate(routine_id)

    def get_disruption_summary(self) -> Dict:
        """Summary of disruption events."""
        with self._lock:
            events = list(self._events)

        by_severity: Dict[str, int] = defaultdict(int)
        by_routine: Dict[str, int] = defaultdict(int)
        for e in events:
            by_severity[e.severity.value] += 1
            by_routine[e.routine_id] += 1

        most_disrupted = sorted(by_routine.items(), key=lambda x: x[1], reverse=True)[
            :5
        ]

        # Trend: compare first half vs second half
        trend = "stable"
        if len(events) >= 4:
            mid = len(events) // 2
            first_half = events[:mid]
            second_half = events[mid:]
            first_span = first_half[-1].timestamp - first_half[0].timestamp
            second_span = second_half[-1].timestamp - second_half[0].timestamp
            # Compare event rates (events per unit time)
            first_rate = len(first_half) / max(first_span, 1e-6)
            second_rate = len(second_half) / max(second_span, 1e-6)
            if first_rate > 0 and second_rate > first_rate * 1.3:
                trend = "increasing"
            elif first_rate > 0 and second_rate < first_rate * 0.7:
                trend = "decreasing"

        return {
            "total_disruptions": len(events),
            "by_severity": dict(by_severity),
            "most_disrupted_routines": [
                {"routine_id": rid, "count": cnt} for rid, cnt in most_disrupted
            ],
            "trend": trend,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_event(
        self,
        routine_id: str,
        severity: DisruptionSeverity,
        expected: str,
        actual: str,
        ts: float,
        reasons: List[str],
    ) -> DisruptionEvent:
        return DisruptionEvent(
            disruption_id=uuid.uuid4().hex,
            routine_id=routine_id,
            severity=severity,
            expected_action=expected,
            actual_action=actual,
            timestamp=ts,
            possible_reasons=reasons,
        )

    def _store_event(self, event: DisruptionEvent) -> None:
        """Store event, enforcing max_events cap."""
        if len(self._events) >= self._max_events:
            self._events = self._events[-(self._max_events // 2) :]
        self._events.append(event)

    @staticmethod
    def _severity_from_consecutive(consecutive: int) -> Optional[DisruptionSeverity]:
        if consecutive >= 7:
            return DisruptionSeverity.CRITICAL
        if consecutive >= 3:
            return DisruptionSeverity.MAJOR
        return None

    @staticmethod
    def _infer_reasons(
        consecutive: int, actual: str, expected: str
    ) -> List[str]:
        reasons: List[str] = []
        if consecutive >= 7:
            reasons.append("Complete routine abandonment detected")
        elif consecutive >= 3:
            reasons.append("Extended routine disruption")
        if actual == "none":
            reasons.append("Action was skipped entirely")
        elif actual != expected:
            reasons.append("Schedule change")
            reasons.append("New workflow")
        return reasons if reasons else ["Unexpected action change"]
