"""Cognitive Load Management — load tracking."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List

from .types import CognitiveSnapshot, FocusState, LoadLevel


@dataclass
class _Interaction:
    topic: str
    complexity: float
    info_volume: int
    timestamp: float


class LoadTracker:
    """Tracks cognitive load metrics over time."""

    _MAX_INTERACTIONS = 5000
    _MAX_TOPIC_LENGTH = 500

    def __init__(self, window_minutes: float = 30.0) -> None:
        self._lock = threading.Lock()
        self._window_minutes = max(1.0, float(window_minutes))
        self._interactions: List[_Interaction] = []
        self._started_at: float = time.time()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_interaction(
        self,
        topic: str,
        complexity: float = 0.5,
        info_volume: int = 1,
    ) -> None:
        """Record a user interaction."""
        complexity = max(0.0, min(1.0, float(complexity)))
        info_volume = max(0, int(info_volume))
        with self._lock:
            self._interactions.append(
                _Interaction(
                    topic=str(topic)[:self._MAX_TOPIC_LENGTH],
                    complexity=complexity,
                    info_volume=info_volume,
                    timestamp=time.time(),
                )
            )
            if len(self._interactions) > self._MAX_INTERACTIONS:
                self._interactions = self._interactions[-self._MAX_INTERACTIONS:]

    def get_current_load(self) -> CognitiveSnapshot:
        """Compute current cognitive load from recent interactions."""
        with self._lock:
            return self._compute_snapshot(time.time())

    def get_load_trend(self, window_minutes: int = 60) -> List[CognitiveSnapshot]:
        """Load snapshots sampled at 5-minute intervals over *window_minutes*."""
        window_minutes = max(5, int(window_minutes))
        now = time.time()
        with self._lock:
            snapshots: List[CognitiveSnapshot] = []
            steps = window_minutes // 5
            for i in range(steps + 1):
                t = now - (steps - i) * 300
                snapshots.append(self._compute_snapshot(t))
            return snapshots

    def reset(self) -> None:
        """Reset all tracker state."""
        with self._lock:
            self._interactions.clear()
            self._started_at = time.time()

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "window_minutes": self._window_minutes,
                "started_at": self._started_at,
                "interactions": [
                    {
                        "topic": ix.topic,
                        "complexity": ix.complexity,
                        "info_volume": ix.info_volume,
                        "timestamp": ix.timestamp,
                    }
                    for ix in self._interactions
                ],
            }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LoadTracker:
        tracker = cls(window_minutes=data.get("window_minutes", 30.0))
        tracker._started_at = data.get("started_at", time.time())
        for ix in data.get("interactions", []):
            tracker._interactions.append(
                _Interaction(
                    topic=ix["topic"],
                    complexity=ix["complexity"],
                    info_volume=ix["info_volume"],
                    timestamp=ix["timestamp"],
                )
            )
        if len(tracker._interactions) > cls._MAX_INTERACTIONS:
            tracker._interactions = tracker._interactions[-cls._MAX_INTERACTIONS:]
        return tracker

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_snapshot(self, at_time: float) -> CognitiveSnapshot:
        """Compute a snapshot as of *at_time*.  Caller must hold lock."""
        cutoff = at_time - self._window_minutes * 60
        recent = [ix for ix in self._interactions if ix.timestamp >= cutoff]

        if not recent:
            return CognitiveSnapshot(
                load_level=LoadLevel.MINIMAL,
                load_score=0.0,
                focus_state=FocusState.FOCUSED,
                active_topics=0,
                context_switches=0,
                session_duration_minutes=(at_time - self._started_at) / 60.0,
                timestamp=at_time,
            )

        unique_topics = {ix.topic for ix in recent}
        topic_diversity_norm = min(1.0, len(unique_topics) / 10.0)

        window_secs = self._window_minutes * 60
        rate = len(recent) / (window_secs / 60.0)  # per minute
        rate_norm = min(1.0, rate / 20.0)

        total_weight = 0.0
        weighted_sum = 0.0
        for i, ix in enumerate(recent):
            w = 1.0 + i * 0.1  # newer interactions weigh more
            weighted_sum += ix.complexity * w
            total_weight += w
        complexity_avg = weighted_sum / total_weight if total_weight > 0 else 0.0

        total_volume = sum(ix.info_volume for ix in recent)
        volume_norm = min(1.0, total_volume / 100.0)

        score = (
            0.30 * topic_diversity_norm
            + 0.25 * rate_norm
            + 0.25 * complexity_avg
            + 0.20 * volume_norm
        )
        score = max(0.0, min(1.0, score))

        load_level = self._score_to_level(score)

        # Context switches: consecutive interactions with different topics
        ctx_switches = 0
        for i in range(1, len(recent)):
            if recent[i].topic != recent[i - 1].topic:
                ctx_switches += 1

        # Focus state heuristic
        if ctx_switches > 7:
            focus = FocusState.SCATTERED
        elif ctx_switches > 3:
            focus = FocusState.DISTRACTED
        elif score > 0.8:
            focus = FocusState.LIGHT_FOCUS
        elif score < 0.3:
            focus = FocusState.DEEP_FOCUS
        else:
            focus = FocusState.FOCUSED

        return CognitiveSnapshot(
            load_level=load_level,
            load_score=round(score, 4),
            focus_state=focus,
            active_topics=len(unique_topics),
            context_switches=ctx_switches,
            session_duration_minutes=(at_time - self._started_at) / 60.0,
            timestamp=at_time,
        )

    @staticmethod
    def _score_to_level(score: float) -> LoadLevel:
        if score < 0.2:
            return LoadLevel.MINIMAL
        if score < 0.4:
            return LoadLevel.LOW
        if score < 0.6:
            return LoadLevel.MODERATE
        if score < 0.8:
            return LoadLevel.HIGH
        return LoadLevel.OVERLOADED
