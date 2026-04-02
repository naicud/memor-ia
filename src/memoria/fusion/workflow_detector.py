"""Cross-product workflow detection from action sequences."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Optional

from .types import DetectedWorkflow, WorkflowType


class WorkflowDetector:
    """Detects cross-product workflows from action sequences."""

    def __init__(
        self, max_sequences: int = 10000, max_workflows: int = 100
    ) -> None:
        self._lock = threading.RLock()
        self._action_sequences: list[tuple[str, float]] = []  # (action_key, ts)
        self._detected_workflows: dict[str, DetectedWorkflow] = {}
        self._max_sequences = max(1, max_sequences)
        self._max_workflows = max(1, max_workflows)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_action(
        self,
        product_id: str,
        action: str,
        timestamp: Optional[float] = None,
    ) -> None:
        """Record a product action as ``'product_id:action'``."""
        with self._lock:
            ts = timestamp if timestamp is not None else time.time()
            key = f"{product_id}:{action}"
            self._action_sequences.append((key, ts))

            if len(self._action_sequences) > self._max_sequences:
                self._action_sequences = self._action_sequences[
                    -self._max_sequences :
                ]

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect_workflows(
        self,
        min_frequency: int = 3,
        min_length: int = 2,
        max_length: int = 6,
    ) -> list[DetectedWorkflow]:
        """Detect repeated action sequences across products.

        Uses a sliding window to find repeated sub-sequences.
        ``RECURRING`` if seen 5+ times, otherwise ``SEQUENTIAL``.
        ``confidence = min(1.0, frequency / 10)``.
        """
        with self._lock:
            min_frequency = max(1, min_frequency)
            min_length = max(2, min_length)
            max_length = max(min_length, max_length)

            actions = [a for a, _ in self._action_sequences]
            timestamps = [t for _, t in self._action_sequences]

            if len(actions) < min_length:
                return list(self._detected_workflows.values())

            # Count sub-sequence occurrences
            seq_counts: dict[tuple[str, ...], list[int]] = {}
            for length in range(min_length, max_length + 1):
                for i in range(len(actions) - length + 1):
                    seq = tuple(actions[i : i + length])
                    if seq not in seq_counts:
                        seq_counts[seq] = []
                    seq_counts[seq].append(i)

            # Build workflows from frequent sequences
            new_workflows: dict[str, DetectedWorkflow] = {}
            for seq, indices in seq_counts.items():
                if len(indices) < min_frequency:
                    continue

                # Deduplicate: skip sub-sequences of already-found longer ones
                seq_key = "|".join(seq)
                frequency = len(indices)
                wtype = (
                    WorkflowType.RECURRING
                    if frequency >= 5
                    else WorkflowType.SEQUENTIAL
                )

                # Compute avg duration
                durations: list[float] = []
                for idx in indices:
                    end_idx = idx + len(seq) - 1
                    if end_idx < len(timestamps):
                        dur = timestamps[end_idx] - timestamps[idx]
                        if dur >= 0:
                            durations.append(dur)
                avg_dur = sum(durations) / len(durations) if durations else 0.0

                last_idx = indices[-1]
                last_end = last_idx + len(seq) - 1
                last_seen = (
                    timestamps[last_end] if last_end < len(timestamps) else 0.0
                )

                wf_id = uuid.uuid4().hex[:12]
                name = " → ".join(seq)
                new_workflows[seq_key] = DetectedWorkflow(
                    workflow_id=wf_id,
                    name=name,
                    workflow_type=wtype,
                    steps=list(seq),
                    frequency=frequency,
                    avg_duration_seconds=avg_dur,
                    last_seen=last_seen,
                    confidence=min(1.0, frequency / 10.0),
                )

            # Merge with existing, enforce cap
            self._detected_workflows.update(new_workflows)
            if len(self._detected_workflows) > self._max_workflows:
                # Keep highest-frequency workflows
                ranked = sorted(
                    self._detected_workflows.items(),
                    key=lambda kv: kv[1].frequency,
                    reverse=True,
                )
                self._detected_workflows = dict(ranked[: self._max_workflows])

            return list(self._detected_workflows.values())

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_workflows(
        self, product_id: Optional[str] = None
    ) -> list[DetectedWorkflow]:
        """Get detected workflows, optionally filtered by product."""
        with self._lock:
            if product_id is None:
                return list(self._detected_workflows.values())
            return [
                wf
                for wf in self._detected_workflows.values()
                if any(step.startswith(f"{product_id}:") for step in wf.steps)
            ]

    def get_active_workflow(
        self, recent_actions: list[str]
    ) -> Optional[DetectedWorkflow]:
        """Find if the user is currently in a known workflow.

        Matches by prefix: if ``recent_actions[-N:]`` matches
        ``workflow.steps[:N]`` for some workflow.
        """
        with self._lock:
            if not recent_actions:
                return None

            best: Optional[DetectedWorkflow] = None
            best_match_len = 0

            for wf in self._detected_workflows.values():
                steps = wf.steps
                for n in range(1, len(steps)):
                    if n > len(recent_actions):
                        break
                    if recent_actions[-n:] == steps[:n]:
                        if n > best_match_len:
                            best = wf
                            best_match_len = n

            return best

    def predict_next_step(
        self, recent_actions: list[str]
    ) -> Optional[str]:
        """If the user is in a known workflow, predict the next step."""
        with self._lock:
            if not recent_actions:
                return None

            wf = self.get_active_workflow(recent_actions)
            if wf is None:
                return None

            steps = wf.steps
            for n in range(len(steps) - 1, 0, -1):
                if n <= len(recent_actions) and recent_actions[-n:] == steps[:n]:
                    if n < len(steps):
                        return steps[n]
            return None

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def get_workflow_summary(self) -> dict:
        """Summary: total workflows, by type, most frequent, avg length."""
        with self._lock:
            workflows = list(self._detected_workflows.values())
            if not workflows:
                return {
                    "total_workflows": 0,
                    "by_type": {},
                    "most_frequent": None,
                    "avg_length": 0.0,
                }

            by_type: dict[str, int] = {}
            for wf in workflows:
                t = wf.workflow_type.value
                by_type[t] = by_type.get(t, 0) + 1

            most_frequent = max(workflows, key=lambda w: w.frequency)
            avg_length = sum(len(wf.steps) for wf in workflows) / len(workflows)

            return {
                "total_workflows": len(workflows),
                "by_type": by_type,
                "most_frequent": most_frequent.name,
                "avg_length": avg_length,
            }
