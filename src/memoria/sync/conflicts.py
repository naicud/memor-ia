"""CRDT-inspired conflict detection and resolution for sync."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SyncConflict:
    """Describes a conflict between local and remote versions of a memory."""

    memory_id: str
    local_version: dict
    remote_version: dict
    conflict_type: str  # "update" | "delete" | "create"


@dataclass
class SyncResolution:
    """Outcome of resolving a conflict."""

    memory_id: str
    winner: str  # "local" | "remote" | "merged"
    resolved_content: dict
    strategy_used: str


# ---------------------------------------------------------------------------
# Strategy enum
# ---------------------------------------------------------------------------


class ConflictStrategy(Enum):
    LAST_WRITER_WINS = "last_writer_wins"
    LOCAL_WINS = "local_wins"
    REMOTE_WINS = "remote_wins"
    MERGE = "merge"
    MANUAL = "manual"


# ---------------------------------------------------------------------------
# SyncConflictResolver
# ---------------------------------------------------------------------------


class SyncConflictResolver:
    """Detects and resolves sync conflicts using configurable strategies."""

    def __init__(
        self,
        default_strategy: ConflictStrategy = ConflictStrategy.LAST_WRITER_WINS,
    ) -> None:
        self._default_strategy = default_strategy
        self._log: list[SyncConflict] = []
        self._max_log: int = 10_000

    # -- detection ---------------------------------------------------------

    def detect(self, local: dict, remote: dict) -> Optional[SyncConflict]:
        """Detect a conflict between *local* and *remote* memory dicts.

        Returns ``None`` when the two sides are compatible (identical content
        or only one side exists).
        """
        local_id = local.get("id", "")
        remote_id = remote.get("id", local_id)
        memory_id = local_id or remote_id

        local_deleted = local.get("_deleted", False)
        remote_deleted = remote.get("_deleted", False)

        # Delete conflict: one deleted, the other modified
        if local_deleted and not remote_deleted:
            conflict = SyncConflict(
                memory_id=memory_id,
                local_version=local,
                remote_version=remote,
                conflict_type="delete",
            )
            self._log.append(conflict)
            if len(self._log) > self._max_log:
                self._log = self._log[-self._max_log:]
            return conflict

        if remote_deleted and not local_deleted:
            conflict = SyncConflict(
                memory_id=memory_id,
                local_version=local,
                remote_version=remote,
                conflict_type="delete",
            )
            self._log.append(conflict)
            if len(self._log) > self._max_log:
                self._log = self._log[-self._max_log:]
            return conflict

        # No conflict if contents identical
        if local.get("content") == remote.get("content"):
            return None

        # Both have content but differ — update conflict
        local_updated = local.get("updated_at", "")
        remote_updated = remote.get("updated_at", "")

        if local_updated and remote_updated and local_updated != remote_updated:
            conflict = SyncConflict(
                memory_id=memory_id,
                local_version=local,
                remote_version=remote,
                conflict_type="update",
            )
            self._log.append(conflict)
            if len(self._log) > self._max_log:
                self._log = self._log[-self._max_log:]
            return conflict

        # Create conflict: both sides created with different content
        if not local_updated and not remote_updated:
            conflict = SyncConflict(
                memory_id=memory_id,
                local_version=local,
                remote_version=remote,
                conflict_type="create",
            )
            self._log.append(conflict)
            if len(self._log) > self._max_log:
                self._log = self._log[-self._max_log:]
            return conflict

        return None

    # -- resolution --------------------------------------------------------

    def resolve(
        self,
        conflict: SyncConflict,
        strategy: ConflictStrategy | None = None,
    ) -> SyncResolution:
        """Resolve a single conflict using the given (or default) strategy."""
        strat = strategy or self._default_strategy

        if strat == ConflictStrategy.LOCAL_WINS:
            return SyncResolution(
                memory_id=conflict.memory_id,
                winner="local",
                resolved_content=dict(conflict.local_version),
                strategy_used=strat.value,
            )

        if strat == ConflictStrategy.REMOTE_WINS:
            return SyncResolution(
                memory_id=conflict.memory_id,
                winner="remote",
                resolved_content=dict(conflict.remote_version),
                strategy_used=strat.value,
            )

        if strat == ConflictStrategy.MERGE:
            merged = dict(conflict.local_version)
            local_content = conflict.local_version.get("content", "")
            remote_content = conflict.remote_version.get("content", "")
            merged["content"] = f"{local_content}\n---\n{remote_content}"
            return SyncResolution(
                memory_id=conflict.memory_id,
                winner="merged",
                resolved_content=merged,
                strategy_used=strat.value,
            )

        if strat == ConflictStrategy.MANUAL:
            return SyncResolution(
                memory_id=conflict.memory_id,
                winner="local",
                resolved_content={
                    "local": dict(conflict.local_version),
                    "remote": dict(conflict.remote_version),
                },
                strategy_used=strat.value,
            )

        # LAST_WRITER_WINS (default)
        local_ts = conflict.local_version.get("updated_at", "")
        remote_ts = conflict.remote_version.get("updated_at", "")
        if remote_ts > local_ts:
            return SyncResolution(
                memory_id=conflict.memory_id,
                winner="remote",
                resolved_content=dict(conflict.remote_version),
                strategy_used=strat.value,
            )
        return SyncResolution(
            memory_id=conflict.memory_id,
            winner="local",
            resolved_content=dict(conflict.local_version),
            strategy_used=strat.value,
        )

    def resolve_batch(self, conflicts: list[SyncConflict]) -> list[SyncResolution]:
        """Resolve a batch of conflicts using the default strategy."""
        return [self.resolve(c) for c in conflicts]

    def conflict_log(self) -> list[SyncConflict]:
        """Return the history of all detected conflicts."""
        return list(self._log)
