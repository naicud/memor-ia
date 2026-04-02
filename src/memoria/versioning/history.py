"""Version history tracking for individual memories."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class VersionEntry:
    """A single version snapshot of a memory."""

    version: int
    memory_id: str
    content: str
    metadata: dict
    changed_by: str
    changed_at: str
    change_type: str  # "create" | "update" | "delete" | "restore"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    content TEXT,
    metadata TEXT,
    changed_by TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    change_type TEXT NOT NULL,
    UNIQUE(memory_id, version)
);
CREATE INDEX IF NOT EXISTS idx_versions_memory ON versions(memory_id);
"""

# ---------------------------------------------------------------------------
# VersionHistory
# ---------------------------------------------------------------------------


class VersionHistory:
    """SQLite-backed version history for memories."""

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
    def _row_to_entry(row: sqlite3.Row) -> VersionEntry:
        raw_meta = row["metadata"]
        return VersionEntry(
            version=row["version"],
            memory_id=row["memory_id"],
            content=row["content"] or "",
            metadata=json.loads(raw_meta) if raw_meta else {},
            changed_by=row["changed_by"],
            changed_at=row["changed_at"],
            change_type=row["change_type"],
        )

    def _next_version(self, memory_id: str) -> int:
        cur = self._conn.execute(
            "SELECT MAX(version) FROM versions WHERE memory_id = ?",
            (memory_id,),
        )
        row = cur.fetchone()
        current_max = row[0]
        return 1 if current_max is None else current_max + 1

    # -- public API --------------------------------------------------------

    def record(
        self,
        memory_id: str,
        content: str,
        metadata: dict | None = None,
        changed_by: str = "system",
        change_type: str = "update",
    ) -> VersionEntry:
        """Record a new version for *memory_id*, auto-incrementing the version number."""
        version = self._next_version(memory_id)
        now = self._now_iso()
        meta_json = json.dumps(metadata) if metadata else None
        self._conn.execute(
            "INSERT INTO versions (memory_id, version, content, metadata, changed_by, changed_at, change_type) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (memory_id, version, content, meta_json, changed_by, now, change_type),
        )
        self._conn.commit()
        return VersionEntry(
            version=version,
            memory_id=memory_id,
            content=content,
            metadata=metadata or {},
            changed_by=changed_by,
            changed_at=now,
            change_type=change_type,
        )

    def get_version(self, memory_id: str, version: int) -> Optional[VersionEntry]:
        """Retrieve a specific version of a memory."""
        cur = self._conn.execute(
            "SELECT * FROM versions WHERE memory_id = ? AND version = ?",
            (memory_id, version),
        )
        row = cur.fetchone()
        return self._row_to_entry(row) if row else None

    def get_latest(self, memory_id: str) -> Optional[VersionEntry]:
        """Retrieve the most recent version of a memory."""
        cur = self._conn.execute(
            "SELECT * FROM versions WHERE memory_id = ? ORDER BY version DESC LIMIT 1",
            (memory_id,),
        )
        row = cur.fetchone()
        return self._row_to_entry(row) if row else None

    def get_history(self, memory_id: str) -> list[VersionEntry]:
        """Return all versions for a memory, oldest first."""
        cur = self._conn.execute(
            "SELECT * FROM versions WHERE memory_id = ? ORDER BY version ASC",
            (memory_id,),
        )
        return [self._row_to_entry(r) for r in cur.fetchall()]

    def version_count(self, memory_id: str) -> int:
        """Return the number of versions recorded for a memory."""
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM versions WHERE memory_id = ?",
            (memory_id,),
        )
        return cur.fetchone()[0]

    def get_state_at(self, memory_id: str, version: int) -> Optional[dict]:
        """Return the memory state (content + metadata) at a given version."""
        entry = self.get_version(memory_id, version)
        if entry is None:
            return None
        return {"content": entry.content, "metadata": entry.metadata}

    def rollback(
        self, memory_id: str, to_version: int, changed_by: str = "system"
    ) -> VersionEntry:
        """Roll back to a previous version by creating a new 'restore' entry."""
        old = self.get_version(memory_id, to_version)
        if old is None:
            raise ValueError(
                f"Version {to_version} does not exist for memory {memory_id!r}"
            )
        return self.record(
            memory_id=memory_id,
            content=old.content,
            metadata=old.metadata if old.metadata else None,
            changed_by=changed_by,
            change_type="restore",
        )
