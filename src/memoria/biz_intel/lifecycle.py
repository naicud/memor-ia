"""User lifecycle stage tracking per product."""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

from .types import LifecyclePosition, LifecycleStage


class LifecycleTracker:
    """Tracks user lifecycle stage per product."""

    def __init__(self, max_products: int = 50) -> None:
        self._lock = threading.Lock()
        self._positions: dict[str, LifecyclePosition] = {}
        self._stage_history: dict[str, list[tuple[LifecycleStage, float]]] = {}
        self._max_products = max(1, max_products)

    def update_position(self, product_id: str, metrics: dict[str, Any]) -> LifecyclePosition:
        """Update lifecycle position based on metrics.

        metrics: {days_active, total_events, feature_count, engagement_score,
                  usage_trend, is_expanding}
        """
        with self._lock:
            if len(self._positions) >= self._max_products and product_id not in self._positions:
                oldest = min(self._positions, key=lambda p: self._positions[p].days_in_stage)
                del self._positions[oldest]
                self._stage_history.pop(oldest, None)

            days_active = metrics.get("days_active", 0)
            total_events = metrics.get("total_events", 0)
            feature_count = metrics.get("feature_count", 0)
            engagement_score = metrics.get("engagement_score", 0.0)
            usage_trend = metrics.get("usage_trend", "stable")
            is_expanding = metrics.get("is_expanding", False)

            prev_position = self._positions.get(product_id)
            prev_stage = prev_position.stage if prev_position else None

            stage: LifecycleStage
            confidence: float

            # Determine stage based on metrics
            if prev_stage == LifecycleStage.DECLINE and usage_trend == "growing":
                stage = LifecycleStage.REACTIVATION
                confidence = 0.7
            elif usage_trend == "declining" and prev_stage not in (None, LifecycleStage.PROSPECT):
                if days_active > 14:
                    stage = LifecycleStage.DECLINE
                    confidence = 0.75
                else:
                    stage = self._determine_stage_from_metrics(
                        days_active, total_events, feature_count, usage_trend, is_expanding,
                    )
                    confidence = 0.6
            else:
                stage = self._determine_stage_from_metrics(
                    days_active, total_events, feature_count, usage_trend, is_expanding,
                )
                confidence = self._compute_confidence(metrics)

            # Compute progression/regression probabilities
            progression_prob = 0.0
            regression_prob = 0.0

            if usage_trend == "growing":
                progression_prob = min(1.0, engagement_score * 0.8)
                regression_prob = max(0.0, 0.1 * (1.0 - engagement_score))
            elif usage_trend == "declining":
                progression_prob = max(0.0, 0.1 * engagement_score)
                regression_prob = min(1.0, 0.5 + 0.3 * (1.0 - engagement_score))
            else:
                progression_prob = min(1.0, engagement_score * 0.4)
                regression_prob = max(0.0, 0.2 * (1.0 - engagement_score))

            stage_health = engagement_score * (1.0 - regression_prob)

            # Track days in stage
            days_in_stage = 0
            if prev_position and prev_stage == stage:
                days_in_stage = prev_position.days_in_stage + 1
            else:
                days_in_stage = 1

            position = LifecyclePosition(
                stage=stage,
                product_id=product_id,
                confidence=max(0.0, min(1.0, confidence)),
                days_in_stage=days_in_stage,
                progression_probability=max(0.0, min(1.0, progression_prob)),
                regression_probability=max(0.0, min(1.0, regression_prob)),
                stage_health=max(0.0, min(1.0, stage_health)),
            )

            self._positions[product_id] = position

            # Record stage history
            if product_id not in self._stage_history:
                self._stage_history[product_id] = []
            if not self._stage_history[product_id] or self._stage_history[product_id][-1][0] != stage:
                self._stage_history[product_id].append((stage, time.time()))
                if len(self._stage_history[product_id]) > 100:
                    self._stage_history[product_id] = self._stage_history[product_id][-100:]

            return position

    def get_position(self, product_id: str) -> Optional[LifecyclePosition]:
        """Get the current lifecycle position for a product."""
        with self._lock:
            return self._positions.get(product_id)

    def get_all_positions(self) -> list[LifecyclePosition]:
        """Get all tracked lifecycle positions."""
        with self._lock:
            return list(self._positions.values())

    def get_stage_duration(self, product_id: str) -> dict[str, float]:
        """How long user has been in each stage for this product (in seconds)."""
        with self._lock:
            history = self._stage_history.get(product_id, [])
            if not history:
                return {}

            durations: dict[str, float] = {}
            for i, (stage, ts) in enumerate(history):
                if i + 1 < len(history):
                    duration = history[i + 1][1] - ts
                else:
                    duration = time.time() - ts
                key = stage.value
                durations[key] = durations.get(key, 0.0) + duration

            return durations

    def get_lifecycle_summary(self) -> dict[str, Any]:
        """Summary: products by stage, avg days per stage, health scores."""
        with self._lock:
            if not self._positions:
                return {
                    "total_products": 0,
                    "by_stage": {},
                    "avg_days_per_stage": 0.0,
                    "avg_health": 0.0,
                }

            by_stage: dict[str, int] = {}
            total_days = 0
            total_health = 0.0

            for pos in self._positions.values():
                stage_name = pos.stage.value
                by_stage[stage_name] = by_stage.get(stage_name, 0) + 1
                total_days += pos.days_in_stage
                total_health += pos.stage_health

            count = len(self._positions)
            return {
                "total_products": count,
                "by_stage": by_stage,
                "avg_days_per_stage": total_days / count,
                "avg_health": total_health / count,
            }

    def _determine_stage_from_metrics(
        self,
        days_active: int,
        total_events: int,
        feature_count: int,
        usage_trend: str,
        is_expanding: bool,
    ) -> LifecycleStage:
        """Determine lifecycle stage purely from metric thresholds."""
        if total_events == 0:
            return LifecycleStage.PROSPECT
        if days_active <= 7 and total_events < 20:
            return LifecycleStage.ONBOARDING
        if total_events >= 200 and usage_trend == "stable" and days_active > 60:
            if feature_count > 80:
                return LifecycleStage.SATURATION
            return LifecycleStage.MATURITY
        if total_events >= 100 and usage_trend == "growing":
            return LifecycleStage.GROWTH
        if days_active <= 30 and 20 <= total_events < 100:
            return LifecycleStage.ADOPTION
        if total_events >= 100:
            return LifecycleStage.GROWTH
        return LifecycleStage.ADOPTION

    def _compute_confidence(self, metrics: dict[str, Any]) -> float:
        """Confidence based on how many key metrics are provided."""
        key_metrics = ["days_active", "total_events", "feature_count", "engagement_score", "usage_trend"]
        present = sum(1 for k in key_metrics if k in metrics)
        return 0.4 + 0.6 * (present / len(key_metrics))
