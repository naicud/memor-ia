"""Emotional Intelligence Layer — empathy engine.

Evaluates EmotionReadings against configurable triggers to recommend
empathetic actions, respecting cooldown windows and tracking
effectiveness statistics.
"""

import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from .types import (
    EmpathyAction,
    EmpathyTrigger,
    EmotionReading,
    EmotionType,
)

# Default trigger set
_DEFAULT_TRIGGERS: List[EmpathyTrigger] = [
    EmpathyTrigger(
        trigger_emotion=EmotionType.FRUSTRATION,
        intensity_threshold=0.6,
        action=EmpathyAction.ENCOURAGE,
        message_template="I understand this is frustrating. Let me help you through this.",
        priority=6,
    ),
    EmpathyTrigger(
        trigger_emotion=EmotionType.FRUSTRATION,
        intensity_threshold=0.8,
        action=EmpathyAction.SUGGEST_BREAK,
        message_template="You might benefit from a short break. This is a tough problem.",
        priority=8,
    ),
    EmpathyTrigger(
        trigger_emotion=EmotionType.ANGER,
        intensity_threshold=0.7,
        action=EmpathyAction.ACKNOWLEDGE,
        message_template="I hear your frustration. Let's take a step back and try a different approach.",
        priority=7,
    ),
    EmpathyTrigger(
        trigger_emotion=EmotionType.CONFUSION,
        intensity_threshold=0.5,
        action=EmpathyAction.SIMPLIFY,
        message_template="Let me explain this differently to make it clearer.",
        priority=5,
    ),
    EmpathyTrigger(
        trigger_emotion=EmotionType.JOY,
        intensity_threshold=0.7,
        action=EmpathyAction.CELEBRATE,
        message_template="Great progress! You're doing well.",
        priority=4,
    ),
    EmpathyTrigger(
        trigger_emotion=EmotionType.SATISFACTION,
        intensity_threshold=0.6,
        action=EmpathyAction.CELEBRATE,
        message_template="Excellent work! That's a solid solution.",
        priority=4,
    ),
    EmpathyTrigger(
        trigger_emotion=EmotionType.FATIGUE,
        intensity_threshold=0.7,
        action=EmpathyAction.SUGGEST_BREAK,
        message_template="You've been working hard. Consider taking a break.",
        priority=7,
    ),
    EmpathyTrigger(
        trigger_emotion=EmotionType.ANXIETY,
        intensity_threshold=0.6,
        action=EmpathyAction.ENCOURAGE,
        message_template="Don't worry, we'll work through this step by step.",
        priority=5,
    ),
    EmpathyTrigger(
        trigger_emotion=EmotionType.BOREDOM,
        intensity_threshold=0.5,
        action=EmpathyAction.REDIRECT,
        message_template="Let me suggest something more interesting to work on.",
        priority=3,
    ),
]


class EmpathyEngine:
    """Rule-based empathy engine with cooldown and effectiveness tracking."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._triggers: List[EmpathyTrigger] = list(_DEFAULT_TRIGGERS)
        self._max_triggers: int = 100
        # cooldown: (emotion.value, action.value) -> last_fired_timestamp
        self._cooldowns: Dict[Tuple[str, str], float] = {}
        # effectiveness: action.value -> {"accepted": int, "rejected": int}
        self._effectiveness: Dict[str, Dict[str, int]] = {}

    # ── evaluation ───────────────────────────────────────────────────

    def evaluate(self, reading: EmotionReading) -> List[EmpathyTrigger]:
        """Return all triggers that fire for the given reading."""
        with self._lock:
            now = time.time()
            fired: List[EmpathyTrigger] = []
            for t in self._triggers:
                if (
                    reading.emotion == t.trigger_emotion
                    and reading.intensity >= t.intensity_threshold
                ):
                    key = (t.trigger_emotion.value, t.action.value)
                    last = self._cooldowns.get(key, 0.0)
                    if now - last >= t.cooldown_seconds:
                        fired.append(t)
            fired.sort(key=lambda t: t.priority, reverse=True)
            return fired

    def get_response(
        self, reading: EmotionReading
    ) -> Optional[Dict[str, Any]]:
        """Return the highest-priority empathetic response, or None."""
        with self._lock:
            fired = self.evaluate(reading)
            if not fired:
                return None
            best = fired[0]
            key = (best.trigger_emotion.value, best.action.value)
            self._cooldowns[key] = time.time()
            return {
                "action": best.action.value,
                "message": best.message_template,
                "priority": best.priority,
                "trigger_emotion": best.trigger_emotion.value,
            }

    def should_intervene(self, reading: EmotionReading) -> bool:
        """Quick check whether any trigger would fire."""
        with self._lock:
            return len(self.evaluate(reading)) > 0

    # ── trigger management ───────────────────────────────────────────

    def add_trigger(self, trigger: EmpathyTrigger) -> None:
        """Add a custom empathy trigger."""
        with self._lock:
            self._triggers.append(trigger)
            if len(self._triggers) > self._max_triggers:
                self._triggers = self._triggers[-self._max_triggers:]

    def remove_trigger(
        self, emotion: EmotionType, action: EmpathyAction
    ) -> bool:
        """Remove the first trigger matching emotion+action. Return True if found."""
        with self._lock:
            for i, t in enumerate(self._triggers):
                if t.trigger_emotion == emotion and t.action == action:
                    self._triggers.pop(i)
                    return True
            return False

    def get_all_triggers(self) -> List[Dict[str, Any]]:
        """Return serializable list of all configured triggers."""
        with self._lock:
            return [t._to_dict() for t in self._triggers]

    # ── effectiveness tracking ───────────────────────────────────────

    def record_response(
        self,
        emotion: EmotionType,
        action: EmpathyAction,
        accepted: bool,
    ) -> None:
        """Record whether the user accepted or rejected a response."""
        with self._lock:
            key = action.value
            stats = self._effectiveness.setdefault(
                key, {"accepted": 0, "rejected": 0}
            )
            if accepted:
                stats["accepted"] += 1
            else:
                stats["rejected"] += 1

    def get_effectiveness_stats(self) -> Dict[str, Any]:
        """Return acceptance/rejection counts per action."""
        with self._lock:
            return {k: dict(v) for k, v in self._effectiveness.items()}
