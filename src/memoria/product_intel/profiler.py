"""Profilazione d'uso dei prodotti basata su flussi di eventi."""

from __future__ import annotations

import math
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .types import (
    AdoptionStage,
    FeatureStatus,
    ProductUsageEvent,
    UsageFrequency,
    UsageProfile,
)

_SECONDS_PER_DAY = 86_400


class UsageProfiler:
    """Builds detailed usage profiles per product from event streams.

    Events are stored per product with oldest-first rotation, and the
    corresponding :class:`UsageProfile` is updated on every
    :pymeth:`record_event` call.
    """

    def __init__(
        self,
        max_events_per_product: int = 10_000,
        max_products: int = 100,
    ) -> None:
        self._lock = threading.RLock()
        self._events: Dict[str, List[ProductUsageEvent]] = {}
        self._profiles: Dict[str, UsageProfile] = {}
        self._max_events = max(1, max_events_per_product)
        self._max_products = max(1, max_products)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_event(
        self,
        product_id: str,
        feature: str,
        action: str,
        timestamp: Optional[float] = None,
        duration: float = 0.0,
        session_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ProductUsageEvent:
        """Record a usage event and update the profile."""
        ts = timestamp if timestamp is not None else time.time()
        if not math.isfinite(ts):
            ts = time.time()
        dur = max(0.0, duration)

        event = ProductUsageEvent(
            product_id=product_id,
            feature=feature,
            action=action,
            timestamp=ts,
            duration_seconds=dur,
            metadata=dict(metadata) if metadata else {},
            session_id=session_id,
        )

        with self._lock:
            # Evict oldest product if at capacity
            if (
                product_id not in self._events
                and len(self._events) >= self._max_products
            ):
                oldest_pid = min(
                    self._events,
                    key=lambda pid: (
                        self._events[pid][-1].timestamp
                        if self._events[pid]
                        else 0.0
                    ),
                )
                del self._events[oldest_pid]
                self._profiles.pop(oldest_pid, None)

            events = self._events.setdefault(product_id, [])
            events.append(event)
            if len(events) > self._max_events:
                self._events[product_id] = events[-self._max_events :]

            self._update_profile(product_id)

        return event

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_profile(self, product_id: str) -> Optional[UsageProfile]:
        """Get the current usage profile for *product_id*."""
        with self._lock:
            return self._profiles.get(product_id)

    def compute_frequency(self, product_id: str) -> UsageFrequency:
        """Compute usage frequency from event timestamps."""
        with self._lock:
            events = self._events.get(product_id, [])
            if not events:
                return UsageFrequency.INACTIVE

            now = time.time()
            days_with_events_7 = self._unique_days(events, now, 7)
            has_30 = any(e.timestamp >= now - 30 * _SECONDS_PER_DAY for e in events)
            has_90 = any(e.timestamp >= now - 90 * _SECONDS_PER_DAY for e in events)
            has_365 = any(e.timestamp >= now - 365 * _SECONDS_PER_DAY for e in events)

            if days_with_events_7 >= 5:
                return UsageFrequency.DAILY
            if days_with_events_7 >= 2:
                return UsageFrequency.WEEKLY
            if has_30:
                return UsageFrequency.MONTHLY
            if has_90:
                return UsageFrequency.OCCASIONAL
            if has_365:
                return UsageFrequency.RARE
            return UsageFrequency.INACTIVE

    def compute_adoption_stage(self, product_id: str) -> AdoptionStage:
        """Compute adoption stage from usage patterns."""
        with self._lock:
            events = self._events.get(product_id, [])
            if not events:
                return AdoptionStage.DISCOVERY

            profile = self._profiles.get(product_id)
            if profile is None:
                return AdoptionStage.DISCOVERY

            total = profile.total_events
            n_features = len(profile.features_used)
            freq = self.compute_frequency(product_id)

            # Check for churned / declining first
            now = time.time()
            last = profile.last_used
            was_regular = total >= 20 and n_features >= 5
            if was_regular and last < now - 60 * _SECONDS_PER_DAY:
                return AdoptionStage.CHURNED

            if was_regular and self._frequency_dropped(product_id, levels=2):
                return AdoptionStage.DECLINING

            # Ascending stages
            if total < 5:
                return AdoptionStage.DISCOVERY
            if total < 20 or n_features < 5:
                return AdoptionStage.ONBOARDING

            # Champion check: power_user + 30+ continuous days
            is_power = (
                total >= 100
                and n_features >= 10
                and freq == UsageFrequency.DAILY
            )
            if is_power:
                span = profile.last_used - profile.first_used
                if span >= 30 * _SECONDS_PER_DAY:
                    return AdoptionStage.CHAMPION
                return AdoptionStage.POWER_USER

            return AdoptionStage.REGULAR

    def get_peak_hours(self, product_id: str) -> List[int]:
        """Get most-active hours (0-23) sorted by frequency desc."""
        with self._lock:
            events = self._events.get(product_id, [])
            if not events:
                return []
            hours = [
                datetime.fromtimestamp(e.timestamp, tz=timezone.utc).hour
                for e in events
            ]
            counts = Counter(hours)
            return [h for h, _ in counts.most_common()]

    def compare_products(
        self, product_id_a: str, product_id_b: str
    ) -> Dict[str, Any]:
        """Compare usage profiles between two products."""
        with self._lock:
            pa = self._profiles.get(product_id_a)
            pb = self._profiles.get(product_id_b)
            if pa is None and pb is None:
                return {"error": "neither product has a profile"}
            if pa is None:
                return {"error": f"no profile for {product_id_a}"}
            if pb is None:
                return {"error": f"no profile for {product_id_b}"}

            shared = set(pa.features_used) & set(pb.features_used)
            return {
                "product_a": product_id_a,
                "product_b": product_id_b,
                "total_events": {
                    product_id_a: pa.total_events,
                    product_id_b: pb.total_events,
                },
                "frequency": {
                    product_id_a: pa.frequency.value,
                    product_id_b: pb.frequency.value,
                },
                "adoption_stage": {
                    product_id_a: pa.adoption_stage.value,
                    product_id_b: pb.adoption_stage.value,
                },
                "shared_features": sorted(shared),
                "unique_to_a": sorted(
                    set(pa.features_used) - set(pb.features_used)
                ),
                "unique_to_b": sorted(
                    set(pb.features_used) - set(pa.features_used)
                ),
            }

    def get_most_used_features(
        self, product_id: str, top_n: int = 10
    ) -> List[Tuple[str, int]]:
        """Get top *top_n* most-used features for a product."""
        with self._lock:
            profile = self._profiles.get(product_id)
            if profile is None:
                return []
            n = max(0, top_n)
            return sorted(
                profile.features_used.items(), key=lambda x: x[1], reverse=True
            )[:n]

    def get_underutilized_features(
        self, product_id: str, available_features: List[str]
    ) -> List[str]:
        """Find features the user hasn't used or barely used (≤2 times)."""
        with self._lock:
            profile = self._profiles.get(product_id)
            used = profile.features_used if profile else {}
            return [
                f for f in available_features if used.get(f, 0) <= 2
            ]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _update_profile(self, product_id: str) -> None:
        """Rebuild the usage profile from stored events (caller holds lock)."""
        events = self._events.get(product_id, [])
        if not events:
            return

        profile = self._profiles.get(product_id)
        if profile is None:
            profile = UsageProfile(product_id=product_id)
            self._profiles[product_id] = profile

        profile.total_events = len(events)
        profile.total_duration_seconds = sum(e.duration_seconds for e in events)

        features: Dict[str, int] = {}
        for e in events:
            features[e.feature] = features.get(e.feature, 0) + 1
        profile.features_used = features

        timestamps = [e.timestamp for e in events]
        profile.first_used = min(timestamps)
        profile.last_used = max(timestamps)

        # Average session duration (group by session_id)
        sessions: Dict[str, float] = {}
        for e in events:
            if e.session_id:
                sessions[e.session_id] = (
                    sessions.get(e.session_id, 0.0) + e.duration_seconds
                )
        if sessions:
            profile.avg_session_duration = sum(sessions.values()) / len(sessions)
        else:
            profile.avg_session_duration = (
                profile.total_duration_seconds / profile.total_events
                if profile.total_events
                else 0.0
            )

        # Peak hours
        hours = [
            datetime.fromtimestamp(e.timestamp, tz=timezone.utc).hour
            for e in events
        ]
        counts = Counter(hours)
        profile.peak_hours = [h for h, _ in counts.most_common()]

        profile.frequency = self.compute_frequency(product_id)
        profile.adoption_stage = self.compute_adoption_stage(product_id)

        # Feature adoption statuses — rebuild from scratch so rotated-out
        # features don't leave stale entries.
        profile.feature_adoption = {}
        for feat, cnt in features.items():
            if cnt >= 50:
                profile.feature_adoption[feat] = FeatureStatus.MASTERED
            elif cnt >= 10:
                profile.feature_adoption[feat] = FeatureStatus.ADOPTED
            elif cnt >= 3:
                profile.feature_adoption[feat] = FeatureStatus.TRIED
            elif cnt >= 1:
                profile.feature_adoption[feat] = FeatureStatus.DISCOVERED

    @staticmethod
    def _unique_days(
        events: List[ProductUsageEvent], now: float, window_days: int
    ) -> int:
        """Count unique calendar days with events in the last *window_days*."""
        cutoff = now - window_days * _SECONDS_PER_DAY
        days = set()
        for e in events:
            if e.timestamp >= cutoff:
                days.add(
                    datetime.fromtimestamp(
                        e.timestamp, tz=timezone.utc
                    ).date()
                )
        return len(days)

    def _frequency_dropped(self, product_id: str, levels: int) -> bool:
        """Check if frequency dropped ≥ *levels* from historic peak."""
        events = self._events.get(product_id, [])
        if not events:
            return False

        order = [
            UsageFrequency.DAILY,
            UsageFrequency.WEEKLY,
            UsageFrequency.MONTHLY,
            UsageFrequency.OCCASIONAL,
            UsageFrequency.RARE,
            UsageFrequency.INACTIVE,
        ]

        # Historic peak: compute frequency with all events
        current = self.compute_frequency(product_id)
        current_idx = order.index(current) if current in order else len(order) - 1

        # Peak is assumed to be the best we ever saw.  Approximate by
        # checking the densest window.
        mid = len(events) // 2
        first_half = events[:mid] if mid else events
        if first_half:
            days_first = self._unique_days(
                first_half, first_half[-1].timestamp, 7
            )
            if days_first >= 5:
                peak_idx = 0
            elif days_first >= 2:
                peak_idx = 1
            else:
                peak_idx = 2
        else:
            peak_idx = current_idx

        return current_idx - peak_idx >= levels
