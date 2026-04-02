from __future__ import annotations

import threading

from .types import ConsolidationAction, DreamJournalEntry


class DreamJournal:
    """Immutable, append-only log of dream consolidation cycles."""

    def __init__(self, max_entries: int = 100):
        self._entries: list[DreamJournalEntry] = []
        self._max = max_entries
        self._lock = threading.RLock()

    def record(self, entry: DreamJournalEntry) -> None:
        """Append a journal entry. Rotates oldest if max exceeded."""
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max:
                self._entries = self._entries[-self._max :]

    def get_entries(
        self, limit: int = 10, since: float = 0.0
    ) -> list[DreamJournalEntry]:
        """Get journal entries, newest first. Optionally filter by started_at >= since."""
        with self._lock:
            if limit <= 0:
                return []
            filtered = self._entries
            if since > 0:
                filtered = [e for e in filtered if e.started_at >= since]
            return list(reversed(filtered[-limit:]))

    def get_cycle(self, cycle_id: str) -> DreamJournalEntry | None:
        """Get a specific dream cycle's journal entry."""
        with self._lock:
            for entry in self._entries:
                if entry.cycle_id == cycle_id:
                    return entry
            return None

    def stats(self) -> dict:
        """Aggregate stats across all journal entries."""
        with self._lock:
            if not self._entries:
                return {
                    "total_cycles": 0,
                    "total_promoted": 0,
                    "total_compressed": 0,
                    "total_forgotten": 0,
                    "total_insights": 0,
                    "avg_memories_per_cycle": 0.0,
                    "avg_duration": 0.0,
                }

            total_promoted = 0
            total_compressed = 0
            total_forgotten = 0
            total_insights = 0
            total_memories = 0
            total_duration = 0.0

            for entry in self._entries:
                total_memories += entry.memories_scanned
                total_insights += len(entry.insights)
                total_duration += entry.completed_at - entry.started_at

                for d in entry.decisions:
                    if d.action == ConsolidationAction.PROMOTE:
                        total_promoted += 1
                    elif d.action == ConsolidationAction.COMPRESS:
                        total_compressed += 1
                    elif d.action == ConsolidationAction.FORGET:
                        total_forgotten += 1

            n = len(self._entries)
            return {
                "total_cycles": n,
                "total_promoted": total_promoted,
                "total_compressed": total_compressed,
                "total_forgotten": total_forgotten,
                "total_insights": total_insights,
                "avg_memories_per_cycle": total_memories / n,
                "avg_duration": total_duration / n,
            }

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._entries.clear()
