"""Tests for MEMORIA Cognitive Load Management module."""

from __future__ import annotations

import json
import math
import time
import unittest

from memoria.cognitive import (
    CognitiveSnapshot,
    ComplexityAdapter,
    ComplexityAssessment,
    ComplexityLevel,
    FocusOptimizer,
    FocusSession,
    FocusState,
    LoadLevel,
    LoadTracker,
    OverloadAlert,
    OverloadPrevention,
    OverloadSignal,
)

EPS = 1e-6


# ======================================================================
# TestLoadTracker
# ======================================================================
class TestLoadTracker(unittest.TestCase):
    """Tests for LoadTracker."""

    def setUp(self):
        self.tracker = LoadTracker()

    # -- interaction recording -----------------------------------------

    def test_record_single_interaction(self):
        self.tracker.record_interaction("python")
        snap = self.tracker.get_current_load()
        self.assertEqual(snap.active_topics, 1)

    def test_record_multiple_topics(self):
        for t in ["python", "rust", "go"]:
            self.tracker.record_interaction(t)
        snap = self.tracker.get_current_load()
        self.assertEqual(snap.active_topics, 3)

    def test_record_clamped_complexity(self):
        self.tracker.record_interaction("x", complexity=2.0)
        self.tracker.record_interaction("y", complexity=-1.0)
        snap = self.tracker.get_current_load()
        self.assertGreaterEqual(snap.load_score, 0.0)

    def test_record_info_volume(self):
        self.tracker.record_interaction("a", info_volume=50)
        snap = self.tracker.get_current_load()
        self.assertGreater(snap.load_score, 0.0)

    def test_record_negative_volume_clamped(self):
        self.tracker.record_interaction("a", info_volume=-5)
        snap = self.tracker.get_current_load()
        self.assertGreaterEqual(snap.load_score, 0.0)

    # -- load computation ----------------------------------------------

    def test_empty_tracker_minimal_load(self):
        snap = self.tracker.get_current_load()
        self.assertEqual(snap.load_level, LoadLevel.MINIMAL)
        self.assertTrue(abs(snap.load_score - 0.0) < EPS)

    def test_load_score_range(self):
        for i in range(50):
            self.tracker.record_interaction(f"topic_{i}", complexity=0.9, info_volume=10)
        snap = self.tracker.get_current_load()
        self.assertGreaterEqual(snap.load_score, 0.0)
        self.assertLessEqual(snap.load_score, 1.0)

    def test_high_topic_diversity_increases_load(self):
        for i in range(15):
            self.tracker.record_interaction(f"topic_{i}")
        snap = self.tracker.get_current_load()
        self.assertGreater(snap.load_score, 0.1)

    def test_high_complexity_increases_load(self):
        for _ in range(10):
            self.tracker.record_interaction("deep", complexity=1.0, info_volume=5)
        snap = self.tracker.get_current_load()
        self.assertGreater(snap.load_score, 0.2)

    def test_high_volume_increases_load(self):
        self.tracker.record_interaction("docs", info_volume=200)
        snap = self.tracker.get_current_load()
        self.assertGreater(snap.load_score, 0.0)

    # -- all load levels -----------------------------------------------

    def test_load_level_minimal(self):
        snap = self.tracker.get_current_load()
        self.assertEqual(snap.load_level, LoadLevel.MINIMAL)

    def test_load_level_low(self):
        for i in range(3):
            self.tracker.record_interaction(f"t{i}", complexity=0.3)
        snap = self.tracker.get_current_load()
        self.assertIn(snap.load_level, [LoadLevel.MINIMAL, LoadLevel.LOW, LoadLevel.MODERATE])

    def test_load_level_overloaded(self):
        for i in range(200):
            self.tracker.record_interaction(f"topic_{i % 50}", complexity=1.0, info_volume=50)
        snap = self.tracker.get_current_load()
        self.assertIn(snap.load_level, [LoadLevel.HIGH, LoadLevel.OVERLOADED])
        self.assertGreater(snap.load_score, 0.6)

    def test_score_to_level_boundaries(self):
        self.assertEqual(LoadTracker._score_to_level(0.0), LoadLevel.MINIMAL)
        self.assertEqual(LoadTracker._score_to_level(0.19), LoadLevel.MINIMAL)
        self.assertEqual(LoadTracker._score_to_level(0.2), LoadLevel.LOW)
        self.assertEqual(LoadTracker._score_to_level(0.39), LoadLevel.LOW)
        self.assertEqual(LoadTracker._score_to_level(0.4), LoadLevel.MODERATE)
        self.assertEqual(LoadTracker._score_to_level(0.59), LoadLevel.MODERATE)
        self.assertEqual(LoadTracker._score_to_level(0.6), LoadLevel.HIGH)
        self.assertEqual(LoadTracker._score_to_level(0.79), LoadLevel.HIGH)
        self.assertEqual(LoadTracker._score_to_level(0.8), LoadLevel.OVERLOADED)
        self.assertEqual(LoadTracker._score_to_level(1.0), LoadLevel.OVERLOADED)

    # -- context switches and focus ------------------------------------

    def test_context_switches_counted(self):
        self.tracker.record_interaction("a")
        self.tracker.record_interaction("b")
        self.tracker.record_interaction("a")
        snap = self.tracker.get_current_load()
        self.assertEqual(snap.context_switches, 2)

    def test_no_context_switch_same_topic(self):
        self.tracker.record_interaction("a")
        self.tracker.record_interaction("a")
        snap = self.tracker.get_current_load()
        self.assertEqual(snap.context_switches, 0)

    def test_focus_state_present(self):
        snap = self.tracker.get_current_load()
        self.assertIsInstance(snap.focus_state, FocusState)

    # -- trend generation ----------------------------------------------

    def test_trend_returns_snapshots(self):
        self.tracker.record_interaction("x")
        trend = self.tracker.get_load_trend(window_minutes=30)
        self.assertGreater(len(trend), 0)
        self.assertIsInstance(trend[0], CognitiveSnapshot)

    def test_trend_interval_count(self):
        trend = self.tracker.get_load_trend(window_minutes=60)
        self.assertEqual(len(trend), 13)  # 60/5 + 1

    def test_trend_minimum_window(self):
        trend = self.tracker.get_load_trend(window_minutes=1)
        self.assertGreater(len(trend), 0)

    # -- sliding window ------------------------------------------------

    def test_old_interactions_excluded(self):
        tracker = LoadTracker(window_minutes=1)
        from memoria.cognitive.tracker import _Interaction
        old = _Interaction(topic="old", complexity=1.0, info_volume=100,
                           timestamp=time.time() - 3600)
        tracker._interactions.append(old)
        snap = tracker.get_current_load()
        self.assertEqual(snap.active_topics, 0)

    def test_window_only_recent(self):
        tracker = LoadTracker(window_minutes=5)
        from memoria.cognitive.tracker import _Interaction
        now = time.time()
        tracker._interactions.append(
            _Interaction("old", 1.0, 50, now - 600)
        )
        tracker._interactions.append(
            _Interaction("new", 0.1, 1, now)
        )
        snap = tracker.get_current_load()
        self.assertEqual(snap.active_topics, 1)

    # -- FIFO rotation -------------------------------------------------

    def test_fifo_rotation(self):
        for i in range(5100):
            self.tracker.record_interaction(f"t{i}")
        with self.tracker._lock:
            self.assertLessEqual(len(self.tracker._interactions), 5000)

    # -- serialisation -------------------------------------------------

    def test_to_dict_json_serialisable(self):
        self.tracker.record_interaction("a", complexity=0.7, info_volume=3)
        d = self.tracker.to_dict()
        s = json.dumps(d)
        self.assertIsInstance(s, str)

    def test_round_trip(self):
        self.tracker.record_interaction("x", complexity=0.5)
        d = self.tracker.to_dict()
        restored = LoadTracker.from_dict(d)
        snap_orig = self.tracker.get_current_load()
        snap_rest = restored.get_current_load()
        self.assertEqual(snap_orig.active_topics, snap_rest.active_topics)

    def test_from_dict_empty(self):
        t = LoadTracker.from_dict({})
        snap = t.get_current_load()
        self.assertEqual(snap.load_level, LoadLevel.MINIMAL)

    # -- edge cases ----------------------------------------------------

    def test_session_duration_positive(self):
        snap = self.tracker.get_current_load()
        self.assertGreaterEqual(snap.session_duration_minutes, 0.0)

    def test_reset_clears_state(self):
        self.tracker.record_interaction("a")
        self.tracker.reset()
        snap = self.tracker.get_current_load()
        self.assertEqual(snap.active_topics, 0)

    def test_custom_window_minutes(self):
        tracker = LoadTracker(window_minutes=10)
        self.assertTrue(abs(tracker._window_minutes - 10.0) < EPS)

    def test_minimum_window_clamped(self):
        tracker = LoadTracker(window_minutes=-5)
        self.assertTrue(tracker._window_minutes >= 1.0)

    def test_snapshot_timestamp(self):
        snap = self.tracker.get_current_load()
        self.assertGreater(snap.timestamp, 0.0)

    def test_cognitive_snapshot_to_dict(self):
        snap = self.tracker.get_current_load()
        d = snap._to_dict()
        self.assertEqual(d["load_level"], snap.load_level.value)
        self.assertIsInstance(d["timestamp"], float)

    def test_cognitive_snapshot_round_trip(self):
        snap = self.tracker.get_current_load()
        d = snap._to_dict()
        restored = CognitiveSnapshot._from_dict(d)
        self.assertEqual(snap.load_level, restored.load_level)
        self.assertTrue(abs(snap.load_score - restored.load_score) < EPS)


# ======================================================================
# TestOverloadPrevention
# ======================================================================
class TestOverloadPrevention(unittest.TestCase):
    """Tests for OverloadPrevention."""

    def setUp(self):
        self.op = OverloadPrevention()

    def _make_snapshot(self, **kw):
        defaults = dict(
            load_level=LoadLevel.MODERATE,
            load_score=0.5,
            focus_state=FocusState.FOCUSED,
            active_topics=3,
            context_switches=0,
            session_duration_minutes=30.0,
        )
        defaults.update(kw)
        return CognitiveSnapshot(**defaults)

    # -- rapid switching signal ----------------------------------------

    def test_rapid_switching_detected(self):
        for i in range(7):
            self.op.add_context_switch(f"a{i}", f"b{i}")
        snap = self._make_snapshot()
        alert = self.op.check_overload(snap)
        self.assertIn(OverloadSignal.RAPID_SWITCHING, alert.signals)

    def test_no_rapid_switching_few_switches(self):
        for i in range(3):
            self.op.add_context_switch(f"a{i}", f"b{i}")
        snap = self._make_snapshot()
        alert = self.op.check_overload(snap)
        self.assertNotIn(OverloadSignal.RAPID_SWITCHING, alert.signals)

    # -- info volume signal --------------------------------------------

    def test_info_volume_detected(self):
        snap = self._make_snapshot(load_score=0.8, active_topics=8)
        alert = self.op.check_overload(snap)
        self.assertIn(OverloadSignal.INFO_VOLUME, alert.signals)

    def test_no_info_volume_low_score(self):
        snap = self._make_snapshot(load_score=0.3, active_topics=8)
        alert = self.op.check_overload(snap)
        self.assertNotIn(OverloadSignal.INFO_VOLUME, alert.signals)

    def test_no_info_volume_few_topics(self):
        snap = self._make_snapshot(load_score=0.9, active_topics=3)
        alert = self.op.check_overload(snap)
        self.assertNotIn(OverloadSignal.INFO_VOLUME, alert.signals)

    # -- complexity spike signal ---------------------------------------

    def test_complexity_spike_detected(self):
        self.op.record_complexity(0.2)
        self.op.record_complexity(0.2)
        self.op.record_complexity(0.8)
        snap = self._make_snapshot()
        alert = self.op.check_overload(snap)
        self.assertIn(OverloadSignal.COMPLEXITY_SPIKE, alert.signals)

    def test_no_complexity_spike_stable(self):
        self.op.record_complexity(0.5)
        self.op.record_complexity(0.5)
        self.op.record_complexity(0.55)
        snap = self._make_snapshot()
        alert = self.op.check_overload(snap)
        self.assertNotIn(OverloadSignal.COMPLEXITY_SPIKE, alert.signals)

    # -- error rate signal ---------------------------------------------

    def test_error_rate_detected(self):
        for _ in range(5):
            self.op.add_error_event("compile_error")
        snap = self._make_snapshot()
        alert = self.op.check_overload(snap)
        self.assertIn(OverloadSignal.ERROR_RATE, alert.signals)

    def test_no_error_rate_few_errors(self):
        self.op.add_error_event("err")
        snap = self._make_snapshot()
        alert = self.op.check_overload(snap)
        self.assertNotIn(OverloadSignal.ERROR_RATE, alert.signals)

    # -- repetition signal ---------------------------------------------

    def test_repetition_detected(self):
        for _ in range(5):
            self.op.record_action("undo")
        snap = self._make_snapshot()
        alert = self.op.check_overload(snap)
        self.assertIn(OverloadSignal.REPETITION, alert.signals)

    def test_no_repetition_varied_actions(self):
        for i in range(5):
            self.op.record_action(f"action_{i}")
        snap = self._make_snapshot()
        alert = self.op.check_overload(snap)
        self.assertNotIn(OverloadSignal.REPETITION, alert.signals)

    # -- fatigue signal ------------------------------------------------

    def test_fatigue_detected(self):
        self.op._last_break_time = time.time() - 8000
        snap = self._make_snapshot(session_duration_minutes=130)
        alert = self.op.check_overload(snap)
        self.assertIn(OverloadSignal.FATIGUE, alert.signals)

    def test_no_fatigue_short_session(self):
        snap = self._make_snapshot(session_duration_minutes=30)
        alert = self.op.check_overload(snap)
        self.assertNotIn(OverloadSignal.FATIGUE, alert.signals)

    def test_no_fatigue_after_break(self):
        self.op.record_break()
        snap = self._make_snapshot(session_duration_minutes=130)
        alert = self.op.check_overload(snap)
        self.assertNotIn(OverloadSignal.FATIGUE, alert.signals)

    # -- multi-signal --------------------------------------------------

    def test_multi_signal_detection(self):
        for i in range(7):
            self.op.add_context_switch(f"a{i}", f"b{i}")
        for _ in range(5):
            self.op.add_error_event("err")
        snap = self._make_snapshot(load_score=0.8, active_topics=8)
        alert = self.op.check_overload(snap)
        self.assertGreater(len(alert.signals), 1)
        self.assertTrue(alert.is_overloaded)

    def test_no_signals_clean_state(self):
        snap = self._make_snapshot()
        alert = self.op.check_overload(snap)
        self.assertFalse(alert.is_overloaded)
        self.assertEqual(len(alert.signals), 0)

    # -- severity & cooldown -------------------------------------------

    def test_severity_range(self):
        for i in range(7):
            self.op.add_context_switch(f"a{i}", f"b{i}")
        for _ in range(5):
            self.op.add_error_event("err")
        snap = self._make_snapshot(load_score=0.8, active_topics=8)
        alert = self.op.check_overload(snap)
        self.assertGreaterEqual(alert.severity, 0.0)
        self.assertLessEqual(alert.severity, 1.0)

    def test_severity_proportional_to_signals(self):
        for _ in range(5):
            self.op.add_error_event("err")
        snap = self._make_snapshot()
        alert1 = self.op.check_overload(snap)
        s1 = alert1.severity

        for i in range(7):
            self.op.add_context_switch(f"a{i}", f"b{i}")
        alert2 = self.op.check_overload(snap)
        self.assertGreaterEqual(alert2.severity, s1)

    def test_cooldown_zero_no_signals(self):
        snap = self._make_snapshot()
        alert = self.op.check_overload(snap)
        self.assertEqual(alert.cooldown_minutes, 0)

    def test_cooldown_positive_with_signals(self):
        for _ in range(5):
            self.op.add_error_event("err")
        snap = self._make_snapshot()
        alert = self.op.check_overload(snap)
        self.assertGreater(alert.cooldown_minutes, 0)

    # -- recommendations -----------------------------------------------

    def test_recommendations_for_rapid_switching(self):
        alert = OverloadAlert(
            is_overloaded=True,
            signals=[OverloadSignal.RAPID_SWITCHING],
            severity=0.17,
            cooldown_minutes=3,
        )
        recs = self.op.get_recommendations(alert)
        self.assertGreater(len(recs), 0)
        self.assertTrue(any("context" in r.lower() for r in recs))

    def test_recommendations_for_fatigue(self):
        alert = OverloadAlert(
            is_overloaded=True,
            signals=[OverloadSignal.FATIGUE],
            severity=0.17,
            cooldown_minutes=3,
        )
        recs = self.op.get_recommendations(alert)
        self.assertTrue(any("break" in r.lower() for r in recs))

    def test_recommendations_include_cooldown(self):
        alert = OverloadAlert(
            is_overloaded=True,
            signals=[OverloadSignal.ERROR_RATE],
            severity=0.17,
            cooldown_minutes=5,
        )
        recs = self.op.get_recommendations(alert)
        self.assertTrue(any("cooldown" in r.lower() for r in recs))

    def test_recommendations_all_signals(self):
        alert = OverloadAlert(
            is_overloaded=True,
            signals=list(OverloadSignal),
            severity=1.0,
            cooldown_minutes=15,
        )
        recs = self.op.get_recommendations(alert)
        self.assertGreater(len(recs), 5)

    def test_recommendations_empty_no_signals(self):
        alert = OverloadAlert(is_overloaded=False, signals=[], cooldown_minutes=0)
        recs = self.op.get_recommendations(alert)
        self.assertEqual(len(recs), 0)

    # -- history -------------------------------------------------------

    def test_history_grows(self):
        snap = self._make_snapshot()
        self.op.check_overload(snap)
        self.op.check_overload(snap)
        hist = self.op.get_overload_history()
        self.assertEqual(len(hist), 2)

    def test_history_capped(self):
        snap = self._make_snapshot()
        for _ in range(1100):
            self.op.check_overload(snap)
        hist = self.op.get_overload_history()
        self.assertLessEqual(len(hist), 1000)

    # -- FIFO rotation -------------------------------------------------

    def test_error_event_fifo(self):
        for i in range(5100):
            self.op.add_error_event(f"err_{i}")
        with self.op._lock:
            self.assertLessEqual(len(self.op._error_events), 5000)

    def test_context_switch_fifo(self):
        for i in range(5100):
            self.op.add_context_switch(f"a{i}", f"b{i}")
        with self.op._lock:
            self.assertLessEqual(len(self.op._context_switches), 5000)

    # -- serialisation -------------------------------------------------

    def test_to_dict_json_serialisable(self):
        self.op.add_error_event("e")
        self.op.add_context_switch("a", "b")
        snap = self._make_snapshot()
        self.op.check_overload(snap)
        d = self.op.to_dict()
        s = json.dumps(d)
        self.assertIsInstance(s, str)

    def test_round_trip(self):
        self.op.add_error_event("e")
        self.op.add_context_switch("a", "b")
        self.op.record_complexity(0.5)
        d = self.op.to_dict()
        restored = OverloadPrevention.from_dict(d)
        self.assertEqual(len(restored._error_events), 1)
        self.assertEqual(len(restored._context_switches), 1)

    def test_from_dict_empty(self):
        op = OverloadPrevention.from_dict({})
        snap = self._make_snapshot()
        alert = op.check_overload(snap)
        self.assertFalse(alert.is_overloaded)

    # -- edge cases ----------------------------------------------------

    def test_overload_alert_to_dict(self):
        alert = OverloadAlert(
            is_overloaded=True,
            signals=[OverloadSignal.FATIGUE],
            severity=0.17,
        )
        d = alert._to_dict()
        self.assertEqual(d["signals"], ["fatigue"])

    def test_overload_alert_round_trip(self):
        alert = OverloadAlert(
            is_overloaded=True,
            signals=[OverloadSignal.RAPID_SWITCHING, OverloadSignal.ERROR_RATE],
            severity=0.33,
            recommendation="slow down",
            cooldown_minutes=5,
        )
        d = alert._to_dict()
        restored = OverloadAlert._from_dict(d)
        self.assertEqual(len(restored.signals), 2)
        self.assertTrue(abs(restored.severity - 0.33) < EPS)

    def test_check_overload_returns_alert(self):
        snap = self._make_snapshot()
        alert = self.op.check_overload(snap)
        self.assertIsInstance(alert, OverloadAlert)


# ======================================================================
# TestComplexityAdapter
# ======================================================================
class TestComplexityAdapter(unittest.TestCase):
    """Tests for ComplexityAdapter."""

    def setUp(self):
        self.adapter = ComplexityAdapter()

    # -- content assessment --------------------------------------------

    def test_assess_short_content(self):
        result = self.adapter.assess_complexity("hello world")
        self.assertIsInstance(result, ComplexityAssessment)
        self.assertLess(result.score, 0.5)

    def test_assess_empty_content(self):
        result = self.adapter.assess_complexity("")
        self.assertTrue(abs(result.score - 0.0) < EPS)

    def test_assess_technical_content(self):
        content = " ".join([
            "algorithm", "api", "async", "authentication", "cache",
            "callback", "concurrency", "database", "encryption", "framework",
            "garbage", "kubernetes", "lambda", "middleware", "mutex",
        ])
        result = self.adapter.assess_complexity(content)
        self.assertGreater(result.score, 0.3)

    def test_assess_long_content(self):
        content = " ".join(["word"] * 600)
        result = self.adapter.assess_complexity(content)
        self.assertGreater(result.factors.get("length", 0), 0.5)

    def test_assess_nested_content(self):
        content = "((([[{{{[()]}}}]]))" * 5
        result = self.adapter.assess_complexity(content)
        self.assertGreater(result.factors.get("nesting", 0), 0.0)

    def test_assess_factors_present(self):
        result = self.adapter.assess_complexity("some content here")
        self.assertIn("length", result.factors)
        self.assertIn("vocabulary", result.factors)
        self.assertIn("technical", result.factors)
        self.assertIn("nesting", result.factors)

    def test_assess_with_metadata(self):
        result = self.adapter.assess_complexity("test", metadata={"key": "val"})
        self.assertIsInstance(result, ComplexityAssessment)

    # -- all complexity levels -----------------------------------------

    def test_level_trivial(self):
        result = self.adapter.assess_complexity("")
        self.assertEqual(result.level, ComplexityLevel.TRIVIAL)

    def test_level_expert(self):
        tech = " ".join([
            "algorithm", "api", "async", "authentication", "cache",
            "callback", "concurrency", "database", "encryption", "framework",
        ] * 5)
        long_text = " ".join(["elaborate"] * 600) + " " + tech
        nested = "((([[[{{{" * 10
        content = long_text + " " + nested
        result = self.adapter.assess_complexity(content)
        self.assertIn(result.level, [ComplexityLevel.COMPLEX, ComplexityLevel.EXPERT])

    def test_score_to_level_boundaries(self):
        self.assertEqual(ComplexityAdapter._score_to_level(0.0), ComplexityLevel.TRIVIAL)
        self.assertEqual(ComplexityAdapter._score_to_level(0.19), ComplexityLevel.TRIVIAL)
        self.assertEqual(ComplexityAdapter._score_to_level(0.2), ComplexityLevel.SIMPLE)
        self.assertEqual(ComplexityAdapter._score_to_level(0.4), ComplexityLevel.MODERATE)
        self.assertEqual(ComplexityAdapter._score_to_level(0.6), ComplexityLevel.COMPLEX)
        self.assertEqual(ComplexityAdapter._score_to_level(0.8), ComplexityLevel.EXPERT)

    # -- user adaptation -----------------------------------------------

    def test_adapt_reduce_on_high_load(self):
        assessment = ComplexityAssessment(
            level=ComplexityLevel.COMPLEX, score=0.7
        )
        load = CognitiveSnapshot(
            load_level=LoadLevel.HIGH,
            load_score=0.75,
            focus_state=FocusState.FOCUSED,
        )
        adapted = self.adapter.adapt_to_user(assessment, load)
        self.assertEqual(adapted.adapted_level, ComplexityLevel.MODERATE)

    def test_adapt_reduce_on_overloaded(self):
        assessment = ComplexityAssessment(
            level=ComplexityLevel.EXPERT, score=0.9
        )
        load = CognitiveSnapshot(
            load_level=LoadLevel.OVERLOADED,
            load_score=0.9,
            focus_state=FocusState.SCATTERED,
        )
        adapted = self.adapter.adapt_to_user(assessment, load)
        self.assertEqual(adapted.adapted_level, ComplexityLevel.COMPLEX)

    def test_adapt_increase_on_low_load(self):
        assessment = ComplexityAssessment(
            level=ComplexityLevel.SIMPLE, score=0.3
        )
        load = CognitiveSnapshot(
            load_level=LoadLevel.LOW,
            load_score=0.2,
            focus_state=FocusState.DEEP_FOCUS,
        )
        adapted = self.adapter.adapt_to_user(assessment, load)
        self.assertEqual(adapted.adapted_level, ComplexityLevel.MODERATE)

    def test_adapt_increase_on_minimal_load(self):
        assessment = ComplexityAssessment(
            level=ComplexityLevel.MODERATE, score=0.5
        )
        load = CognitiveSnapshot(
            load_level=LoadLevel.MINIMAL,
            load_score=0.1,
            focus_state=FocusState.DEEP_FOCUS,
        )
        adapted = self.adapter.adapt_to_user(assessment, load)
        self.assertEqual(adapted.adapted_level, ComplexityLevel.COMPLEX)

    def test_adapt_no_change_moderate_load(self):
        assessment = ComplexityAssessment(
            level=ComplexityLevel.MODERATE, score=0.5
        )
        load = CognitiveSnapshot(
            load_level=LoadLevel.MODERATE,
            load_score=0.5,
            focus_state=FocusState.FOCUSED,
        )
        adapted = self.adapter.adapt_to_user(assessment, load)
        self.assertEqual(adapted.adapted_level, ComplexityLevel.MODERATE)

    def test_adapt_no_reduce_below_trivial(self):
        assessment = ComplexityAssessment(
            level=ComplexityLevel.TRIVIAL, score=0.1
        )
        load = CognitiveSnapshot(
            load_level=LoadLevel.OVERLOADED,
            load_score=0.95,
            focus_state=FocusState.SCATTERED,
        )
        adapted = self.adapter.adapt_to_user(assessment, load)
        self.assertEqual(adapted.adapted_level, ComplexityLevel.TRIVIAL)

    def test_adapt_no_increase_above_expert(self):
        assessment = ComplexityAssessment(
            level=ComplexityLevel.EXPERT, score=0.95
        )
        load = CognitiveSnapshot(
            load_level=LoadLevel.MINIMAL,
            load_score=0.05,
            focus_state=FocusState.DEEP_FOCUS,
        )
        adapted = self.adapter.adapt_to_user(assessment, load)
        self.assertEqual(adapted.adapted_level, ComplexityLevel.EXPERT)

    def test_adapted_preserves_original_level(self):
        assessment = ComplexityAssessment(
            level=ComplexityLevel.COMPLEX, score=0.7
        )
        load = CognitiveSnapshot(
            load_level=LoadLevel.HIGH,
            load_score=0.75,
            focus_state=FocusState.LIGHT_FOCUS,
        )
        adapted = self.adapter.adapt_to_user(assessment, load)
        self.assertEqual(adapted.level, ComplexityLevel.COMPLEX)

    # -- capacity estimation -------------------------------------------

    def test_capacity_full_minimal_load(self):
        load = CognitiveSnapshot(
            load_level=LoadLevel.MINIMAL,
            load_score=0.0,
            focus_state=FocusState.DEEP_FOCUS,
        )
        cap = self.adapter.get_user_capacity(load)
        self.assertTrue(abs(cap - 1.0) < EPS)

    def test_capacity_none_overloaded(self):
        load = CognitiveSnapshot(
            load_level=LoadLevel.OVERLOADED,
            load_score=1.0,
            focus_state=FocusState.SCATTERED,
        )
        cap = self.adapter.get_user_capacity(load)
        self.assertTrue(abs(cap - 0.0) < EPS)

    def test_capacity_range(self):
        load = CognitiveSnapshot(
            load_level=LoadLevel.MODERATE,
            load_score=0.5,
            focus_state=FocusState.FOCUSED,
        )
        cap = self.adapter.get_user_capacity(load)
        self.assertGreater(cap, 0.0)
        self.assertLess(cap, 1.0)

    # -- simplification suggestions ------------------------------------

    def test_suggest_already_at_target(self):
        result = self.adapter.suggest_simplification("short text", ComplexityLevel.EXPERT)
        self.assertTrue(result["already_at_target"])
        self.assertEqual(len(result["suggestions"]), 0)

    def test_suggest_generates_suggestions(self):
        tech = " ".join([
            "algorithm", "api", "async", "authentication", "cache",
            "callback", "concurrency", "database", "encryption", "framework",
        ] * 5)
        content = " ".join(["elaborate"] * 600) + " " + tech
        content += " ((([[[" * 10
        result = self.adapter.suggest_simplification(content, ComplexityLevel.TRIVIAL)
        self.assertFalse(result["already_at_target"])
        self.assertGreater(len(result["suggestions"]), 0)

    def test_suggest_keys_present(self):
        result = self.adapter.suggest_simplification("text", ComplexityLevel.TRIVIAL)
        self.assertIn("current_level", result)
        self.assertIn("target_level", result)
        self.assertIn("suggestions", result)
        self.assertIn("score", result)

    # -- serialisation -------------------------------------------------

    def test_to_dict_json_serialisable(self):
        self.adapter.assess_complexity("some content")
        d = self.adapter.to_dict()
        s = json.dumps(d)
        self.assertIsInstance(s, str)

    def test_round_trip(self):
        self.adapter.assess_complexity("some content")
        d = self.adapter.to_dict()
        restored = ComplexityAdapter.from_dict(d)
        self.assertEqual(len(restored._history), 1)

    def test_from_dict_empty(self):
        adapter = ComplexityAdapter.from_dict({})
        self.assertEqual(len(adapter._history), 0)

    def test_complexity_assessment_to_dict(self):
        a = ComplexityAssessment(
            level=ComplexityLevel.MODERATE,
            score=0.5,
            factors={"length": 0.3},
            adapted_level=ComplexityLevel.SIMPLE,
        )
        d = a._to_dict()
        self.assertEqual(d["level"], "moderate")
        self.assertEqual(d["adapted_level"], "simple")

    def test_complexity_assessment_round_trip(self):
        a = ComplexityAssessment(
            level=ComplexityLevel.COMPLEX,
            score=0.7,
            factors={"length": 0.5, "vocabulary": 0.3},
            adapted_level=ComplexityLevel.MODERATE,
        )
        d = a._to_dict()
        restored = ComplexityAssessment._from_dict(d)
        self.assertEqual(restored.level, ComplexityLevel.COMPLEX)
        self.assertEqual(restored.adapted_level, ComplexityLevel.MODERATE)

    # -- edge cases ----------------------------------------------------

    def test_score_clamped_to_range(self):
        result = self.adapter.assess_complexity("x")
        self.assertGreaterEqual(result.score, 0.0)
        self.assertLessEqual(result.score, 1.0)

    def test_history_capped(self):
        for i in range(1100):
            self.adapter.assess_complexity(f"content {i}")
        with self.adapter._lock:
            self.assertLessEqual(len(self.adapter._history), 1000)

    def test_adapted_level_none_when_not_set(self):
        a = ComplexityAssessment(level=ComplexityLevel.SIMPLE, score=0.3)
        self.assertIsNone(a.adapted_level)

    def test_assessment_has_timestamp(self):
        result = self.adapter.assess_complexity("hello")
        self.assertGreater(result.timestamp, 0.0)


# ======================================================================
# TestFocusOptimizer
# ======================================================================
class TestFocusOptimizer(unittest.TestCase):
    """Tests for FocusOptimizer."""

    def setUp(self):
        self.optimizer = FocusOptimizer()

    # -- session lifecycle ---------------------------------------------

    def test_start_session(self):
        session = self.optimizer.start_session("s1")
        self.assertEqual(session.session_id, "s1")
        self.assertIsNone(session.ended_at)

    def test_start_session_auto_id(self):
        session = self.optimizer.start_session()
        self.assertIsNotNone(session.session_id)
        self.assertGreater(len(session.session_id), 0)

    def test_end_session(self):
        self.optimizer.start_session("s1")
        ended = self.optimizer.end_session("s1")
        self.assertIsNotNone(ended.ended_at)

    def test_end_unknown_session_raises(self):
        with self.assertRaises(KeyError):
            self.optimizer.end_session("nonexistent")

    def test_session_started_at_set(self):
        session = self.optimizer.start_session("s1")
        self.assertGreater(session.started_at, 0.0)

    # -- focus recording -----------------------------------------------

    def test_record_focus_point(self):
        self.optimizer.start_session("s1")
        self.optimizer.record_focus_point("s1", "coding", 0.8)
        stats = self.optimizer.get_session_stats("s1")
        self.assertEqual(stats["total_focus_points"], 1)

    def test_record_clamps_score(self):
        self.optimizer.start_session("s1")
        self.optimizer.record_focus_point("s1", "a", 1.5)
        self.optimizer.record_focus_point("s1", "b", -0.5)
        stats = self.optimizer.get_session_stats("s1")
        self.assertEqual(stats["total_focus_points"], 2)

    def test_record_ignores_ended_session(self):
        self.optimizer.start_session("s1")
        self.optimizer.end_session("s1")
        self.optimizer.record_focus_point("s1", "late", 0.5)
        stats = self.optimizer.get_session_stats("s1")
        self.assertEqual(stats["total_focus_points"], 0)

    def test_record_ignores_unknown_session(self):
        self.optimizer.record_focus_point("unknown", "topic", 0.5)

    def test_context_switch_tracked(self):
        self.optimizer.start_session("s1")
        self.optimizer.record_focus_point("s1", "a", 0.7)
        self.optimizer.record_focus_point("s1", "b", 0.6)
        self.optimizer.record_focus_point("s1", "a", 0.5)
        stats = self.optimizer.get_session_stats("s1")
        self.assertEqual(stats["context_switches"], 2)

    def test_peak_focus_tracked(self):
        self.optimizer.start_session("s1")
        self.optimizer.record_focus_point("s1", "a", 0.5)
        self.optimizer.record_focus_point("s1", "a", 0.9)
        self.optimizer.record_focus_point("s1", "a", 0.6)
        stats = self.optimizer.get_session_stats("s1")
        self.assertTrue(abs(stats["peak_focus"] - 0.9) < EPS)

    # -- all 5 focus states --------------------------------------------

    def test_detect_deep_focus(self):
        self.optimizer.start_session("s1")
        for _ in range(5):
            self.optimizer.record_focus_point("s1", "coding", 0.9)
        state = self.optimizer.detect_focus_state("s1")
        self.assertEqual(state, FocusState.DEEP_FOCUS)

    def test_detect_focused(self):
        self.optimizer.start_session("s1")
        for score in [0.7, 0.75, 0.7, 0.72, 0.68]:
            self.optimizer.record_focus_point("s1", "coding", score)
        state = self.optimizer.detect_focus_state("s1")
        self.assertEqual(state, FocusState.FOCUSED)

    def test_detect_light_focus(self):
        self.optimizer.start_session("s1")
        for score in [0.5, 0.55, 0.45, 0.5, 0.5]:
            self.optimizer.record_focus_point("s1", "coding", score)
        state = self.optimizer.detect_focus_state("s1")
        self.assertEqual(state, FocusState.LIGHT_FOCUS)

    def test_detect_distracted(self):
        self.optimizer.start_session("s1")
        for score in [0.3, 0.35, 0.25, 0.3, 0.28]:
            self.optimizer.record_focus_point("s1", "coding", score)
        state = self.optimizer.detect_focus_state("s1")
        self.assertIn(state, [FocusState.DISTRACTED, FocusState.SCATTERED])

    def test_detect_scattered(self):
        self.optimizer.start_session("s1")
        for score in [0.1, 0.15, 0.05, 0.1, 0.2]:
            self.optimizer.record_focus_point("s1", "coding", score)
        state = self.optimizer.detect_focus_state("s1")
        self.assertEqual(state, FocusState.SCATTERED)

    def test_detect_distracted_many_switches(self):
        self.optimizer.start_session("s1")
        topics = ["a", "b", "c", "d", "a", "b", "c", "d"]
        for i, t in enumerate(topics):
            self.optimizer.record_focus_point("s1", t, 0.4)
        state = self.optimizer.detect_focus_state("s1")
        self.assertIn(state, [FocusState.DISTRACTED, FocusState.SCATTERED])

    def test_detect_focus_empty_session(self):
        self.optimizer.start_session("s1")
        state = self.optimizer.detect_focus_state("s1")
        self.assertEqual(state, FocusState.FOCUSED)

    def test_detect_unknown_session_raises(self):
        with self.assertRaises(KeyError):
            self.optimizer.detect_focus_state("nonexistent")

    # -- stats computation ---------------------------------------------

    def test_stats_average(self):
        self.optimizer.start_session("s1")
        self.optimizer.record_focus_point("s1", "a", 0.6)
        self.optimizer.record_focus_point("s1", "a", 0.8)
        stats = self.optimizer.get_session_stats("s1")
        self.assertTrue(abs(stats["average_focus"] - 0.7) < EPS)

    def test_stats_duration(self):
        self.optimizer.start_session("s1")
        stats = self.optimizer.get_session_stats("s1")
        self.assertGreaterEqual(stats["duration_minutes"], 0.0)

    def test_stats_unique_topics(self):
        self.optimizer.start_session("s1")
        self.optimizer.record_focus_point("s1", "a", 0.5)
        self.optimizer.record_focus_point("s1", "b", 0.5)
        self.optimizer.record_focus_point("s1", "a", 0.5)
        stats = self.optimizer.get_session_stats("s1")
        self.assertEqual(stats["unique_topics"], 2)

    def test_stats_unknown_session_raises(self):
        with self.assertRaises(KeyError):
            self.optimizer.get_session_stats("nonexistent")

    def test_stats_std_dev_present(self):
        self.optimizer.start_session("s1")
        self.optimizer.record_focus_point("s1", "a", 0.5)
        self.optimizer.record_focus_point("s1", "a", 0.7)
        stats = self.optimizer.get_session_stats("s1")
        self.assertIn("std_dev", stats)
        self.assertGreater(stats["std_dev"], 0.0)

    # -- recommendations -----------------------------------------------

    def test_recommendations_deep_focus(self):
        recs = self.optimizer.get_focus_recommendations(FocusState.DEEP_FOCUS)
        self.assertGreater(len(recs), 0)

    def test_recommendations_scattered(self):
        recs = self.optimizer.get_focus_recommendations(FocusState.SCATTERED)
        self.assertGreater(len(recs), 0)
        self.assertTrue(any("break" in r.lower() for r in recs))

    def test_recommendations_each_state(self):
        for state in FocusState:
            recs = self.optimizer.get_focus_recommendations(state)
            self.assertGreater(len(recs), 0, f"No recs for {state}")

    # -- multi-session -------------------------------------------------

    def test_multiple_active_sessions(self):
        self.optimizer.start_session("s1")
        self.optimizer.start_session("s2")
        active = self.optimizer.get_active_sessions()
        self.assertEqual(len(active), 2)

    def test_ended_not_in_active(self):
        self.optimizer.start_session("s1")
        self.optimizer.start_session("s2")
        self.optimizer.end_session("s1")
        active = self.optimizer.get_active_sessions()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].session_id, "s2")

    def test_get_active_returns_copies(self):
        self.optimizer.start_session("s1")
        active = self.optimizer.get_active_sessions()
        active[0].focus_scores.append(999)
        stats = self.optimizer.get_session_stats("s1")
        self.assertEqual(stats["total_focus_points"], 0)

    # -- session caps --------------------------------------------------

    def test_session_cap_enforced(self):
        for i in range(110):
            s = self.optimizer.start_session(f"s{i}")
            self.optimizer.end_session(f"s{i}")
        # Start one more
        self.optimizer.start_session("latest")
        with self.optimizer._lock:
            self.assertLessEqual(len(self.optimizer._sessions), 100)

    def test_focus_scores_cap(self):
        self.optimizer.start_session("s1")
        for i in range(1100):
            self.optimizer.record_focus_point("s1", "a", 0.5)
        with self.optimizer._lock:
            self.assertLessEqual(len(self.optimizer._sessions["s1"].focus_scores), 1000)

    # -- serialisation -------------------------------------------------

    def test_to_dict_json_serialisable(self):
        self.optimizer.start_session("s1")
        self.optimizer.record_focus_point("s1", "a", 0.8)
        d = self.optimizer.to_dict()
        s = json.dumps(d)
        self.assertIsInstance(s, str)

    def test_round_trip(self):
        self.optimizer.start_session("s1")
        self.optimizer.record_focus_point("s1", "coding", 0.8)
        d = self.optimizer.to_dict()
        restored = FocusOptimizer.from_dict(d)
        stats = restored.get_session_stats("s1")
        self.assertEqual(stats["total_focus_points"], 1)

    def test_from_dict_empty(self):
        opt = FocusOptimizer.from_dict({})
        self.assertEqual(len(opt.get_active_sessions()), 0)

    # -- edge cases ----------------------------------------------------

    def test_end_session_computes_average(self):
        self.optimizer.start_session("s1")
        self.optimizer.record_focus_point("s1", "a", 0.4)
        self.optimizer.record_focus_point("s1", "a", 0.6)
        ended = self.optimizer.end_session("s1")
        self.assertTrue(abs(ended.average_focus - 0.5) < EPS)

    def test_focus_session_to_dict(self):
        s = FocusSession(session_id="t1", focus_scores=[0.5, 0.6], topics=["a"])
        d = s._to_dict()
        self.assertEqual(d["session_id"], "t1")
        self.assertEqual(len(d["focus_scores"]), 2)

    def test_focus_session_round_trip(self):
        s = FocusSession(
            session_id="t1",
            focus_scores=[0.5, 0.6],
            topics=["a", "b"],
            context_switches=1,
            peak_focus=0.6,
            average_focus=0.55,
        )
        d = s._to_dict()
        restored = FocusSession._from_dict(d)
        self.assertEqual(restored.session_id, "t1")
        self.assertEqual(len(restored.focus_scores), 2)

    def test_safe_std_single_value(self):
        result = FocusOptimizer._safe_std([0.5])
        self.assertTrue(abs(result - 0.0) < EPS)

    def test_safe_std_empty(self):
        result = FocusOptimizer._safe_std([])
        self.assertTrue(abs(result - 0.0) < EPS)

    def test_safe_std_two_values(self):
        result = FocusOptimizer._safe_std([0.0, 1.0])
        self.assertGreater(result, 0.0)

    def test_topics_are_unique_in_session(self):
        self.optimizer.start_session("s1")
        self.optimizer.record_focus_point("s1", "a", 0.5)
        self.optimizer.record_focus_point("s1", "a", 0.5)
        stats = self.optimizer.get_session_stats("s1")
        self.assertEqual(stats["unique_topics"], 1)


if __name__ == "__main__":
    unittest.main()
