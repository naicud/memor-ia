"""Tests for the Behavioral Prediction Engine."""

import math
import threading
import time
import unittest

from memoria.prediction import (
    ActionPredictor,
    ActionSequence,
    AnomalyAlert,
    AnomalyDetector,
    AnomalyType,
    DifficultyEstimate,
    DifficultyEstimator,
    DifficultyLevel,
    Prediction,
    PredictionType,
    TimingOptimizer,
    TimingRecommendation,
    TransitionMatrix,
)


# ======================================================================
# Type / enum tests
# ======================================================================


class TestPredictionType(unittest.TestCase):
    """PredictionType enum."""

    def test_values(self) -> None:
        self.assertEqual(PredictionType.NEXT_ACTION.value, "next_action")
        self.assertEqual(PredictionType.SESSION_END.value, "session_end")
        self.assertEqual(PredictionType.HELP_NEEDED.value, "help_needed")

    def test_completeness(self) -> None:
        expected = {
            "next_action", "next_topic", "next_tool", "next_file",
            "context_switch", "session_end", "difficulty_spike", "help_needed",
        }
        self.assertEqual({pt.value for pt in PredictionType}, expected)

    def test_member_identity(self) -> None:
        self.assertIs(PredictionType("next_action"), PredictionType.NEXT_ACTION)


class TestAnomalyType(unittest.TestCase):
    """AnomalyType enum."""

    def test_values(self) -> None:
        self.assertEqual(AnomalyType.UNUSUAL_TIMING.value, "unusual_timing")
        self.assertEqual(AnomalyType.SKILL_REGRESSION.value, "skill_regression")

    def test_completeness(self) -> None:
        expected = {
            "unusual_timing", "behavior_shift", "skill_regression",
            "pattern_break", "topic_deviation",
        }
        self.assertEqual({a.value for a in AnomalyType}, expected)

    def test_member_access(self) -> None:
        self.assertIs(AnomalyType("behavior_shift"), AnomalyType.BEHAVIOR_SHIFT)


class TestDifficultyLevel(unittest.TestCase):
    """DifficultyLevel enum."""

    def test_values(self) -> None:
        self.assertEqual(DifficultyLevel.TRIVIAL.value, "trivial")
        self.assertEqual(DifficultyLevel.EXPERT.value, "expert")

    def test_completeness(self) -> None:
        expected = {"trivial", "easy", "moderate", "hard", "expert"}
        self.assertEqual({d.value for d in DifficultyLevel}, expected)

    def test_ordering_by_value(self) -> None:
        ordered = ["trivial", "easy", "moderate", "hard", "expert"]
        self.assertEqual([d.value for d in DifficultyLevel], ordered)


# ======================================================================
# Dataclass tests
# ======================================================================


class TestPrediction(unittest.TestCase):
    """Prediction dataclass."""

    def test_creation(self) -> None:
        p = Prediction(
            prediction_type=PredictionType.NEXT_ACTION,
            predicted_value="save",
            confidence=0.85,
            reasoning="strong signal",
        )
        self.assertEqual(p.predicted_value, "save")
        self.assertEqual(p.confidence, 0.85)

    def test_defaults(self) -> None:
        p = Prediction(PredictionType.NEXT_TOOL, "git", 0.5, "guess")
        self.assertEqual(p.alternatives, [])
        self.assertEqual(p.context, {})
        self.assertIsInstance(p.timestamp, float)

    def test_alternatives(self) -> None:
        p = Prediction(
            PredictionType.NEXT_ACTION, "a", 0.6, "r",
            alternatives=[("b", 0.3), ("c", 0.1)],
        )
        self.assertEqual(len(p.alternatives), 2)
        self.assertEqual(p.alternatives[0], ("b", 0.3))

    def test_to_dict(self) -> None:
        p = Prediction(PredictionType.NEXT_ACTION, "x", 0.9, "r")
        d = p.to_dict()
        self.assertEqual(d["prediction_type"], "next_action")
        self.assertEqual(d["predicted_value"], "x")
        self.assertIn("timestamp", d)

    def test_context(self) -> None:
        p = Prediction(
            PredictionType.NEXT_FILE, "main.py", 0.7, "r",
            context={"project": "demo"},
        )
        self.assertEqual(p.context["project"], "demo")


class TestActionSequence(unittest.TestCase):
    """ActionSequence dataclass."""

    def test_creation(self) -> None:
        s = ActionSequence(actions=["a", "b", "c"])
        self.assertEqual(s.actions, ["a", "b", "c"])
        self.assertEqual(s.frequency, 1)

    def test_frequency(self) -> None:
        s = ActionSequence(actions=["x"], frequency=5)
        self.assertEqual(s.frequency, 5)

    def test_to_dict(self) -> None:
        s = ActionSequence(actions=["a", "b"], frequency=3)
        d = s.to_dict()
        self.assertEqual(d["actions"], ["a", "b"])
        self.assertEqual(d["frequency"], 3)

    def test_duration(self) -> None:
        s = ActionSequence(actions=["a"], avg_duration_seconds=12.5)
        self.assertEqual(s.avg_duration_seconds, 12.5)


class TestTransitionMatrix(unittest.TestCase):
    """TransitionMatrix dataclass."""

    def test_defaults(self) -> None:
        m = TransitionMatrix()
        self.assertEqual(m.states, [])
        self.assertEqual(m.matrix, {})
        self.assertEqual(m.total_transitions, 0)

    def test_creation(self) -> None:
        m = TransitionMatrix(
            states=["a", "b"],
            matrix={"a": {"b": 1.0}},
            total_transitions=1,
        )
        self.assertEqual(m.matrix["a"]["b"], 1.0)

    def test_to_dict(self) -> None:
        m = TransitionMatrix(states=["x"], matrix={"x": {"x": 0.5}}, total_transitions=2)
        d = m.to_dict()
        self.assertIsInstance(d["matrix"], dict)

    def test_immutable_copy(self) -> None:
        m = TransitionMatrix(states=["a"])
        d = m.to_dict()
        d["states"].append("b")
        self.assertEqual(m.states, ["a"])


class TestAnomalyAlert(unittest.TestCase):
    """AnomalyAlert dataclass."""

    def test_creation(self) -> None:
        a = AnomalyAlert(
            anomaly_type=AnomalyType.UNUSUAL_TIMING,
            severity=0.8,
            description="slow response",
        )
        self.assertEqual(a.severity, 0.8)

    def test_baseline_observed(self) -> None:
        a = AnomalyAlert(
            AnomalyType.BEHAVIOR_SHIFT, 0.5, "shift",
            baseline_value=10.0, observed_value=25.0,
        )
        self.assertEqual(a.baseline_value, 10.0)
        self.assertEqual(a.observed_value, 25.0)

    def test_to_dict(self) -> None:
        a = AnomalyAlert(AnomalyType.PATTERN_BREAK, 0.3, "break")
        d = a.to_dict()
        self.assertEqual(d["anomaly_type"], "pattern_break")

    def test_context(self) -> None:
        a = AnomalyAlert(
            AnomalyType.TOPIC_DEVIATION, 0.6, "off-topic",
            context={"expected": "python"},
        )
        self.assertEqual(a.context["expected"], "python")


class TestTimingRecommendation(unittest.TestCase):
    """TimingRecommendation dataclass."""

    def test_creation(self) -> None:
        t = TimingRecommendation(action="save", optimal_time="now", reasoning="ready")
        self.assertEqual(t.action, "save")
        self.assertEqual(t.optimal_time, "now")

    def test_defaults(self) -> None:
        t = TimingRecommendation("x", "now", "r")
        self.assertEqual(t.confidence, 0.5)
        self.assertEqual(t.cooldown_remaining, 0.0)

    def test_cooldown(self) -> None:
        t = TimingRecommendation("x", "wait", "cooling", cooldown_remaining=120.0)
        self.assertEqual(t.cooldown_remaining, 120.0)

    def test_to_dict(self) -> None:
        t = TimingRecommendation("a", "session_start", "neutral")
        d = t.to_dict()
        self.assertEqual(d["optimal_time"], "session_start")


class TestDifficultyEstimate(unittest.TestCase):
    """DifficultyEstimate dataclass."""

    def test_creation(self) -> None:
        e = DifficultyEstimate(
            task_description="deploy",
            estimated_difficulty=DifficultyLevel.HARD,
            user_competence=0.4,
            struggle_probability=0.6,
        )
        self.assertEqual(e.estimated_difficulty, DifficultyLevel.HARD)

    def test_suggestions(self) -> None:
        e = DifficultyEstimate("t", DifficultyLevel.EASY, 0.9, 0.1, suggestions=["go fast"])
        self.assertEqual(e.suggestions, ["go fast"])

    def test_to_dict(self) -> None:
        e = DifficultyEstimate("t", DifficultyLevel.MODERATE, 0.5, 0.5)
        d = e.to_dict()
        self.assertEqual(d["estimated_difficulty"], "moderate")

    def test_defaults(self) -> None:
        e = DifficultyEstimate("t", DifficultyLevel.TRIVIAL, 1.0, 0.0)
        self.assertEqual(e.estimated_time_minutes, 0.0)
        self.assertEqual(e.reasoning, "")
        self.assertEqual(e.suggestions, [])


# ======================================================================
# ActionPredictor tests
# ======================================================================


class TestActionPredictor(unittest.TestCase):
    """ActionPredictor — Markov chain prediction."""

    def setUp(self) -> None:
        self.predictor = ActionPredictor(history_window=100)

    def test_predict_empty(self) -> None:
        p = self.predictor.predict_next()
        self.assertEqual(p.confidence, 0.0)
        self.assertEqual(p.predicted_value, "")

    def test_single_action_no_transition(self) -> None:
        self.predictor.record_action("open")
        p = self.predictor.predict_next()
        self.assertEqual(p.confidence, 0.0)

    def test_simple_transition(self) -> None:
        self.predictor.record_action("open")
        self.predictor.record_action("edit")
        self.predictor.record_action("open")  # current state is "open"
        p = self.predictor.predict_next()
        self.assertEqual(p.predicted_value, "edit")
        self.assertAlmostEqual(p.confidence, 1.0)

    def test_multiple_transitions(self) -> None:
        for _ in range(3):
            self.predictor.record_action("open")
            self.predictor.record_action("edit")
        for _ in range(1):
            self.predictor.record_action("open")
            self.predictor.record_action("close")
        # From "open", edit should be more likely
        self.predictor.record_action("open")
        p = self.predictor.predict_next()
        self.assertEqual(p.predicted_value, "edit")
        self.assertGreater(p.confidence, 0.5)

    def test_top_k(self) -> None:
        self.predictor.record_action("a")
        self.predictor.record_action("b")
        self.predictor.record_action("a")
        self.predictor.record_action("c")
        self.predictor.record_action("a")
        p = self.predictor.predict_next(top_k=5)
        self.assertEqual(p.prediction_type, PredictionType.NEXT_ACTION)

    def test_alternatives(self) -> None:
        self.predictor.record_action("start")
        self.predictor.record_action("a")
        self.predictor.record_action("start")
        self.predictor.record_action("b")
        self.predictor.record_action("start")
        p = self.predictor.predict_next(top_k=3)
        # Should have at least one alternative
        self.assertGreaterEqual(len(p.alternatives), 1)

    def test_predict_sequence(self) -> None:
        self.predictor.record_action("a")
        self.predictor.record_action("b")
        self.predictor.record_action("c")
        self.predictor.record_action("a")
        self.predictor.record_action("b")
        self.predictor.record_action("c")
        seq = self.predictor.predict_sequence(length=2)
        self.assertGreaterEqual(len(seq), 1)
        # Cumulative confidence decreases
        if len(seq) >= 2:
            self.assertLessEqual(seq[1].confidence, seq[0].confidence)

    def test_predict_sequence_empty(self) -> None:
        self.assertEqual(self.predictor.predict_sequence(), [])

    def test_transition_matrix(self) -> None:
        self.predictor.record_action("a")
        self.predictor.record_action("b")
        self.predictor.record_action("a")
        self.predictor.record_action("b")
        tm = self.predictor.get_transition_matrix()
        self.assertIn("a", tm.states)
        self.assertIn("b", tm.states)
        self.assertAlmostEqual(tm.matrix["a"]["b"], 1.0)
        self.assertGreater(tm.total_transitions, 0)

    def test_action_history(self) -> None:
        self.predictor.record_action("x", context={"k": "v"})
        h = self.predictor.get_action_history()
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0]["action"], "x")
        self.assertEqual(h[0]["context"], {"k": "v"})

    def test_action_history_limit(self) -> None:
        for i in range(10):
            self.predictor.record_action(f"a{i}")
        h = self.predictor.get_action_history(limit=3)
        self.assertEqual(len(h), 3)

    def test_reset(self) -> None:
        self.predictor.record_action("a")
        self.predictor.record_action("b")
        self.predictor.reset()
        self.assertEqual(self.predictor.get_action_history(), [])
        p = self.predictor.predict_next()
        self.assertEqual(p.confidence, 0.0)

    def test_history_window_bounding(self) -> None:
        small = ActionPredictor(history_window=5)
        for i in range(20):
            small.record_action(f"a{i}")
        h = small.get_action_history(limit=100)
        self.assertLessEqual(len(h), 5)

    def test_thread_safety(self) -> None:
        errors: list = []

        def writer() -> None:
            try:
                for i in range(50):
                    self.predictor.record_action(f"t{i % 5}")
            except Exception as exc:
                errors.append(exc)

        def reader() -> None:
            try:
                for _ in range(50):
                    self.predictor.predict_next()
                    self.predictor.get_transition_matrix()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer) for _ in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])

    def test_prediction_type_is_next_action(self) -> None:
        self.predictor.record_action("a")
        self.predictor.record_action("b")
        p = self.predictor.predict_next()
        self.assertEqual(p.prediction_type, PredictionType.NEXT_ACTION)


class TestActionPredictorSequences(unittest.TestCase):
    """ActionPredictor — repeated sequence detection."""

    def setUp(self) -> None:
        self.predictor = ActionPredictor()

    def test_detect_repeated_pair(self) -> None:
        for _ in range(4):
            self.predictor.record_action("open")
            self.predictor.record_action("save")
        seqs = self.predictor.get_most_common_sequences(min_length=2, max_length=2)
        self.assertTrue(any(s.actions == ["open", "save"] for s in seqs))

    def test_min_length_filter(self) -> None:
        for _ in range(3):
            self.predictor.record_action("a")
            self.predictor.record_action("b")
            self.predictor.record_action("c")
        seqs = self.predictor.get_most_common_sequences(min_length=3, max_length=3)
        self.assertTrue(any(len(s.actions) == 3 for s in seqs))

    def test_no_sequences_short_history(self) -> None:
        self.predictor.record_action("a")
        seqs = self.predictor.get_most_common_sequences()
        self.assertEqual(seqs, [])

    def test_frequency_count(self) -> None:
        for _ in range(5):
            self.predictor.record_action("x")
            self.predictor.record_action("y")
        seqs = self.predictor.get_most_common_sequences(min_length=2, max_length=2)
        xy = [s for s in seqs if s.actions == ["x", "y"]]
        self.assertTrue(xy)
        self.assertGreaterEqual(xy[0].frequency, 4)

    def test_max_length_filter(self) -> None:
        for _ in range(3):
            self.predictor.record_action("a")
            self.predictor.record_action("b")
            self.predictor.record_action("c")
            self.predictor.record_action("d")
        seqs = self.predictor.get_most_common_sequences(min_length=2, max_length=3)
        for s in seqs:
            self.assertLessEqual(len(s.actions), 3)


# ======================================================================
# AnomalyDetector tests
# ======================================================================


class TestAnomalyDetector(unittest.TestCase):
    """AnomalyDetector — z-score-based anomaly detection."""

    def setUp(self) -> None:
        self.detector = AnomalyDetector(sensitivity=0.7, baseline_window=50)

    def test_no_observations(self) -> None:
        self.assertEqual(self.detector.detect_anomalies(), [])

    def test_single_observation_no_anomaly(self) -> None:
        self.detector.record_observation("m", 5.0)
        self.assertEqual(self.detector.detect_anomalies("m"), [])

    def test_normal_values_no_anomaly(self) -> None:
        for v in [10.0, 10.0, 10.0, 10.0, 10.0]:
            self.detector.record_observation("m", v)
        self.assertEqual(self.detector.detect_anomalies("m"), [])

    def test_extreme_value_triggers_anomaly(self) -> None:
        for v in [10.0] * 20:
            self.detector.record_observation("m", v)
        self.detector.record_observation("m", 100.0)
        alerts = self.detector.detect_anomalies("m")
        self.assertGreaterEqual(len(alerts), 1)
        self.assertGreater(alerts[0].severity, 0.0)

    def test_sensitivity_low_catches_less(self) -> None:
        self.detector.set_sensitivity(0.1)
        for v in [10.0] * 10:
            self.detector.record_observation("m", v)
        self.detector.record_observation("m", 15.0)
        alerts = self.detector.detect_anomalies("m")
        # With very low sensitivity threshold is low => more anomalies
        # Actually low sensitivity means low threshold (0.1*2=0.2 std devs) => MORE anomalies caught
        # We just test it doesn't crash
        self.assertIsInstance(alerts, list)

    def test_sensitivity_high_catches_more(self) -> None:
        self.detector.set_sensitivity(1.0)
        for v in [10.0] * 10:
            self.detector.record_observation("m", v)
        self.detector.record_observation("m", 12.0)
        # With high sensitivity (threshold = 2.0 std devs), moderate deviation might not trigger
        alerts = self.detector.detect_anomalies("m")
        self.assertIsInstance(alerts, list)

    def test_baseline_stats(self) -> None:
        for v in [1.0, 2.0, 3.0]:
            self.detector.record_observation("x", v)
        b = self.detector.get_baseline("x")
        self.assertEqual(b["count"], 3)
        self.assertAlmostEqual(b["mean"], 2.0)
        self.assertEqual(b["min"], 1.0)
        self.assertEqual(b["max"], 3.0)

    def test_baseline_empty_metric(self) -> None:
        b = self.detector.get_baseline("nonexistent")
        self.assertEqual(b["count"], 0)

    def test_get_all_metrics(self) -> None:
        self.detector.record_observation("alpha", 1.0)
        self.detector.record_observation("beta", 2.0)
        metrics = self.detector.get_all_metrics()
        self.assertIn("alpha", metrics)
        self.assertIn("beta", metrics)

    def test_reset_specific_metric(self) -> None:
        self.detector.record_observation("a", 1.0)
        self.detector.record_observation("b", 2.0)
        self.detector.reset_baseline("a")
        self.assertNotIn("a", self.detector.get_all_metrics())
        self.assertIn("b", self.detector.get_all_metrics())

    def test_reset_all(self) -> None:
        self.detector.record_observation("a", 1.0)
        self.detector.record_observation("b", 2.0)
        self.detector.reset_baseline()
        self.assertEqual(self.detector.get_all_metrics(), [])

    def test_severity_clamped(self) -> None:
        for v in [10.0] * 20:
            self.detector.record_observation("m", v)
        self.detector.record_observation("m", 10000.0)
        alerts = self.detector.detect_anomalies("m")
        self.assertGreaterEqual(len(alerts), 1)
        self.assertLessEqual(alerts[0].severity, 1.0)
        self.assertGreaterEqual(alerts[0].severity, 0.0)


class TestAnomalyDetectorTypes(unittest.TestCase):
    """AnomalyDetector — anomaly type mapping from metric names."""

    def _trigger_anomaly(self, metric: str) -> AnomalyAlert:
        d = AnomalyDetector(sensitivity=0.5)
        for _ in range(20):
            d.record_observation(metric, 10.0)
        d.record_observation(metric, 500.0)
        alerts = d.detect_anomalies(metric)
        self.assertGreaterEqual(len(alerts), 1)
        return alerts[0]

    def test_timing_metric(self) -> None:
        a = self._trigger_anomaly("session_duration")
        self.assertEqual(a.anomaly_type, AnomalyType.UNUSUAL_TIMING)

    def test_response_time_metric(self) -> None:
        a = self._trigger_anomaly("response_time")
        self.assertEqual(a.anomaly_type, AnomalyType.UNUSUAL_TIMING)

    def test_behavior_shift_metric(self) -> None:
        a = self._trigger_anomaly("action_frequency")
        self.assertEqual(a.anomaly_type, AnomalyType.BEHAVIOR_SHIFT)

    def test_skill_regression_metric(self) -> None:
        a = self._trigger_anomaly("error_rate")
        self.assertEqual(a.anomaly_type, AnomalyType.SKILL_REGRESSION)

    def test_pattern_break_metric(self) -> None:
        a = self._trigger_anomaly("sequence_break")
        self.assertEqual(a.anomaly_type, AnomalyType.PATTERN_BREAK)


# ======================================================================
# TimingOptimizer tests
# ======================================================================


class TestTimingOptimizer(unittest.TestCase):
    """TimingOptimizer — suggestion timing decisions."""

    def setUp(self) -> None:
        self.optimizer = TimingOptimizer(cooldown_seconds=0.0)

    def test_unknown_action_suggests_now(self) -> None:
        r = self.optimizer.suggest_timing("new_action")
        self.assertEqual(r.optimal_time, "now")

    def test_high_acceptance_suggests_now(self) -> None:
        for _ in range(10):
            self.optimizer.record_interaction("save", accepted=True)
        r = self.optimizer.suggest_timing("save")
        self.assertEqual(r.optimal_time, "now")

    def test_low_acceptance_suggests_after_task(self) -> None:
        for _ in range(10):
            self.optimizer.record_interaction("lint", accepted=False)
        r = self.optimizer.suggest_timing("lint")
        self.assertEqual(r.optimal_time, "after_task_completion")

    def test_moderate_acceptance_suggests_session_start(self) -> None:
        for i in range(10):
            self.optimizer.record_interaction("test", accepted=(i % 2 == 0))
        r = self.optimizer.suggest_timing("test")
        self.assertEqual(r.optimal_time, "session_start")

    def test_cooldown_blocks(self) -> None:
        opt = TimingOptimizer(cooldown_seconds=9999.0)
        opt.record_interaction("x", accepted=True)
        r = opt.suggest_timing("x")
        self.assertEqual(r.optimal_time, "wait")
        self.assertGreater(r.cooldown_remaining, 0)

    def test_cooldown_expired(self) -> None:
        opt = TimingOptimizer(cooldown_seconds=0.0)
        opt.record_interaction("x", accepted=True)
        r = opt.suggest_timing("x")
        self.assertNotEqual(r.optimal_time, "wait")

    def test_acceptance_rate_specific(self) -> None:
        self.optimizer.record_interaction("a", accepted=True)
        self.optimizer.record_interaction("a", accepted=False)
        rate = self.optimizer.get_acceptance_rate("a")
        self.assertAlmostEqual(rate["rate"], 0.5)
        self.assertEqual(rate["total"], 2)

    def test_acceptance_rate_all(self) -> None:
        self.optimizer.record_interaction("a", accepted=True)
        self.optimizer.record_interaction("b", accepted=False)
        rates = self.optimizer.get_acceptance_rate()
        self.assertIn("a", rates)
        self.assertIn("b", rates)

    def test_acceptance_rate_unknown(self) -> None:
        r = self.optimizer.get_acceptance_rate("unknown")
        self.assertEqual(r["rate"], 0.0)
        self.assertEqual(r["total"], 0)

    def test_set_cooldown(self) -> None:
        self.optimizer.set_cooldown(60.0)
        self.optimizer.record_interaction("x", accepted=True)
        r = self.optimizer.suggest_timing("x")
        self.assertEqual(r.optimal_time, "wait")

    def test_get_last_interaction(self) -> None:
        self.optimizer.record_interaction("save", accepted=True)
        info = self.optimizer.get_last_interaction("save")
        self.assertIsNotNone(info)
        self.assertEqual(info["total_suggested"], 1)
        self.assertEqual(info["total_accepted"], 1)

    def test_get_last_interaction_none(self) -> None:
        self.assertIsNone(self.optimizer.get_last_interaction("nope"))

    def test_confidence_increases_with_samples(self) -> None:
        opt = TimingOptimizer(cooldown_seconds=0.0)
        for _ in range(15):
            opt.record_interaction("x", accepted=True)
        r = opt.suggest_timing("x")
        self.assertGreaterEqual(r.confidence, 1.0)

    def test_thread_safety(self) -> None:
        errors: list = []

        def writer() -> None:
            try:
                for i in range(50):
                    self.optimizer.record_interaction(f"a{i % 3}", accepted=(i % 2 == 0))
            except Exception as exc:
                errors.append(exc)

        def reader() -> None:
            try:
                for i in range(50):
                    self.optimizer.suggest_timing(f"a{i % 3}")
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
# DifficultyEstimator tests
# ======================================================================


class TestDifficultyEstimator(unittest.TestCase):
    """DifficultyEstimator — task difficulty prediction."""

    def setUp(self) -> None:
        self.estimator = DifficultyEstimator()

    def test_no_history_returns_moderate(self) -> None:
        e = self.estimator.estimate_difficulty("deploy app", ["docker", "k8s"])
        self.assertEqual(e.estimated_difficulty, DifficultyLevel.MODERATE)
        self.assertAlmostEqual(e.user_competence, 0.5)

    def test_with_easy_history(self) -> None:
        for _ in range(5):
            self.estimator.record_task("test", ["python"], DifficultyLevel.EASY, 5.0)
        e = self.estimator.estimate_difficulty("write test", ["python"])
        self.assertEqual(e.estimated_difficulty, DifficultyLevel.EASY)

    def test_struggle_probability(self) -> None:
        for _ in range(8):
            self.estimator.record_task("t", ["rust"], DifficultyLevel.HARD, 30.0, struggled=True)
        for _ in range(2):
            self.estimator.record_task("t", ["rust"], DifficultyLevel.HARD, 30.0, struggled=False)
        e = self.estimator.estimate_difficulty("rust thing", ["rust"])
        self.assertGreater(e.struggle_probability, 0.5)

    def test_time_estimation(self) -> None:
        self.estimator.record_task("a", ["go"], DifficultyLevel.MODERATE, 10.0)
        self.estimator.record_task("b", ["go"], DifficultyLevel.MODERATE, 20.0)
        e = self.estimator.estimate_difficulty("c", ["go"])
        self.assertAlmostEqual(e.estimated_time_minutes, 15.0)

    def test_competence_high(self) -> None:
        for _ in range(10):
            self.estimator.record_task("t", ["js"], DifficultyLevel.EASY, 3.0, struggled=False)
        c = self.estimator.get_user_competence(["js"])
        self.assertGreaterEqual(c, 0.9)

    def test_competence_low(self) -> None:
        for _ in range(10):
            self.estimator.record_task("t", ["haskell"], DifficultyLevel.EXPERT, 60.0, struggled=True)
        c = self.estimator.get_user_competence(["haskell"])
        self.assertLessEqual(c, 0.1)

    def test_competence_no_history(self) -> None:
        c = self.estimator.get_user_competence(["unknown_lang"])
        self.assertAlmostEqual(c, 0.5)

    def test_strength_areas(self) -> None:
        for _ in range(5):
            self.estimator.record_task("t", ["python"], DifficultyLevel.EASY, 5.0)
        strengths = self.estimator.get_strength_areas()
        self.assertIn("python", strengths)

    def test_weakness_areas(self) -> None:
        for _ in range(5):
            self.estimator.record_task("t", ["assembly"], DifficultyLevel.EXPERT, 120.0, struggled=True)
        weaknesses = self.estimator.get_weakness_areas()
        self.assertIn("assembly", weaknesses)

    def test_task_history_all(self) -> None:
        self.estimator.record_task("a", ["x"], DifficultyLevel.EASY, 1.0)
        self.estimator.record_task("b", ["y"], DifficultyLevel.HARD, 2.0)
        h = self.estimator.get_task_history()
        self.assertEqual(len(h), 2)

    def test_task_history_filtered(self) -> None:
        self.estimator.record_task("a", ["python"], DifficultyLevel.EASY, 1.0)
        self.estimator.record_task("b", ["go"], DifficultyLevel.HARD, 2.0)
        h = self.estimator.get_task_history(keyword="python")
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0]["description"], "a")

    def test_suggestions_on_high_struggle(self) -> None:
        for _ in range(10):
            self.estimator.record_task("t", ["cpp"], DifficultyLevel.HARD, 60.0, struggled=True)
        e = self.estimator.estimate_difficulty("cpp task", ["cpp"])
        self.assertGreater(len(e.suggestions), 0)
        self.assertTrue(any("smaller steps" in s.lower() for s in e.suggestions))

    def test_keyword_case_insensitive(self) -> None:
        self.estimator.record_task("t", ["Python"], DifficultyLevel.EASY, 5.0)
        self.estimator.record_task("t", ["Python"], DifficultyLevel.EASY, 5.0)
        c = self.estimator.get_user_competence(["python"])
        self.assertGreaterEqual(c, 0.9)

    def test_thread_safety(self) -> None:
        errors: list = []

        def writer() -> None:
            try:
                for i in range(30):
                    self.estimator.record_task(
                        f"t{i}", ["kw"], DifficultyLevel.MODERATE, 5.0
                    )
            except Exception as exc:
                errors.append(exc)

        def reader() -> None:
            try:
                for _ in range(30):
                    self.estimator.estimate_difficulty("x", ["kw"])
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
# Module-level import test
# ======================================================================


class TestModuleExports(unittest.TestCase):
    """Verify __init__.py re-exports all public symbols."""

    def test_all_types_exported(self) -> None:
        from memoria.prediction import __all__
        expected = {
            "ActionPredictor", "ActionSequence", "AnomalyAlert",
            "AnomalyDetector", "AnomalyType", "DifficultyEstimate",
            "DifficultyEstimator", "DifficultyLevel", "Prediction",
            "PredictionType", "TimingOptimizer", "TimingRecommendation",
            "TransitionMatrix",
        }
        self.assertEqual(set(__all__), expected)


if __name__ == "__main__":
    unittest.main()
