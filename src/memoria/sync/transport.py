"""Sync transport abstraction and implementations."""

from __future__ import annotations

import glob as _glob
import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class SyncTransport(ABC):
    """Abstract base for moving memories between instances."""

    @abstractmethod
    def send(self, memories: list[dict], namespace: str | None = None) -> dict:
        """Send memories to remote.

        Returns ``{"accepted": int, "rejected": int, "errors": []}``.
        """
        ...

    @abstractmethod
    def receive(self, namespace: str | None = None, since: str | None = None) -> list[dict]:
        """Receive memories from remote, optionally filtered by *since* timestamp."""
        ...

    @abstractmethod
    def ping(self) -> bool:
        """Check if remote is reachable."""
        ...


# ---------------------------------------------------------------------------
# InMemoryTransport — for testing
# ---------------------------------------------------------------------------


class InMemoryTransport(SyncTransport):
    """In-memory transport that stores everything in dicts."""

    def __init__(self) -> None:
        self._store: dict[str, list[dict]] = {}

    def send(self, memories: list[dict], namespace: str | None = None) -> dict:
        key = namespace or "__all__"
        if key not in self._store:
            self._store[key] = []
        self._store[key] = list(memories)
        return {"accepted": len(memories), "rejected": 0, "errors": []}

    def receive(self, namespace: str | None = None, since: str | None = None) -> list[dict]:
        key = namespace or "__all__"
        memories = list(self._store.get(key, []))
        if since:
            memories = [
                m for m in memories
                if m.get("updated_at", "") >= since
            ]
        return memories

    def ping(self) -> bool:
        return True

    def clear(self) -> None:
        """Reset all stored data."""
        self._store.clear()


# ---------------------------------------------------------------------------
# FileTransport — file-based sync via JSON export/import
# ---------------------------------------------------------------------------


class FileTransport(SyncTransport):
    """File-based sync via JSON export/import."""

    def __init__(self, export_dir: str | Path) -> None:
        self._dir = Path(export_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _now_stamp() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    def send(self, memories: list[dict], namespace: str | None = None) -> dict:
        ns_tag = namespace.replace("/", "_") if namespace else "all"
        filename = f"{ns_tag}_export_{self._now_stamp()}.json"
        path = self._dir / filename
        try:
            path.write_text(json.dumps(memories, indent=2, default=str), encoding="utf-8")
            return {"accepted": len(memories), "rejected": 0, "errors": []}
        except OSError as exc:
            return {"accepted": 0, "rejected": len(memories), "errors": [str(exc)]}

    def receive(self, namespace: str | None = None, since: str | None = None) -> list[dict]:
        exports = self.list_exports(namespace)
        if not exports:
            return []
        latest = exports[-1]
        memories: list[dict] = json.loads(latest.read_text(encoding="utf-8"))
        if since:
            memories = [m for m in memories if m.get("updated_at", "") >= since]
        return memories

    def ping(self) -> bool:
        return self._dir.exists()

    def list_exports(self, namespace: str | None = None) -> list[Path]:
        """Return export files sorted oldest-first."""
        ns_tag = namespace.replace("/", "_") if namespace else "all"
        pattern = str(self._dir / f"{ns_tag}_export_*.json")
        return sorted(Path(p) for p in _glob.glob(pattern))

    def cleanup(self, keep_latest: int = 5) -> int:
        """Delete old export files, keeping the *keep_latest* most recent. Returns count deleted."""
        deleted = 0
        seen_prefixes: dict[str, list[Path]] = {}
        for path in sorted(self._dir.glob("*_export_*.json")):
            prefix = path.name.rsplit("_export_", 1)[0]
            seen_prefixes.setdefault(prefix, []).append(path)

        for files in seen_prefixes.values():
            to_remove = files[:-keep_latest] if len(files) > keep_latest else []
            for f in to_remove:
                f.unlink()
                deleted += 1
        return deleted
