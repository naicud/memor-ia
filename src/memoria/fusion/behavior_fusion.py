"""Behavioral signal fusion into a unified user model."""

from __future__ import annotations

import math
import threading
import time
from collections import Counter
from typing import Optional

from .types import BehavioralSignal, SignalType, UnifiedUserModel


class BehaviorFusion:
    """Merges behavioral signals from multiple products into a unified user model."""

    def __init__(
        self, max_signals: int = 50000, decay_halflife_days: float = 30.0
    ) -> None:
        self._lock = threading.RLock()
        self._signals: list[BehavioralSignal] = []
        self._model = UnifiedUserModel()
        self._max_signals = max(1, max_signals)
        self._decay_halflife = max(0.001, decay_halflife_days)

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest_signal(
        self,
        source_product: str,
        signal_type: SignalType,
        name: str,
        value: float,
        timestamp: Optional[float] = None,
        confidence: float = 1.0,
        metadata: Optional[dict] = None,
    ) -> BehavioralSignal:
        """Ingest a behavioral signal from any product.

        Auto-updates the unified model. Enforces *max_signals* with
        oldest-first rotation.
        """
        with self._lock:
            signal = BehavioralSignal(
                source_product=source_product,
                signal_type=signal_type,
                name=name,
                value=value,
                timestamp=timestamp if timestamp is not None else time.time(),
                confidence=max(0.0, min(1.0, confidence)),
                metadata=metadata or {},
            )
            self._signals.append(signal)

            # Enforce cap
            if len(self._signals) > self._max_signals:
                self._signals = self._signals[-self._max_signals :]

            self._rebuild_model()
            return signal

    # ------------------------------------------------------------------
    # Model
    # ------------------------------------------------------------------

    def get_unified_model(self) -> UnifiedUserModel:
        """Return the current unified user model, recomputed from all signals."""
        with self._lock:
            self._rebuild_model()
            return self._model

    def _rebuild_model(self) -> None:
        if not self._signals:
            self._model = UnifiedUserModel()
            return

        products = sorted({s.source_product for s in self._signals})
        breakdown: dict[str, int] = {}
        for s in self._signals:
            key = s.signal_type.value
            breakdown[key] = breakdown.get(key, 0) + 1

        self._model = UnifiedUserModel(
            user_id=self._model.user_id,
            total_signals=len(self._signals),
            products_active=products,
            dominant_patterns=self._compute_dominant_patterns(5),
            engagement_score=self._compute_engagement(None),
            consistency_score=self._compute_consistency(products),
            cross_product_activity=min(1.0, len(products) / 10.0),
            last_updated=time.time(),
            signal_breakdown=breakdown,
        )

    def _compute_engagement(self, product_id: Optional[str]) -> float:
        """Engagement = mean(value * confidence * decay_factor)."""
        now = time.time()
        total = 0.0
        count = 0
        for s in self._signals:
            if product_id and s.source_product != product_id:
                continue
            age_days = max(0.0, (now - s.timestamp) / 86400.0)
            decay = math.pow(0.5, age_days / self._decay_halflife)
            total += s.value * s.confidence * decay
            count += 1
        if count == 0:
            return 0.0
        raw = total / count
        return max(0.0, min(1.0, raw))

    def _compute_consistency(self, products: list[str]) -> float:
        """Consistency = 1 - stddev of per-product engagement."""
        if len(products) <= 1:
            return 1.0
        scores = [self._compute_engagement(p) for p in products]
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        std = math.sqrt(variance)
        return max(0.0, min(1.0, 1.0 - std))

    def _compute_dominant_patterns(self, top_n: int) -> list[str]:
        counter: Counter[str] = Counter()
        for s in self._signals:
            counter[s.name] += 1
        return [name for name, _ in counter.most_common(top_n)]

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_product_signals(
        self,
        product_id: str,
        signal_type: Optional[SignalType] = None,
        limit: int = 100,
    ) -> list[BehavioralSignal]:
        """Get signals from a specific product, optionally filtered by type."""
        with self._lock:
            limit = max(0, limit)
            if limit == 0:
                return []
            results: list[BehavioralSignal] = []
            for s in reversed(self._signals):
                if s.source_product != product_id:
                    continue
                if signal_type is not None and s.signal_type != signal_type:
                    continue
                results.append(s)
                if len(results) >= limit:
                    break
            return results

    def get_signal_timeline(
        self,
        name: Optional[str] = None,
        hours: float = 24,
    ) -> list[BehavioralSignal]:
        """Get recent signals within a time window."""
        with self._lock:
            cutoff = time.time() - max(0.0, hours) * 3600
            results: list[BehavioralSignal] = []
            for s in self._signals:
                if s.timestamp < cutoff:
                    continue
                if name is not None and s.name != name:
                    continue
                results.append(s)
            return results

    def compute_engagement_score(self, product_id: Optional[str] = None) -> float:
        """Compute engagement score for a product or overall."""
        with self._lock:
            return self._compute_engagement(product_id)

    def get_dominant_patterns(self, top_n: int = 5) -> list[str]:
        """Find most common signal names across all products."""
        with self._lock:
            return self._compute_dominant_patterns(max(0, top_n))
