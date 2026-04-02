"""Extreme fuzzing and stress testing for MEMORIA core and infrastructure modules.

Covers: malformed input, boundary conditions, concurrency stress, and
serialization round-trips across all major modules.
"""

from __future__ import annotations

import asyncio
import math
import sys
import threading
import time
import unittest
from collections import Counter
from unittest import mock

from memoria.core.importance import ImportanceScorer, ImportanceSignals, ImportanceTracker
from memoria.core.self_edit import (
    EditAction,
    EditDecision,
    MemoryBudget,
    SelfEditingMemory,
)
from memoria.core.store import (
    EntrypointTruncation,
    truncate_entrypoint,
)
from memoria.core.types import (
    MemoryFrontmatter,
    MemoryType,
    format_frontmatter,
    parse_frontmatter,
    parse_memory_type,
)
from memoria.tiered import WorkingMemory, TieredMemoryManager
from memoria.episodic.store import EpisodicMemory
from memoria.episodic.types import Episode, EpisodicEvent, EventType
from memoria.procedural.store import ProceduralMemory
from memoria.procedural.types import (
    Procedure,
    ProcedureStatus,
    ToolPattern,
    WorkflowStep,
    WorkflowTemplate,
)
from memoria.context.window import (
    TokenBudget,
    ContextAnalysis,
    estimate_tokens,
    estimate_message_tokens,
    estimate_messages_tokens,
    analyze_context,
)
from memoria.context.compaction import (
    CompactBoundary,
    CompactionConfig,
    ContextCompactor,
)
from memoria.extraction.dedup import MemoryDeduplicator, jaccard_similarity
from memoria.extraction.conflicts import (
    ConflictDetector,
    ConflictType,
    ResolutionStrategy,
)
from memoria.extraction.enricher import MemoryEnricher, MemoryCategory


# ---------------------------------------------------------------------------
# Fuzz data constants
# ---------------------------------------------------------------------------

EMPTY = ""
LONG_100KB = "x" * 100_000
LONG_1MB = "a" * 1_000_000
UNICODE_ZWJ = "a\u200b\u200c\u200db"          # zero-width chars
UNICODE_EMOJI = "🧠💾🔥🎯"
UNICODE_NULL = "hello\x00world"
UNICODE_SURROGATES = "test\ud800data"           # lone surrogate (only in str)
UNICODE_RTL = "\u202eRIGHT-TO-LEFT"
UNICODE_MIXED = "café naïve résumé 日本語 العربية"
SQL_INJECTION = "'; DROP TABLE memories; --"
BACKSLASH_NEWLINE = 'line1\nline2\\nline3\r\n\ttab'
SPECIAL_CHARS = '<script>alert(1)</script>&amp;"quotes"'
DEEPLY_NESTED_META = {"l1": {"l2": {"l3": {"l4": {"l5": "deep"}}}}}


# ═══════════════════════════════════════════════════════════════════════════
# 1. ImportanceScorer Fuzzing
# ═══════════════════════════════════════════════════════════════════════════


class TestImportanceScorerFuzz(unittest.TestCase):
    """Fuzz ImportanceScorer with extreme numeric inputs."""

    def setUp(self):
        self.scorer = ImportanceScorer()

    # -- malformed numeric signals ------------------------------------------

    def test_nan_relevance(self):
        sig = ImportanceSignals(relevance_score=float("nan"))
        score = self.scorer.score(sig)
        self.assertTrue(0.0 <= score <= 1.0, f"NaN input produced {score}")

    def test_inf_relevance(self):
        sig = ImportanceSignals(relevance_score=float("inf"))
        score = self.scorer.score(sig)
        self.assertTrue(0.0 <= score <= 1.0)

    def test_neg_inf_relevance(self):
        sig = ImportanceSignals(relevance_score=float("-inf"))
        score = self.scorer.score(sig)
        self.assertTrue(0.0 <= score <= 1.0)

    def test_negative_access_count(self):
        sig = ImportanceSignals(access_count=-100)
        score = self.scorer.score(sig)
        self.assertTrue(0.0 <= score <= 1.0)

    def test_huge_access_count(self):
        sig = ImportanceSignals(access_count=10**9)
        score = self.scorer.score(sig)
        self.assertTrue(0.0 <= score <= 1.0)

    def test_max_float_word_count(self):
        sig = ImportanceSignals(word_count=sys.maxsize)
        score = self.scorer.score(sig)
        self.assertTrue(0.0 <= score <= 1.0)

    def test_negative_word_count(self):
        sig = ImportanceSignals(word_count=-50)
        score = self.scorer.score(sig)
        self.assertTrue(0.0 <= score <= 1.0)

    def test_extreme_explicit_boost_positive(self):
        sig = ImportanceSignals(explicit_boost=100.0)
        score = self.scorer.score(sig)
        self.assertTrue(0.0 <= score <= 1.0)

    def test_extreme_explicit_boost_negative(self):
        sig = ImportanceSignals(explicit_boost=-100.0)
        score = self.scorer.score(sig)
        self.assertTrue(0.0 <= score <= 1.0)

    def test_future_last_accessed(self):
        sig = ImportanceSignals(last_accessed=time.time() + 86400 * 365)
        score = self.scorer.score(sig)
        self.assertTrue(0.0 <= score <= 1.0)

    def test_very_old_last_accessed(self):
        sig = ImportanceSignals(last_accessed=1.0)  # 1970-01-01
        score = self.scorer.score(sig)
        self.assertTrue(0.0 <= score <= 1.0)

    def test_zero_half_life(self):
        scorer = ImportanceScorer(recency_half_life_days=0.0)
        sig = ImportanceSignals(last_accessed=time.time())
        score = scorer.score(sig)
        self.assertTrue(0.0 <= score <= 1.0)

    def test_negative_half_life(self):
        scorer = ImportanceScorer(recency_half_life_days=-5.0)
        sig = ImportanceSignals(last_accessed=time.time())
        score = scorer.score(sig)
        self.assertTrue(0.0 <= score <= 1.0)

    def test_all_zero_weights_raises(self):
        with self.assertRaises(ValueError):
            ImportanceScorer(
                frequency_weight=0,
                recency_weight=0,
                relevance_weight=0,
                connectivity_weight=0,
                richness_weight=0,
            )

    def test_all_signals_maxed(self):
        sig = ImportanceSignals(
            access_count=10**6,
            last_accessed=time.time(),
            connection_count=10**6,
            explicit_boost=1.0,
            relevance_score=1.0,
            word_count=10**6,
            has_entities=True,
            referenced_by_count=10**6,
        )
        score = self.scorer.score(sig)
        self.assertTrue(0.0 <= score <= 1.0)

    def test_score_batch_empty(self):
        result = self.scorer.score_batch([])
        self.assertEqual(result, [])

    def test_score_batch_large(self):
        signals = [ImportanceSignals(access_count=i) for i in range(200)]
        result = self.scorer.score_batch(signals)
        self.assertEqual(len(result), 200)
        for s in result:
            self.assertTrue(0.0 <= s <= 1.0)

    def test_should_forget_with_nan(self):
        sig = ImportanceSignals(relevance_score=float("nan"))
        result = self.scorer.should_forget(sig)
        self.assertIsInstance(result, bool)

    def test_should_promote_boundary(self):
        sig = ImportanceSignals(
            access_count=20,
            last_accessed=time.time(),
            relevance_score=1.0,
            connection_count=10,
            explicit_boost=1.0,
            word_count=200,
            has_entities=True,
            referenced_by_count=10,
        )
        result = self.scorer.should_promote(sig)
        self.assertIsInstance(result, bool)


# ═══════════════════════════════════════════════════════════════════════════
# 2. ImportanceTracker Fuzzing
# ═══════════════════════════════════════════════════════════════════════════


class TestImportanceTrackerFuzz(unittest.TestCase):

    def test_record_access_empty_id(self):
        tracker = ImportanceTracker()
        tracker.record_access("")
        sig = tracker.get_signals("")
        self.assertEqual(sig.access_count, 1)

    def test_set_explicit_boost_extreme(self):
        tracker = ImportanceTracker()
        tracker.set_explicit_boost("m1", 999.0)
        sig = tracker.get_signals("m1")
        self.assertLessEqual(sig.explicit_boost, 1.0)

    def test_set_relevance_negative(self):
        tracker = ImportanceTracker()
        tracker.set_relevance("m1", -5.0)
        sig = tracker.get_signals("m1")
        self.assertEqual(sig.relevance_score, 0.0)

    def test_set_connections_negative(self):
        tracker = ImportanceTracker()
        tracker.set_connections("m1", -10)
        sig = tracker.get_signals("m1")
        self.assertEqual(sig.connection_count, 0)

    def test_remove_nonexistent(self):
        tracker = ImportanceTracker()
        tracker.remove("does-not-exist")  # should not raise

    def test_unicode_memory_id(self):
        tracker = ImportanceTracker()
        tracker.record_creation(UNICODE_EMOJI, word_count=5)
        sig = tracker.get_signals(UNICODE_EMOJI)
        self.assertEqual(sig.word_count, 5)


# ═══════════════════════════════════════════════════════════════════════════
# 3. SelfEditingMemory Fuzzing
# ═══════════════════════════════════════════════════════════════════════════


class TestSelfEditingMemoryFuzz(unittest.TestCase):

    def setUp(self):
        self.sem = SelfEditingMemory()

    def test_keep_empty_id(self):
        d = self.sem.keep("")
        self.assertEqual(d.action, EditAction.KEEP)

    def test_keep_unicode_reason(self):
        d = self.sem.keep("m1", reason=UNICODE_MIXED)
        self.assertIn(UNICODE_MIXED, d.reason)

    def test_compress_with_long_content(self):
        d = self.sem.compress("m1", LONG_100KB)
        self.assertEqual(len(d.new_content), 100_000)

    def test_merge_empty_list_raises(self):
        with self.assertRaises(ValueError):
            self.sem.merge([], "merged")

    def test_merge_single_item(self):
        d = self.sem.merge(["only"], "content")
        self.assertEqual(d.memory_id, "only")
        self.assertEqual(d.merged_ids, ["only"])

    def test_edit_history_rotation(self):
        for i in range(600):
            self.sem.keep(f"m{i}")
        history = self.sem.get_edit_history(limit=1000)
        self.assertLessEqual(len(self.sem._edit_history), 500)

    def test_auto_manage_empty_memories(self):
        decisions = self.sem.auto_manage([], {})
        self.assertEqual(decisions, [])

    def test_auto_manage_over_budget(self):
        budget = MemoryBudget(max_working_memories=2)
        sem = SelfEditingMemory(budget=budget)
        memories = [
            {"id": f"m{i}", "tier": "working", "token_count": 10}
            for i in range(5)
        ]
        scores = {f"m{i}": 0.01 * i for i in range(5)}
        decisions = sem.auto_manage(memories, scores)
        self.assertGreater(len(decisions), 0)

    def test_check_budget_empty(self):
        result = self.sem.check_budget({})
        self.assertEqual(result["action_needed"], "none")

    def test_check_budget_overflow(self):
        result = self.sem.check_budget({"working": 10**6})
        self.assertEqual(result["action_needed"], "forget")

    def test_stats_after_mixed_ops(self):
        self.sem.keep("a")
        self.sem.discard("b")
        self.sem.compress("c", "short")
        stats = self.sem.stats()
        self.assertEqual(stats["total_edits"], 3)

    def test_sql_injection_memory_id(self):
        d = self.sem.keep(SQL_INJECTION, reason=SQL_INJECTION)
        self.assertEqual(d.memory_id, SQL_INJECTION)

    def test_null_bytes_in_content(self):
        d = self.sem.compress("m1", UNICODE_NULL)
        self.assertIn("\x00", d.new_content)


# ═══════════════════════════════════════════════════════════════════════════
# 4. Core Store (truncate_entrypoint, parse_frontmatter) Fuzzing
# ═══════════════════════════════════════════════════════════════════════════


class TestCoreStoreFuzz(unittest.TestCase):

    def test_truncate_empty(self):
        t = truncate_entrypoint("")
        self.assertEqual(t.content, "")
        self.assertFalse(t.was_line_truncated)
        self.assertFalse(t.was_byte_truncated)

    def test_truncate_long_content(self):
        big = "line\n" * 500
        t = truncate_entrypoint(big, max_lines=10, max_bytes=100)
        self.assertTrue(t.was_line_truncated)
        self.assertLessEqual(len(t.content.encode("utf-8")), 100)

    def test_truncate_unicode_boundary(self):
        content = "é" * 200
        t = truncate_entrypoint(content, max_lines=300, max_bytes=50)
        t.content.encode("utf-8")  # must not raise

    def test_truncate_100kb_content(self):
        t = truncate_entrypoint(LONG_100KB, max_lines=5, max_bytes=1000)
        self.assertLessEqual(len(t.content.encode("utf-8")), 1000)

    def test_truncate_zero_limits(self):
        t = truncate_entrypoint("hello world", max_lines=0, max_bytes=0)
        self.assertEqual(t.content, "")

    def test_parse_frontmatter_empty(self):
        fm, body = parse_frontmatter("")
        self.assertEqual(fm.name, "")
        self.assertEqual(body, "")

    def test_parse_frontmatter_no_close(self):
        fm, body = parse_frontmatter("---\nname: test\n")
        self.assertEqual(fm.name, "")  # no closing ---

    def test_parse_frontmatter_unicode(self):
        content = f'---\nname: "{UNICODE_MIXED}"\n---\nbody'
        fm, body = parse_frontmatter(content)
        self.assertEqual(body, "body")

    def test_parse_frontmatter_sql_injection(self):
        content = f'---\nname: "{SQL_INJECTION}"\n---\nok'
        fm, body = parse_frontmatter(content)
        self.assertEqual(body, "ok")

    def test_parse_memory_type_invalid(self):
        self.assertIsNone(parse_memory_type("INVALID_TYPE"))

    def test_parse_memory_type_empty(self):
        self.assertIsNone(parse_memory_type(""))

    def test_format_frontmatter_all_fields(self):
        fm = MemoryFrontmatter(name="test", description="desc", type=MemoryType.USER)
        result = format_frontmatter(fm)
        self.assertIn("test", result)
        self.assertIn("user", result)

    def test_format_frontmatter_empty(self):
        fm = MemoryFrontmatter()
        result = format_frontmatter(fm)
        self.assertIn("---", result)


# ═══════════════════════════════════════════════════════════════════════════
# 5. WorkingMemory Fuzzing
# ═══════════════════════════════════════════════════════════════════════════


class TestWorkingMemoryFuzz(unittest.TestCase):

    def test_add_empty_content(self):
        wm = WorkingMemory()
        item_id = wm.add("")
        self.assertIsNotNone(wm.get(item_id))

    def test_add_100kb_content(self):
        wm = WorkingMemory(max_tokens=1_000_000, max_items=100)
        item_id = wm.add(LONG_100KB)
        item = wm.get(item_id)
        self.assertEqual(len(item["content"]), 100_000)

    def test_add_unicode_content(self):
        wm = WorkingMemory()
        for text in [UNICODE_ZWJ, UNICODE_EMOJI, UNICODE_NULL, UNICODE_RTL, UNICODE_MIXED]:
            item_id = wm.add(text)
            item = wm.get(item_id)
            self.assertEqual(item["content"], text)

    def test_add_sql_injection_content(self):
        wm = WorkingMemory()
        item_id = wm.add(SQL_INJECTION)
        self.assertIn(SQL_INJECTION, wm.get(item_id)["content"])

    def test_add_backslash_newline(self):
        wm = WorkingMemory()
        item_id = wm.add(BACKSLASH_NEWLINE)
        self.assertEqual(wm.get(item_id)["content"], BACKSLASH_NEWLINE)

    def test_add_deeply_nested_metadata(self):
        wm = WorkingMemory()
        item_id = wm.add("x", metadata=DEEPLY_NESTED_META)
        item = wm.get(item_id)
        self.assertEqual(item["metadata"]["l1"]["l2"]["l3"]["l4"]["l5"], "deep")

    def test_get_nonexistent(self):
        wm = WorkingMemory()
        self.assertIsNone(wm.get("does-not-exist"))

    def test_remove_nonexistent(self):
        wm = WorkingMemory()
        self.assertFalse(wm.remove("nope"))

    def test_search_empty_query(self):
        wm = WorkingMemory()
        wm.add("hello world")
        results = wm.search("")
        self.assertGreater(len(results), 0)

    def test_search_special_chars(self):
        wm = WorkingMemory()
        wm.add(SPECIAL_CHARS)
        results = wm.search("<script>")
        self.assertGreater(len(results), 0)

    def test_capacity_at_max_items(self):
        wm = WorkingMemory(max_tokens=10**6, max_items=5)
        for i in range(5):
            wm.add(f"item {i}")
        self.assertTrue(wm.is_full())

    def test_capacity_at_max_tokens(self):
        wm = WorkingMemory(max_tokens=10, max_items=100)
        wm.add("x" * 80)  # 80 chars ≈ 20 tokens
        self.assertTrue(wm.is_full())

    def test_evict_zero(self):
        wm = WorkingMemory()
        wm.add("a")
        evicted = wm.evict(0)
        self.assertEqual(evicted, [])

    def test_evict_negative(self):
        wm = WorkingMemory()
        wm.add("a")
        evicted = wm.evict(-5)
        self.assertEqual(evicted, [])

    def test_evict_more_than_available(self):
        wm = WorkingMemory()
        wm.add("only one")
        evicted = wm.evict(100)
        self.assertEqual(len(evicted), 1)

    def test_auto_evict_when_full(self):
        wm = WorkingMemory(max_tokens=10, max_items=2)
        wm.add("aaa", importance=0.1)
        wm.add("bbb", importance=0.9)
        wm.add("ccc", importance=0.5)
        evicted = wm.auto_evict()
        self.assertGreater(len(evicted), 0)

    def test_clear_returns_count(self):
        wm = WorkingMemory()
        wm.add("a")
        wm.add("b")
        count = wm.clear()
        self.assertEqual(count, 2)

    def test_clear_empty(self):
        wm = WorkingMemory()
        self.assertEqual(wm.clear(), 0)

    def test_importance_negative(self):
        wm = WorkingMemory()
        item_id = wm.add("x", importance=-1.0)
        item = wm.get(item_id)
        self.assertEqual(item["importance"], -1.0)

    def test_importance_very_large(self):
        wm = WorkingMemory()
        item_id = wm.add("x", importance=1e10)
        item = wm.get(item_id)
        self.assertEqual(item["importance"], 1e10)


# ═══════════════════════════════════════════════════════════════════════════
# 6. TieredMemoryManager Fuzzing
# ═══════════════════════════════════════════════════════════════════════════


class TestTieredManagerFuzz(unittest.TestCase):

    def setUp(self):
        self.mgr = TieredMemoryManager()

    def test_add_unknown_tier_raises(self):
        with self.assertRaises(ValueError):
            self.mgr.add("content", tier="nonexistent")

    def test_add_to_all_tiers(self):
        w_id = self.mgr.add("w", tier="working")
        r_id = self.mgr.add("r", tier="recall")
        a_id = self.mgr.add("a", tier="archival")
        self.assertIsNotNone(self.mgr.get(w_id))
        self.assertIsNotNone(self.mgr.get(r_id))
        self.assertIsNotNone(self.mgr.get(a_id))

    def test_get_nonexistent(self):
        self.assertIsNone(self.mgr.get("fake-id"))

    def test_delete_nonexistent(self):
        self.assertFalse(self.mgr.delete("fake-id"))

    def test_search_empty_query(self):
        self.mgr.add("hello world")
        results = self.mgr.search("")
        self.assertIsInstance(results, list)

    def test_search_unicode(self):
        self.mgr.add(UNICODE_MIXED)
        results = self.mgr.search("café")
        self.assertGreater(len(results), 0)

    def test_stats(self):
        self.mgr.add("working item")
        stats = self.mgr.stats()
        self.assertIn("working", stats)
        self.assertIn("recall", stats)
        self.assertIn("archival", stats)

    def test_promote_unsupported_raises(self):
        with self.assertRaises(ValueError):
            self.mgr.promote("id", "working", "archival")

    def test_flush_session_empty(self):
        result = self.mgr.flush_session()
        self.assertIsInstance(result, dict)

    def test_sql_injection_in_recall(self):
        r_id = self.mgr.add(SQL_INJECTION, tier="recall")
        item = self.mgr.get(r_id)
        self.assertEqual(item["content"], SQL_INJECTION)


# ═══════════════════════════════════════════════════════════════════════════
# 7. EpisodicMemory Fuzzing
# ═══════════════════════════════════════════════════════════════════════════


class TestEpisodicMemoryFuzz(unittest.TestCase):

    def setUp(self):
        self.em = EpisodicMemory()

    def test_start_episode_empty_fields(self):
        ep = self.em.start_episode()
        self.assertIsNotNone(ep.episode_id)

    def test_end_episode_no_active(self):
        result = self.em.end_episode()
        self.assertIsNone(result)

    def test_end_nonexistent_episode(self):
        result = self.em.end_episode(episode_id="fake")
        self.assertIsNone(result)

    def test_record_event_no_episode(self):
        ev = self.em.record_event("auto-start")
        self.assertIsNotNone(ev.event_id)
        self.assertIsNotNone(self.em.get_active_episode())

    def test_record_event_empty_content(self):
        self.em.start_episode()
        ev = self.em.record_event("")
        self.assertEqual(ev.content, "")

    def test_record_event_100kb_content(self):
        self.em.start_episode()
        ev = self.em.record_event(LONG_100KB)
        self.assertEqual(len(ev.content), 100_000)

    def test_record_event_unicode(self):
        self.em.start_episode()
        ev = self.em.record_event(UNICODE_EMOJI)
        self.assertEqual(ev.content, UNICODE_EMOJI)

    def test_record_event_null_bytes(self):
        self.em.start_episode()
        ev = self.em.record_event(UNICODE_NULL)
        self.assertIn("\x00", ev.content)

    def test_record_event_max_events_per_episode(self):
        em = EpisodicMemory(max_events_per_episode=2)
        em.start_episode()
        em.record_event("e1")
        em.record_event("e2")
        ev3 = em.record_event("e3-dropped")
        self.assertTrue(ev3.metadata.get("_dropped", False))

    def test_record_interaction(self):
        self.em.start_episode()
        ev = self.em.record_interaction("hi", role="user")
        self.assertEqual(ev.metadata["role"], "user")

    def test_record_tool_use(self):
        self.em.start_episode()
        ev = self.em.record_tool_use("grep", "pattern", "found")
        self.assertIn("grep", ev.content)

    def test_record_decision(self):
        self.em.start_episode()
        ev = self.em.record_decision("pick A", reasoning="better")
        self.assertEqual(ev.metadata["reasoning"], "better")

    def test_query_timeline_empty(self):
        events = self.em.query_timeline()
        self.assertEqual(events, [])

    def test_query_timeline_with_filters(self):
        self.em.start_episode()
        self.em.record_event("test", importance=0.9)
        events = self.em.query_timeline(min_importance=0.8)
        self.assertGreater(len(events), 0)

    def test_search_episodes_empty_query(self):
        results = self.em.search_episodes("")
        self.assertEqual(results, [])

    def test_search_episodes_unicode(self):
        self.em.start_episode(title=UNICODE_MIXED)
        self.em.record_event("café event")
        results = self.em.search_episodes("café")
        self.assertGreater(len(results), 0)

    def test_compact_nonexistent(self):
        result = self.em.compact_episode("fake")
        self.assertIsNone(result)

    def test_compact_episode_all_high_importance(self):
        ep = self.em.start_episode()
        self.em.record_event("important", importance=0.9)
        result = self.em.compact_episode(ep.episode_id)
        self.assertEqual(len(result.events), 1)

    def test_compact_episode_all_low_importance(self):
        ep = self.em.start_episode()
        for i in range(5):
            self.em.record_event(f"low {i}", importance=0.1)
        result = self.em.compact_episode(ep.episode_id)
        self.assertEqual(len(result.events), 0)
        self.assertIn("Compacted", result.summary)

    def test_episode_rotation(self):
        em = EpisodicMemory(max_episodes=3)
        for i in range(5):
            ep = em.start_episode(title=f"ep{i}")
            em.end_episode()
        self.assertLessEqual(len(em._episodes), 4)  # 3 max + possibly 1 active

    def test_zero_duration_episode(self):
        ep = self.em.start_episode()
        self.em.end_episode()
        self.assertIsNotNone(ep.ended_at is None)  # just ended
        self.assertGreaterEqual(ep.duration_s, 0)

    def test_episode_summary_no_summary(self):
        ep = self.em.start_episode(title="test")
        self.em.record_event("hello")
        summary = self.em.get_episode_summary(ep.episode_id)
        self.assertIn("test", summary)

    def test_episode_summary_nonexistent(self):
        summary = self.em.get_episode_summary("nope")
        self.assertEqual(summary, "")

    def test_stats(self):
        self.em.start_episode()
        self.em.record_event("x")
        stats = self.em.stats()
        self.assertGreater(stats["total_events"], 0)


# ═══════════════════════════════════════════════════════════════════════════
# 8. ProceduralMemory Fuzzing
# ═══════════════════════════════════════════════════════════════════════════


class TestProceduralMemoryFuzz(unittest.TestCase):

    def setUp(self):
        self.pm = ProceduralMemory()

    def test_record_tool_use_empty(self):
        p = self.pm.record_tool_use("", "", "")
        self.assertEqual(p.tool_name, "")

    def test_record_tool_use_unicode(self):
        p = self.pm.record_tool_use(UNICODE_EMOJI, UNICODE_MIXED, "ok")
        self.assertEqual(p.tool_name, UNICODE_EMOJI)

    def test_record_tool_failure(self):
        p = self.pm.record_tool_use("grep", "*.py", "error: no match", success=False)
        self.assertIn("error: no match", p.common_errors)

    def test_record_tool_negative_duration(self):
        p = self.pm.record_tool_use("tool", "input", "out", duration_ms=-100)
        self.assertIsNotNone(p)

    def test_get_tool_patterns_empty(self):
        result = self.pm.get_tool_patterns("nonexistent")
        self.assertEqual(result, [])

    def test_suggest_tool_empty_context(self):
        result = self.pm.suggest_tool("")
        self.assertIsNone(result)

    def test_add_workflow_empty_steps(self):
        wf = self.pm.add_workflow("empty-wf", [])
        self.assertEqual(wf.step_count, 0)

    def test_add_workflow_unicode_name(self):
        wf = self.pm.add_workflow(UNICODE_EMOJI, [{"tool_name": "t"}])
        self.assertEqual(wf.name, UNICODE_EMOJI)

    def test_find_workflows_no_match(self):
        results = self.pm.find_workflows(context="nonexistent")
        self.assertEqual(results, [])

    def test_update_workflow_outcome_nonexistent(self):
        self.pm.update_workflow_outcome("fake-id", True)  # should not raise

    def test_register_procedure_empty(self):
        proc = self.pm.register_procedure("", "")
        self.assertEqual(proc.name, "")

    def test_observe_nonexistent_procedure(self):
        self.pm.observe_procedure("nope")  # should not raise

    def test_execute_nonexistent_procedure(self):
        self.pm.execute_procedure("nope")  # should not raise

    def test_procedure_confidence_tracking(self):
        proc = self.pm.register_procedure("p1", "desc")
        for _ in range(3):
            self.pm.observe_procedure(proc.procedure_id)
        self.pm.execute_procedure(proc.procedure_id, success=True)
        self.pm.execute_procedure(proc.procedure_id, success=False)
        p = self.pm.get_procedure(proc.procedure_id)
        self.assertEqual(p.execution_count, 2)
        self.assertTrue(0.0 <= p.confidence <= 1.0)

    def test_suggest_procedure_empty(self):
        result = self.pm.suggest_procedure("")
        self.assertIsNone(result)

    def test_list_procedures_filter(self):
        self.pm.register_procedure("p1", "desc1")
        result = self.pm.list_procedures(status=ProcedureStatus.LEARNING)
        self.assertGreater(len(result), 0)

    def test_deprecate_stale_empty(self):
        count = self.pm.deprecate_stale()
        self.assertEqual(count, 0)

    def test_detect_workflow_short_sequence(self):
        wf = self.pm.detect_workflow()
        self.assertIsNone(wf)

    def test_stats(self):
        self.pm.record_tool_use("tool1", "in", "out")
        stats = self.pm.stats()
        self.assertIn("total_tool_patterns", stats)


# ═══════════════════════════════════════════════════════════════════════════
# 9. ContextWindow (token estimation) Fuzzing
# ═══════════════════════════════════════════════════════════════════════════


class TestContextWindowFuzz(unittest.TestCase):

    def test_estimate_tokens_empty(self):
        self.assertEqual(estimate_tokens(""), 0)

    def test_estimate_tokens_short(self):
        result = estimate_tokens("hi")
        self.assertGreaterEqual(result, 1)

    def test_estimate_tokens_100kb(self):
        result = estimate_tokens(LONG_100KB)
        self.assertGreater(result, 0)

    def test_estimate_tokens_unicode(self):
        result = estimate_tokens(UNICODE_EMOJI)
        self.assertGreater(result, 0)

    def test_estimate_message_tokens_empty(self):
        result = estimate_message_tokens({})
        self.assertGreater(result, 0)  # overhead exists

    def test_estimate_message_tokens_list_content(self):
        msg = {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "tool_use", "input": {"key": "val"}},
                {"type": "tool_result", "content": "result"},
            ],
        }
        result = estimate_message_tokens(msg)
        self.assertGreater(result, 0)

    def test_analyze_context_empty(self):
        budget = TokenBudget()
        analysis = analyze_context([], budget)
        self.assertEqual(analysis.total_tokens, 0)
        self.assertFalse(analysis.needs_compaction)

    def test_analyze_context_at_threshold(self):
        budget = TokenBudget(max_input_tokens=100, reserve_tokens=10, compact_threshold=0.5)
        # 90 available, trigger at 45
        msgs = [{"role": "user", "content": "x" * 200}]
        analysis = analyze_context(msgs, budget)
        self.assertTrue(analysis.needs_compaction)

    def test_budget_zero_input_tokens(self):
        budget = TokenBudget(max_input_tokens=0)
        analysis = analyze_context([], budget)
        self.assertEqual(analysis.utilization, 0)


# ═══════════════════════════════════════════════════════════════════════════
# 10. ContextCompactor Fuzzing
# ═══════════════════════════════════════════════════════════════════════════


class TestContextCompactorFuzz(unittest.TestCase):

    def test_micro_compact_empty(self):
        compactor = ContextCompactor()
        result = compactor.micro_compact([])
        self.assertEqual(result, [])

    def test_micro_compact_disabled(self):
        cfg = CompactionConfig(enabled=False)
        compactor = ContextCompactor(config=cfg)
        msgs = [{"role": "tool", "content": "x"}]
        result = compactor.micro_compact(msgs)
        self.assertEqual(result, msgs)

    def test_micro_compact_preserves_system(self):
        compactor = ContextCompactor(config=CompactionConfig(preserve_recent_n=0))
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "tool", "content": "x"},
        ]
        result = compactor.micro_compact(msgs)
        self.assertTrue(any(m["role"] == "system" for m in result))

    def test_full_compact_empty(self):
        compactor = ContextCompactor()
        result, boundary = asyncio.new_event_loop().run_until_complete(
            compactor.full_compact([])
        )
        self.assertEqual(result, [])
        self.assertIsNone(boundary)

    def test_full_compact_all_preserved(self):
        compactor = ContextCompactor(config=CompactionConfig(preserve_recent_n=100))
        msgs = [{"role": "user", "content": f"msg{i}"} for i in range(5)]
        result, boundary = asyncio.new_event_loop().run_until_complete(
            compactor.full_compact(msgs)
        )
        self.assertIsNone(boundary)

    def test_get_messages_after_boundary(self):
        compactor = ContextCompactor()
        msgs = [
            {"role": "user", "content": "before"},
            {"role": "assistant", "content": "summary", "_compact_boundary": True},
            {"role": "user", "content": "after"},
        ]
        result = compactor.get_messages_after_boundary(msgs)
        self.assertEqual(len(result), 2)

    def test_get_messages_no_boundary(self):
        compactor = ContextCompactor()
        msgs = [{"role": "user", "content": "hi"}]
        result = compactor.get_messages_after_boundary(msgs)
        self.assertEqual(result, msgs)


# ═══════════════════════════════════════════════════════════════════════════
# 11. Deduplicator Fuzzing
# ═══════════════════════════════════════════════════════════════════════════


class TestDeduplicatorFuzz(unittest.TestCase):

    def test_jaccard_empty_strings(self):
        self.assertEqual(jaccard_similarity("", ""), 1.0)

    def test_jaccard_one_empty(self):
        self.assertEqual(jaccard_similarity("hello", ""), 0.0)

    def test_jaccard_identical(self):
        self.assertEqual(jaccard_similarity("hello world", "hello world"), 1.0)

    def test_jaccard_unicode(self):
        result = jaccard_similarity(UNICODE_MIXED, UNICODE_MIXED)
        self.assertGreaterEqual(result, 0.0)

    def test_jaccard_special_chars_only(self):
        result = jaccard_similarity("!@#$%", "!@#$%")
        # No alphanumeric tokens → both empty → 1.0
        self.assertEqual(result, 1.0)

    def test_is_duplicate_similar(self):
        dedup = MemoryDeduplicator(similarity_threshold=0.8)
        self.assertTrue(dedup.is_duplicate(
            "the quick brown fox jumps over the lazy dog today",
            "the quick brown fox jumps over the lazy dog now",
        ))

    def test_find_duplicates_empty(self):
        dedup = MemoryDeduplicator()
        result = dedup.find_duplicates([])
        self.assertEqual(result, [])

    def test_find_duplicates_no_ids(self):
        dedup = MemoryDeduplicator(similarity_threshold=0.5)
        memories = [
            {"content": "hello world test"},
            {"content": "hello world test again"},
        ]
        result = dedup.find_duplicates(memories)
        self.assertIsInstance(result, list)

    def test_merge_memories_empty(self):
        dedup = MemoryDeduplicator()
        merged = dedup.merge_memories(
            {"content": "", "metadata": {}},
            {"content": "longer", "metadata": {"key": "val"}},
        )
        self.assertEqual(merged["content"], "longer")

    def test_deduplicate_empty_list(self):
        dedup = MemoryDeduplicator()
        self.assertEqual(dedup.deduplicate([]), [])

    def test_deduplicate_all_unique(self):
        dedup = MemoryDeduplicator()
        memories = [
            {"id": "1", "content": "alpha beta gamma"},
            {"id": "2", "content": "completely different topic here"},
        ]
        result = dedup.deduplicate(memories)
        self.assertEqual(len(result), 2)

    def test_deduplicate_all_identical(self):
        dedup = MemoryDeduplicator(similarity_threshold=0.8)
        memories = [
            {"id": str(i), "content": "exact same content here"} for i in range(5)
        ]
        result = dedup.deduplicate(memories)
        self.assertEqual(len(result), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 12. ConflictDetector Fuzzing
# ═══════════════════════════════════════════════════════════════════════════


class TestConflictDetectorFuzz(unittest.TestCase):

    def test_detect_empty(self):
        cd = ConflictDetector()
        result = cd.detect_conflicts([])
        self.assertEqual(result, [])

    def test_detect_single_memory(self):
        cd = ConflictDetector()
        result = cd.detect_conflicts([{"id": "1", "content": "hello"}])
        self.assertEqual(result, [])

    def test_detect_contradiction(self):
        cd = ConflictDetector()
        mems = [
            {"id": "1", "content": "user likes Python"},
            {"id": "2", "content": "user hates Python"},
        ]
        conflicts = cd.detect_conflicts(mems)
        contradictions = [c for c in conflicts if c.conflict_type == ConflictType.CONTRADICTION]
        self.assertGreater(len(contradictions), 0)

    def test_detect_redundant(self):
        cd = ConflictDetector(redundancy_threshold=0.8)
        mems = [
            {"id": "1", "content": "the quick brown fox jumps over the lazy dog"},
            {"id": "2", "content": "the quick brown fox jumps over the lazy dog"},
        ]
        conflicts = cd.detect_conflicts(mems)
        redundant = [c for c in conflicts if c.conflict_type == ConflictType.REDUNDANT]
        self.assertGreater(len(redundant), 0)

    def test_detect_outdated(self):
        cd = ConflictDetector()
        mems = [
            {"id": "1", "content": "user uses Python 3.9", "created_at": "2020-01-01"},
            {"id": "2", "content": "user uses Python 3.12", "created_at": "2024-01-01"},
        ]
        conflicts = cd.detect_conflicts(mems)
        outdated = [c for c in conflicts if c.conflict_type == ConflictType.OUTDATED]
        self.assertGreater(len(outdated), 0)

    def test_resolve_latest_wins(self):
        cd = ConflictDetector()
        from memoria.extraction.conflicts import Conflict
        conflict = Conflict("m1", "m2", ConflictType.OUTDATED, 0.8, "test")
        mems = {
            "m1": {"content": "old", "created_at": "2020-01-01"},
            "m2": {"content": "new", "created_at": "2024-01-01"},
        }
        winner = cd.resolve(conflict, ResolutionStrategy.LATEST_WINS, mems)
        self.assertEqual(winner["content"], "new")

    def test_resolve_confidence_weighted(self):
        cd = ConflictDetector()
        from memoria.extraction.conflicts import Conflict
        conflict = Conflict("m1", "m2", ConflictType.CONTRADICTION, 0.8, "test")
        mems = {
            "m1": {"content": "a", "metadata": {"confidence": 0.3}},
            "m2": {"content": "b", "metadata": {"confidence": 0.9}},
        }
        winner = cd.resolve(conflict, ResolutionStrategy.CONFIDENCE_WEIGHTED, mems)
        self.assertEqual(winner["content"], "b")

    def test_resolve_manual(self):
        cd = ConflictDetector()
        from memoria.extraction.conflicts import Conflict
        conflict = Conflict("m1", "m2", ConflictType.CONTRADICTION, 0.8, "test")
        mems = {
            "m1": {"content": "a", "metadata": {}},
            "m2": {"content": "b", "metadata": {}},
        }
        result = cd.resolve(conflict, ResolutionStrategy.MANUAL, mems)
        self.assertTrue(result["metadata"]["needs_review"])

    def test_resolve_merge(self):
        cd = ConflictDetector()
        from memoria.extraction.conflicts import Conflict
        conflict = Conflict("m1", "m2", ConflictType.REDUNDANT, 0.9, "test")
        mems = {
            "m1": {"content": "short", "metadata": {"a": 1}},
            "m2": {"content": "longer content here", "metadata": {"b": 2}},
        }
        result = cd.resolve(conflict, ResolutionStrategy.MERGE, mems)
        self.assertEqual(result["content"], "longer content here")


# ═══════════════════════════════════════════════════════════════════════════
# 13. MemoryEnricher Fuzzing
# ═══════════════════════════════════════════════════════════════════════════


class TestMemoryEnricherFuzz(unittest.TestCase):

    def setUp(self):
        self.enricher = MemoryEnricher()

    def test_categorize_empty(self):
        cat = self.enricher.categorize("")
        self.assertEqual(cat, MemoryCategory.FACT)

    def test_categorize_preference(self):
        cat = self.enricher.categorize("I prefer dark mode")
        self.assertEqual(cat, MemoryCategory.PREFERENCE)

    def test_categorize_event(self):
        cat = self.enricher.categorize("meeting yesterday with the team")
        self.assertEqual(cat, MemoryCategory.EVENT)

    def test_categorize_unicode(self):
        cat = self.enricher.categorize(UNICODE_MIXED)
        self.assertIsInstance(cat, MemoryCategory)

    def test_extract_tags_empty(self):
        tags = self.enricher.extract_tags("")
        self.assertIsInstance(tags, list)

    def test_extract_tags_100kb(self):
        tags = self.enricher.extract_tags(LONG_100KB)
        self.assertIsInstance(tags, list)

    def test_enrich_empty_memory(self):
        result = self.enricher.enrich({"content": ""})
        self.assertIn("category", result["metadata"])

    def test_enrich_no_content_key(self):
        result = self.enricher.enrich({})
        self.assertEqual(result["metadata"]["category"], "fact")

    def test_enrich_with_existing_metadata(self):
        result = self.enricher.enrich({
            "content": "I prefer Python",
            "metadata": {"existing_key": "val"},
        })
        self.assertEqual(result["metadata"]["existing_key"], "val")
        self.assertEqual(result["metadata"]["category"], "preference")

    def test_enrich_batch_empty(self):
        result = self.enricher.enrich_batch([])
        self.assertEqual(result, [])

    def test_enrich_sql_injection(self):
        result = self.enricher.enrich({"content": SQL_INJECTION})
        self.assertIn("category", result["metadata"])


# ═══════════════════════════════════════════════════════════════════════════
# 14. Concurrency Stress Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestConcurrencyStress(unittest.TestCase):

    def test_concurrent_working_memory_adds(self):
        """20+ threads concurrently adding to WorkingMemory."""
        wm = WorkingMemory(max_tokens=10**7, max_items=10000)
        errors = []

        def add_items(thread_idx):
            try:
                for i in range(50):
                    wm.add(f"thread-{thread_idx}-item-{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_items, args=(t,)) for t in range(25)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(errors, [])
        self.assertGreater(len(wm.all()), 0)

    def test_concurrent_read_write_working_memory(self):
        """Concurrent reads and writes on WorkingMemory."""
        wm = WorkingMemory(max_tokens=10**7, max_items=10000)
        ids = [wm.add(f"initial-{i}") for i in range(100)]
        errors = []

        def writer():
            try:
                for i in range(50):
                    wm.add(f"new-{i}")
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for item_id in ids[:50]:
                    wm.get(item_id)
                    wm.search("initial", limit=5)
            except Exception as e:
                errors.append(e)

        threads = (
            [threading.Thread(target=writer) for _ in range(10)]
            + [threading.Thread(target=reader) for _ in range(10)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(errors, [])

    def test_concurrent_importance_scoring(self):
        """Multiple threads scoring concurrently."""
        scorer = ImportanceScorer()
        errors = []

        def score_many(offset):
            try:
                for i in range(100):
                    sig = ImportanceSignals(
                        access_count=offset + i,
                        last_accessed=time.time(),
                        relevance_score=0.5,
                    )
                    s = scorer.score(sig)
                    assert 0.0 <= s <= 1.0
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=score_many, args=(t * 100,)) for t in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(errors, [])

    def test_concurrent_episodic_recording(self):
        """Multiple threads recording events concurrently."""
        em = EpisodicMemory(max_events_per_episode=10000)
        em.start_episode()
        errors = []

        def record_events(thread_idx):
            try:
                for i in range(50):
                    em.record_event(f"t{thread_idx}-e{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_events, args=(t,)) for t in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(errors, [])
        stats = em.stats()
        self.assertGreater(stats["total_events"], 0)

    def test_concurrent_tiered_manager_ops(self):
        """Concurrent adds/gets/searches on TieredMemoryManager (working tier only to avoid SQLite threading)."""
        mgr = TieredMemoryManager()
        errors = []

        def ops(thread_idx):
            try:
                for i in range(20):
                    mgr.working.add(f"t{thread_idx}-{i}")
                    mgr.working.search(f"t{thread_idx}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=ops, args=(t,)) for t in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(errors, [])


# ═══════════════════════════════════════════════════════════════════════════
# 15. Serialization / Round-trip Tests
# ═══════════════════════════════════════════════════════════════════════════


class TestSerializationRoundTrip(unittest.TestCase):

    def test_frontmatter_roundtrip(self):
        fm = MemoryFrontmatter(name="test-name", description="my desc", type=MemoryType.FEEDBACK)
        text = format_frontmatter(fm) + "\n\nbody content"
        fm2, body = parse_frontmatter(text)
        self.assertEqual(fm2.name, fm.name)
        self.assertEqual(fm2.type, fm.type)
        self.assertEqual(body.strip(), "body content")

    def test_frontmatter_roundtrip_empty_fields(self):
        fm = MemoryFrontmatter()
        text = format_frontmatter(fm)
        fm2, body = parse_frontmatter(text)
        self.assertEqual(fm2.name, "")

    def test_importance_signals_field_preservation(self):
        sig = ImportanceSignals(
            access_count=42,
            last_accessed=12345.0,
            connection_count=7,
            explicit_boost=0.5,
            relevance_score=0.8,
            word_count=100,
            has_entities=True,
            referenced_by_count=3,
        )
        # Simulate serialize/deserialize via dict
        d = {
            "access_count": sig.access_count,
            "last_accessed": sig.last_accessed,
            "connection_count": sig.connection_count,
            "explicit_boost": sig.explicit_boost,
            "relevance_score": sig.relevance_score,
            "word_count": sig.word_count,
            "has_entities": sig.has_entities,
            "referenced_by_count": sig.referenced_by_count,
        }
        sig2 = ImportanceSignals(**d)
        self.assertEqual(sig.access_count, sig2.access_count)
        self.assertEqual(sig.relevance_score, sig2.relevance_score)
        self.assertEqual(sig.has_entities, sig2.has_entities)

    def test_edit_decision_roundtrip(self):
        d = EditDecision(
            memory_id="m1",
            action=EditAction.MERGE,
            reason="combined",
            new_content="merged content",
            target_tier="working",
            confidence=0.75,
            merged_ids=["m1", "m2", "m3"],
        )
        # Simulate roundtrip
        data = {
            "memory_id": d.memory_id,
            "action": d.action.value,
            "reason": d.reason,
            "new_content": d.new_content,
            "target_tier": d.target_tier,
            "confidence": d.confidence,
            "merged_ids": list(d.merged_ids),
        }
        d2 = EditDecision(
            memory_id=data["memory_id"],
            action=EditAction(data["action"]),
            reason=data["reason"],
            new_content=data["new_content"],
            target_tier=data["target_tier"],
            confidence=data["confidence"],
            merged_ids=data["merged_ids"],
        )
        self.assertEqual(d.memory_id, d2.memory_id)
        self.assertEqual(d.action, d2.action)
        self.assertEqual(d.merged_ids, d2.merged_ids)

    def test_memory_budget_roundtrip(self):
        budget = MemoryBudget(
            max_working_memories=10,
            max_recall_memories=100,
            max_archival_memories=1000,
            max_total_tokens=50000,
            compress_threshold=0.9,
            forget_threshold=0.98,
        )
        d = {
            "max_working_memories": budget.max_working_memories,
            "max_recall_memories": budget.max_recall_memories,
            "max_archival_memories": budget.max_archival_memories,
            "max_total_tokens": budget.max_total_tokens,
            "compress_threshold": budget.compress_threshold,
            "forget_threshold": budget.forget_threshold,
        }
        budget2 = MemoryBudget(**d)
        self.assertEqual(budget.max_total_tokens, budget2.max_total_tokens)
        self.assertEqual(budget.forget_threshold, budget2.forget_threshold)

    def test_token_budget_roundtrip(self):
        b = TokenBudget(max_input_tokens=150_000, max_output_tokens=4096,
                        compact_threshold=0.9, reserve_tokens=5000)
        d = {
            "max_input_tokens": b.max_input_tokens,
            "max_output_tokens": b.max_output_tokens,
            "compact_threshold": b.compact_threshold,
            "reserve_tokens": b.reserve_tokens,
        }
        b2 = TokenBudget(**d)
        self.assertEqual(b.available_tokens, b2.available_tokens)
        self.assertEqual(b.compact_trigger, b2.compact_trigger)

    def test_compact_boundary_roundtrip(self):
        cb = CompactBoundary(summary="test summary", original_message_count=10,
                             original_token_count=500)
        d = {
            "summary": cb.summary,
            "timestamp": cb.timestamp,
            "original_message_count": cb.original_message_count,
            "original_token_count": cb.original_token_count,
        }
        cb2 = CompactBoundary(**d)
        self.assertEqual(cb.summary, cb2.summary)
        self.assertEqual(cb.original_message_count, cb2.original_message_count)

    def test_episodic_event_roundtrip(self):
        ev = EpisodicEvent(
            event_id="e1",
            event_type=EventType.TOOL_USE,
            content="used grep",
            agent_id="agent-1",
            user_id="user-1",
            importance=0.8,
            metadata={"tool": "grep"},
        )
        d = {
            "event_id": ev.event_id,
            "event_type": ev.event_type,
            "content": ev.content,
            "timestamp": ev.timestamp,
            "agent_id": ev.agent_id,
            "user_id": ev.user_id,
            "importance": ev.importance,
            "metadata": dict(ev.metadata),
        }
        ev2 = EpisodicEvent(**d)
        self.assertEqual(ev.event_id, ev2.event_id)
        self.assertEqual(ev.event_type, ev2.event_type)
        self.assertEqual(ev.metadata, ev2.metadata)

    def test_procedure_roundtrip(self):
        proc = Procedure(
            procedure_id="p1",
            name="test-proc",
            description="a test procedure",
            status=ProcedureStatus.LEARNED,
            confidence=0.85,
            observation_count=5,
            execution_count=3,
            success_count=2,
            preconditions=["pre1"],
            postconditions=["post1"],
            related_tools=["tool1"],
        )
        d = {
            "procedure_id": proc.procedure_id,
            "name": proc.name,
            "description": proc.description,
            "status": proc.status,
            "confidence": proc.confidence,
            "observation_count": proc.observation_count,
            "execution_count": proc.execution_count,
            "success_count": proc.success_count,
            "preconditions": list(proc.preconditions),
            "postconditions": list(proc.postconditions),
            "related_tools": list(proc.related_tools),
        }
        proc2 = Procedure(**d)
        self.assertEqual(proc.name, proc2.name)
        self.assertEqual(proc.status, proc2.status)
        self.assertEqual(proc.confidence, proc2.confidence)

    def test_workflow_template_roundtrip(self):
        wf = WorkflowTemplate(
            workflow_id="wf1",
            name="deploy",
            description="deploy workflow",
            steps=[WorkflowStep(step_index=0, tool_name="build", description="build")],
            trigger_context="deploy",
            success_count=5,
            fail_count=1,
            tags=["ci", "deploy"],
        )
        self.assertEqual(wf.success_rate, 5 / 6)
        self.assertEqual(wf.step_count, 1)


# ═══════════════════════════════════════════════════════════════════════════
# 16. Additional Edge Cases
# ═══════════════════════════════════════════════════════════════════════════


class TestAdditionalEdgeCases(unittest.TestCase):

    def test_working_memory_none_metadata(self):
        wm = WorkingMemory()
        item_id = wm.add("content", metadata=None)
        item = wm.get(item_id)
        self.assertEqual(item["metadata"], {})

    def test_recall_memory_sql_injection(self):
        mgr = TieredMemoryManager()
        r_id = mgr.add(SQL_INJECTION, tier="recall")
        results = mgr.recall.search(SQL_INJECTION)
        self.assertGreater(len(results), 0)

    def test_archival_memory_special_namespace(self):
        mgr = TieredMemoryManager()
        a_id = mgr.archival.add("test", namespace="'; DROP TABLE;--")
        item = mgr.archival.get(a_id)
        self.assertIsNotNone(item)

    def test_episodic_multiple_episode_starts(self):
        """Starting a new episode should auto-close the previous one."""
        em = EpisodicMemory()
        ep1 = em.start_episode(title="first")
        ep2 = em.start_episode(title="second")
        # ep1 should be ended
        stored_ep1 = em.get_episode(ep1.episode_id)
        self.assertIsNotNone(stored_ep1.ended_at)
        self.assertEqual(em.get_active_episode().episode_id, ep2.episode_id)

    def test_procedural_tool_pattern_update(self):
        """Same tool input should update existing pattern, not create new."""
        pm = ProceduralMemory()
        pm.record_tool_use("grep", "search pattern test", "found")
        pm.record_tool_use("grep", "search pattern test", "found again")
        patterns = pm.get_tool_patterns("grep")
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0].use_count, 2)

    def test_dedup_with_none_metadata(self):
        dedup = MemoryDeduplicator()
        merged = dedup.merge_memories(
            {"content": "hello", "metadata": None},
            {"content": "hello world", "metadata": {"k": "v"}},
        )
        self.assertEqual(merged["metadata"]["k"], "v")

    def test_conflict_detector_no_timestamps(self):
        cd = ConflictDetector()
        mems = [
            {"id": "1", "content": "hello world"},
            {"id": "2", "content": "hello world again"},
        ]
        conflicts = cd.detect_conflicts(mems)
        # Should not crash even without created_at
        self.assertIsInstance(conflicts, list)

    def test_enricher_relationship_category(self):
        enricher = MemoryEnricher()
        cat = enricher.categorize("Alice works with Bob on the project")
        self.assertEqual(cat, MemoryCategory.RELATIONSHIP)

    def test_enricher_skill_category(self):
        enricher = MemoryEnricher()
        cat = enricher.categorize("She is proficient in Rust programming")
        self.assertEqual(cat, MemoryCategory.SKILL)

    def test_enricher_opinion_category(self):
        enricher = MemoryEnricher()
        cat = enricher.categorize("I think this approach is better")
        self.assertEqual(cat, MemoryCategory.OPINION)


if __name__ == "__main__":
    unittest.main()
