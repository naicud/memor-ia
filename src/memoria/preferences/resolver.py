"""Conflict resolution for contradictory preferences."""
from __future__ import annotations

import threading

from .types import Preference, PreferenceConflict

_MAX_CONFLICTS = 500


class ConflictResolver:
    """Resolves contradictions between preferences."""

    def __init__(self) -> None:
        self._conflicts: list[PreferenceConflict] = []
        self._lock = threading.RLock()

    def detect_conflict(
        self, existing: Preference, new: Preference,
    ) -> PreferenceConflict | None:
        """Check if two preferences conflict (same category+key, different value)."""
        if existing is None or new is None:
            return None
        if (
            existing.category == new.category
            and existing.key == new.key
            and existing.value != new.value
        ):
            conflict = PreferenceConflict(
                preference_a=existing,
                preference_b=new,
            )
            with self._lock:
                self._conflicts.append(conflict)
                if len(self._conflicts) > _MAX_CONFLICTS:
                    # Evict resolved conflicts first, then oldest
                    self._conflicts = [c for c in self._conflicts if not c.resolution]
                    if len(self._conflicts) > _MAX_CONFLICTS:
                        self._conflicts = self._conflicts[-_MAX_CONFLICTS:]
            return conflict
        return None

    def resolve(
        self, conflict: PreferenceConflict, strategy: str = "confidence",
    ) -> PreferenceConflict:
        """Resolve a conflict using strategy: 'confidence', 'recency', 'frequency', 'manual'."""
        with self._lock:
            a = conflict.preference_a
            b = conflict.preference_b

            if strategy == "confidence":
                if a.confidence >= b.confidence:
                    conflict.resolution = "a_wins"
                    conflict.resolution_reason = (
                        f"higher confidence: {a.confidence:.2f} vs {b.confidence:.2f}"
                    )
                else:
                    conflict.resolution = "b_wins"
                    conflict.resolution_reason = (
                        f"higher confidence: {b.confidence:.2f} vs {a.confidence:.2f}"
                    )

            elif strategy == "recency":
                if a.updated_at >= b.updated_at:
                    conflict.resolution = "a_wins"
                    conflict.resolution_reason = (
                        f"more recent: {a.updated_at} vs {b.updated_at}"
                    )
                else:
                    conflict.resolution = "b_wins"
                    conflict.resolution_reason = (
                        f"more recent: {b.updated_at} vs {a.updated_at}"
                    )

            elif strategy == "frequency":
                if a.observation_count >= b.observation_count:
                    conflict.resolution = "a_wins"
                    conflict.resolution_reason = (
                        f"more observations: {a.observation_count} vs {b.observation_count}"
                    )
                else:
                    conflict.resolution = "b_wins"
                    conflict.resolution_reason = (
                        f"more observations: {b.observation_count} vs {a.observation_count}"
                    )

            elif strategy == "manual":
                conflict.resolution = "unresolved"
                conflict.resolution_reason = "awaiting manual resolution"

            else:
                conflict.resolution = "unresolved"
                conflict.resolution_reason = f"unknown strategy: {strategy}"

            return conflict

    def get_conflicts(self, user_id: str = "") -> list[PreferenceConflict]:
        """Get all unresolved conflicts, optionally filtered by user."""
        with self._lock:
            results: list[PreferenceConflict] = []
            for c in self._conflicts:
                if c.resolution and c.resolution != "unresolved":
                    continue
                if user_id and c.preference_a.user_id != user_id and c.preference_b.user_id != user_id:
                    continue
                results.append(c)
            return results

    def get_resolved(self) -> list[PreferenceConflict]:
        """Get all resolved conflicts."""
        with self._lock:
            return [
                c for c in self._conflicts
                if c.resolution and c.resolution != "unresolved"
            ]
