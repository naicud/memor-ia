"""Webhook registry — register, unregister, list, and persist webhook URLs."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Webhook:
    """A registered webhook endpoint."""

    webhook_id: str
    url: str
    events: list[str] = field(default_factory=lambda: ["*"])
    secret: str = ""
    active: bool = True
    consecutive_failures: int = 0
    description: str = ""
    created_at: str = ""

    def matches_event(self, event_type: str) -> bool:
        """Return True if this webhook should receive *event_type*."""
        if not self.active:
            return False
        if "*" in self.events:
            return True
        return event_type in self.events


_SCHEMA = """
CREATE TABLE IF NOT EXISTS webhooks (
    webhook_id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    events TEXT NOT NULL DEFAULT '["*"]',
    secret TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT ''
);
"""


class WebhookRegistry:
    """SQLite-backed registry for webhook configurations."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            p = Path(db_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(p), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def register(
        self,
        url: str,
        *,
        events: list[str] | None = None,
        secret: str = "",
        description: str = "",
    ) -> Webhook:
        """Register a new webhook. Returns the created Webhook."""
        from datetime import datetime, timezone

        wh = Webhook(
            webhook_id=f"wh_{uuid.uuid4().hex[:12]}",
            url=url,
            events=events or ["*"],
            secret=secret,
            description=description,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO webhooks (webhook_id, url, events, secret, active, "
                "consecutive_failures, description, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    wh.webhook_id,
                    wh.url,
                    json.dumps(wh.events),
                    wh.secret,
                    1,
                    0,
                    wh.description,
                    wh.created_at,
                ),
            )
            self._conn.commit()
        return wh

    def unregister(self, webhook_id: str) -> bool:
        """Remove a webhook. Returns True if found and deleted."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM webhooks WHERE webhook_id = ?", (webhook_id,)
            )
            self._conn.commit()
            return cur.rowcount > 0

    def get(self, webhook_id: str) -> Webhook | None:
        """Fetch a single webhook by ID."""
        row = self._conn.execute(
            "SELECT * FROM webhooks WHERE webhook_id = ?", (webhook_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_webhook(row)

    def list_all(self, *, active_only: bool = False) -> list[Webhook]:
        """Return all registered webhooks."""
        if active_only:
            rows = self._conn.execute(
                "SELECT * FROM webhooks WHERE active = 1 ORDER BY created_at"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM webhooks ORDER BY created_at"
            ).fetchall()
        return [self._row_to_webhook(r) for r in rows]

    def for_event(self, event_type: str) -> list[Webhook]:
        """Return active webhooks subscribed to *event_type*."""
        all_active = self.list_all(active_only=True)
        return [wh for wh in all_active if wh.matches_event(event_type)]

    def record_failure(self, webhook_id: str) -> None:
        """Increment failure counter. Deactivate after 10 consecutive failures."""
        with self._lock:
            row = self._conn.execute(
                "SELECT consecutive_failures FROM webhooks WHERE webhook_id = ?",
                (webhook_id,),
            ).fetchone()
            if row is None:
                return
            failures = row["consecutive_failures"] + 1
            active = 0 if failures >= 10 else 1
            self._conn.execute(
                "UPDATE webhooks SET consecutive_failures = ?, active = ? WHERE webhook_id = ?",
                (failures, active, webhook_id),
            )
            self._conn.commit()

    def record_success(self, webhook_id: str) -> None:
        """Reset failure counter on successful delivery."""
        with self._lock:
            self._conn.execute(
                "UPDATE webhooks SET consecutive_failures = 0 WHERE webhook_id = ?",
                (webhook_id,),
            )
            self._conn.commit()

    def update_active(self, webhook_id: str, active: bool) -> bool:
        """Manually activate or deactivate a webhook."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE webhooks SET active = ?, consecutive_failures = 0 WHERE webhook_id = ?",
                (1 if active else 0, webhook_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    @staticmethod
    def _row_to_webhook(row: sqlite3.Row) -> Webhook:
        return Webhook(
            webhook_id=row["webhook_id"],
            url=row["url"],
            events=json.loads(row["events"]),
            secret=row["secret"],
            active=bool(row["active"]),
            consecutive_failures=row["consecutive_failures"],
            description=row["description"],
            created_at=row["created_at"],
        )
