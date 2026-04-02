"""Emotional Intelligence Layer — emotional arc tracker.

Maintains per-session reading histories and computes trends,
dominant emotions, turning points, volatility, and cross-session
aggregates.
"""

import statistics
import threading
from collections import Counter
from typing import Any, Dict, List

from .types import (
    EmotionalArc,
    EmotionalProfile,
    EmotionReading,
    EmotionType,
    TrendDirection,
)

# VAD valence mapping for trend computation
_VALENCE: Dict[EmotionType, float] = {
    EmotionType.JOY:          0.9,
    EmotionType.SATISFACTION:  0.7,
    EmotionType.EXCITEMENT:    0.8,
    EmotionType.CONFIDENCE:    0.6,
    EmotionType.FRUSTRATION:  -0.7,
    EmotionType.ANGER:        -0.8,
    EmotionType.CONFUSION:    -0.4,
    EmotionType.ANXIETY:      -0.6,
    EmotionType.BOREDOM:      -0.3,
    EmotionType.FATIGUE:      -0.5,
    EmotionType.CURIOSITY:     0.5,
    EmotionType.NEUTRAL:       0.0,
}


class EmotionalArcTracker:
    """Tracks emotional trajectories across one or more sessions."""

    def __init__(self, max_readings: int = 500) -> None:
        self._lock = threading.RLock()
        self._max_readings = max_readings
        self._sessions: Dict[str, List[EmotionReading]] = {}
        self._max_sessions: int = 1_000

    # ── recording ────────────────────────────────────────────────────

    def record_reading(
        self, reading: EmotionReading, session_id: str = "default"
    ) -> None:
        """Append a reading to the given session."""
        with self._lock:
            lst = self._sessions.setdefault(session_id, [])
            lst.append(reading)
            if len(lst) > self._max_readings:
                self._sessions[session_id] = lst[-self._max_readings :]
            if len(self._sessions) > self._max_sessions:
                oldest = next(iter(self._sessions))
                del self._sessions[oldest]

    # ── queries ──────────────────────────────────────────────────────

    def get_arc(self, session_id: str = "default") -> EmotionalArc:
        """Build and return the full EmotionalArc for a session."""
        with self._lock:
            readings = list(self._sessions.get(session_id, []))
            arc = EmotionalArc(session_id=session_id, readings=readings)
            if not readings:
                return arc

            valences = [self._valence_of(r) for r in readings]
            arc.average_valence = round(sum(valences) / len(valences), 4)
            arc.volatility = self._volatility(valences)
            arc.trend = self._compute_trend(valences)
            arc.dominant_emotion = self._dominant(readings)
            arc.turning_points = self._turning_points(readings, valences)
            return arc

    def get_trend(self, session_id: str = "default") -> TrendDirection:
        """Return the current trend for a session."""
        with self._lock:
            readings = self._sessions.get(session_id, [])
            if not readings:
                return TrendDirection.STABLE
            valences = [self._valence_of(r) for r in readings]
            return self._compute_trend(valences)

    def get_dominant_emotion(
        self, session_id: str = "default"
    ) -> EmotionType:
        """Return the most frequent emotion in a session."""
        with self._lock:
            readings = self._sessions.get(session_id, [])
            return self._dominant(readings)

    def get_turning_points(
        self, session_id: str = "default"
    ) -> List[Dict[str, Any]]:
        """Return moments of significant emotional change."""
        with self._lock:
            readings = self._sessions.get(session_id, [])
            if not readings:
                return []
            valences = [self._valence_of(r) for r in readings]
            return self._turning_points(readings, valences)

    def get_cross_session_trend(self, limit: int = 10) -> Dict[str, Any]:
        """Aggregate trend across the most recent *limit* sessions."""
        with self._lock:
            session_ids = list(self._sessions.keys())[-limit:]
            if not session_ids:
                return {
                    "sessions": 0,
                    "trend": TrendDirection.STABLE.value,
                    "avg_valences": [],
                }
            avg_vals: List[float] = []
            for sid in session_ids:
                readings = self._sessions[sid]
                if readings:
                    vals = [self._valence_of(r) for r in readings]
                    avg_vals.append(round(sum(vals) / len(vals), 4))
            trend = self._compute_trend(avg_vals) if avg_vals else TrendDirection.STABLE
            return {
                "sessions": len(session_ids),
                "trend": trend.value,
                "avg_valences": avg_vals,
            }

    def get_emotional_profile(self) -> EmotionalProfile:
        """Build an aggregate EmotionalProfile from all sessions."""
        with self._lock:
            all_readings: List[EmotionReading] = []
            for readings in self._sessions.values():
                all_readings.extend(readings)

            profile = EmotionalProfile(user_id="aggregate")
            profile.sessions_analyzed = len(self._sessions)

            if not all_readings:
                return profile

            profile.baseline_mood = self._dominant(all_readings)

            # Resilience: average recovery speed from negative emotions
            resilience_samples: List[float] = []
            for readings in self._sessions.values():
                for i in range(1, len(readings)):
                    prev_v = self._valence_of(readings[i - 1])
                    cur_v = self._valence_of(readings[i])
                    if prev_v < -0.2 and cur_v > prev_v:
                        recovery = min(1.0, (cur_v - prev_v) / 1.0)
                        resilience_samples.append(recovery)
            if resilience_samples:
                profile.emotional_resilience = round(
                    sum(resilience_samples) / len(resilience_samples), 4
                )

            return profile

    # ── session management ───────────────────────────────────────────

    def reset_session(self, session_id: str = "default") -> None:
        """Clear all data for a session."""
        with self._lock:
            self._sessions.pop(session_id, None)

    # ── helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _valence_of(reading: EmotionReading) -> float:
        base = _VALENCE.get(reading.emotion, 0.0)
        return round(base * reading.intensity, 4)

    @staticmethod
    def _dominant(readings: List[EmotionReading]) -> EmotionType:
        if not readings:
            return EmotionType.NEUTRAL
        counter: Counter = Counter(r.emotion for r in readings)
        return counter.most_common(1)[0][0]

    @staticmethod
    def _compute_trend(valences: List[float]) -> TrendDirection:
        if len(valences) < 2:
            return TrendDirection.STABLE
        mid = len(valences) // 2
        first_half = valences[:mid] if mid else valences[:1]
        second_half = valences[mid:] if mid else valences[1:]
        avg_first = sum(first_half) / len(first_half) if first_half else 0.0
        avg_second = sum(second_half) / len(second_half) if second_half else 0.0

        # Directional trends take priority over volatility
        if avg_second > avg_first + 0.1:
            return TrendDirection.IMPROVING
        if avg_second < avg_first - 0.1:
            return TrendDirection.DECLINING

        if len(valences) >= 3:
            sd = statistics.pstdev(valences)
            if sd > 0.3:
                return TrendDirection.VOLATILE

        return TrendDirection.STABLE

    @staticmethod
    def _volatility(valences: List[float]) -> float:
        if len(valences) < 2:
            return 0.0
        return round(min(1.0, statistics.pstdev(valences)), 4)

    @staticmethod
    def _turning_points(
        readings: List[EmotionReading], valences: List[float]
    ) -> List[Dict[str, Any]]:
        points: List[Dict[str, Any]] = []
        for i in range(1, len(valences)):
            delta = valences[i] - valences[i - 1]
            if abs(delta) > 0.3:
                points.append({
                    "index": i,
                    "from_emotion": readings[i - 1].emotion.value,
                    "to_emotion": readings[i].emotion.value,
                    "valence_delta": round(delta, 4),
                    "timestamp": readings[i].timestamp,
                })
        return points
