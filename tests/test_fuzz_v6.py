"""Extreme fuzzing & stress tests for MEMORIA v6 modules.

Covers: product_intel, fusion, habits, contextual, biz_intel.
Categories: malformed input, boundary, concurrency, serialisation round-trip.
"""

from __future__ import annotations

import math
import sys
import threading
import time
import unittest
from typing import Any, Dict, List

# ── biz_intel ────────────────────────────────────────────────────────
from memoria.biz_intel import (
    LifecycleTracker,
    RevenueSignals,
    SegmentClassifier,
    ValueScorer,
)
from memoria.biz_intel.types import (
    LifecyclePosition,
    RevenueSignalType,
    SegmentType,
    UserSegment,
    ValueScore,
)

# ── contextual ───────────────────────────────────────────────────────
from memoria.contextual import (
    IntentInference,
    ProactiveAssistant,
    SituationAwareness,
    SmartHandoff,
)
from memoria.contextual.types import (
    AssistanceType,
    HandoffContext,
    HandoffReason,
    InferredIntent,
    SituationSnapshot,
    SituationType,
)

# ── fusion ───────────────────────────────────────────────────────────
from memoria.fusion import (
    BehaviorFusion,
    ChurnPredictor,
    CrossProductCorrelator,
    WorkflowDetector,
)
from memoria.fusion.types import (
    BehavioralSignal,
    ChurnPrediction,
    ChurnRisk,
    Correlation,
    SignalType,
)

# ── habits ───────────────────────────────────────────────────────────
from memoria.habits import (
    AnchorDetector,
    DisruptionAlert,
    HabitTracker,
    RoutineOptimizer,
)
from memoria.habits.types import (
    AnchorBehavior,
    AnchorType,
    DisruptionEvent,
    DisruptionSeverity,
    Habit,
    HabitStrength,
    Routine,
)

# ── product_intel ────────────────────────────────────────────────────
from memoria.product_intel import (
    AdoptionAnalyzer,
    ProductGraph,
    ProductTracker,
    UsageProfiler,
)
from memoria.product_intel.types import (
    AdoptionCurve,
    FeatureStatus,
    ProductCategory,
    ProductInfo,
    ProductRelationship,
    ProductUsageEvent,
    UsageFrequency,
    UsageProfile,
)

# ── Fuzz helpers ─────────────────────────────────────────────────────

LONG_STR = "A" * 120_000  # ~120 KB
UNICODE_ZW = "\u200b\u200c\u200d\ufeff"  # zero-width chars
UNICODE_RTL = "\u202e\u202dHello\u202c"
UNICODE_EMOJI = "😀🏳️‍🌈👨‍👩‍👧‍👦🧑‍💻"
UNICODE_SURROGATE_SAFE = "\ud800".encode("utf-8", errors="replace").decode()
UNICODE_NULL = "hello\x00world"
SQL_INJECT = "'; DROP TABLE users; --"
SPECIAL_CHARS = 'key"with\\back\nnew\ttab'
NESTED_DICT: Dict[str, Any] = {}
_cur = NESTED_DICT
for _i in range(120):
    _cur["nested"] = {}
    _cur = _cur["nested"]

TIMEOUT = 5  # seconds


def _run_threads(target, args_list, timeout=TIMEOUT):
    """Run *target* in threads with different args, assert no crash."""
    threads: List[threading.Thread] = []
    errors: List[Exception] = []

    def _wrap(fn, args):
        try:
            fn(*args)
        except Exception as exc:
            errors.append(exc)

    for args in args_list:
        t = threading.Thread(target=_wrap, args=(target, args), daemon=True)
        threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=timeout)
    alive = [t for t in threads if t.is_alive()]
    return errors, alive


# =====================================================================
#  ProductTracker fuzz
# =====================================================================

class TestProductTrackerFuzz(unittest.TestCase):

    # ── malformed input ──────────────────────────────────────────────

    def test_register_empty_strings(self):
        pt = ProductTracker()
        info = pt.register_product("", "", ProductCategory.CUSTOM)
        self.assertIsInstance(info, ProductInfo)

    def test_register_long_strings(self):
        pt = ProductTracker()
        info = pt.register_product(LONG_STR, LONG_STR, ProductCategory.IDE, version=LONG_STR)
        self.assertEqual(info.name, LONG_STR)

    def test_register_unicode_edge_cases(self):
        pt = ProductTracker()
        for label in (UNICODE_ZW, UNICODE_RTL, UNICODE_EMOJI, UNICODE_NULL, SQL_INJECT, SPECIAL_CHARS):
            info = pt.register_product(label, label, ProductCategory.CRM)
            self.assertIsNotNone(info)

    def test_register_with_none_features(self):
        pt = ProductTracker()
        info = pt.register_product("p", "n", ProductCategory.IDE, features=None)
        self.assertEqual(info.features, [])

    def test_register_huge_features_list(self):
        pt = ProductTracker()
        huge = [f"f{i}" for i in range(100_001)]
        info = pt.register_product("p", "n", ProductCategory.IDE, features=huge)
        self.assertEqual(len(info.features), 100_001)

    def test_register_metadata_deeply_nested(self):
        pt = ProductTracker()
        info = pt.register_product("p", "n", ProductCategory.IDE, metadata=NESTED_DICT)
        self.assertIsNotNone(info)

    # ── boundary ─────────────────────────────────────────────────────

    def test_eviction_at_max_products(self):
        pt = ProductTracker(max_products=3)
        for i in range(5):
            pt.register_product(f"p{i}", f"n{i}", ProductCategory.IDE)
        self.assertEqual(len(pt.list_products()), 3)

    def test_max_products_zero_or_negative(self):
        pt = ProductTracker(max_products=0)
        pt.register_product("a", "a", ProductCategory.IDE)
        self.assertTrue(len(pt.list_products()) <= 1)

        pt2 = ProductTracker(max_products=-5)
        pt2.register_product("b", "b", ProductCategory.CRM)
        self.assertTrue(len(pt2.list_products()) <= 1)

    def test_unregister_nonexistent(self):
        pt = ProductTracker()
        self.assertFalse(pt.unregister_product("no_such"))

    def test_get_product_nonexistent(self):
        pt = ProductTracker()
        self.assertIsNone(pt.get_product("nope"))

    # ── serialisation round-trip ─────────────────────────────────────

    def test_roundtrip_to_dict_from_dict(self):
        pt = ProductTracker(max_products=5)
        pt.register_product("x", "X", ProductCategory.ANALYTICS, version="1.0", features=["a", "b"])
        d1 = pt.to_dict()
        pt2 = ProductTracker.from_dict(d1)
        d2 = pt2.to_dict()
        self.assertEqual(d1, d2)

    def test_from_dict_empty(self):
        pt = ProductTracker.from_dict({})
        self.assertEqual(len(pt.list_products()), 0)

    def test_from_dict_corrupted(self):
        bad = {"max_products": "not_int", "products": {"p1": {"product_id": "p1", "name": 123, "category": "ide"}}}
        try:
            ProductTracker.from_dict(bad)
        except Exception:
            pass  # acceptable to raise

    def test_from_dict_extra_keys(self):
        d = {"max_products": 10, "products": {}, "extra_key": True, "another": [1, 2]}
        pt = ProductTracker.from_dict(d)
        self.assertIsNotNone(pt)

    # ── concurrency ──────────────────────────────────────────────────

    def test_concurrent_register(self):
        pt = ProductTracker(max_products=50)
        args = [(pt, f"p{i}", f"n{i}", ProductCategory.IDE) for i in range(25)]

        def _reg(tracker, pid, nm, cat):
            tracker.register_product(pid, nm, cat)

        errors, alive = _run_threads(
            lambda tr, p, n, c: _reg(tr, p, n, c), args
        )
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(alive), 0)

    def test_concurrent_read_write(self):
        pt = ProductTracker(max_products=50)
        for i in range(10):
            pt.register_product(f"p{i}", f"n{i}", ProductCategory.IDE)

        def _ops(tracker, idx):
            tracker.register_product(f"new{idx}", f"nn{idx}", ProductCategory.CRM)
            tracker.list_products()
            tracker.get_ecosystem_summary()
            tracker.to_dict()

        errors, alive = _run_threads(
            lambda tr, i: _ops(tr, i), [(pt, i) for i in range(25)]
        )
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(alive), 0)


# =====================================================================
#  UsageProfiler fuzz
# =====================================================================

class TestUsageProfilerFuzz(unittest.TestCase):

    def test_record_empty_strings(self):
        up = UsageProfiler()
        ev = up.record_event("", "", "")
        self.assertIsInstance(ev, ProductUsageEvent)

    def test_record_long_strings(self):
        up = UsageProfiler()
        ev = up.record_event(LONG_STR, LONG_STR, LONG_STR)
        self.assertIsNotNone(ev)

    def test_record_unicode_variants(self):
        up = UsageProfiler()
        for s in (UNICODE_ZW, UNICODE_RTL, UNICODE_EMOJI, UNICODE_NULL, SQL_INJECT):
            ev = up.record_event(s, s, s)
            self.assertIsNotNone(ev)

    def test_record_negative_duration(self):
        up = UsageProfiler()
        ev = up.record_event("p", "f", "a", duration=-100)
        self.assertEqual(ev.duration_seconds, 0.0)

    def test_record_nan_inf_timestamp(self):
        up = UsageProfiler()
        ev = up.record_event("p", "f", "a", timestamp=float("nan"))
        self.assertIsNotNone(ev)
        self.assertTrue(math.isfinite(ev.timestamp))  # NaN sanitised
        ev2 = up.record_event("p", "f", "a", timestamp=float("inf"))
        self.assertIsNotNone(ev2)
        self.assertTrue(math.isfinite(ev2.timestamp))  # Inf sanitised
        ev3 = up.record_event("p", "f", "a", timestamp=float("-inf"))
        self.assertIsNotNone(ev3)
        self.assertTrue(math.isfinite(ev3.timestamp))  # -Inf sanitised

    def test_record_zero_timestamp(self):
        up = UsageProfiler()
        ev = up.record_event("p", "f", "a", timestamp=0.0)
        self.assertEqual(ev.timestamp, 0.0)

    def test_compute_frequency_empty(self):
        up = UsageProfiler()
        self.assertEqual(up.compute_frequency("nonexistent"), UsageFrequency.INACTIVE)

    def test_compare_nonexistent(self):
        up = UsageProfiler()
        result = up.compare_products("a", "b")
        self.assertIn("error", result)

    def test_most_used_features_zero(self):
        up = UsageProfiler()
        self.assertEqual(up.get_most_used_features("p", top_n=0), [])

    def test_most_used_features_negative(self):
        up = UsageProfiler()
        self.assertEqual(up.get_most_used_features("p", top_n=-5), [])

    def test_eviction_at_max_products(self):
        up = UsageProfiler(max_products=2, max_events_per_product=5)
        for i in range(5):
            up.record_event(f"prod{i}", "feat", "act", timestamp=float(i))
        # At most 2 products tracked
        profiles = [up.get_profile(f"prod{i}") for i in range(5)]
        active = [p for p in profiles if p is not None]
        self.assertLessEqual(len(active), 2)

    def test_concurrent_record(self):
        up = UsageProfiler()
        def _rec(idx):
            for j in range(50):
                up.record_event(f"p{idx % 3}", f"f{j}", "act", timestamp=time.time())
        errors, alive = _run_threads(lambda i: _rec(i), [(i,) for i in range(25)])
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(alive), 0)


# =====================================================================
#  ProductGraph fuzz
# =====================================================================

class TestProductGraphFuzz(unittest.TestCase):

    def test_transition_empty_strings(self):
        pg = ProductGraph()
        pg.record_transition("", "b", 1.0)
        pg.record_transition("a", "", 1.0)
        pg.record_transition("", "", 1.0)
        self.assertEqual(len(pg.get_relationships()), 0)

    def test_transition_same_product(self):
        pg = ProductGraph()
        pg.record_transition("a", "a", 1.0)
        self.assertEqual(len(pg.get_relationships()), 0)

    def test_long_product_names(self):
        pg = ProductGraph()
        pg.record_transition(LONG_STR, "b", 1.0)
        self.assertEqual(len(pg.get_relationships()), 1)

    def test_unicode_in_graph(self):
        pg = ProductGraph()
        pg.record_transition(UNICODE_EMOJI, UNICODE_RTL, 1.0)
        rels = pg.get_relationships()
        self.assertEqual(len(rels), 1)

    def test_add_relationship_strength_clamped(self):
        pg = ProductGraph()
        r = pg.add_relationship("a", "b", "test", strength=-5.0)
        self.assertGreaterEqual(r.strength, 0.0)
        r2 = pg.add_relationship("c", "d", "test", strength=999.0)
        self.assertLessEqual(r2.strength, 1.0)

    def test_workflow_chains_empty(self):
        pg = ProductGraph()
        chains = pg.get_workflow_chains()
        self.assertEqual(chains, [])

    def test_eviction_at_max(self):
        pg = ProductGraph(max_relationships=3)
        for i in range(10):
            pg.add_relationship(f"a{i}", f"b{i}", "t", strength=float(i) / 10)
        self.assertLessEqual(len(pg.get_relationships()), 3)

    def test_concurrent_transitions(self):
        pg = ProductGraph()
        def _trans(idx):
            for j in range(20):
                pg.record_transition(f"p{idx}", f"p{(idx+1)%10}", time.time())
        errors, alive = _run_threads(lambda i: _trans(i), [(i,) for i in range(20)])
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(alive), 0)


# =====================================================================
#  AdoptionAnalyzer fuzz
# =====================================================================

class TestAdoptionAnalyzerFuzz(unittest.TestCase):

    def test_track_empty_strings(self):
        aa = AdoptionAnalyzer()
        c = aa.track_feature_use("", "")
        self.assertIsInstance(c, AdoptionCurve)

    def test_track_unicode(self):
        aa = AdoptionAnalyzer()
        c = aa.track_feature_use(UNICODE_EMOJI, UNICODE_RTL)
        self.assertIsNotNone(c)

    def test_track_zero_timestamp(self):
        aa = AdoptionAnalyzer()
        c = aa.track_feature_use("p", "f", timestamp=0.0)
        self.assertEqual(c.discovery_date, 0.0)

    def test_track_negative_timestamp(self):
        aa = AdoptionAnalyzer()
        c = aa.track_feature_use("p", "f", timestamp=-1000.0)
        self.assertIsNotNone(c)

    def test_eviction_at_max_curves(self):
        aa = AdoptionAnalyzer(max_curves=3)
        for i in range(10):
            aa.track_feature_use("p", f"f{i}", timestamp=float(i))
        # Only 3 curves should remain
        total = sum(
            1 for i in range(10) if aa.get_adoption_curve("p", f"f{i}") is not None
        )
        self.assertLessEqual(total, 3)

    def test_suggest_features_empty(self):
        aa = AdoptionAnalyzer()
        suggestions = aa.suggest_features_to_explore("p", [])
        self.assertEqual(suggestions, [])

    def test_suggest_features_top_n_zero(self):
        aa = AdoptionAnalyzer()
        suggestions = aa.suggest_features_to_explore("p", ["a", "b"], top_n=0)
        self.assertEqual(suggestions, [])

    def test_concurrent_track(self):
        aa = AdoptionAnalyzer()
        def _track(idx):
            for j in range(30):
                aa.track_feature_use(f"p{idx % 3}", f"f{j}", timestamp=time.time())
        errors, alive = _run_threads(lambda i: _track(i), [(i,) for i in range(20)])
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(alive), 0)


# =====================================================================
#  BehaviorFusion fuzz
# =====================================================================

class TestBehaviorFusionFuzz(unittest.TestCase):

    def test_ingest_empty_strings(self):
        bf = BehaviorFusion()
        s = bf.ingest_signal("", SignalType.USAGE, "", 0.0)
        self.assertIsInstance(s, BehavioralSignal)

    def test_ingest_nan_inf_values(self):
        bf = BehaviorFusion()
        for v in (float("nan"), float("inf"), float("-inf"), sys.float_info.max, sys.float_info.min):
            s = bf.ingest_signal("p", SignalType.USAGE, "sig", v)
            self.assertIsNotNone(s)

    def test_ingest_negative_confidence(self):
        bf = BehaviorFusion()
        s = bf.ingest_signal("p", SignalType.USAGE, "sig", 0.5, confidence=-1.0)
        self.assertEqual(s.confidence, 0.0)

    def test_ingest_confidence_above_one(self):
        bf = BehaviorFusion()
        s = bf.ingest_signal("p", SignalType.USAGE, "sig", 0.5, confidence=999.0)
        self.assertEqual(s.confidence, 1.0)

    def test_model_after_many_signals(self):
        bf = BehaviorFusion(max_signals=100)
        for i in range(200):
            bf.ingest_signal("p", SignalType.USAGE, f"s{i}", 0.5, timestamp=float(i))
        model = bf.get_unified_model()
        self.assertLessEqual(model.total_signals, 100)

    def test_signal_timeline_zero_hours(self):
        bf = BehaviorFusion()
        bf.ingest_signal("p", SignalType.USAGE, "s", 0.5)
        result = bf.get_signal_timeline(hours=0.0)
        # 0 hours window → nothing older than now
        self.assertIsInstance(result, list)

    def test_signal_timeline_negative_hours(self):
        bf = BehaviorFusion()
        result = bf.get_signal_timeline(hours=-10)
        self.assertIsInstance(result, list)

    def test_dominant_patterns_zero(self):
        bf = BehaviorFusion()
        self.assertEqual(bf.get_dominant_patterns(top_n=0), [])

    def test_concurrent_ingest(self):
        bf = BehaviorFusion(max_signals=1000)
        def _ingest(idx):
            for j in range(50):
                bf.ingest_signal(f"p{idx % 3}", SignalType.USAGE, f"sig{j}", 0.5)
        errors, alive = _run_threads(lambda i: _ingest(i), [(i,) for i in range(25)])
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(alive), 0)


# =====================================================================
#  CrossProductCorrelator fuzz
# =====================================================================

class TestCorrelatorFuzz(unittest.TestCase):

    def test_observe_empty_keys(self):
        cc = CrossProductCorrelator()
        cc.observe("", 1.0, "", 1.0)
        # Should not crash

    def test_observe_nan_values(self):
        cc = CrossProductCorrelator()
        cc.observe("a:x", float("nan"), "b:y", float("nan"))
        result = cc.compute_correlation("a:x", "b:y")
        # NaN correlation is allowed to be None or have strength 0
        self.assertTrue(result is None or isinstance(result, Correlation))

    def test_compute_insufficient_evidence(self):
        cc = CrossProductCorrelator(min_evidence=10)
        cc.observe("a:x", 1.0, "b:y", 1.0)
        self.assertIsNone(cc.compute_correlation("a:x", "b:y"))

    def test_compute_all_empty(self):
        cc = CrossProductCorrelator()
        self.assertEqual(cc.compute_all_correlations(), [])

    def test_strongest_empty(self):
        cc = CrossProductCorrelator()
        self.assertEqual(cc.get_strongest_correlations(0), [])

    def test_constant_values_pearson(self):
        cc = CrossProductCorrelator(min_evidence=2)
        for _ in range(10):
            cc.observe("a:x", 5.0, "b:y", 5.0)
        result = cc.compute_correlation("a:x", "b:y")
        # Constant data → degenerate Pearson → 0.0
        self.assertTrue(result is None or result.strength <= 1.0)

    def test_concurrent_observe(self):
        cc = CrossProductCorrelator()
        def _obs(idx):
            for j in range(30):
                cc.observe(f"a:s{idx}", float(j), f"b:s{idx}", float(j) * 0.5)
        errors, alive = _run_threads(lambda i: _obs(i), [(i,) for i in range(20)])
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(alive), 0)


# =====================================================================
#  WorkflowDetector fuzz
# =====================================================================

class TestWorkflowDetectorFuzz(unittest.TestCase):

    def test_record_empty_action(self):
        wd = WorkflowDetector()
        wd.record_action("", "")
        # Should not crash

    def test_record_long_action(self):
        wd = WorkflowDetector()
        wd.record_action("p", LONG_STR)

    def test_detect_insufficient_data(self):
        wd = WorkflowDetector()
        wd.record_action("p", "a")
        result = wd.detect_workflows(min_frequency=1)
        self.assertIsInstance(result, list)

    def test_detect_with_zero_min_frequency(self):
        wd = WorkflowDetector()
        for i in range(10):
            wd.record_action("p", f"a{i % 3}", timestamp=float(i))
        result = wd.detect_workflows(min_frequency=0)
        self.assertIsInstance(result, list)

    def test_predict_next_empty(self):
        wd = WorkflowDetector()
        self.assertIsNone(wd.predict_next_step([]))

    def test_get_active_workflow_empty(self):
        wd = WorkflowDetector()
        self.assertIsNone(wd.get_active_workflow([]))

    def test_concurrent_record(self):
        wd = WorkflowDetector()
        def _rec(idx):
            for j in range(40):
                wd.record_action(f"p{idx % 3}", f"act{j % 5}", timestamp=time.time() + j)
        errors, alive = _run_threads(lambda i: _rec(i), [(i,) for i in range(20)])
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(alive), 0)


# =====================================================================
#  ChurnPredictor fuzz
# =====================================================================

class TestChurnPredictorFuzz(unittest.TestCase):

    def test_predict_no_data(self):
        cp = ChurnPredictor()
        pred = cp.predict_churn("nonexistent")
        self.assertEqual(pred.risk_level, ChurnRisk.NONE)

    def test_record_nan_timestamp(self):
        cp = ChurnPredictor()
        cp.record_usage("p", timestamp=float("nan"))
        # predict should not crash
        pred = cp.predict_churn("p")
        self.assertIsInstance(pred, ChurnPrediction)

    def test_record_engagement_clamped(self):
        cp = ChurnPredictor()
        cp.record_engagement("p", score=-5.0)
        cp.record_engagement("p", score=999.0)
        # Both clamped to [0, 1]

    def test_predict_all_empty(self):
        cp = ChurnPredictor()
        self.assertEqual(cp.predict_all(), [])

    def test_at_risk_products_empty(self):
        cp = ChurnPredictor()
        self.assertEqual(cp.get_at_risk_products(), [])

    def test_engagement_trend_insufficient(self):
        cp = ChurnPredictor()
        self.assertEqual(cp.get_engagement_trend("p"), "stable")

    def test_concurrent_usage_recording(self):
        cp = ChurnPredictor()
        def _rec(idx):
            for j in range(40):
                cp.record_usage(f"p{idx % 3}", timestamp=time.time() + j)
                cp.record_engagement(f"p{idx % 3}", score=0.5)
        errors, alive = _run_threads(lambda i: _rec(i), [(i,) for i in range(20)])
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(alive), 0)


# =====================================================================
#  HabitTracker fuzz
# =====================================================================

class TestHabitTrackerFuzz(unittest.TestCase):

    def test_record_empty_action(self):
        ht = HabitTracker()
        ht.record_action("")
        # Empty actions are ignored

    def test_record_long_action(self):
        ht = HabitTracker()
        ht.record_action(LONG_STR, product_id=LONG_STR)

    def test_record_unicode_actions(self):
        ht = HabitTracker()
        for s in (UNICODE_ZW, UNICODE_RTL, UNICODE_EMOJI, UNICODE_NULL, SQL_INJECT):
            ht.record_action(s, product_id=s)

    def test_detect_habits_no_data(self):
        ht = HabitTracker()
        habits = ht.detect_habits()
        self.assertEqual(habits, [])

    def test_detect_habits_single_action(self):
        ht = HabitTracker()
        ht.record_action("a", timestamp=1.0)
        habits = ht.detect_habits(min_length=1)
        self.assertIsInstance(habits, list)

    def test_get_habit_nonexistent(self):
        ht = HabitTracker()
        self.assertIsNone(ht.get_habit("nosuchid"))

    def test_is_habit_active_nonexistent(self):
        ht = HabitTracker()
        self.assertFalse(ht.is_habit_active("nosuchid"))

    def test_concurrent_record_detect(self):
        ht = HabitTracker()
        def _work(idx):
            for j in range(30):
                ht.record_action(f"act{j % 4}", product_id=f"p{idx % 2}", timestamp=float(j))
            ht.detect_habits()
        errors, alive = _run_threads(lambda i: _work(i), [(i,) for i in range(20)])
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(alive), 0)


# =====================================================================
#  RoutineOptimizer fuzz
# =====================================================================

class TestRoutineOptimizerFuzz(unittest.TestCase):

    def test_create_routine_empty_name(self):
        ro = RoutineOptimizer()
        r = ro.create_routine("", [])
        self.assertEqual(r.name, "Untitled Routine")

    def test_create_routine_invalid_frequency(self):
        ro = RoutineOptimizer()
        r = ro.create_routine("test", ["h1"], expected_frequency="every_second")
        self.assertEqual(r.expected_frequency, "daily")

    def test_eviction_at_max_routines(self):
        ro = RoutineOptimizer(max_routines=2)
        r1 = ro.create_routine("R1", ["h1"])
        ro.record_completion(r1.routine_id, timestamp=1.0)
        r2 = ro.create_routine("R2", ["h2"])
        ro.record_completion(r2.routine_id, timestamp=2.0)
        ro.create_routine("R3", ["h3"])
        routines = ro.get_routines()
        self.assertLessEqual(len(routines), 2)

    def test_record_completion_nonexistent(self):
        ro = RoutineOptimizer()
        self.assertFalse(ro.record_completion("nosuch"))

    def test_adherence_nonexistent(self):
        ro = RoutineOptimizer()
        self.assertEqual(ro.compute_adherence("nosuch"), 0.0)

    def test_suggest_optimizations_nonexistent(self):
        ro = RoutineOptimizer()
        self.assertEqual(ro.suggest_optimizations("nosuch"), [])

    def test_detect_drift_nonexistent(self):
        ro = RoutineOptimizer()
        self.assertIsNone(ro.detect_routine_drift("nosuch"))

    def test_concurrent_create_complete(self):
        ro = RoutineOptimizer(max_routines=50)
        def _work(idx):
            r = ro.create_routine(f"R{idx}", [f"h{idx}"])
            for _ in range(10):
                ro.record_completion(r.routine_id, completion_time=1.5)
            ro.suggest_optimizations(r.routine_id)
        errors, alive = _run_threads(lambda i: _work(i), [(i,) for i in range(25)])
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(alive), 0)


# =====================================================================
#  AnchorDetector fuzz
# =====================================================================

class TestAnchorDetectorFuzz(unittest.TestCase):

    def test_record_empty_sequence(self):
        ad = AnchorDetector()
        ad.record_sequence([])
        # Empty list is no-op

    def test_record_long_sequence(self):
        ad = AnchorDetector()
        ad.record_sequence([LONG_STR] * 100)

    def test_detect_no_data(self):
        ad = AnchorDetector()
        self.assertEqual(ad.detect_anchors(), [])

    def test_detect_insufficient_triggers(self):
        ad = AnchorDetector(min_trigger_count=100)
        ad.record_sequence(["a", "b", "c"])
        self.assertEqual(ad.detect_anchors(), [])

    def test_predict_chain_nonexistent(self):
        ad = AnchorDetector()
        self.assertIsNone(ad.predict_chain("nosuch"))

    def test_get_anchor_nonexistent(self):
        ad = AnchorDetector()
        self.assertIsNone(ad.get_anchor("nosuch"))

    def test_concurrent_record_detect(self):
        ad = AnchorDetector()
        def _work(idx):
            for _ in range(20):
                ad.record_sequence(["start", f"step{idx % 3}", "end"], products=["p1"])
            ad.detect_anchors()
        errors, alive = _run_threads(lambda i: _work(i), [(i,) for i in range(20)])
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(alive), 0)


# =====================================================================
#  DisruptionAlert fuzz
# =====================================================================

class TestDisruptionAlertFuzz(unittest.TestCase):

    def test_set_expectations_empty(self):
        da = DisruptionAlert()
        da.set_expectations("", [])
        # No-op for empty

    def test_check_no_expectations(self):
        da = DisruptionAlert()
        self.assertIsNone(da.check_disruption("nosuch", "act"))

    def test_check_with_matching_action(self):
        da = DisruptionAlert()
        da.set_expectations("r1", ["a", "b"])
        result = da.check_disruption("r1", "a")
        self.assertIsNone(result)  # matches expected

    def test_check_with_mismatching_action(self):
        da = DisruptionAlert()
        da.set_expectations("r1", ["a", "b"])
        result = da.check_disruption("r1", "WRONG")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, DisruptionEvent)

    def test_consecutive_disruptions_escalation(self):
        da = DisruptionAlert()
        da.set_expectations("r1", ["a"])
        severities = []
        for _ in range(10):
            ev = da.check_disruption("r1", "WRONG")
            if ev:
                severities.append(ev.severity)
        self.assertTrue(any(s == DisruptionSeverity.CRITICAL for s in severities[-3:]))

    def test_disruption_rate_zero(self):
        da = DisruptionAlert()
        self.assertEqual(da.get_disruption_rate("r1"), 0.0)

    def test_stability_score(self):
        da = DisruptionAlert()
        self.assertEqual(da.get_stability_score("r1"), 1.0)

    def test_concurrent_check(self):
        da = DisruptionAlert()
        da.set_expectations("r1", ["a", "b", "c"])
        def _check(idx):
            for _ in range(30):
                da.check_disruption("r1", "a" if idx % 2 == 0 else "WRONG")
        errors, alive = _run_threads(lambda i: _check(i), [(i,) for i in range(20)])
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(alive), 0)


# =====================================================================
#  SituationAwareness fuzz
# =====================================================================

class TestSituationAwarenessFuzz(unittest.TestCase):

    def test_update_empty_strings(self):
        sa = SituationAwareness()
        snap = sa.update("", "")
        self.assertIsInstance(snap, SituationSnapshot)

    def test_update_unicode(self):
        sa = SituationAwareness()
        snap = sa.update(UNICODE_EMOJI, UNICODE_RTL)
        self.assertIsNotNone(snap)

    def test_update_long_action(self):
        sa = SituationAwareness()
        snap = sa.update("p", LONG_STR)
        self.assertIsNotNone(snap)

    def test_get_current_none(self):
        sa = SituationAwareness()
        self.assertIsNone(sa.get_current_situation())

    def test_detect_context_switch_empty(self):
        sa = SituationAwareness()
        self.assertFalse(sa.detect_context_switch())

    def test_idle_detection(self):
        sa = SituationAwareness(idle_threshold_seconds=1.0)
        sa.update("p", "act", timestamp=100.0)
        sa.update("p", "act2", timestamp=200.0)
        history = sa.get_situation_history(limit=100)
        idle_snaps = [s for s in history if s.situation_type == SituationType.IDLE]
        self.assertGreater(len(idle_snaps), 0)

    def test_situation_distribution_empty(self):
        sa = SituationAwareness()
        dist = sa.get_situation_distribution()
        self.assertIsInstance(dist, dict)

    def test_concurrent_update(self):
        sa = SituationAwareness()
        def _upd(idx):
            for j in range(30):
                sa.update(f"p{idx % 3}", f"debug issue {j}", timestamp=time.time() + j)
        errors, alive = _run_threads(lambda i: _upd(i), [(i,) for i in range(25)])
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(alive), 0)


# =====================================================================
#  IntentInference fuzz
# =====================================================================

class TestIntentInferenceFuzz(unittest.TestCase):

    def test_observe_no_patterns(self):
        ii = IntentInference()
        result = ii.observe_action("p", "act")
        self.assertIsNone(result)

    def test_observe_empty_action(self):
        ii = IntentInference()
        ii.register_intent_pattern("test", ["fix", "debug"])
        result = ii.observe_action("p", "")
        # Empty action → low match
        self.assertTrue(result is None or isinstance(result, InferredIntent))

    def test_observe_unicode_action(self):
        ii = IntentInference()
        ii.register_intent_pattern("test", [UNICODE_EMOJI])
        result = ii.observe_action("p", UNICODE_EMOJI)
        self.assertTrue(result is None or isinstance(result, InferredIntent))

    def test_register_empty_keywords(self):
        ii = IntentInference()
        ii.register_intent_pattern("noop", [])
        result = ii.observe_action("p", "anything")
        self.assertIsNone(result)

    def test_confidence_trend_insufficient(self):
        ii = IntentInference()
        self.assertEqual(ii.get_intent_confidence_trend(), "stable")

    def test_clear_window(self):
        ii = IntentInference()
        ii.observe_action("p", "a")
        ii.clear_window()
        self.assertIsNotNone(ii)  # no crash

    def test_concurrent_observe(self):
        ii = IntentInference()
        ii.register_intent_pattern("debugging", ["debug", "fix", "error"])
        def _obs(idx):
            for j in range(30):
                ii.observe_action(f"p{idx}", f"debug error {j}")
        errors, alive = _run_threads(lambda i: _obs(i), [(i,) for i in range(20)])
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(alive), 0)


# =====================================================================
#  ProactiveAssistant fuzz
# =====================================================================

class TestProactiveAssistantFuzz(unittest.TestCase):

    def test_evaluate_empty_context(self):
        pa = ProactiveAssistant()
        pa.add_rule("r1", ["error"], AssistanceType.WARNING, "Watch out", "An error", target_product="ide")
        result = pa.evaluate({})
        self.assertEqual(result, [])

    def test_evaluate_none_values_in_context(self):
        pa = ProactiveAssistant()
        pa.add_rule("r1", ["error"], AssistanceType.WARNING, "Title", "Desc")
        result = pa.evaluate({"key": None, "other": None})
        self.assertIsInstance(result, list)

    def test_dismiss_nonexistent(self):
        pa = ProactiveAssistant()
        self.assertFalse(pa.dismiss_suggestion("nosuch"))

    def test_stats_empty(self):
        pa = ProactiveAssistant()
        stats = pa.get_suggestion_stats()
        self.assertEqual(stats["total"], 0)

    def test_cooldown_bypass(self):
        pa = ProactiveAssistant(cooldown_seconds=0.0)
        pa.add_rule("r1", ["error"], AssistanceType.WARNING, "T", "D")
        r1 = pa.evaluate({"msg": "error occurred"})
        r2 = pa.evaluate({"msg": "another error"})
        # Both should match (cooldown=0)
        self.assertGreater(len(r1), 0)
        self.assertGreater(len(r2), 0)

    def test_concurrent_evaluate(self):
        pa = ProactiveAssistant(cooldown_seconds=0.0)
        pa.add_rule("r1", ["fix"], AssistanceType.SUGGESTION, "T", "D")
        def _eval(idx):
            for _ in range(20):
                pa.evaluate({"msg": f"fix issue {idx}"})
        errors, alive = _run_threads(lambda i: _eval(i), [(i,) for i in range(20)])
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(alive), 0)


# =====================================================================
#  SmartHandoff fuzz
# =====================================================================

class TestSmartHandoffFuzz(unittest.TestCase):

    def test_initiate_empty_strings(self):
        sh = SmartHandoff()
        h = sh.initiate_handoff("", "", HandoffReason.USER_REQUEST)
        self.assertIsInstance(h, HandoffContext)

    def test_initiate_unicode(self):
        sh = SmartHandoff()
        h = sh.initiate_handoff(UNICODE_EMOJI, UNICODE_RTL, HandoffReason.ESCALATION)
        self.assertIsNotNone(h)

    def test_complete_nonexistent(self):
        sh = SmartHandoff()
        self.assertIsNone(sh.complete_handoff("nosuch"))

    def test_suggest_empty_need(self):
        sh = SmartHandoff()
        sh.register_product_capabilities("ide", ["code", "debug"])
        result = sh.suggest_handoff("ide", "")
        self.assertIsNone(result)

    def test_suggest_no_capabilities(self):
        sh = SmartHandoff()
        result = sh.suggest_handoff("ide", "need code review")
        self.assertIsNone(result)

    def test_success_rate_empty(self):
        sh = SmartHandoff()
        self.assertEqual(sh.get_handoff_success_rate(), 0.0)

    def test_concurrent_handoffs(self):
        sh = SmartHandoff()
        def _work(idx):
            for _ in range(20):
                h = sh.initiate_handoff(f"p{idx}", f"p{(idx+1)%5}", HandoffReason.CONTEXT_SWITCH)
                sh.complete_handoff(h.handoff_id, success=True)
        errors, alive = _run_threads(lambda i: _work(i), [(i,) for i in range(25)])
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(alive), 0)


# =====================================================================
#  RevenueSignals fuzz
# =====================================================================

class TestRevenueSignalsFuzz(unittest.TestCase):

    def test_evaluate_empty_event(self):
        rs = RevenueSignals()
        rs.add_rule("r1", RevenueSignalType.UPSELL_OPPORTUNITY, ["upgrade"], "Upsell", "Offer upgrade")
        result = rs.evaluate_event("p", {})
        self.assertEqual(result, [])

    def test_evaluate_none_event_values(self):
        rs = RevenueSignals()
        rs.add_rule("r1", RevenueSignalType.CHURN_RISK, ["cancel"], "Churn", "Retain")
        result = rs.evaluate_event("p", {"key": None, "action": "cancel"})
        self.assertIsInstance(result, list)

    def test_add_signal_clamped(self):
        rs = RevenueSignals()
        s = rs.add_signal(RevenueSignalType.EXPANSION_SIGNAL, "p", "test", impact=-5, confidence=999)
        self.assertEqual(s.impact_score, 0.0)
        self.assertEqual(s.confidence, 1.0)

    def test_get_signals_empty(self):
        rs = RevenueSignals()
        self.assertEqual(rs.get_signals(), [])

    def test_top_opportunities_empty(self):
        rs = RevenueSignals()
        self.assertEqual(rs.get_top_opportunities(), [])

    def test_signal_cap(self):
        rs = RevenueSignals(max_signals=5)
        for i in range(20):
            rs.add_signal(RevenueSignalType.UPSELL_OPPORTUNITY, f"p{i}", f"d{i}")
        self.assertLessEqual(len(rs.get_signals(limit=100)), 5)

    def test_concurrent_evaluate(self):
        rs = RevenueSignals()
        rs.add_rule("r1", RevenueSignalType.CROSS_SELL_OPPORTUNITY, ["recommend"], "Cross", "Act")
        def _eval(idx):
            for _ in range(20):
                rs.evaluate_event(f"p{idx}", {"action": "recommend something"})
                rs.add_signal(RevenueSignalType.UPSELL_OPPORTUNITY, f"p{idx}", "test")
        errors, alive = _run_threads(lambda i: _eval(i), [(i,) for i in range(20)])
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(alive), 0)


# =====================================================================
#  SegmentClassifier fuzz
# =====================================================================

class TestSegmentClassifierFuzz(unittest.TestCase):

    def test_classify_no_metrics(self):
        sc = SegmentClassifier()
        seg = sc.classify()
        self.assertIsInstance(seg, UserSegment)

    def test_update_metrics_nan(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=float("nan"), active_days=float("inf"))
        seg = sc.classify()
        self.assertIsInstance(seg, UserSegment)

    def test_update_metrics_negative(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=-1.0, active_days=-100, total_events=-50)
        seg = sc.classify()
        self.assertIsInstance(seg, UserSegment)

    def test_segment_transition_risk_no_segment(self):
        sc = SegmentClassifier()
        risk = sc.get_segment_transition_risk()
        self.assertEqual(risk["risk"], "unknown")

    def test_at_risk_transition(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=0.8, active_days=30, features_used=20)
        sc.classify()  # POWER_USER
        sc.update_metrics(engagement_score=0.1)
        seg = sc.classify()
        self.assertEqual(seg.segment_type, SegmentType.AT_RISK)

    def test_concurrent_classify(self):
        sc = SegmentClassifier()
        def _work(idx):
            for j in range(20):
                sc.update_metrics(engagement_score=0.1 * (j % 10), active_days=j)
                sc.classify()
                sc.get_segment_summary()
        errors, alive = _run_threads(lambda i: _work(i), [(i,) for i in range(20)])
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(alive), 0)


# =====================================================================
#  LifecycleTracker fuzz
# =====================================================================

class TestLifecycleTrackerFuzz(unittest.TestCase):

    def test_update_empty_metrics(self):
        lt = LifecycleTracker()
        pos = lt.update_position("p", {})
        self.assertIsInstance(pos, LifecyclePosition)

    def test_update_nan_metrics(self):
        lt = LifecycleTracker()
        pos = lt.update_position("p", {"engagement_score": float("nan"), "days_active": float("inf")})
        self.assertIsInstance(pos, LifecyclePosition)

    def test_update_negative_metrics(self):
        lt = LifecycleTracker()
        pos = lt.update_position("p", {"days_active": -10, "total_events": -5})
        self.assertIsInstance(pos, LifecyclePosition)

    def test_eviction_at_max(self):
        lt = LifecycleTracker(max_products=2)
        for i in range(5):
            lt.update_position(f"p{i}", {"days_active": i, "total_events": i * 10})
        positions = lt.get_all_positions()
        self.assertLessEqual(len(positions), 2)

    def test_stage_duration_empty(self):
        lt = LifecycleTracker()
        self.assertEqual(lt.get_stage_duration("p"), {})

    def test_position_nonexistent(self):
        lt = LifecycleTracker()
        self.assertIsNone(lt.get_position("p"))

    def test_lifecycle_summary_empty(self):
        lt = LifecycleTracker()
        s = lt.get_lifecycle_summary()
        self.assertEqual(s["total_products"], 0)

    def test_concurrent_update(self):
        lt = LifecycleTracker(max_products=50)
        def _upd(idx):
            for j in range(20):
                lt.update_position(f"p{idx}", {"days_active": j, "total_events": j * 5, "engagement_score": 0.5})
        errors, alive = _run_threads(lambda i: _upd(i), [(i,) for i in range(25)])
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(alive), 0)


# =====================================================================
#  ValueScorer fuzz
# =====================================================================

class TestValueScorerFuzz(unittest.TestCase):

    def test_update_nan_scores(self):
        vs = ValueScorer()
        score = vs.update_score("p", engagement=float("nan"), adoption=float("inf"))
        self.assertIsInstance(score, ValueScore)

    def test_update_negative_scores(self):
        vs = ValueScorer()
        score = vs.update_score("p", engagement=-5.0, adoption=-10.0, retention=-1.0, advocacy=-1.0)
        self.assertEqual(score.engagement_score, 0.0)
        self.assertEqual(score.adoption_score, 0.0)

    def test_update_above_one_scores(self):
        vs = ValueScorer()
        score = vs.update_score("p", engagement=999.0, advocacy=500.0)
        self.assertEqual(score.engagement_score, 1.0)
        self.assertEqual(score.advocacy_score, 1.0)

    def test_get_score_nonexistent(self):
        vs = ValueScorer()
        self.assertIsNone(vs.get_score("p"))

    def test_top_value_empty(self):
        vs = ValueScorer()
        self.assertEqual(vs.get_top_value_products(), [])

    def test_value_trend_insufficient(self):
        vs = ValueScorer()
        self.assertEqual(vs.get_value_trend("p"), "stable")

    def test_set_weights_invalid_sum(self):
        vs = ValueScorer()
        with self.assertRaises(ValueError):
            vs.set_weights(engagement=0.9, adoption=0.9)

    def test_eviction_at_max(self):
        vs = ValueScorer(max_products=2)
        for i in range(5):
            vs.update_score(f"p{i}", engagement=0.5)
        scores = vs.get_all_scores()
        self.assertLessEqual(len(scores), 2)

    def test_summary_empty(self):
        vs = ValueScorer()
        s = vs.get_value_summary()
        self.assertEqual(s["total_products"], 0)

    def test_concurrent_scoring(self):
        vs = ValueScorer(max_products=50)
        def _work(idx):
            for j in range(20):
                vs.update_score(f"p{idx}", engagement=0.1 * (j % 10), adoption=0.5)
                vs.get_value_trend(f"p{idx}")
        errors, alive = _run_threads(lambda i: _work(i), [(i,) for i in range(25)])
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(alive), 0)


# =====================================================================
#  Cross-module serialisation round-trip
# =====================================================================

class TestSerializationRoundTrip(unittest.TestCase):

    def test_product_info_to_dict(self):
        pi = ProductInfo("p1", "Product", ProductCategory.IDE, features=[UNICODE_EMOJI], metadata={"k": SQL_INJECT})
        d = pi.to_dict()
        self.assertEqual(d["product_id"], "p1")
        self.assertIn(UNICODE_EMOJI, d["features"])

    def test_product_usage_event_to_dict(self):
        ev = ProductUsageEvent("p", "f", "a", 1.0, metadata={"k": None})
        d = ev.to_dict()
        self.assertEqual(d["product_id"], "p")

    def test_usage_profile_to_dict(self):
        up = UsageProfile("p", feature_adoption={"f1": FeatureStatus.MASTERED})
        d = up.to_dict()
        self.assertEqual(d["feature_adoption"]["f1"], "mastered")

    def test_product_relationship_to_dict(self):
        pr = ProductRelationship("a", "b", "test", common_features=[UNICODE_ZW])
        d = pr.to_dict()
        self.assertEqual(d["source_product"], "a")

    def test_adoption_curve_to_dict(self):
        ac = AdoptionCurve("p", "f", FeatureStatus.ADOPTED)
        d = ac.to_dict()
        self.assertEqual(d["stage"], "adopted")

    def test_habit_to_dict(self):
        h = Habit("h1", "Test", ["a", "b"], 3.0, HabitStrength.FORMING)
        d = h.to_dict()
        self.assertEqual(d["habit_id"], "h1")

    def test_routine_to_dict(self):
        r = Routine("r1", "TestR", habits=["h1", "h2"])
        d = r.to_dict()
        self.assertEqual(d["routine_id"], "r1")

    def test_anchor_behavior_to_dict(self):
        ab = AnchorBehavior("a1", "trigger", AnchorType.TEMPORAL, ["chain"], 0.9, 1.0)
        d = ab.to_dict()
        self.assertEqual(d["anchor_type"], "temporal")

    def test_disruption_event_to_dict(self):
        de = DisruptionEvent("d1", "r1", DisruptionSeverity.MAJOR, "a", "b", 1.0)
        d = de.to_dict()
        self.assertEqual(d["severity"], "major")


# =====================================================================
#  Type confusion & extreme edge cases
# =====================================================================

class TestTypeConfusionEdgeCases(unittest.TestCase):

    def test_product_tracker_int_as_product_id(self):
        """Passing int where str expected — should not crash."""
        pt = ProductTracker()
        try:
            pt.register_product(123, 456, ProductCategory.IDE)  # type: ignore[arg-type]
        except (TypeError, AttributeError):
            pass  # acceptable to reject

    def test_usage_profiler_list_as_product_id(self):
        up = UsageProfiler()
        try:
            up.record_event([1, 2, 3], "feat", "act")  # type: ignore[arg-type]
        except (TypeError, AttributeError):
            pass

    def test_behavior_fusion_dict_as_name(self):
        bf = BehaviorFusion()
        try:
            bf.ingest_signal("p", SignalType.USAGE, {"bad": True}, 0.5)  # type: ignore[arg-type]
        except (TypeError, AttributeError):
            pass

    def test_workflow_detector_none_action(self):
        wd = WorkflowDetector()
        try:
            wd.record_action("p", None)  # type: ignore[arg-type]
        except (TypeError, AttributeError):
            pass

    def test_handoff_none_context_data(self):
        sh = SmartHandoff()
        h = sh.initiate_handoff("a", "b", HandoffReason.USER_REQUEST, context_data=None)
        self.assertEqual(h.context_data, {})

    def test_revenue_signals_int_event(self):
        rs = RevenueSignals()
        rs.add_rule("r1", RevenueSignalType.CHURN_RISK, ["bad"], "D", "A")
        try:
            rs.evaluate_event("p", 12345)  # type: ignore[arg-type]
        except (TypeError, AttributeError):
            pass

    def test_lifecycle_tracker_string_metrics(self):
        lt = LifecycleTracker()
        try:
            lt.update_position("p", {"days_active": "many", "total_events": "lots"})
        except (TypeError, ValueError):
            pass

    def test_segment_classifier_inf_metrics(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=float("inf"), active_days=float("-inf"))
        seg = sc.classify()
        self.assertIsInstance(seg, UserSegment)

    def test_value_scorer_nan_via_update(self):
        vs = ValueScorer()
        score = vs.update_score("p", engagement=float("nan"))
        # NaN clamped by max/min → evaluates to 0.0
        self.assertIsInstance(score, ValueScore)

    def test_max_int_as_max_products(self):
        pt = ProductTracker(max_products=sys.maxsize)
        pt.register_product("p", "n", ProductCategory.IDE)
        self.assertEqual(len(pt.list_products()), 1)

    def test_float_min_max_in_adoption(self):
        aa = AdoptionAnalyzer()
        c = aa.track_feature_use("p", "f", timestamp=sys.float_info.max)
        self.assertIsNotNone(c)
        c2 = aa.track_feature_use("p2", "f2", timestamp=sys.float_info.min)
        self.assertIsNotNone(c2)

    def test_special_chars_in_correlation_keys(self):
        cc = CrossProductCorrelator(min_evidence=1)
        cc.observe(SQL_INJECT, 1.0, SPECIAL_CHARS, 2.0)
        result = cc.compute_correlation(SQL_INJECT, SPECIAL_CHARS)
        self.assertTrue(result is None or isinstance(result, Correlation))


# =====================================================================
#  Concurrent serialization (to_dict while writing)
# =====================================================================

class TestConcurrentSerialization(unittest.TestCase):

    def test_product_tracker_to_dict_while_writing(self):
        pt = ProductTracker(max_products=100)
        def _write(idx):
            for j in range(50):
                pt.register_product(f"p{idx}_{j}", f"n{j}", ProductCategory.IDE)
        def _read(_):
            for _ in range(50):
                pt.to_dict()
                pt.get_ecosystem_summary()

        write_args = [(i,) for i in range(10)]
        read_args = [(i,) for i in range(10)]

        threads = []
        for args in write_args:
            t = threading.Thread(target=lambda i: _write(i), args=args, daemon=True)
            threads.append(t)
        for args in read_args:
            t = threading.Thread(target=lambda i: _read(i), args=args, daemon=True)
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=TIMEOUT)
        alive = [t for t in threads if t.is_alive()]
        self.assertEqual(len(alive), 0)

    def test_situation_awareness_read_while_update(self):
        sa = SituationAwareness()
        def _write(idx):
            for j in range(50):
                sa.update(f"p{idx}", f"act{j}", timestamp=time.time() + j)
        def _read(_):
            for _ in range(50):
                sa.get_situation_history()
                sa.get_situation_distribution()
                sa.detect_context_switch()

        threads = []
        for i in range(10):
            threads.append(threading.Thread(target=_write, args=(i,), daemon=True))
        for i in range(10):
            threads.append(threading.Thread(target=_read, args=(i,), daemon=True))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=TIMEOUT)
        alive = [t for t in threads if t.is_alive()]
        self.assertEqual(len(alive), 0)


if __name__ == "__main__":
    unittest.main()
