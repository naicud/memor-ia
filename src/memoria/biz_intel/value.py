"""User engagement and value scoring per product."""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

from .types import ValueScore, ValueTier


class ValueScorer:
    """Scores user engagement and value realization per product."""

    def __init__(self, max_products: int = 50) -> None:
        self._lock = threading.Lock()
        self._scores: dict[str, ValueScore] = {}
        self._score_history: dict[str, list[tuple[float, float]]] = {}
        self._max_products = max(1, max_products)
        self._weights = {
            "engagement": 0.3,
            "adoption": 0.3,
            "retention": 0.25,
            "advocacy": 0.15,
        }

    def update_score(
        self,
        product_id: str,
        engagement: Optional[float] = None,
        adoption: Optional[float] = None,
        retention: Optional[float] = None,
        advocacy: Optional[float] = None,
    ) -> ValueScore:
        """Update individual scores and recompute overall value."""
        with self._lock:
            if len(self._scores) >= self._max_products and product_id not in self._scores:
                oldest_key = min(
                    self._scores,
                    key=lambda p: self._scores[p].last_computed,
                )
                del self._scores[oldest_key]
                self._score_history.pop(oldest_key, None)

            existing = self._scores.get(product_id)

            eng = self._clamp(engagement if engagement is not None else (existing.engagement_score if existing else 0.0))
            adp = self._clamp(adoption if adoption is not None else (existing.adoption_score if existing else 0.0))
            ret = self._clamp(retention if retention is not None else (existing.retention_score if existing else 0.0))
            adv = self._clamp(advocacy if advocacy is not None else (existing.advocacy_score if existing else 0.0))

            overall = (
                eng * self._weights["engagement"]
                + adp * self._weights["adoption"]
                + ret * self._weights["retention"]
                + adv * self._weights["advocacy"]
            )
            overall = self._clamp(overall)

            tier = self._tier_from_value(overall)
            now = time.time()

            # Track history for trend computation
            if product_id not in self._score_history:
                self._score_history[product_id] = []
            self._score_history[product_id].append((now, overall))
            if len(self._score_history[product_id]) > 100:
                self._score_history[product_id] = self._score_history[product_id][-100:]

            trend = self._compute_trend(product_id)

            score = ValueScore(
                product_id=product_id,
                engagement_score=eng,
                adoption_score=adp,
                retention_score=ret,
                advocacy_score=adv,
                overall_value=overall,
                value_tier=tier,
                trend=trend,
                last_computed=now,
            )
            self._scores[product_id] = score
            return score

    def get_score(self, product_id: str) -> Optional[ValueScore]:
        """Get the current value score for a product."""
        with self._lock:
            return self._scores.get(product_id)

    def get_all_scores(self) -> list[ValueScore]:
        """Get all tracked value scores."""
        with self._lock:
            return list(self._scores.values())

    def get_top_value_products(self, top_n: int = 5) -> list[ValueScore]:
        """Products sorted by overall_value descending."""
        with self._lock:
            sorted_scores = sorted(
                self._scores.values(),
                key=lambda s: s.overall_value,
                reverse=True,
            )
            return sorted_scores[:top_n]

    def get_value_trend(self, product_id: str) -> str:
        """'growing', 'stable', or 'declining' based on history."""
        with self._lock:
            return self._compute_trend(product_id)

    def get_value_summary(self) -> dict[str, Any]:
        """Summary: products by tier, avg value, trend distribution."""
        with self._lock:
            if not self._scores:
                return {
                    "total_products": 0,
                    "by_tier": {},
                    "avg_value": 0.0,
                    "trend_distribution": {},
                }

            by_tier: dict[str, int] = {}
            trend_dist: dict[str, int] = {}
            total_value = 0.0

            for s in self._scores.values():
                tier_name = s.value_tier.value
                by_tier[tier_name] = by_tier.get(tier_name, 0) + 1
                trend_dist[s.trend] = trend_dist.get(s.trend, 0) + 1
                total_value += s.overall_value

            count = len(self._scores)
            return {
                "total_products": count,
                "by_tier": by_tier,
                "avg_value": total_value / count,
                "trend_distribution": trend_dist,
            }

    def set_weights(
        self,
        engagement: Optional[float] = None,
        adoption: Optional[float] = None,
        retention: Optional[float] = None,
        advocacy: Optional[float] = None,
    ) -> None:
        """Override default scoring weights. Must sum to 1.0."""
        with self._lock:
            new_weights = dict(self._weights)
            if engagement is not None:
                new_weights["engagement"] = engagement
            if adoption is not None:
                new_weights["adoption"] = adoption
            if retention is not None:
                new_weights["retention"] = retention
            if advocacy is not None:
                new_weights["advocacy"] = advocacy

            total = sum(new_weights.values())
            if abs(total - 1.0) > 0.01:
                raise ValueError(f"Weights must sum to 1.0, got {total:.4f}")

            self._weights = new_weights

    def _compute_trend(self, product_id: str) -> str:
        """Compute trend from last 3 historical values."""
        history = self._score_history.get(product_id, [])
        if len(history) < 2:
            return "stable"

        recent = history[-3:] if len(history) >= 3 else history
        values = [v for _, v in recent]

        if len(values) < 2:
            return "stable"

        diffs = [values[i + 1] - values[i] for i in range(len(values) - 1)]
        avg_diff = sum(diffs) / len(diffs)

        if avg_diff > 0.02:
            return "growing"
        elif avg_diff < -0.02:
            return "declining"
        return "stable"

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))

    @staticmethod
    def _tier_from_value(overall: float) -> ValueTier:
        if overall >= 0.85:
            return ValueTier.PLATINUM
        if overall >= 0.65:
            return ValueTier.GOLD
        if overall >= 0.40:
            return ValueTier.SILVER
        return ValueTier.BRONZE
