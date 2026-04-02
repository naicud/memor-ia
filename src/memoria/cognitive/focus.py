"""Cognitive Load Management — focus session optimisation."""

from __future__ import annotations

import math
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from .types import FocusSession, FocusState


class FocusOptimizer:
    """Focus session tracking and optimisation."""

    _MAX_SESSIONS = 100
    _MAX_FOCUS_SCORES = 1000
    _MAX_TOPICS = 500
    _MAX_TOPIC_LENGTH = 500

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: Dict[str, FocusSession] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_session(self, session_id: Optional[str] = None) -> FocusSession:
        """Start a new focus tracking session."""
        sid = str(session_id) if session_id else str(uuid.uuid4())
        session = FocusSession(session_id=sid)
        with self._lock:
            self._sessions[sid] = session
            self._enforce_session_cap()
            return FocusSession(
                session_id=session.session_id,
                started_at=session.started_at,
                ended_at=session.ended_at,
                focus_scores=list(session.focus_scores),
                context_switches=session.context_switches,
                topics=list(session.topics),
                peak_focus=session.peak_focus,
                average_focus=session.average_focus,
            )

    def record_focus_point(
        self,
        session_id: str,
        topic: str,
        focus_score: float,
    ) -> None:
        """Record a focus measurement for a session."""
        focus_score = max(0.0, min(1.0, float(focus_score)))
        topic = str(topic)[:self._MAX_TOPIC_LENGTH]
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.ended_at is not None:
                return
            # Track context switch
            if session.topics and session.topics[-1] != topic:
                session.context_switches += 1
            if topic not in session.topics:
                session.topics.append(topic)
                if len(session.topics) > self._MAX_TOPICS:
                    session.topics = session.topics[-self._MAX_TOPICS:]
            session.focus_scores.append(focus_score)
            if len(session.focus_scores) > self._MAX_FOCUS_SCORES:
                session.focus_scores = session.focus_scores[-self._MAX_FOCUS_SCORES:]
            if focus_score > session.peak_focus:
                session.peak_focus = focus_score

    def end_session(self, session_id: str) -> FocusSession:
        """End a session and compute final stats."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"Session '{session_id}' not found")
            session.ended_at = time.time()
            if session.focus_scores:
                session.average_focus = round(
                    sum(session.focus_scores) / len(session.focus_scores), 4
                )
            # Return a copy
            return FocusSession(
                session_id=session.session_id,
                started_at=session.started_at,
                ended_at=session.ended_at,
                focus_scores=list(session.focus_scores),
                context_switches=session.context_switches,
                topics=list(session.topics),
                peak_focus=session.peak_focus,
                average_focus=session.average_focus,
            )

    def get_active_sessions(self) -> List[FocusSession]:
        """Get all currently active (not ended) sessions."""
        with self._lock:
            return [
                FocusSession(
                    session_id=s.session_id,
                    started_at=s.started_at,
                    ended_at=s.ended_at,
                    focus_scores=list(s.focus_scores),
                    context_switches=s.context_switches,
                    topics=list(s.topics),
                    peak_focus=s.peak_focus,
                    average_focus=s.average_focus,
                )
                for s in self._sessions.values()
                if s.ended_at is None
            ]

    def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """Detailed stats for a session."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"Session '{session_id}' not found")
            # Copy all mutable state inside the lock to avoid TOCTOU races
            scores = list(session.focus_scores)
            sid = session.session_id
            started_at = session.started_at
            ended_at = session.ended_at
            ctx_switches = session.context_switches
            topics = list(session.topics)

        avg = sum(scores) / len(scores) if scores else 0.0
        peak = max(scores) if scores else 0.0
        low = min(scores) if scores else 0.0
        std = self._safe_std(scores)
        duration = (
            (ended_at or time.time()) - started_at
        ) / 60.0

        return {
            "session_id": sid,
            "started_at": started_at,
            "ended_at": ended_at,
            "is_active": ended_at is None,
            "duration_minutes": round(duration, 2),
            "total_focus_points": len(scores),
            "average_focus": round(avg, 4),
            "peak_focus": round(peak, 4),
            "lowest_focus": round(low, 4),
            "std_dev": round(std, 4),
            "context_switches": ctx_switches,
            "unique_topics": len(topics),
            "topics": topics,
        }

    def detect_focus_state(self, session_id: str) -> FocusState:
        """Detect current focus state from last 5 focus scores."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError(f"Session '{session_id}' not found")
            scores = list(session.focus_scores)
            ctx_switches = session.context_switches

        if not scores:
            return FocusState.FOCUSED

        recent = scores[-5:]
        avg = sum(recent) / len(recent)
        std = self._safe_std(recent)

        if avg > 0.85 and std < 0.1:
            return FocusState.DEEP_FOCUS
        if avg > 0.65 and std < 0.2:
            return FocusState.FOCUSED
        if avg > 0.45:
            return FocusState.LIGHT_FOCUS
        if avg > 0.25 or ctx_switches > 3:
            return FocusState.DISTRACTED
        return FocusState.SCATTERED

    def get_focus_recommendations(self, state: FocusState) -> List[str]:
        """Recommendations based on focus state."""
        recs: List[str] = []
        if state == FocusState.DEEP_FOCUS:
            recs.append("Excellent flow state — avoid interruptions.")
            recs.append("Consider tackling the most challenging tasks now.")
        elif state == FocusState.FOCUSED:
            recs.append("Good focus — maintain current pace.")
            recs.append("Stay on the current topic to deepen focus.")
        elif state == FocusState.LIGHT_FOCUS:
            recs.append("Focus is drifting — try removing distractions.")
            recs.append("Consider a short break or change of environment.")
        elif state == FocusState.DISTRACTED:
            recs.append("High distraction — close unnecessary tabs and apps.")
            recs.append("Use a timer to commit to focused intervals.")
            recs.append("Reduce context switching between topics.")
        elif state == FocusState.SCATTERED:
            recs.append("Unable to maintain focus — take a break.")
            recs.append("Consider physical movement or meditation.")
            recs.append("When returning, start with one simple task.")
        return recs

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "sessions": {
                    sid: s._to_dict() for sid, s in self._sessions.items()
                },
            }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FocusOptimizer:
        opt = cls()
        for sid, sdata in data.get("sessions", {}).items():
            opt._sessions[sid] = FocusSession._from_dict(sdata)
        opt._enforce_session_cap()
        return opt

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _enforce_session_cap(self) -> None:
        """Remove oldest completed sessions if over cap.  Caller holds lock."""
        if len(self._sessions) <= self._MAX_SESSIONS:
            return
        completed = [
            (sid, s) for sid, s in self._sessions.items()
            if s.ended_at is not None
        ]
        completed.sort(key=lambda x: x[1].ended_at or 0)
        while len(self._sessions) > self._MAX_SESSIONS and completed:
            sid, _ = completed.pop(0)
            del self._sessions[sid]

    @staticmethod
    def _safe_std(values: List[float]) -> float:
        """Compute std-dev safely (0.0 for fewer than 2 values)."""
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        return math.sqrt(variance)
