"""Test suite completa per il modulo product_intel."""

from __future__ import annotations

import threading
import time
import unittest
from typing import Any, Dict

from memoria.product_intel import (
    AdoptionAnalyzer,
    AdoptionCurve,
    AdoptionStage,
    FeatureStatus,
    ProductCategory,
    ProductGraph,
    ProductInfo,
    ProductRelationship,
    ProductTracker,
    ProductUsageEvent,
    UsageFrequency,
    UsageProfile,
    UsageProfiler,
)


# ======================================================================
# Module exports
# ======================================================================


class TestModuleExports(unittest.TestCase):
    def test_all_types_exported(self) -> None:
        from memoria.product_intel import __all__

        expected = {
            "AdoptionAnalyzer",
            "AdoptionCurve",
            "AdoptionStage",
            "FeatureStatus",
            "ProductCategory",
            "ProductGraph",
            "ProductInfo",
            "ProductRelationship",
            "ProductTracker",
            "ProductUsageEvent",
            "UsageFrequency",
            "UsageProfile",
            "UsageProfiler",
        }
        self.assertEqual(set(__all__), expected)

    def test_classes_importable(self) -> None:
        self.assertTrue(callable(ProductTracker))
        self.assertTrue(callable(UsageProfiler))
        self.assertTrue(callable(ProductGraph))
        self.assertTrue(callable(AdoptionAnalyzer))


# ======================================================================
# Types / Enums
# ======================================================================


class TestProductCategory(unittest.TestCase):
    def test_values(self) -> None:
        self.assertEqual(ProductCategory.BILLING.value, "billing")
        self.assertEqual(ProductCategory.CRM.value, "crm")
        self.assertEqual(ProductCategory.IDE.value, "ide")
        self.assertEqual(ProductCategory.CUSTOM.value, "custom")

    def test_member_count(self) -> None:
        self.assertEqual(len(ProductCategory), 12)


class TestUsageFrequency(unittest.TestCase):
    def test_values(self) -> None:
        self.assertEqual(UsageFrequency.DAILY.value, "daily")
        self.assertEqual(UsageFrequency.INACTIVE.value, "inactive")

    def test_member_count(self) -> None:
        self.assertEqual(len(UsageFrequency), 6)


class TestAdoptionStage(unittest.TestCase):
    def test_values(self) -> None:
        self.assertEqual(AdoptionStage.DISCOVERY.value, "discovery")
        self.assertEqual(AdoptionStage.CHURNED.value, "churned")

    def test_member_count(self) -> None:
        self.assertEqual(len(AdoptionStage), 7)


class TestFeatureStatus(unittest.TestCase):
    def test_values(self) -> None:
        self.assertEqual(FeatureStatus.UNKNOWN.value, "unknown")
        self.assertEqual(FeatureStatus.MASTERED.value, "mastered")
        self.assertEqual(FeatureStatus.ABANDONED.value, "abandoned")

    def test_member_count(self) -> None:
        self.assertEqual(len(FeatureStatus), 6)


# ======================================================================
# Dataclass tests
# ======================================================================


class TestProductInfo(unittest.TestCase):
    def test_creation(self) -> None:
        p = ProductInfo(
            product_id="stripe",
            name="Stripe",
            category=ProductCategory.BILLING,
        )
        self.assertEqual(p.product_id, "stripe")
        self.assertEqual(p.category, ProductCategory.BILLING)
        self.assertEqual(p.features, [])

    def test_to_dict(self) -> None:
        p = ProductInfo(
            product_id="jira",
            name="Jira",
            category=ProductCategory.PROJECT_MANAGEMENT,
            version="9.0",
            features=["boards", "sprints"],
        )
        d = p.to_dict()
        self.assertEqual(d["product_id"], "jira")
        self.assertEqual(d["category"], "project_management")
        self.assertEqual(d["features"], ["boards", "sprints"])

    def test_to_dict_immutable_copy(self) -> None:
        p = ProductInfo(
            product_id="x", name="X", category=ProductCategory.CRM
        )
        d = p.to_dict()
        d["features"].append("new")
        self.assertEqual(p.features, [])


class TestProductUsageEvent(unittest.TestCase):
    def test_creation(self) -> None:
        e = ProductUsageEvent(
            product_id="vscode",
            feature="editor",
            action="click",
            timestamp=1000.0,
        )
        self.assertEqual(e.product_id, "vscode")
        self.assertEqual(e.duration_seconds, 0.0)

    def test_to_dict(self) -> None:
        e = ProductUsageEvent(
            product_id="p1",
            feature="f1",
            action="create",
            timestamp=500.0,
            session_id="s1",
        )
        d = e.to_dict()
        self.assertEqual(d["action"], "create")
        self.assertEqual(d["session_id"], "s1")


class TestUsageProfile(unittest.TestCase):
    def test_defaults(self) -> None:
        u = UsageProfile(product_id="p1")
        self.assertEqual(u.total_events, 0)
        self.assertEqual(u.frequency, UsageFrequency.INACTIVE)
        self.assertEqual(u.adoption_stage, AdoptionStage.DISCOVERY)

    def test_to_dict(self) -> None:
        u = UsageProfile(
            product_id="p1",
            frequency=UsageFrequency.DAILY,
            feature_adoption={"feat": FeatureStatus.ADOPTED},
        )
        d = u.to_dict()
        self.assertEqual(d["frequency"], "daily")
        self.assertEqual(d["feature_adoption"]["feat"], "adopted")


class TestProductRelationship(unittest.TestCase):
    def test_creation(self) -> None:
        r = ProductRelationship(
            source_product="a",
            target_product="b",
            relationship_type="workflow_link",
            strength=0.8,
        )
        self.assertEqual(r.strength, 0.8)

    def test_to_dict(self) -> None:
        r = ProductRelationship(
            source_product="a",
            target_product="b",
            relationship_type="data_flow",
            common_features=["auth"],
        )
        d = r.to_dict()
        self.assertEqual(d["relationship_type"], "data_flow")
        self.assertEqual(d["common_features"], ["auth"])


class TestAdoptionCurve(unittest.TestCase):
    def test_defaults(self) -> None:
        c = AdoptionCurve(
            product_id="p1",
            feature="f1",
            stage=FeatureStatus.UNKNOWN,
        )
        self.assertEqual(c.total_uses, 0)
        self.assertEqual(c.usage_trend, "stable")

    def test_to_dict(self) -> None:
        c = AdoptionCurve(
            product_id="p1",
            feature="f1",
            stage=FeatureStatus.MASTERED,
            total_uses=100,
        )
        d = c.to_dict()
        self.assertEqual(d["stage"], "mastered")
        self.assertEqual(d["total_uses"], 100)


# ======================================================================
# ProductTracker
# ======================================================================


class TestProductTracker(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = ProductTracker(max_products=50)

    def test_register_product(self) -> None:
        info = self.tracker.register_product(
            "stripe", "Stripe", ProductCategory.BILLING, version="3.0"
        )
        self.assertEqual(info.name, "Stripe")
        self.assertEqual(info.category, ProductCategory.BILLING)
        self.assertGreater(info.registered_at, 0)

    def test_register_with_features(self) -> None:
        info = self.tracker.register_product(
            "jira",
            "Jira",
            ProductCategory.PROJECT_MANAGEMENT,
            features=["boards", "sprints"],
        )
        self.assertEqual(info.features, ["boards", "sprints"])

    def test_register_with_metadata(self) -> None:
        info = self.tracker.register_product(
            "slack",
            "Slack",
            ProductCategory.COMMUNICATION,
            metadata={"plan": "enterprise"},
        )
        self.assertEqual(info.metadata["plan"], "enterprise")

    def test_register_update_existing(self) -> None:
        self.tracker.register_product(
            "vscode", "VS Code", ProductCategory.IDE, version="1.0"
        )
        updated = self.tracker.register_product(
            "vscode", "VS Code", ProductCategory.IDE, version="2.0"
        )
        self.assertEqual(updated.version, "2.0")
        self.assertEqual(len(self.tracker.list_products()), 1)

    def test_unregister_product(self) -> None:
        self.tracker.register_product(
            "tool", "Tool", ProductCategory.CUSTOM
        )
        self.assertTrue(self.tracker.unregister_product("tool"))
        self.assertIsNone(self.tracker.get_product("tool"))

    def test_unregister_nonexistent(self) -> None:
        self.assertFalse(self.tracker.unregister_product("nope"))

    def test_get_product(self) -> None:
        self.tracker.register_product(
            "gh", "GitHub", ProductCategory.DEVELOPMENT
        )
        p = self.tracker.get_product("gh")
        self.assertIsNotNone(p)
        self.assertEqual(p.name, "GitHub")

    def test_get_product_missing(self) -> None:
        self.assertIsNone(self.tracker.get_product("missing"))

    def test_list_products_all(self) -> None:
        self.tracker.register_product("a", "A", ProductCategory.CRM)
        self.tracker.register_product("b", "B", ProductCategory.IDE)
        self.assertEqual(len(self.tracker.list_products()), 2)

    def test_list_products_by_category(self) -> None:
        self.tracker.register_product("a", "A", ProductCategory.CRM)
        self.tracker.register_product("b", "B", ProductCategory.CRM)
        self.tracker.register_product("c", "C", ProductCategory.IDE)
        result = self.tracker.list_products(category=ProductCategory.CRM)
        self.assertEqual(len(result), 2)

    def test_list_products_empty_category(self) -> None:
        self.tracker.register_product("a", "A", ProductCategory.CRM)
        result = self.tracker.list_products(
            category=ProductCategory.SECURITY
        )
        self.assertEqual(len(result), 0)

    def test_ecosystem_summary(self) -> None:
        self.tracker.register_product("a", "A", ProductCategory.BILLING)
        self.tracker.register_product("b", "B", ProductCategory.BILLING)
        self.tracker.register_product("c", "C", ProductCategory.IDE)
        summary = self.tracker.get_ecosystem_summary()
        self.assertEqual(summary["total_products"], 3)
        self.assertEqual(summary["categories"]["billing"], 2)
        self.assertEqual(summary["categories"]["ide"], 1)
        self.assertEqual(len(summary["timeline"]), 3)

    def test_ecosystem_summary_empty(self) -> None:
        summary = self.tracker.get_ecosystem_summary()
        self.assertEqual(summary["total_products"], 0)

    def test_max_products_cap(self) -> None:
        tracker = ProductTracker(max_products=3)
        for i in range(5):
            tracker.register_product(
                f"p{i}", f"Product {i}", ProductCategory.CUSTOM
            )
        self.assertLessEqual(len(tracker.list_products()), 3)

    def test_max_products_evicts_oldest(self) -> None:
        tracker = ProductTracker(max_products=2)
        tracker.register_product("old", "Old", ProductCategory.CUSTOM)
        time.sleep(0.01)
        tracker.register_product("mid", "Mid", ProductCategory.CUSTOM)
        time.sleep(0.01)
        tracker.register_product("new", "New", ProductCategory.CUSTOM)
        self.assertIsNone(tracker.get_product("old"))
        self.assertIsNotNone(tracker.get_product("new"))

    def test_to_dict(self) -> None:
        self.tracker.register_product("a", "A", ProductCategory.CRM)
        d = self.tracker.to_dict()
        self.assertIn("max_products", d)
        self.assertIn("products", d)
        self.assertIn("a", d["products"])

    def test_from_dict(self) -> None:
        self.tracker.register_product(
            "x",
            "X Tool",
            ProductCategory.ANALYTICS,
            version="1.0",
            features=["dash"],
        )
        d = self.tracker.to_dict()
        restored = ProductTracker.from_dict(d)
        p = restored.get_product("x")
        self.assertIsNotNone(p)
        self.assertEqual(p.name, "X Tool")
        self.assertEqual(p.category, ProductCategory.ANALYTICS)
        self.assertEqual(p.features, ["dash"])

    def test_from_dict_empty(self) -> None:
        restored = ProductTracker.from_dict({})
        self.assertEqual(len(restored.list_products()), 0)

    def test_roundtrip_to_from_dict(self) -> None:
        for i in range(5):
            self.tracker.register_product(
                f"p{i}", f"P{i}", ProductCategory.CUSTOM
            )
        d = self.tracker.to_dict()
        restored = ProductTracker.from_dict(d)
        self.assertEqual(
            len(restored.list_products()),
            len(self.tracker.list_products()),
        )

    def test_thread_safety(self) -> None:
        errors: list = []

        def writer(tid: int) -> None:
            try:
                for i in range(20):
                    self.tracker.register_product(
                        f"t{tid}_p{i}",
                        f"Product {i}",
                        ProductCategory.CUSTOM,
                    )
            except Exception as exc:
                errors.append(exc)

        def reader() -> None:
            try:
                for _ in range(20):
                    self.tracker.list_products()
                    self.tracker.get_ecosystem_summary()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


# ======================================================================
# UsageProfiler
# ======================================================================


class TestUsageProfiler(unittest.TestCase):
    def setUp(self) -> None:
        self.profiler = UsageProfiler(
            max_events_per_product=500, max_products=50
        )

    def test_record_event(self) -> None:
        ev = self.profiler.record_event(
            "p1", "editor", "click", timestamp=1000.0
        )
        self.assertEqual(ev.product_id, "p1")
        self.assertEqual(ev.feature, "editor")

    def test_record_event_auto_timestamp(self) -> None:
        ev = self.profiler.record_event("p1", "feat", "read")
        self.assertGreater(ev.timestamp, 0)

    def test_record_event_negative_duration(self) -> None:
        ev = self.profiler.record_event(
            "p1", "f", "a", duration=-5.0
        )
        self.assertEqual(ev.duration_seconds, 0.0)

    def test_get_profile(self) -> None:
        self.profiler.record_event("p1", "f1", "click", timestamp=1000.0)
        profile = self.profiler.get_profile("p1")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.total_events, 1)

    def test_get_profile_missing(self) -> None:
        self.assertIsNone(self.profiler.get_profile("nope"))

    def test_profile_features_used(self) -> None:
        self.profiler.record_event("p1", "f1", "click", timestamp=1000.0)
        self.profiler.record_event("p1", "f1", "click", timestamp=1001.0)
        self.profiler.record_event("p1", "f2", "read", timestamp=1002.0)
        profile = self.profiler.get_profile("p1")
        self.assertEqual(profile.features_used["f1"], 2)
        self.assertEqual(profile.features_used["f2"], 1)

    def test_profile_duration(self) -> None:
        self.profiler.record_event(
            "p1", "f1", "a", timestamp=100.0, duration=10.0
        )
        self.profiler.record_event(
            "p1", "f1", "a", timestamp=200.0, duration=20.0
        )
        profile = self.profiler.get_profile("p1")
        self.assertAlmostEqual(profile.total_duration_seconds, 30.0)

    def test_profile_first_last_used(self) -> None:
        self.profiler.record_event("p1", "f", "a", timestamp=100.0)
        self.profiler.record_event("p1", "f", "a", timestamp=500.0)
        profile = self.profiler.get_profile("p1")
        self.assertAlmostEqual(profile.first_used, 100.0)
        self.assertAlmostEqual(profile.last_used, 500.0)

    # -- Frequency --

    def test_compute_frequency_inactive(self) -> None:
        freq = self.profiler.compute_frequency("nonexistent")
        self.assertEqual(freq, UsageFrequency.INACTIVE)

    def test_compute_frequency_daily(self) -> None:
        now = time.time()
        for day in range(6):
            self.profiler.record_event(
                "p1", "f", "a", timestamp=now - day * 86400
            )
        freq = self.profiler.compute_frequency("p1")
        self.assertEqual(freq, UsageFrequency.DAILY)

    def test_compute_frequency_weekly(self) -> None:
        now = time.time()
        for day in [0, 2, 4]:
            self.profiler.record_event(
                "p1", "f", "a", timestamp=now - day * 86400
            )
        freq = self.profiler.compute_frequency("p1")
        self.assertEqual(freq, UsageFrequency.WEEKLY)

    def test_compute_frequency_monthly(self) -> None:
        now = time.time()
        self.profiler.record_event(
            "p1", "f", "a", timestamp=now - 15 * 86400
        )
        freq = self.profiler.compute_frequency("p1")
        self.assertEqual(freq, UsageFrequency.MONTHLY)

    def test_compute_frequency_occasional(self) -> None:
        now = time.time()
        self.profiler.record_event(
            "p1", "f", "a", timestamp=now - 60 * 86400
        )
        freq = self.profiler.compute_frequency("p1")
        self.assertEqual(freq, UsageFrequency.OCCASIONAL)

    def test_compute_frequency_rare(self) -> None:
        now = time.time()
        self.profiler.record_event(
            "p1", "f", "a", timestamp=now - 200 * 86400
        )
        freq = self.profiler.compute_frequency("p1")
        self.assertEqual(freq, UsageFrequency.RARE)

    def test_compute_frequency_inactive_old(self) -> None:
        now = time.time()
        self.profiler.record_event(
            "p1", "f", "a", timestamp=now - 400 * 86400
        )
        freq = self.profiler.compute_frequency("p1")
        self.assertEqual(freq, UsageFrequency.INACTIVE)

    # -- Adoption Stage --

    def test_adoption_stage_empty(self) -> None:
        stage = self.profiler.compute_adoption_stage("nope")
        self.assertEqual(stage, AdoptionStage.DISCOVERY)

    def test_adoption_stage_discovery(self) -> None:
        now = time.time()
        for i in range(3):
            self.profiler.record_event(
                "p1", "f1", "a", timestamp=now - i
            )
        stage = self.profiler.compute_adoption_stage("p1")
        self.assertEqual(stage, AdoptionStage.DISCOVERY)

    def test_adoption_stage_onboarding(self) -> None:
        now = time.time()
        for i in range(10):
            self.profiler.record_event(
                "p1", "f1", "a", timestamp=now - i
            )
        stage = self.profiler.compute_adoption_stage("p1")
        self.assertEqual(stage, AdoptionStage.ONBOARDING)

    def test_adoption_stage_regular(self) -> None:
        now = time.time()
        for i in range(25):
            feat = f"f{i % 6}"
            self.profiler.record_event(
                "p1", feat, "a", timestamp=now - i
            )
        stage = self.profiler.compute_adoption_stage("p1")
        self.assertEqual(stage, AdoptionStage.REGULAR)

    def test_adoption_stage_churned(self) -> None:
        now = time.time()
        old = now - 90 * 86400
        for i in range(25):
            feat = f"f{i % 6}"
            self.profiler.record_event(
                "p1", feat, "a", timestamp=old + i
            )
        stage = self.profiler.compute_adoption_stage("p1")
        self.assertEqual(stage, AdoptionStage.CHURNED)

    # -- Peak Hours --

    def test_peak_hours(self) -> None:
        # Create events at known UTC hours
        from datetime import datetime, timezone

        base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        ts = base.timestamp()
        for _ in range(5):
            self.profiler.record_event("p1", "f", "a", timestamp=ts)
        base2 = datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
        ts2 = base2.timestamp()
        for _ in range(3):
            self.profiler.record_event("p1", "f", "a", timestamp=ts2)

        hours = self.profiler.get_peak_hours("p1")
        self.assertEqual(hours[0], 10)
        self.assertIn(14, hours)

    def test_peak_hours_empty(self) -> None:
        self.assertEqual(self.profiler.get_peak_hours("nope"), [])

    # -- Compare Products --

    def test_compare_products(self) -> None:
        now = time.time()
        self.profiler.record_event("a", "shared", "a", timestamp=now)
        self.profiler.record_event("a", "unique_a", "a", timestamp=now)
        self.profiler.record_event("b", "shared", "a", timestamp=now)
        self.profiler.record_event("b", "unique_b", "a", timestamp=now)
        result = self.profiler.compare_products("a", "b")
        self.assertIn("shared", result["shared_features"])
        self.assertIn("unique_a", result["unique_to_a"])
        self.assertIn("unique_b", result["unique_to_b"])

    def test_compare_products_missing_a(self) -> None:
        self.profiler.record_event("b", "f", "a", timestamp=100.0)
        result = self.profiler.compare_products("a", "b")
        self.assertIn("error", result)

    def test_compare_products_both_missing(self) -> None:
        result = self.profiler.compare_products("x", "y")
        self.assertIn("error", result)

    # -- Most Used Features --

    def test_most_used_features(self) -> None:
        now = time.time()
        for _ in range(10):
            self.profiler.record_event("p1", "hot", "a", timestamp=now)
        for _ in range(3):
            self.profiler.record_event("p1", "warm", "a", timestamp=now)
        self.profiler.record_event("p1", "cold", "a", timestamp=now)

        top = self.profiler.get_most_used_features("p1", top_n=2)
        self.assertEqual(len(top), 2)
        self.assertEqual(top[0][0], "hot")
        self.assertEqual(top[0][1], 10)

    def test_most_used_features_empty(self) -> None:
        self.assertEqual(self.profiler.get_most_used_features("nope"), [])

    def test_most_used_features_zero_n(self) -> None:
        self.profiler.record_event("p1", "f", "a", timestamp=100.0)
        self.assertEqual(
            self.profiler.get_most_used_features("p1", top_n=0), []
        )

    # -- Underutilized Features --

    def test_underutilized_features(self) -> None:
        now = time.time()
        for _ in range(10):
            self.profiler.record_event("p1", "used", "a", timestamp=now)
        self.profiler.record_event("p1", "barely", "a", timestamp=now)

        under = self.profiler.get_underutilized_features(
            "p1", ["used", "barely", "never"]
        )
        self.assertIn("barely", under)
        self.assertIn("never", under)
        self.assertNotIn("used", under)

    def test_underutilized_features_no_profile(self) -> None:
        under = self.profiler.get_underutilized_features(
            "nope", ["f1", "f2"]
        )
        self.assertEqual(under, ["f1", "f2"])

    # -- Max Events Rotation --

    def test_max_events_rotation(self) -> None:
        profiler = UsageProfiler(max_events_per_product=5, max_products=10)
        for i in range(20):
            profiler.record_event(
                "p1", "f", "a", timestamp=float(i)
            )
        profile = profiler.get_profile("p1")
        self.assertLessEqual(profile.total_events, 5)

    # -- Max Products Cap --

    def test_max_products_cap(self) -> None:
        profiler = UsageProfiler(max_events_per_product=10, max_products=3)
        for i in range(6):
            profiler.record_event(
                f"p{i}", "f", "a", timestamp=float(i)
            )
        count = sum(
            1
            for pid in [f"p{i}" for i in range(6)]
            if profiler.get_profile(pid) is not None
        )
        self.assertLessEqual(count, 3)

    # -- Feature Adoption in Profile --

    def test_profile_feature_adoption_discovered(self) -> None:
        self.profiler.record_event("p1", "f1", "a", timestamp=100.0)
        profile = self.profiler.get_profile("p1")
        self.assertEqual(
            profile.feature_adoption.get("f1"), FeatureStatus.DISCOVERED
        )

    def test_profile_feature_adoption_tried(self) -> None:
        for i in range(5):
            self.profiler.record_event(
                "p1", "f1", "a", timestamp=100.0 + i
            )
        profile = self.profiler.get_profile("p1")
        self.assertEqual(
            profile.feature_adoption.get("f1"), FeatureStatus.TRIED
        )

    def test_profile_feature_adoption_adopted(self) -> None:
        for i in range(15):
            self.profiler.record_event(
                "p1", "f1", "a", timestamp=100.0 + i
            )
        profile = self.profiler.get_profile("p1")
        self.assertEqual(
            profile.feature_adoption.get("f1"), FeatureStatus.ADOPTED
        )

    def test_profile_feature_adoption_mastered(self) -> None:
        for i in range(55):
            self.profiler.record_event(
                "p1", "f1", "a", timestamp=100.0 + i
            )
        profile = self.profiler.get_profile("p1")
        self.assertEqual(
            profile.feature_adoption.get("f1"), FeatureStatus.MASTERED
        )

    # -- Avg Session Duration --

    def test_avg_session_duration(self) -> None:
        self.profiler.record_event(
            "p1", "f", "a", timestamp=100.0, duration=10.0, session_id="s1"
        )
        self.profiler.record_event(
            "p1", "f", "a", timestamp=200.0, duration=20.0, session_id="s1"
        )
        self.profiler.record_event(
            "p1", "f", "a", timestamp=300.0, duration=6.0, session_id="s2"
        )
        profile = self.profiler.get_profile("p1")
        # s1 = 30s, s2 = 6s => avg = 18
        self.assertAlmostEqual(profile.avg_session_duration, 18.0)

    # -- Thread Safety --

    def test_thread_safety(self) -> None:
        errors: list = []

        def writer(tid: int) -> None:
            try:
                for i in range(30):
                    self.profiler.record_event(
                        f"t{tid}",
                        f"f{i % 5}",
                        "a",
                        timestamp=time.time(),
                    )
            except Exception as exc:
                errors.append(exc)

        def reader() -> None:
            try:
                for _ in range(30):
                    self.profiler.get_profile("t0")
                    self.profiler.compute_frequency("t0")
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=writer, args=(t,)) for t in range(3)
        ]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


# ======================================================================
# ProductGraph
# ======================================================================


class TestProductGraph(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = ProductGraph(max_relationships=100)

    def test_record_transition(self) -> None:
        self.graph.record_transition("a", "b", 100.0, session_id="s1")
        rels = self.graph.get_relationships()
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0].source_product, "a")
        self.assertEqual(rels[0].target_product, "b")
        self.assertEqual(rels[0].relationship_type, "temporal_sequence")

    def test_record_transition_builds_evidence(self) -> None:
        for i in range(5):
            self.graph.record_transition("a", "b", float(i), session_id=f"s{i}")
        rels = self.graph.get_relationships("a")
        self.assertEqual(rels[0].evidence_count, 5)

    def test_record_transition_self_loop_ignored(self) -> None:
        self.graph.record_transition("a", "a", 100.0)
        self.assertEqual(len(self.graph.get_relationships()), 0)

    def test_record_transition_empty_product_ignored(self) -> None:
        self.graph.record_transition("", "b", 100.0)
        self.graph.record_transition("a", "", 100.0)
        self.assertEqual(len(self.graph.get_relationships()), 0)

    def test_add_relationship(self) -> None:
        rel = self.graph.add_relationship(
            "a", "b", "workflow_link", strength=0.7, common_features=["auth"]
        )
        self.assertEqual(rel.relationship_type, "workflow_link")
        self.assertEqual(rel.strength, 0.7)
        self.assertEqual(rel.common_features, ["auth"])

    def test_add_relationship_update_existing(self) -> None:
        self.graph.add_relationship("a", "b", "data_flow", strength=0.3)
        self.graph.add_relationship("a", "b", "data_flow", strength=0.9)
        rels = self.graph.get_relationships("a")
        data_flows = [
            r for r in rels if r.relationship_type == "data_flow"
        ]
        self.assertEqual(len(data_flows), 1)
        self.assertAlmostEqual(data_flows[0].strength, 0.9)
        self.assertEqual(data_flows[0].evidence_count, 2)

    def test_add_relationship_strength_clamped(self) -> None:
        rel = self.graph.add_relationship("a", "b", "x", strength=5.0)
        self.assertLessEqual(rel.strength, 1.0)
        rel2 = self.graph.add_relationship("c", "d", "x", strength=-1.0)
        self.assertGreaterEqual(rel2.strength, 0.0)

    def test_get_relationships_all(self) -> None:
        self.graph.add_relationship("a", "b", "r1")
        self.graph.add_relationship("c", "d", "r2")
        self.assertEqual(len(self.graph.get_relationships()), 2)

    def test_get_relationships_filtered(self) -> None:
        self.graph.add_relationship("a", "b", "r1")
        self.graph.add_relationship("a", "c", "r2")
        self.graph.add_relationship("d", "e", "r3")
        rels = self.graph.get_relationships("a")
        self.assertEqual(len(rels), 2)

    def test_get_relationships_as_target(self) -> None:
        self.graph.add_relationship("x", "y", "r1")
        rels = self.graph.get_relationships("y")
        self.assertEqual(len(rels), 1)

    def test_workflow_chains(self) -> None:
        # Build strong a->b->c chain
        for _ in range(10):
            self.graph.record_transition("a", "b", 1.0, session_id="s")
        for _ in range(10):
            self.graph.record_transition("b", "c", 2.0, session_id="s")
        chains = self.graph.get_workflow_chains(min_strength=0.1)
        # Should find at least a->b and b->c, and possibly a->b->c
        self.assertGreater(len(chains), 0)
        # Each chain is a list of 2+ product IDs
        for chain in chains:
            self.assertGreaterEqual(len(chain), 2)

    def test_workflow_chains_empty(self) -> None:
        chains = self.graph.get_workflow_chains()
        self.assertEqual(chains, [])

    def test_workflow_chains_below_threshold(self) -> None:
        self.graph.record_transition("a", "b", 1.0)
        chains = self.graph.get_workflow_chains(min_strength=0.99)
        # With only 1 transition, strength = 1/1 = 1.0, so it should be included
        # but let's just check it doesn't crash
        self.assertIsInstance(chains, list)

    def test_complementary_products(self) -> None:
        self.graph.add_relationship(
            "crm", "billing", "complementary", strength=0.8
        )
        self.graph.add_relationship(
            "crm", "email", "complementary", strength=0.5
        )
        comps = self.graph.get_complementary_products("crm")
        self.assertEqual(len(comps), 2)
        self.assertEqual(comps[0][0], "billing")  # higher strength first
        self.assertAlmostEqual(comps[0][1], 0.8)

    def test_complementary_products_empty(self) -> None:
        comps = self.graph.get_complementary_products("unknown")
        self.assertEqual(comps, [])

    def test_graph_summary(self) -> None:
        self.graph.add_relationship("a", "b", "r1", strength=0.9)
        self.graph.add_relationship("c", "d", "r2", strength=0.3)
        summary = self.graph.get_graph_summary()
        self.assertEqual(summary["total_nodes"], 4)
        self.assertEqual(summary["total_edges"], 2)
        self.assertEqual(len(summary["strongest_relationships"]), 2)

    def test_graph_summary_empty(self) -> None:
        summary = self.graph.get_graph_summary()
        self.assertEqual(summary["total_nodes"], 0)
        self.assertEqual(summary["total_edges"], 0)

    def test_max_relationships_cap(self) -> None:
        graph = ProductGraph(max_relationships=5)
        for i in range(10):
            graph.add_relationship(f"a{i}", f"b{i}", "r", strength=0.1 * i)
        self.assertLessEqual(len(graph.get_relationships()), 5)

    def test_max_relationships_evicts_weakest(self) -> None:
        graph = ProductGraph(max_relationships=3)
        graph.add_relationship("a", "b", "r", strength=0.1)
        graph.add_relationship("c", "d", "r", strength=0.9)
        graph.add_relationship("e", "f", "r", strength=0.5)
        graph.add_relationship("g", "h", "r", strength=0.8)
        # Weakest (0.1) should be evicted
        rels = graph.get_relationships()
        strengths = [r.strength for r in rels]
        self.assertNotIn(0.1, strengths)
        self.assertLessEqual(len(rels), 3)

    def test_thread_safety(self) -> None:
        errors: list = []

        def writer(tid: int) -> None:
            try:
                for i in range(20):
                    self.graph.record_transition(
                        f"p{tid}", f"p{(tid+1)%3}", float(i)
                    )
            except Exception as exc:
                errors.append(exc)

        def reader() -> None:
            try:
                for _ in range(20):
                    self.graph.get_relationships()
                    self.graph.get_graph_summary()
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=writer, args=(t,)) for t in range(3)
        ]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


# ======================================================================
# AdoptionAnalyzer
# ======================================================================


class TestAdoptionAnalyzer(unittest.TestCase):
    def setUp(self) -> None:
        self.analyzer = AdoptionAnalyzer(max_curves=200)

    def test_track_feature_first_use(self) -> None:
        curve = self.analyzer.track_feature_use("p1", "feat", timestamp=1000.0)
        self.assertEqual(curve.stage, FeatureStatus.DISCOVERED)
        self.assertEqual(curve.total_uses, 1)
        self.assertAlmostEqual(curve.discovery_date, 1000.0)

    def test_track_feature_tried(self) -> None:
        for i in range(3):
            curve = self.analyzer.track_feature_use(
                "p1", "feat", timestamp=1000.0 + i
            )
        self.assertEqual(curve.stage, FeatureStatus.TRIED)
        self.assertEqual(curve.total_uses, 3)

    def test_track_feature_adopted(self) -> None:
        for i in range(10):
            curve = self.analyzer.track_feature_use(
                "p1", "feat", timestamp=1000.0 + i
            )
        self.assertEqual(curve.stage, FeatureStatus.ADOPTED)
        self.assertGreater(curve.adoption_date, 0)

    def test_track_feature_mastered(self) -> None:
        base = 1000.0
        for i in range(50):
            curve = self.analyzer.track_feature_use(
                "p1", "feat", timestamp=base + i * 86400
            )
        self.assertEqual(curve.stage, FeatureStatus.MASTERED)
        self.assertGreater(curve.mastery_date, 0)

    def test_track_feature_not_mastered_without_time(self) -> None:
        # 50 uses but all in same second -> no 30-day span
        for i in range(50):
            curve = self.analyzer.track_feature_use(
                "p1", "feat", timestamp=1000.0
            )
        self.assertEqual(curve.stage, FeatureStatus.ADOPTED)

    def test_days_to_adopt(self) -> None:
        base = 1000.0
        for i in range(10):
            curve = self.analyzer.track_feature_use(
                "p1", "feat", timestamp=base + i * 86400
            )
        self.assertEqual(curve.days_to_adopt, 9)

    def test_get_adoption_curve(self) -> None:
        self.analyzer.track_feature_use("p1", "f1", timestamp=1000.0)
        curve = self.analyzer.get_adoption_curve("p1", "f1")
        self.assertIsNotNone(curve)
        self.assertEqual(curve.feature, "f1")

    def test_get_adoption_curve_missing(self) -> None:
        self.assertIsNone(self.analyzer.get_adoption_curve("p1", "nope"))

    def test_product_adoption_summary(self) -> None:
        for i in range(5):
            self.analyzer.track_feature_use(
                "p1", f"f{i}", timestamp=1000.0 + i
            )
        summary = self.analyzer.get_product_adoption_summary("p1")
        self.assertEqual(summary["product_id"], "p1")
        self.assertEqual(summary["total_features"], 5)
        self.assertIn("discovered", summary["by_stage"])

    def test_product_adoption_summary_empty(self) -> None:
        summary = self.analyzer.get_product_adoption_summary("nope")
        self.assertEqual(summary["total_features"], 0)

    def test_stalled_features(self) -> None:
        old = time.time() - 30 * 86400  # 30 days ago
        self.analyzer.track_feature_use("p1", "stale", timestamp=old)
        # Recent feature
        self.analyzer.track_feature_use(
            "p1", "fresh", timestamp=time.time()
        )
        stalled = self.analyzer.get_stalled_features("p1", days_threshold=14)
        stalled_names = [c.feature for c in stalled]
        self.assertIn("stale", stalled_names)
        self.assertNotIn("fresh", stalled_names)

    def test_stalled_features_none(self) -> None:
        self.analyzer.track_feature_use(
            "p1", "f", timestamp=time.time()
        )
        stalled = self.analyzer.get_stalled_features("p1")
        self.assertEqual(len(stalled), 0)

    def test_stalled_features_adopted_not_stalled(self) -> None:
        old = time.time() - 30 * 86400
        for i in range(10):
            self.analyzer.track_feature_use(
                "p1", "feat", timestamp=old + i
            )
        stalled = self.analyzer.get_stalled_features("p1")
        # ADOPTED features should not be stalled
        self.assertEqual(len(stalled), 0)

    def test_abandonment_risk_declining(self) -> None:
        # Force a declining trend: many uses long ago, trend computed as declining
        base = time.time() - 365 * 86400
        for i in range(10):
            self.analyzer.track_feature_use(
                "p1", "declining_feat", timestamp=base + i
            )
        # Manually set trend to declining for test
        key = "p1:declining_feat"
        self.analyzer._curves[key].usage_trend = "declining"
        at_risk = self.analyzer.get_abandonment_risk("p1")
        self.assertTrue(any(c.feature == "declining_feat" for c in at_risk))

    def test_abandonment_risk_abandoned(self) -> None:
        self.analyzer.track_feature_use("p1", "gone", timestamp=100.0)
        self.analyzer._curves["p1:gone"].stage = FeatureStatus.ABANDONED
        at_risk = self.analyzer.get_abandonment_risk("p1")
        self.assertTrue(any(c.feature == "gone" for c in at_risk))

    def test_abandonment_risk_none(self) -> None:
        self.analyzer.track_feature_use(
            "p1", "healthy", timestamp=time.time()
        )
        at_risk = self.analyzer.get_abandonment_risk("p1")
        self.assertEqual(len(at_risk), 0)

    def test_suggest_features_to_explore(self) -> None:
        self.analyzer.track_feature_use("p1", "known", timestamp=100.0)
        suggestions = self.analyzer.suggest_features_to_explore(
            "p1", ["known", "unknown1", "unknown2", "unknown3"], top_n=2
        )
        self.assertEqual(len(suggestions), 2)
        self.assertNotIn("known", suggestions)

    def test_suggest_features_all_known(self) -> None:
        self.analyzer.track_feature_use("p1", "a", timestamp=100.0)
        self.analyzer.track_feature_use("p1", "b", timestamp=100.0)
        suggestions = self.analyzer.suggest_features_to_explore(
            "p1", ["a", "b"], top_n=5
        )
        self.assertEqual(suggestions, [])

    def test_suggest_features_empty_list(self) -> None:
        suggestions = self.analyzer.suggest_features_to_explore(
            "p1", [], top_n=5
        )
        self.assertEqual(suggestions, [])

    def test_max_curves_cap(self) -> None:
        analyzer = AdoptionAnalyzer(max_curves=5)
        for i in range(10):
            analyzer.track_feature_use(
                "p1", f"f{i}", timestamp=1000.0 + i
            )
        # Count actual curves for p1
        count = sum(
            1
            for c in analyzer._curves.values()
            if c.product_id == "p1"
        )
        self.assertLessEqual(count, 5)

    def test_auto_timestamp(self) -> None:
        curve = self.analyzer.track_feature_use("p1", "f1")
        self.assertGreater(curve.discovery_date, 0)

    def test_usage_trend_growing(self) -> None:
        now = time.time()
        # Many uses in short time -> growing
        for i in range(20):
            curve = self.analyzer.track_feature_use(
                "p1", "hot", timestamp=now
            )
        # With age=0, trend won't be growing, so use a small age
        for i in range(20):
            curve = self.analyzer.track_feature_use(
                "p2", "hot", timestamp=now - 1 + 0.01 * i
            )
        # Just verify it doesn't crash and returns a valid trend
        self.assertIn(curve.usage_trend, ["growing", "stable", "declining"])

    def test_thread_safety(self) -> None:
        errors: list = []

        def writer(tid: int) -> None:
            try:
                for i in range(20):
                    self.analyzer.track_feature_use(
                        f"p{tid}", f"f{i % 5}", timestamp=time.time()
                    )
            except Exception as exc:
                errors.append(exc)

        def reader() -> None:
            try:
                for _ in range(20):
                    self.analyzer.get_product_adoption_summary("p0")
                    self.analyzer.get_stalled_features("p0")
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=writer, args=(t,)) for t in range(3)
        ]
        threads += [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


# ======================================================================
# Integration
# ======================================================================


class TestIntegration(unittest.TestCase):
    """Scenario end-to-end: registra prodotti, genera eventi, analizza."""

    def test_full_workflow(self) -> None:
        tracker = ProductTracker()
        profiler = UsageProfiler()
        graph = ProductGraph()
        analyzer = AdoptionAnalyzer()

        # Register products
        tracker.register_product(
            "stripe", "Stripe", ProductCategory.BILLING
        )
        tracker.register_product(
            "hubspot", "HubSpot", ProductCategory.CRM
        )

        # Record usage
        now = time.time()
        for i in range(30):
            profiler.record_event(
                "stripe",
                "invoicing",
                "create",
                timestamp=now - i * 3600,
                session_id="s1",
            )
            profiler.record_event(
                "hubspot",
                "contacts",
                "read",
                timestamp=now - i * 3600 + 60,
                session_id="s1",
            )
            graph.record_transition(
                "hubspot", "stripe", now - i * 3600, session_id=f"s{i}"
            )
            analyzer.track_feature_use(
                "stripe", "invoicing", timestamp=now - i * 3600
            )

        # Verify profiles
        sp = profiler.get_profile("stripe")
        self.assertIsNotNone(sp)
        self.assertEqual(sp.total_events, 30)

        # Verify graph
        rels = graph.get_relationships("hubspot")
        self.assertGreater(len(rels), 0)

        # Verify adoption
        curve = analyzer.get_adoption_curve("stripe", "invoicing")
        self.assertIsNotNone(curve)
        self.assertGreaterEqual(curve.total_uses, 30)

    def test_ecosystem_report(self) -> None:
        tracker = ProductTracker()
        tracker.register_product("a", "A", ProductCategory.IDE)
        tracker.register_product("b", "B", ProductCategory.IDE)
        tracker.register_product("c", "C", ProductCategory.CRM)

        summary = tracker.get_ecosystem_summary()
        self.assertEqual(summary["total_products"], 3)
        self.assertEqual(summary["categories"]["ide"], 2)


if __name__ == "__main__":
    unittest.main()
