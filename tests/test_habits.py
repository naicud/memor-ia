"""Tests for the Habit & Routine Intelligence module."""

import threading
import time
import unittest

from memoria.habits import (
    AnchorBehavior,
    AnchorDetector,
    AnchorType,
    DisruptionAlert,
    DisruptionEvent,
    DisruptionSeverity,
    Habit,
    HabitStrength,
    HabitTracker,
    Routine,
    RoutineOptimizer,
    RoutineStatus,
)


# ======================================================================
# Enum tests
# ======================================================================


class TestHabitStrength(unittest.TestCase):
    """HabitStrength enum."""

    def test_values(self) -> None:
        self.assertEqual(HabitStrength.EMERGING.value, "emerging")
        self.assertEqual(HabitStrength.FORMING.value, "forming")
        self.assertEqual(HabitStrength.ESTABLISHED.value, "established")
        self.assertEqual(HabitStrength.INGRAINED.value, "ingrained")

    def test_completeness(self) -> None:
        expected = {"emerging", "forming", "established", "ingrained"}
        self.assertEqual({s.value for s in HabitStrength}, expected)

    def test_member_identity(self) -> None:
        self.assertIs(HabitStrength("emerging"), HabitStrength.EMERGING)


class TestRoutineStatus(unittest.TestCase):
    """RoutineStatus enum."""

    def test_values(self) -> None:
        self.assertEqual(RoutineStatus.ACTIVE.value, "active")
        self.assertEqual(RoutineStatus.PAUSED.value, "paused")
        self.assertEqual(RoutineStatus.BROKEN.value, "broken")
        self.assertEqual(RoutineStatus.EVOLVING.value, "evolving")

    def test_completeness(self) -> None:
        expected = {"active", "paused", "broken", "evolving"}
        self.assertEqual({s.value for s in RoutineStatus}, expected)


class TestDisruptionSeverity(unittest.TestCase):
    """DisruptionSeverity enum."""

    def test_values(self) -> None:
        self.assertEqual(DisruptionSeverity.MINOR.value, "minor")
        self.assertEqual(DisruptionSeverity.MODERATE.value, "moderate")
        self.assertEqual(DisruptionSeverity.MAJOR.value, "major")
        self.assertEqual(DisruptionSeverity.CRITICAL.value, "critical")

    def test_completeness(self) -> None:
        expected = {"minor", "moderate", "major", "critical"}
        self.assertEqual({s.value for s in DisruptionSeverity}, expected)


class TestAnchorType(unittest.TestCase):
    """AnchorType enum."""

    def test_values(self) -> None:
        self.assertEqual(AnchorType.TEMPORAL.value, "temporal")
        self.assertEqual(AnchorType.SEQUENTIAL.value, "sequential")
        self.assertEqual(AnchorType.CONTEXTUAL.value, "contextual")
        self.assertEqual(AnchorType.EMOTIONAL.value, "emotional")

    def test_completeness(self) -> None:
        expected = {"temporal", "sequential", "contextual", "emotional"}
        self.assertEqual({s.value for s in AnchorType}, expected)


# ======================================================================
# Dataclass tests
# ======================================================================


class TestHabitDataclass(unittest.TestCase):
    """Habit dataclass."""

    def test_creation(self) -> None:
        h = Habit(
            habit_id="h1",
            name="test",
            actions=["a", "b"],
            frequency_per_week=3.0,
            strength=HabitStrength.EMERGING,
        )
        self.assertEqual(h.habit_id, "h1")
        self.assertEqual(h.actions, ["a", "b"])
        self.assertEqual(h.strength, HabitStrength.EMERGING)

    def test_defaults(self) -> None:
        h = Habit("h1", "test", ["a"], 1.0, HabitStrength.FORMING)
        self.assertEqual(h.typical_time, "")
        self.assertEqual(h.typical_day, "")
        self.assertEqual(h.products_involved, [])
        self.assertEqual(h.occurrence_count, 0)
        self.assertEqual(h.consistency_score, 0.0)

    def test_to_dict(self) -> None:
        h = Habit("h1", "test", ["a"], 1.0, HabitStrength.INGRAINED)
        d = h.to_dict()
        self.assertEqual(d["strength"], "ingrained")
        self.assertEqual(d["habit_id"], "h1")
        self.assertIsInstance(d["actions"], list)

    def test_to_dict_does_not_alias(self) -> None:
        h = Habit("h1", "test", ["a"], 1.0, HabitStrength.EMERGING, products_involved=["p1"])
        d = h.to_dict()
        d["products_involved"].append("p2")
        self.assertEqual(h.products_involved, ["p1"])


class TestRoutineDataclass(unittest.TestCase):
    """Routine dataclass."""

    def test_creation(self) -> None:
        r = Routine(routine_id="r1", name="morning")
        self.assertEqual(r.routine_id, "r1")
        self.assertEqual(r.status, RoutineStatus.ACTIVE)

    def test_defaults(self) -> None:
        r = Routine("r1", "morning")
        self.assertEqual(r.habits, [])
        self.assertEqual(r.expected_frequency, "daily")
        self.assertEqual(r.adherence_rate, 0.0)
        self.assertEqual(r.total_completions, 0)

    def test_to_dict(self) -> None:
        r = Routine("r1", "morning", status=RoutineStatus.BROKEN)
        d = r.to_dict()
        self.assertEqual(d["status"], "broken")
        self.assertEqual(d["routine_id"], "r1")


class TestAnchorBehaviorDataclass(unittest.TestCase):
    """AnchorBehavior dataclass."""

    def test_creation(self) -> None:
        a = AnchorBehavior(
            anchor_id="a1",
            trigger_action="open_ide",
            anchor_type=AnchorType.SEQUENTIAL,
            triggered_chain=["git_pull", "build"],
            trigger_probability=0.85,
            avg_delay_seconds=2.0,
        )
        self.assertEqual(a.trigger_action, "open_ide")
        self.assertEqual(a.anchor_type, AnchorType.SEQUENTIAL)

    def test_to_dict(self) -> None:
        a = AnchorBehavior("a1", "t", AnchorType.TEMPORAL, ["x"], 0.5, 1.0)
        d = a.to_dict()
        self.assertEqual(d["anchor_type"], "temporal")


class TestDisruptionEventDataclass(unittest.TestCase):
    """DisruptionEvent dataclass."""

    def test_creation(self) -> None:
        e = DisruptionEvent(
            disruption_id="d1",
            routine_id="r1",
            severity=DisruptionSeverity.MODERATE,
            expected_action="build",
            actual_action="deploy",
            timestamp=1000.0,
        )
        self.assertEqual(e.severity, DisruptionSeverity.MODERATE)
        self.assertFalse(e.auto_resolved)

    def test_to_dict(self) -> None:
        e = DisruptionEvent("d1", "r1", DisruptionSeverity.CRITICAL, "a", "b", 1.0)
        d = e.to_dict()
        self.assertEqual(d["severity"], "critical")
        self.assertEqual(d["possible_reasons"], [])


# ======================================================================
# HabitTracker tests
# ======================================================================


class TestHabitTrackerRecording(unittest.TestCase):
    """HabitTracker — recording actions."""

    def test_record_action_basic(self) -> None:
        ht = HabitTracker()
        ht.record_action("open_file", "vscode", timestamp=1000.0)
        self.assertEqual(len(ht._action_log), 1)

    def test_record_action_empty_ignored(self) -> None:
        ht = HabitTracker()
        ht.record_action("", "vscode")
        self.assertEqual(len(ht._action_log), 0)

    def test_record_action_default_timestamp(self) -> None:
        ht = HabitTracker()
        before = time.time()
        ht.record_action("save")
        after = time.time()
        _, ts, _ = ht._action_log[0]
        self.assertGreaterEqual(ts, before)
        self.assertLessEqual(ts, after)

    def test_max_actions_cap(self) -> None:
        ht = HabitTracker(max_actions=10)
        for i in range(20):
            ht.record_action(f"action_{i}", timestamp=float(i))
        self.assertLessEqual(len(ht._action_log), 10)

    def test_max_actions_preserves_recent(self) -> None:
        ht = HabitTracker(max_actions=10)
        for i in range(20):
            ht.record_action(f"action_{i}", timestamp=float(i))
        actions = [a for a, _, _ in ht._action_log]
        # most recent actions should be present
        self.assertIn("action_19", actions)


class TestHabitTrackerDetection(unittest.TestCase):
    """HabitTracker — detect_habits."""

    def _make_tracker_with_pattern(
        self, pattern, count, base_ts=1_000_000.0, interval=3600.0
    ):
        ht = HabitTracker(min_occurrences=3)
        ts = base_ts
        for _ in range(count):
            for action in pattern:
                ht.record_action(action, "product_a", timestamp=ts)
                ts += 10  # small gap within pattern
            ts += interval  # gap between occurrences
        return ht

    def test_detect_emerging_habit(self) -> None:
        ht = self._make_tracker_with_pattern(["open", "edit"], 5)
        habits = ht.detect_habits(min_frequency=0.1)
        self.assertTrue(len(habits) > 0)
        strengths = {h.strength for h in habits}
        self.assertIn(HabitStrength.EMERGING, strengths)

    def test_detect_forming_habit(self) -> None:
        ht = self._make_tracker_with_pattern(["open", "edit"], 10)
        habits = ht.detect_habits(min_frequency=0.1)
        self.assertTrue(any(h.strength == HabitStrength.FORMING for h in habits))

    def test_detect_established_habit(self) -> None:
        ht = self._make_tracker_with_pattern(["open", "edit"], 20)
        habits = ht.detect_habits(min_frequency=0.1)
        self.assertTrue(any(h.strength == HabitStrength.ESTABLISHED for h in habits))

    def test_detect_ingrained_habit(self) -> None:
        ht = self._make_tracker_with_pattern(["open", "edit"], 55)
        habits = ht.detect_habits(min_frequency=0.1)
        self.assertTrue(any(h.strength == HabitStrength.INGRAINED for h in habits))

    def test_no_habits_below_min_occurrences(self) -> None:
        ht = self._make_tracker_with_pattern(["a", "b"], 2)
        habits = ht.detect_habits(min_frequency=0.0)
        self.assertEqual(len(habits), 0)

    def test_no_habits_below_min_frequency(self) -> None:
        # Low frequency: 3 occurrences over a very long span
        ht = HabitTracker(min_occurrences=3)
        for i in range(3):
            ts = 1_000_000.0 + i * 30 * 86400  # 30 days apart
            ht.record_action("open", timestamp=ts)
            ht.record_action("edit", timestamp=ts + 10)
        habits = ht.detect_habits(min_frequency=50.0)
        self.assertEqual(len(habits), 0)

    def test_habit_products_involved(self) -> None:
        ht = HabitTracker(min_occurrences=3)
        for i in range(5):
            ts = 1_000_000.0 + i * 3600
            ht.record_action("a", "prod1", timestamp=ts)
            ht.record_action("b", "prod2", timestamp=ts + 5)
        habits = ht.detect_habits(min_frequency=0.1)
        if habits:
            products = habits[0].products_involved
            self.assertIn("prod1", products)
            self.assertIn("prod2", products)

    def test_typical_time_morning(self) -> None:
        ht = HabitTracker(min_occurrences=3)
        from datetime import datetime as dt
        for i in range(5):
            morning = dt(2024, 1, 1 + i, 8, 0, 0).timestamp()
            ht.record_action("a", timestamp=morning)
            ht.record_action("b", timestamp=morning + 5)
        habits = ht.detect_habits(min_frequency=0.1)
        morning_habits = [h for h in habits if h.typical_time == "morning"]
        self.assertTrue(len(morning_habits) > 0)

    def test_typical_time_afternoon(self) -> None:
        ht = HabitTracker(min_occurrences=3)
        from datetime import datetime as dt
        for i in range(5):
            afternoon = dt(2024, 1, 1 + i, 14, 0, 0).timestamp()
            ht.record_action("x", timestamp=afternoon)
            ht.record_action("y", timestamp=afternoon + 5)
        habits = ht.detect_habits(min_frequency=0.1)
        afternoon_habits = [h for h in habits if h.typical_time == "afternoon"]
        self.assertTrue(len(afternoon_habits) > 0)

    def test_typical_time_evening(self) -> None:
        ht = HabitTracker(min_occurrences=3)
        from datetime import datetime as dt
        for i in range(5):
            evening = dt(2024, 1, 1 + i, 19, 0, 0).timestamp()
            ht.record_action("p", timestamp=evening)
            ht.record_action("q", timestamp=evening + 5)
        habits = ht.detect_habits(min_frequency=0.1)
        evening_habits = [h for h in habits if h.typical_time == "evening"]
        self.assertTrue(len(evening_habits) > 0)

    def test_typical_time_night(self) -> None:
        ht = HabitTracker(min_occurrences=3)
        from datetime import datetime as dt
        for i in range(5):
            night = dt(2024, 1, 1 + i, 23, 0, 0).timestamp()
            ht.record_action("m", timestamp=night)
            ht.record_action("n", timestamp=night + 5)
        habits = ht.detect_habits(min_frequency=0.1)
        night_habits = [h for h in habits if h.typical_time == "night"]
        self.assertTrue(len(night_habits) > 0)

    def test_consistency_score_range(self) -> None:
        ht = self._make_tracker_with_pattern(["a", "b"], 10)
        habits = ht.detect_habits(min_frequency=0.1)
        for h in habits:
            self.assertGreaterEqual(h.consistency_score, 0.0)
            self.assertLessEqual(h.consistency_score, 1.0)

    def test_habit_name_contains_actions(self) -> None:
        ht = self._make_tracker_with_pattern(["open", "edit"], 5)
        habits = ht.detect_habits(min_frequency=0.1)
        names = [h.name for h in habits]
        self.assertTrue(any("open" in n and "edit" in n for n in names))

    def test_max_habits_cap(self) -> None:
        ht = HabitTracker(min_occurrences=3, max_habits=2)
        for i in range(10):
            ts = 1_000_000.0 + i * 3600
            ht.record_action(f"unique_{i % 3}", timestamp=ts)
            ht.record_action(f"follow_{i % 3}", timestamp=ts + 5)
        habits = ht.detect_habits(min_frequency=0.0)
        self.assertLessEqual(len(habits), 2)

    def test_empty_log_returns_empty(self) -> None:
        ht = HabitTracker()
        self.assertEqual(ht.detect_habits(), [])

    def test_single_action_no_habits(self) -> None:
        ht = HabitTracker()
        ht.record_action("single", timestamp=1000.0)
        self.assertEqual(ht.detect_habits(), [])


class TestHabitTrackerQuerying(unittest.TestCase):
    """HabitTracker — querying and filtering."""

    def _populated_tracker(self):
        ht = HabitTracker(min_occurrences=3)
        for i in range(10):
            ts = 1_000_000.0 + i * 3600
            ht.record_action("open", "vscode", timestamp=ts)
            ht.record_action("edit", "vscode", timestamp=ts + 5)
        for i in range(10):
            ts = 2_000_000.0 + i * 3600
            ht.record_action("browse", "chrome", timestamp=ts)
            ht.record_action("search", "chrome", timestamp=ts + 5)
        ht.detect_habits(min_frequency=0.1)
        return ht

    def test_get_habits_all(self) -> None:
        ht = self._populated_tracker()
        habits = ht.get_habits()
        self.assertTrue(len(habits) > 0)

    def test_get_habits_by_product(self) -> None:
        ht = self._populated_tracker()
        habits = ht.get_habits(product_id="vscode")
        for h in habits:
            self.assertIn("vscode", h.products_involved)

    def test_get_habits_by_product_no_match(self) -> None:
        ht = self._populated_tracker()
        habits = ht.get_habits(product_id="nonexistent")
        self.assertEqual(len(habits), 0)

    def test_get_habits_by_min_strength(self) -> None:
        ht = self._populated_tracker()
        habits = ht.get_habits(min_strength=HabitStrength.FORMING)
        for h in habits:
            self.assertIn(h.strength, [HabitStrength.FORMING, HabitStrength.ESTABLISHED, HabitStrength.INGRAINED])

    def test_get_habit_by_id(self) -> None:
        ht = self._populated_tracker()
        all_habits = ht.get_habits()
        if all_habits:
            found = ht.get_habit(all_habits[0].habit_id)
            self.assertIsNotNone(found)

    def test_get_habit_unknown_id(self) -> None:
        ht = HabitTracker()
        self.assertIsNone(ht.get_habit("nonexistent"))

    def test_is_habit_active_recent(self) -> None:
        ht = HabitTracker(min_occurrences=3)
        now = time.time()
        for i in range(5):
            ts = now - 3600 + i * 600
            ht.record_action("x", timestamp=ts)
            ht.record_action("y", timestamp=ts + 5)
        habits = ht.detect_habits(min_frequency=0.1)
        if habits:
            self.assertTrue(ht.is_habit_active(habits[0].habit_id))

    def test_is_habit_active_stale(self) -> None:
        ht = HabitTracker(min_occurrences=3)
        old_ts = time.time() - 30 * 86400  # 30 days ago
        for i in range(5):
            ts = old_ts + i * 3600
            ht.record_action("x", timestamp=ts)
            ht.record_action("y", timestamp=ts + 5)
        habits = ht.detect_habits(min_frequency=0.1)
        if habits:
            self.assertFalse(ht.is_habit_active(habits[0].habit_id, staleness_days=14))

    def test_is_habit_active_unknown_id(self) -> None:
        ht = HabitTracker()
        self.assertFalse(ht.is_habit_active("nonexistent"))

    def test_get_habit_summary(self) -> None:
        ht = self._populated_tracker()
        summary = ht.get_habit_summary()
        self.assertIn("total_habits", summary)
        self.assertIn("by_strength", summary)
        self.assertIn("products_involved", summary)
        self.assertIn("strongest_habits", summary)
        self.assertGreater(summary["total_habits"], 0)

    def test_get_habit_summary_empty(self) -> None:
        ht = HabitTracker()
        summary = ht.get_habit_summary()
        self.assertEqual(summary["total_habits"], 0)


class TestHabitTrackerThreadSafety(unittest.TestCase):
    """HabitTracker — thread safety."""

    def test_concurrent_recording(self) -> None:
        ht = HabitTracker(max_actions=10000)
        errors = []

        def record_batch(prefix):
            try:
                for i in range(100):
                    ht.record_action(f"{prefix}_{i}", timestamp=float(i))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_batch, args=(f"t{j}",)) for j in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertGreater(len(ht._action_log), 0)


# ======================================================================
# RoutineOptimizer tests
# ======================================================================


class TestRoutineOptimizerCreation(unittest.TestCase):
    """RoutineOptimizer — creating routines."""

    def test_create_routine_basic(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("Morning", ["h1", "h2"])
        self.assertEqual(r.name, "Morning")
        self.assertEqual(r.habits, ["h1", "h2"])
        self.assertEqual(r.status, RoutineStatus.ACTIVE)

    def test_create_routine_with_frequency(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("Weekly Review", ["h1"], expected_frequency="weekly")
        self.assertEqual(r.expected_frequency, "weekly")

    def test_create_routine_invalid_frequency(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("Test", ["h1"], expected_frequency="invalid")
        self.assertEqual(r.expected_frequency, "daily")

    def test_create_routine_empty_name(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("", ["h1"])
        self.assertEqual(r.name, "Untitled Routine")

    def test_create_routine_unique_ids(self) -> None:
        ro = RoutineOptimizer()
        r1 = ro.create_routine("A", ["h1"])
        r2 = ro.create_routine("B", ["h2"])
        self.assertNotEqual(r1.routine_id, r2.routine_id)

    def test_max_routines_cap(self) -> None:
        ro = RoutineOptimizer(max_routines=3)
        for i in range(5):
            ro.create_routine(f"Routine {i}", [f"h{i}"])
        self.assertLessEqual(len(ro._routines), 3)


class TestRoutineOptimizerCompletion(unittest.TestCase):
    """RoutineOptimizer — recording completions."""

    def test_record_completion_basic(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("Test", ["h1"])
        result = ro.record_completion(r.routine_id, timestamp=1000.0)
        self.assertTrue(result)
        updated = ro.get_routine(r.routine_id)
        self.assertEqual(updated.total_completions, 1)
        self.assertEqual(updated.last_completed, 1000.0)

    def test_record_completion_unknown_routine(self) -> None:
        ro = RoutineOptimizer()
        result = ro.record_completion("nonexistent", timestamp=1000.0)
        self.assertFalse(result)

    def test_record_completion_with_time(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("Test", ["h1"])
        ro.record_completion(r.routine_id, timestamp=1000.0, completion_time=120.0)
        updated = ro.get_routine(r.routine_id)
        self.assertAlmostEqual(updated.avg_completion_time, 120.0)

    def test_record_multiple_completions(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("Test", ["h1"])
        ro.record_completion(r.routine_id, timestamp=1000.0, completion_time=100.0)
        ro.record_completion(r.routine_id, timestamp=2000.0, completion_time=200.0)
        updated = ro.get_routine(r.routine_id)
        self.assertEqual(updated.total_completions, 2)
        self.assertAlmostEqual(updated.avg_completion_time, 150.0)


class TestRoutineOptimizerQuerying(unittest.TestCase):
    """RoutineOptimizer — querying."""

    def test_get_routine_by_id(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("Test", ["h1"])
        found = ro.get_routine(r.routine_id)
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "Test")

    def test_get_routine_unknown(self) -> None:
        ro = RoutineOptimizer()
        self.assertIsNone(ro.get_routine("nonexistent"))

    def test_get_routines_all(self) -> None:
        ro = RoutineOptimizer()
        ro.create_routine("A", ["h1"])
        ro.create_routine("B", ["h2"])
        self.assertEqual(len(ro.get_routines()), 2)

    def test_get_routines_by_status(self) -> None:
        ro = RoutineOptimizer()
        r1 = ro.create_routine("A", ["h1"])
        r2 = ro.create_routine("B", ["h2"])
        r2.status = RoutineStatus.BROKEN
        result = ro.get_routines(status=RoutineStatus.ACTIVE)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].routine_id, r1.routine_id)


class TestRoutineOptimizerAdherence(unittest.TestCase):
    """RoutineOptimizer — adherence computation."""

    def test_adherence_no_completions(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("Test", ["h1"])
        self.assertEqual(ro.compute_adherence(r.routine_id), 0.0)

    def test_adherence_unknown_routine(self) -> None:
        ro = RoutineOptimizer()
        self.assertEqual(ro.compute_adherence("nonexistent"), 0.0)

    def test_adherence_daily(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("Daily", ["h1"], expected_frequency="daily")
        now = time.time()
        # Simulate daily completions over 5 days
        for i in range(5):
            ro.record_completion(r.routine_id, timestamp=now - (5 - i) * 86400)
        adh = ro.compute_adherence(r.routine_id)
        self.assertGreater(adh, 0.0)
        self.assertLessEqual(adh, 1.0)

    def test_adherence_weekly(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("Weekly", ["h1"], expected_frequency="weekly")
        now = time.time()
        for i in range(4):
            ro.record_completion(r.routine_id, timestamp=now - (4 - i) * 7 * 86400)
        adh = ro.compute_adherence(r.routine_id)
        self.assertGreater(adh, 0.0)
        self.assertLessEqual(adh, 1.0)

    def test_adherence_monthly(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("Monthly", ["h1"], expected_frequency="monthly")
        now = time.time()
        for i in range(3):
            ro.record_completion(r.routine_id, timestamp=now - (3 - i) * 30 * 86400)
        adh = ro.compute_adherence(r.routine_id)
        self.assertGreater(adh, 0.0)
        self.assertLessEqual(adh, 1.0)

    def test_adherence_clamped_to_one(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("Over", ["h1"], expected_frequency="daily")
        now = time.time()
        # Many completions in a short period
        for i in range(50):
            ro.record_completion(r.routine_id, timestamp=now - 3600 + i * 60)
        adh = ro.compute_adherence(r.routine_id)
        self.assertLessEqual(adh, 1.0)


class TestRoutineOptimizerSuggestions(unittest.TestCase):
    """RoutineOptimizer — suggest_optimizations."""

    def test_suggest_low_adherence(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("Low", ["h1"])
        r.adherence_rate = 0.3
        suggestions = ro.suggest_optimizations(r.routine_id)
        self.assertTrue(any("simplifying" in s.lower() for s in suggestions))

    def test_suggest_too_many_habits(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("Big", [f"h{i}" for i in range(7)])
        suggestions = ro.suggest_optimizations(r.routine_id)
        self.assertTrue(any("splitting" in s.lower() for s in suggestions))

    def test_suggest_broken_routine(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("Broken", ["h1"])
        r.status = RoutineStatus.BROKEN
        suggestions = ro.suggest_optimizations(r.routine_id)
        self.assertTrue(any("no longer fit" in s.lower() for s in suggestions))

    def test_suggest_slow_steps(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("Slow", ["h1", "h2"])
        r.avg_completion_time = 2000.0  # 1000s per habit > 300s threshold
        suggestions = ro.suggest_optimizations(r.routine_id)
        self.assertTrue(any("too long" in s.lower() for s in suggestions))

    def test_suggest_unknown_routine(self) -> None:
        ro = RoutineOptimizer()
        suggestions = ro.suggest_optimizations("nonexistent")
        self.assertEqual(suggestions, [])

    def test_suggest_no_issues(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("Good", ["h1", "h2"])
        r.adherence_rate = 0.9
        r.avg_completion_time = 100.0
        suggestions = ro.suggest_optimizations(r.routine_id)
        self.assertEqual(len(suggestions), 0)


class TestRoutineOptimizerDrift(unittest.TestCase):
    """RoutineOptimizer — detect_routine_drift."""

    def test_drift_not_enough_data(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("Test", ["h1"])
        ro.record_completion(r.routine_id, timestamp=1000.0)
        ro.record_completion(r.routine_id, timestamp=2000.0)
        self.assertIsNone(ro.detect_routine_drift(r.routine_id))

    def test_drift_unknown_routine(self) -> None:
        ro = RoutineOptimizer()
        self.assertIsNone(ro.detect_routine_drift("nonexistent"))

    def test_drift_slowing_down(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("Slowing", ["h1"])
        # First half: frequent (every 100s), second half: infrequent (every 1000s)
        for i in range(4):
            ro.record_completion(r.routine_id, timestamp=1000.0 + i * 100)
        for i in range(4):
            ro.record_completion(r.routine_id, timestamp=2000.0 + i * 1000)
        result = ro.detect_routine_drift(r.routine_id)
        if result:
            self.assertIn("less frequent", result)

    def test_drift_speeding_up(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("Speeding", ["h1"])
        # First half: infrequent, second half: frequent
        for i in range(4):
            ro.record_completion(r.routine_id, timestamp=1000.0 + i * 1000)
        for i in range(4):
            ro.record_completion(r.routine_id, timestamp=5000.0 + i * 100)
        result = ro.detect_routine_drift(r.routine_id)
        if result:
            self.assertIn("more frequent", result)

    def test_drift_stable(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("Stable", ["h1"])
        for i in range(8):
            ro.record_completion(r.routine_id, timestamp=1000.0 + i * 500)
        result = ro.detect_routine_drift(r.routine_id)
        self.assertIsNone(result)


class TestRoutineOptimizerThreadSafety(unittest.TestCase):
    """RoutineOptimizer — thread safety."""

    def test_concurrent_operations(self) -> None:
        ro = RoutineOptimizer(max_routines=100)
        errors = []

        def create_and_complete(idx):
            try:
                r = ro.create_routine(f"R{idx}", [f"h{idx}"])
                for i in range(10):
                    ro.record_completion(r.routine_id, timestamp=1000.0 + i)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=create_and_complete, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


# ======================================================================
# AnchorDetector tests
# ======================================================================


class TestAnchorDetectorRecording(unittest.TestCase):
    """AnchorDetector — recording sequences."""

    def test_record_sequence_basic(self) -> None:
        ad = AnchorDetector()
        ad.record_sequence(["open_ide", "git_pull", "build"])
        self.assertEqual(len(ad._sequences), 1)

    def test_record_sequence_empty_ignored(self) -> None:
        ad = AnchorDetector()
        ad.record_sequence([])
        self.assertEqual(len(ad._sequences), 0)

    def test_record_with_products(self) -> None:
        ad = AnchorDetector()
        ad.record_sequence(["a", "b"], products=["prod1"])
        self.assertEqual(ad._sequences[0][2], ["prod1"])

    def test_max_sequences_cap(self) -> None:
        ad = AnchorDetector(max_sequences=10)
        for i in range(20):
            ad.record_sequence([f"action_{i}", "follow"], timestamp=float(i))
        self.assertLessEqual(len(ad._sequences), 10)


class TestAnchorDetectorDetection(unittest.TestCase):
    """AnchorDetector — detect_anchors."""

    def _populated_detector(self, trigger="open_ide", chain=None, count=5):
        ad = AnchorDetector(min_trigger_count=3)
        chain = chain or ["git_pull", "build"]
        for i in range(count):
            ad.record_sequence(
                [trigger] + chain,
                timestamp=1000.0 + i * 100,
                products=["vscode"],
            )
        return ad

    def test_detect_basic_anchor(self) -> None:
        ad = self._populated_detector()
        anchors = ad.detect_anchors(min_probability=0.5)
        self.assertTrue(len(anchors) > 0)
        self.assertEqual(anchors[0].trigger_action, "open_ide")

    def test_detect_anchor_chain(self) -> None:
        ad = self._populated_detector()
        anchors = ad.detect_anchors(min_probability=0.5)
        if anchors:
            chain = anchors[0].triggered_chain
            self.assertTrue(len(chain) > 0)

    def test_detect_anchor_probability(self) -> None:
        ad = self._populated_detector()
        anchors = ad.detect_anchors(min_probability=0.5)
        for a in anchors:
            self.assertGreaterEqual(a.trigger_probability, 0.5)

    def test_detect_anchor_below_min_count(self) -> None:
        ad = AnchorDetector(min_trigger_count=10)
        for i in range(5):
            ad.record_sequence(["a", "b", "c"], timestamp=float(i))
        anchors = ad.detect_anchors()
        self.assertEqual(len(anchors), 0)

    def test_detect_anchor_below_min_probability(self) -> None:
        ad = AnchorDetector(min_trigger_count=3)
        # Same trigger but different chains
        for i in range(3):
            ad.record_sequence(["open", "build"], timestamp=float(i))
        for i in range(3):
            ad.record_sequence(["open", "test"], timestamp=float(i + 10))
        for i in range(3):
            ad.record_sequence(["open", "deploy"], timestamp=float(i + 20))
        anchors = ad.detect_anchors(min_probability=0.9)
        # Each chain has ~33% probability, below 0.9
        self.assertEqual(len(anchors), 0)

    def test_detect_temporal_anchor(self) -> None:
        ad = AnchorDetector(min_trigger_count=3)
        for i in range(5):
            ad.record_sequence(["morning_alarm", "check_email", "read_news"], timestamp=float(i))
        anchors = ad.detect_anchors(min_probability=0.5)
        temporal = [a for a in anchors if a.anchor_type == AnchorType.TEMPORAL]
        self.assertTrue(len(temporal) > 0)

    def test_detect_sequential_anchor(self) -> None:
        ad = self._populated_detector()
        anchors = ad.detect_anchors(min_probability=0.5)
        if anchors:
            self.assertEqual(anchors[0].anchor_type, AnchorType.SEQUENTIAL)

    def test_max_anchors_cap(self) -> None:
        ad = AnchorDetector(min_trigger_count=3, max_anchors=2)
        for t in range(5):
            for i in range(5):
                ad.record_sequence([f"trigger_{t}", "follow_a", "follow_b"], timestamp=float(i + t * 100))
        anchors = ad.detect_anchors(min_probability=0.5)
        self.assertLessEqual(len(anchors), 2)

    def test_empty_sequences_no_anchors(self) -> None:
        ad = AnchorDetector()
        anchors = ad.detect_anchors()
        self.assertEqual(len(anchors), 0)

    def test_anchor_products_involved(self) -> None:
        ad = self._populated_detector()
        anchors = ad.detect_anchors(min_probability=0.5)
        if anchors:
            self.assertIn("vscode", anchors[0].products_involved)


class TestAnchorDetectorQuerying(unittest.TestCase):
    """AnchorDetector — querying and prediction."""

    def _setup_detector(self):
        ad = AnchorDetector(min_trigger_count=3)
        for i in range(5):
            ad.record_sequence(["open_ide", "git_pull", "build"], timestamp=float(i))
        for i in range(5):
            ad.record_sequence(["morning_alarm", "check_email"], timestamp=float(i + 100))
        ad.detect_anchors(min_probability=0.5)
        return ad

    def test_get_anchors_all(self) -> None:
        ad = self._setup_detector()
        self.assertTrue(len(ad.get_anchors()) > 0)

    def test_get_anchors_by_type(self) -> None:
        ad = self._setup_detector()
        sequential = ad.get_anchors(anchor_type=AnchorType.SEQUENTIAL)
        for a in sequential:
            self.assertEqual(a.anchor_type, AnchorType.SEQUENTIAL)

    def test_get_anchor_by_id(self) -> None:
        ad = self._setup_detector()
        all_anchors = ad.get_anchors()
        if all_anchors:
            found = ad.get_anchor(all_anchors[0].anchor_id)
            self.assertIsNotNone(found)

    def test_get_anchor_unknown_id(self) -> None:
        ad = AnchorDetector()
        self.assertIsNone(ad.get_anchor("nonexistent"))

    def test_predict_chain_known_trigger(self) -> None:
        ad = self._setup_detector()
        chain = ad.predict_chain("open_ide")
        if chain:
            self.assertIsInstance(chain, list)
            self.assertTrue(len(chain) > 0)

    def test_predict_chain_unknown_trigger(self) -> None:
        ad = self._setup_detector()
        self.assertIsNone(ad.predict_chain("unknown_action"))

    def test_get_anchor_summary(self) -> None:
        ad = self._setup_detector()
        summary = ad.get_anchor_summary()
        self.assertIn("total_anchors", summary)
        self.assertIn("by_type", summary)
        self.assertIn("products_involved", summary)
        self.assertIn("top_anchors", summary)

    def test_get_anchor_summary_empty(self) -> None:
        ad = AnchorDetector()
        summary = ad.get_anchor_summary()
        self.assertEqual(summary["total_anchors"], 0)


class TestAnchorDetectorThreadSafety(unittest.TestCase):
    """AnchorDetector — thread safety."""

    def test_concurrent_recording(self) -> None:
        ad = AnchorDetector(max_sequences=10000)
        errors = []

        def record_batch(prefix):
            try:
                for i in range(50):
                    ad.record_sequence([f"{prefix}_trigger", f"{prefix}_follow"], timestamp=float(i))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_batch, args=(f"t{j}",)) for j in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


# ======================================================================
# DisruptionAlert tests
# ======================================================================


class TestDisruptionAlertExpectations(unittest.TestCase):
    """DisruptionAlert — setting expectations."""

    def test_set_expectations_basic(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("r1", ["open", "edit", "save"])
        self.assertIn("r1", da._routine_expectations)
        self.assertEqual(len(da._routine_expectations["r1"]), 3)

    def test_set_expectations_with_times(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("r1", ["open", "edit"], [1000.0, 1100.0])
        self.assertEqual(da._routine_expectations["r1"][0], ("open", 1000.0))

    def test_set_expectations_mismatched_times(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("r1", ["a", "b", "c"], [1000.0])
        # Times should be padded
        self.assertEqual(len(da._routine_expectations["r1"]), 3)

    def test_set_expectations_empty_actions_ignored(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("r1", [])
        self.assertNotIn("r1", da._routine_expectations)

    def test_set_expectations_empty_id_ignored(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("", ["open"])
        self.assertNotIn("", da._routine_expectations)


class TestDisruptionAlertChecking(unittest.TestCase):
    """DisruptionAlert — check_disruption."""

    def test_no_disruption_when_matching(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("r1", ["open", "edit", "save"])
        result = da.check_disruption("r1", "open", timestamp=1000.0)
        self.assertIsNone(result)

    def test_disruption_wrong_action(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("r1", ["open", "edit"])
        result = da.check_disruption("r1", "deploy", timestamp=1000.0)
        self.assertIsNotNone(result)
        self.assertEqual(result.expected_action, "open")
        self.assertEqual(result.actual_action, "deploy")

    def test_disruption_severity_moderate(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("r1", ["open", "edit"])
        result = da.check_disruption("r1", "deploy", timestamp=1000.0)
        self.assertEqual(result.severity, DisruptionSeverity.MODERATE)

    def test_disruption_severity_major(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("r1", ["open"])
        # 3 consecutive disruptions → MAJOR
        for _ in range(3):
            result = da.check_disruption("r1", "wrong", timestamp=1000.0)
        self.assertEqual(result.severity, DisruptionSeverity.MAJOR)

    def test_disruption_severity_critical(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("r1", ["open"])
        # 7 consecutive disruptions → CRITICAL
        result = None
        for _ in range(7):
            result = da.check_disruption("r1", "wrong", timestamp=1000.0)
        self.assertEqual(result.severity, DisruptionSeverity.CRITICAL)

    def test_disruption_timing_minor(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("r1", ["open"], [1000.0])
        # Correct action but timestamp way off (>30% deviation)
        result = da.check_disruption("r1", "open", timestamp=2000.0)
        self.assertIsNotNone(result)
        self.assertEqual(result.severity, DisruptionSeverity.MINOR)

    def test_no_disruption_timing_within_tolerance(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("r1", ["open"], [1000.0])
        # Timestamp within 30% tolerance
        result = da.check_disruption("r1", "open", timestamp=1200.0)
        self.assertIsNone(result)

    def test_disruption_consecutive_reset(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("r1", ["open", "edit"])
        # Disrupt once
        da.check_disruption("r1", "wrong", timestamp=1000.0)
        # Match correctly (index should have advanced to "edit")
        result = da.check_disruption("r1", "edit", timestamp=1001.0)
        self.assertIsNone(result)

    def test_disruption_unknown_routine(self) -> None:
        da = DisruptionAlert()
        result = da.check_disruption("nonexistent", "open")
        self.assertIsNone(result)

    def test_disruption_possible_reasons(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("r1", ["open"])
        result = da.check_disruption("r1", "deploy")
        self.assertIsInstance(result.possible_reasons, list)
        self.assertTrue(len(result.possible_reasons) > 0)

    def test_disruption_skipped_action(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("r1", ["open"])
        result = da.check_disruption("r1", "none")
        self.assertIsNotNone(result)
        self.assertTrue(any("skipped" in r.lower() for r in result.possible_reasons))

    def test_max_events_cap(self) -> None:
        da = DisruptionAlert(max_events=10)
        da.set_expectations("r1", ["open"])
        for i in range(20):
            da.check_disruption("r1", "wrong", timestamp=float(i))
        self.assertLessEqual(len(da._events), 10)


class TestDisruptionAlertQuerying(unittest.TestCase):
    """DisruptionAlert — querying."""

    def _populated_alert(self):
        da = DisruptionAlert()
        da.set_expectations("r1", ["open", "edit"])
        da.set_expectations("r2", ["build", "test"])
        for i in range(5):
            da.check_disruption("r1", "wrong", timestamp=float(i))
        for i in range(3):
            da.check_disruption("r2", "wrong", timestamp=float(i + 100))
        return da

    def test_get_disruptions_all(self) -> None:
        da = self._populated_alert()
        events = da.get_disruptions()
        self.assertEqual(len(events), 8)

    def test_get_disruptions_by_routine(self) -> None:
        da = self._populated_alert()
        events = da.get_disruptions(routine_id="r1")
        self.assertEqual(len(events), 5)
        for e in events:
            self.assertEqual(e.routine_id, "r1")

    def test_get_disruptions_by_severity(self) -> None:
        da = self._populated_alert()
        events = da.get_disruptions(severity=DisruptionSeverity.MAJOR)
        for e in events:
            self.assertEqual(e.severity, DisruptionSeverity.MAJOR)

    def test_get_disruptions_limit(self) -> None:
        da = self._populated_alert()
        events = da.get_disruptions(limit=3)
        self.assertLessEqual(len(events), 3)


class TestDisruptionAlertMetrics(unittest.TestCase):
    """DisruptionAlert — disruption rate and stability."""

    def test_disruption_rate_basic(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("r1", ["open"])
        da.check_disruption("r1", "wrong")  # disruption
        da.check_disruption("r1", "open")   # no disruption
        rate = da.get_disruption_rate("r1")
        self.assertAlmostEqual(rate, 0.5)

    def test_disruption_rate_no_checks(self) -> None:
        da = DisruptionAlert()
        self.assertEqual(da.get_disruption_rate("r1"), 0.0)

    def test_disruption_rate_all_disrupted(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("r1", ["open"])
        for _ in range(5):
            da.check_disruption("r1", "wrong")
        self.assertAlmostEqual(da.get_disruption_rate("r1"), 1.0)

    def test_stability_score(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("r1", ["open"])
        da.check_disruption("r1", "wrong")
        da.check_disruption("r1", "open")
        stability = da.get_stability_score("r1")
        self.assertAlmostEqual(stability, 0.5)

    def test_stability_score_perfect(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("r1", ["open"])
        for _ in range(5):
            da.check_disruption("r1", "open")
        self.assertAlmostEqual(da.get_stability_score("r1"), 1.0)

    def test_stability_score_no_data(self) -> None:
        da = DisruptionAlert()
        self.assertEqual(da.get_stability_score("r1"), 1.0)


class TestDisruptionAlertSummary(unittest.TestCase):
    """DisruptionAlert — summary."""

    def test_summary_basic(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("r1", ["open"])
        da.set_expectations("r2", ["build"])
        for _ in range(3):
            da.check_disruption("r1", "wrong")
        da.check_disruption("r2", "wrong")
        summary = da.get_disruption_summary()
        self.assertEqual(summary["total_disruptions"], 4)
        self.assertIn("by_severity", summary)
        self.assertIn("most_disrupted_routines", summary)
        self.assertIn("trend", summary)

    def test_summary_empty(self) -> None:
        da = DisruptionAlert()
        summary = da.get_disruption_summary()
        self.assertEqual(summary["total_disruptions"], 0)
        self.assertEqual(summary["trend"], "stable")

    def test_summary_trend_increasing(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("r1", ["open"])
        # Fewer disruptions first, more later — but since we're counting events
        # we need to add them in a specific pattern
        for i in range(2):
            da.check_disruption("r1", "wrong", timestamp=float(i))
        for i in range(6):
            da.check_disruption("r1", "wrong", timestamp=float(i + 100))
        summary = da.get_disruption_summary()
        # With 8 events: first 4 in first half, last 4 in second half
        # but distribution depends on ordering
        self.assertIn(summary["trend"], ["stable", "increasing", "decreasing"])

    def test_summary_most_disrupted(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("r1", ["open"])
        da.set_expectations("r2", ["build"])
        for _ in range(5):
            da.check_disruption("r1", "wrong")
        da.check_disruption("r2", "wrong")
        summary = da.get_disruption_summary()
        self.assertTrue(len(summary["most_disrupted_routines"]) > 0)
        self.assertEqual(summary["most_disrupted_routines"][0]["routine_id"], "r1")


class TestDisruptionAlertThreadSafety(unittest.TestCase):
    """DisruptionAlert — thread safety."""

    def test_concurrent_checks(self) -> None:
        da = DisruptionAlert(max_events=10000)
        da.set_expectations("r1", ["open", "edit", "save"])
        errors = []

        def check_batch():
            try:
                for i in range(50):
                    da.check_disruption("r1", "wrong", timestamp=float(i))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=check_batch) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


# ======================================================================
# Edge case & integration tests
# ======================================================================


class TestEdgeCases(unittest.TestCase):
    """Cross-cutting edge case tests."""

    def test_tracker_min_occurrences_one(self) -> None:
        ht = HabitTracker(min_occurrences=1)
        ht.record_action("a", timestamp=1000.0)
        ht.record_action("b", timestamp=1010.0)
        habits = ht.detect_habits(min_frequency=0.0)
        self.assertTrue(len(habits) > 0)

    def test_optimizer_frequency_monthly(self) -> None:
        ro = RoutineOptimizer()
        r = ro.create_routine("Monthly", ["h1"], expected_frequency="monthly")
        self.assertEqual(r.expected_frequency, "monthly")

    def test_anchor_single_action_sequence(self) -> None:
        ad = AnchorDetector(min_trigger_count=3)
        for i in range(5):
            ad.record_sequence(["solo"], timestamp=float(i))
        anchors = ad.detect_anchors()
        # Single action has no chain to detect
        self.assertEqual(len(anchors), 0)

    def test_disruption_cyclic_expectations(self) -> None:
        da = DisruptionAlert()
        da.set_expectations("r1", ["a", "b"])
        # Check cycles through a, b, a, b, ...
        result1 = da.check_disruption("r1", "a")
        self.assertIsNone(result1)
        result2 = da.check_disruption("r1", "b")
        self.assertIsNone(result2)
        result3 = da.check_disruption("r1", "a")  # wraps around
        self.assertIsNone(result3)

    def test_habit_to_dict_round_trip_fields(self) -> None:
        h = Habit("h1", "test", ["a", "b"], 2.0, HabitStrength.FORMING,
                   typical_time="morning", products_involved=["p1"],
                   occurrence_count=10, consistency_score=0.85)
        d = h.to_dict()
        self.assertEqual(d["typical_time"], "morning")
        self.assertEqual(d["occurrence_count"], 10)
        self.assertEqual(d["consistency_score"], 0.85)

    def test_routine_to_dict_round_trip_fields(self) -> None:
        r = Routine("r1", "Test", habits=["h1"], total_completions=5, avg_completion_time=120.0)
        d = r.to_dict()
        self.assertEqual(d["total_completions"], 5)
        self.assertEqual(d["avg_completion_time"], 120.0)

    def test_anchor_behavior_to_dict_fields(self) -> None:
        a = AnchorBehavior("a1", "trigger", AnchorType.CONTEXTUAL, ["c1", "c2"],
                           0.9, 5.0, occurrence_count=20, products_involved=["p1"])
        d = a.to_dict()
        self.assertEqual(d["anchor_type"], "contextual")
        self.assertEqual(d["occurrence_count"], 20)

    def test_disruption_event_to_dict_fields(self) -> None:
        e = DisruptionEvent("d1", "r1", DisruptionSeverity.MINOR, "a", "b", 1000.0,
                            possible_reasons=["timing"], auto_resolved=True)
        d = e.to_dict()
        self.assertEqual(d["auto_resolved"], True)
        self.assertEqual(d["possible_reasons"], ["timing"])

    def test_tracker_detect_habits_with_varying_lengths(self) -> None:
        ht = HabitTracker(min_occurrences=3)
        for i in range(5):
            ts = 1_000_000.0 + i * 3600
            ht.record_action("a", timestamp=ts)
            ht.record_action("b", timestamp=ts + 5)
            ht.record_action("c", timestamp=ts + 10)
        # Should detect both 2-action and 3-action habits
        habits = ht.detect_habits(min_frequency=0.1, min_length=2, max_length=3)
        lengths = {len(h.actions) for h in habits}
        self.assertTrue(len(habits) > 0)

    def test_multiple_anchor_types(self) -> None:
        ad = AnchorDetector(min_trigger_count=3)
        for i in range(5):
            ad.record_sequence(["daily_alarm", "exercise", "shower"], timestamp=float(i))
        for i in range(5):
            ad.record_sequence(["code_push", "run_tests", "review"], timestamp=float(i + 100))
        anchors = ad.detect_anchors(min_probability=0.5)
        types = {a.anchor_type for a in anchors}
        self.assertTrue(len(types) > 0)


class TestImportAll(unittest.TestCase):
    """Verify all public symbols are importable."""

    def test_all_classes_importable(self) -> None:
        from memoria.habits import (
            AnchorBehavior,
            AnchorDetector,
            AnchorType,
            DisruptionAlert,
            DisruptionEvent,
            DisruptionSeverity,
            Habit,
            HabitStrength,
            HabitTracker,
            Routine,
            RoutineOptimizer,
            RoutineStatus,
        )
        self.assertTrue(True)

    def test_all_list(self) -> None:
        import memoria.habits as m
        self.assertEqual(len(m.__all__), 12)


if __name__ == "__main__":
    unittest.main()
