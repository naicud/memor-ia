"""SQLite-backed recall memory for session history."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS recall_items (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    metadata TEXT,
    importance REAL DEFAULT 0.5,
    session_id TEXT,
    created_at TEXT NOT NULL,
    accessed_at TEXT NOT NULL,
    access_count INTEGER DEFAULT 0
);
"""

# ---------------------------------------------------------------------------
# RecallMemory
# ---------------------------------------------------------------------------


class RecallMemory:
    """Thread-safe SQLite store for session-scoped recall memories."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        max_items: int = 1000,
    ) -> None:
        self.max_items = max_items
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
        session_id: str | None = None,
    ) -> str:
        """Store a recall item and return its UUID."""
        item_id = str(uuid.uuid4())
        now = self._now_iso()
        meta_json = json.dumps(metadata) if metadata else None
        self._conn.execute(
            "INSERT INTO recall_items "
            "(id, content, metadata, importance, session_id, created_at, accessed_at, access_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
            (item_id, content, meta_json, importance, session_id, now, now),
        )
        self._conn.commit()
        return item_id

    def get(self, item_id: str) -> Optional[dict]:
        """Retrieve a recall item, updating access tracking."""
        cur = self._conn.execute(
            "SELECT * FROM recall_items WHERE id = ?", (item_id,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        now = self._now_iso()
        self._conn.execute(
            "UPDATE recall_items SET accessed_at = ?, access_count = access_count + 1 WHERE id = ?",
            (now, item_id),
        )
        self._conn.commit()
        d = self._row_to_dict(row)
        d["access_count"] += 1
        d["accessed_at"] = now
        return d

    def remove(self, item_id: str) -> bool:
        """Delete a recall item. Returns ``True`` if it existed."""
        cur = self._conn.execute(
            "DELETE FROM recall_items WHERE id = ?", (item_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    # -- query -------------------------------------------------------------

    def search(
        self,
        query: str,
        session_id: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Keyword search across recall items."""
        clauses: list[str] = ["content LIKE ?"]
        params: list[str | int] = [f"%{query}%"]
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        sql = (
            f"SELECT * FROM recall_items WHERE {' AND '.join(clauses)} "
            "ORDER BY accessed_at DESC LIMIT ?"
        )
        params.append(limit)
        cur = self._conn.execute(sql, params)
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def list_by_session(self, session_id: str, limit: int = 50) -> list[dict]:
        """List recall items for a given session."""
        cur = self._conn.execute(
            "SELECT * FROM recall_items WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        )
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def count(self) -> int:
        """Total number of recall items."""
        cur = self._conn.execute("SELECT COUNT(*) FROM recall_items")
        return cur.fetchone()[0]

    def recent(self, limit: int = 20) -> list[dict]:
        """Most recent recall items."""
        cur = self._conn.execute(
            "SELECT * FROM recall_items ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def prune(self, max_age_days: int = 30) -> int:
        """Remove items older than *max_age_days*. Returns count removed."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
        cur = self._conn.execute(
            "DELETE FROM recall_items WHERE created_at < ?", (cutoff,)
        )
        self._conn.commit()
        return cur.rowcount
