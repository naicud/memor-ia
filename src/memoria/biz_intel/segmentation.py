"""Dynamic user segmentation based on behavioral metrics."""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

from .types import SegmentType, UserSegment


class SegmentClassifier:
    """Classifies users into behavioral segments dynamically."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current_segment: Optional[UserSegment] = None
        self._segment_history: list[UserSegment] = []
        self._max_history = 100
        self._metrics: dict[str, float] = {}

    def update_metrics(self, **kwargs: float) -> None:
        """Update classification metrics.

        Expected: total_events, active_days, products_used, features_used,
                  engagement_score, churn_risk, advocacy_actions, days_since_signup
        """
        with self._lock:
            for key, value in kwargs.items():
                self._metrics[key] = float(value)

    def classify(self) -> UserSegment:
        """Classify user into a segment based on current metrics.

        CHAMPION: engagement >= 0.8 AND advocacy_actions >= 5 AND active_days >= 90
        POWER_USER: engagement >= 0.7 AND features_used >= 15 AND active_days >= 30
        REGULAR: engagement >= 0.4 AND active_days >= 14
        CASUAL: engagement >= 0.2 AND active_days >= 3
        NEW_USER: days_since_signup <= 14
        AT_RISK: was REGULAR+ but engagement dropped below 0.3
        DORMANT: no events in 30+ days (active_days == 0 AND days_since_signup > 30)
        """
        with self._lock:
            m = self._metrics
            engagement = m.get("engagement_score", 0.0)
            advocacy = m.get("advocacy_actions", 0.0)
            active_days = m.get("active_days", 0.0)
            features_used = m.get("features_used", 0.0)
            days_since_signup = m.get("days_since_signup", 0.0)
            total_events = m.get("total_events", 0.0)

            factors: list[str] = []
            segment_type: SegmentType
            confidence: float

            # AT_RISK: was a higher segment but engagement dropped
            prev_higher = (
                self._current_segment is not None
                and self._current_segment.segment_type
                in (SegmentType.CHAMPION, SegmentType.POWER_USER, SegmentType.REGULAR)
            )
            if prev_higher and engagement < 0.3:
                segment_type = SegmentType.AT_RISK
                factors = [
                    f"engagement_dropped_to_{engagement:.2f}",
                    f"was_{self._current_segment.segment_type.value}",  # type: ignore[union-attr]
                ]
                confidence = min(1.0, (0.3 - engagement) / 0.3 + 0.5)
            elif active_days == 0 and days_since_signup > 30 and total_events == 0:
                segment_type = SegmentType.DORMANT
                factors = ["no_activity", f"days_since_signup={days_since_signup}"]
                confidence = 0.9
            elif engagement >= 0.8 and advocacy >= 5 and active_days >= 90:
                segment_type = SegmentType.CHAMPION
                factors = [
                    f"engagement={engagement:.2f}",
                    f"advocacy={advocacy}",
                    f"active_days={active_days}",
                ]
                confidence = self._compute_confidence(["engagement_score", "advocacy_actions", "active_days"])
            elif engagement >= 0.7 and features_used >= 15 and active_days >= 30:
                segment_type = SegmentType.POWER_USER
                factors = [
                    f"engagement={engagement:.2f}",
                    f"features_used={features_used}",
                    f"active_days={active_days}",
                ]
                confidence = self._compute_confidence(["engagement_score", "features_used", "active_days"])
            elif engagement >= 0.4 and active_days >= 14:
                segment_type = SegmentType.REGULAR
                factors = [f"engagement={engagement:.2f}", f"active_days={active_days}"]
                confidence = self._compute_confidence(["engagement_score", "active_days"])
            elif engagement >= 0.2 and active_days >= 3:
                segment_type = SegmentType.CASUAL
                factors = [f"engagement={engagement:.2f}", f"active_days={active_days}"]
                confidence = self._compute_confidence(["engagement_score", "active_days"])
            elif days_since_signup <= 14:
                segment_type = SegmentType.NEW_USER
                factors = [f"days_since_signup={days_since_signup}"]
                confidence = 0.8
            else:
                segment_type = SegmentType.CASUAL
                factors = ["default_fallback"]
                confidence = 0.3

            segment = UserSegment(
                segment_type=segment_type,
                confidence=max(0.0, min(1.0, confidence)),
                factors=factors,
                since=time.time(),
            )

            if self._current_segment is None or self._current_segment.segment_type != segment_type:
                self._segment_history.append(segment)
                if len(self._segment_history) > self._max_history:
                    self._segment_history = self._segment_history[-self._max_history:]

            self._current_segment = segment
            return segment

    def get_current_segment(self) -> Optional[UserSegment]:
        """Return the current segment, if classified."""
        with self._lock:
            return self._current_segment

    def get_segment_history(self, limit: int = 20) -> list[UserSegment]:
        """Return recent segment history."""
        with self._lock:
            return list(self._segment_history[-limit:])

    def get_segment_transition_risk(self) -> dict[str, Any]:
        """Risk of transitioning to a worse segment. Based on metric trends."""
        with self._lock:
            if self._current_segment is None:
                return {"risk": "unknown", "probability": 0.0, "factors": []}

            engagement = self._metrics.get("engagement_score", 0.0)
            churn_risk = self._metrics.get("churn_risk", 0.0)
            current = self._current_segment.segment_type

            risk_factors: list[str] = []
            probability = 0.0

            if engagement < 0.3:
                risk_factors.append("low_engagement")
                probability += 0.3
            if churn_risk > 0.5:
                risk_factors.append("high_churn_risk")
                probability += 0.3
            if current in (SegmentType.CHAMPION, SegmentType.POWER_USER) and engagement < 0.5:
                risk_factors.append("engagement_below_segment_threshold")
                probability += 0.2

            probability = min(1.0, probability)
            if probability >= 0.6:
                risk_level = "high"
            elif probability >= 0.3:
                risk_level = "medium"
            else:
                risk_level = "low"

            return {
                "risk": risk_level,
                "probability": probability,
                "current_segment": current.value,
                "factors": risk_factors,
            }

    def get_segment_summary(self) -> dict[str, Any]:
        """Summary of current segmentation state."""
        with self._lock:
            return {
                "current_segment": self._current_segment.segment_type.value if self._current_segment else None,
                "confidence": self._current_segment.confidence if self._current_segment else 0.0,
                "total_transitions": len(self._segment_history),
                "metrics_tracked": len(self._metrics),
                "metrics": dict(self._metrics),
            }

    def _compute_confidence(self, required_keys: list[str]) -> float:
        """Compute confidence based on how many required metrics are present."""
        if not required_keys:
            return 0.5
        present = sum(1 for k in required_keys if k in self._metrics)
        return 0.4 + 0.6 * (present / len(required_keys))
