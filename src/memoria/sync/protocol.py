"""Core sync protocol: push, pull, bidirectional sync with state tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from memoria.namespace.store import SharedMemoryStore

from .conflicts import SyncConflictResolver
from .transport import SyncTransport

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SyncState:
    """Current state of the sync protocol."""

    last_sync_at: str  # ISO-8601 or ""
    sync_count: int
    pending_changes: int


@dataclass
class SyncResult:
    """Outcome of a sync operation."""

    pushed: int
    pulled: int
    conflicts: int
    resolved: int
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SyncProtocol
# ---------------------------------------------------------------------------


class SyncProtocol:
    """Orchestrates local ↔ remote synchronisation."""

    def __init__(
        self,
        local_store: SharedMemoryStore,
        transport: SyncTransport | None = None,
    ) -> None:
        self._store = local_store
        self._transport = transport
        self._resolver = SyncConflictResolver()
        self._last_sync_at: str = ""
        self._sync_count: int = 0
        self._change_log: list[dict] = []
        self._max_change_log: int = 50_000

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _all_memories(self, namespace: str | None = None) -> list[dict]:
        """Return all memories, optionally filtered by namespace."""
        if namespace:
            return self._store.list_by_namespace(namespace, recursive=True)
        memories: list[dict] = []
        for ns in self._store.namespaces():
            memories.extend(self._store.list_by_namespace(ns))
        return memories

    # -- public API --------------------------------------------------------

    def push(self, namespace: str | None = None) -> SyncResult:
        """Push local changes to the remote via the configured transport."""
        if self._transport is None:
            return SyncResult(pushed=0, pulled=0, conflicts=0, resolved=0,
                              errors=["no transport configured"])

        memories = self._all_memories(namespace)
        result = self._transport.send(memories, namespace)
        pushed = result.get("accepted", 0)
        errors = result.get("errors", [])

        self._last_sync_at = self._now_iso()
        self._sync_count += 1
        # Clear change log for pushed items
        if namespace:
            self._change_log = [
                c for c in self._change_log if c.get("namespace") != namespace
            ]
        else:
            self._change_log.clear()

        return SyncResult(pushed=pushed, pulled=0, conflicts=0, resolved=0, errors=errors)

    def pull(self, namespace: str | None = None) -> SyncResult:
        """Pull remote changes into the local store."""
        if self._transport is None:
            return SyncResult(pushed=0, pulled=0, conflicts=0, resolved=0,
                              errors=["no transport configured"])

        since = self._last_sync_at or None
        remote_memories = self._transport.receive(namespace, since)

        pulled = 0
        conflicts_found = 0
        resolved_count = 0
        errors: list[str] = []

        for remote_mem in remote_memories:
            mem_id = remote_mem.get("id", "")
            local_mem = self._store.get(mem_id) if mem_id else None

            if local_mem is None:
                # New memory — import it
                try:
                    ns = remote_mem.get("namespace", namespace or "default")
                    self._store.add(
                        ns,
                        remote_mem.get("content", ""),
                        metadata=remote_mem.get("metadata"),
                        user_id=remote_mem.get("user_id"),
                        agent_id=remote_mem.get("agent_id"),
                    )
                    pulled += 1
                except Exception as exc:  # noqa: BLE001
                    errors.append(str(exc))
            else:
                # Exists locally — detect conflicts
                conflict = self._resolver.detect(local_mem, remote_mem)
                if conflict:
                    conflicts_found += 1
                    resolution = self._resolver.resolve(conflict)
                    resolved_count += 1
                    # Apply the resolution
                    resolved = resolution.resolved_content
                    if resolved.get("content") != local_mem.get("content"):
                        self._store.delete(mem_id)
                        ns = resolved.get("namespace", local_mem.get("namespace", "default"))
                        self._store.add(
                            ns,
                            resolved.get("content", ""),
                            metadata=resolved.get("metadata"),
                            user_id=resolved.get("user_id"),
                            agent_id=resolved.get("agent_id"),
                        )
                        pulled += 1
                else:
                    # No conflict — contents are identical, nothing to do
                    pass

        self._last_sync_at = self._now_iso()
        self._sync_count += 1

        return SyncResult(
            pushed=0, pulled=pulled, conflicts=conflicts_found,
            resolved=resolved_count, errors=errors,
        )

    def sync(self, namespace: str | None = None) -> SyncResult:
        """Bidirectional sync: push then pull."""
        push_result = self.push(namespace)
        pull_result = self.pull(namespace)
        return SyncResult(
            pushed=push_result.pushed,
            pulled=pull_result.pulled,
            conflicts=pull_result.conflicts,
            resolved=pull_result.resolved,
            errors=push_result.errors + pull_result.errors,
        )

    def get_state(self) -> SyncState:
        """Return current sync state."""
        return SyncState(
            last_sync_at=self._last_sync_at,
            sync_count=self._sync_count,
            pending_changes=len(self._change_log),
        )

    def reset_state(self) -> None:
        """Reset all sync tracking."""
        self._last_sync_at = ""
        self._sync_count = 0
        self._change_log.clear()

    def get_pending_changes(self, namespace: str | None = None) -> list[dict]:
        """Return changes recorded since the last sync."""
        if namespace:
            return [c for c in self._change_log if c.get("namespace") == namespace]
        return list(self._change_log)

    def record_change(self, memory_id: str, namespace: str, change_type: str) -> None:
        """Record a local change for sync tracking."""
        self._change_log.append({
            "memory_id": memory_id,
            "namespace": namespace,
            "change_type": change_type,
            "timestamp": self._now_iso(),
        })
        if len(self._change_log) > self._max_change_log:
            self._change_log = self._change_log[-self._max_change_log:]
