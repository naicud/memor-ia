"""Markov-chain action predictor."""

from __future__ import annotations

import threading
import time
from collections import Counter
from typing import Any, Dict, List, Optional

from .types import ActionSequence, Prediction, PredictionType, TransitionMatrix


class ActionPredictor:
    """Predicts the user's next action using a first-order Markov chain.

    Records a stream of discrete actions, builds a transition matrix on the
    fly, and exposes :pymeth:`predict_next` / :pymeth:`predict_sequence` for
    look-ahead predictions.
    """

    def __init__(self, history_window: int = 100) -> None:
        self._lock = threading.RLock()
        self._history_window = max(1, history_window)
        self._history: List[Dict[str, Any]] = []  # [{action, context, timestamp}]
        self._transitions: Dict[str, Counter] = {}  # from -> Counter(to)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_action(self, action: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Record a user action and update the transition matrix."""
        with self._lock:
            entry = {
                "action": action,
                "context": context or {},
                "timestamp": time.time(),
            }
            prev_action = self._history[-1]["action"] if self._history else None
            self._history.append(entry)

            # Trim to window
            if len(self._history) > self._history_window:
                self._history = self._history[-self._history_window:]
                # Rebuild transitions from windowed history
                self._transitions.clear()
                for i in range(1, len(self._history)):
                    prev = self._history[i - 1]["action"]
                    curr = self._history[i]["action"]
                    if prev not in self._transitions:
                        self._transitions[prev] = Counter()
                    self._transitions[prev][curr] += 1
            else:
                # Update transition counts incrementally
                if prev_action is not None:
                    if prev_action not in self._transitions:
                        self._transitions[prev_action] = Counter()
                    self._transitions[prev_action][action] += 1

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict_next(self, top_k: int = 3) -> Prediction:
        """Predict the most likely next action from the current state."""
        top_k = max(1, top_k)
        with self._lock:
            if not self._history:
                return Prediction(
                    prediction_type=PredictionType.NEXT_ACTION,
                    predicted_value="",
                    confidence=0.0,
                    reasoning="No action history available",
                )

            current = self._history[-1]["action"]
            counts = self._transitions.get(current)
            if not counts:
                return Prediction(
                    prediction_type=PredictionType.NEXT_ACTION,
                    predicted_value="",
                    confidence=0.0,
                    reasoning=f"No transitions recorded from '{current}'",
                )

            total = sum(counts.values())
            ranked = counts.most_common(top_k)
            best_action, best_count = ranked[0]
            confidence = best_count / total

            alternatives = [
                (action, count / total) for action, count in ranked[1:]
            ]

            return Prediction(
                prediction_type=PredictionType.NEXT_ACTION,
                predicted_value=best_action,
                confidence=confidence,
                reasoning=(
                    f"Based on {total} transitions from '{current}', "
                    f"'{best_action}' occurred {best_count} times "
                    f"({confidence:.0%} probability)"
                ),
                alternatives=alternatives,
            )

    def predict_sequence(self, length: int = 3) -> List[Prediction]:
        """Predict the next *length* actions by chaining single predictions."""
        with self._lock:
            predictions: List[Prediction] = []
            if not self._history:
                return predictions

            # Work on a *copy* of the last action to walk forward
            current = self._history[-1]["action"]
            cumulative_confidence = 1.0

            for _ in range(length):
                counts = self._transitions.get(current)
                if not counts:
                    break
                total = sum(counts.values())
                best_action, best_count = counts.most_common(1)[0]
                step_confidence = best_count / total
                cumulative_confidence *= step_confidence

                predictions.append(
                    Prediction(
                        prediction_type=PredictionType.NEXT_ACTION,
                        predicted_value=best_action,
                        confidence=cumulative_confidence,
                        reasoning=f"Step {len(predictions)}: '{current}' -> '{best_action}' (p={step_confidence:.2f}, cumulative={cumulative_confidence:.2f})",
                    )
                )
                current = best_action

            return predictions

    # ------------------------------------------------------------------
    # Inspection helpers
    # ------------------------------------------------------------------

    def get_transition_matrix(self) -> TransitionMatrix:
        """Return the current Markov transition matrix as probabilities."""
        with self._lock:
            states = sorted(
                {s for s in self._transitions}
                | {t for cts in self._transitions.values() for t in cts}
            )
            matrix: Dict[str, Dict[str, float]] = {}
            total_transitions = 0
            for src, counts in self._transitions.items():
                total = sum(counts.values())
                total_transitions += total
                matrix[src] = {dst: cnt / total for dst, cnt in counts.items()}

            return TransitionMatrix(
                states=states,
                matrix=matrix,
                total_transitions=total_transitions,
            )

    def get_action_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent action entries."""
        with self._lock:
            return [dict(e) for e in self._history[-limit:]]

    def get_most_common_sequences(
        self, min_length: int = 2, max_length: int = 5
    ) -> List[ActionSequence]:
        """Find repeated sub-sequences in the action history."""
        with self._lock:
            actions = [e["action"] for e in self._history]
            if len(actions) < min_length:
                return []

            seq_counter: Counter = Counter()
            for length in range(min_length, min(max_length, len(actions)) + 1):
                for i in range(len(actions) - length + 1):
                    key = tuple(actions[i : i + length])
                    seq_counter[key] += 1

            results: List[ActionSequence] = []
            for seq, count in seq_counter.most_common():
                if count < 2:
                    continue
                results.append(
                    ActionSequence(
                        actions=list(seq),
                        frequency=count,
                    )
                )
            return results

    def reset(self) -> None:
        """Clear all history and transition data."""
        with self._lock:
            self._history.clear()
            self._transitions.clear()
