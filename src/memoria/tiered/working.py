"""In-context ephemeral working memory (dict-backed, no persistence)."""

from __future__ import annotations

import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional


class WorkingMemory:
    """Fixed-capacity in-memory store for the current context window."""

    def __init__(self, max_tokens: int = 4096, max_items: int = 50) -> None:
        self.max_tokens = max_tokens
        self.max_items = max_items
        self._items: OrderedDict[str, dict] = OrderedDict()

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _estimate_tokens(content: str) -> int:
        return len(content) // 4

    # -- CRUD --------------------------------------------------------------

    def add(
        self,
        content: str,
        metadata: dict | None = None,
        importance: float = 0.5,
    ) -> str:
        """Add an item and return its UUID."""
        item_id = str(uuid.uuid4())
        now = self._now_iso()
        self._items[item_id] = {
            "id": item_id,
            "content": content,
            "metadata": dict(metadata) if metadata else {},
            "importance": importance,
            "added_at": now,
            "last_accessed": now,
            "access_count": 0,
        }
        # Move to end so insertion order == recency
        self._items.move_to_end(item_id)
        return item_id

    def get(self, item_id: str) -> Optional[dict]:
        """Retrieve an item, updating access tracking."""
        item = self._items.get(item_id)
        if item is None:
            return None
        item["access_count"] += 1
        item["last_accessed"] = self._now_iso()
        return dict(item)

    def remove(self, item_id: str) -> bool:
        """Remove an item. Returns ``True`` if it existed."""
        if item_id in self._items:
            del self._items[item_id]
            return True
        return False

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Simple keyword search across item content."""
        query_lower = query.lower()
        results = [
            dict(item)
            for item in self._items.values()
            if query_lower in item["content"].lower()
        ]
        # Most recent first (reverse insertion order)
        results.reverse()
        return results[:limit]

    def all(self) -> list[dict]:
        """Return all items ordered by recency (most recent first)."""
        items = [dict(item) for item in self._items.values()]
        items.reverse()
        return items

    def clear(self) -> int:
        """Remove all items. Returns count of items removed."""
        count = len(self._items)
        self._items.clear()
        return count

    # -- capacity ----------------------------------------------------------

    def token_count(self) -> int:
        """Estimated total tokens across all items."""
        return sum(self._estimate_tokens(item["content"]) for item in self._items.values())

    def is_full(self) -> bool:
        """True when token or item capacity is reached."""
        return self.token_count() >= self.max_tokens or len(self._items) >= self.max_items

    def evict(self, count: int = 1) -> list[dict]:
        """Evict lowest-importance items. Ties broken by oldest first."""
        if count <= 0 or not self._items:
            return []
        sorted_items = sorted(
            self._items.values(),
            key=lambda x: (x["importance"], x["added_at"]),
        )
        evicted: list[dict] = []
        for item in sorted_items[:count]:
            evicted.append(dict(item))
            del self._items[item["id"]]
        return evicted

    def auto_evict(self) -> list[dict]:
        """Evict items until the store is no longer full."""
        evicted: list[dict] = []
        while self.is_full() and self._items:
            evicted.extend(self.evict(1))
        return evicted
