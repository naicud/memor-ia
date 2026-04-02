"""Optimal suggestion timing based on acceptance history."""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

from .types import TimingRecommendation

# Acceptance-rate thresholds for timing decisions
HIGH_ACCEPTANCE_RATE = 0.7
LOW_ACCEPTANCE_RATE = 0.3
# Number of interactions needed to reach full confidence
CONFIDENCE_SAMPLE_THRESHOLD = 10.0


class TimingOptimizer:
    """Decides *when* to surface a suggestion based on past acceptance rates.

    Tracks per-action acceptance statistics and applies cooldown logic so that
    the user is never overwhelmed with recommendations.
    """

    def __init__(self, cooldown_seconds: float = 300.0) -> None:
        self._lock = threading.RLock()
        self._cooldown = max(0.0, cooldown_seconds)
        self._max_actions: int = 500
        # action -> {total_suggested, total_accepted, last_suggested_at, last_accepted_at}
        self._stats: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_interaction(
        self,
        action: str,
        accepted: bool,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record that *action* was suggested and whether the user accepted."""
        with self._lock:
            now = time.time()
            if action not in self._stats:
                self._stats[action] = {
                    "total_suggested": 0,
                    "total_accepted": 0,
                    "last_suggested_at": 0.0,
                    "last_accepted_at": 0.0,
                    "context": context or {},
                }
            st = self._stats[action]
            st["total_suggested"] += 1
            st["last_suggested_at"] = now
            if accepted:
                st["total_accepted"] += 1
                st["last_accepted_at"] = now
            st["context"] = context or st.get("context", {})

            # Evict oldest entry if over capacity
            if len(self._stats) > self._max_actions:
                oldest = min(self._stats, key=lambda a: self._stats[a]["last_suggested_at"])
                del self._stats[oldest]

    # ------------------------------------------------------------------
    # Timing recommendation
    # ------------------------------------------------------------------

    def suggest_timing(self, action: str) -> TimingRecommendation:
        """Recommend the best moment to suggest *action*."""
        with self._lock:
            st = self._stats.get(action)
            now = time.time()

            if st is None:
                return TimingRecommendation(
                    action=action,
                    optimal_time="now",
                    reasoning="No prior interaction history; suggesting now as default",
                    confidence=0.5,
                    cooldown_remaining=0.0,
                )

            elapsed = now - st["last_suggested_at"]
            cooldown_remaining = max(0.0, self._cooldown - elapsed)

            if cooldown_remaining > 0:
                return TimingRecommendation(
                    action=action,
                    optimal_time="wait",
                    reasoning=(
                        f"Cooldown active — {cooldown_remaining:.0f}s remaining "
                        f"before re-suggesting '{action}'"
                    ),
                    confidence=min(1.0, st["total_suggested"] / CONFIDENCE_SAMPLE_THRESHOLD),
                    cooldown_remaining=cooldown_remaining,
                )

            rate = self._acceptance_rate(st)
            confidence = min(1.0, st["total_suggested"] / CONFIDENCE_SAMPLE_THRESHOLD)

            if rate > HIGH_ACCEPTANCE_RATE:
                return TimingRecommendation(
                    action=action,
                    optimal_time="now",
                    reasoning=(
                        f"High acceptance rate ({rate:.0%}) — user is "
                        f"receptive to '{action}'"
                    ),
                    confidence=confidence,
                )

            if rate < LOW_ACCEPTANCE_RATE:
                return TimingRecommendation(
                    action=action,
                    optimal_time="after_task_completion",
                    reasoning=(
                        f"Low acceptance rate ({rate:.0%}) — avoid "
                        f"interrupting the user"
                    ),
                    confidence=confidence,
                )

            return TimingRecommendation(
                action=action,
                optimal_time="session_start",
                reasoning=(
                    f"Moderate acceptance rate ({rate:.0%}) — suggest at "
                    f"a natural break point"
                ),
                confidence=confidence,
            )

    # ------------------------------------------------------------------
    # Stats helpers
    # ------------------------------------------------------------------

    def get_acceptance_rate(
        self, action: Optional[str] = None
    ) -> Dict[str, Any]:
        """Return acceptance rate(s).

        If *action* is given, returns stats for that action; otherwise returns
        a dict of all actions.
        """
        with self._lock:
            if action is not None:
                st = self._stats.get(action)
                if st is None:
                    return {"action": action, "rate": 0.0, "total": 0}
                return {
                    "action": action,
                    "rate": self._acceptance_rate(st),
                    "total": st["total_suggested"],
                }

            result: Dict[str, Any] = {}
            for act, st in self._stats.items():
                result[act] = {
                    "rate": self._acceptance_rate(st),
                    "total": st["total_suggested"],
                }
            return result

    def set_cooldown(self, seconds: float) -> None:
        """Adjust the cooldown period between repeated suggestions."""
        with self._lock:
            self._cooldown = max(0.0, seconds)

    def get_last_interaction(self, action: str) -> Optional[Dict[str, Any]]:
        """Return metadata about the last interaction for *action*."""
        with self._lock:
            st = self._stats.get(action)
            if st is None:
                return None
            return {
                "action": action,
                "last_suggested_at": st["last_suggested_at"],
                "last_accepted_at": st["last_accepted_at"],
                "total_suggested": st["total_suggested"],
                "total_accepted": st["total_accepted"],
            }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _acceptance_rate(st: Dict[str, Any]) -> float:
        total = st["total_suggested"]
        if total == 0:
            return 0.5
        return st["total_accepted"] / total
