"""Comprehensive tests for the Cross-Domain Behavioral Fusion module."""

from __future__ import annotations

import threading
import time
import unittest

from memoria.fusion import (
    BehaviorFusion,
    BehavioralSignal,
    ChurnPrediction,
    ChurnPredictor,
    ChurnRisk,
    Correlation,
    CorrelationType,
    CrossProductCorrelator,
    DetectedWorkflow,
    SignalType,
    UnifiedUserModel,
    WorkflowDetector,
    WorkflowType,
)


# ======================================================================
# Types / Enums
# ======================================================================


class TestSignalType(unittest.TestCase):
    """SignalType enum tests."""

    def test_values(self) -> None:
        self.assertEqual(SignalType.USAGE.value, "usage")
        self.assertEqual(SignalType.BEHAVIORAL.value, "behavioral")
        self.assertEqual(SignalType.TEMPORAL.value, "temporal")
        self.assertEqual(SignalType.EMOTIONAL.value, "emotional")
        self.assertEqual(SignalType.PREFERENCE.value, "preference")
        self.assertEqual(SignalType.PERFORMANCE.value, "performance")

    def test_member_count(self) -> None:
        self.assertEqual(len(SignalType), 6)


class TestCorrelationType(unittest.TestCase):
    """CorrelationType enum tests."""

    def test_values(self) -> None:
        self.assertEqual(CorrelationType.POSITIVE.value, "positive")
        self.assertEqual(CorrelationType.NEGATIVE.value, "negative")
        self.assertEqual(CorrelationType.TEMPORAL.value, "temporal")
        self.assertEqual(CorrelationType.CAUSAL.value, "causal")
        self.assertEqual(CorrelationType.COMPLEMENTARY.value, "complementary")

    def test_member_count(self) -> None:
        self.assertEqual(len(CorrelationType), 5)


class TestChurnRisk(unittest.TestCase):
    """ChurnRisk enum tests."""

    def test_values(self) -> None:
        self.assertEqual(ChurnRisk.NONE.value, "none")
        self.assertEqual(ChurnRisk.LOW.value, "low")
        self.assertEqual(ChurnRisk.MEDIUM.value, "medium")
        self.assertEqual(ChurnRisk.HIGH.value, "high")
        self.assertEqual(ChurnRisk.CRITICAL.value, "critical")

    def test_member_count(self) -> None:
        self.assertEqual(len(ChurnRisk), 5)


class TestWorkflowType(unittest.TestCase):
    """WorkflowType enum tests."""

    def test_values(self) -> None:
        self.assertEqual(WorkflowType.SEQUENTIAL.value, "sequential")
        self.assertEqual(WorkflowType.PARALLEL.value, "parallel")
        self.assertEqual(WorkflowType.CONDITIONAL.value, "conditional")
        self.assertEqual(WorkflowType.RECURRING.value, "recurring")

    def test_member_count(self) -> None:
        self.assertEqual(len(WorkflowType), 4)


# ======================================================================
# Dataclasses
# ======================================================================


class TestBehavioralSignal(unittest.TestCase):
    def test_creation(self) -> None:
        sig = BehavioralSignal(
            source_product="editor",
            signal_type=SignalType.USAGE,
            name="file_open",
            value=0.8,
            timestamp=1000.0,
        )
        self.assertEqual(sig.source_product, "editor")
        self.assertEqual(sig.signal_type, SignalType.USAGE)
        self.assertEqual(sig.name, "file_open")
        self.assertEqual(sig.value, 0.8)
        self.assertEqual(sig.confidence, 1.0)
        self.assertEqual(sig.metadata, {})

    def test_with_metadata(self) -> None:
        sig = BehavioralSignal(
            source_product="ide",
            signal_type=SignalType.BEHAVIORAL,
            name="autocomplete",
            value=0.5,
            timestamp=2000.0,
            confidence=0.9,
            metadata={"lang": "python"},
        )
        self.assertEqual(sig.metadata["lang"], "python")
        self.assertEqual(sig.confidence, 0.9)


class TestUnifiedUserModel(unittest.TestCase):
    def test_defaults(self) -> None:
        model = UnifiedUserModel()
        self.assertEqual(model.user_id, "default")
        self.assertEqual(model.total_signals, 0)
        self.assertEqual(model.products_active, [])
        self.assertEqual(model.engagement_score, 0.0)
        self.assertEqual(model.consistency_score, 0.0)
        self.assertEqual(model.signal_breakdown, {})


class TestCorrelation(unittest.TestCase):
    def test_creation(self) -> None:
        c = Correlation(
            signal_a="A:click",
            signal_b="B:scroll",
            correlation_type=CorrelationType.POSITIVE,
            strength=0.7,
        )
        self.assertEqual(c.signal_a, "A:click")
        self.assertEqual(c.strength, 0.7)
        self.assertEqual(c.evidence_count, 0)


class TestDetectedWorkflow(unittest.TestCase):
    def test_creation(self) -> None:
        wf = DetectedWorkflow(
            workflow_id="abc",
            name="test",
            workflow_type=WorkflowType.SEQUENTIAL,
            steps=["A:open", "B:edit"],
        )
        self.assertEqual(wf.steps, ["A:open", "B:edit"])
        self.assertEqual(wf.frequency, 0)


class TestChurnPrediction(unittest.TestCase):
    def test_creation(self) -> None:
        cp = ChurnPrediction(
            product_id="ide",
            risk_level=ChurnRisk.HIGH,
            probability=0.75,
        )
        self.assertEqual(cp.product_id, "ide")
        self.assertEqual(cp.risk_level, ChurnRisk.HIGH)
        self.assertEqual(cp.days_until_likely_churn, -1)
        self.assertEqual(cp.warning_signals, [])


# ======================================================================
# BehaviorFusion
# ======================================================================


class TestBehaviorFusionIngest(unittest.TestCase):
    """BehaviorFusion — signal ingestion."""

    def setUp(self) -> None:
        self.fusion = BehaviorFusion(max_signals=100)

    def test_ingest_returns_signal(self) -> None:
        sig = self.fusion.ingest_signal("editor", SignalType.USAGE, "open", 0.5)
        self.assertIsInstance(sig, BehavioralSignal)
        self.assertEqual(sig.source_product, "editor")

    def test_ingest_auto_timestamp(self) -> None:
        before = time.time()
        sig = self.fusion.ingest_signal("editor", SignalType.USAGE, "open", 0.5)
        after = time.time()
        self.assertGreaterEqual(sig.timestamp, before)
        self.assertLessEqual(sig.timestamp, after)

    def test_ingest_explicit_timestamp(self) -> None:
        sig = self.fusion.ingest_signal(
            "editor", SignalType.USAGE, "open", 0.5, timestamp=42.0
        )
        self.assertEqual(sig.timestamp, 42.0)

    def test_ingest_clamps_confidence(self) -> None:
        sig = self.fusion.ingest_signal(
            "editor", SignalType.USAGE, "open", 0.5, confidence=5.0
        )
        self.assertEqual(sig.confidence, 1.0)
        sig2 = self.fusion.ingest_signal(
            "editor", SignalType.USAGE, "open", 0.5, confidence=-1.0
        )
        self.assertEqual(sig2.confidence, 0.0)

    def test_ingest_metadata(self) -> None:
        sig = self.fusion.ingest_signal(
            "editor", SignalType.USAGE, "open", 0.5, metadata={"k": "v"}
        )
        self.assertEqual(sig.metadata, {"k": "v"})

    def test_ingest_none_metadata(self) -> None:
        sig = self.fusion.ingest_signal(
            "editor", SignalType.USAGE, "open", 0.5, metadata=None
        )
        self.assertEqual(sig.metadata, {})


class TestBehaviorFusionUnifiedModel(unittest.TestCase):
    """BehaviorFusion — unified model computation."""

    def setUp(self) -> None:
        self.fusion = BehaviorFusion(max_signals=100)

    def test_empty_model(self) -> None:
        model = self.fusion.get_unified_model()
        self.assertEqual(model.total_signals, 0)
        self.assertEqual(model.products_active, [])
        self.assertEqual(model.engagement_score, 0.0)

    def test_model_after_ingest(self) -> None:
        now = time.time()
        self.fusion.ingest_signal("editor", SignalType.USAGE, "open", 0.8, timestamp=now)
        self.fusion.ingest_signal("browser", SignalType.USAGE, "click", 0.6, timestamp=now)
        model = self.fusion.get_unified_model()
        self.assertEqual(model.total_signals, 2)
        self.assertIn("editor", model.products_active)
        self.assertIn("browser", model.products_active)

    def test_model_signal_breakdown(self) -> None:
        self.fusion.ingest_signal("a", SignalType.USAGE, "x", 0.5)
        self.fusion.ingest_signal("a", SignalType.USAGE, "y", 0.5)
        self.fusion.ingest_signal("a", SignalType.BEHAVIORAL, "z", 0.5)
        model = self.fusion.get_unified_model()
        self.assertEqual(model.signal_breakdown["usage"], 2)
        self.assertEqual(model.signal_breakdown["behavioral"], 1)

    def test_model_consistency_single_product(self) -> None:
        self.fusion.ingest_signal("editor", SignalType.USAGE, "a", 0.5)
        model = self.fusion.get_unified_model()
        self.assertEqual(model.consistency_score, 1.0)

    def test_model_engagement_bounded(self) -> None:
        for i in range(20):
            self.fusion.ingest_signal("p", SignalType.USAGE, "a", 0.9)
        model = self.fusion.get_unified_model()
        self.assertGreaterEqual(model.engagement_score, 0.0)
        self.assertLessEqual(model.engagement_score, 1.0)

    def test_model_cross_product_activity(self) -> None:
        self.fusion.ingest_signal("a", SignalType.USAGE, "x", 0.5)
        self.fusion.ingest_signal("b", SignalType.USAGE, "x", 0.5)
        model = self.fusion.get_unified_model()
        self.assertGreater(model.cross_product_activity, 0.0)


class TestBehaviorFusionProductSignals(unittest.TestCase):
    """BehaviorFusion — product signal queries."""

    def setUp(self) -> None:
        self.fusion = BehaviorFusion()
        now = time.time()
        for i in range(10):
            self.fusion.ingest_signal("editor", SignalType.USAGE, f"sig_{i}", 0.5, timestamp=now + i)
        for i in range(5):
            self.fusion.ingest_signal("browser", SignalType.BEHAVIORAL, f"sig_{i}", 0.3, timestamp=now + i)

    def test_get_product_signals(self) -> None:
        sigs = self.fusion.get_product_signals("editor")
        self.assertEqual(len(sigs), 10)
        self.assertTrue(all(s.source_product == "editor" for s in sigs))

    def test_get_product_signals_limit(self) -> None:
        sigs = self.fusion.get_product_signals("editor", limit=3)
        self.assertEqual(len(sigs), 3)

    def test_get_product_signals_type_filter(self) -> None:
        sigs = self.fusion.get_product_signals("browser", signal_type=SignalType.BEHAVIORAL)
        self.assertEqual(len(sigs), 5)

    def test_get_product_signals_type_mismatch(self) -> None:
        sigs = self.fusion.get_product_signals("browser", signal_type=SignalType.USAGE)
        self.assertEqual(len(sigs), 0)

    def test_get_product_signals_unknown_product(self) -> None:
        sigs = self.fusion.get_product_signals("nonexistent")
        self.assertEqual(len(sigs), 0)


class TestBehaviorFusionTimeline(unittest.TestCase):
    """BehaviorFusion — signal timeline."""

    def setUp(self) -> None:
        self.fusion = BehaviorFusion()

    def test_timeline_empty(self) -> None:
        result = self.fusion.get_signal_timeline()
        self.assertEqual(result, [])

    def test_timeline_recent(self) -> None:
        now = time.time()
        self.fusion.ingest_signal("a", SignalType.USAGE, "x", 0.5, timestamp=now)
        self.fusion.ingest_signal("a", SignalType.USAGE, "y", 0.5, timestamp=now - 7200)
        result = self.fusion.get_signal_timeline(hours=1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "x")

    def test_timeline_with_name_filter(self) -> None:
        now = time.time()
        self.fusion.ingest_signal("a", SignalType.USAGE, "x", 0.5, timestamp=now)
        self.fusion.ingest_signal("a", SignalType.USAGE, "y", 0.5, timestamp=now)
        result = self.fusion.get_signal_timeline(name="x", hours=1)
        self.assertEqual(len(result), 1)


class TestBehaviorFusionEngagement(unittest.TestCase):
    """BehaviorFusion — engagement score."""

    def setUp(self) -> None:
        self.fusion = BehaviorFusion(decay_halflife_days=30.0)

    def test_engagement_empty(self) -> None:
        score = self.fusion.compute_engagement_score()
        self.assertEqual(score, 0.0)

    def test_engagement_recent_signals(self) -> None:
        now = time.time()
        for _ in range(10):
            self.fusion.ingest_signal("a", SignalType.USAGE, "x", 0.8, timestamp=now)
        score = self.fusion.compute_engagement_score()
        self.assertGreater(score, 0.0)

    def test_engagement_per_product(self) -> None:
        now = time.time()
        self.fusion.ingest_signal("a", SignalType.USAGE, "x", 0.9, timestamp=now)
        self.fusion.ingest_signal("b", SignalType.USAGE, "x", 0.1, timestamp=now)
        score_a = self.fusion.compute_engagement_score("a")
        score_b = self.fusion.compute_engagement_score("b")
        self.assertGreater(score_a, score_b)

    def test_engagement_decays_with_age(self) -> None:
        now = time.time()
        self.fusion.ingest_signal(
            "a", SignalType.USAGE, "x", 0.8, timestamp=now - 90 * 86400
        )
        old_score = self.fusion.compute_engagement_score()
        fusion2 = BehaviorFusion(decay_halflife_days=30.0)
        fusion2.ingest_signal("a", SignalType.USAGE, "x", 0.8, timestamp=now)
        new_score = fusion2.compute_engagement_score()
        self.assertGreater(new_score, old_score)


class TestBehaviorFusionDominantPatterns(unittest.TestCase):
    """BehaviorFusion — dominant patterns."""

    def test_empty(self) -> None:
        fusion = BehaviorFusion()
        patterns = fusion.get_dominant_patterns()
        self.assertEqual(patterns, [])

    def test_top_patterns(self) -> None:
        fusion = BehaviorFusion()
        for _ in range(10):
            fusion.ingest_signal("a", SignalType.USAGE, "click", 0.5)
        for _ in range(5):
            fusion.ingest_signal("a", SignalType.USAGE, "scroll", 0.5)
        for _ in range(2):
            fusion.ingest_signal("a", SignalType.USAGE, "type", 0.5)
        patterns = fusion.get_dominant_patterns(top_n=2)
        self.assertEqual(len(patterns), 2)
        self.assertEqual(patterns[0], "click")

    def test_top_n_zero(self) -> None:
        fusion = BehaviorFusion()
        fusion.ingest_signal("a", SignalType.USAGE, "x", 0.5)
        self.assertEqual(fusion.get_dominant_patterns(top_n=0), [])


class TestBehaviorFusionMaxSignals(unittest.TestCase):
    """BehaviorFusion — max signals rotation."""

    def test_rotation(self) -> None:
        fusion = BehaviorFusion(max_signals=5)
        for i in range(10):
            fusion.ingest_signal("a", SignalType.USAGE, f"sig_{i}", 0.5)
        model = fusion.get_unified_model()
        self.assertEqual(model.total_signals, 5)
        sigs = fusion.get_product_signals("a", limit=100)
        names = [s.name for s in sigs]
        self.assertNotIn("sig_0", names)
        self.assertIn("sig_9", names)


class TestBehaviorFusionThreadSafety(unittest.TestCase):
    """BehaviorFusion — concurrent access."""

    def test_thread_safety(self) -> None:
        fusion = BehaviorFusion(max_signals=500)
        errors: list[Exception] = []

        def writer() -> None:
            try:
                for i in range(50):
                    fusion.ingest_signal("p", SignalType.USAGE, f"s{i}", 0.5)
            except Exception as exc:
                errors.append(exc)

        def reader() -> None:
            try:
                for _ in range(50):
                    fusion.get_unified_model()
                    fusion.compute_engagement_score()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer) for _ in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


# ======================================================================
# CrossProductCorrelator
# ======================================================================


class TestCorrelatorObserve(unittest.TestCase):
    """CrossProductCorrelator — observation recording."""

    def setUp(self) -> None:
        self.corr = CrossProductCorrelator(min_evidence=3)

    def test_observe_creates_pair(self) -> None:
        self.corr.observe("A:click", 1.0, "B:scroll", 2.0)
        # No crash, pair recorded internally
        result = self.corr.compute_all_correlations()
        self.assertEqual(len(result), 0)  # Not enough evidence yet

    def test_observe_auto_timestamp(self) -> None:
        self.corr.observe("A:x", 1.0, "B:y", 2.0)
        # Should not raise


class TestCorrelatorCompute(unittest.TestCase):
    """CrossProductCorrelator — correlation computation."""

    def setUp(self) -> None:
        self.corr = CrossProductCorrelator(min_evidence=3)

    def test_positive_correlation(self) -> None:
        for i in range(10):
            self.corr.observe("A:x", float(i), "B:y", float(i) * 1.5)
        result = self.corr.compute_correlation("A:x", "B:y")
        self.assertIsNotNone(result)
        self.assertEqual(result.correlation_type, CorrelationType.POSITIVE)
        self.assertGreater(result.strength, 0.3)

    def test_negative_correlation(self) -> None:
        for i in range(10):
            self.corr.observe("A:x", float(i), "B:y", float(10 - i))
        result = self.corr.compute_correlation("A:x", "B:y")
        self.assertIsNotNone(result)
        self.assertEqual(result.correlation_type, CorrelationType.NEGATIVE)
        self.assertGreater(result.strength, 0.3)

    def test_complementary_correlation(self) -> None:
        for i in range(10):
            self.corr.observe("A:x", 1.0, "B:y", 1.0)
        result = self.corr.compute_correlation("A:x", "B:y")
        self.assertIsNotNone(result)
        # Constant values -> r=0, but co-occurrence is high -> COMPLEMENTARY
        self.assertEqual(result.correlation_type, CorrelationType.COMPLEMENTARY)

    def test_insufficient_evidence(self) -> None:
        self.corr.observe("A:x", 1.0, "B:y", 2.0)
        result = self.corr.compute_correlation("A:x", "B:y")
        self.assertIsNone(result)

    def test_confidence_scaling(self) -> None:
        for i in range(20):
            self.corr.observe("A:x", float(i), "B:y", float(i))
        result = self.corr.compute_correlation("A:x", "B:y")
        self.assertIsNotNone(result)
        self.assertEqual(result.confidence, 1.0)  # 20/20

    def test_evidence_count(self) -> None:
        for i in range(7):
            self.corr.observe("A:x", float(i), "B:y", float(i))
        result = self.corr.compute_correlation("A:x", "B:y")
        self.assertIsNotNone(result)
        self.assertEqual(result.evidence_count, 7)

    def test_no_observations(self) -> None:
        result = self.corr.compute_correlation("X:a", "Y:b")
        self.assertIsNone(result)

    def test_canonical_key_order(self) -> None:
        for i in range(5):
            self.corr.observe("B:y", float(i), "A:x", float(i))
        result = self.corr.compute_correlation("B:y", "A:x")
        self.assertIsNotNone(result)
        self.assertEqual(result.signal_a, "A:x")
        self.assertEqual(result.signal_b, "B:y")


class TestCorrelatorAll(unittest.TestCase):
    """CrossProductCorrelator — compute all correlations."""

    def test_compute_all(self) -> None:
        corr = CrossProductCorrelator(min_evidence=3)
        for i in range(10):
            corr.observe("A:x", float(i), "B:y", float(i))
            corr.observe("C:a", float(i), "D:b", float(10 - i))
        results = corr.compute_all_correlations()
        self.assertEqual(len(results), 2)

    def test_compute_all_empty(self) -> None:
        corr = CrossProductCorrelator()
        results = corr.compute_all_correlations()
        self.assertEqual(results, [])


class TestCorrelatorFilter(unittest.TestCase):
    """CrossProductCorrelator — filtering."""

    def setUp(self) -> None:
        self.corr = CrossProductCorrelator(min_evidence=3)
        for i in range(10):
            self.corr.observe("A:x", float(i), "B:y", float(i))
            self.corr.observe("C:a", float(i), "D:b", float(i) * 0.5)
        self.corr.compute_all_correlations()

    def test_filter_by_product(self) -> None:
        results = self.corr.get_correlations(product_id="A")
        self.assertTrue(all("A" in c.signal_a or "A" in c.signal_b for c in results))

    def test_filter_by_min_strength(self) -> None:
        results = self.corr.get_correlations(min_strength=0.5)
        self.assertTrue(all(c.strength >= 0.5 for c in results))

    def test_filter_no_match(self) -> None:
        results = self.corr.get_correlations(product_id="ZZZZZ")
        self.assertEqual(len(results), 0)


class TestCorrelatorStrongest(unittest.TestCase):
    """CrossProductCorrelator — strongest correlations."""

    def test_strongest(self) -> None:
        corr = CrossProductCorrelator(min_evidence=3)
        for i in range(10):
            corr.observe("A:x", float(i), "B:y", float(i))
            corr.observe("C:a", float(i), "D:b", float(i) * 0.1 + 0.5)
        corr.compute_all_correlations()
        top = corr.get_strongest_correlations(top_n=1)
        self.assertEqual(len(top), 1)

    def test_strongest_empty(self) -> None:
        corr = CrossProductCorrelator()
        self.assertEqual(corr.get_strongest_correlations(), [])

    def test_strongest_top_n_zero(self) -> None:
        corr = CrossProductCorrelator()
        self.assertEqual(corr.get_strongest_correlations(top_n=0), [])


class TestCorrelatorTemporal(unittest.TestCase):
    """CrossProductCorrelator — temporal correlations."""

    def test_find_temporal(self) -> None:
        corr = CrossProductCorrelator(min_evidence=3)
        now = time.time()
        for i in range(5):
            corr.observe("A:x", 1.0, "B:y", 1.0, timestamp=now + i)
        results = corr.find_temporal_correlations("A:x", time_window_seconds=3600)
        self.assertTrue(len(results) >= 1)
        self.assertEqual(results[0].correlation_type, CorrelationType.TEMPORAL)

    def test_find_temporal_no_match(self) -> None:
        corr = CrossProductCorrelator(min_evidence=3)
        results = corr.find_temporal_correlations("X:nonexistent")
        self.assertEqual(results, [])


class TestCorrelatorMaxCap(unittest.TestCase):
    """CrossProductCorrelator — max correlations cap."""

    def test_max_cap(self) -> None:
        corr = CrossProductCorrelator(min_evidence=1, max_correlations=2)
        for i in range(5):
            for j in range(5):
                if i != j:
                    corr.observe(f"P{i}:s", float(i), f"P{j}:s", float(j))
        results = corr.compute_all_correlations()
        self.assertLessEqual(len(results), 2)


class TestCorrelatorThreadSafety(unittest.TestCase):
    """CrossProductCorrelator — concurrent access."""

    def test_thread_safety(self) -> None:
        corr = CrossProductCorrelator(min_evidence=3)
        errors: list[Exception] = []

        def writer() -> None:
            try:
                for i in range(50):
                    corr.observe("A:x", float(i), "B:y", float(i))
            except Exception as exc:
                errors.append(exc)

        def reader() -> None:
            try:
                for _ in range(20):
                    corr.compute_all_correlations()
                    corr.get_strongest_correlations()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer) for _ in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


# ======================================================================
# WorkflowDetector
# ======================================================================


class TestWorkflowDetectorRecord(unittest.TestCase):
    """WorkflowDetector — action recording."""

    def setUp(self) -> None:
        self.wd = WorkflowDetector()

    def test_record_action(self) -> None:
        self.wd.record_action("editor", "open")
        # No crash; verify via detect
        workflows = self.wd.detect_workflows(min_frequency=1, min_length=2)
        # Single action can't form a workflow
        self.assertIsInstance(workflows, list)

    def test_record_auto_timestamp(self) -> None:
        self.wd.record_action("editor", "open")

    def test_record_explicit_timestamp(self) -> None:
        self.wd.record_action("editor", "open", timestamp=1000.0)


class TestWorkflowDetectorDetect(unittest.TestCase):
    """WorkflowDetector — workflow detection."""

    def setUp(self) -> None:
        self.wd = WorkflowDetector()

    def test_detect_sequential(self) -> None:
        for _ in range(4):
            self.wd.record_action("editor", "open", timestamp=time.time())
            self.wd.record_action("browser", "search", timestamp=time.time())
        workflows = self.wd.detect_workflows(min_frequency=3, min_length=2)
        self.assertTrue(len(workflows) >= 1)
        found = any(
            wf.workflow_type == WorkflowType.SEQUENTIAL
            for wf in workflows
        )
        self.assertTrue(found)

    def test_detect_recurring(self) -> None:
        for _ in range(6):
            self.wd.record_action("A", "x")
            self.wd.record_action("B", "y")
        workflows = self.wd.detect_workflows(min_frequency=3, min_length=2)
        recurring = [wf for wf in workflows if wf.workflow_type == WorkflowType.RECURRING]
        self.assertTrue(len(recurring) >= 1)

    def test_detect_empty(self) -> None:
        workflows = self.wd.detect_workflows()
        self.assertEqual(workflows, [])

    def test_detect_single_action(self) -> None:
        self.wd.record_action("A", "x")
        workflows = self.wd.detect_workflows(min_frequency=1)
        self.assertIsInstance(workflows, list)

    def test_detect_confidence(self) -> None:
        for _ in range(10):
            self.wd.record_action("A", "x")
            self.wd.record_action("B", "y")
        workflows = self.wd.detect_workflows(min_frequency=3, min_length=2)
        for wf in workflows:
            self.assertGreaterEqual(wf.confidence, 0.0)
            self.assertLessEqual(wf.confidence, 1.0)


class TestWorkflowDetectorGetWorkflows(unittest.TestCase):
    """WorkflowDetector — workflow queries."""

    def setUp(self) -> None:
        self.wd = WorkflowDetector()
        for _ in range(5):
            self.wd.record_action("editor", "open")
            self.wd.record_action("browser", "search")
        self.wd.detect_workflows(min_frequency=3, min_length=2)

    def test_get_all(self) -> None:
        workflows = self.wd.get_workflows()
        self.assertTrue(len(workflows) >= 1)

    def test_get_filtered(self) -> None:
        wfs = self.wd.get_workflows(product_id="editor")
        for wf in wfs:
            self.assertTrue(
                any(s.startswith("editor:") for s in wf.steps)
            )

    def test_get_filtered_no_match(self) -> None:
        wfs = self.wd.get_workflows(product_id="nonexistent")
        self.assertEqual(wfs, [])


class TestWorkflowDetectorActive(unittest.TestCase):
    """WorkflowDetector — active workflow detection."""

    def setUp(self) -> None:
        self.wd = WorkflowDetector()
        for _ in range(5):
            self.wd.record_action("A", "step1")
            self.wd.record_action("B", "step2")
            self.wd.record_action("C", "step3")
        self.wd.detect_workflows(min_frequency=3, min_length=2)

    def test_active_workflow(self) -> None:
        wf = self.wd.get_active_workflow(["A:step1", "B:step2"])
        self.assertIsNotNone(wf)

    def test_active_workflow_partial(self) -> None:
        wf = self.wd.get_active_workflow(["A:step1"])
        self.assertIsNotNone(wf)

    def test_active_workflow_empty(self) -> None:
        wf = self.wd.get_active_workflow([])
        self.assertIsNone(wf)

    def test_active_workflow_no_match(self) -> None:
        wf = self.wd.get_active_workflow(["X:unknown"])
        self.assertIsNone(wf)


class TestWorkflowDetectorPredict(unittest.TestCase):
    """WorkflowDetector — next step prediction."""

    def setUp(self) -> None:
        self.wd = WorkflowDetector()
        for _ in range(5):
            self.wd.record_action("A", "step1")
            self.wd.record_action("B", "step2")
            self.wd.record_action("C", "step3")
        self.wd.detect_workflows(min_frequency=3, min_length=2)

    def test_predict_next(self) -> None:
        nxt = self.wd.predict_next_step(["A:step1"])
        self.assertIsNotNone(nxt)
        self.assertEqual(nxt, "B:step2")

    def test_predict_mid_workflow(self) -> None:
        nxt = self.wd.predict_next_step(["A:step1", "B:step2"])
        self.assertIsNotNone(nxt)
        self.assertEqual(nxt, "C:step3")

    def test_predict_empty(self) -> None:
        nxt = self.wd.predict_next_step([])
        self.assertIsNone(nxt)

    def test_predict_no_match(self) -> None:
        nxt = self.wd.predict_next_step(["Z:unknown"])
        self.assertIsNone(nxt)


class TestWorkflowDetectorSummary(unittest.TestCase):
    """WorkflowDetector — summary."""

    def test_summary_empty(self) -> None:
        wd = WorkflowDetector()
        s = wd.get_workflow_summary()
        self.assertEqual(s["total_workflows"], 0)
        self.assertIsNone(s["most_frequent"])

    def test_summary_with_data(self) -> None:
        wd = WorkflowDetector()
        for _ in range(5):
            wd.record_action("A", "x")
            wd.record_action("B", "y")
        wd.detect_workflows(min_frequency=3)
        s = wd.get_workflow_summary()
        self.assertGreater(s["total_workflows"], 0)
        self.assertIsNotNone(s["most_frequent"])
        self.assertGreater(s["avg_length"], 0)


class TestWorkflowDetectorMaxCap(unittest.TestCase):
    """WorkflowDetector — max caps."""

    def test_max_sequences(self) -> None:
        wd = WorkflowDetector(max_sequences=5)
        for i in range(10):
            wd.record_action("A", f"act_{i}")
        # Should not exceed 5 internally
        self.assertLessEqual(len(wd._action_sequences), 5)

    def test_max_workflows(self) -> None:
        wd = WorkflowDetector(max_sequences=10000, max_workflows=2)
        # Generate many distinct repeating patterns
        for _ in range(5):
            wd.record_action("A", "a1")
            wd.record_action("A", "a2")
        for _ in range(5):
            wd.record_action("B", "b1")
            wd.record_action("B", "b2")
        for _ in range(5):
            wd.record_action("C", "c1")
            wd.record_action("C", "c2")
        wd.detect_workflows(min_frequency=3)
        self.assertLessEqual(len(wd._detected_workflows), 2)


class TestWorkflowDetectorThreadSafety(unittest.TestCase):
    """WorkflowDetector — concurrent access."""

    def test_thread_safety(self) -> None:
        wd = WorkflowDetector()
        errors: list[Exception] = []

        def writer() -> None:
            try:
                for i in range(50):
                    wd.record_action("P", f"a{i % 3}")
            except Exception as exc:
                errors.append(exc)

        def reader() -> None:
            try:
                for _ in range(20):
                    wd.detect_workflows(min_frequency=2)
                    wd.get_workflow_summary()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer) for _ in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


# ======================================================================
# ChurnPredictor
# ======================================================================


class TestChurnPredictorRecording(unittest.TestCase):
    """ChurnPredictor — usage & engagement recording."""

    def setUp(self) -> None:
        self.cp = ChurnPredictor()

    def test_record_usage(self) -> None:
        self.cp.record_usage("ide")
        pred = self.cp.predict_churn("ide")
        self.assertEqual(pred.product_id, "ide")

    def test_record_usage_auto_timestamp(self) -> None:
        before = time.time()
        self.cp.record_usage("ide")
        self.assertTrue(len(self.cp._usage_history["ide"]) == 1)
        self.assertGreaterEqual(self.cp._usage_history["ide"][0], before)

    def test_record_engagement(self) -> None:
        self.cp.record_engagement("ide", 0.8)
        self.assertEqual(len(self.cp._engagement_scores["ide"]), 1)

    def test_record_engagement_clamps(self) -> None:
        self.cp.record_engagement("ide", 5.0)
        self.assertEqual(self.cp._engagement_scores["ide"][0][1], 1.0)
        self.cp.record_engagement("ide", -1.0)
        self.assertEqual(self.cp._engagement_scores["ide"][1][1], 0.0)


class TestChurnPredictorPredictNone(unittest.TestCase):
    """ChurnPredictor — NONE risk."""

    def test_stable_usage(self) -> None:
        cp = ChurnPredictor(inactivity_threshold_days=30)
        now = time.time()
        # Regular usage every day for 30 days
        for i in range(30):
            cp.record_usage("ide", timestamp=now - i * 86400)
            cp.record_engagement("ide", 0.8, timestamp=now - i * 86400)
        pred = cp.predict_churn("ide")
        self.assertEqual(pred.risk_level, ChurnRisk.NONE)
        self.assertEqual(pred.probability, 0.0)

    def test_no_data(self) -> None:
        cp = ChurnPredictor()
        pred = cp.predict_churn("unknown")
        self.assertEqual(pred.risk_level, ChurnRisk.NONE)
        self.assertEqual(pred.confidence, 0.0)


class TestChurnPredictorPredictLow(unittest.TestCase):
    """ChurnPredictor — LOW risk."""

    def test_minor_decrease(self) -> None:
        cp = ChurnPredictor(inactivity_threshold_days=30)
        now = time.time()
        # First half: frequent usage (every 1 day)
        for i in range(20):
            cp.record_usage("ide", timestamp=now - (40 - i) * 86400)
        # Second half: slightly less frequent (every 1.5 days)
        for i in range(10):
            cp.record_usage("ide", timestamp=now - (10 - i) * 1.5 * 86400)
        # Slight engagement dip
        cp.record_engagement("ide", 0.8, timestamp=now - 20 * 86400)
        cp.record_engagement("ide", 0.7, timestamp=now)
        pred = cp.predict_churn("ide")
        self.assertIn(pred.risk_level, [ChurnRisk.LOW, ChurnRisk.NONE, ChurnRisk.MEDIUM])


class TestChurnPredictorPredictMedium(unittest.TestCase):
    """ChurnPredictor — MEDIUM risk."""

    def test_declining_engagement(self) -> None:
        cp = ChurnPredictor(inactivity_threshold_days=30)
        now = time.time()
        # Regular recent usage
        for i in range(10):
            cp.record_usage("ide", timestamp=now - i * 86400)
        # Declining engagement
        cp.record_engagement("ide", 0.9, timestamp=now - 20 * 86400)
        cp.record_engagement("ide", 0.85, timestamp=now - 15 * 86400)
        cp.record_engagement("ide", 0.6, timestamp=now - 10 * 86400)
        cp.record_engagement("ide", 0.4, timestamp=now - 5 * 86400)
        cp.record_engagement("ide", 0.3, timestamp=now)
        pred = cp.predict_churn("ide")
        self.assertIn(pred.risk_level, [ChurnRisk.MEDIUM, ChurnRisk.HIGH])


class TestChurnPredictorPredictHigh(unittest.TestCase):
    """ChurnPredictor — HIGH risk."""

    def test_no_usage_past_threshold(self) -> None:
        cp = ChurnPredictor(inactivity_threshold_days=30)
        now = time.time()
        cp.record_usage("ide", timestamp=now - 35 * 86400)
        pred = cp.predict_churn("ide")
        self.assertEqual(pred.risk_level, ChurnRisk.HIGH)
        self.assertTrue(len(pred.warning_signals) > 0)
        self.assertTrue(len(pred.recommended_actions) > 0)

    def test_engagement_dropped_50pct(self) -> None:
        cp = ChurnPredictor(inactivity_threshold_days=30)
        now = time.time()
        for i in range(10):
            cp.record_usage("ide", timestamp=now - i * 86400)
        cp.record_engagement("ide", 1.0, timestamp=now - 10 * 86400)
        cp.record_engagement("ide", 0.4, timestamp=now)
        pred = cp.predict_churn("ide")
        self.assertIn(pred.risk_level, [ChurnRisk.HIGH, ChurnRisk.MEDIUM])


class TestChurnPredictorPredictCritical(unittest.TestCase):
    """ChurnPredictor — CRITICAL risk."""

    def test_critical_no_usage_and_declining(self) -> None:
        cp = ChurnPredictor(inactivity_threshold_days=10)
        now = time.time()
        cp.record_usage("ide", timestamp=now - 25 * 86400)  # 2.5x threshold
        # Declining engagement
        cp.record_engagement("ide", 0.9, timestamp=now - 30 * 86400)
        cp.record_engagement("ide", 0.5, timestamp=now - 20 * 86400)
        cp.record_engagement("ide", 0.2, timestamp=now)
        pred = cp.predict_churn("ide")
        self.assertEqual(pred.risk_level, ChurnRisk.CRITICAL)
        self.assertEqual(pred.days_until_likely_churn, 0)


class TestChurnPredictorPredictAll(unittest.TestCase):
    """ChurnPredictor — predict all products."""

    def test_predict_all(self) -> None:
        cp = ChurnPredictor()
        now = time.time()
        cp.record_usage("ide", timestamp=now)
        cp.record_usage("browser", timestamp=now - 100 * 86400)
        preds = cp.predict_all()
        self.assertEqual(len(preds), 2)
        products = {p.product_id for p in preds}
        self.assertEqual(products, {"ide", "browser"})

    def test_predict_all_empty(self) -> None:
        cp = ChurnPredictor()
        self.assertEqual(cp.predict_all(), [])


class TestChurnPredictorAtRisk(unittest.TestCase):
    """ChurnPredictor — at-risk products."""

    def test_at_risk(self) -> None:
        cp = ChurnPredictor(inactivity_threshold_days=10)
        now = time.time()
        cp.record_usage("healthy", timestamp=now)
        cp.record_usage("risky", timestamp=now - 15 * 86400)
        at_risk = cp.get_at_risk_products(min_risk=ChurnRisk.MEDIUM)
        risky_ids = {p.product_id for p in at_risk}
        self.assertIn("risky", risky_ids)
        self.assertNotIn("healthy", risky_ids)

    def test_at_risk_none_threshold(self) -> None:
        cp = ChurnPredictor()
        cp.record_usage("x", timestamp=time.time())
        results = cp.get_at_risk_products(min_risk=ChurnRisk.NONE)
        self.assertTrue(len(results) >= 1)


class TestChurnPredictorEngagementTrend(unittest.TestCase):
    """ChurnPredictor — engagement trend."""

    def test_growing(self) -> None:
        cp = ChurnPredictor()
        now = time.time()
        cp.record_engagement("ide", 0.3, timestamp=now - 5)
        cp.record_engagement("ide", 0.4, timestamp=now - 4)
        cp.record_engagement("ide", 0.7, timestamp=now - 3)
        cp.record_engagement("ide", 0.9, timestamp=now - 2)
        self.assertEqual(cp.get_engagement_trend("ide"), "growing")

    def test_declining(self) -> None:
        cp = ChurnPredictor()
        now = time.time()
        cp.record_engagement("ide", 0.9, timestamp=now - 5)
        cp.record_engagement("ide", 0.8, timestamp=now - 4)
        cp.record_engagement("ide", 0.4, timestamp=now - 3)
        cp.record_engagement("ide", 0.2, timestamp=now - 2)
        self.assertEqual(cp.get_engagement_trend("ide"), "declining")

    def test_stable(self) -> None:
        cp = ChurnPredictor()
        now = time.time()
        cp.record_engagement("ide", 0.5, timestamp=now - 4)
        cp.record_engagement("ide", 0.5, timestamp=now - 3)
        cp.record_engagement("ide", 0.5, timestamp=now - 2)
        cp.record_engagement("ide", 0.5, timestamp=now - 1)
        self.assertEqual(cp.get_engagement_trend("ide"), "stable")

    def test_no_data(self) -> None:
        cp = ChurnPredictor()
        self.assertEqual(cp.get_engagement_trend("unknown"), "stable")

    def test_single_point(self) -> None:
        cp = ChurnPredictor()
        cp.record_engagement("ide", 0.5)
        self.assertEqual(cp.get_engagement_trend("ide"), "stable")


class TestChurnPredictorInactivityThreshold(unittest.TestCase):
    """ChurnPredictor — custom inactivity threshold."""

    def test_custom_threshold(self) -> None:
        cp = ChurnPredictor(inactivity_threshold_days=5)
        now = time.time()
        cp.record_usage("ide", timestamp=now - 6 * 86400)
        pred = cp.predict_churn("ide")
        self.assertIn(pred.risk_level, [ChurnRisk.HIGH, ChurnRisk.CRITICAL])


class TestChurnPredictorMaxHistory(unittest.TestCase):
    """ChurnPredictor — max history cap."""

    def test_max_history_usage(self) -> None:
        cp = ChurnPredictor(max_history=5)
        for i in range(10):
            cp.record_usage("ide", timestamp=float(i))
        self.assertEqual(len(cp._usage_history["ide"]), 5)

    def test_max_history_engagement(self) -> None:
        cp = ChurnPredictor(max_history=5)
        for i in range(10):
            cp.record_engagement("ide", 0.5, timestamp=float(i))
        self.assertEqual(len(cp._engagement_scores["ide"]), 5)


class TestChurnPredictorThreadSafety(unittest.TestCase):
    """ChurnPredictor — concurrent access."""

    def test_thread_safety(self) -> None:
        cp = ChurnPredictor()
        errors: list[Exception] = []

        def writer() -> None:
            try:
                for i in range(50):
                    cp.record_usage("ide", timestamp=time.time())
                    cp.record_engagement("ide", 0.5)
            except Exception as exc:
                errors.append(exc)

        def reader() -> None:
            try:
                for _ in range(30):
                    cp.predict_churn("ide")
                    cp.get_engagement_trend("ide")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer) for _ in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


# ======================================================================
# Integration / edge-case tests
# ======================================================================


class TestEmptyStateEdgeCases(unittest.TestCase):
    """Edge cases when all components are freshly initialised."""

    def test_fusion_empty_model(self) -> None:
        f = BehaviorFusion()
        m = f.get_unified_model()
        self.assertEqual(m.total_signals, 0)
        self.assertEqual(m.dominant_patterns, [])

    def test_correlator_empty(self) -> None:
        c = CrossProductCorrelator()
        self.assertEqual(c.compute_all_correlations(), [])
        self.assertEqual(c.get_strongest_correlations(), [])
        self.assertEqual(c.get_correlations(), [])

    def test_workflow_empty(self) -> None:
        w = WorkflowDetector()
        self.assertEqual(w.detect_workflows(), [])
        self.assertEqual(w.get_workflows(), [])
        self.assertIsNone(w.get_active_workflow([]))
        self.assertIsNone(w.predict_next_step([]))

    def test_churn_empty(self) -> None:
        c = ChurnPredictor()
        self.assertEqual(c.predict_all(), [])
        self.assertEqual(c.get_at_risk_products(), [])
        self.assertEqual(c.get_engagement_trend("x"), "stable")


class TestCrossModuleIntegration(unittest.TestCase):
    """Integration: feed BehaviorFusion signals into other components."""

    def test_fusion_to_correlator(self) -> None:
        fusion = BehaviorFusion()
        corr = CrossProductCorrelator(min_evidence=3)
        now = time.time()

        for i in range(10):
            s1 = fusion.ingest_signal("editor", SignalType.USAGE, "edits", float(i), timestamp=now + i)
            s2 = fusion.ingest_signal("browser", SignalType.USAGE, "searches", float(i) * 2, timestamp=now + i)
            corr.observe(
                f"{s1.source_product}:{s1.name}", s1.value,
                f"{s2.source_product}:{s2.name}", s2.value,
                timestamp=now + i,
            )

        results = corr.compute_all_correlations()
        self.assertTrue(len(results) >= 1)

    def test_fusion_to_churn(self) -> None:
        fusion = BehaviorFusion()
        churn = ChurnPredictor()
        now = time.time()

        for i in range(10):
            sig = fusion.ingest_signal("ide", SignalType.USAGE, "cmd", 0.8, timestamp=now - i * 86400)
            churn.record_usage("ide", timestamp=sig.timestamp)
            score = fusion.compute_engagement_score("ide")
            churn.record_engagement("ide", score, timestamp=sig.timestamp)

        pred = churn.predict_churn("ide")
        self.assertIsInstance(pred, ChurnPrediction)


class TestPearsonEdgeCases(unittest.TestCase):
    """Pearson correlation edge cases."""

    def test_constant_values(self) -> None:
        corr = CrossProductCorrelator(min_evidence=3)
        for _ in range(5):
            corr.observe("A:x", 5.0, "B:y", 5.0)
        result = corr.compute_correlation("A:x", "B:y")
        # Constant -> r=0 -> should be COMPLEMENTARY (co-occurrence=1.0)
        self.assertIsNotNone(result)

    def test_single_observation(self) -> None:
        corr = CrossProductCorrelator(min_evidence=1)
        corr.observe("A:x", 1.0, "B:y", 2.0)
        result = corr.compute_correlation("A:x", "B:y")
        self.assertIsNotNone(result)

    def test_zero_values(self) -> None:
        corr = CrossProductCorrelator(min_evidence=3)
        for _ in range(5):
            corr.observe("A:x", 0.0, "B:y", 0.0)
        result = corr.compute_correlation("A:x", "B:y")
        self.assertIsNotNone(result)


class TestNegativeAndBoundaryInputs(unittest.TestCase):
    """Test with negative and boundary values."""

    def test_negative_signal_value(self) -> None:
        f = BehaviorFusion()
        sig = f.ingest_signal("a", SignalType.USAGE, "x", -1.0)
        self.assertEqual(sig.value, -1.0)

    def test_zero_hours_timeline(self) -> None:
        f = BehaviorFusion()
        f.ingest_signal("a", SignalType.USAGE, "x", 0.5)
        result = f.get_signal_timeline(hours=0)
        # Zero-hour window should return nothing (or only exact-now signals)
        self.assertIsInstance(result, list)

    def test_zero_limit_product_signals(self) -> None:
        f = BehaviorFusion()
        f.ingest_signal("a", SignalType.USAGE, "x", 0.5)
        result = f.get_product_signals("a", limit=0)
        self.assertEqual(result, [])

    def test_churn_negative_threshold(self) -> None:
        # min clamp should prevent issues
        cp = ChurnPredictor(inactivity_threshold_days=-5)
        self.assertGreater(cp._inactivity_threshold, 0)


if __name__ == "__main__":
    unittest.main()
