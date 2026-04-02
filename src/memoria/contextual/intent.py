"""Contextual Intelligence Engine — intent inference."""

import threading
import time
from typing import Optional

from .types import InferredIntent, IntentConfidence


class IntentInference:
    """Infers user's high-level intent from cross-product behavior patterns."""

    def __init__(
        self,
        max_intents: int = 500,
        max_action_window: int = 50,
    ) -> None:
        self._lock = threading.RLock()
        self._action_window: list[tuple[str, str, float]] = []
        self._intent_history: list[InferredIntent] = []
        self._intent_patterns: dict[str, tuple[list[str], list[str]]] = {}
        self._max_intents = max_intents
        self._max_window = max_action_window

    def register_intent_pattern(
        self,
        intent_name: str,
        keywords: list[str],
        products: Optional[list[str]] = None,
    ) -> None:
        """Register an intent pattern for future inference."""
        with self._lock:
            self._intent_patterns[intent_name] = (
                list(keywords),
                list(products) if products else [],
            )

    def observe_action(
        self,
        product_id: str,
        action: str,
        timestamp: Optional[float] = None,
    ) -> Optional[InferredIntent]:
        """Observe an action and attempt to infer intent."""
        ts = timestamp if timestamp is not None else time.time()

        with self._lock:
            self._action_window.append((product_id, action, ts))
            if len(self._action_window) > self._max_window:
                self._action_window = self._action_window[-self._max_window:]

            if not self._intent_patterns:
                return None

            best_intent: Optional[InferredIntent] = None
            best_confidence = 0.0

            window_text = " ".join(
                act.lower() for _, act, _ in self._action_window
            )
            window_products = {prod for prod, _, _ in self._action_window}

            for intent_name, (keywords, products) in self._intent_patterns.items():
                if not keywords:
                    continue

                matched_kw: list[str] = []
                unmatched_kw: list[str] = []
                for kw in keywords:
                    if kw.lower() in window_text:
                        matched_kw.append(kw)
                    else:
                        unmatched_kw.append(kw)

                confidence = len(matched_kw) / len(keywords)
                confidence = max(0.0, min(1.0, confidence))

                if confidence <= 0.3:
                    continue

                if confidence > best_confidence:
                    level = self._confidence_level(confidence)
                    best_confidence = confidence
                    best_intent = InferredIntent(
                        intent=intent_name,
                        confidence=confidence,
                        confidence_level=level,
                        supporting_evidence=list(matched_kw),
                        related_products=products if products else sorted(window_products),
                        predicted_next_actions=list(unmatched_kw),
                        timestamp=ts,
                    )

            if best_intent is not None:
                self._intent_history.append(best_intent)
                if len(self._intent_history) > self._max_intents:
                    self._intent_history = self._intent_history[-self._max_intents:]

            return best_intent

    def get_current_intent(self) -> Optional[InferredIntent]:
        """Get most recently inferred intent."""
        with self._lock:
            return self._intent_history[-1] if self._intent_history else None

    def get_intent_history(self, limit: int = 20) -> list[InferredIntent]:
        with self._lock:
            return list(self._intent_history[-limit:])

    def get_intent_confidence_trend(self) -> str:
        """'increasing', 'stable', or 'decreasing' based on last 5 intents."""
        with self._lock:
            recent = self._intent_history[-5:]
            if len(recent) < 2:
                return "stable"
            confidences = [i.confidence for i in recent]
            diff = confidences[-1] - confidences[0]
            if diff > 0.05:
                return "increasing"
            if diff < -0.05:
                return "decreasing"
            return "stable"

    def clear_window(self) -> None:
        """Clear the action window."""
        with self._lock:
            self._action_window.clear()

    @staticmethod
    def _confidence_level(confidence: float) -> IntentConfidence:
        if confidence > 0.7:
            return IntentConfidence.HIGH
        if confidence >= 0.3:
            return IntentConfidence.MEDIUM
        return IntentConfidence.LOW
