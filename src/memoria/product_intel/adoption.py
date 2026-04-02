"""Analisi delle curve di adozione delle funzionalità."""

from __future__ import annotations

import random
import threading
import time
from typing import Any, Dict, List, Optional

from .types import AdoptionCurve, FeatureStatus

_SECONDS_PER_DAY = 86_400


class AdoptionAnalyzer:
    """Analyzes feature adoption curves and identifies underutilized features.

    Tracks per-feature usage counts and auto-transitions through
    :class:`FeatureStatus` stages as usage accumulates.
    """

    def __init__(self, max_curves: int = 1000) -> None:
        self._lock = threading.RLock()
        self._curves: Dict[str, AdoptionCurve] = {}  # "product:feature" -> curve
        self._max_curves = max(1, max_curves)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def track_feature_use(
        self, product_id: str, feature: str, timestamp: Optional[float] = None
    ) -> AdoptionCurve:
        """Record feature usage and update the adoption curve.

        Stage transitions:
        UNKNOWN  → DISCOVERED  (1st use)
        DISCOVERED → TRIED     (3+ uses)
        TRIED    → ADOPTED     (10+ uses)
        ADOPTED  → MASTERED    (50+ uses, 30+ days since discovery)
        """
        ts = timestamp if timestamp is not None else time.time()
        key = f"{product_id}:{feature}"

        with self._lock:
            curve = self._curves.get(key)
            if curve is None:
                # Evict oldest curve if at capacity
                if len(self._curves) >= self._max_curves:
                    oldest_key = min(
                        self._curves,
                        key=lambda k: self._curves[k].discovery_date
                        if self._curves[k].discovery_date
                        else float("inf"),
                    )
                    del self._curves[oldest_key]

                curve = AdoptionCurve(
                    product_id=product_id,
                    feature=feature,
                    stage=FeatureStatus.UNKNOWN,
                )
                self._curves[key] = curve

            curve.total_uses += 1

            # Stage transitions
            if curve.stage == FeatureStatus.UNKNOWN:
                curve.stage = FeatureStatus.DISCOVERED
                curve.discovery_date = ts

            if (
                curve.stage == FeatureStatus.DISCOVERED
                and curve.total_uses >= 3
            ):
                curve.stage = FeatureStatus.TRIED

            if curve.stage == FeatureStatus.TRIED and curve.total_uses >= 10:
                curve.stage = FeatureStatus.ADOPTED
                curve.adoption_date = ts
                if curve.discovery_date > 0:
                    curve.days_to_adopt = int(
                        (ts - curve.discovery_date) / _SECONDS_PER_DAY
                    )

            if curve.stage == FeatureStatus.ADOPTED and curve.total_uses >= 50:
                if (
                    curve.discovery_date > 0
                    and (ts - curve.discovery_date) >= 30 * _SECONDS_PER_DAY
                ):
                    curve.stage = FeatureStatus.MASTERED
                    curve.mastery_date = ts

            # Update trend heuristic
            curve.usage_trend = self._compute_trend(curve, ts)

            return curve

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_adoption_curve(
        self, product_id: str, feature: str
    ) -> Optional[AdoptionCurve]:
        """Get the adoption curve for a specific feature."""
        with self._lock:
            return self._curves.get(f"{product_id}:{feature}")

    def get_product_adoption_summary(
        self, product_id: str
    ) -> Dict[str, Any]:
        """Summary: features by stage, avg days_to_adopt, trend distribution."""
        with self._lock:
            curves = [
                c
                for c in self._curves.values()
                if c.product_id == product_id
            ]
            if not curves:
                return {
                    "product_id": product_id,
                    "total_features": 0,
                    "by_stage": {},
                    "avg_days_to_adopt": 0.0,
                    "trends": {},
                }

            by_stage: Dict[str, int] = {}
            trends: Dict[str, int] = {}
            adopt_days: List[int] = []

            for c in curves:
                stage_val = c.stage.value
                by_stage[stage_val] = by_stage.get(stage_val, 0) + 1
                trends[c.usage_trend] = trends.get(c.usage_trend, 0) + 1
                if c.days_to_adopt > 0:
                    adopt_days.append(c.days_to_adopt)

            avg_days = sum(adopt_days) / len(adopt_days) if adopt_days else 0.0

            return {
                "product_id": product_id,
                "total_features": len(curves),
                "by_stage": by_stage,
                "avg_days_to_adopt": avg_days,
                "trends": trends,
            }

    def get_stalled_features(
        self, product_id: str, days_threshold: int = 14
    ) -> List[AdoptionCurve]:
        """Find features stuck at DISCOVERED/TRIED for > *days_threshold*."""
        threshold = max(0, days_threshold)
        now = time.time()

        with self._lock:
            stalled: List[AdoptionCurve] = []
            for c in self._curves.values():
                if c.product_id != product_id:
                    continue
                if c.stage not in (
                    FeatureStatus.DISCOVERED,
                    FeatureStatus.TRIED,
                ):
                    continue
                if (
                    c.discovery_date > 0
                    and (now - c.discovery_date) > threshold * _SECONDS_PER_DAY
                ):
                    stalled.append(c)
            return stalled

    def get_abandonment_risk(
        self, product_id: str
    ) -> List[AdoptionCurve]:
        """Find features with declining usage or ABANDONED status."""
        with self._lock:
            return [
                c
                for c in self._curves.values()
                if c.product_id == product_id
                and (
                    c.usage_trend == "declining"
                    or c.stage == FeatureStatus.ABANDONED
                )
            ]

    def suggest_features_to_explore(
        self,
        product_id: str,
        all_features: List[str],
        top_n: int = 5,
    ) -> List[str]:
        """Suggest features the user hasn't tried, randomly selected."""
        with self._lock:
            known = {
                c.feature
                for c in self._curves.values()
                if c.product_id == product_id
            }
            unknown = [f for f in all_features if f not in known]
            n = max(0, min(top_n, len(unknown)))
            return random.sample(unknown, n) if unknown else []

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_trend(curve: AdoptionCurve, now: float) -> str:
        """Simple heuristic: growing if recently discovered, stable otherwise."""
        if curve.discovery_date <= 0:
            return "stable"
        age_days = (now - curve.discovery_date) / _SECONDS_PER_DAY
        if age_days <= 0:
            return "stable"
        rate = curve.total_uses / age_days
        if rate >= 2.0:
            return "growing"
        if rate < 0.1 and curve.total_uses > 5:
            return "declining"
        return "stable"
