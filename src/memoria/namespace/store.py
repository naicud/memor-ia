"""SQLite-backed shared memory store with namespace scoping."""

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
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT,
    user_id TEXT,
    agent_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_namespace ON memories(namespace);
CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id);
"""

# ---------------------------------------------------------------------------
# SharedMemoryStore
# ---------------------------------------------------------------------------


class SharedMemoryStore:
    """Thread-safe SQLite store for namespace-scoped memories."""

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
        namespace: str,
        content: str,
        *,
        metadata: dict | None = None,
        user_id: str | None = None,
        agent_id: str | None = None,
    ) -> str:
        """Store a new memory and return its UUID."""
        memory_id = str(uuid.uuid4())
        now = self._now_iso()
        meta_json = json.dumps(metadata) if metadata else None
        self._conn.execute(
            "INSERT INTO memories (id, namespace, content, metadata, user_id, agent_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (memory_id, namespace, content, meta_json, user_id, agent_id, now, now),
        )
        self._conn.commit()
        return memory_id

    def get(self, memory_id: str) -> Optional[dict]:
        """Retrieve a single memory by ID, or ``None``."""
        cur = self._conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,))
        row = cur.fetchone()
        return self._row_to_dict(row) if row else None

    def delete(self, memory_id: str) -> bool:
        """Delete a memory. Returns ``True`` if it existed."""
        cur = self._conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self._conn.commit()
        return cur.rowcount > 0

    # -- query -------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        namespace: str | None = None,
        user_id: str | None = None,
        limit: int = 10,
        offset: int = 0,
        include_ancestors: bool = True,
    ) -> list[dict]:
        """Keyword search across memories.

        When *include_ancestors* is ``True`` and a *namespace* is given, the
        search also covers all ancestor namespaces (walking up the hierarchy).
        """
        clauses: list[str] = ["content LIKE ?"]
        params: list[str | int] = [f"%{query}%"]

        if namespace is not None:
            if include_ancestors:
                ns_clause, ns_params = self._ancestor_clauses(namespace)
                clauses.append(f"({ns_clause})")
                params.extend(ns_params)
            else:
                clauses.append("namespace = ?")
                params.append(namespace)

        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)

        sql = f"SELECT * FROM memories WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.append(limit)
        params.append(offset)
        cur = self._conn.execute(sql, params)
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def list_by_namespace(
        self,
        namespace: str,
        *,
        recursive: bool = False,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[dict]:
        """List memories in a namespace.

        If *recursive* is ``True``, also includes sub-namespaces.
        """
        if recursive:
            cur = self._conn.execute(
                "SELECT * FROM memories WHERE namespace = ? OR namespace LIKE ? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (namespace, f"{namespace}/%", limit, offset),
            )
        else:
            cur = self._conn.execute(
                "SELECT * FROM memories WHERE namespace = ? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (namespace, limit, offset),
            )
        return [self._row_to_dict(r) for r in cur.fetchall()]

    def count(self, namespace: str | None = None) -> int:
        """Count memories, optionally filtered by namespace."""
        if namespace is None:
            cur = self._conn.execute("SELECT COUNT(*) FROM memories")
        else:
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM memories WHERE namespace = ? OR namespace LIKE ?",
                (namespace, f"{namespace}/%"),
            )
        return cur.fetchone()[0]

    def namespaces(self) -> list[str]:
        """Return all distinct namespace paths."""
        cur = self._conn.execute(
            "SELECT DISTINCT namespace FROM memories ORDER BY namespace"
        )
        return [row[0] for row in cur.fetchall()]

    def move(self, memory_id: str, new_namespace: str) -> bool:
        """Move a memory to a different namespace. Returns ``True`` on success."""
        now = self._now_iso()
        cur = self._conn.execute(
            "UPDATE memories SET namespace = ?, updated_at = ? WHERE id = ?",
            (new_namespace, now, memory_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    # -- internal ----------------------------------------------------------

    @staticmethod
    def _ancestor_clauses(namespace: str) -> tuple[str, list[str]]:
        """Build an OR chain matching the namespace and all its ancestors.

        Returns ``(clause_str, params)`` using parameterised placeholders.
        """
        parts = namespace.split("/")
        paths: list[str] = [""]  # global (empty string)
        for i in range(len(parts)):
            paths.append("/".join(parts[: i + 1]))
        placeholders = " OR ".join("namespace = ?" for _ in paths)
        return placeholders, paths
