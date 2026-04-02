"""Selective namespace sync engine for federation."""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from memoria.federation.conflict import ConflictResolver, MemoryVersion


@dataclass
class SyncResult:
    """Result of a sync operation."""
    sync_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    peer_id: str = ""
    namespace: str = ""
    direction: str = ""  # push | pull | bidirectional
    memories_sent: int = 0
    memories_received: int = 0
    conflicts_resolved: int = 0
    errors: list[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    status: str = "pending"  # pending | in_progress | completed | failed

    def to_dict(self) -> dict:
        return asdict(self)


class SyncEngine:
    """Manages selective namespace sync between federation peers.

    Operates on MemoryVersion objects with vector clocks for
    conflict-free replication.
    """

    def __init__(self, instance_id: str, resolver: ConflictResolver | None = None) -> None:
        self._instance_id = instance_id
        self._resolver = resolver or ConflictResolver()
        self._local_store: dict[str, dict[str, MemoryVersion]] = {}
        self._sync_history: list[SyncResult] = []

    @property
    def instance_id(self) -> str:
        return self._instance_id

    def add_local(self, memory: MemoryVersion) -> None:
        """Add or update a memory in the local store."""
        memory.vector_clock.increment(self._instance_id)
        memory.origin_instance = self._instance_id
        ns = memory.namespace
        self._local_store.setdefault(ns, {})[memory.memory_id] = memory

    def get_local(self, namespace: str) -> list[MemoryVersion]:
        """Get all local memories in a namespace."""
        return list(self._local_store.get(namespace, {}).values())

    def get_local_memory(self, memory_id: str, namespace: str = "general") -> MemoryVersion | None:
        return self._local_store.get(namespace, {}).get(memory_id)

    def prepare_push(self, namespace: str,
                     filter_fn: Any | None = None) -> list[dict]:
        """Prepare memories for pushing to a peer."""
        memories = self.get_local(namespace)
        if filter_fn:
            memories = [m for m in memories if filter_fn(m)]
        return [m.to_dict() for m in memories]

    def receive_pull(self, namespace: str,
                     remote_memories: list[dict],
                     peer_id: str = "") -> SyncResult:
        """Receive memories from a peer (pull direction)."""
        result = SyncResult(
            peer_id=peer_id,
            namespace=namespace,
            direction="pull",
            status="in_progress",
        )

        for remote_data in remote_memories:
            try:
                remote = MemoryVersion.from_dict(remote_data)
                local = self._local_store.get(namespace, {}).get(remote.memory_id)

                if local is None:
                    remote.vector_clock.increment(self._instance_id)
                    self._local_store.setdefault(namespace, {})[remote.memory_id] = remote
                    result.memories_received += 1
                else:
                    resolved = self._resolver.resolve(local, remote)
                    resolved.vector_clock.increment(self._instance_id)
                    self._local_store[namespace][resolved.memory_id] = resolved
                    if resolved is not local:
                        result.memories_received += 1
                    result.conflicts_resolved += 1
            except Exception as e:
                result.errors.append(str(e))

        result.status = "completed" if not result.errors else "failed"
        result.completed_at = time.time()
        self._sync_history.append(result)
        return result

    def sync_bidirectional(self, namespace: str,
                           remote_memories: list[dict],
                           peer_id: str = "") -> tuple[SyncResult, list[dict]]:
        """Bidirectional sync: receive remote + prepare local for push.

        Returns (sync_result, memories_to_send_to_peer).
        """
        pull_result = self.receive_pull(namespace, remote_memories, peer_id)
        to_push = self.prepare_push(namespace)

        pull_result.direction = "bidirectional"
        pull_result.memories_sent = len(to_push)

        return pull_result, to_push

    def get_sync_history(self, limit: int = 20) -> list[dict]:
        return [s.to_dict() for s in self._sync_history[-limit:]]

    def get_namespace_stats(self, namespace: str) -> dict:
        memories = self._local_store.get(namespace, {})
        return {
            "namespace": namespace,
            "memory_count": len(memories),
            "origins": list(set(m.origin_instance for m in memories.values())),
        }

    def list_synced_namespaces(self) -> list[str]:
        return list(self._local_store.keys())

    def status(self) -> dict:
        total_memories = sum(len(ns) for ns in self._local_store.values())
        return {
            "instance_id": self._instance_id,
            "namespaces": len(self._local_store),
            "total_memories": total_memories,
            "total_syncs": len(self._sync_history),
        }
