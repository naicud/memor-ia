"""Tests for importance scoring and self-editing memory."""

from __future__ import annotations

import time
from unittest import mock

import pytest

from memoria.core.importance import ImportanceScorer, ImportanceSignals, ImportanceTracker
from memoria.core.self_edit import (
    EditAction,
    EditDecision,
    MemoryBudget,
    SelfEditingMemory,
)


# ===========================================================================
# ImportanceSignals
# ===========================================================================


class TestImportanceSignals:
    def test_defaults(self):
        s = ImportanceSignals()
        assert s.access_count == 0
        assert s.last_accessed == 0.0
        assert s.connection_count == 0
        assert s.explicit_boost == 0.0
        assert s.relevance_score == 0.0
        assert s.word_count == 0
        assert s.has_entities is False
        assert s.referenced_by_count == 0

    def test_created_at_auto(self):
        before = time.time()
        s = ImportanceSignals()
        after = time.time()
        assert before <= s.created_at <= after


# ===========================================================================
# ImportanceScorer — individual signals
# ===========================================================================


class TestScorerFrequency:
    def test_zero_access(self):
        scorer = ImportanceScorer()
        s = ImportanceSignals(access_count=0, last_accessed=time.time())
        score = scorer.score(s)
        assert score >= 0.0

    def test_increasing_access_increases_score(self):
        scorer = ImportanceScorer()
        now = time.time()
        s1 = ImportanceSignals(access_count=1, last_accessed=now)
        s2 = ImportanceSignals(access_count=10, last_accessed=now)
        assert scorer.score(s2) > scorer.score(s1)

    def test_frequency_saturates(self):
        scorer = ImportanceScorer()
        now = time.time()
        s20 = ImportanceSignals(access_count=20, last_accessed=now)
        s100 = ImportanceSignals(access_count=100, last_accessed=now)
        diff = abs(scorer.score(s100) - scorer.score(s20))
        assert diff < 0.05  # nearly saturated


class TestScorerRecency:
    def test_just_accessed(self):
        scorer = ImportanceScorer()
        s = ImportanceSignals(last_accessed=time.time(), access_count=1)
        score = scorer.score(s)
        assert score > 0.3  # fresh access should contribute meaningfully

    def test_old_access_decays(self):
        scorer = ImportanceScorer(recency_half_life_days=7.0)
        now = time.time()
        recent = ImportanceSignals(last_accessed=now, access_count=1)
        old = ImportanceSignals(
            last_accessed=now - 30 * 86400, access_count=1
        )  # 30 days ago
        assert scorer.score(recent) > scorer.score(old)

    def test_never_accessed_zero_recency(self):
        scorer = ImportanceScorer()
        s = ImportanceSignals(last_accessed=0.0, access_count=0)
        # Should not crash, recency = 0
        score = scorer.score(s)
        assert score >= 0.0

    def test_half_life_decay_curve(self):
        scorer = ImportanceScorer(recency_half_life_days=14.0)
        now = time.time()
        # After one half-life the recency component should be ~0.5
        s = ImportanceSignals(last_accessed=now - 14 * 86400, access_count=0)
        recency_component = scorer._recency_score(s.last_accessed)
        assert 0.45 <= recency_component <= 0.55


class TestScorerMultiSignal:
    def test_all_signals_high(self):
        scorer = ImportanceScorer()
        s = ImportanceSignals(
            access_count=20,
            last_accessed=time.time(),
            connection_count=5,
            relevance_score=0.9,
            word_count=200,
            has_entities=True,
            referenced_by_count=3,
        )
        assert scorer.score(s) > 0.7

    def test_all_signals_low(self):
        scorer = ImportanceScorer()
        s = ImportanceSignals(
            access_count=0,
            last_accessed=0.0,
            connection_count=0,
            relevance_score=0.0,
            word_count=0,
        )
        assert scorer.score(s) < 0.1

    def test_explicit_boost_positive(self):
        scorer = ImportanceScorer()
        base = ImportanceSignals(access_count=1, last_accessed=time.time())
        boosted = ImportanceSignals(
            access_count=1, last_accessed=time.time(), explicit_boost=1.0
        )
        assert scorer.score(boosted) > scorer.score(base)

    def test_explicit_boost_negative(self):
        scorer = ImportanceScorer()
        base = ImportanceSignals(
            access_count=5,
            last_accessed=time.time(),
            relevance_score=0.5,
        )
        penalized = ImportanceSignals(
            access_count=5,
            last_accessed=time.time(),
            relevance_score=0.5,
            explicit_boost=-1.0,
        )
        assert scorer.score(penalized) < scorer.score(base)

    def test_score_clamped_to_unit(self):
        scorer = ImportanceScorer()
        # Even with max boost the score must not exceed 1
        s = ImportanceSignals(
            access_count=100,
            last_accessed=time.time(),
            relevance_score=1.0,
            connection_count=50,
            word_count=500,
            has_entities=True,
            referenced_by_count=10,
            explicit_boost=1.0,
        )
        assert scorer.score(s) <= 1.0

        # Even with min boost the score must not go below 0
        s2 = ImportanceSignals(explicit_boost=-1.0)
        assert scorer.score(s2) >= 0.0


class TestScorerWeights:
    def test_weights_normalised(self):
        scorer = ImportanceScorer(
            frequency_weight=1.0,
            recency_weight=1.0,
            relevance_weight=1.0,
            connectivity_weight=1.0,
            richness_weight=1.0,
        )
        # After normalisation each should be 0.2
        assert abs(scorer._weights["frequency"] - 0.2) < 1e-9

    def test_zero_total_weight_raises(self):
        with pytest.raises(ValueError):
            ImportanceScorer(
                frequency_weight=0,
                recency_weight=0,
                relevance_weight=0,
                connectivity_weight=0,
                richness_weight=0,
            )


class TestBatchScoring:
    def test_batch_matches_individual(self):
        scorer = ImportanceScorer()
        now = time.time()
        # Use last_accessed=0 to avoid time-dependent recency drift between calls
        signals = [
            ImportanceSignals(access_count=i, last_accessed=0) for i in range(5)
        ]
        batch = scorer.score_batch(signals)
        individual = [scorer.score(s) for s in signals]
        assert batch == individual

    def test_batch_empty(self):
        scorer = ImportanceScorer()
        assert scorer.score_batch([]) == []


# ===========================================================================
# Threshold decisions
# ===========================================================================


class TestThresholdDecisions:
    def test_should_forget_low(self):
        scorer = ImportanceScorer()
        s = ImportanceSignals()  # all zeros
        assert scorer.should_forget(s)

    def test_should_not_forget_high(self):
        scorer = ImportanceScorer()
        s = ImportanceSignals(
            access_count=10, last_accessed=time.time(), relevance_score=0.8
        )
        assert not scorer.should_forget(s)

    def test_should_compress_mid(self):
        scorer = ImportanceScorer()
        # A memory that scores around 0.07–0.14 should be in compress range
        s = ImportanceSignals(access_count=1, last_accessed=time.time())
        score = scorer.score(s)
        if 0.05 <= score < 0.15:
            assert scorer.should_compress(s)

    def test_should_promote_high(self):
        scorer = ImportanceScorer()
        s = ImportanceSignals(
            access_count=20,
            last_accessed=time.time(),
            relevance_score=0.9,
            connection_count=5,
            word_count=200,
            has_entities=True,
        )
        assert scorer.should_promote(s)

    def test_custom_thresholds(self):
        scorer = ImportanceScorer()
        s = ImportanceSignals()
        # With very high thresholds nothing passes
        assert not scorer.should_promote(s, threshold=0.99)
        # With very low thresholds everything passes
        assert scorer.should_forget(s, threshold=1.0)


# ===========================================================================
# ImportanceTracker
# ===========================================================================


class TestImportanceTracker:
    def test_record_access(self):
        t = ImportanceTracker()
        t.record_access("m1")
        sig = t.get_signals("m1")
        assert sig.access_count == 1
        assert sig.last_accessed > 0

    def test_multiple_accesses(self):
        t = ImportanceTracker()
        t.record_access("m1")
        t.record_access("m1")
        t.record_access("m1")
        assert t.get_signals("m1").access_count == 3

    def test_record_creation(self):
        t = ImportanceTracker()
        t.record_creation("m1", word_count=150, has_entities=True)
        sig = t.get_signals("m1")
        assert sig.word_count == 150
        assert sig.has_entities is True
        assert sig.created_at > 0

    def test_set_explicit_boost_clamped(self):
        t = ImportanceTracker()
        t.set_explicit_boost("m1", 5.0)
        assert t.get_signals("m1").explicit_boost == 1.0
        t.set_explicit_boost("m1", -5.0)
        assert t.get_signals("m1").explicit_boost == -1.0

    def test_set_relevance_clamped(self):
        t = ImportanceTracker()
        t.set_relevance("m1", 2.0)
        assert t.get_signals("m1").relevance_score == 1.0
        t.set_relevance("m1", -0.5)
        assert t.get_signals("m1").relevance_score == 0.0

    def test_set_connections(self):
        t = ImportanceTracker()
        t.set_connections("m1", 7)
        assert t.get_signals("m1").connection_count == 7
        t.set_connections("m1", -1)
        assert t.get_signals("m1").connection_count == 0

    def test_get_all_signals(self):
        t = ImportanceTracker()
        t.record_access("a")
        t.record_access("b")
        all_sigs = t.get_all_signals()
        assert set(all_sigs.keys()) == {"a", "b"}

    def test_remove(self):
        t = ImportanceTracker()
        t.record_access("m1")
        t.remove("m1")
        # Should create fresh default on next access
        sig = t.get_signals("m1")
        assert sig.access_count == 0

    def test_remove_nonexistent(self):
        t = ImportanceTracker()
        t.remove("nonexistent")  # should not raise


# ===========================================================================
# SelfEditingMemory — explicit edits
# ===========================================================================


class TestSelfEditingMemoryExplicit:
    def test_keep(self):
        sem = SelfEditingMemory()
        d = sem.keep("m1", reason="important info")
        assert d.action == EditAction.KEEP
        assert d.memory_id == "m1"
        assert d.confidence == 1.0

    def test_discard(self):
        sem = SelfEditingMemory()
        d = sem.discard("m1", reason="outdated")
        assert d.action == EditAction.DISCARD

    def test_compress(self):
        sem = SelfEditingMemory()
        d = sem.compress("m1", new_content="short version", reason="too long")
        assert d.action == EditAction.COMPRESS
        assert d.new_content == "short version"

    def test_promote(self):
        sem = SelfEditingMemory()
        d = sem.promote("m1", target_tier="working", reason="frequently used")
        assert d.action == EditAction.PROMOTE
        assert d.target_tier == "working"

    def test_demote(self):
        sem = SelfEditingMemory()
        d = sem.demote("m1", target_tier="archival", reason="rarely used")
        assert d.action == EditAction.DEMOTE
        assert d.target_tier == "archival"

    def test_merge(self):
        sem = SelfEditingMemory()
        d = sem.merge(["m1", "m2", "m3"], merged_content="combined", reason="overlap")
        assert d.action == EditAction.MERGE
        assert d.memory_id == "m1"
        assert d.merged_ids == ["m1", "m2", "m3"]
        assert d.new_content == "combined"

    def test_merge_empty_raises(self):
        sem = SelfEditingMemory()
        with pytest.raises(ValueError):
            sem.merge([], merged_content="nothing")


# ===========================================================================
# SelfEditingMemory — auto-manage
# ===========================================================================


class TestAutoManage:
    def _make_memories(self, n: int, tier: str = "recall") -> list[dict]:
        return [{"id": f"m{i}", "tier": tier} for i in range(n)]

    def test_no_action_under_budget(self):
        sem = SelfEditingMemory(
            budget=MemoryBudget(max_recall_memories=100)
        )
        memories = self._make_memories(10)
        scores = {f"m{i}": 0.5 for i in range(10)}
        decisions = sem.auto_manage(memories, scores)
        # No budget pressure — only promotions for high-score items
        discard_count = sum(1 for d in decisions if d.action == EditAction.DISCARD)
        assert discard_count == 0

    def test_forget_over_threshold(self):
        budget = MemoryBudget(max_recall_memories=10, forget_threshold=0.95)
        sem = SelfEditingMemory(budget=budget)
        memories = self._make_memories(10)  # 10/10 = 100% > 95%
        scores = {f"m{i}": 0.01 * i for i in range(10)}  # m0=0.0 … m9=0.09
        decisions = sem.auto_manage(memories, scores)
        discard_ids = [d.memory_id for d in decisions if d.action == EditAction.DISCARD]
        assert len(discard_ids) > 0
        # Lowest scored memories should be discarded
        assert "m0" in discard_ids

    def test_compress_at_threshold(self):
        budget = MemoryBudget(
            max_recall_memories=20,
            compress_threshold=0.85,
            forget_threshold=0.95,
        )
        sem = SelfEditingMemory(budget=budget)
        memories = self._make_memories(18)  # 18/20 = 90% > 85%
        scores = {f"m{i}": 0.10 for i in range(18)}
        decisions = sem.auto_manage(memories, scores)
        compress_count = sum(
            1 for d in decisions if d.action == EditAction.COMPRESS
        )
        assert compress_count > 0

    def test_promote_high_importance(self):
        sem = SelfEditingMemory()
        memories = [{"id": "m1", "tier": "recall"}]
        scores = {"m1": 0.85}
        decisions = sem.auto_manage(memories, scores)
        promote_ids = [
            d.memory_id for d in decisions if d.action == EditAction.PROMOTE
        ]
        assert "m1" in promote_ids

    def test_no_promote_working_tier(self):
        sem = SelfEditingMemory()
        memories = [{"id": "m1", "tier": "working"}]
        scores = {"m1": 0.85}
        decisions = sem.auto_manage(memories, scores)
        promote_count = sum(1 for d in decisions if d.action == EditAction.PROMOTE)
        assert promote_count == 0


# ===========================================================================
# Budget checking
# ===========================================================================


class TestBudgetChecking:
    def test_under_budget(self):
        sem = SelfEditingMemory()
        result = sem.check_budget({"working": 10, "recall": 100, "archival": 500})
        assert result["action_needed"] == "none"
        assert result["working"]["usage"] == pytest.approx(0.2)

    def test_compress_threshold(self):
        budget = MemoryBudget(max_working_memories=100, compress_threshold=0.85)
        sem = SelfEditingMemory(budget=budget)
        result = sem.check_budget({"working": 90})
        assert result["action_needed"] == "compress"

    def test_forget_threshold(self):
        budget = MemoryBudget(max_working_memories=100, forget_threshold=0.95)
        sem = SelfEditingMemory(budget=budget)
        result = sem.check_budget({"working": 96})
        assert result["action_needed"] == "forget"

    def test_empty_counts(self):
        sem = SelfEditingMemory()
        result = sem.check_budget({})
        assert result["action_needed"] == "none"
        assert result["working"]["current"] == 0


# ===========================================================================
# Edit history
# ===========================================================================


class TestEditHistory:
    def test_history_recorded(self):
        sem = SelfEditingMemory()
        sem.keep("m1")
        sem.discard("m2")
        history = sem.get_edit_history()
        assert len(history) == 2
        # Most recent first
        assert history[0].action == EditAction.DISCARD
        assert history[1].action == EditAction.KEEP

    def test_history_limit(self):
        sem = SelfEditingMemory()
        for i in range(10):
            sem.keep(f"m{i}")
        history = sem.get_edit_history(limit=3)
        assert len(history) == 3

    def test_edits_for_memory(self):
        sem = SelfEditingMemory()
        sem.keep("m1")
        sem.discard("m2")
        sem.compress("m1", new_content="short")
        edits = sem.get_edits_for_memory("m1")
        assert len(edits) == 2
        assert edits[0].action == EditAction.KEEP
        assert edits[1].action == EditAction.COMPRESS

    def test_history_rotation(self):
        sem = SelfEditingMemory()
        sem._max_edit_history = 5
        for i in range(10):
            sem.keep(f"m{i}")
        assert len(sem._edit_history) == 5
        # Oldest entries should have been dropped
        assert sem._edit_history[0].memory_id == "m5"


# ===========================================================================
# Statistics
# ===========================================================================


class TestStats:
    def test_stats_empty(self):
        sem = SelfEditingMemory()
        s = sem.stats()
        assert s["total_edits"] == 0
        assert s["edits_by_action"] == {}

    def test_stats_counts(self):
        sem = SelfEditingMemory()
        sem.keep("m1")
        sem.keep("m2")
        sem.discard("m3")
        s = sem.stats()
        assert s["total_edits"] == 3
        assert s["edits_by_action"]["keep"] == 2
        assert s["edits_by_action"]["discard"] == 1

    def test_stats_budget_included(self):
        budget = MemoryBudget(max_working_memories=42)
        sem = SelfEditingMemory(budget=budget)
        s = sem.stats()
        assert s["budget"]["max_working_memories"] == 42


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    def test_score_with_all_zeros(self):
        scorer = ImportanceScorer()
        s = ImportanceSignals(
            access_count=0,
            last_accessed=0.0,
            created_at=0.0,
            connection_count=0,
            relevance_score=0.0,
            word_count=0,
        )
        score = scorer.score(s)
        assert 0.0 <= score <= 1.0

    def test_auto_manage_empty_memories(self):
        sem = SelfEditingMemory()
        decisions = sem.auto_manage([], {})
        assert decisions == []

    def test_auto_manage_missing_scores(self):
        sem = SelfEditingMemory()
        memories = [{"id": "m1", "tier": "recall"}]
        decisions = sem.auto_manage(memories, {})  # no scores provided
        # Should not crash — defaults to 0.0
        assert isinstance(decisions, list)

    def test_tracker_get_signals_creates_default(self):
        t = ImportanceTracker()
        sig = t.get_signals("new_id")
        assert sig.access_count == 0

    def test_edit_decision_defaults(self):
        d = EditDecision(memory_id="x", action=EditAction.KEEP)
        assert d.reason == ""
        assert d.new_content == ""
        assert d.target_tier == ""
        assert d.confidence == 0.5
        assert d.merged_ids == []


class TestMemoriaFacadeMerge:
    """Test MERGE action through the Memoria.self_edit_action facade."""

    def test_merge_action_returns_decision(self):
        from memoria import Memoria
        import tempfile
        d = tempfile.mkdtemp()
        try:
            m = Memoria(project_dir=d)
            result = m.self_edit_action(
                "m1", action="merge",
                memory_ids=["m1", "m2"],
                new_content="combined content",
                reason="overlap",
            )
            assert result["action"] == "merge"
            assert result["memory_id"] == "m1"
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)

    def test_merge_action_requires_new_content(self):
        from memoria import Memoria
        import tempfile
        d = tempfile.mkdtemp()
        try:
            m = Memoria(project_dir=d)
            result = m.self_edit_action(
                "m1", action="merge",
                memory_ids=["m1", "m2"],
                new_content="",  # empty
            )
            assert "error" in result
            assert "new_content" in result["error"]
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)
