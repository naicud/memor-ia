"""Cross-product churn risk prediction."""

from __future__ import annotations

import threading
import time
from typing import Optional

from .types import ChurnPrediction, ChurnRisk


class ChurnPredictor:
    """Predicts user disengagement risk for individual products using cross-product signals."""

    def __init__(
        self, inactivity_threshold_days: int = 30, max_history: int = 1000
    ) -> None:
        self._lock = threading.RLock()
        self._usage_history: dict[str, list[float]] = {}  # product -> [ts]
        self._engagement_scores: dict[str, list[tuple[float, float]]] = {}  # product -> [(ts, score)]
        self._max_history = max(1, max_history)
        self._inactivity_threshold = max(1, inactivity_threshold_days)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_usage(
        self, product_id: str, timestamp: Optional[float] = None
    ) -> None:
        """Record a usage event for churn analysis."""
        with self._lock:
            ts = timestamp if timestamp is not None else time.time()
            if product_id not in self._usage_history:
                self._usage_history[product_id] = []
            self._usage_history[product_id].append(ts)

            if len(self._usage_history[product_id]) > self._max_history:
                self._usage_history[product_id] = self._usage_history[product_id][
                    -self._max_history :
                ]

    def record_engagement(
        self, product_id: str, score: float, timestamp: Optional[float] = None
    ) -> None:
        """Record an engagement score (0–1) for trend analysis."""
        with self._lock:
            ts = timestamp if timestamp is not None else time.time()
            score = max(0.0, min(1.0, score))
            if product_id not in self._engagement_scores:
                self._engagement_scores[product_id] = []
            self._engagement_scores[product_id].append((ts, score))

            if len(self._engagement_scores[product_id]) > self._max_history:
                self._engagement_scores[product_id] = self._engagement_scores[
                    product_id
                ][-self._max_history :]

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict_churn(self, product_id: str) -> ChurnPrediction:
        """Predict churn risk for a product.

        Risk levels:
        * CRITICAL — no usage in 2× threshold AND declining engagement
        * HIGH — no usage in threshold OR engagement dropped 50%+
        * MEDIUM — usage frequency dropped 50%+ OR engagement declining
        * LOW — minor usage decrease OR slight engagement dip
        * NONE — stable or growing usage
        """
        with self._lock:
            warnings: list[str] = []
            actions: list[str] = []
            now = time.time()

            usage = self._usage_history.get(product_id, [])
            engagement = self._engagement_scores.get(product_id, [])

            if not usage and not engagement:
                return ChurnPrediction(
                    product_id=product_id,
                    risk_level=ChurnRisk.NONE,
                    probability=0.0,
                    days_until_likely_churn=-1,
                    warning_signals=["No data available"],
                    recommended_actions=["Start tracking usage"],
                    confidence=0.0,
                )

            # ---- Inactivity analysis ----
            days_inactive = 0.0
            if usage:
                last_usage = max(usage)
                days_inactive = (now - last_usage) / 86400.0

            # ---- Engagement trend ----
            eng_declining = False
            eng_dropped_50 = False
            eng_slight_dip = False
            if len(engagement) >= 2:
                scores = [s for _, s in engagement]
                peak = max(scores)
                recent = scores[-1]
                if peak > 0:
                    drop_pct = (peak - recent) / peak
                    if drop_pct >= 0.5:
                        eng_dropped_50 = True
                    elif drop_pct >= 0.1:
                        eng_slight_dip = True

                # Trend: compare first half vs second half
                mid = len(scores) // 2
                if mid > 0:
                    first_half = sum(scores[:mid]) / mid
                    second_half = sum(scores[mid:]) / len(scores[mid:])
                    if second_half < first_half * 0.9:
                        eng_declining = True

            # ---- Usage frequency trend ----
            usage_freq_dropped = False
            usage_minor_decrease = False
            if len(usage) >= 4:
                sorted_usage = sorted(usage)
                mid = len(sorted_usage) // 2
                first_intervals = self._avg_interval(sorted_usage[:mid])
                second_intervals = self._avg_interval(sorted_usage[mid:])
                if first_intervals > 0 and second_intervals > 0:
                    # Longer intervals = less frequent
                    ratio = second_intervals / first_intervals
                    if ratio >= 2.0:
                        usage_freq_dropped = True
                    elif ratio >= 1.3:
                        usage_minor_decrease = True

            # ---- Determine risk ----
            _threshold_secs = self._inactivity_threshold * 86400.0

            risk = ChurnRisk.NONE
            probability = 0.0
            days_until = -1

            if usage and days_inactive >= 2 * self._inactivity_threshold and eng_declining:
                risk = ChurnRisk.CRITICAL
                probability = min(1.0, 0.8 + days_inactive / (10 * self._inactivity_threshold))
                days_until = 0
                warnings.append(f"No usage for {days_inactive:.0f} days (2× threshold)")
                warnings.append("Engagement is declining")
                actions.append("Immediate re-engagement campaign")
                actions.append("Executive outreach recommended")
            elif usage and (
                days_inactive >= self._inactivity_threshold or eng_dropped_50
            ):
                risk = ChurnRisk.HIGH
                probability = min(1.0, 0.6 + days_inactive / (5 * self._inactivity_threshold))
                days_until = max(0, int(self._inactivity_threshold - days_inactive))
                if days_inactive >= self._inactivity_threshold:
                    warnings.append(f"No usage for {days_inactive:.0f} days")
                if eng_dropped_50:
                    warnings.append("Engagement dropped 50%+ from peak")
                actions.append("Send re-engagement offer")
                actions.append("Schedule check-in call")
            elif usage_freq_dropped or eng_declining:
                risk = ChurnRisk.MEDIUM
                probability = 0.4
                days_until = int(self._inactivity_threshold)
                if usage_freq_dropped:
                    warnings.append("Usage frequency dropped 50%+")
                if eng_declining:
                    warnings.append("Engagement trend declining")
                actions.append("Send feature highlights")
                actions.append("Offer training session")
            elif usage_minor_decrease or eng_slight_dip:
                risk = ChurnRisk.LOW
                probability = 0.2
                days_until = int(2 * self._inactivity_threshold)
                if usage_minor_decrease:
                    warnings.append("Minor usage decrease detected")
                if eng_slight_dip:
                    warnings.append("Slight engagement dip")
                actions.append("Monitor closely")
            else:
                risk = ChurnRisk.NONE
                probability = 0.0
                days_until = -1

            confidence = min(
                1.0, (len(usage) + len(engagement)) / 20.0
            )

            return ChurnPrediction(
                product_id=product_id,
                risk_level=risk,
                probability=min(1.0, probability),
                days_until_likely_churn=days_until,
                warning_signals=warnings,
                recommended_actions=actions,
                confidence=confidence,
            )

    @staticmethod
    def _avg_interval(timestamps: list[float]) -> float:
        """Average interval between consecutive timestamps."""
        if len(timestamps) < 2:
            return 0.0
        intervals = [
            timestamps[i + 1] - timestamps[i]
            for i in range(len(timestamps) - 1)
        ]
        return sum(intervals) / len(intervals) if intervals else 0.0

    # ------------------------------------------------------------------
    # Bulk queries
    # ------------------------------------------------------------------

    def predict_all(self) -> list[ChurnPrediction]:
        """Predict churn for all tracked products."""
        with self._lock:
            products = set(self._usage_history) | set(self._engagement_scores)
            return [self.predict_churn(p) for p in sorted(products)]

    def get_at_risk_products(
        self, min_risk: ChurnRisk = ChurnRisk.MEDIUM
    ) -> list[ChurnPrediction]:
        """Get products at or above minimum risk level."""
        risk_order = [
            ChurnRisk.NONE,
            ChurnRisk.LOW,
            ChurnRisk.MEDIUM,
            ChurnRisk.HIGH,
            ChurnRisk.CRITICAL,
        ]
        min_idx = risk_order.index(min_risk)
        predictions = self.predict_all()
        return [p for p in predictions if risk_order.index(p.risk_level) >= min_idx]

    # ------------------------------------------------------------------
    # Trend
    # ------------------------------------------------------------------

    def get_engagement_trend(self, product_id: str) -> str:
        """Return ``'growing'``, ``'stable'``, or ``'declining'``."""
        with self._lock:
            engagement = self._engagement_scores.get(product_id, [])
            if len(engagement) < 2:
                return "stable"
            scores = [s for _, s in engagement]
            mid = len(scores) // 2
            if mid == 0:
                return "stable"
            first_half = sum(scores[:mid]) / mid
            second_half = sum(scores[mid:]) / len(scores[mid:])
            if second_half > first_half * 1.1:
                return "growing"
            if second_half < first_half * 0.9:
                return "declining"
            return "stable"
