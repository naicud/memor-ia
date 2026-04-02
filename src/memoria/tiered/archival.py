"""SQLite-backed archival memory for long-term storage."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS archival_items (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    metadata TEXT,
    importance REAL DEFAULT 0.5,
    source_tier TEXT,
    namespace TEXT DEFAULT 'global',
    created_at TEXT NOT NULL,
    archived_at TEXT NOT NULL,
    access_count INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_archival_namespace ON archival_items(namespace);
"""

# ---------------------------------------------------------------------------
# ArchivalMemory
# ---------------------------------------------------------------------------


class ArchivalMemory:
    """Thread-safe SQLite store for long-term archival memories."""

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
    def _row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        raw = d.get("metadata")
        d["metadata"] = json.loads(raw) if raw else {}
        return d

    # -- CRUD --------------------------------------------------------------

    def add(
        self,
        content: str,
        metadata: dict | None = None,
        importance: float = 0.5,
        source_tier: str | None = None,
        namespace: str = "global",
    ) -> str:
        """Store an archival item and return its UUID."""
        item_id = str(uuid.uuid4())
        now = self._now_iso()
        meta_json = json.dumps(metadata) if metadata else None
        self._conn.execute(
            "INSERT INTO archival_items "
            "(id, content, metadata, importance, source_tier, namespace, created_at, archived_at, access_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (item_id, content, meta_json, importance, source_tier, namespace, now, now),
        )
        self._conn.commit()
        return item_id

    def get(self, item_id: str) -> Optional[dict]:
        """Retrieve an archival item by ID."""
        cur = self._conn.execute(
            "SELECT * FROM archival_items WHERE id = ?", (item_id,)
        )
        row = cur.fetchone()
        return self._row_to_dict(row) if row else None

    def remove(self, item_id: str) -> bool:
        """Delete an archival item. Returns ``True`` if it existed."""
        cur = self._conn.execute(
            "DELETE FROM archival_items WHERE id = ?", (item_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    # -- query -------------------------------------------------------------

    def search(
        self,
        query: str,
        namespace: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Keyword search across archival items."""
        clauses: list[str] = ["content LIKE ?"]
        params: list[str | int] = [f"%{query}%"]
        if namespace is not None:
            clauses.append("namespace = ?")
            params.append(namespace)
        sql = (
            f"SELECT * FROM archival_items WHERE {' AND '.join(clauses)} "
            "ORDER BY archived_at DESC LIMIT ?"
        )
        params.append(limit)
        cur = self._conn.execute(sql, params)
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def count(self, namespace: str | None = None) -> int:
        """Count archival items, optionally filtered by namespace."""
        if namespace is None:
            cur = self._conn.execute("SELECT COUNT(*) FROM archival_items")
        else:
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM archival_items WHERE namespace = ?",
                (namespace,),
            )
        return cur.fetchone()[0]

    def list_by_namespace(self, namespace: str, limit: int = 50) -> list[dict]:
        """List archival items in a given namespace."""
        cur = self._conn.execute(
            "SELECT * FROM archival_items WHERE namespace = ? ORDER BY archived_at DESC LIMIT ?",
            (namespace, limit),
        )
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def stats(self) -> dict:
        """Aggregate statistics about the archival store."""
        total = self.count()

        cur = self._conn.execute(
            "SELECT namespace, COUNT(*) as cnt FROM archival_items GROUP BY namespace"
        )
        by_namespace = {row["namespace"]: row["cnt"] for row in cur.fetchall()}

        cur = self._conn.execute(
            "SELECT source_tier, COUNT(*) as cnt FROM archival_items GROUP BY source_tier"
        )
        by_source_tier = {(row["source_tier"] or "unknown"): row["cnt"] for row in cur.fetchall()}

        return {
            "total": total,
            "by_namespace": by_namespace,
            "by_source_tier": by_source_tier,
        }
