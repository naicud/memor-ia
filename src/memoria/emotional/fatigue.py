"""Emotional Intelligence Layer — fatigue and burnout detector.

Tracks cumulative fatigue across readings and sessions using
exponential decay and provides burnout-risk assessments.
"""

import math
import threading
import time
from typing import Any, Dict, List

from .types import (
    EmotionReading,
    EmotionType,
    FatigueScore,
)

_NEGATIVE_EMOTIONS = frozenset({
    EmotionType.FRUSTRATION,
    EmotionType.ANGER,
    EmotionType.CONFUSION,
    EmotionType.ANXIETY,
})

_POSITIVE_EMOTIONS = frozenset({
    EmotionType.JOY,
    EmotionType.SATISFACTION,
    EmotionType.EXCITEMENT,
})


class FatigueDetector:
    """Cross-session fatigue and burnout detection engine."""

    _NEGATIVE_FATIGUE_RATE: float = 0.1
    _POSITIVE_RECOVERY_RATE: float = 0.05
    _LONG_SESSION_THRESHOLD_MIN: int = 60
    _LONG_SESSION_INTERVAL_MIN: float = 30.0
    _LONG_SESSION_FATIGUE_RATE: float = 0.05

    def __init__(self, fatigue_halflife_minutes: float = 120.0) -> None:
        self._lock = threading.RLock()
        self._halflife = fatigue_halflife_minutes
        self._fatigue: float = 0.0
        self._frustration_acc: float = 0.0
        self._last_negative_ts: float = 0.0
        self._last_update_ts: float = 0.0
        self._session_duration: float = 0.0
        self._contributing: List[str] = []
        self._session_history: List[Dict[str, Any]] = []
        self._last_applied_duration: float = 0.0
        self._max_session_history: int = 1_000

    # ── core API ─────────────────────────────────────────────────────

    def update(
        self,
        reading: EmotionReading,
        session_duration_minutes: float = 0.0,
    ) -> None:
        """Incorporate a new reading into the fatigue model."""
        with self._lock:
            now = reading.timestamp
            self._session_duration = session_duration_minutes

            # Decay existing fatigue since last update
            if self._last_update_ts > 0 and now > self._last_update_ts:
                elapsed_min = (now - self._last_update_ts) / 60.0
                self._fatigue = self._decay(self._fatigue, elapsed_min)
            self._last_update_ts = now

            # Accumulate from negative emotions
            if reading.emotion in _NEGATIVE_EMOTIONS:
                increment = self._NEGATIVE_FATIGUE_RATE * reading.intensity
                self._fatigue += increment
                self._last_negative_ts = now
                if reading.emotion == EmotionType.FRUSTRATION:
                    self._frustration_acc += increment
                factor = f"negative_emotion:{reading.emotion.value}"
                if factor not in self._contributing:
                    self._contributing.append(factor)

            # Recover from positive emotions
            if reading.emotion in _POSITIVE_EMOTIONS:
                decrement = self._POSITIVE_RECOVERY_RATE * reading.intensity
                self._fatigue = max(0.0, self._fatigue - decrement)

            # Session duration contribution (incremental)
            if session_duration_minutes > self._LONG_SESSION_THRESHOLD_MIN:
                total = (session_duration_minutes - self._LONG_SESSION_THRESHOLD_MIN) / self._LONG_SESSION_INTERVAL_MIN * self._LONG_SESSION_FATIGUE_RATE
            else:
                total = 0.0
            if self._last_applied_duration > self._LONG_SESSION_THRESHOLD_MIN:
                prev = (self._last_applied_duration - self._LONG_SESSION_THRESHOLD_MIN) / self._LONG_SESSION_INTERVAL_MIN * self._LONG_SESSION_FATIGUE_RATE
            else:
                prev = 0.0
            delta = total - prev
            if delta > 0:
                self._fatigue += delta
                if "long_session" not in self._contributing:
                    self._contributing.append("long_session")
            self._last_applied_duration = session_duration_minutes

            self._fatigue = max(0.0, min(1.0, self._fatigue))

    def get_fatigue_score(self) -> FatigueScore:
        """Return current FatigueScore with burnout risk assessment."""
        with self._lock:
            level = max(0.0, min(1.0, self._fatigue))
            return FatigueScore(
                current_level=round(level, 4),
                session_duration_minutes=self._session_duration,
                frustration_accumulation=round(self._frustration_acc, 4),
                recovery_estimate_minutes=round(self._recovery_estimate(), 2),
                burnout_risk=self._risk_label(level),
                contributing_factors=list(self._contributing),
            )

    def get_recovery_estimate(self) -> float:
        """Estimated minutes to recover below 0.2 fatigue."""
        with self._lock:
            return round(self._recovery_estimate(), 2)

    def is_burnout_risk(self) -> bool:
        """Quick check: is burnout risk high or critical?"""
        with self._lock:
            return self._fatigue >= 0.5

    # ── session lifecycle ────────────────────────────────────────────

    def record_session_end(
        self,
        session_id: str,
        duration_minutes: float,
        outcome: str = "completed",
    ) -> None:
        """Finalize session fatigue data and store history entry."""
        with self._lock:
            entry = {
                "session_id": session_id,
                "duration_minutes": duration_minutes,
                "outcome": outcome,
                "fatigue_at_end": round(self._fatigue, 4),
                "frustration_accumulation": round(self._frustration_acc, 4),
                "burnout_risk": self._risk_label(self._fatigue),
                "timestamp": time.time(),
            }
            self._session_history.append(entry)
            if len(self._session_history) > self._max_session_history:
                self._session_history = self._session_history[-self._max_session_history:]
            # Inter-session recovery
            self._fatigue = max(0.0, self._fatigue - 0.3)
            self._frustration_acc = max(0.0, self._frustration_acc - 0.1)
            self._contributing.clear()
            self._last_applied_duration = 0.0

    def get_session_fatigue_history(
        self, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Return fatigue summary for the last *limit* sessions."""
        with self._lock:
            return list(self._session_history[-limit:])

    # ── reset ────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Clear all fatigue data."""
        with self._lock:
            self._fatigue = 0.0
            self._frustration_acc = 0.0
            self._last_negative_ts = 0.0
            self._last_update_ts = 0.0
            self._session_duration = 0.0
            self._contributing.clear()
            self._session_history.clear()
            self._last_applied_duration = 0.0

    # ── helpers ──────────────────────────────────────────────────────

    def _decay(self, value: float, elapsed_minutes: float) -> float:
        if self._halflife <= 0 or elapsed_minutes <= 0:
            return value
        return value * math.exp(
            -math.log(2) * elapsed_minutes / self._halflife
        )

    def _recovery_estimate(self) -> float:
        if self._fatigue <= 0.2:
            return 0.0
        if self._halflife <= 0:
            return 0.0
        # time for fatigue to decay from current to 0.2
        # f(t) = fatigue * exp(-ln2 * t / halflife) = 0.2
        # t = -halflife * ln(0.2 / fatigue) / ln2
        ratio = 0.2 / self._fatigue
        if ratio >= 1.0:
            return 0.0
        return -self._halflife * math.log(ratio) / math.log(2)

    @staticmethod
    def _risk_label(level: float) -> str:
        if level < 0.3:
            return "low"
        if level < 0.5:
            return "medium"
        if level < 0.7:
            return "high"
        return "critical"
