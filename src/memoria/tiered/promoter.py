"""Automatic tier-transition logic for the tiered memory system."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .working import WorkingMemory
from .recall_mem import RecallMemory
from .archival import ArchivalMemory

_DEFAULT_CONFIG: dict = {
    "auto_promote_working_to_recall": True,
    "auto_promote_recall_to_archival": True,
    "recall_to_archival_days": 7,
    "min_importance_for_archival": 0.3,
    "boost_on_access": 0.1,
}


class TierPromoter:
    """Manages automatic promotion/demotion between memory tiers."""

    def __init__(
        self,
        working: WorkingMemory,
        recall: RecallMemory,
        archival: ArchivalMemory,
        config: dict | None = None,
    ) -> None:
        self.working = working
        self.recall = recall
        self.archival = archival
        self.config = {**_DEFAULT_CONFIG, **(config or {})}

    # -- working → recall --------------------------------------------------

    def promote_working_to_recall(self, item_id: str | None = None) -> list[str]:
        """Promote working-memory items to recall.

        If *item_id* is given, promotes that single item.  Otherwise promotes
        all items currently evicted via ``auto_evict``.
        """
        promoted_ids: list[str] = []

        if item_id is not None:
            item = self.working.get(item_id)
            if item is None:
                return promoted_ids
            self.working.remove(item_id)
            new_id = self.recall.add(
                content=item["content"],
                metadata=item["metadata"],
                importance=item["importance"],
            )
            promoted_ids.append(new_id)
        else:
            evicted = self.working.auto_evict()
            for item in evicted:
                new_id = self.recall.add(
                    content=item["content"],
                    metadata=item["metadata"],
                    importance=item["importance"],
                )
                promoted_ids.append(new_id)

        return promoted_ids

    # -- recall → archival -------------------------------------------------

    def promote_recall_to_archival(
        self,
        session_id: str | None = None,
        min_age_days: int | None = None,
    ) -> list[str]:
        """Promote old recall items to archival storage."""
        age_days = min_age_days if min_age_days is not None else self.config["recall_to_archival_days"]
        min_importance = self.config["min_importance_for_archival"]
        cutoff = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()

        if session_id is not None:
            items = self.recall.list_by_session(session_id, limit=10000)
        else:
            items = self.recall.recent(limit=10000)

        promoted_ids: list[str] = []
        for item in items:
            if item["created_at"] < cutoff and item["importance"] >= min_importance:
                new_id = self.archival.add(
                    content=item["content"],
                    metadata=item["metadata"],
                    importance=item["importance"],
                    source_tier="recall",
                )
                self.recall.remove(item["id"])
                promoted_ids.append(new_id)

        return promoted_ids

    # -- archival → recall (demotion) --------------------------------------

    def demote_to_recall(self, archival_item_id: str) -> str | None:
        """Bring an archival item back to recall tier."""
        item = self.archival.get(archival_item_id)
        if item is None:
            return None
        new_id = self.recall.add(
            content=item["content"],
            metadata=item["metadata"],
            importance=item["importance"],
        )
        self.archival.remove(archival_item_id)
        return new_id

    # -- batch operations --------------------------------------------------

    def auto_promote(self) -> dict:
        """Run all configured automatic promotions."""
        result: dict[str, list[str]] = {
            "working_to_recall": [],
            "recall_to_archival": [],
        }
        if self.config["auto_promote_working_to_recall"]:
            result["working_to_recall"] = self.promote_working_to_recall()
        if self.config["auto_promote_recall_to_archival"]:
            result["recall_to_archival"] = self.promote_recall_to_archival()
        return result

    def promote_batch_working_to_recall(self, item_ids: list[str]) -> list[str]:
        """Promote multiple specific working-memory items to recall."""
        promoted_ids: list[str] = []
        for item_id in item_ids:
            result = self.promote_working_to_recall(item_id)
            promoted_ids.extend(result)
        return promoted_ids

    def flush_working(self) -> list[str]:
        """Promote ALL working-memory items to recall (e.g. on session end)."""
        promoted_ids: list[str] = []
        items = self.working.all()
        for item in items:
            new_id = self.recall.add(
                content=item["content"],
                metadata=item["metadata"],
                importance=item["importance"],
            )
            promoted_ids.append(new_id)
        self.working.clear()
        return promoted_ids
