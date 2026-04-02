"""Point-in-time namespace snapshots."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class Snapshot:
    """A frozen copy of all memories in a namespace at a point in time."""

    snapshot_id: str
    namespace: str
    created_at: str
    created_by: str
    memory_count: int
    data: list[dict]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    memory_count INTEGER NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_namespace ON snapshots(namespace);
"""

# ---------------------------------------------------------------------------
# SnapshotStore
# ---------------------------------------------------------------------------


class SnapshotStore:
    """SQLite-backed store for namespace snapshots."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            p = Path(db_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(p), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA_SQL)

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _row_to_snapshot(row: sqlite3.Row, *, include_data: bool = True) -> Snapshot:
        return Snapshot(
            snapshot_id=row["snapshot_id"],
            namespace=row["namespace"],
            created_at=row["created_at"],
            created_by=row["created_by"],
            memory_count=row["memory_count"],
            data=json.loads(row["data"]) if include_data else [],
        )

    # -- public API --------------------------------------------------------

    def create_snapshot(
        self,
        namespace: str,
        memories: list[dict],
        created_by: str = "system",
    ) -> Snapshot:
        """Capture a point-in-time snapshot of a namespace."""
        snapshot_id = str(uuid.uuid4())
        now = self._now_iso()
        data_json = json.dumps(memories)
        self._conn.execute(
            "INSERT INTO snapshots (snapshot_id, namespace, created_at, created_by, memory_count, data) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (snapshot_id, namespace, now, created_by, len(memories), data_json),
        )
        self._conn.commit()
        return Snapshot(
            snapshot_id=snapshot_id,
            namespace=namespace,
            created_at=now,
            created_by=created_by,
            memory_count=len(memories),
            data=memories,
        )

    def get_snapshot(self, snapshot_id: str) -> Optional[Snapshot]:
        """Retrieve a snapshot by ID (including data)."""
        cur = self._conn.execute(
            "SELECT * FROM snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        )
        row = cur.fetchone()
        return self._row_to_snapshot(row) if row else None

    def list_snapshots(self, namespace: str) -> list[Snapshot]:
        """List snapshots for a namespace (lightweight — no data loaded)."""
        cur = self._conn.execute(
            "SELECT * FROM snapshots WHERE namespace = ? ORDER BY created_at DESC",
            (namespace,),
        )
        return [self._row_to_snapshot(r, include_data=False) for r in cur.fetchall()]

    def diff_snapshots(self, snap1_id: str, snap2_id: str) -> dict:
        """Compare two snapshots and return added / removed / modified memories.

        Each memory dict is expected to have an ``"id"`` key for matching.
        """
        s1 = self.get_snapshot(snap1_id)
        s2 = self.get_snapshot(snap2_id)
        if s1 is None or s2 is None:
            raise ValueError("One or both snapshot IDs are invalid")

        map1 = {m["id"]: m for m in s1.data if "id" in m}
        map2 = {m["id"]: m for m in s2.data if "id" in m}

        ids1 = set(map1)
        ids2 = set(map2)

        added = [map2[mid] for mid in sorted(ids2 - ids1)]
        removed = [map1[mid] for mid in sorted(ids1 - ids2)]
        modified = [
            map2[mid]
            for mid in sorted(ids1 & ids2)
            if map1[mid] != map2[mid]
        ]

        return {"added": added, "removed": removed, "modified": modified}

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot. Returns ``True`` if it existed."""
        cur = self._conn.execute(
            "DELETE FROM snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def restore_snapshot(self, snapshot_id: str) -> list[dict]:
        """Return the memories stored in a snapshot for restoration."""
        snap = self.get_snapshot(snapshot_id)
        if snap is None:
            raise ValueError(f"Snapshot {snapshot_id!r} not found")
        return snap.data
