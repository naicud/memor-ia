"""CRDT-based conflict resolution for federated memory sync."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VectorClock:
    """Vector clock for distributed ordering of events."""
    clocks: dict[str, int] = field(default_factory=dict)

    def increment(self, node_id: str) -> None:
        self.clocks[node_id] = self.clocks.get(node_id, 0) + 1

    def merge(self, other: VectorClock) -> VectorClock:
        """Merge two vector clocks (element-wise max)."""
        merged = VectorClock(clocks=dict(self.clocks))
        for node_id, count in other.clocks.items():
            merged.clocks[node_id] = max(merged.clocks.get(node_id, 0), count)
        return merged

    def __gt__(self, other: VectorClock) -> bool:
        """True if self happened-after other (dominates)."""
        if not other.clocks:
            return bool(self.clocks)
        all_ge = all(
            self.clocks.get(k, 0) >= v for k, v in other.clocks.items()
        )
        any_gt = any(
            self.clocks.get(k, 0) > v for k, v in other.clocks.items()
        ) or any(
            k not in other.clocks for k in self.clocks
        )
        return all_ge and any_gt

    def __lt__(self, other: VectorClock) -> bool:
        return other > self

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VectorClock):
            return NotImplemented
        return self.clocks == other.clocks

    def is_concurrent(self, other: VectorClock) -> bool:
        """True if neither clock dominates the other."""
        return not (self > other) and not (other > self) and self != other

    def to_dict(self) -> dict:
        return {"clocks": dict(self.clocks)}

    @classmethod
    def from_dict(cls, data: dict) -> VectorClock:
        return cls(clocks=data.get("clocks", {}))


@dataclass
class MemoryVersion:
    """A versioned memory entry for conflict resolution."""
    memory_id: str
    content: str
    namespace: str = "general"
    metadata: dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5
    vector_clock: VectorClock = field(default_factory=VectorClock)
    origin_instance: str = ""
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "memory_id": self.memory_id,
            "content": self.content,
            "namespace": self.namespace,
            "metadata": self.metadata,
            "importance": self.importance,
            "vector_clock": self.vector_clock.to_dict(),
            "origin_instance": self.origin_instance,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MemoryVersion:
        vc = VectorClock.from_dict(data.get("vector_clock", {}))
        return cls(
            memory_id=data["memory_id"],
            content=data.get("content", ""),
            namespace=data.get("namespace", "general"),
            metadata=data.get("metadata", {}),
            importance=data.get("importance", 0.5),
            vector_clock=vc,
            origin_instance=data.get("origin_instance", ""),
            updated_at=data.get("updated_at", time.time()),
        )


class ConflictResolver:
    """Resolves conflicts between local and remote memory versions.

    Strategy: Last-Writer-Wins with vector clock ordering.
    Concurrent writes are merged by combining metadata and keeping
    the version with higher importance.
    """

    def __init__(self, strategy: str = "lww") -> None:
        self._strategy = strategy  # lww | merge | local_first | remote_first
        self._resolution_log: list[dict] = []

    @property
    def strategy(self) -> str:
        return self._strategy

    def resolve(self, local: MemoryVersion, remote: MemoryVersion) -> MemoryVersion:
        """Resolve conflict between local and remote versions."""
        if local.vector_clock > remote.vector_clock:
            result = self._pick(local, "local_dominates")
        elif remote.vector_clock > local.vector_clock:
            result = self._pick(remote, "remote_dominates")
        elif local.vector_clock == remote.vector_clock:
            result = self._pick(local, "identical")
        else:
            result = self._resolve_concurrent(local, remote)

        return result

    def _pick(self, winner: MemoryVersion, reason: str) -> MemoryVersion:
        self._resolution_log.append({
            "memory_id": winner.memory_id,
            "reason": reason,
            "strategy": self._strategy,
            "timestamp": time.time(),
        })
        return winner

    def _resolve_concurrent(self, local: MemoryVersion, remote: MemoryVersion) -> MemoryVersion:
        """Resolve concurrent (neither dominates) writes."""
        if self._strategy == "local_first":
            return self._pick(local, "concurrent_local_first")
        if self._strategy == "remote_first":
            return self._pick(remote, "concurrent_remote_first")
        if self._strategy == "merge":
            return self._merge(local, remote)

        # Default LWW: pick by importance, then by timestamp
        if local.importance > remote.importance:
            return self._pick(local, "concurrent_lww_importance")
        if remote.importance > local.importance:
            return self._pick(remote, "concurrent_lww_importance")
        if local.updated_at >= remote.updated_at:
            return self._pick(local, "concurrent_lww_timestamp")
        return self._pick(remote, "concurrent_lww_timestamp")

    def _merge(self, local: MemoryVersion, remote: MemoryVersion) -> MemoryVersion:
        """Merge concurrent versions: combine metadata, pick best content."""
        merged_metadata = {**local.metadata, **remote.metadata}
        merged_clock = local.vector_clock.merge(remote.vector_clock)

        winner = local if local.importance >= remote.importance else remote
        merged = MemoryVersion(
            memory_id=winner.memory_id,
            content=winner.content,
            namespace=winner.namespace,
            metadata=merged_metadata,
            importance=max(local.importance, remote.importance),
            vector_clock=merged_clock,
            origin_instance=winner.origin_instance,
        )

        self._resolution_log.append({
            "memory_id": merged.memory_id,
            "reason": "concurrent_merged",
            "strategy": "merge",
            "local_origin": local.origin_instance,
            "remote_origin": remote.origin_instance,
            "timestamp": time.time(),
        })
        return merged

    def get_resolution_log(self, limit: int = 50) -> list[dict]:
        return self._resolution_log[-limit:]

    def clear_log(self) -> None:
        self._resolution_log.clear()
