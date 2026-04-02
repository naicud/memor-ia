"""Tests for the MEMORIA tiered memory system (M9)."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from memoria.tiered import (
    ArchivalMemory,
    RecallMemory,
    TierPromoter,
    TieredMemoryManager,
    WorkingMemory,
)

# =========================================================================
# TestWorkingMemory
# =========================================================================


class TestWorkingMemory:
    def _make(self, **kw):
        return WorkingMemory(**kw)

    # -- add / get ---------------------------------------------------------

    def test_add_returns_uuid(self):
        wm = self._make()
        item_id = wm.add("hello world")
        assert isinstance(item_id, str) and len(item_id) == 36

    def test_get_returns_item(self):
        wm = self._make()
        item_id = wm.add("hello", metadata={"k": "v"}, importance=0.8)
        item = wm.get(item_id)
        assert item is not None
        assert item["content"] == "hello"
        assert item["metadata"] == {"k": "v"}
        assert item["importance"] == 0.8

    def test_get_missing_returns_none(self):
        wm = self._make()
        assert wm.get("nonexistent") is None

    def test_get_increments_access_count(self):
        wm = self._make()
        item_id = wm.add("test")
        wm.get(item_id)
        wm.get(item_id)
        item = wm.get(item_id)
        assert item["access_count"] == 3

    def test_get_updates_last_accessed(self):
        wm = self._make()
        item_id = wm.add("test")
        first = wm.get(item_id)["last_accessed"]
        time.sleep(0.01)
        second = wm.get(item_id)["last_accessed"]
        assert second >= first

    # -- remove / clear ----------------------------------------------------

    def test_remove_existing(self):
        wm = self._make()
        item_id = wm.add("test")
        assert wm.remove(item_id) is True
        assert wm.get(item_id) is None

    def test_remove_nonexistent(self):
        wm = self._make()
        assert wm.remove("nope") is False

    def test_clear(self):
        wm = self._make()
        wm.add("a")
        wm.add("b")
        removed = wm.clear()
        assert removed == 2
        assert wm.all() == []

    # -- search ------------------------------------------------------------

    def test_search_keyword(self):
        wm = self._make()
        wm.add("the quick brown fox")
        wm.add("lazy dog")
        wm.add("quick rabbit")
        results = wm.search("quick")
        assert len(results) == 2
        assert all("quick" in r["content"].lower() for r in results)

    def test_search_case_insensitive(self):
        wm = self._make()
        wm.add("Hello World")
        assert len(wm.search("hello")) == 1

    def test_search_limit(self):
        wm = self._make()
        for i in range(10):
            wm.add(f"item {i}")
        assert len(wm.search("item", limit=3)) == 3

    # -- all ---------------------------------------------------------------

    def test_all_ordered_by_recency(self):
        wm = self._make()
        wm.add("first")
        wm.add("second")
        wm.add("third")
        items = wm.all()
        assert [i["content"] for i in items] == ["third", "second", "first"]

    # -- token / capacity --------------------------------------------------

    def test_token_count(self):
        wm = self._make()
        wm.add("a" * 100)  # 25 tokens
        wm.add("b" * 200)  # 50 tokens
        assert wm.token_count() == 75

    def test_is_full_by_tokens(self):
        wm = self._make(max_tokens=10, max_items=100)
        wm.add("a" * 40)  # 10 tokens
        assert wm.is_full() is True

    def test_is_full_by_items(self):
        wm = self._make(max_tokens=99999, max_items=2)
        wm.add("a")
        assert wm.is_full() is False
        wm.add("b")
        assert wm.is_full() is True

    # -- eviction ----------------------------------------------------------

    def test_evict_lowest_importance(self):
        wm = self._make()
        wm.add("low", importance=0.1)
        wm.add("high", importance=0.9)
        evicted = wm.evict(1)
        assert len(evicted) == 1
        assert evicted[0]["content"] == "low"
        assert len(wm.all()) == 1

    def test_evict_tiebreak_oldest(self):
        wm = self._make()
        wm.add("old", importance=0.5)
        time.sleep(0.01)
        wm.add("new", importance=0.5)
        evicted = wm.evict(1)
        assert evicted[0]["content"] == "old"

    def test_auto_evict(self):
        wm = self._make(max_tokens=10, max_items=100)
        wm.add("a" * 40, importance=0.1)  # 10 tokens
        wm.add("b" * 8, importance=0.9)   # 2 tokens
        assert wm.is_full()
        evicted = wm.auto_evict()
        assert not wm.is_full()
        assert any(e["content"] == "a" * 40 for e in evicted)

    def test_evict_empty(self):
        wm = self._make()
        assert wm.evict(5) == []


# =========================================================================
# TestRecallMemory
# =========================================================================


class TestRecallMemory:
    def _make(self, **kw):
        return RecallMemory(**kw)

    def test_add_and_get(self):
        rm = self._make()
        item_id = rm.add("recall this", metadata={"source": "test"})
        item = rm.get(item_id)
        assert item["content"] == "recall this"
        assert item["metadata"] == {"source": "test"}

    def test_get_updates_access(self):
        rm = self._make()
        item_id = rm.add("test")
        item = rm.get(item_id)
        assert item["access_count"] == 1

    def test_get_missing(self):
        rm = self._make()
        assert rm.get("missing") is None

    def test_remove(self):
        rm = self._make()
        item_id = rm.add("test")
        assert rm.remove(item_id) is True
        assert rm.get(item_id) is None

    def test_remove_nonexistent(self):
        rm = self._make()
        assert rm.remove("nope") is False

    def test_search(self):
        rm = self._make()
        rm.add("python programming")
        rm.add("java programming")
        rm.add("cooking recipe")
        results = rm.search("programming")
        assert len(results) == 2

    def test_search_by_session(self):
        rm = self._make()
        rm.add("sess1 item", session_id="s1")
        rm.add("sess2 item", session_id="s2")
        results = rm.search("item", session_id="s1")
        assert len(results) == 1
        assert results[0]["session_id"] == "s1"

    def test_list_by_session(self):
        rm = self._make()
        rm.add("a", session_id="s1")
        rm.add("b", session_id="s1")
        rm.add("c", session_id="s2")
        items = rm.list_by_session("s1")
        assert len(items) == 2

    def test_count(self):
        rm = self._make()
        rm.add("a")
        rm.add("b")
        assert rm.count() == 2

    def test_recent(self):
        rm = self._make()
        rm.add("old")
        rm.add("new")
        items = rm.recent(limit=1)
        assert len(items) == 1
        assert items[0]["content"] == "new"

    def test_prune(self):
        rm = self._make()
        rm.add("recent")
        # Manually backdate one item
        rm._conn.execute(
            "INSERT INTO recall_items (id, content, metadata, importance, session_id, created_at, accessed_at, access_count) "
            "VALUES (?, ?, NULL, 0.5, NULL, ?, ?, 0)",
            (
                "old-id",
                "ancient item",
                (datetime.now(timezone.utc) - timedelta(days=60)).isoformat(),
                (datetime.now(timezone.utc) - timedelta(days=60)).isoformat(),
            ),
        )
        rm._conn.commit()
        pruned = rm.prune(max_age_days=30)
        assert pruned == 1
        assert rm.count() == 1


# =========================================================================
# TestArchivalMemory
# =========================================================================


class TestArchivalMemory:
    def _make(self):
        return ArchivalMemory()

    def test_add_and_get(self):
        am = self._make()
        item_id = am.add("long term", metadata={"tag": "important"}, namespace="projects")
        item = am.get(item_id)
        assert item["content"] == "long term"
        assert item["namespace"] == "projects"
        assert item["metadata"] == {"tag": "important"}

    def test_get_missing(self):
        am = self._make()
        assert am.get("nope") is None

    def test_remove(self):
        am = self._make()
        item_id = am.add("test")
        assert am.remove(item_id) is True
        assert am.get(item_id) is None

    def test_search(self):
        am = self._make()
        am.add("python tips")
        am.add("java tips")
        am.add("cooking recipe")
        results = am.search("tips")
        assert len(results) == 2

    def test_search_by_namespace(self):
        am = self._make()
        am.add("item a", namespace="ns1")
        am.add("item b", namespace="ns2")
        results = am.search("item", namespace="ns1")
        assert len(results) == 1

    def test_count(self):
        am = self._make()
        am.add("a", namespace="ns1")
        am.add("b", namespace="ns1")
        am.add("c", namespace="ns2")
        assert am.count() == 3
        assert am.count(namespace="ns1") == 2

    def test_list_by_namespace(self):
        am = self._make()
        am.add("x", namespace="work")
        am.add("y", namespace="personal")
        items = am.list_by_namespace("work")
        assert len(items) == 1
        assert items[0]["content"] == "x"

    def test_stats(self):
        am = self._make()
        am.add("a", namespace="ns1", source_tier="working")
        am.add("b", namespace="ns1", source_tier="recall")
        am.add("c", namespace="ns2", source_tier="recall")
        stats = am.stats()
        assert stats["total"] == 3
        assert stats["by_namespace"]["ns1"] == 2
        assert stats["by_namespace"]["ns2"] == 1
        assert stats["by_source_tier"]["working"] == 1
        assert stats["by_source_tier"]["recall"] == 2

    def test_default_namespace_is_global(self):
        am = self._make()
        item_id = am.add("global item")
        item = am.get(item_id)
        assert item["namespace"] == "global"


# =========================================================================
# TestTierPromoter
# =========================================================================


class TestTierPromoter:
    def _make(self, **config):
        wm = WorkingMemory(max_tokens=20, max_items=5)
        rm = RecallMemory()
        am = ArchivalMemory()
        tp = TierPromoter(wm, rm, am, config=config or None)
        return wm, rm, am, tp

    def test_promote_working_to_recall_by_id(self):
        wm, rm, am, tp = self._make()
        item_id = wm.add("promote me", importance=0.7)
        promoted = tp.promote_working_to_recall(item_id)
        assert len(promoted) == 1
        assert wm.get(item_id) is None
        recall_item = rm.get(promoted[0])
        assert recall_item["content"] == "promote me"

    def test_promote_working_to_recall_auto_evict(self):
        wm, rm, am, tp = self._make()
        # Fill up working memory
        for i in range(6):
            wm.add(f"item {i}" * 5, importance=0.1 * i)
        promoted = tp.promote_working_to_recall()
        assert len(promoted) > 0
        assert rm.count() > 0

    def test_promote_recall_to_archival(self):
        wm, rm, am, tp = self._make()
        # Manually insert an old recall item
        rm._conn.execute(
            "INSERT INTO recall_items (id, content, metadata, importance, session_id, created_at, accessed_at, access_count) "
            "VALUES (?, ?, NULL, 0.5, NULL, ?, ?, 0)",
            (
                "old-recall",
                "old content",
                (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
                (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
            ),
        )
        rm._conn.commit()
        promoted = tp.promote_recall_to_archival()
        assert len(promoted) == 1
        assert am.count() == 1
        assert rm.count() == 0

    def test_promote_recall_skips_low_importance(self):
        wm, rm, am, tp = self._make(min_importance_for_archival=0.5)
        rm._conn.execute(
            "INSERT INTO recall_items (id, content, metadata, importance, session_id, created_at, accessed_at, access_count) "
            "VALUES (?, ?, NULL, 0.2, NULL, ?, ?, 0)",
            (
                "low-imp",
                "low importance",
                (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
                (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(),
            ),
        )
        rm._conn.commit()
        promoted = tp.promote_recall_to_archival()
        assert len(promoted) == 0

    def test_demote_to_recall(self):
        wm, rm, am, tp = self._make()
        arch_id = am.add("archived item", importance=0.6)
        recall_id = tp.demote_to_recall(arch_id)
        assert recall_id is not None
        assert am.get(arch_id) is None
        item = rm.get(recall_id)
        assert item["content"] == "archived item"

    def test_demote_nonexistent(self):
        wm, rm, am, tp = self._make()
        assert tp.demote_to_recall("nope") is None

    def test_auto_promote(self):
        wm, rm, am, tp = self._make()
        result = tp.auto_promote()
        assert "working_to_recall" in result
        assert "recall_to_archival" in result

    def test_flush_working(self):
        wm, rm, am, tp = self._make()
        wm.add("a", importance=0.5)
        wm.add("b", importance=0.7)
        promoted = tp.flush_working()
        assert len(promoted) == 2
        assert len(wm.all()) == 0
        assert rm.count() == 2

    def test_promote_working_nonexistent(self):
        wm, rm, am, tp = self._make()
        promoted = tp.promote_working_to_recall("nonexistent")
        assert promoted == []


# =========================================================================
# TestTieredMemoryManager
# =========================================================================


class TestTieredMemoryManager:
    def _make(self):
        return TieredMemoryManager()

    def test_add_to_working(self):
        mgr = self._make()
        item_id = mgr.add("hello", tier="working")
        item = mgr.working.get(item_id)
        assert item["content"] == "hello"

    def test_add_to_recall(self):
        mgr = self._make()
        item_id = mgr.add("recall this", tier="recall")
        item = mgr.recall.get(item_id)
        assert item["content"] == "recall this"

    def test_add_to_archival(self):
        mgr = self._make()
        item_id = mgr.add("archive this", tier="archival", namespace="proj")
        item = mgr.archival.get(item_id)
        assert item["content"] == "archive this"
        assert item["namespace"] == "proj"

    def test_add_invalid_tier(self):
        mgr = self._make()
        with pytest.raises(ValueError):
            mgr.add("oops", tier="bogus")

    def test_cross_tier_get_working(self):
        mgr = self._make()
        item_id = mgr.add("w", tier="working")
        result = mgr.get(item_id)
        assert result["tier"] == "working"

    def test_cross_tier_get_recall(self):
        mgr = self._make()
        item_id = mgr.add("r", tier="recall")
        result = mgr.get(item_id)
        assert result["tier"] == "recall"

    def test_cross_tier_get_archival(self):
        mgr = self._make()
        item_id = mgr.add("a", tier="archival")
        result = mgr.get(item_id)
        assert result["tier"] == "archival"

    def test_get_missing(self):
        mgr = self._make()
        assert mgr.get("nope") is None

    def test_cross_tier_search(self):
        mgr = self._make()
        mgr.add("python in working", tier="working")
        mgr.add("python in recall", tier="recall")
        mgr.add("python in archival", tier="archival")
        results = mgr.search("python")
        tiers_found = {r["tier"] for r in results}
        assert tiers_found == {"working", "recall", "archival"}

    def test_search_specific_tiers(self):
        mgr = self._make()
        mgr.add("python in working", tier="working")
        mgr.add("python in recall", tier="recall")
        results = mgr.search("python", tiers=["working"])
        assert all(r["tier"] == "working" for r in results)

    def test_delete_from_any_tier(self):
        mgr = self._make()
        wid = mgr.add("w", tier="working")
        rid = mgr.add("r", tier="recall")
        assert mgr.delete(wid) is True
        assert mgr.delete(rid) is True
        assert mgr.get(wid) is None
        assert mgr.get(rid) is None

    def test_delete_nonexistent(self):
        mgr = self._make()
        assert mgr.delete("nope") is False

    def test_promote_working_to_recall(self):
        mgr = self._make()
        wid = mgr.add("promote me", tier="working")
        new_id = mgr.promote(wid, "working", "recall")
        assert new_id is not None
        assert mgr.working.get(wid) is None
        assert mgr.recall.get(new_id) is not None

    def test_promote_recall_to_archival(self):
        mgr = self._make()
        rid = mgr.add("archive me", tier="recall")
        new_id = mgr.promote(rid, "recall", "archival")
        assert new_id is not None
        item = mgr.archival.get(new_id)
        assert item["content"] == "archive me"

    def test_promote_invalid(self):
        mgr = self._make()
        with pytest.raises(ValueError):
            mgr.promote("x", "archival", "working")

    def test_stats(self):
        mgr = self._make()
        mgr.add("w", tier="working")
        mgr.add("r", tier="recall")
        mgr.add("a", tier="archival")
        stats = mgr.stats()
        assert stats["working"]["count"] == 1
        assert stats["recall"]["count"] == 1
        assert stats["archival"]["count"] == 1

    def test_flush_session(self):
        mgr = self._make()
        mgr.add("w1", tier="working")
        mgr.add("w2", tier="working")
        result = mgr.flush_session()
        assert len(result["flushed_to_recall"]) == 2
        assert len(mgr.working.all()) == 0
        assert mgr.recall.count() == 2

    def test_properties_accessible(self):
        mgr = self._make()
        assert isinstance(mgr.working, WorkingMemory)
        assert isinstance(mgr.recall, RecallMemory)
        assert isinstance(mgr.archival, ArchivalMemory)
        assert isinstance(mgr.promoter, TierPromoter)
