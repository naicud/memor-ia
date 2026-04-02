"""Cognitive Load Management — overload prevention."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List

from .types import CognitiveSnapshot, OverloadAlert, OverloadSignal


@dataclass
class _ErrorEvent:
    error_type: str
    timestamp: float


@dataclass
class _ContextSwitch:
    from_topic: str
    to_topic: str
    timestamp: float


class OverloadPrevention:
    """Detects information overload and provides prevention strategies."""

    _MAX_HISTORY = 1000
    _MAX_ERROR_EVENTS = 5000
    _MAX_CONTEXT_SWITCHES = 5000

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._error_events: List[_ErrorEvent] = []
        self._context_switches: List[_ContextSwitch] = []
        self._overload_history: List[OverloadAlert] = []
        self._complexity_history: List[float] = []
        self._action_log: List[tuple] = []  # (action, timestamp)
        self._last_break_time: float = time.time()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_overload(self, snapshot: CognitiveSnapshot) -> OverloadAlert:
        """Analyse *snapshot* for overload signals."""
        with self._lock:
            now = time.time()
            signals: List[OverloadSignal] = []

            # RAPID_SWITCHING: >5 context switches in 10 minutes
            recent_switches = [
                cs for cs in self._context_switches
                if cs.timestamp >= now - 600
            ]
            if len(recent_switches) > 5:
                signals.append(OverloadSignal.RAPID_SWITCHING)

            # INFO_VOLUME: load_score > 0.7 and active_topics > 5
            if snapshot.load_score > 0.7 and snapshot.active_topics > 5:
                signals.append(OverloadSignal.INFO_VOLUME)

            # COMPLEXITY_SPIKE: latest value >0.3 above historical baseline
            if len(self._complexity_history) >= 2:
                recent = self._complexity_history[-1]
                older_vals = list(self._complexity_history[:-1])
                if older_vals:
                    baseline = sum(older_vals) / len(older_vals)
                    if recent - baseline > 0.3:
                        signals.append(OverloadSignal.COMPLEXITY_SPIKE)

            # ERROR_RATE: >3 errors in 5 minutes
            recent_errors = [
                e for e in self._error_events
                if e.timestamp >= now - 300
            ]
            if len(recent_errors) > 3:
                signals.append(OverloadSignal.ERROR_RATE)

            # REPETITION: same action recorded >3 times in 5 minutes
            recent_actions = [
                a for a in self._action_log
                if a[1] >= now - 300
            ]
            if recent_actions:
                from collections import Counter
                counts = Counter(a[0] for a in recent_actions)
                if any(c > 3 for c in counts.values()):
                    signals.append(OverloadSignal.REPETITION)

            # FATIGUE: session > 120 min without break
            session_mins = snapshot.session_duration_minutes
            minutes_since_break = (now - self._last_break_time) / 60.0
            if session_mins > 120 and minutes_since_break > 120:
                signals.append(OverloadSignal.FATIGUE)

            severity = min(1.0, len(signals) / 6.0)
            cooldown = math.ceil(severity * 15) if severity > 0 else 0
            is_overloaded = len(signals) > 0

            recommendation = ""
            if is_overloaded:
                recommendation = self._build_recommendation(signals)

            alert = OverloadAlert(
                is_overloaded=is_overloaded,
                signals=list(signals),
                severity=round(severity, 4),
                recommendation=recommendation,
                cooldown_minutes=cooldown,
                timestamp=now,
            )
            self._overload_history.append(alert)
            if len(self._overload_history) > self._MAX_HISTORY:
                self._overload_history = self._overload_history[-self._MAX_HISTORY:]

            return alert

    def add_error_event(self, error_type: str = "generic") -> None:
        """Track an error occurrence."""
        with self._lock:
            self._error_events.append(
                _ErrorEvent(error_type=str(error_type), timestamp=time.time())
            )
            if len(self._error_events) > self._MAX_ERROR_EVENTS:
                self._error_events = self._error_events[-self._MAX_ERROR_EVENTS:]

    def add_context_switch(self, from_topic: str, to_topic: str) -> None:
        """Track a context switch between topics."""
        with self._lock:
            self._context_switches.append(
                _ContextSwitch(
                    from_topic=str(from_topic),
                    to_topic=str(to_topic),
                    timestamp=time.time(),
                )
            )
            if len(self._context_switches) > self._MAX_CONTEXT_SWITCHES:
                self._context_switches = self._context_switches[-self._MAX_CONTEXT_SWITCHES:]

    def record_action(self, action: str) -> None:
        """Record a user action for repetition detection."""
        with self._lock:
            self._action_log.append((str(action), time.time()))
            if len(self._action_log) > self._MAX_ERROR_EVENTS:
                self._action_log = self._action_log[-self._MAX_ERROR_EVENTS:]

    def record_complexity(self, complexity: float) -> None:
        """Record a complexity measurement for spike detection."""
        with self._lock:
            self._complexity_history.append(
                max(0.0, min(1.0, float(complexity)))
            )
            if len(self._complexity_history) > self._MAX_ERROR_EVENTS:
                self._complexity_history = self._complexity_history[-self._MAX_ERROR_EVENTS:]

    def record_break(self) -> None:
        """Record that the user took a break (resets fatigue timer)."""
        with self._lock:
            self._last_break_time = time.time()

    def get_recommendations(self, alert: OverloadAlert) -> List[str]:
        """Generate specific recommendations based on overload signals."""
        recs: List[str] = []
        signals = list(alert.signals)
        for sig in signals:
            if sig == OverloadSignal.RAPID_SWITCHING:
                recs.append(
                    "Reduce context switching — focus on one topic at a time."
                )
            elif sig == OverloadSignal.INFO_VOLUME:
                recs.append(
                    "Information overload detected — consider summarising or prioritising."
                )
            elif sig == OverloadSignal.COMPLEXITY_SPIKE:
                recs.append(
                    "Complexity spike — break the problem into smaller parts."
                )
            elif sig == OverloadSignal.ERROR_RATE:
                recs.append(
                    "Rising error rate — slow down and review recent work."
                )
            elif sig == OverloadSignal.REPETITION:
                recs.append(
                    "Repetitive actions detected — consider automating or changing approach."
                )
            elif sig == OverloadSignal.FATIGUE:
                recs.append(
                    "Session fatigue — take a break to restore cognitive capacity."
                )
        if alert.cooldown_minutes > 0:
            recs.append(
                f"Suggested cooldown: {alert.cooldown_minutes} minutes."
            )
        return recs

    def get_overload_history(self) -> List[OverloadAlert]:
        """Return past overload alerts."""
        with self._lock:
            return list(self._overload_history)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "error_events": [
                    {"error_type": e.error_type, "timestamp": e.timestamp}
                    for e in self._error_events
                ],
                "context_switches": [
                    {
                        "from_topic": cs.from_topic,
                        "to_topic": cs.to_topic,
                        "timestamp": cs.timestamp,
                    }
                    for cs in self._context_switches
                ],
                "overload_history": [
                    a._to_dict() for a in self._overload_history
                ],
                "complexity_history": list(self._complexity_history),
                "action_log": [
                    {"action": a[0], "timestamp": a[1]}
                    for a in self._action_log
                ],
                "last_break_time": self._last_break_time,
            }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> OverloadPrevention:
        op = cls()
        for e in data.get("error_events", []):
            op._error_events.append(
                _ErrorEvent(error_type=e["error_type"], timestamp=e["timestamp"])
            )
        for cs in data.get("context_switches", []):
            op._context_switches.append(
                _ContextSwitch(
                    from_topic=cs["from_topic"],
                    to_topic=cs["to_topic"],
                    timestamp=cs["timestamp"],
                )
            )
        for a in data.get("overload_history", []):
            op._overload_history.append(OverloadAlert._from_dict(a))
        op._complexity_history = list(data.get("complexity_history", []))
        for a in data.get("action_log", []):
            op._action_log.append((a["action"], a["timestamp"]))
        op._last_break_time = data.get("last_break_time", time.time())
        # enforce caps
        if len(op._error_events) > cls._MAX_ERROR_EVENTS:
            op._error_events = op._error_events[-cls._MAX_ERROR_EVENTS:]
        if len(op._context_switches) > cls._MAX_CONTEXT_SWITCHES:
            op._context_switches = op._context_switches[-cls._MAX_CONTEXT_SWITCHES:]
        if len(op._overload_history) > cls._MAX_HISTORY:
            op._overload_history = op._overload_history[-cls._MAX_HISTORY:]
        return op

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _build_recommendation(signals: List[OverloadSignal]) -> str:
        parts: List[str] = []
        if OverloadSignal.RAPID_SWITCHING in signals:
            parts.append("reduce context switching")
        if OverloadSignal.INFO_VOLUME in signals:
            parts.append("limit information intake")
        if OverloadSignal.COMPLEXITY_SPIKE in signals:
            parts.append("simplify current task")
        if OverloadSignal.ERROR_RATE in signals:
            parts.append("slow down")
        if OverloadSignal.REPETITION in signals:
            parts.append("change approach")
        if OverloadSignal.FATIGUE in signals:
            parts.append("take a break")
        return "Consider: " + ", ".join(parts) + "." if parts else ""
