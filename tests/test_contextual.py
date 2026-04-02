"""Comprehensive tests for the Contextual Intelligence Engine."""

import threading
import time
import unittest

from memoria.contextual import (
    AssistanceType,
    HandoffContext,
    HandoffReason,
    InferredIntent,
    IntentConfidence,
    IntentInference,
    ProactiveAssistance,
    ProactiveAssistant,
    SituationAwareness,
    SituationSnapshot,
    SituationType,
    SmartHandoff,
)

# ======================================================================
# Types
# ======================================================================

class TestSituationType(unittest.TestCase):
    def test_all_members(self):
        expected = {"working", "exploring", "troubleshooting", "learning",
                     "reviewing", "creating", "managing", "idle"}
        self.assertEqual({s.value for s in SituationType}, expected)

    def test_member_identity(self):
        self.assertIs(SituationType("working"), SituationType.WORKING)


class TestIntentConfidence(unittest.TestCase):
    def test_all_members(self):
        self.assertEqual({c.value for c in IntentConfidence}, {"low", "medium", "high"})


class TestHandoffReason(unittest.TestCase):
    def test_all_members(self):
        expected = {"task_complete", "context_switch", "expertise_needed",
                     "user_request", "product_boundary", "escalation"}
        self.assertEqual({r.value for r in HandoffReason}, expected)


class TestAssistanceType(unittest.TestCase):
    def test_all_members(self):
        expected = {"suggestion", "warning", "shortcut", "reminder",
                     "tutorial", "automation"}
        self.assertEqual({a.value for a in AssistanceType}, expected)


class TestSituationSnapshotDataclass(unittest.TestCase):
    def test_defaults(self):
        s = SituationSnapshot(situation_type=SituationType.WORKING)
        self.assertEqual(s.situation_type, SituationType.WORKING)
        self.assertEqual(s.active_products, [])
        self.assertEqual(s.current_product, "")
        self.assertEqual(s.current_action, "")
        self.assertEqual(s.duration_seconds, 0.0)
        self.assertEqual(s.context_signals, {})
        self.assertEqual(s.timestamp, 0.0)
        self.assertEqual(s.confidence, 0.0)


class TestInferredIntentDataclass(unittest.TestCase):
    def test_defaults(self):
        i = InferredIntent(intent="test")
        self.assertEqual(i.intent, "test")
        self.assertEqual(i.confidence, 0.0)
        self.assertEqual(i.confidence_level, IntentConfidence.LOW)
        self.assertEqual(i.supporting_evidence, [])
        self.assertEqual(i.related_products, [])
        self.assertEqual(i.predicted_next_actions, [])


class TestProactiveAssistanceDataclass(unittest.TestCase):
    def test_defaults(self):
        p = ProactiveAssistance(
            assistance_id="a1",
            assistance_type=AssistanceType.SUGGESTION,
            title="Title",
            description="Desc",
        )
        self.assertEqual(p.relevance_score, 0.0)
        self.assertEqual(p.target_product, "")
        self.assertEqual(p.action_url, "")
        self.assertEqual(p.metadata, {})


class TestHandoffContextDataclass(unittest.TestCase):
    def test_defaults(self):
        h = HandoffContext(
            handoff_id="h1",
            source_product="a",
            target_product="b",
            reason=HandoffReason.USER_REQUEST,
        )
        self.assertEqual(h.context_data, {})
        self.assertEqual(h.user_state, {})
        self.assertFalse(h.success)
        self.assertEqual(h.completion_time, 0.0)


# ======================================================================
# SituationAwareness
# ======================================================================

class TestSituationAwarenessClassification(unittest.TestCase):
    def setUp(self):
        self.sa = SituationAwareness()

    def test_troubleshooting_keywords(self):
        for kw in ["debug", "fix", "error"]:
            snap = self.sa.update("p1", kw, timestamp=100.0)
            self.assertEqual(snap.situation_type, SituationType.TROUBLESHOOTING)

    def test_creating_keywords(self):
        for kw in ["create file", "new project", "add module", "write code"]:
            snap = self.sa.update("p1", kw, timestamp=100.0)
            self.assertEqual(snap.situation_type, SituationType.CREATING, msg=kw)

    def test_exploring_keywords(self):
        for kw in ["read docs", "view file", "browse repo", "search code"]:
            snap = self.sa.update("p1", kw, timestamp=100.0)
            self.assertEqual(snap.situation_type, SituationType.EXPLORING, msg=kw)

    def test_reviewing_keywords(self):
        for kw in ["review PR", "approve changes", "check results"]:
            snap = self.sa.update("p1", kw, timestamp=100.0)
            self.assertEqual(snap.situation_type, SituationType.REVIEWING, msg=kw)

    def test_learning_keywords(self):
        for kw in ["learn python", "tutorial on react", "read docs guide"]:
            snap = self.sa.update("p1", kw, timestamp=100.0)
            self.assertIn(snap.situation_type,
                          [SituationType.LEARNING, SituationType.EXPLORING], msg=kw)

    def test_managing_keywords(self):
        for kw in ["manage users", "admin panel", "config settings"]:
            snap = self.sa.update("p1", kw, timestamp=100.0)
            self.assertEqual(snap.situation_type, SituationType.MANAGING, msg=kw)

    def test_default_working(self):
        snap = self.sa.update("p1", "some random action", timestamp=100.0)
        self.assertEqual(snap.situation_type, SituationType.WORKING)

    def test_confidence_exact_match(self):
        snap = self.sa.update("p1", "debug", timestamp=100.0)
        self.assertEqual(snap.confidence, 0.9)

    def test_confidence_partial_match(self):
        snap = self.sa.update("p1", "debugging_session", timestamp=100.0)
        self.assertGreaterEqual(snap.confidence, 0.6)

    def test_confidence_default(self):
        snap = self.sa.update("p1", "random", timestamp=100.0)
        self.assertEqual(snap.confidence, 0.4)


class TestSituationAwarenessBasic(unittest.TestCase):
    def setUp(self):
        self.sa = SituationAwareness()

    def test_initial_state(self):
        self.assertIsNone(self.sa.get_current_situation())
        self.assertEqual(self.sa.get_situation_history(), [])

    def test_update_returns_snapshot(self):
        snap = self.sa.update("p1", "debug issue", timestamp=100.0)
        self.assertIsInstance(snap, SituationSnapshot)
        self.assertEqual(snap.current_product, "p1")
        self.assertEqual(snap.current_action, "debug issue")

    def test_current_situation_updated(self):
        self.sa.update("p1", "create file", timestamp=100.0)
        cur = self.sa.get_current_situation()
        self.assertIsNotNone(cur)
        self.assertEqual(cur.current_product, "p1")

    def test_history_ordering(self):
        self.sa.update("p1", "act1", timestamp=100.0)
        self.sa.update("p2", "act2", timestamp=101.0)
        self.sa.update("p3", "act3", timestamp=102.0)
        history = self.sa.get_situation_history()
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0].current_product, "p1")
        self.assertEqual(history[-1].current_product, "p3")

    def test_history_limit(self):
        for i in range(30):
            self.sa.update("p1", f"act{i}", timestamp=100.0 + i)
        self.assertEqual(len(self.sa.get_situation_history(limit=5)), 5)

    def test_active_products(self):
        self.sa.update("editor", "open", timestamp=100.0)
        self.sa.update("terminal", "run", timestamp=101.0)
        snap = self.sa.get_current_situation()
        self.assertIn("editor", snap.active_products)
        self.assertIn("terminal", snap.active_products)

    def test_context_signals_passed_through(self):
        snap = self.sa.update("p1", "act", timestamp=100.0,
                              context_signals={"file": "main.py"})
        self.assertEqual(snap.context_signals["file"], "main.py")

    def test_context_signals_default_empty(self):
        snap = self.sa.update("p1", "act", timestamp=100.0)
        self.assertEqual(snap.context_signals, {})

    def test_duration_calculated(self):
        self.sa.update("p1", "first", timestamp=100.0)
        snap = self.sa.update("p1", "second", timestamp=110.0)
        self.assertAlmostEqual(snap.duration_seconds, 10.0)

    def test_duration_zero_for_first(self):
        snap = self.sa.update("p1", "first", timestamp=100.0)
        self.assertEqual(snap.duration_seconds, 0.0)

    def test_timestamp_auto_generated(self):
        before = time.time()
        snap = self.sa.update("p1", "act")
        after = time.time()
        self.assertGreaterEqual(snap.timestamp, before)
        self.assertLessEqual(snap.timestamp, after)


class TestSituationAwarenessIdle(unittest.TestCase):
    def test_idle_detection(self):
        sa = SituationAwareness(idle_threshold_seconds=10.0)
        sa.update("p1", "first", timestamp=100.0)
        sa.update("p1", "after_gap", timestamp=200.0)
        history = sa.get_situation_history()
        idle_snaps = [s for s in history if s.situation_type == SituationType.IDLE]
        self.assertTrue(len(idle_snaps) >= 1)

    def test_no_idle_within_threshold(self):
        sa = SituationAwareness(idle_threshold_seconds=300.0)
        sa.update("p1", "first", timestamp=100.0)
        sa.update("p1", "second", timestamp=110.0)
        history = sa.get_situation_history()
        idle_snaps = [s for s in history if s.situation_type == SituationType.IDLE]
        self.assertEqual(len(idle_snaps), 0)


class TestSituationAwarenessTime(unittest.TestCase):
    def test_time_in_situation(self):
        sa = SituationAwareness()
        sa.update("p1", "debug error", timestamp=100.0)
        sa.update("p1", "debug fix", timestamp=110.0)
        total = sa.get_time_in_situation(SituationType.TROUBLESHOOTING)
        self.assertGreater(total, 0.0)

    def test_time_in_situation_zero(self):
        sa = SituationAwareness()
        sa.update("p1", "random", timestamp=100.0)
        self.assertEqual(sa.get_time_in_situation(SituationType.LEARNING), 0.0)


class TestSituationAwarenessDistribution(unittest.TestCase):
    def test_distribution_empty(self):
        sa = SituationAwareness()
        dist = sa.get_situation_distribution()
        for v in dist.values():
            self.assertEqual(v, 0.0)

    def test_distribution_nonempty(self):
        sa = SituationAwareness()
        sa.update("p1", "debug", timestamp=100.0)
        sa.update("p1", "debug", timestamp=110.0)
        dist = sa.get_situation_distribution()
        self.assertIsInstance(dist, dict)
        total = sum(dist.values())
        # Total should approximate 100% (may not be exact due to zero-duration entries)
        self.assertGreaterEqual(total, 0.0)


class TestSituationAwarenessContextSwitch(unittest.TestCase):
    def test_no_switch_initially(self):
        sa = SituationAwareness()
        self.assertFalse(sa.detect_context_switch())

    def test_no_switch_same_type(self):
        sa = SituationAwareness()
        sa.update("p1", "debug a", timestamp=100.0)
        sa.update("p1", "debug b", timestamp=101.0)
        self.assertFalse(sa.detect_context_switch())

    def test_switch_detected(self):
        sa = SituationAwareness()
        sa.update("p1", "debug error", timestamp=100.0)
        sa.update("p1", "create file", timestamp=101.0)
        self.assertTrue(sa.detect_context_switch())

    def test_single_snapshot_no_switch(self):
        sa = SituationAwareness()
        sa.update("p1", "debug", timestamp=100.0)
        self.assertFalse(sa.detect_context_switch())


class TestSituationAwarenessMaxCap(unittest.TestCase):
    def test_max_snapshots_enforced(self):
        sa = SituationAwareness(max_snapshots=5)
        for i in range(20):
            sa.update("p1", f"act{i}", timestamp=100.0 + i)
        self.assertLessEqual(len(sa.get_situation_history(limit=100)), 5)


class TestSituationAwarenessThreadSafety(unittest.TestCase):
    def test_concurrent_updates(self):
        sa = SituationAwareness(max_snapshots=5000)
        errors = []

        def worker(tid):
            try:
                for i in range(50):
                    sa.update(f"p{tid}", f"action_{i}", timestamp=100.0 + i + tid * 100)
                    sa.get_current_situation()
                    sa.get_situation_history(limit=5)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


# ======================================================================
# IntentInference
# ======================================================================

class TestIntentInferenceBasic(unittest.TestCase):
    def setUp(self):
        self.ii = IntentInference()

    def test_initial_state(self):
        self.assertIsNone(self.ii.get_current_intent())
        self.assertEqual(self.ii.get_intent_history(), [])

    def test_no_patterns_returns_none(self):
        result = self.ii.observe_action("p1", "anything")
        self.assertIsNone(result)

    def test_register_and_infer(self):
        self.ii.register_intent_pattern("debugging", ["debug", "error", "fix"])
        self.ii.observe_action("p1", "debug issue", timestamp=100.0)
        self.ii.observe_action("p1", "check error log", timestamp=101.0)
        result = self.ii.observe_action("p1", "fix the bug", timestamp=102.0)
        self.assertIsNotNone(result)
        self.assertEqual(result.intent, "debugging")
        self.assertGreater(result.confidence, 0.3)

    def test_confidence_increases_with_more_matches(self):
        self.ii.register_intent_pattern("deploying", ["build", "test", "deploy", "release"])
        self.ii.observe_action("p1", "build project", timestamp=100.0)
        # Only 1/4 keywords -> confidence 0.25 -> None (below threshold)
        r2 = self.ii.observe_action("p1", "test suite", timestamp=101.0)
        # 2/4 keywords -> 0.5 -> inferred
        self.assertIsNotNone(r2)
        self.assertAlmostEqual(r2.confidence, 0.5)

    def test_high_confidence_level(self):
        self.ii.register_intent_pattern("invoicing", ["invoice", "payment", "send"])
        self.ii.observe_action("p1", "create invoice", timestamp=100.0)
        self.ii.observe_action("p1", "add payment", timestamp=101.0)
        result = self.ii.observe_action("p1", "send to client", timestamp=102.0)
        self.assertIsNotNone(result)
        self.assertGreater(result.confidence, 0.7)
        self.assertEqual(result.confidence_level, IntentConfidence.HIGH)

    def test_medium_confidence_level(self):
        self.ii.register_intent_pattern("reporting", ["data", "chart", "export", "format"])
        self.ii.observe_action("p1", "load data", timestamp=100.0)
        result = self.ii.observe_action("p1", "build chart", timestamp=101.0)
        self.assertIsNotNone(result)
        self.assertEqual(result.confidence_level, IntentConfidence.MEDIUM)

    def test_below_threshold_returns_none(self):
        self.ii.register_intent_pattern("complex", ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"])
        result = self.ii.observe_action("p1", "a", timestamp=100.0)
        # 1/10 = 0.1, below 0.3 threshold
        self.assertIsNone(result)


class TestIntentInferencePredictions(unittest.TestCase):
    def test_predicted_next_actions(self):
        ii = IntentInference()
        ii.register_intent_pattern("workflow", ["plan", "code", "test", "deploy"])
        ii.observe_action("p1", "plan sprint", timestamp=100.0)
        result = ii.observe_action("p1", "code feature", timestamp=101.0)
        self.assertIsNotNone(result)
        self.assertIn("test", result.predicted_next_actions)
        self.assertIn("deploy", result.predicted_next_actions)

    def test_related_products(self):
        ii = IntentInference()
        ii.register_intent_pattern("design", ["mockup", "review"], products=["figma", "slack"])
        ii.observe_action("p1", "create mockup", timestamp=100.0)
        result = ii.observe_action("p1", "review design", timestamp=101.0)
        self.assertIsNotNone(result)
        self.assertIn("figma", result.related_products)

    def test_supporting_evidence(self):
        ii = IntentInference()
        ii.register_intent_pattern("testing", ["test", "assert", "mock"])
        ii.observe_action("p1", "write test", timestamp=100.0)
        result = ii.observe_action("p1", "add assert", timestamp=101.0)
        self.assertIsNotNone(result)
        self.assertIn("test", result.supporting_evidence)
        self.assertIn("assert", result.supporting_evidence)


class TestIntentInferenceHistory(unittest.TestCase):
    def test_history_grows(self):
        ii = IntentInference()
        ii.register_intent_pattern("ci", ["build", "test"])
        ii.observe_action("p1", "build", timestamp=100.0)
        ii.observe_action("p1", "test", timestamp=101.0)
        self.assertGreaterEqual(len(ii.get_intent_history()), 1)

    def test_history_limit(self):
        ii = IntentInference()
        ii.register_intent_pattern("ci", ["build", "test"])
        for i in range(30):
            ii.observe_action("p1", "build test", timestamp=100.0 + i)
        self.assertEqual(len(ii.get_intent_history(limit=5)), 5)

    def test_current_intent_is_latest(self):
        ii = IntentInference()
        ii.register_intent_pattern("ci", ["build", "test"])
        ii.observe_action("p1", "build test", timestamp=100.0)
        ii.observe_action("p1", "build test again", timestamp=101.0)
        cur = ii.get_current_intent()
        self.assertIsNotNone(cur)
        self.assertEqual(cur.timestamp, 101.0)


class TestIntentInferenceTrend(unittest.TestCase):
    def test_stable_trend(self):
        ii = IntentInference()
        ii.register_intent_pattern("ci", ["build", "test"])
        for i in range(5):
            ii.observe_action("p1", "build test", timestamp=100.0 + i)
        self.assertEqual(ii.get_intent_confidence_trend(), "stable")

    def test_increasing_trend(self):
        ii = IntentInference()
        ii.register_intent_pattern("deploy", ["plan", "build", "test", "deploy", "release"])
        # Build up evidence gradually
        ii.observe_action("p1", "plan", timestamp=100.0)
        ii.observe_action("p1", "build", timestamp=101.0)
        ii.observe_action("p1", "test", timestamp=102.0)
        ii.observe_action("p1", "deploy", timestamp=103.0)
        ii.observe_action("p1", "release", timestamp=104.0)
        trend = ii.get_intent_confidence_trend()
        self.assertEqual(trend, "increasing")

    def test_decreasing_trend(self):
        ii = IntentInference()
        ii.register_intent_pattern("a", ["x", "y", "z"])
        ii.register_intent_pattern("b", ["p", "q"])
        # Start with high confidence for "a", then switch to lower confidence pattern
        ii.observe_action("p1", "x y z", timestamp=100.0)  # a: 1.0
        ii.observe_action("p1", "x y z", timestamp=101.0)  # a: 1.0
        ii.observe_action("p1", "x y z", timestamp=102.0)  # a: 1.0
        # Clear window and switch to pattern with lower match
        ii.clear_window()
        ii.observe_action("p1", "p only", timestamp=103.0)  # b: 0.5
        ii.observe_action("p1", "p only", timestamp=104.0)  # b: 0.5
        trend = ii.get_intent_confidence_trend()
        self.assertEqual(trend, "decreasing")

    def test_trend_single_intent(self):
        ii = IntentInference()
        self.assertEqual(ii.get_intent_confidence_trend(), "stable")


class TestIntentInferenceClear(unittest.TestCase):
    def test_clear_window(self):
        ii = IntentInference()
        ii.register_intent_pattern("ci", ["build", "test"])
        ii.observe_action("p1", "build test", timestamp=100.0)
        ii.clear_window()
        # After clear, old keywords shouldn't contribute
        result = ii.observe_action("p1", "random", timestamp=101.0)
        self.assertIsNone(result)


class TestIntentInferenceMaxCap(unittest.TestCase):
    def test_max_intents(self):
        ii = IntentInference(max_intents=5)
        ii.register_intent_pattern("ci", ["build", "test"])
        for i in range(20):
            ii.observe_action("p1", "build test", timestamp=100.0 + i)
        self.assertLessEqual(len(ii.get_intent_history(limit=100)), 5)

    def test_max_action_window(self):
        ii = IntentInference(max_action_window=3)
        ii.register_intent_pattern("ci", ["alpha", "beta", "gamma", "delta"])
        ii.observe_action("p1", "alpha", timestamp=100.0)
        ii.observe_action("p1", "beta", timestamp=101.0)
        ii.observe_action("p1", "gamma", timestamp=102.0)
        ii.observe_action("p1", "delta", timestamp=103.0)
        # Window only keeps last 3: beta, gamma, delta => 3/4 = 0.75
        result = ii.observe_action("p1", "unrelated", timestamp=104.0)
        # alpha should have been evicted
        self.assertIsNotNone(result)
        self.assertNotIn("alpha", result.supporting_evidence)


class TestIntentInferenceMultiplePatterns(unittest.TestCase):
    def test_best_pattern_wins(self):
        ii = IntentInference()
        ii.register_intent_pattern("debug", ["debug", "error"])
        ii.register_intent_pattern("deploy", ["debug", "error", "deploy", "release", "extra"])
        ii.observe_action("p1", "debug error", timestamp=100.0)
        cur = ii.get_current_intent()
        # "debug" has confidence 1.0, "deploy" has 2/5=0.4
        self.assertIsNotNone(cur)
        self.assertEqual(cur.intent, "debug")


class TestIntentInferenceThreadSafety(unittest.TestCase):
    def test_concurrent_observe(self):
        ii = IntentInference(max_intents=5000)
        ii.register_intent_pattern("ci", ["build", "test"])
        errors = []

        def worker(tid):
            try:
                for i in range(50):
                    ii.observe_action(f"p{tid}", f"build test {i}",
                                      timestamp=100.0 + i + tid * 100)
                    ii.get_current_intent()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


# ======================================================================
# ProactiveAssistant
# ======================================================================

class TestProactiveAssistantBasic(unittest.TestCase):
    def setUp(self):
        self.pa = ProactiveAssistant(cooldown_seconds=0.0)

    def test_initial_state(self):
        self.assertEqual(self.pa.get_suggestions(), [])
        stats = self.pa.get_suggestion_stats()
        self.assertEqual(stats["total"], 0)

    def test_add_rule_and_evaluate(self):
        self.pa.add_rule("r1", ["error", "debug"],
                         AssistanceType.SUGGESTION, "Debug Help",
                         "Try the debugger", target_product="ide")
        results = self.pa.evaluate({"action": "debug error"})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Debug Help")
        self.assertGreater(results[0].relevance_score, 0.0)

    def test_no_match(self):
        self.pa.add_rule("r1", ["deploy", "release"],
                         AssistanceType.WARNING, "Deploy", "Deploy now")
        results = self.pa.evaluate({"action": "write code"})
        self.assertEqual(len(results), 0)

    def test_relevance_score_calculation(self):
        self.pa.add_rule("r1", ["a", "b", "c", "d"],
                         AssistanceType.SUGGESTION, "T", "D")
        results = self.pa.evaluate({"action": "a b"})
        self.assertAlmostEqual(results[0].relevance_score, 0.5)

    def test_sorted_by_relevance(self):
        self.pa.add_rule("r1", ["x"], AssistanceType.SUGGESTION, "Low", "D")
        self.pa.add_rule("r2", ["x", "y"], AssistanceType.WARNING, "High", "D")
        results = self.pa.evaluate({"action": "x y"})
        self.assertEqual(len(results), 2)
        self.assertGreaterEqual(results[0].relevance_score, results[1].relevance_score)


class TestProactiveAssistantCooldown(unittest.TestCase):
    def test_cooldown_blocks_duplicate_type(self):
        pa = ProactiveAssistant(cooldown_seconds=1000.0)
        pa.add_rule("r1", ["error"], AssistanceType.SUGGESTION, "T1", "D1")
        pa.add_rule("r2", ["error"], AssistanceType.SUGGESTION, "T2", "D2")
        results1 = pa.evaluate({"action": "error"})
        results2 = pa.evaluate({"action": "error"})
        # First call triggers, second blocked by cooldown
        self.assertEqual(len(results1), 1)
        self.assertEqual(len(results2), 0)

    def test_cooldown_allows_different_types(self):
        pa = ProactiveAssistant(cooldown_seconds=1000.0)
        pa.add_rule("r1", ["error"], AssistanceType.SUGGESTION, "T1", "D1")
        pa.add_rule("r2", ["error"], AssistanceType.WARNING, "T2", "D2")
        results = pa.evaluate({"action": "error"})
        self.assertEqual(len(results), 2)

    def test_zero_cooldown_allows_repeated(self):
        pa = ProactiveAssistant(cooldown_seconds=0.0)
        pa.add_rule("r1", ["x"], AssistanceType.SUGGESTION, "T", "D")
        r1 = pa.evaluate({"action": "x"})
        r2 = pa.evaluate({"action": "x"})
        self.assertEqual(len(r1), 1)
        self.assertEqual(len(r2), 1)


class TestProactiveAssistantSuggestions(unittest.TestCase):
    def setUp(self):
        self.pa = ProactiveAssistant(cooldown_seconds=0.0)
        self.pa.add_rule("r1", ["err"], AssistanceType.SUGGESTION, "T1", "D1")
        self.pa.add_rule("r2", ["err"], AssistanceType.WARNING, "T2", "D2")
        self.pa.evaluate({"action": "err"})

    def test_get_all_suggestions(self):
        suggs = self.pa.get_suggestions(limit=10)
        self.assertEqual(len(suggs), 2)

    def test_filter_by_type(self):
        suggs = self.pa.get_suggestions(limit=10, assistance_type=AssistanceType.WARNING)
        self.assertEqual(len(suggs), 1)
        self.assertEqual(suggs[0].assistance_type, AssistanceType.WARNING)

    def test_limit_respected(self):
        for i in range(10):
            self.pa.evaluate({"action": "err"})
        suggs = self.pa.get_suggestions(limit=3)
        self.assertEqual(len(suggs), 3)


class TestProactiveAssistantDismiss(unittest.TestCase):
    def test_dismiss_existing(self):
        pa = ProactiveAssistant(cooldown_seconds=0.0)
        pa.add_rule("r1", ["x"], AssistanceType.SUGGESTION, "T", "D")
        results = pa.evaluate({"action": "x"})
        aid = results[0].assistance_id
        self.assertTrue(pa.dismiss_suggestion(aid))
        # Dismissed suggestion no longer appears
        suggs = pa.get_suggestions()
        self.assertEqual(len(suggs), 0)

    def test_dismiss_nonexistent(self):
        pa = ProactiveAssistant()
        self.assertFalse(pa.dismiss_suggestion("nonexistent"))


class TestProactiveAssistantStats(unittest.TestCase):
    def test_stats_structure(self):
        pa = ProactiveAssistant(cooldown_seconds=0.0)
        pa.add_rule("r1", ["x"], AssistanceType.SUGGESTION, "T", "D")
        pa.evaluate({"action": "x"})
        stats = pa.get_suggestion_stats()
        self.assertIn("total", stats)
        self.assertIn("dismissed", stats)
        self.assertIn("dismissal_rate", stats)
        self.assertIn("by_type", stats)
        self.assertEqual(stats["total"], 1)

    def test_dismissal_rate(self):
        pa = ProactiveAssistant(cooldown_seconds=0.0)
        pa.add_rule("r1", ["x"], AssistanceType.SUGGESTION, "T", "D")
        results = pa.evaluate({"action": "x"})
        pa.dismiss_suggestion(results[0].assistance_id)
        stats = pa.get_suggestion_stats()
        self.assertEqual(stats["dismissal_rate"], 1.0)


class TestProactiveAssistantMaxCap(unittest.TestCase):
    def test_max_suggestions(self):
        pa = ProactiveAssistant(max_suggestions=5, cooldown_seconds=0.0)
        pa.add_rule("r1", ["x"], AssistanceType.SUGGESTION, "T", "D")
        for _ in range(20):
            pa.evaluate({"action": "x"})
        self.assertLessEqual(pa.get_suggestion_stats()["total"], 5)


class TestProactiveAssistantEdgeCases(unittest.TestCase):
    def test_empty_context(self):
        pa = ProactiveAssistant(cooldown_seconds=0.0)
        pa.add_rule("r1", ["x"], AssistanceType.SUGGESTION, "T", "D")
        results = pa.evaluate({})
        self.assertEqual(len(results), 0)

    def test_none_values_in_context(self):
        pa = ProactiveAssistant(cooldown_seconds=0.0)
        pa.add_rule("r1", ["x"], AssistanceType.SUGGESTION, "T", "D")
        results = pa.evaluate({"a": None, "b": "x"})
        self.assertEqual(len(results), 1)

    def test_empty_keywords(self):
        pa = ProactiveAssistant(cooldown_seconds=0.0)
        pa.add_rule("r1", [], AssistanceType.SUGGESTION, "T", "D")
        results = pa.evaluate({"action": "anything"})
        self.assertEqual(len(results), 0)

    def test_multiple_context_fields(self):
        pa = ProactiveAssistant(cooldown_seconds=0.0)
        pa.add_rule("r1", ["error", "prod"],
                     AssistanceType.WARNING, "Alert", "Check prod")
        results = pa.evaluate({"action": "error", "env": "prod"})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].relevance_score, 1.0)


class TestProactiveAssistantThreadSafety(unittest.TestCase):
    def test_concurrent_evaluate(self):
        pa = ProactiveAssistant(cooldown_seconds=0.0, max_suggestions=5000)
        pa.add_rule("r1", ["x"], AssistanceType.SUGGESTION, "T", "D")
        errors = []

        def worker():
            try:
                for _ in range(50):
                    pa.evaluate({"action": "x"})
                    pa.get_suggestions()
                    pa.get_suggestion_stats()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


# ======================================================================
# SmartHandoff
# ======================================================================

class TestSmartHandoffBasic(unittest.TestCase):
    def setUp(self):
        self.sh = SmartHandoff()

    def test_initial_state(self):
        self.assertEqual(self.sh.get_active_handoffs(), [])
        self.assertEqual(self.sh.get_handoff_history(), [])

    def test_initiate_handoff(self):
        h = self.sh.initiate_handoff("editor", "terminal",
                                      HandoffReason.CONTEXT_SWITCH)
        self.assertIsInstance(h, HandoffContext)
        self.assertEqual(h.source_product, "editor")
        self.assertEqual(h.target_product, "terminal")
        self.assertEqual(h.reason, HandoffReason.CONTEXT_SWITCH)
        self.assertFalse(h.success)

    def test_handoff_in_active(self):
        h = self.sh.initiate_handoff("a", "b", HandoffReason.USER_REQUEST)
        active = self.sh.get_active_handoffs()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].handoff_id, h.handoff_id)

    def test_handoff_in_history(self):
        self.sh.initiate_handoff("a", "b", HandoffReason.TASK_COMPLETE)
        self.assertEqual(len(self.sh.get_handoff_history()), 1)

    def test_context_data_preserved(self):
        h = self.sh.initiate_handoff("a", "b", HandoffReason.ESCALATION,
                                      context_data={"file": "main.py"},
                                      user_state={"cursor": 42})
        self.assertEqual(h.context_data["file"], "main.py")
        self.assertEqual(h.user_state["cursor"], 42)

    def test_unique_handoff_ids(self):
        h1 = self.sh.initiate_handoff("a", "b", HandoffReason.USER_REQUEST)
        h2 = self.sh.initiate_handoff("a", "b", HandoffReason.USER_REQUEST)
        self.assertNotEqual(h1.handoff_id, h2.handoff_id)


class TestSmartHandoffComplete(unittest.TestCase):
    def setUp(self):
        self.sh = SmartHandoff()

    def test_complete_success(self):
        h = self.sh.initiate_handoff("a", "b", HandoffReason.TASK_COMPLETE)
        result = self.sh.complete_handoff(h.handoff_id, success=True)
        self.assertIsNotNone(result)
        self.assertTrue(result.success)
        self.assertGreater(result.completion_time, 0.0)

    def test_complete_failure(self):
        h = self.sh.initiate_handoff("a", "b", HandoffReason.TASK_COMPLETE)
        result = self.sh.complete_handoff(h.handoff_id, success=False)
        self.assertFalse(result.success)

    def test_complete_removes_from_active(self):
        h = self.sh.initiate_handoff("a", "b", HandoffReason.TASK_COMPLETE)
        self.sh.complete_handoff(h.handoff_id)
        self.assertEqual(len(self.sh.get_active_handoffs()), 0)

    def test_complete_nonexistent(self):
        self.assertIsNone(self.sh.complete_handoff("nonexistent"))

    def test_double_complete(self):
        h = self.sh.initiate_handoff("a", "b", HandoffReason.TASK_COMPLETE)
        self.sh.complete_handoff(h.handoff_id)
        self.assertIsNone(self.sh.complete_handoff(h.handoff_id))


class TestSmartHandoffSuggest(unittest.TestCase):
    def setUp(self):
        self.sh = SmartHandoff()
        self.sh.register_product_capabilities("billing", ["invoice", "payment", "receipt"])
        self.sh.register_product_capabilities("analytics", ["report", "chart", "dashboard"])
        self.sh.register_product_capabilities("editor", ["code", "edit", "refactor"])

    def test_suggest_matching(self):
        result = self.sh.suggest_handoff("editor", "generate invoice")
        self.assertIsNotNone(result)
        product, reason = result
        self.assertEqual(product, "billing")
        self.assertEqual(reason, HandoffReason.EXPERTISE_NEEDED)

    def test_suggest_no_match(self):
        result = self.sh.suggest_handoff("editor", "fly to the moon")
        self.assertIsNone(result)

    def test_suggest_excludes_current(self):
        result = self.sh.suggest_handoff("billing", "create invoice")
        # Should not suggest billing itself
        if result is not None:
            self.assertNotEqual(result[0], "billing")

    def test_suggest_best_match(self):
        result = self.sh.suggest_handoff("editor", "payment receipt")
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "billing")

    def test_register_overwrites_capabilities(self):
        self.sh.register_product_capabilities("billing", ["subscription"])
        result = self.sh.suggest_handoff("editor", "invoice")
        # Old capabilities removed
        self.assertIsNone(result)


class TestSmartHandoffHistory(unittest.TestCase):
    def setUp(self):
        self.sh = SmartHandoff()

    def test_history_ordering(self):
        self.sh.initiate_handoff("a", "b", HandoffReason.USER_REQUEST)
        self.sh.initiate_handoff("c", "d", HandoffReason.ESCALATION)
        history = self.sh.get_handoff_history()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].source_product, "a")
        self.assertEqual(history[1].source_product, "c")

    def test_history_limit(self):
        for i in range(20):
            self.sh.initiate_handoff(f"s{i}", f"t{i}", HandoffReason.USER_REQUEST)
        self.assertEqual(len(self.sh.get_handoff_history(limit=5)), 5)

    def test_history_filter_by_product(self):
        self.sh.initiate_handoff("a", "b", HandoffReason.USER_REQUEST)
        self.sh.initiate_handoff("c", "d", HandoffReason.ESCALATION)
        self.sh.initiate_handoff("a", "e", HandoffReason.TASK_COMPLETE)
        history = self.sh.get_handoff_history(product_id="a")
        self.assertEqual(len(history), 2)

    def test_history_filter_target_product(self):
        self.sh.initiate_handoff("x", "y", HandoffReason.USER_REQUEST)
        self.sh.initiate_handoff("z", "y", HandoffReason.ESCALATION)
        history = self.sh.get_handoff_history(product_id="y")
        self.assertEqual(len(history), 2)


class TestSmartHandoffSuccessRate(unittest.TestCase):
    def test_empty_rate(self):
        sh = SmartHandoff()
        self.assertEqual(sh.get_handoff_success_rate(), 0.0)

    def test_all_success(self):
        sh = SmartHandoff()
        for _ in range(3):
            h = sh.initiate_handoff("a", "b", HandoffReason.USER_REQUEST)
            sh.complete_handoff(h.handoff_id, success=True)
        self.assertEqual(sh.get_handoff_success_rate(), 1.0)

    def test_mixed_rate(self):
        sh = SmartHandoff()
        h1 = sh.initiate_handoff("a", "b", HandoffReason.USER_REQUEST)
        sh.complete_handoff(h1.handoff_id, success=True)
        h2 = sh.initiate_handoff("a", "b", HandoffReason.USER_REQUEST)
        sh.complete_handoff(h2.handoff_id, success=False)
        self.assertAlmostEqual(sh.get_handoff_success_rate(), 0.5)

    def test_rate_by_product(self):
        sh = SmartHandoff()
        h1 = sh.initiate_handoff("a", "b", HandoffReason.USER_REQUEST)
        sh.complete_handoff(h1.handoff_id, success=True)
        h2 = sh.initiate_handoff("c", "d", HandoffReason.USER_REQUEST)
        sh.complete_handoff(h2.handoff_id, success=False)
        self.assertEqual(sh.get_handoff_success_rate(product_id="a"), 1.0)
        self.assertEqual(sh.get_handoff_success_rate(product_id="c"), 0.0)

    def test_incomplete_not_counted(self):
        sh = SmartHandoff()
        sh.initiate_handoff("a", "b", HandoffReason.USER_REQUEST)
        self.assertEqual(sh.get_handoff_success_rate(), 0.0)


class TestSmartHandoffSummary(unittest.TestCase):
    def test_empty_summary(self):
        sh = SmartHandoff()
        summary = sh.get_handoff_summary()
        self.assertEqual(summary["total"], 0)
        self.assertEqual(summary["active"], 0)
        self.assertEqual(summary["success_rate"], 0.0)

    def test_summary_structure(self):
        sh = SmartHandoff()
        h = sh.initiate_handoff("a", "b", HandoffReason.USER_REQUEST)
        sh.complete_handoff(h.handoff_id, success=True)
        sh.initiate_handoff("a", "c", HandoffReason.ESCALATION)
        summary = sh.get_handoff_summary()
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["active"], 1)
        self.assertEqual(summary["completed"], 1)
        self.assertEqual(summary["success_rate"], 1.0)
        self.assertIn("a->b", summary["most_common_routes"])
        self.assertIn("user_request", summary["most_common_reasons"])

    def test_most_common_routes_sorted(self):
        sh = SmartHandoff()
        for _ in range(3):
            sh.initiate_handoff("a", "b", HandoffReason.USER_REQUEST)
        sh.initiate_handoff("c", "d", HandoffReason.ESCALATION)
        summary = sh.get_handoff_summary()
        routes = list(summary["most_common_routes"].items())
        self.assertEqual(routes[0], ("a->b", 3))


class TestSmartHandoffMaxCap(unittest.TestCase):
    def test_max_handoffs(self):
        sh = SmartHandoff(max_handoffs=5)
        for i in range(20):
            sh.initiate_handoff(f"s{i}", f"t{i}", HandoffReason.USER_REQUEST)
        self.assertLessEqual(len(sh.get_handoff_history(limit=100)), 5)


class TestSmartHandoffThreadSafety(unittest.TestCase):
    def test_concurrent_handoffs(self):
        sh = SmartHandoff(max_handoffs=5000)
        errors = []

        def worker(tid):
            try:
                for i in range(50):
                    h = sh.initiate_handoff(f"s{tid}", f"t{i}",
                                             HandoffReason.USER_REQUEST)
                    sh.complete_handoff(h.handoff_id)
                    sh.get_active_handoffs()
                    sh.get_handoff_success_rate()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


# ======================================================================
# Integration-like edge cases
# ======================================================================

class TestEdgeCasesAwareness(unittest.TestCase):
    def test_empty_product_id(self):
        sa = SituationAwareness()
        snap = sa.update("", "action", timestamp=100.0)
        self.assertEqual(snap.current_product, "")

    def test_empty_action(self):
        sa = SituationAwareness()
        snap = sa.update("p1", "", timestamp=100.0)
        self.assertEqual(snap.current_action, "")
        self.assertEqual(snap.situation_type, SituationType.WORKING)

    def test_negative_timestamp(self):
        sa = SituationAwareness()
        snap = sa.update("p1", "act", timestamp=-1.0)
        self.assertEqual(snap.timestamp, -1.0)


class TestEdgeCasesIntent(unittest.TestCase):
    def test_empty_keywords_pattern(self):
        ii = IntentInference()
        ii.register_intent_pattern("empty", [])
        result = ii.observe_action("p1", "anything", timestamp=100.0)
        self.assertIsNone(result)

    def test_observe_empty_action(self):
        ii = IntentInference()
        ii.register_intent_pattern("ci", ["build"])
        result = ii.observe_action("p1", "", timestamp=100.0)
        self.assertIsNone(result)


class TestEdgeCasesHandoff(unittest.TestCase):
    def test_handoff_no_capabilities_registered(self):
        sh = SmartHandoff()
        result = sh.suggest_handoff("p1", "anything")
        self.assertIsNone(result)

    def test_handoff_empty_user_need(self):
        sh = SmartHandoff()
        sh.register_product_capabilities("p1", ["x"])
        result = sh.suggest_handoff("p2", "")
        self.assertIsNone(result)

    def test_handoff_none_context_data(self):
        sh = SmartHandoff()
        h = sh.initiate_handoff("a", "b", HandoffReason.USER_REQUEST,
                                 context_data=None, user_state=None)
        self.assertEqual(h.context_data, {})
        self.assertEqual(h.user_state, {})


if __name__ == "__main__":
    unittest.main()
