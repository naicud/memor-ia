"""Statistical anomaly detection for behavioural metrics."""

from __future__ import annotations

import math
import threading
import time
from typing import Any, Dict, List, Optional

from .types import AnomalyAlert, AnomalyType

# Metric-name → AnomalyType mapping
_METRIC_TYPE_MAP: Dict[str, AnomalyType] = {
    "session_duration": AnomalyType.UNUSUAL_TIMING,
    "response_time": AnomalyType.UNUSUAL_TIMING,
    "action_frequency": AnomalyType.BEHAVIOR_SHIFT,
    "tool_usage": AnomalyType.BEHAVIOR_SHIFT,
    "error_rate": AnomalyType.SKILL_REGRESSION,
    "retry_count": AnomalyType.SKILL_REGRESSION,
    "sequence_break": AnomalyType.PATTERN_BREAK,
    "topic_similarity": AnomalyType.TOPIC_DEVIATION,
}


def _anomaly_type_for(metric: str) -> AnomalyType:
    """Resolve the anomaly type for a given metric name."""
    if metric in _METRIC_TYPE_MAP:
        return _METRIC_TYPE_MAP[metric]
    # Fallback heuristics based on substring matching
    lower = metric.lower()
    if "time" in lower or "duration" in lower:
        return AnomalyType.UNUSUAL_TIMING
    if "error" in lower or "retry" in lower or "fail" in lower:
        return AnomalyType.SKILL_REGRESSION
    if "topic" in lower or "similarity" in lower:
        return AnomalyType.TOPIC_DEVIATION
    if "break" in lower or "sequence" in lower:
        return AnomalyType.PATTERN_BREAK
    return AnomalyType.BEHAVIOR_SHIFT


class AnomalyDetector:
    """Detects anomalous behavioural observations using z-score analysis.

    Each metric is tracked independently.  An observation is flagged when its
    z-score exceeds ``sensitivity * 2`` standard deviations from the running
    mean.  Severity is ``|z| / 4`` clamped to [0, 1].
    """

    def __init__(
        self, sensitivity: float = 0.7, baseline_window: int = 50
    ) -> None:
        self._lock = threading.RLock()
        self._sensitivity = max(0.0, min(1.0, sensitivity))
        self._baseline_window = max(1, baseline_window)
        # metric -> list of (value, timestamp, context)
        self._observations: Dict[str, List[Dict[str, Any]]] = {}

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_observation(
        self,
        metric: str,
        value: float,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add a data point for *metric*."""
        if not math.isfinite(value):
            return
        with self._lock:
            if metric not in self._observations:
                self._observations[metric] = []
            self._observations[metric].append(
                {
                    "value": value,
                    "timestamp": time.time(),
                    "context": context or {},
                }
            )
            # Trim to baseline window
            if len(self._observations[metric]) > self._baseline_window:
                self._observations[metric] = self._observations[metric][
                    -self._baseline_window :
                ]

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect_anomalies(
        self, metric: Optional[str] = None
    ) -> List[AnomalyAlert]:
        """Check the latest observation(s) for anomalies.

        If *metric* is given only that metric is checked; otherwise all
        tracked metrics are scanned.
        """
        with self._lock:
            metrics = [metric] if metric else list(self._observations)
            alerts: List[AnomalyAlert] = []
            for m in metrics:
                alert = self._check_metric(m)
                if alert is not None:
                    alerts.append(alert)
            return alerts

    def _check_metric(self, metric: str) -> Optional[AnomalyAlert]:
        obs = self._observations.get(metric)
        if not obs or len(obs) < 2:
            return None

        values = [o["value"] for o in obs]
        mean = sum(values) / len(values)

        variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        std = math.sqrt(variance)

        if std < 1e-12:
            return None

        latest = values[-1]
        z_score = (latest - mean) / std
        threshold = self._sensitivity * 2.0

        if abs(z_score) <= threshold:
            return None

        severity = min(1.0, abs(z_score) / 4.0)
        anomaly_type = _anomaly_type_for(metric)

        return AnomalyAlert(
            anomaly_type=anomaly_type,
            severity=severity,
            description=(
                f"Metric '{metric}' value {latest:.3f} deviates "
                f"{abs(z_score):.1f} σ from mean {mean:.3f} "
                f"(threshold {threshold:.1f} σ)"
            ),
            baseline_value=mean,
            observed_value=latest,
            context=obs[-1].get("context", {}),
        )

    # ------------------------------------------------------------------
    # Baseline & inspection
    # ------------------------------------------------------------------

    def get_baseline(self, metric: str) -> Dict[str, Any]:
        """Return baseline statistics for a single metric."""
        with self._lock:
            obs = self._observations.get(metric)
            if not obs:
                return {"metric": metric, "count": 0}
            values = [o["value"] for o in obs]
            mean = sum(values) / len(values)
            N = len(values)
            variance = sum((v - mean) ** 2 for v in values) / (N - 1) if N > 1 else 0.0
            std = math.sqrt(variance)
            return {
                "metric": metric,
                "count": len(values),
                "mean": mean,
                "std": std,
                "min": min(values),
                "max": max(values),
            }

    def set_sensitivity(self, sensitivity: float) -> None:
        """Adjust the anomaly detection threshold (0.0–1.0)."""
        with self._lock:
            self._sensitivity = max(0.0, min(1.0, sensitivity))

    def get_all_metrics(self) -> List[str]:
        """Return the names of all tracked metrics."""
        with self._lock:
            return list(self._observations.keys())

    def reset_baseline(self, metric: Optional[str] = None) -> None:
        """Reset observations for one or all metrics."""
        with self._lock:
            if metric:
                self._observations.pop(metric, None)
            else:
                self._observations.clear()
