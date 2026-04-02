"""Audit trail — who changed what, when."""

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
class AuditEvent:
    """A single audit-log entry."""

    event_id: str
    memory_id: str
    action: str
    agent_id: str
    namespace: Optional[str]
    timestamp: str
    details: dict


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS audit_log (
    event_id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    action TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    namespace TEXT,
    timestamp TEXT NOT NULL,
    details TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_memory ON audit_log(memory_id);
CREATE INDEX IF NOT EXISTS idx_audit_agent ON audit_log(agent_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
"""

# ---------------------------------------------------------------------------
# AuditTrail
# ---------------------------------------------------------------------------


class AuditTrail:
    """SQLite-backed audit log for memory operations."""

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
    def _row_to_event(row: sqlite3.Row) -> AuditEvent:
        raw = row["details"]
        return AuditEvent(
            event_id=row["event_id"],
            memory_id=row["memory_id"],
            action=row["action"],
            agent_id=row["agent_id"],
            namespace=row["namespace"],
            timestamp=row["timestamp"],
            details=json.loads(raw) if raw else {},
        )

    # -- public API --------------------------------------------------------

    def log(
        self,
        memory_id: str,
        action: str,
        agent_id: str,
        namespace: str | None = None,
        details: dict | None = None,
    ) -> str:
        """Record an audit event and return the generated *event_id*."""
        event_id = str(uuid.uuid4())
        now = self._now_iso()
        details_json = json.dumps(details) if details else None
        self._conn.execute(
            "INSERT INTO audit_log (event_id, memory_id, action, agent_id, namespace, timestamp, details) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (event_id, memory_id, action, agent_id, namespace, now, details_json),
        )
        self._conn.commit()
        return event_id

    def get_events(self, memory_id: str, limit: int = 1000) -> list[AuditEvent]:
        """Return all events for a given memory, newest first."""
        cur = self._conn.execute(
            "SELECT * FROM audit_log WHERE memory_id = ? ORDER BY timestamp DESC LIMIT ?",
            (memory_id, limit),
        )
        return [self._row_to_event(r) for r in cur.fetchall()]

    def get_agent_activity(self, agent_id: str, limit: int = 50) -> list[AuditEvent]:
        """Return recent events by a specific agent."""
        cur = self._conn.execute(
            "SELECT * FROM audit_log WHERE agent_id = ? ORDER BY timestamp DESC LIMIT ?",
            (agent_id, limit),
        )
        return [self._row_to_event(r) for r in cur.fetchall()]

    def get_events_in_range(self, start: str, end: str, limit: int = 1000) -> list[AuditEvent]:
        """Return events whose timestamp falls within [*start*, *end*] (ISO strings)."""
        cur = self._conn.execute(
            "SELECT * FROM audit_log WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp ASC LIMIT ?",
            (start, end, limit),
        )
        return [self._row_to_event(r) for r in cur.fetchall()]

    def get_events_by_action(self, action: str, limit: int = 1000) -> list[AuditEvent]:
        """Return all events with a given action type."""
        cur = self._conn.execute(
            "SELECT * FROM audit_log WHERE action = ? ORDER BY timestamp DESC LIMIT ?",
            (action, limit),
        )
        return [self._row_to_event(r) for r in cur.fetchall()]

    def count(self, memory_id: str | None = None) -> int:
        """Count total audit events, optionally for a specific memory."""
        if memory_id is None:
            cur = self._conn.execute("SELECT COUNT(*) FROM audit_log")
        else:
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM audit_log WHERE memory_id = ?",
                (memory_id,),
            )
        return cur.fetchone()[0]

    def purge_before(self, timestamp: str) -> int:
        """Delete events older than *timestamp*. Returns count of deleted rows (GDPR compliance)."""
        cur = self._conn.execute(
            "DELETE FROM audit_log WHERE timestamp < ?",
            (timestamp,),
        )
        self._conn.commit()
        return cur.rowcount
