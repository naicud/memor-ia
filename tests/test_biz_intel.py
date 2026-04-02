"""Comprehensive tests for the biz_intel module."""

from __future__ import annotations

import threading
import time

import pytest

from memoria.biz_intel import (
    LifecyclePosition,
    LifecycleStage,
    LifecycleTracker,
    RevenueSignal,
    RevenueSignals,
    RevenueSignalType,
    SegmentClassifier,
    SegmentType,
    UserSegment,
    ValueScore,
    ValueScorer,
    ValueTier,
)


# ──────────────────────────────────────────────────────────────
# RevenueSignals
# ──────────────────────────────────────────────────────────────

class TestRevenueSignalsInit:
    def test_default_init(self):
        rs = RevenueSignals()
        assert rs._max_signals == 5000
        assert rs._signals == []
        assert rs._rules == {}

    def test_custom_max_signals(self):
        rs = RevenueSignals(max_signals=10)
        assert rs._max_signals == 10

    def test_min_max_signals_clamped(self):
        rs = RevenueSignals(max_signals=0)
        assert rs._max_signals == 1


class TestRevenueSignalsAddRule:
    def test_add_single_rule(self):
        rs = RevenueSignals()
        rs.add_rule(
            "upsell_premium",
            RevenueSignalType.UPSELL_OPPORTUNITY,
            ["premium", "upgrade", "plan"],
            "User shows interest in premium features",
            "Offer premium trial",
            min_impact=0.7,
        )
        assert "upsell_premium" in rs._rules
        assert rs._rules["upsell_premium"]["signal_type"] == RevenueSignalType.UPSELL_OPPORTUNITY

    def test_add_multiple_rules(self):
        rs = RevenueSignals()
        rs.add_rule("r1", RevenueSignalType.CHURN_RISK, ["cancel"], "Churn", "Retain")
        rs.add_rule("r2", RevenueSignalType.EXPANSION_SIGNAL, ["grow"], "Expand", "Upsell")
        assert len(rs._rules) == 2

    def test_overwrite_rule(self):
        rs = RevenueSignals()
        rs.add_rule("r1", RevenueSignalType.CHURN_RISK, ["cancel"], "v1", "Retain")
        rs.add_rule("r1", RevenueSignalType.EXPANSION_SIGNAL, ["grow"], "v2", "Upsell")
        assert rs._rules["r1"]["signal_type"] == RevenueSignalType.EXPANSION_SIGNAL

    def test_min_impact_clamped(self):
        rs = RevenueSignals()
        rs.add_rule("r1", RevenueSignalType.CHURN_RISK, ["x"], "d", "a", min_impact=2.0)
        assert rs._rules["r1"]["min_impact"] == 1.0


class TestRevenueSignalsEvaluateEvent:
    def test_event_matches_rule(self):
        rs = RevenueSignals()
        rs.add_rule(
            "churn",
            RevenueSignalType.CHURN_RISK,
            ["cancel", "unsubscribe", "stop"],
            "Churn risk detected",
            "Offer discount",
        )
        signals = rs.evaluate_event("prod_1", {"action": "cancel subscription", "reason": "too expensive"})
        assert len(signals) == 1
        assert signals[0].signal_type == RevenueSignalType.CHURN_RISK
        assert signals[0].product_id == "prod_1"
        assert signals[0].confidence > 0.0

    def test_event_no_match(self):
        rs = RevenueSignals()
        rs.add_rule(
            "churn",
            RevenueSignalType.CHURN_RISK,
            ["cancel", "unsubscribe", "stop"],
            "Churn risk",
            "Retain",
        )
        signals = rs.evaluate_event("prod_1", {"action": "login", "feature": "dashboard"})
        assert len(signals) == 0

    def test_event_low_confidence_filtered(self):
        rs = RevenueSignals()
        rs.add_rule(
            "churn",
            RevenueSignalType.CHURN_RISK,
            ["cancel", "unsubscribe", "stop", "delete", "remove", "end"],
            "Churn risk",
            "Retain",
        )
        # Only 1 out of 6 keywords matches → confidence ~0.167 < 0.3
        signals = rs.evaluate_event("prod_1", {"action": "cancel"})
        assert len(signals) == 0

    def test_event_matches_multiple_rules(self):
        rs = RevenueSignals()
        rs.add_rule("r1", RevenueSignalType.CHURN_RISK, ["cancel", "stop"], "Churn", "Retain")
        rs.add_rule("r2", RevenueSignalType.CONTRACTION_SIGNAL, ["cancel", "downgrade"], "Contract", "Save")
        signals = rs.evaluate_event("prod_1", {"action": "cancel and downgrade"})
        assert len(signals) == 2

    def test_event_empty_keywords_skipped(self):
        rs = RevenueSignals()
        rs.add_rule("r1", RevenueSignalType.CHURN_RISK, [], "Churn", "Retain")
        signals = rs.evaluate_event("prod_1", {"action": "cancel"})
        assert len(signals) == 0

    def test_evaluate_event_stores_signals(self):
        rs = RevenueSignals()
        rs.add_rule("r1", RevenueSignalType.CHURN_RISK, ["cancel"], "Churn", "Retain")
        rs.evaluate_event("prod_1", {"action": "cancel"})
        assert len(rs._signals) == 1

    def test_signal_has_evidence(self):
        rs = RevenueSignals()
        rs.add_rule("r1", RevenueSignalType.CHURN_RISK, ["cancel", "stop"], "Churn", "Retain")
        signals = rs.evaluate_event("prod_1", {"action": "cancel and stop"})
        assert "rule:r1" in signals[0].evidence
        assert "cancel" in signals[0].evidence


class TestRevenueSignalsAddManual:
    def test_add_manual_signal(self):
        rs = RevenueSignals()
        s = rs.add_signal(
            RevenueSignalType.ADVOCACY_SIGNAL,
            "prod_x",
            "User referred 3 friends",
            impact=0.9,
            confidence=0.95,
            evidence=["referral_count:3"],
            action="Send reward",
        )
        assert s.signal_type == RevenueSignalType.ADVOCACY_SIGNAL
        assert s.impact_score == 0.9
        assert s.recommended_action == "Send reward"
        assert len(rs._signals) == 1

    def test_add_manual_defaults(self):
        rs = RevenueSignals()
        s = rs.add_signal(RevenueSignalType.CHURN_RISK, "p1", "risk")
        assert s.impact_score == 0.5
        assert s.confidence == 0.5
        assert s.evidence == []

    def test_impact_clamped(self):
        rs = RevenueSignals()
        s = rs.add_signal(RevenueSignalType.CHURN_RISK, "p1", "risk", impact=5.0, confidence=-1.0)
        assert s.impact_score == 1.0
        assert s.confidence == 0.0

    def test_signal_has_id(self):
        rs = RevenueSignals()
        s = rs.add_signal(RevenueSignalType.CHURN_RISK, "p1", "risk")
        assert len(s.signal_id) == 32  # uuid4().hex

    def test_signal_has_timestamp(self):
        rs = RevenueSignals()
        before = time.time()
        s = rs.add_signal(RevenueSignalType.CHURN_RISK, "p1", "risk")
        assert s.timestamp >= before


class TestRevenueSignalsGetFiltered:
    def setup_method(self):
        self.rs = RevenueSignals()
        self.rs.add_signal(RevenueSignalType.CHURN_RISK, "p1", "churn1", impact=0.3)
        self.rs.add_signal(RevenueSignalType.CHURN_RISK, "p2", "churn2", impact=0.7)
        self.rs.add_signal(RevenueSignalType.UPSELL_OPPORTUNITY, "p1", "upsell", impact=0.9)
        self.rs.add_signal(RevenueSignalType.EXPANSION_SIGNAL, "p3", "expand", impact=0.5)

    def test_get_all(self):
        assert len(self.rs.get_signals()) == 4

    def test_filter_by_type(self):
        result = self.rs.get_signals(signal_type=RevenueSignalType.CHURN_RISK)
        assert len(result) == 2

    def test_filter_by_product(self):
        result = self.rs.get_signals(product_id="p1")
        assert len(result) == 2

    def test_filter_by_min_impact(self):
        result = self.rs.get_signals(min_impact=0.6)
        assert len(result) == 2

    def test_combined_filters(self):
        result = self.rs.get_signals(signal_type=RevenueSignalType.CHURN_RISK, product_id="p1")
        assert len(result) == 1

    def test_limit(self):
        result = self.rs.get_signals(limit=2)
        assert len(result) == 2

    def test_empty_result(self):
        result = self.rs.get_signals(signal_type=RevenueSignalType.RENEWAL_RISK)
        assert len(result) == 0


class TestRevenueSignalsTopOpportunities:
    def test_top_opportunities_sorted(self):
        rs = RevenueSignals()
        rs.add_signal(RevenueSignalType.CHURN_RISK, "p1", "low", impact=0.2, confidence=0.2)
        rs.add_signal(RevenueSignalType.UPSELL_OPPORTUNITY, "p2", "high", impact=0.9, confidence=0.9)
        rs.add_signal(RevenueSignalType.EXPANSION_SIGNAL, "p3", "mid", impact=0.5, confidence=0.5)
        top = rs.get_top_opportunities(top_n=2)
        assert len(top) == 2
        assert top[0].description == "high"

    def test_top_empty(self):
        rs = RevenueSignals()
        assert rs.get_top_opportunities() == []


class TestRevenueSignalsSummary:
    def test_summary_with_signals(self):
        rs = RevenueSignals()
        rs.add_signal(RevenueSignalType.CHURN_RISK, "p1", "d1", impact=0.4)
        rs.add_signal(RevenueSignalType.CHURN_RISK, "p2", "d2", impact=0.6)
        rs.add_signal(RevenueSignalType.UPSELL_OPPORTUNITY, "p1", "d3", impact=0.8)
        summary = rs.get_signal_summary()
        assert summary["total_signals"] == 3
        assert summary["by_type"]["churn_risk"] == 2
        assert summary["by_type"]["upsell_opportunity"] == 1
        assert summary["avg_impact"] == pytest.approx(0.6, abs=0.01)
        assert "p1" in summary["top_products"]

    def test_summary_empty(self):
        rs = RevenueSignals()
        summary = rs.get_signal_summary()
        assert summary["total_signals"] == 0
        assert summary["avg_impact"] == 0.0


class TestRevenueSignalsMaxCap:
    def test_signals_capped(self):
        rs = RevenueSignals(max_signals=5)
        for i in range(10):
            rs.add_signal(RevenueSignalType.CHURN_RISK, f"p{i}", f"d{i}")
        assert len(rs._signals) == 5
        assert rs._signals[-1].product_id == "p9"

    def test_cap_via_evaluate(self):
        rs = RevenueSignals(max_signals=3)
        rs.add_rule("r1", RevenueSignalType.CHURN_RISK, ["x"], "d", "a")
        for i in range(5):
            rs.evaluate_event(f"p{i}", {"action": "x"})
        assert len(rs._signals) <= 3


# ──────────────────────────────────────────────────────────────
# SegmentClassifier
# ──────────────────────────────────────────────────────────────

class TestSegmentClassifierInit:
    def test_default_init(self):
        sc = SegmentClassifier()
        assert sc._current_segment is None
        assert sc._segment_history == []
        assert sc._metrics == {}

    def test_no_current_segment(self):
        sc = SegmentClassifier()
        assert sc.get_current_segment() is None


class TestSegmentClassifierUpdateMetrics:
    def test_update_single_metric(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=0.75)
        assert sc._metrics["engagement_score"] == 0.75

    def test_update_multiple_metrics(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=0.5, active_days=30, features_used=10)
        assert len(sc._metrics) == 3

    def test_update_overwrites(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=0.5)
        sc.update_metrics(engagement_score=0.9)
        assert sc._metrics["engagement_score"] == 0.9


class TestSegmentClassifierClassify:
    def test_classify_champion(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=0.85, advocacy_actions=10, active_days=120)
        seg = sc.classify()
        assert seg.segment_type == SegmentType.CHAMPION
        assert seg.confidence > 0.0

    def test_classify_power_user(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=0.75, features_used=20, active_days=60)
        seg = sc.classify()
        assert seg.segment_type == SegmentType.POWER_USER

    def test_classify_regular(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=0.5, active_days=20)
        seg = sc.classify()
        assert seg.segment_type == SegmentType.REGULAR

    def test_classify_casual(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=0.25, active_days=5)
        seg = sc.classify()
        assert seg.segment_type == SegmentType.CASUAL

    def test_classify_new_user(self):
        sc = SegmentClassifier()
        sc.update_metrics(days_since_signup=5, engagement_score=0.1, active_days=1)
        seg = sc.classify()
        assert seg.segment_type == SegmentType.NEW_USER

    def test_classify_dormant(self):
        sc = SegmentClassifier()
        sc.update_metrics(active_days=0, days_since_signup=60, total_events=0)
        seg = sc.classify()
        assert seg.segment_type == SegmentType.DORMANT

    def test_classify_at_risk(self):
        sc = SegmentClassifier()
        # First become REGULAR
        sc.update_metrics(engagement_score=0.5, active_days=20)
        sc.classify()
        # Then engagement drops
        sc.update_metrics(engagement_score=0.1)
        seg = sc.classify()
        assert seg.segment_type == SegmentType.AT_RISK

    def test_classify_at_risk_from_champion(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=0.85, advocacy_actions=10, active_days=120)
        sc.classify()
        sc.update_metrics(engagement_score=0.2)
        seg = sc.classify()
        assert seg.segment_type == SegmentType.AT_RISK

    def test_classify_at_risk_from_power_user(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=0.75, features_used=20, active_days=60)
        sc.classify()
        sc.update_metrics(engagement_score=0.15)
        seg = sc.classify()
        assert seg.segment_type == SegmentType.AT_RISK

    def test_classify_default_fallback(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=0.1, active_days=1, days_since_signup=30)
        seg = sc.classify()
        assert seg.segment_type == SegmentType.CASUAL
        assert seg.confidence == 0.3

    def test_classify_empty_metrics(self):
        sc = SegmentClassifier()
        seg = sc.classify()
        # days_since_signup=0 <= 14 → NEW_USER
        assert seg.segment_type == SegmentType.NEW_USER

    def test_classify_sets_current_segment(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=0.5, active_days=20)
        sc.classify()
        assert sc.get_current_segment() is not None
        assert sc.get_current_segment().segment_type == SegmentType.REGULAR

    def test_confidence_bounded(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=0.9, advocacy_actions=100, active_days=365)
        seg = sc.classify()
        assert 0.0 <= seg.confidence <= 1.0


class TestSegmentClassifierHistory:
    def test_segment_history_on_transition(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=0.5, active_days=20)
        sc.classify()
        sc.update_metrics(engagement_score=0.8, advocacy_actions=10, active_days=120)
        sc.classify()
        history = sc.get_segment_history()
        assert len(history) == 2

    def test_no_duplicate_in_history(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=0.5, active_days=20)
        sc.classify()
        sc.classify()  # same segment
        history = sc.get_segment_history()
        assert len(history) == 1

    def test_history_limit(self):
        sc = SegmentClassifier()
        history = sc.get_segment_history(limit=5)
        assert len(history) <= 5

    def test_history_max_capped(self):
        sc = SegmentClassifier()
        sc._max_history = 3
        for i in range(10):
            eng = 0.5 if i % 2 == 0 else 0.85
            act = 20 if i % 2 == 0 else 120
            adv = 0 if i % 2 == 0 else 10
            sc.update_metrics(engagement_score=eng, active_days=act, advocacy_actions=adv)
            sc.classify()
        assert len(sc._segment_history) <= 3


class TestSegmentClassifierTransitionRisk:
    def test_transition_risk_low(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=0.9, advocacy_actions=10, active_days=120)
        sc.classify()
        risk = sc.get_segment_transition_risk()
        assert risk["risk"] == "low"

    def test_transition_risk_high(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=0.1, churn_risk=0.8, active_days=20)
        sc.classify()
        risk = sc.get_segment_transition_risk()
        assert risk["risk"] == "high"

    def test_transition_risk_unknown_no_segment(self):
        sc = SegmentClassifier()
        risk = sc.get_segment_transition_risk()
        assert risk["risk"] == "unknown"

    def test_transition_risk_medium(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=0.5, churn_risk=0.6, active_days=20)
        sc.classify()
        risk = sc.get_segment_transition_risk()
        assert risk["risk"] in ("medium", "high")

    def test_transition_risk_power_user_low_engagement(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=0.75, features_used=20, active_days=60)
        sc.classify()
        sc.update_metrics(engagement_score=0.25)
        sc.classify()  # reclassify — now AT_RISK with low engagement
        risk = sc.get_segment_transition_risk()
        assert risk["probability"] > 0


class TestSegmentClassifierSummary:
    def test_summary_empty(self):
        sc = SegmentClassifier()
        summary = sc.get_segment_summary()
        assert summary["current_segment"] is None
        assert summary["confidence"] == 0.0

    def test_summary_with_data(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=0.5, active_days=20)
        sc.classify()
        summary = sc.get_segment_summary()
        assert summary["current_segment"] == "regular"
        assert summary["confidence"] > 0
        assert summary["metrics_tracked"] >= 2


# ──────────────────────────────────────────────────────────────
# LifecycleTracker
# ──────────────────────────────────────────────────────────────

class TestLifecycleTrackerInit:
    def test_default_init(self):
        lt = LifecycleTracker()
        assert lt._max_products == 50
        assert lt._positions == {}

    def test_custom_max(self):
        lt = LifecycleTracker(max_products=5)
        assert lt._max_products == 5

    def test_min_max_clamped(self):
        lt = LifecycleTracker(max_products=0)
        assert lt._max_products == 1


class TestLifecycleTrackerUpdatePosition:
    def test_prospect(self):
        lt = LifecycleTracker()
        pos = lt.update_position("p1", {"total_events": 0, "days_active": 0})
        assert pos.stage == LifecycleStage.PROSPECT

    def test_onboarding(self):
        lt = LifecycleTracker()
        pos = lt.update_position("p1", {"total_events": 10, "days_active": 3})
        assert pos.stage == LifecycleStage.ONBOARDING

    def test_adoption(self):
        lt = LifecycleTracker()
        pos = lt.update_position("p1", {"total_events": 50, "days_active": 15})
        assert pos.stage == LifecycleStage.ADOPTION

    def test_growth(self):
        lt = LifecycleTracker()
        pos = lt.update_position("p1", {
            "total_events": 150, "days_active": 40,
            "usage_trend": "growing", "engagement_score": 0.7,
        })
        assert pos.stage == LifecycleStage.GROWTH

    def test_maturity(self):
        lt = LifecycleTracker()
        pos = lt.update_position("p1", {
            "total_events": 250, "days_active": 90,
            "usage_trend": "stable", "feature_count": 50,
            "engagement_score": 0.6,
        })
        assert pos.stage == LifecycleStage.MATURITY

    def test_saturation(self):
        lt = LifecycleTracker()
        pos = lt.update_position("p1", {
            "total_events": 300, "days_active": 120,
            "usage_trend": "stable", "feature_count": 90,
            "engagement_score": 0.7,
        })
        assert pos.stage == LifecycleStage.SATURATION

    def test_decline(self):
        lt = LifecycleTracker()
        # First establish a non-prospect stage
        lt.update_position("p1", {"total_events": 100, "days_active": 30, "usage_trend": "growing"})
        pos = lt.update_position("p1", {
            "total_events": 100, "days_active": 30,
            "usage_trend": "declining", "engagement_score": 0.3,
        })
        assert pos.stage == LifecycleStage.DECLINE

    def test_reactivation(self):
        lt = LifecycleTracker()
        # Establish then decline
        lt.update_position("p1", {"total_events": 100, "days_active": 30, "usage_trend": "growing"})
        lt.update_position("p1", {"total_events": 100, "days_active": 30, "usage_trend": "declining"})
        # Now reactivate
        pos = lt.update_position("p1", {
            "total_events": 120, "days_active": 35,
            "usage_trend": "growing", "engagement_score": 0.6,
        })
        assert pos.stage == LifecycleStage.REACTIVATION

    def test_days_in_stage_increments(self):
        lt = LifecycleTracker()
        lt.update_position("p1", {"total_events": 0, "days_active": 0})
        pos = lt.update_position("p1", {"total_events": 0, "days_active": 0})
        assert pos.days_in_stage == 2

    def test_days_in_stage_resets_on_transition(self):
        lt = LifecycleTracker()
        lt.update_position("p1", {"total_events": 0, "days_active": 0})
        lt.update_position("p1", {"total_events": 0, "days_active": 0})
        pos = lt.update_position("p1", {"total_events": 10, "days_active": 3})
        assert pos.days_in_stage == 1

    def test_stage_health_computed(self):
        lt = LifecycleTracker()
        pos = lt.update_position("p1", {
            "total_events": 150, "days_active": 40,
            "usage_trend": "growing", "engagement_score": 0.8,
        })
        assert 0.0 <= pos.stage_health <= 1.0
        assert pos.stage_health > 0

    def test_progression_probability_growing(self):
        lt = LifecycleTracker()
        pos = lt.update_position("p1", {
            "total_events": 50, "days_active": 15,
            "usage_trend": "growing", "engagement_score": 0.8,
        })
        assert pos.progression_probability > 0.0

    def test_regression_probability_declining(self):
        lt = LifecycleTracker()
        lt.update_position("p1", {"total_events": 100, "days_active": 30, "usage_trend": "growing"})
        pos = lt.update_position("p1", {
            "total_events": 100, "days_active": 30,
            "usage_trend": "declining", "engagement_score": 0.2,
        })
        assert pos.regression_probability > 0.3

    def test_confidence_bounded(self):
        lt = LifecycleTracker()
        pos = lt.update_position("p1", {"total_events": 100, "days_active": 30})
        assert 0.0 <= pos.confidence <= 1.0


class TestLifecycleTrackerGetPosition:
    def test_get_existing(self):
        lt = LifecycleTracker()
        lt.update_position("p1", {"total_events": 0})
        assert lt.get_position("p1") is not None

    def test_get_nonexistent(self):
        lt = LifecycleTracker()
        assert lt.get_position("p_none") is None

    def test_get_all_positions(self):
        lt = LifecycleTracker()
        lt.update_position("p1", {"total_events": 0})
        lt.update_position("p2", {"total_events": 10, "days_active": 3})
        assert len(lt.get_all_positions()) == 2


class TestLifecycleTrackerMaxProducts:
    def test_evicts_when_full(self):
        lt = LifecycleTracker(max_products=3)
        for i in range(5):
            lt.update_position(f"p{i}", {"total_events": i * 10, "days_active": i})
        assert len(lt._positions) == 3


class TestLifecycleTrackerStageDuration:
    def test_stage_duration_empty(self):
        lt = LifecycleTracker()
        assert lt.get_stage_duration("p_none") == {}

    def test_stage_duration_has_value(self):
        lt = LifecycleTracker()
        lt.update_position("p1", {"total_events": 0})
        durations = lt.get_stage_duration("p1")
        assert "prospect" in durations
        assert durations["prospect"] >= 0

    def test_stage_duration_multiple_stages(self):
        lt = LifecycleTracker()
        lt.update_position("p1", {"total_events": 0})
        lt.update_position("p1", {"total_events": 10, "days_active": 3})
        durations = lt.get_stage_duration("p1")
        assert len(durations) >= 1


class TestLifecycleTrackerSummary:
    def test_summary_empty(self):
        lt = LifecycleTracker()
        summary = lt.get_lifecycle_summary()
        assert summary["total_products"] == 0

    def test_summary_with_data(self):
        lt = LifecycleTracker()
        lt.update_position("p1", {"total_events": 0})
        lt.update_position("p2", {"total_events": 100, "days_active": 30, "usage_trend": "growing"})
        summary = lt.get_lifecycle_summary()
        assert summary["total_products"] == 2
        assert len(summary["by_stage"]) >= 1
        assert summary["avg_days_per_stage"] >= 0


# ──────────────────────────────────────────────────────────────
# ValueScorer
# ──────────────────────────────────────────────────────────────

class TestValueScorerInit:
    def test_default_init(self):
        vs = ValueScorer()
        assert vs._max_products == 50
        assert vs._scores == {}
        assert abs(sum(vs._weights.values()) - 1.0) < 0.01

    def test_custom_max(self):
        vs = ValueScorer(max_products=5)
        assert vs._max_products == 5

    def test_min_max_clamped(self):
        vs = ValueScorer(max_products=0)
        assert vs._max_products == 1


class TestValueScorerUpdateScore:
    def test_update_creates_score(self):
        vs = ValueScorer()
        score = vs.update_score("p1", engagement=0.8, adoption=0.7, retention=0.6, advocacy=0.5)
        assert score.product_id == "p1"
        assert score.engagement_score == 0.8
        assert score.adoption_score == 0.7
        assert score.retention_score == 0.6
        assert score.advocacy_score == 0.5

    def test_overall_value_computed(self):
        vs = ValueScorer()
        score = vs.update_score("p1", engagement=1.0, adoption=1.0, retention=1.0, advocacy=1.0)
        assert score.overall_value == pytest.approx(1.0, abs=0.01)

    def test_overall_value_zero(self):
        vs = ValueScorer()
        score = vs.update_score("p1", engagement=0.0, adoption=0.0, retention=0.0, advocacy=0.0)
        assert score.overall_value == pytest.approx(0.0, abs=0.01)

    def test_partial_update_preserves(self):
        vs = ValueScorer()
        vs.update_score("p1", engagement=0.8, adoption=0.7, retention=0.6, advocacy=0.5)
        score = vs.update_score("p1", engagement=0.9)
        assert score.engagement_score == 0.9
        assert score.adoption_score == 0.7  # preserved

    def test_values_clamped(self):
        vs = ValueScorer()
        score = vs.update_score("p1", engagement=2.0, adoption=-0.5)
        assert score.engagement_score == 1.0
        assert score.adoption_score == 0.0

    def test_timestamp_set(self):
        vs = ValueScorer()
        before = time.time()
        score = vs.update_score("p1", engagement=0.5)
        assert score.last_computed >= before


class TestValueScorerTiers:
    def test_tier_platinum(self):
        vs = ValueScorer()
        score = vs.update_score("p1", engagement=1.0, adoption=1.0, retention=1.0, advocacy=1.0)
        assert score.value_tier == ValueTier.PLATINUM

    def test_tier_gold(self):
        vs = ValueScorer()
        score = vs.update_score("p1", engagement=0.7, adoption=0.7, retention=0.7, advocacy=0.5)
        assert score.value_tier == ValueTier.GOLD

    def test_tier_silver(self):
        vs = ValueScorer()
        score = vs.update_score("p1", engagement=0.5, adoption=0.4, retention=0.5, advocacy=0.3)
        assert score.value_tier == ValueTier.SILVER

    def test_tier_bronze(self):
        vs = ValueScorer()
        score = vs.update_score("p1", engagement=0.1, adoption=0.1, retention=0.1, advocacy=0.1)
        assert score.value_tier == ValueTier.BRONZE


class TestValueScorerGet:
    def test_get_existing(self):
        vs = ValueScorer()
        vs.update_score("p1", engagement=0.5)
        assert vs.get_score("p1") is not None

    def test_get_nonexistent(self):
        vs = ValueScorer()
        assert vs.get_score("nope") is None

    def test_get_all_scores(self):
        vs = ValueScorer()
        vs.update_score("p1", engagement=0.5)
        vs.update_score("p2", engagement=0.7)
        assert len(vs.get_all_scores()) == 2


class TestValueScorerTopProducts:
    def test_top_products_sorted(self):
        vs = ValueScorer()
        vs.update_score("low", engagement=0.1, adoption=0.1, retention=0.1, advocacy=0.1)
        vs.update_score("high", engagement=0.9, adoption=0.9, retention=0.9, advocacy=0.9)
        vs.update_score("mid", engagement=0.5, adoption=0.5, retention=0.5, advocacy=0.5)
        top = vs.get_top_value_products(top_n=2)
        assert len(top) == 2
        assert top[0].product_id == "high"

    def test_top_products_empty(self):
        vs = ValueScorer()
        assert vs.get_top_value_products() == []


class TestValueScorerTrend:
    def test_trend_stable_single_entry(self):
        vs = ValueScorer()
        vs.update_score("p1", engagement=0.5)
        assert vs.get_value_trend("p1") == "stable"

    def test_trend_growing(self):
        vs = ValueScorer()
        vs.update_score("p1", engagement=0.3, adoption=0.3, retention=0.3, advocacy=0.3)
        vs.update_score("p1", engagement=0.5, adoption=0.5, retention=0.5, advocacy=0.5)
        vs.update_score("p1", engagement=0.8, adoption=0.8, retention=0.8, advocacy=0.8)
        assert vs.get_value_trend("p1") == "growing"

    def test_trend_declining(self):
        vs = ValueScorer()
        vs.update_score("p1", engagement=0.8, adoption=0.8, retention=0.8, advocacy=0.8)
        vs.update_score("p1", engagement=0.5, adoption=0.5, retention=0.5, advocacy=0.5)
        vs.update_score("p1", engagement=0.2, adoption=0.2, retention=0.2, advocacy=0.2)
        assert vs.get_value_trend("p1") == "declining"

    def test_trend_nonexistent_product(self):
        vs = ValueScorer()
        assert vs.get_value_trend("nope") == "stable"


class TestValueScorerSummary:
    def test_summary_empty(self):
        vs = ValueScorer()
        summary = vs.get_value_summary()
        assert summary["total_products"] == 0

    def test_summary_with_data(self):
        vs = ValueScorer()
        vs.update_score("p1", engagement=0.9, adoption=0.9, retention=0.9, advocacy=0.9)
        vs.update_score("p2", engagement=0.2, adoption=0.2, retention=0.2, advocacy=0.2)
        summary = vs.get_value_summary()
        assert summary["total_products"] == 2
        assert len(summary["by_tier"]) >= 1
        assert summary["avg_value"] > 0


class TestValueScorerWeights:
    def test_set_valid_weights(self):
        vs = ValueScorer()
        vs.set_weights(engagement=0.4, adoption=0.2, retention=0.2, advocacy=0.2)
        assert vs._weights["engagement"] == 0.4

    def test_set_partial_weights(self):
        vs = ValueScorer()
        # Default: 0.3 + 0.3 + 0.25 + 0.15 = 1.0
        # Change engagement to 0.25 → 0.25 + 0.3 + 0.25 + 0.15 = 0.95 → error
        with pytest.raises(ValueError):
            vs.set_weights(engagement=0.25)

    def test_set_weights_invalid_sum(self):
        vs = ValueScorer()
        with pytest.raises(ValueError, match="sum to 1.0"):
            vs.set_weights(engagement=0.5, adoption=0.5, retention=0.5, advocacy=0.5)

    def test_weights_affect_overall(self):
        vs = ValueScorer()
        # With default weights
        score1 = vs.update_score("p1", engagement=1.0, adoption=0.0, retention=0.0, advocacy=0.0)
        val1 = score1.overall_value

        vs2 = ValueScorer()
        vs2.set_weights(engagement=0.7, adoption=0.1, retention=0.1, advocacy=0.1)
        score2 = vs2.update_score("p1", engagement=1.0, adoption=0.0, retention=0.0, advocacy=0.0)
        val2 = score2.overall_value

        assert val2 > val1


class TestValueScorerMaxProducts:
    def test_evicts_when_full(self):
        vs = ValueScorer(max_products=3)
        for i in range(5):
            vs.update_score(f"p{i}", engagement=0.5)
        assert len(vs._scores) == 3

    def test_history_cleaned_on_eviction(self):
        vs = ValueScorer(max_products=2)
        vs.update_score("p0", engagement=0.5)
        vs.update_score("p1", engagement=0.6)
        vs.update_score("p2", engagement=0.7)
        assert len(vs._scores) == 2


# ──────────────────────────────────────────────────────────────
# Thread safety
# ──────────────────────────────────────────────────────────────

class TestThreadSafety:
    def test_revenue_signals_threaded(self):
        rs = RevenueSignals()
        errors = []

        def add_signals(start):
            try:
                for i in range(50):
                    rs.add_signal(RevenueSignalType.CHURN_RISK, f"p{start + i}", f"d{i}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_signals, args=(i * 50,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert len(rs._signals) == 200

    def test_segment_classifier_threaded(self):
        sc = SegmentClassifier()
        errors = []

        def classify_loop():
            try:
                for _ in range(50):
                    sc.update_metrics(engagement_score=0.5, active_days=20)
                    sc.classify()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=classify_loop) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors

    def test_lifecycle_tracker_threaded(self):
        lt = LifecycleTracker()
        errors = []

        def update_loop(start):
            try:
                for i in range(50):
                    lt.update_position(f"p{start + i}", {"total_events": i * 10, "days_active": i})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=update_loop, args=(i * 50,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors

    def test_value_scorer_threaded(self):
        vs = ValueScorer()
        errors = []

        def update_loop(start):
            try:
                for i in range(50):
                    vs.update_score(f"p{start + i}", engagement=0.5)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=update_loop, args=(i * 50,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors


# ──────────────────────────────────────────────────────────────
# Edge cases & integration
# ──────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_revenue_signal_dataclass_defaults(self):
        s = RevenueSignal(signal_id="x", signal_type=RevenueSignalType.CHURN_RISK, product_id="p", description="d")
        assert s.impact_score == 0.0
        assert s.evidence == []
        assert s.metadata == {}

    def test_user_segment_dataclass_defaults(self):
        seg = UserSegment(segment_type=SegmentType.REGULAR)
        assert seg.confidence == 0.0
        assert seg.factors == []

    def test_lifecycle_position_dataclass_defaults(self):
        pos = LifecyclePosition(stage=LifecycleStage.PROSPECT, product_id="p")
        assert pos.days_in_stage == 0
        assert pos.stage_health == 0.0

    def test_value_score_dataclass_defaults(self):
        vs = ValueScore(product_id="p")
        assert vs.value_tier == ValueTier.BRONZE
        assert vs.trend == "stable"

    def test_enum_values(self):
        assert RevenueSignalType.UPSELL_OPPORTUNITY.value == "upsell_opportunity"
        assert SegmentType.POWER_USER.value == "power_user"
        assert LifecycleStage.ONBOARDING.value == "onboarding"
        assert ValueTier.PLATINUM.value == "platinum"

    def test_all_revenue_signal_types(self):
        assert len(RevenueSignalType) == 7

    def test_all_segment_types(self):
        assert len(SegmentType) == 7

    def test_all_lifecycle_stages(self):
        assert len(LifecycleStage) == 8

    def test_all_value_tiers(self):
        assert len(ValueTier) == 4

    def test_revenue_signals_evaluate_no_rules(self):
        rs = RevenueSignals()
        signals = rs.evaluate_event("p1", {"action": "anything"})
        assert signals == []

    def test_lifecycle_tracker_empty_metrics(self):
        lt = LifecycleTracker()
        pos = lt.update_position("p1", {})
        assert pos.stage == LifecycleStage.PROSPECT

    def test_value_scorer_update_no_dimensions(self):
        vs = ValueScorer()
        score = vs.update_score("p1")
        assert score.overall_value == 0.0
        assert score.value_tier == ValueTier.BRONZE

    def test_segment_classifier_factors_not_empty(self):
        sc = SegmentClassifier()
        sc.update_metrics(engagement_score=0.5, active_days=20)
        seg = sc.classify()
        assert len(seg.factors) > 0

    def test_lifecycle_stage_history_recorded(self):
        lt = LifecycleTracker()
        lt.update_position("p1", {"total_events": 0})
        lt.update_position("p1", {"total_events": 10, "days_active": 3})
        assert len(lt._stage_history["p1"]) == 2
