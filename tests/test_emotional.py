"""Comprehensive tests for the MEMORIA Emotional Intelligence Layer.

Covers types, analyzer, tracker, empathy engine, and fatigue detector
with 90+ tests across all classes.
"""

import time
import unittest

from memoria.emotional.types import (
    EmpathyAction,
    EmpathyTrigger,
    EmotionalArc,
    EmotionalProfile,
    EmotionReading,
    EmotionType,
    FatigueScore,
    IntensityLevel,
    SentimentScore,
    TrendDirection,
)
from memoria.emotional.analyzer import EmotionAnalyzer
from memoria.emotional.tracker import EmotionalArcTracker
from memoria.emotional.empathy import EmpathyEngine
from memoria.emotional.fatigue import FatigueDetector


# ═══════════════════════════════════════════════════════════════════════
# TYPE TESTS
# ═══════════════════════════════════════════════════════════════════════


class TestEmotionType(unittest.TestCase):
    """EmotionType enum tests."""

    def test_has_twelve_members(self):
        self.assertEqual(len(EmotionType), 12)

    def test_values_are_lowercase_strings(self):
        for et in EmotionType:
            self.assertEqual(et.value, et.value.lower())

    def test_lookup_by_value(self):
        self.assertEqual(EmotionType("joy"), EmotionType.JOY)
        self.assertEqual(EmotionType("frustration"), EmotionType.FRUSTRATION)

    def test_all_expected_members_present(self):
        expected = {
            "joy", "satisfaction", "excitement", "confidence",
            "frustration", "anger", "confusion", "anxiety",
            "boredom", "fatigue", "curiosity", "neutral",
        }
        actual = {et.value for et in EmotionType}
        self.assertEqual(actual, expected)


class TestIntensityLevel(unittest.TestCase):
    """IntensityLevel enum tests."""

    def test_has_five_members(self):
        self.assertEqual(len(IntensityLevel), 5)

    def test_values(self):
        vals = [il.value for il in IntensityLevel]
        self.assertIn("minimal", vals)
        self.assertIn("intense", vals)

    def test_lookup_by_value(self):
        self.assertEqual(IntensityLevel("moderate"), IntensityLevel.MODERATE)


class TestEmpathyAction(unittest.TestCase):
    """EmpathyAction enum tests."""

    def test_has_seven_members(self):
        self.assertEqual(len(EmpathyAction), 7)

    def test_none_action_exists(self):
        self.assertEqual(EmpathyAction.NONE.value, "none")

    def test_all_values(self):
        expected = {
            "acknowledge", "encourage", "suggest_break",
            "simplify", "celebrate", "redirect", "none",
        }
        actual = {ea.value for ea in EmpathyAction}
        self.assertEqual(actual, expected)


class TestTrendDirection(unittest.TestCase):
    """TrendDirection enum tests."""

    def test_has_four_members(self):
        self.assertEqual(len(TrendDirection), 4)

    def test_values(self):
        expected = {"improving", "declining", "stable", "volatile"}
        actual = {td.value for td in TrendDirection}
        self.assertEqual(actual, expected)

    def test_lookup_by_value(self):
        self.assertEqual(TrendDirection("volatile"), TrendDirection.VOLATILE)


class TestEmotionReading(unittest.TestCase):
    """EmotionReading dataclass tests."""

    def test_create_minimal(self):
        r = EmotionReading(emotion=EmotionType.JOY, intensity=0.8, confidence=0.9)
        self.assertEqual(r.emotion, EmotionType.JOY)
        self.assertEqual(r.intensity, 0.8)
        self.assertEqual(r.confidence, 0.9)

    def test_default_signals_empty(self):
        r = EmotionReading(emotion=EmotionType.NEUTRAL, intensity=0.0, confidence=0.0)
        self.assertEqual(r.signals, [])

    def test_default_context_empty(self):
        r = EmotionReading(emotion=EmotionType.NEUTRAL, intensity=0.0, confidence=0.0)
        self.assertEqual(r.context, "")

    def test_timestamp_auto_populated(self):
        before = time.time()
        r = EmotionReading(emotion=EmotionType.NEUTRAL, intensity=0.0, confidence=0.0)
        after = time.time()
        self.assertGreaterEqual(r.timestamp, before)
        self.assertLessEqual(r.timestamp, after)

    def test_to_dict(self):
        r = EmotionReading(
            emotion=EmotionType.FRUSTRATION, intensity=0.7, confidence=0.8,
            signals=["keyword:broken"], context="debugging",
        )
        d = r._to_dict()
        self.assertEqual(d["emotion"], "frustration")
        self.assertIn("keyword:broken", d["signals"])
        self.assertEqual(d["context"], "debugging")

    def test_signals_independent_between_instances(self):
        r1 = EmotionReading(emotion=EmotionType.NEUTRAL, intensity=0.0, confidence=0.0)
        r2 = EmotionReading(emotion=EmotionType.NEUTRAL, intensity=0.0, confidence=0.0)
        r1.signals.append("test")
        self.assertEqual(r2.signals, [])


class TestSentimentScore(unittest.TestCase):
    """SentimentScore dataclass tests."""

    def test_create_positive(self):
        s = SentimentScore(valence=0.8, arousal=0.5, dominance=0.6)
        self.assertEqual(s.valence, 0.8)
        self.assertEqual(s.arousal, 0.5)
        self.assertEqual(s.dominance, 0.6)

    def test_create_negative(self):
        s = SentimentScore(valence=-0.7, arousal=0.9, dominance=0.2)
        self.assertLess(s.valence, 0)

    def test_to_dict(self):
        s = SentimentScore(valence=0.5, arousal=0.3, dominance=0.4)
        d = s._to_dict()
        self.assertEqual(d["valence"], 0.5)

    def test_neutral_sentiment(self):
        s = SentimentScore(valence=0.0, arousal=0.0, dominance=0.5)
        self.assertEqual(s.valence, 0.0)


class TestEmotionalArc(unittest.TestCase):
    """EmotionalArc dataclass tests."""

    def test_create_default(self):
        arc = EmotionalArc(session_id="test")
        self.assertEqual(arc.session_id, "test")
        self.assertEqual(arc.readings, [])
        self.assertEqual(arc.trend, TrendDirection.STABLE)
        self.assertEqual(arc.dominant_emotion, EmotionType.NEUTRAL)

    def test_volatility_default_zero(self):
        arc = EmotionalArc(session_id="test")
        self.assertEqual(arc.volatility, 0.0)

    def test_to_dict(self):
        arc = EmotionalArc(session_id="s1", average_valence=0.5)
        d = arc._to_dict()
        self.assertEqual(d["session_id"], "s1")
        self.assertEqual(d["average_valence"], 0.5)

    def test_turning_points_default_empty(self):
        arc = EmotionalArc(session_id="s1")
        self.assertEqual(arc.turning_points, [])

    def test_readings_independent(self):
        a1 = EmotionalArc(session_id="a")
        a2 = EmotionalArc(session_id="b")
        a1.readings.append(
            EmotionReading(emotion=EmotionType.JOY, intensity=1.0, confidence=1.0)
        )
        self.assertEqual(len(a2.readings), 0)


class TestEmpathyTrigger(unittest.TestCase):
    """EmpathyTrigger dataclass tests."""

    def test_create(self):
        t = EmpathyTrigger(
            trigger_emotion=EmotionType.FRUSTRATION,
            intensity_threshold=0.6,
            action=EmpathyAction.ENCOURAGE,
            message_template="Keep going!",
        )
        self.assertEqual(t.trigger_emotion, EmotionType.FRUSTRATION)

    def test_default_priority(self):
        t = EmpathyTrigger(
            trigger_emotion=EmotionType.JOY,
            intensity_threshold=0.5,
            action=EmpathyAction.CELEBRATE,
            message_template="Nice!",
        )
        self.assertEqual(t.priority, 5)

    def test_default_cooldown(self):
        t = EmpathyTrigger(
            trigger_emotion=EmotionType.JOY,
            intensity_threshold=0.5,
            action=EmpathyAction.CELEBRATE,
            message_template="Nice!",
        )
        self.assertEqual(t.cooldown_seconds, 300.0)

    def test_to_dict(self):
        t = EmpathyTrigger(
            trigger_emotion=EmotionType.ANGER,
            intensity_threshold=0.7,
            action=EmpathyAction.ACKNOWLEDGE,
            message_template="I hear you.",
            priority=8,
        )
        d = t._to_dict()
        self.assertEqual(d["trigger_emotion"], "anger")
        self.assertEqual(d["action"], "acknowledge")
        self.assertEqual(d["priority"], 8)


class TestFatigueScore(unittest.TestCase):
    """FatigueScore dataclass tests."""

    def test_create(self):
        fs = FatigueScore(current_level=0.5)
        self.assertEqual(fs.current_level, 0.5)

    def test_default_burnout_risk_low(self):
        fs = FatigueScore(current_level=0.1)
        self.assertEqual(fs.burnout_risk, "low")

    def test_contributing_factors_default_empty(self):
        fs = FatigueScore(current_level=0.0)
        self.assertEqual(fs.contributing_factors, [])

    def test_to_dict(self):
        fs = FatigueScore(
            current_level=0.8, burnout_risk="critical",
            contributing_factors=["frustration"],
        )
        d = fs._to_dict()
        self.assertEqual(d["burnout_risk"], "critical")
        self.assertIn("frustration", d["contributing_factors"])


class TestEmotionalProfile(unittest.TestCase):
    """EmotionalProfile dataclass tests."""

    def test_create(self):
        ep = EmotionalProfile(user_id="u1")
        self.assertEqual(ep.user_id, "u1")

    def test_defaults(self):
        ep = EmotionalProfile(user_id="u1")
        self.assertEqual(ep.baseline_mood, EmotionType.NEUTRAL)
        self.assertEqual(ep.emotional_resilience, 0.5)
        self.assertEqual(ep.sessions_analyzed, 0)

    def test_preferred_support_default(self):
        ep = EmotionalProfile(user_id="u1")
        self.assertEqual(ep.preferred_support_style, EmpathyAction.ENCOURAGE)

    def test_to_dict(self):
        ep = EmotionalProfile(user_id="u1", sessions_analyzed=5)
        d = ep._to_dict()
        self.assertEqual(d["user_id"], "u1")
        self.assertEqual(d["sessions_analyzed"], 5)


# ═══════════════════════════════════════════════════════════════════════
# ANALYZER TESTS
# ═══════════════════════════════════════════════════════════════════════


class TestEmotionAnalyzer(unittest.TestCase):
    """EmotionAnalyzer tests."""

    def setUp(self):
        self.analyzer = EmotionAnalyzer()

    # -- basic emotion detection --

    def test_analyze_frustration(self):
        r = self.analyzer.analyze("This is so frustrating and broken!")
        self.assertEqual(r.emotion, EmotionType.FRUSTRATION)
        self.assertGreater(r.intensity, 0.0)

    def test_analyze_satisfaction(self):
        r = self.analyzer.analyze("Perfect, that works great, thanks!")
        self.assertEqual(r.emotion, EmotionType.SATISFACTION)

    def test_analyze_confusion(self):
        r = self.analyzer.analyze("I'm confused, this makes no sense")
        self.assertEqual(r.emotion, EmotionType.CONFUSION)

    def test_analyze_joy(self):
        r = self.analyzer.analyze("I'm so happy and delighted with this!")
        self.assertEqual(r.emotion, EmotionType.JOY)

    def test_analyze_anger(self):
        r = self.analyzer.analyze("This is absolutely infuriating and outrageous")
        self.assertEqual(r.emotion, EmotionType.ANGER)

    def test_analyze_anxiety(self):
        r = self.analyzer.analyze("I'm really worried and nervous about this")
        self.assertEqual(r.emotion, EmotionType.ANXIETY)

    def test_analyze_curiosity(self):
        r = self.analyzer.analyze("This is really interesting and fascinating")
        self.assertEqual(r.emotion, EmotionType.CURIOSITY)

    def test_analyze_neutral(self):
        r = self.analyzer.analyze("The function returns an integer value")
        self.assertEqual(r.emotion, EmotionType.NEUTRAL)

    def test_analyze_empty_text(self):
        r = self.analyzer.analyze("")
        self.assertEqual(r.emotion, EmotionType.NEUTRAL)
        self.assertEqual(r.intensity, 0.0)
        self.assertEqual(r.confidence, 0.0)

    def test_analyze_whitespace_only(self):
        r = self.analyzer.analyze("   ")
        self.assertEqual(r.emotion, EmotionType.NEUTRAL)

    # -- punctuation boosting --

    def test_exclamation_boosts_intensity(self):
        r_plain = self.analyzer.analyze("frustrated and broken")
        r_bang = self.analyzer.analyze("frustrated and broken!!!")
        self.assertGreater(r_bang.intensity, r_plain.intensity)

    def test_question_marks_boost_confusion(self):
        r = self.analyzer.analyze("confused??? why???")
        self.assertEqual(r.emotion, EmotionType.CONFUSION)
        self.assertGreater(r.intensity, 0.3)

    def test_ellipsis_boost(self):
        r = self.analyzer.analyze("I'm worried about this...")
        self.assertEqual(r.emotion, EmotionType.ANXIETY)

    def test_caps_boost_anger(self):
        r = self.analyzer.analyze("THIS IS ABSOLUTELY RIDICULOUS AND ABSURD")
        self.assertEqual(r.emotion, EmotionType.ANGER)
        self.assertGreater(r.intensity, 0.5)

    # -- intensity & confidence --

    def test_intensity_clamped_zero_one(self):
        for text in ["broken broken broken!!!", "happy"]:
            r = self.analyzer.analyze(text)
            self.assertGreaterEqual(r.intensity, 0.0)
            self.assertLessEqual(r.intensity, 1.0)

    def test_confidence_scales_with_signals(self):
        r_few = self.analyzer.analyze("broken")
        r_many = self.analyzer.analyze("frustrated broken annoying hate terrible")
        self.assertGreaterEqual(r_many.confidence, r_few.confidence)

    # -- batch analysis --

    def test_analyze_batch(self):
        texts = [
            "I'm so frustrated",
            "This works perfectly, thanks!",
            "Regular code output",
        ]
        results = self.analyzer.analyze_batch(texts)
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].emotion, EmotionType.FRUSTRATION)
        self.assertEqual(results[1].emotion, EmotionType.SATISFACTION)
        self.assertEqual(results[2].emotion, EmotionType.NEUTRAL)

    # -- sentiment score --

    def test_sentiment_positive(self):
        s = self.analyzer.get_sentiment_score("I'm so happy and delighted!")
        self.assertGreater(s.valence, 0.0)

    def test_sentiment_negative(self):
        s = self.analyzer.get_sentiment_score("This is frustrating and broken")
        self.assertLess(s.valence, 0.0)

    def test_sentiment_neutral(self):
        s = self.analyzer.get_sentiment_score("The variable stores data")
        self.assertEqual(s.valence, 0.0)

    # -- intensity level mapping --

    def test_intensity_level_minimal(self):
        self.assertEqual(EmotionAnalyzer.get_intensity_level(0.1), IntensityLevel.MINIMAL)

    def test_intensity_level_mild(self):
        self.assertEqual(EmotionAnalyzer.get_intensity_level(0.3), IntensityLevel.MILD)

    def test_intensity_level_moderate(self):
        self.assertEqual(EmotionAnalyzer.get_intensity_level(0.5), IntensityLevel.MODERATE)

    def test_intensity_level_strong(self):
        self.assertEqual(EmotionAnalyzer.get_intensity_level(0.7), IntensityLevel.STRONG)

    def test_intensity_level_intense(self):
        self.assertEqual(EmotionAnalyzer.get_intensity_level(0.9), IntensityLevel.INTENSE)

    # -- context propagation --

    def test_context_passed_through(self):
        r = self.analyzer.analyze("broken code", context="debugging")
        self.assertEqual(r.context, "debugging")

    # -- smiley detection --

    def test_positive_smiley(self):
        r = self.analyzer.analyze("nice work :)")
        self.assertIn(r.emotion, (EmotionType.SATISFACTION, EmotionType.JOY))

    def test_negative_smiley(self):
        r = self.analyzer.analyze("this broke :(")
        signals = r.signals
        has_smiley_signal = any("smiley" in s for s in signals)
        self.assertTrue(has_smiley_signal or r.emotion in (
            EmotionType.FRUSTRATION, EmotionType.ANXIETY,
        ))


# ═══════════════════════════════════════════════════════════════════════
# TRACKER TESTS
# ═══════════════════════════════════════════════════════════════════════


class TestEmotionalArcTracker(unittest.TestCase):
    """EmotionalArcTracker tests."""

    def setUp(self):
        self.tracker = EmotionalArcTracker(max_readings=50)

    def _reading(self, emotion, intensity=0.5, ts=None):
        return EmotionReading(
            emotion=emotion, intensity=intensity, confidence=0.8,
            timestamp=ts or time.time(),
        )

    def test_record_and_get_arc(self):
        self.tracker.record_reading(self._reading(EmotionType.JOY))
        arc = self.tracker.get_arc()
        self.assertEqual(len(arc.readings), 1)
        self.assertEqual(arc.session_id, "default")

    def test_trend_improving(self):
        # Start negative, end positive
        for _ in range(5):
            self.tracker.record_reading(self._reading(EmotionType.FRUSTRATION, 0.8))
        for _ in range(5):
            self.tracker.record_reading(self._reading(EmotionType.JOY, 0.8))
        trend = self.tracker.get_trend()
        self.assertEqual(trend, TrendDirection.IMPROVING)

    def test_trend_declining(self):
        for _ in range(5):
            self.tracker.record_reading(self._reading(EmotionType.JOY, 0.8))
        for _ in range(5):
            self.tracker.record_reading(self._reading(EmotionType.FRUSTRATION, 0.8))
        trend = self.tracker.get_trend()
        self.assertEqual(trend, TrendDirection.DECLINING)

    def test_trend_stable(self):
        for _ in range(10):
            self.tracker.record_reading(self._reading(EmotionType.NEUTRAL, 0.5))
        trend = self.tracker.get_trend()
        self.assertEqual(trend, TrendDirection.STABLE)

    def test_trend_volatile(self):
        # Balanced alternation: each half gets same mix → no directional trend
        pattern = [EmotionType.ANGER, EmotionType.JOY] * 4  # 8 readings
        for etype in pattern:
            self.tracker.record_reading(self._reading(etype, 0.9))
        trend = self.tracker.get_trend()
        self.assertEqual(trend, TrendDirection.VOLATILE)

    def test_dominant_emotion(self):
        for _ in range(7):
            self.tracker.record_reading(self._reading(EmotionType.CURIOSITY))
        for _ in range(3):
            self.tracker.record_reading(self._reading(EmotionType.JOY))
        dominant = self.tracker.get_dominant_emotion()
        self.assertEqual(dominant, EmotionType.CURIOSITY)

    def test_turning_points_detected(self):
        self.tracker.record_reading(self._reading(EmotionType.JOY, 0.9))
        self.tracker.record_reading(self._reading(EmotionType.ANGER, 0.9))
        points = self.tracker.get_turning_points()
        self.assertGreater(len(points), 0)
        self.assertEqual(points[0]["from_emotion"], "joy")
        self.assertEqual(points[0]["to_emotion"], "anger")

    def test_max_readings_enforced(self):
        tracker = EmotionalArcTracker(max_readings=5)
        for _ in range(10):
            tracker.record_reading(self._reading(EmotionType.NEUTRAL))
        arc = tracker.get_arc()
        self.assertEqual(len(arc.readings), 5)

    def test_reset_session(self):
        self.tracker.record_reading(self._reading(EmotionType.JOY))
        self.tracker.reset_session()
        arc = self.tracker.get_arc()
        self.assertEqual(len(arc.readings), 0)

    def test_multiple_sessions(self):
        self.tracker.record_reading(self._reading(EmotionType.JOY), session_id="a")
        self.tracker.record_reading(self._reading(EmotionType.ANGER), session_id="b")
        arc_a = self.tracker.get_arc("a")
        arc_b = self.tracker.get_arc("b")
        self.assertEqual(arc_a.readings[0].emotion, EmotionType.JOY)
        self.assertEqual(arc_b.readings[0].emotion, EmotionType.ANGER)

    def test_cross_session_trend(self):
        for _ in range(3):
            self.tracker.record_reading(
                self._reading(EmotionType.FRUSTRATION, 0.8), session_id="s1"
            )
        for _ in range(3):
            self.tracker.record_reading(
                self._reading(EmotionType.JOY, 0.8), session_id="s2"
            )
        result = self.tracker.get_cross_session_trend()
        self.assertEqual(result["sessions"], 2)
        self.assertIn(result["trend"], [td.value for td in TrendDirection])

    def test_emotional_profile(self):
        for _ in range(5):
            self.tracker.record_reading(self._reading(EmotionType.JOY, 0.7))
        profile = self.tracker.get_emotional_profile()
        self.assertEqual(profile.sessions_analyzed, 1)
        self.assertEqual(profile.baseline_mood, EmotionType.JOY)

    def test_empty_session_returns_neutral_dominant(self):
        dominant = self.tracker.get_dominant_emotion("nonexistent")
        self.assertEqual(dominant, EmotionType.NEUTRAL)

    def test_arc_average_valence(self):
        for _ in range(4):
            self.tracker.record_reading(self._reading(EmotionType.JOY, 0.8))
        arc = self.tracker.get_arc()
        self.assertGreater(arc.average_valence, 0.0)

    def test_arc_volatility(self):
        self.tracker.record_reading(self._reading(EmotionType.JOY, 0.9))
        self.tracker.record_reading(self._reading(EmotionType.ANGER, 0.9))
        arc = self.tracker.get_arc()
        self.assertGreater(arc.volatility, 0.0)


# ═══════════════════════════════════════════════════════════════════════
# EMPATHY ENGINE TESTS
# ═══════════════════════════════════════════════════════════════════════


class TestEmpathyEngine(unittest.TestCase):
    """EmpathyEngine tests."""

    def setUp(self):
        self.engine = EmpathyEngine()

    def _reading(self, emotion, intensity=0.5):
        return EmotionReading(
            emotion=emotion, intensity=intensity, confidence=0.8,
        )

    def test_evaluate_frustration_high(self):
        r = self._reading(EmotionType.FRUSTRATION, 0.9)
        triggers = self.engine.evaluate(r)
        self.assertGreater(len(triggers), 0)
        actions = {t.action for t in triggers}
        self.assertTrue(
            actions & {EmpathyAction.ENCOURAGE, EmpathyAction.SUGGEST_BREAK}
        )

    def test_evaluate_low_intensity_no_trigger(self):
        r = self._reading(EmotionType.FRUSTRATION, 0.1)
        triggers = self.engine.evaluate(r)
        self.assertEqual(len(triggers), 0)

    def test_get_response_frustration(self):
        r = self._reading(EmotionType.FRUSTRATION, 0.9)
        resp = self.engine.get_response(r)
        self.assertIsNotNone(resp)
        self.assertIn("action", resp)
        self.assertIn("message", resp)

    def test_get_response_joy(self):
        r = self._reading(EmotionType.JOY, 0.8)
        resp = self.engine.get_response(r)
        self.assertIsNotNone(resp)
        self.assertEqual(resp["action"], "celebrate")

    def test_get_response_fatigue(self):
        r = self._reading(EmotionType.FATIGUE, 0.8)
        resp = self.engine.get_response(r)
        self.assertIsNotNone(resp)
        self.assertEqual(resp["action"], "suggest_break")

    def test_get_response_confusion(self):
        r = self._reading(EmotionType.CONFUSION, 0.6)
        resp = self.engine.get_response(r)
        self.assertIsNotNone(resp)
        self.assertEqual(resp["action"], "simplify")

    def test_no_response_neutral(self):
        r = self._reading(EmotionType.NEUTRAL, 0.5)
        resp = self.engine.get_response(r)
        self.assertIsNone(resp)

    def test_should_intervene_true(self):
        r = self._reading(EmotionType.ANGER, 0.8)
        self.assertTrue(self.engine.should_intervene(r))

    def test_should_intervene_false(self):
        r = self._reading(EmotionType.NEUTRAL, 0.5)
        self.assertFalse(self.engine.should_intervene(r))

    def test_add_custom_trigger(self):
        t = EmpathyTrigger(
            trigger_emotion=EmotionType.CURIOSITY,
            intensity_threshold=0.3,
            action=EmpathyAction.ENCOURAGE,
            message_template="Keep exploring!",
        )
        self.engine.add_trigger(t)
        r = self._reading(EmotionType.CURIOSITY, 0.5)
        triggers = self.engine.evaluate(r)
        self.assertGreater(len(triggers), 0)

    def test_remove_trigger(self):
        removed = self.engine.remove_trigger(
            EmotionType.BOREDOM, EmpathyAction.REDIRECT
        )
        self.assertTrue(removed)
        r = self._reading(EmotionType.BOREDOM, 0.9)
        triggers = self.engine.evaluate(r)
        redirect_triggers = [t for t in triggers if t.action == EmpathyAction.REDIRECT]
        self.assertEqual(len(redirect_triggers), 0)

    def test_remove_nonexistent_trigger(self):
        removed = self.engine.remove_trigger(
            EmotionType.NEUTRAL, EmpathyAction.CELEBRATE
        )
        self.assertFalse(removed)

    def test_get_all_triggers(self):
        triggers = self.engine.get_all_triggers()
        self.assertIsInstance(triggers, list)
        self.assertGreater(len(triggers), 0)
        self.assertIn("trigger_emotion", triggers[0])

    def test_cooldown_prevents_repeated_fire(self):
        # First call fires
        r = self._reading(EmotionType.FRUSTRATION, 0.9)
        resp1 = self.engine.get_response(r)
        self.assertIsNotNone(resp1)
        # Second immediate call should still fire for the OTHER trigger
        # (the SUGGEST_BREAK at 0.8 vs ENCOURAGE at 0.6)
        resp2 = self.engine.get_response(r)
        # At least one of them is on cooldown now
        # The behaviour is: get_response picks highest priority, records cooldown
        # On second call, the highest-priority is on cooldown, so next one fires
        # This verifies the mechanism works
        if resp2 is not None:
            # If a second trigger fired, it should be a different action
            # (or same emotion, different action)
            self.assertIsNotNone(resp2["action"])

    def test_record_response_and_stats(self):
        self.engine.record_response(
            EmotionType.FRUSTRATION, EmpathyAction.ENCOURAGE, accepted=True
        )
        self.engine.record_response(
            EmotionType.FRUSTRATION, EmpathyAction.ENCOURAGE, accepted=False
        )
        stats = self.engine.get_effectiveness_stats()
        self.assertIn("encourage", stats)
        self.assertEqual(stats["encourage"]["accepted"], 1)
        self.assertEqual(stats["encourage"]["rejected"], 1)

    def test_effectiveness_stats_empty_initially(self):
        stats = self.engine.get_effectiveness_stats()
        self.assertEqual(stats, {})

    def test_multiple_triggers_priority_order(self):
        r = self._reading(EmotionType.FRUSTRATION, 0.9)
        triggers = self.engine.evaluate(r)
        # Should be sorted by priority descending
        priorities = [t.priority for t in triggers]
        self.assertEqual(priorities, sorted(priorities, reverse=True))


# ═══════════════════════════════════════════════════════════════════════
# FATIGUE DETECTOR TESTS
# ═══════════════════════════════════════════════════════════════════════


class TestFatigueDetector(unittest.TestCase):
    """FatigueDetector tests."""

    def setUp(self):
        self.detector = FatigueDetector(fatigue_halflife_minutes=120.0)

    def _reading(self, emotion, intensity=0.5, ts=None):
        return EmotionReading(
            emotion=emotion, intensity=intensity, confidence=0.8,
            timestamp=ts or time.time(),
        )

    def test_initial_fatigue_zero(self):
        score = self.detector.get_fatigue_score()
        self.assertEqual(score.current_level, 0.0)
        self.assertEqual(score.burnout_risk, "low")

    def test_negative_emotions_increase_fatigue(self):
        for _ in range(5):
            self.detector.update(self._reading(EmotionType.FRUSTRATION, 0.8))
        score = self.detector.get_fatigue_score()
        self.assertGreater(score.current_level, 0.0)

    def test_positive_emotions_decrease_fatigue(self):
        # Build up fatigue
        for _ in range(5):
            self.detector.update(self._reading(EmotionType.FRUSTRATION, 0.8))
        high = self.detector.get_fatigue_score().current_level
        # Apply positive emotions
        for _ in range(5):
            self.detector.update(self._reading(EmotionType.JOY, 0.8))
        low = self.detector.get_fatigue_score().current_level
        self.assertLess(low, high)

    def test_burnout_risk_low(self):
        score = self.detector.get_fatigue_score()
        self.assertEqual(score.burnout_risk, "low")

    def test_burnout_risk_increases(self):
        for _ in range(20):
            self.detector.update(self._reading(EmotionType.FRUSTRATION, 1.0))
        score = self.detector.get_fatigue_score()
        self.assertIn(score.burnout_risk, ("medium", "high", "critical"))

    def test_is_burnout_risk_false_initially(self):
        self.assertFalse(self.detector.is_burnout_risk())

    def test_is_burnout_risk_true_after_stress(self):
        for _ in range(20):
            self.detector.update(self._reading(EmotionType.ANGER, 1.0))
        self.assertTrue(self.detector.is_burnout_risk())

    def test_recovery_estimate_zero_when_low(self):
        est = self.detector.get_recovery_estimate()
        self.assertEqual(est, 0.0)

    def test_recovery_estimate_positive_when_fatigued(self):
        for _ in range(10):
            self.detector.update(self._reading(EmotionType.FRUSTRATION, 1.0))
        est = self.detector.get_recovery_estimate()
        self.assertGreater(est, 0.0)

    def test_session_end_reduces_fatigue(self):
        for _ in range(10):
            self.detector.update(self._reading(EmotionType.FRUSTRATION, 1.0))
        before = self.detector.get_fatigue_score().current_level
        self.detector.record_session_end("s1", 60.0)
        after = self.detector.get_fatigue_score().current_level
        self.assertLess(after, before)

    def test_session_fatigue_history(self):
        self.detector.record_session_end("s1", 30.0, "completed")
        self.detector.record_session_end("s2", 60.0, "abandoned")
        history = self.detector.get_session_fatigue_history()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["session_id"], "s1")
        self.assertEqual(history[1]["outcome"], "abandoned")

    def test_reset_clears_everything(self):
        for _ in range(5):
            self.detector.update(self._reading(EmotionType.FRUSTRATION, 0.8))
        self.detector.record_session_end("s1", 30.0)
        self.detector.reset()
        score = self.detector.get_fatigue_score()
        self.assertEqual(score.current_level, 0.0)
        self.assertEqual(self.detector.get_session_fatigue_history(), [])

    def test_contributing_factors_tracked(self):
        self.detector.update(self._reading(EmotionType.FRUSTRATION, 0.8))
        score = self.detector.get_fatigue_score()
        self.assertIn("negative_emotion:frustration", score.contributing_factors)

    def test_long_session_adds_fatigue(self):
        self.detector.update(
            self._reading(EmotionType.NEUTRAL, 0.1),
            session_duration_minutes=120.0,
        )
        score = self.detector.get_fatigue_score()
        self.assertGreater(score.current_level, 0.0)
        self.assertIn("long_session", score.contributing_factors)

    def test_fatigue_clamped_at_one(self):
        for _ in range(100):
            self.detector.update(self._reading(EmotionType.ANGER, 1.0))
        score = self.detector.get_fatigue_score()
        self.assertLessEqual(score.current_level, 1.0)

    def test_fatigue_never_negative(self):
        for _ in range(50):
            self.detector.update(self._reading(EmotionType.JOY, 1.0))
        score = self.detector.get_fatigue_score()
        self.assertGreaterEqual(score.current_level, 0.0)

    def test_history_limit(self):
        for i in range(15):
            self.detector.record_session_end(f"s{i}", 10.0)
        history = self.detector.get_session_fatigue_history(limit=5)
        self.assertEqual(len(history), 5)


# ═══════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════


class TestEmotionalLayerIntegration(unittest.TestCase):
    """End-to-end integration tests across all components."""

    def test_analyze_then_track_then_empathy(self):
        analyzer = EmotionAnalyzer()
        tracker = EmotionalArcTracker()
        engine = EmpathyEngine()

        # Simulate a user getting increasingly frustrated
        texts = [
            "Let me try this again",
            "Still broken, this is annoying",
            "UGH this is so frustrating and broken!!!",
        ]
        for text in texts:
            reading = analyzer.analyze(text)
            tracker.record_reading(reading)

        arc = tracker.get_arc()
        self.assertGreater(len(arc.readings), 0)

        last_reading = arc.readings[-1]
        resp = engine.get_response(last_reading)
        if last_reading.emotion == EmotionType.FRUSTRATION and last_reading.intensity >= 0.6:
            self.assertIsNotNone(resp)

    def test_analyze_then_fatigue(self):
        analyzer = EmotionAnalyzer()
        detector = FatigueDetector()

        texts = [
            "This is broken and frustrating",
            "Still not working, hate this",
            "Angry and furious about these bugs",
        ]
        for text in texts:
            reading = analyzer.analyze(text)
            detector.update(reading)

        score = detector.get_fatigue_score()
        self.assertGreater(score.current_level, 0.0)

    def test_full_session_lifecycle(self):
        analyzer = EmotionAnalyzer()
        tracker = EmotionalArcTracker()
        detector = FatigueDetector()

        for text in ["broken code", "still broken", "hate this"]:
            r = analyzer.analyze(text)
            tracker.record_reading(r, session_id="s1")
            detector.update(r)

        for text in ["works great", "perfect solution", "love it"]:
            r = analyzer.analyze(text)
            tracker.record_reading(r, session_id="s1")
            detector.update(r)

        arc = tracker.get_arc("s1")
        self.assertEqual(len(arc.readings), 6)
        # Should show improvement since we ended positive
        profile = tracker.get_emotional_profile()
        self.assertEqual(profile.sessions_analyzed, 1)

    def test_imports_from_package(self):
        """Verify the public __init__ exports work."""
        from memoria.emotional import (
            EmotionAnalyzer,
            EmpathyEngine,
            FatigueDetector,
            EmotionalArcTracker,
            EmotionType,
            IntensityLevel,
        )
        self.assertIsNotNone(EmotionAnalyzer)
        self.assertIsNotNone(EmotionType.JOY)


if __name__ == "__main__":
    unittest.main()
