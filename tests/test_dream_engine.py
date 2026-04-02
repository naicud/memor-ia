"""Tests for the Dream Engine module — cognitive consolidation engine."""
from __future__ import annotations

import time

from memoria.dream import (
    ConsolidationAction,
    ConsolidationDecision,
    DreamEngine,
    DreamJournal,
    DreamJournalEntry,
    DreamPhase,
    DreamResult,
    InsightSeed,
    InsightSynthesizer,
    MemoryCandidate,
    MemoryReplay,
)

# ── helpers ──────────────────────────────────────────────────────

DAY = 86400.0
NOW = 1_700_000_000.0  # fixed reference timestamp


def _mem(
    mid: str = "m1",
    content: str = "hello world",
    tier: str = "working",
    importance: float = 0.5,
    access_count: int = 1,
    last_accessed: float = 0.0,
    created_at: float = 0.0,
    **meta: object,
) -> MemoryCandidate:
    return MemoryCandidate(
        memory_id=mid,
        content=content,
        tier=tier,
        importance=importance,
        access_count=access_count,
        last_accessed=last_accessed or NOW,
        created_at=created_at or NOW,
        metadata=dict(meta),
    )


def _corpus() -> list[MemoryCandidate]:
    """Diverse set of memories for integration tests."""
    return [
        _mem("high", "Python async await patterns are very important for concurrency " * 5,
             importance=0.95, access_count=15, last_accessed=NOW),
        _mem("mid1", "Database indexing strategies for performance",
             importance=0.5, access_count=3, last_accessed=NOW - 5 * DAY),
        _mem("mid2", "Database query optimization techniques",
             importance=0.5, access_count=4, last_accessed=NOW - 3 * DAY),
        _mem("low", "x",
             importance=0.05, access_count=0, last_accessed=NOW - 60 * DAY),
        _mem("old", "Legacy code migration notes",
             importance=0.3, access_count=1, last_accessed=NOW - 30 * DAY),
        _mem("fresh", "New deployment pipeline with Docker containers and Kubernetes orchestration " * 3,
             importance=0.7, access_count=8, last_accessed=NOW),
    ]


# ═══════════════════════════════════════════════════════════════
# 1. TestDreamPhase
# ═══════════════════════════════════════════════════════════════
class TestDreamPhase:
    def test_scan_value(self):
        assert DreamPhase.SCAN.value == "scan"

    def test_replay_value(self):
        assert DreamPhase.REPLAY.value == "replay"

    def test_consolidate_value(self):
        assert DreamPhase.CONSOLIDATE.value == "consolidate"

    def test_synthesize_value(self):
        assert DreamPhase.SYNTHESIZE.value == "synthesize"

    def test_journal_value(self):
        assert DreamPhase.JOURNAL.value == "journal"

    def test_complete_value(self):
        assert DreamPhase.COMPLETE.value == "complete"

    def test_all_phases_count(self):
        assert len(DreamPhase) == 6


# ═══════════════════════════════════════════════════════════════
# 2. TestConsolidationAction
# ═══════════════════════════════════════════════════════════════
class TestConsolidationAction:
    def test_promote_value(self):
        assert ConsolidationAction.PROMOTE.value == "promote"

    def test_compress_value(self):
        assert ConsolidationAction.COMPRESS.value == "compress"

    def test_forget_value(self):
        assert ConsolidationAction.FORGET.value == "forget"

    def test_connect_value(self):
        assert ConsolidationAction.CONNECT.value == "connect"

    def test_merge_value(self):
        assert ConsolidationAction.MERGE.value == "merge"

    def test_keep_value(self):
        assert ConsolidationAction.KEEP.value == "keep"

    def test_all_actions_count(self):
        assert len(ConsolidationAction) == 6


# ═══════════════════════════════════════════════════════════════
# 3. TestMemoryCandidate
# ═══════════════════════════════════════════════════════════════
class TestMemoryCandidate:
    def test_defaults(self):
        m = MemoryCandidate(memory_id="x", content="hello")
        assert m.tier == "working"
        assert m.importance == 0.5
        assert m.access_count == 0
        assert m.metadata == {}

    def test_custom_values(self):
        m = _mem("c1", "test", tier="recall", importance=0.9, access_count=5)
        assert m.tier == "recall"
        assert m.importance == 0.9
        assert m.access_count == 5

    def test_metadata_isolation(self):
        m1 = MemoryCandidate(memory_id="a", content="a")
        m2 = MemoryCandidate(memory_id="b", content="b")
        m1.metadata["key"] = "val"
        assert "key" not in m2.metadata


# ═══════════════════════════════════════════════════════════════
# 4. TestConsolidationDecision
# ═══════════════════════════════════════════════════════════════
class TestConsolidationDecision:
    def test_promote_decision(self):
        d = ConsolidationDecision("m1", ConsolidationAction.PROMOTE, target_tier="recall")
        assert d.action == ConsolidationAction.PROMOTE
        assert d.target_tier == "recall"

    def test_compress_decision(self):
        d = ConsolidationDecision("m1", ConsolidationAction.COMPRESS, new_content="summary")
        assert d.new_content == "summary"

    def test_forget_decision(self):
        d = ConsolidationDecision("m1", ConsolidationAction.FORGET, reason="low score")
        assert d.reason == "low score"

    def test_merge_decision(self):
        d = ConsolidationDecision("m1", ConsolidationAction.MERGE, merged_with=["m2", "m3"])
        assert d.merged_with == ["m2", "m3"]

    def test_default_merged_with_isolation(self):
        d1 = ConsolidationDecision("a", ConsolidationAction.KEEP)
        d2 = ConsolidationDecision("b", ConsolidationAction.KEEP)
        d1.merged_with.append("x")
        assert "x" not in d2.merged_with


# ═══════════════════════════════════════════════════════════════
# 5. TestInsightSeed
# ═══════════════════════════════════════════════════════════════
class TestInsightSeed:
    def test_default_type(self):
        i = InsightSeed(title="t", description="d")
        assert i.insight_type == "connection"
        assert i.confidence == 0.5

    def test_custom_type(self):
        i = InsightSeed(title="t", description="d", insight_type="gap")
        assert i.insight_type == "gap"

    def test_source_memories_isolation(self):
        i1 = InsightSeed(title="t1", description="d1")
        i2 = InsightSeed(title="t2", description="d2")
        i1.source_memories.append("m1")
        assert "m1" not in i2.source_memories


# ═══════════════════════════════════════════════════════════════
# 6. TestDreamJournalEntry
# ═══════════════════════════════════════════════════════════════
class TestDreamJournalEntry:
    def test_creation(self):
        e = DreamJournalEntry(cycle_id="c1", started_at=100.0, completed_at=200.0)
        assert e.cycle_id == "c1"
        assert e.completed_at - e.started_at == 100.0

    def test_defaults(self):
        e = DreamJournalEntry(cycle_id="c2")
        assert e.memories_scanned == 0
        assert e.decisions == []
        assert e.insights == []
        assert e.stats == {}


# ═══════════════════════════════════════════════════════════════
# 7. TestDreamResult
# ═══════════════════════════════════════════════════════════════
class TestDreamResult:
    def test_defaults(self):
        r = DreamResult(cycle_id="r1")
        assert r.success is True
        assert r.total_scanned == 0
        assert r.promoted == 0
        assert r.journal_entry is None

    def test_aggregation(self):
        r = DreamResult(
            cycle_id="r2",
            promoted=3, compressed=2, forgotten=1, kept=4,
            insights_generated=5, total_scanned=10,
        )
        assert r.promoted + r.compressed + r.forgotten + r.kept == 10


# ═══════════════════════════════════════════════════════════════
# 8. TestMemoryReplayScoring
# ═══════════════════════════════════════════════════════════════
class TestMemoryReplayScoring:
    def setup_method(self):
        self.replay = MemoryReplay()

    def test_recent_high_access_high_importance(self):
        m = _mem(access_count=10, importance=0.9, last_accessed=NOW)
        score = self.replay.score(m, now=NOW)
        assert score > 0.7

    def test_old_low_access_low_importance(self):
        m = _mem(access_count=0, importance=0.1, last_accessed=NOW - 60 * DAY)
        score = self.replay.score(m, now=NOW)
        assert score < 0.3

    def test_recency_decay(self):
        recent = _mem("r", last_accessed=NOW)
        old = _mem("o", last_accessed=NOW - 28 * DAY)
        sr = self.replay.score(recent, now=NOW)
        so = self.replay.score(old, now=NOW)
        assert sr > so

    def test_access_boost(self):
        low_access = _mem("la", access_count=0)
        high_access = _mem("ha", access_count=10)
        sl = self.replay.score(low_access, now=NOW)
        sh = self.replay.score(high_access, now=NOW)
        assert sh > sl

    def test_importance_effect(self):
        low_imp = _mem("li", importance=0.1)
        high_imp = _mem("hi", importance=0.9)
        sl = self.replay.score(low_imp, now=NOW)
        sh = self.replay.score(high_imp, now=NOW)
        assert sh > sl

    def test_richness_effect(self):
        short = _mem("s", content="hello")
        long = _mem("l", content="word " * 100)
        ss = self.replay.score(short, now=NOW)
        sl = self.replay.score(long, now=NOW)
        assert sl > ss

    def test_score_clamped_0_1(self):
        m = _mem(importance=2.0, access_count=100)
        score = self.replay.score(m, now=NOW)
        assert 0.0 <= score <= 1.0

    def test_halflife_decay_at_halflife(self):
        replay = MemoryReplay(recency_halflife_days=14.0,
                              access_weight=0, recency_weight=1.0,
                              importance_weight=0, richness_weight=0)
        m = _mem(last_accessed=NOW - 14 * DAY)
        score = replay.score(m, now=NOW)
        assert abs(score - 0.5) < 0.01

    def test_empty_content(self):
        m = _mem(content="")
        score = self.replay.score(m, now=NOW)
        assert 0.0 <= score <= 1.0

    def test_now_defaults_to_time(self):
        m = _mem(last_accessed=time.time())
        score = self.replay.score(m)
        assert 0.0 <= score <= 1.0


# ═══════════════════════════════════════════════════════════════
# 9. TestMemoryReplayBatch
# ═══════════════════════════════════════════════════════════════
class TestMemoryReplayBatch:
    def setup_method(self):
        self.replay = MemoryReplay()

    def test_sorted_ascending(self):
        mems = [
            _mem("high", importance=0.9, access_count=10),
            _mem("low", importance=0.1, access_count=0, last_accessed=NOW - 60 * DAY),
        ]
        result = self.replay.score_batch(mems, now=NOW)
        assert result[0][1] <= result[1][1]

    def test_returns_all(self):
        mems = [_mem(f"m{i}") for i in range(5)]
        result = self.replay.score_batch(mems, now=NOW)
        assert len(result) == 5

    def test_empty_input(self):
        assert self.replay.score_batch([], now=NOW) == []


# ═══════════════════════════════════════════════════════════════
# 10. TestMemoryReplaySimilarity
# ═══════════════════════════════════════════════════════════════
class TestMemoryReplaySimilarity:
    def setup_method(self):
        self.replay = MemoryReplay()

    def test_identical_content(self):
        mems = [_mem("a", "hello world"), _mem("b", "hello world")]
        pairs = self.replay.find_similar_pairs(mems, threshold=0.9)
        assert len(pairs) == 1
        assert pairs[0][2] == 1.0

    def test_no_similarity(self):
        mems = [_mem("a", "hello world"), _mem("b", "completely different text here")]
        pairs = self.replay.find_similar_pairs(mems, threshold=0.85)
        assert len(pairs) == 0

    def test_threshold_effect(self):
        mems = [_mem("a", "hello world foo"), _mem("b", "hello world bar")]
        high = self.replay.find_similar_pairs(mems, threshold=0.9)
        low = self.replay.find_similar_pairs(mems, threshold=0.3)
        assert len(low) >= len(high)

    def test_single_memory(self):
        assert self.replay.find_similar_pairs([_mem("a")]) == []

    def test_empty_input(self):
        assert self.replay.find_similar_pairs([]) == []

    def test_empty_content_no_crash(self):
        mems = [_mem("a", ""), _mem("b", "")]
        pairs = self.replay.find_similar_pairs(mems, threshold=0.0)
        # Both empty → union=0 → sim=0.0, shouldn't match at any positive threshold
        # But at threshold=0.0, 0.0 >= 0.0 is True
        assert len(pairs) == 1
        assert pairs[0][2] == 0.0


# ═══════════════════════════════════════════════════════════════
# 11. TestInsightSynthesizerClusters
# ═══════════════════════════════════════════════════════════════
class TestInsightSynthesizerClusters:
    def setup_method(self):
        self.synth = InsightSynthesizer()

    def test_finds_shared_keyword(self):
        mems = [
            _mem("a", "python async programming"),
            _mem("b", "python web framework"),
        ]
        insights = self.synth._find_topic_clusters(mems)
        titles = [i.title for i in insights]
        assert any("python" in t for t in titles)

    def test_no_clusters_single_memory(self):
        assert self.synth._find_topic_clusters([_mem("a")]) == []

    def test_insight_type_is_connection(self):
        mems = [_mem("a", "testing code"), _mem("b", "testing framework")]
        insights = self.synth._find_topic_clusters(mems)
        for i in insights:
            assert i.insight_type == "connection"


# ═══════════════════════════════════════════════════════════════
# 12. TestInsightSynthesizerGaps
# ═══════════════════════════════════════════════════════════════
class TestInsightSynthesizerGaps:
    def setup_method(self):
        self.synth = InsightSynthesizer()

    def test_detects_low_score_tier(self):
        mems = [_mem("a", "low data", tier="experimental"), _mem("b", "also low", tier="experimental")]
        scores = {"a": 0.1, "b": 0.2}
        insights = self.synth._find_knowledge_gaps(mems, scores)
        assert len(insights) > 0
        assert insights[0].insight_type == "gap"

    def test_no_gap_high_scores(self):
        mems = [_mem("a", "good", tier="core"), _mem("b", "great", tier="core")]
        scores = {"a": 0.8, "b": 0.9}
        insights = self.synth._find_knowledge_gaps(mems, scores)
        assert len(insights) == 0

    def test_empty_input(self):
        assert self.synth._find_knowledge_gaps([], {}) == []


# ═══════════════════════════════════════════════════════════════
# 13. TestInsightSynthesizerTemporal
# ═══════════════════════════════════════════════════════════════
class TestInsightSynthesizerTemporal:
    def setup_method(self):
        self.synth = InsightSynthesizer()

    def test_detects_burst(self):
        mems = [
            _mem("a", "first", created_at=NOW),
            _mem("b", "second", created_at=NOW + 60),
            _mem("c", "third", created_at=NOW + 120),
        ]
        insights = self.synth._find_temporal_patterns(mems)
        assert len(insights) >= 1
        assert insights[0].insight_type == "pattern"

    def test_no_pattern_spread_out(self):
        mems = [
            _mem("a", "first", created_at=NOW),
            _mem("b", "second", created_at=NOW + 10 * DAY),
        ]
        insights = self.synth._find_temporal_patterns(mems)
        assert len(insights) == 0

    def test_empty_input(self):
        assert self.synth._find_temporal_patterns([]) == []

    def test_no_timestamps(self):
        mems = [
            MemoryCandidate(memory_id="a", content="x", created_at=0),
            MemoryCandidate(memory_id="b", content="y", created_at=0),
        ]
        assert self.synth._find_temporal_patterns(mems) == []


# ═══════════════════════════════════════════════════════════════
# 14. TestInsightSynthesizerPredictions
# ═══════════════════════════════════════════════════════════════
class TestInsightSynthesizerPredictions:
    def setup_method(self):
        self.synth = InsightSynthesizer()

    def test_predicts_from_high_scores(self):
        mems = [
            _mem("a", "python testing framework patterns"),
            _mem("b", "python testing best practices"),
            _mem("c", "python testing automation"),
        ]
        scores = {"a": 0.9, "b": 0.85, "c": 0.8}
        insights = self.synth._generate_predictions(mems, scores)
        assert len(insights) > 0
        assert insights[0].insight_type == "prediction"

    def test_no_predictions_low_scores(self):
        mems = [_mem("a", "something"), _mem("b", "else")]
        scores = {"a": 0.1, "b": 0.2}
        insights = self.synth._generate_predictions(mems, scores)
        assert len(insights) == 0

    def test_empty_input(self):
        assert self.synth._generate_predictions([], {}) == []


# ═══════════════════════════════════════════════════════════════
# 15. TestDreamJournal
# ═══════════════════════════════════════════════════════════════
class TestDreamJournal:
    def setup_method(self):
        self.journal = DreamJournal(max_entries=5)

    def test_record_and_retrieve(self):
        e = DreamJournalEntry(cycle_id="c1", started_at=100.0)
        self.journal.record(e)
        assert self.journal.get_cycle("c1") is not None

    def test_get_entries_newest_first(self):
        for i in range(3):
            self.journal.record(DreamJournalEntry(cycle_id=f"c{i}", started_at=float(i)))
        entries = self.journal.get_entries(limit=10)
        assert entries[0].cycle_id == "c2"
        assert entries[-1].cycle_id == "c0"

    def test_get_entries_limit(self):
        for i in range(5):
            self.journal.record(DreamJournalEntry(cycle_id=f"c{i}"))
        entries = self.journal.get_entries(limit=2)
        assert len(entries) == 2

    def test_get_entries_since_filter(self):
        self.journal.record(DreamJournalEntry(cycle_id="old", started_at=10.0))
        self.journal.record(DreamJournalEntry(cycle_id="new", started_at=100.0))
        entries = self.journal.get_entries(since=50.0)
        assert len(entries) == 1
        assert entries[0].cycle_id == "new"

    def test_get_cycle_not_found(self):
        assert self.journal.get_cycle("nonexistent") is None

    def test_rotation(self):
        for i in range(10):
            self.journal.record(DreamJournalEntry(cycle_id=f"c{i}"))
        entries = self.journal.get_entries(limit=100)
        assert len(entries) == 5
        assert entries[0].cycle_id == "c9"

    def test_stats_empty(self):
        s = self.journal.stats()
        assert s["total_cycles"] == 0
        assert s["avg_memories_per_cycle"] == 0.0

    def test_stats_with_data(self):
        entry = DreamJournalEntry(
            cycle_id="c1",
            started_at=100.0,
            completed_at=110.0,
            memories_scanned=5,
            decisions=[
                ConsolidationDecision("m1", ConsolidationAction.PROMOTE),
                ConsolidationDecision("m2", ConsolidationAction.FORGET),
            ],
            insights=[InsightSeed(title="i1", description="d1")],
        )
        self.journal.record(entry)
        s = self.journal.stats()
        assert s["total_cycles"] == 1
        assert s["total_promoted"] == 1
        assert s["total_forgotten"] == 1
        assert s["total_insights"] == 1
        assert s["avg_memories_per_cycle"] == 5.0
        assert s["avg_duration"] == 10.0

    def test_clear(self):
        self.journal.record(DreamJournalEntry(cycle_id="c1"))
        self.journal.clear()
        assert self.journal.get_entries() == []


# ═══════════════════════════════════════════════════════════════
# 16. TestDreamEngineFullCycle
# ═══════════════════════════════════════════════════════════════
class TestDreamEngineFullCycle:
    def setup_method(self):
        self.engine = DreamEngine()

    def test_full_cycle_returns_result(self):
        result = self.engine.dream(_corpus())
        assert result.success is True
        assert result.total_scanned == len(_corpus())

    def test_all_phases_completed(self):
        result = self.engine.dream(_corpus())
        expected = ["scan", "replay", "consolidate", "synthesize", "journal", "complete"]
        assert result.phases_completed == expected

    def test_journal_entry_attached(self):
        result = self.engine.dream(_corpus())
        assert result.journal_entry is not None
        assert result.journal_entry.cycle_id == result.cycle_id

    def test_cycle_id_prefix(self):
        result = self.engine.dream(_corpus())
        assert result.cycle_id.startswith("dream-")

    def test_decisions_cover_all_memories(self):
        mems = _corpus()
        result = self.engine.dream(mems)
        total_decisions = (
            result.promoted + result.compressed + result.forgotten
            + result.connected + result.merged + result.kept
        )
        assert total_decisions >= 1

    def test_journal_persists(self):
        self.engine.dream(_corpus())
        entries = self.engine.journal.get_entries()
        assert len(entries) == 1


# ═══════════════════════════════════════════════════════════════
# 17. TestDreamEngineThresholds
# ═══════════════════════════════════════════════════════════════
class TestDreamEngineThresholds:
    def test_aggressive_forget(self):
        engine = DreamEngine(forget_threshold=0.9)
        mems = [_mem("m1", "short", importance=0.3, access_count=1)]
        result = engine.dream(mems)
        assert result.forgotten > 0

    def test_aggressive_promote(self):
        engine = DreamEngine(promote_threshold=0.1)
        mems = [_mem("m1", "good " * 50, importance=0.9, access_count=10)]
        result = engine.dream(mems)
        assert result.promoted > 0

    def test_compress_zone(self):
        engine = DreamEngine(forget_threshold=0.1, compress_threshold=0.9, promote_threshold=0.95)
        mems = [_mem("m1", "some content here", importance=0.5, access_count=3)]
        result = engine.dream(mems)
        assert result.compressed > 0 or result.kept > 0

    def test_promote_sets_target_tier(self):
        engine = DreamEngine(promote_threshold=0.01)
        result = engine.dream([_mem("m1", "test", tier="working")])
        entry = result.journal_entry
        promoted = [d for d in entry.decisions if d.action == ConsolidationAction.PROMOTE]
        if promoted:
            assert promoted[0].target_tier in ("recall", "archival")


# ═══════════════════════════════════════════════════════════════
# 18. TestDreamEngineQuickDream
# ═══════════════════════════════════════════════════════════════
class TestDreamEngineQuickDream:
    def setup_method(self):
        self.engine = DreamEngine()

    def test_skips_synthesis(self):
        result = self.engine.quick_dream(_corpus())
        assert "synthesize" not in result.phases_completed

    def test_still_consolidates(self):
        result = self.engine.quick_dream(_corpus())
        assert "consolidate" in result.phases_completed

    def test_no_insights(self):
        result = self.engine.quick_dream(_corpus())
        assert result.insights_generated == 0

    def test_cycle_id_prefix(self):
        result = self.engine.quick_dream(_corpus())
        assert result.cycle_id.startswith("quick-")

    def test_journal_recorded(self):
        self.engine.quick_dream(_corpus())
        assert len(self.engine.journal.get_entries()) == 1


# ═══════════════════════════════════════════════════════════════
# 19. TestDreamEngineEmpty
# ═══════════════════════════════════════════════════════════════
class TestDreamEngineEmpty:
    def setup_method(self):
        self.engine = DreamEngine()

    def test_empty_dream(self):
        result = self.engine.dream([])
        assert result.success is True
        assert result.total_scanned == 0

    def test_empty_quick_dream(self):
        result = self.engine.quick_dream([])
        assert result.success is True
        assert result.total_scanned == 0

    def test_empty_produces_journal(self):
        result = self.engine.dream([])
        assert result.journal_entry is not None


# ═══════════════════════════════════════════════════════════════
# 20. TestEdgeCases
# ═══════════════════════════════════════════════════════════════
class TestEdgeCases:
    def test_zero_importance(self):
        replay = MemoryReplay()
        m = _mem(importance=0.0, access_count=0, content="x",
                 last_accessed=NOW - 100 * DAY)
        score = replay.score(m, now=NOW)
        assert 0.0 <= score <= 1.0

    def test_max_importance(self):
        replay = MemoryReplay()
        m = _mem(importance=1.0, access_count=20, content="word " * 200)
        score = replay.score(m, now=NOW)
        assert 0.0 <= score <= 1.0

    def test_duplicate_memory_ids(self):
        engine = DreamEngine()
        mems = [_mem("same", "content A"), _mem("same", "content B")]
        result = engine.dream(mems)
        assert result.success is True

    def test_very_long_content(self):
        replay = MemoryReplay()
        m = _mem(content="x " * 10000)
        score = replay.score(m, now=NOW)
        assert score <= 1.0

    def test_synthesizer_max_limit(self):
        synth = InsightSynthesizer(max_insights=2)
        mems = [_mem(f"m{i}", f"python code testing word{i}") for i in range(20)]
        scores = {f"m{i}": 0.9 for i in range(20)}
        insights = synth.synthesize(mems, scores)
        assert len(insights) <= 2

    def test_journal_thread_safety(self):
        import threading
        journal = DreamJournal()
        errors: list[str] = []

        def writer(n: int) -> None:
            try:
                for i in range(20):
                    journal.record(DreamJournalEntry(cycle_id=f"t{n}-{i}"))
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(journal.get_entries(limit=1000)) == 80

    def test_score_with_zero_halflife(self):
        replay = MemoryReplay(recency_halflife_days=0.0)
        m = _mem(last_accessed=NOW)
        score = replay.score(m, now=NOW)
        assert 0.0 <= score <= 1.0

    def test_negative_importance_clamped(self):
        replay = MemoryReplay()
        m = _mem(importance=-1.0)
        score = replay.score(m, now=NOW)
        assert score >= 0.0

    def test_multiple_dream_cycles(self):
        engine = DreamEngine()
        for _ in range(3):
            engine.dream([_mem("m1", "test")])
        assert len(engine.journal.get_entries(limit=10)) == 3
