"""Revenue signal tracking and generation from usage patterns."""

from __future__ import annotations

import threading
import time
import uuid
from collections import Counter
from typing import Any, Optional

from .types import RevenueSignal, RevenueSignalType


class RevenueSignals:
    """Tracks and generates revenue-relevant signals from usage patterns."""

    def __init__(self, max_signals: int = 5000) -> None:
        self._lock = threading.Lock()
        self._signals: list[RevenueSignal] = []
        self._rules: dict[str, dict[str, Any]] = {}
        self._max_signals = max(1, max_signals)

    def add_rule(
        self,
        name: str,
        signal_type: RevenueSignalType,
        keywords: list[str],
        description_template: str,
        recommended_action: str,
        min_impact: float = 0.5,
    ) -> None:
        """Add a signal detection rule. Keywords matched against event data."""
        with self._lock:
            self._rules[name] = {
                "signal_type": signal_type,
                "keywords": keywords,
                "description_template": description_template,
                "recommended_action": recommended_action,
                "min_impact": max(0.0, min(1.0, min_impact)),
            }

    def evaluate_event(self, product_id: str, event_data: dict[str, Any]) -> list[RevenueSignal]:
        """Evaluate an event against all rules. Returns generated signals.

        Match: count keyword hits in str(event_data), confidence = hits/total_keywords.
        Only generate signal if confidence >= 0.3.
        """
        with self._lock:
            generated: list[RevenueSignal] = []
            event_str = str(event_data).lower()

            for rule_name, rule in self._rules.items():
                keywords: list[str] = rule["keywords"]
                if not keywords:
                    continue

                hits = sum(1 for kw in keywords if kw.lower() in event_str)
                confidence = hits / len(keywords)

                if confidence < 0.3:
                    continue

                signal = RevenueSignal(
                    signal_id=uuid.uuid4().hex,
                    signal_type=rule["signal_type"],
                    product_id=product_id,
                    description=rule["description_template"],
                    impact_score=rule["min_impact"],
                    confidence=confidence,
                    timestamp=time.time(),
                    evidence=[f"rule:{rule_name}"] + [kw for kw in keywords if kw.lower() in event_str],
                    recommended_action=rule["recommended_action"],
                    metadata={"rule_name": rule_name, "event_data": dict(event_data)},
                )
                self._signals.append(signal)
                generated.append(signal)

            self._enforce_cap()
            return generated

    def add_signal(
        self,
        signal_type: RevenueSignalType,
        product_id: str,
        description: str,
        impact: float = 0.5,
        confidence: float = 0.5,
        evidence: Optional[list[str]] = None,
        action: str = "",
    ) -> RevenueSignal:
        """Manually add a revenue signal."""
        with self._lock:
            signal = RevenueSignal(
                signal_id=uuid.uuid4().hex,
                signal_type=signal_type,
                product_id=product_id,
                description=description,
                impact_score=max(0.0, min(1.0, impact)),
                confidence=max(0.0, min(1.0, confidence)),
                timestamp=time.time(),
                evidence=evidence or [],
                recommended_action=action,
            )
            self._signals.append(signal)
            self._enforce_cap()
            return signal

    def get_signals(
        self,
        signal_type: Optional[RevenueSignalType] = None,
        product_id: Optional[str] = None,
        min_impact: float = 0.0,
        limit: int = 50,
    ) -> list[RevenueSignal]:
        """Get signals with optional filters."""
        with self._lock:
            results = list(self._signals)

            if signal_type is not None:
                results = [s for s in results if s.signal_type == signal_type]
            if product_id is not None:
                results = [s for s in results if s.product_id == product_id]
            if min_impact > 0.0:
                results = [s for s in results if s.impact_score >= min_impact]

            return results[-limit:]

    def get_top_opportunities(self, top_n: int = 10) -> list[RevenueSignal]:
        """Get top N revenue opportunities sorted by impact * confidence."""
        with self._lock:
            sorted_signals = sorted(
                self._signals,
                key=lambda s: s.impact_score * s.confidence,
                reverse=True,
            )
            return sorted_signals[:top_n]

    def get_signal_summary(self) -> dict[str, Any]:
        """Summary: total signals, by type, avg impact, top products."""
        with self._lock:
            if not self._signals:
                return {
                    "total_signals": 0,
                    "by_type": {},
                    "avg_impact": 0.0,
                    "top_products": [],
                }

            by_type: Counter = Counter()
            product_counter: Counter = Counter()
            total_impact = 0.0

            for s in self._signals:
                by_type[s.signal_type.value] += 1
                product_counter[s.product_id] += 1
                total_impact += s.impact_score

            return {
                "total_signals": len(self._signals),
                "by_type": dict(by_type),
                "avg_impact": total_impact / len(self._signals),
                "top_products": [p for p, _ in product_counter.most_common(5)],
            }

    def _enforce_cap(self) -> None:
        """Trim signals to max_signals, keeping most recent."""
        if len(self._signals) > self._max_signals:
            self._signals = self._signals[-self._max_signals:]
