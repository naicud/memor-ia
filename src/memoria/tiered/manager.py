"""Unified interface for the tiered memory system."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .working import WorkingMemory
from .recall_mem import RecallMemory
from .archival import ArchivalMemory
from .promoter import TierPromoter


class TieredMemoryManager:
    """Single entry-point for working / recall / archival memory."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        working_config: dict | None = None,
    ) -> None:
        wc = working_config or {}
        self._working = WorkingMemory(
            max_tokens=wc.get("max_tokens", 4096),
            max_items=wc.get("max_items", 50),
        )

        recall_path = str(Path(db_path) / "recall.db") if db_path else None
        archival_path = str(Path(db_path) / "archival.db") if db_path else None

        self._recall = RecallMemory(db_path=recall_path)
        self._archival = ArchivalMemory(db_path=archival_path)
        self._promoter = TierPromoter(
            working=self._working,
            recall=self._recall,
            archival=self._archival,
        )

    # -- tier accessors ----------------------------------------------------

    @property
    def working(self) -> WorkingMemory:
        return self._working

    @property
    def recall(self) -> RecallMemory:
        return self._recall

    @property
    def archival(self) -> ArchivalMemory:
        return self._archival

    @property
    def promoter(self) -> TierPromoter:
        return self._promoter

    # -- unified API -------------------------------------------------------

    def add(self, content: str, tier: str = "working", **kwargs) -> str:
        """Add content to a specific tier."""
        if tier == "working":
            return self._working.add(content, **kwargs)
        if tier == "recall":
            return self._recall.add(content, **kwargs)
        if tier == "archival":
            return self._archival.add(content, **kwargs)
        raise ValueError(f"Unknown tier: {tier!r}")

    def get(self, item_id: str) -> Optional[dict]:
        """Search across all tiers and return the first match with tier info."""
        for tier_name, store in [
            ("working", self._working),
            ("recall", self._recall),
            ("archival", self._archival),
        ]:
            item = store.get(item_id)
            if item is not None:
                return {**item, "tier": tier_name}
        return None

    def search(
        self,
        query: str,
        tiers: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Search across specified tiers (default: all), merge results."""
        target_tiers = tiers or ["working", "recall", "archival"]
        results: list[dict] = []
        for tier_name in target_tiers:
            if tier_name == "working":
                items = self._working.search(query, limit=limit)
            elif tier_name == "recall":
                items = self._recall.search(query, limit=limit)
            elif tier_name == "archival":
                items = self._archival.search(query, limit=limit)
            else:
                continue
            for item in items:
                results.append({**item, "tier": tier_name})
        return results[:limit]

    def delete(self, item_id: str) -> bool:
        """Delete an item from any tier."""
        for store in (self._working, self._recall, self._archival):
            if store.remove(item_id):
                return True
        return False

    def promote(self, item_id: str, from_tier: str, to_tier: str) -> str | None:
        """Manual promotion between tiers."""
        if from_tier == "working" and to_tier == "recall":
            return (self._promoter.promote_working_to_recall(item_id) or [None])[0]
        if from_tier == "recall" and to_tier == "archival":
            item = self._recall.get(item_id)
            if item is None:
                return None
            new_id = self._archival.add(
                content=item["content"],
                metadata=item["metadata"],
                importance=item["importance"],
                source_tier="recall",
            )
            self._recall.remove(item_id)
            return new_id
        if from_tier == "archival" and to_tier == "recall":
            return self._promoter.demote_to_recall(item_id)
        raise ValueError(f"Unsupported promotion: {from_tier!r} → {to_tier!r}")

    def stats(self) -> dict:
        """Aggregate statistics across all tiers."""
        archival_stats = self._archival.stats()
        return {
            "working": {
                "count": len(self._working._items),
                "tokens": self._working.token_count(),
            },
            "recall": {
                "count": self._recall.count(),
            },
            "archival": {
                "count": archival_stats["total"],
                "by_namespace": archival_stats["by_namespace"],
            },
        }

    def flush_session(self) -> dict:
        """Flush working to recall and run automatic promotions."""
        flushed = self._promoter.flush_working()
        auto = self._promoter.auto_promote()
        return {
            "flushed_to_recall": flushed,
            "auto_promoted": auto,
        }
