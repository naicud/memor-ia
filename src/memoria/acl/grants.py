"""SQLite-backed grant storage for role assignments."""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .roles import Role, RoleAssignment

# ── Schema ───────────────────────────────────────────────────────

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS grants (
    id         TEXT PRIMARY KEY,
    agent_id   TEXT NOT NULL,
    namespace  TEXT NOT NULL,
    role       TEXT NOT NULL,
    granted_by TEXT NOT NULL,
    granted_at TEXT NOT NULL,
    UNIQUE(agent_id, namespace)
);
"""


# ── GrantStore ───────────────────────────────────────────────────


class GrantStore:
    """Persistent (or in-memory) store for access-control grants.

    Parameters
    ----------
    db_path
        Path to a SQLite database file.  Defaults to ``":memory:"``
        for an ephemeral in-memory store.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        path = str(db_path) if db_path is not None else ":memory:"
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.executescript(_SCHEMA)

    # ── mutations ────────────────────────────────────────────────

    def grant(
        self,
        agent_id: str,
        namespace: str,
        role: Role,
        granted_by: str,
    ) -> str:
        """Create or update a role grant.  Returns the grant id."""
        grant_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO grants (id, agent_id, namespace, role, granted_by, granted_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_id, namespace) DO UPDATE SET
                id         = excluded.id,
                role       = excluded.role,
                granted_by = excluded.granted_by,
                granted_at = excluded.granted_at
            """,
            (grant_id, agent_id, namespace, role.name, granted_by, now),
        )
        self._conn.commit()
        return grant_id

    def revoke(self, agent_id: str, namespace: str) -> bool:
        """Remove a grant.  Returns *True* if a row was deleted."""
        cur = self._conn.execute(
            "DELETE FROM grants WHERE agent_id = ? AND namespace = ?",
            (agent_id, namespace),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def revoke_all(self, namespace: str) -> int:
        """Remove every grant on *namespace*.  Returns delete count."""
        cur = self._conn.execute(
            "DELETE FROM grants WHERE namespace = ?",
            (namespace,),
        )
        self._conn.commit()
        return cur.rowcount

    # ── queries ──────────────────────────────────────────────────

    def get_role(self, agent_id: str, namespace: str) -> Optional[Role]:
        """Return the direct role for *agent_id* on *namespace*, or ``None``."""
        row = self._conn.execute(
            "SELECT role FROM grants WHERE agent_id = ? AND namespace = ?",
            (agent_id, namespace),
        ).fetchone()
        if row is None:
            return None
        return Role[row[0]]

    def get_grants_for_agent(self, agent_id: str) -> list[RoleAssignment]:
        """Return every grant held by *agent_id*."""
        rows = self._conn.execute(
            "SELECT agent_id, namespace, role, granted_by, granted_at "
            "FROM grants WHERE agent_id = ?",
            (agent_id,),
        ).fetchall()
        return [self._row_to_assignment(r) for r in rows]

    def get_grants_for_namespace(self, namespace: str) -> list[RoleAssignment]:
        """Return every grant on *namespace*."""
        rows = self._conn.execute(
            "SELECT agent_id, namespace, role, granted_by, granted_at "
            "FROM grants WHERE namespace = ?",
            (namespace,),
        ).fetchall()
        return [self._row_to_assignment(r) for r in rows]

    def has_any_grant(self, agent_id: str) -> bool:
        """Quick check whether *agent_id* has at least one grant."""
        row = self._conn.execute(
            "SELECT 1 FROM grants WHERE agent_id = ? LIMIT 1",
            (agent_id,),
        ).fetchone()
        return row is not None

    # ── internals ────────────────────────────────────────────────

    @staticmethod
    def _row_to_assignment(row: tuple) -> RoleAssignment:
        agent_id, namespace, role_name, granted_by, granted_at = row
        return RoleAssignment(
            agent_id=agent_id,
            namespace=namespace,
            role=Role[role_name],
            granted_by=granted_by,
            granted_at=granted_at,
        )
