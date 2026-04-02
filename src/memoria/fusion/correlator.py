"""Cross-product signal correlation analysis."""

from __future__ import annotations

import math
import threading
import time
from typing import Optional

from .types import Correlation, CorrelationType


class CrossProductCorrelator:
    """Finds correlations between usage patterns across products."""

    def __init__(
        self, min_evidence: int = 5, max_correlations: int = 200,
        max_observations_per_pair: int = 10000,
    ) -> None:
        self._lock = threading.RLock()
        # "A:sig|B:sig" -> [(val_a, val_b, timestamp), ...]
        self._observations: dict[str, list[tuple[float, float, float]]] = {}
        self._correlations: list[Correlation] = []
        self._min_evidence = max(1, min_evidence)
        self._max_correlations = max(1, max_correlations)
        self._max_obs_per_pair = max(1, max_observations_per_pair)

    # ------------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------------

    def observe(
        self,
        signal_a_key: str,
        value_a: float,
        signal_b_key: str,
        value_b: float,
        timestamp: Optional[float] = None,
    ) -> None:
        """Record a paired observation of two signals.

        Key format: ``"product_id:signal_name"``.
        """
        with self._lock:
            ts = timestamp if timestamp is not None else time.time()
            pair_key = self._make_key(signal_a_key, signal_b_key)
            if pair_key not in self._observations:
                self._observations[pair_key] = []
            self._observations[pair_key].append((value_a, value_b, ts))
            obs_list = self._observations[pair_key]
            if len(obs_list) > self._max_obs_per_pair:
                self._observations[pair_key] = obs_list[-self._max_obs_per_pair :]

    @staticmethod
    def _make_key(a: str, b: str) -> str:
        return f"{a}|{b}" if a <= b else f"{b}|{a}"

    # ------------------------------------------------------------------
    # Correlation computation
    # ------------------------------------------------------------------

    def compute_correlation(
        self, signal_a_key: str, signal_b_key: str
    ) -> Optional[Correlation]:
        """Compute Pearson correlation between two signal series.

        Returns ``None`` if insufficient evidence.

        * POSITIVE if r > 0.3
        * NEGATIVE if r < −0.3
        * COMPLEMENTARY if co-occurrence > 0.7
        * confidence = min(1.0, evidence_count / 20)
        """
        with self._lock:
            pair_key = self._make_key(signal_a_key, signal_b_key)
            obs = self._observations.get(pair_key)
            if not obs or len(obs) < self._min_evidence:
                return None

            vals_a = [o[0] for o in obs]
            vals_b = [o[1] for o in obs]

            r = self._pearson(vals_a, vals_b)
            strength = abs(r)
            n = len(obs)
            confidence = min(1.0, n / 20.0)

            # Determine type
            if r > 0.3:
                ctype = CorrelationType.POSITIVE
            elif r < -0.3:
                ctype = CorrelationType.NEGATIVE
            else:
                co_occ = self._co_occurrence(vals_a, vals_b)
                if co_occ > 0.7:
                    ctype = CorrelationType.COMPLEMENTARY
                    strength = co_occ
                else:
                    ctype = CorrelationType.POSITIVE
                    strength = abs(r)

            # Canonical key order
            if signal_a_key <= signal_b_key:
                sa, sb = signal_a_key, signal_b_key
            else:
                sa, sb = signal_b_key, signal_a_key

            return Correlation(
                signal_a=sa,
                signal_b=sb,
                correlation_type=ctype,
                strength=strength,
                confidence=confidence,
                evidence_count=n,
                description=(
                    f"{ctype.value} correlation (r={r:.3f}) between "
                    f"'{sa}' and '{sb}' over {n} observations"
                ),
            )

    @staticmethod
    def _pearson(xs: list[float], ys: list[float]) -> float:
        """Manual Pearson correlation; returns 0.0 on degenerate input."""
        n = len(xs)
        if n == 0:
            return 0.0
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        denom_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
        denom_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
        denom = denom_x * denom_y
        if denom < 1e-12:
            return 0.0
        r = num / denom
        return max(-1.0, min(1.0, r))

    @staticmethod
    def _co_occurrence(xs: list[float], ys: list[float]) -> float:
        """Fraction of observations where both values are non-zero."""
        if not xs:
            return 0.0
        both = sum(1 for x, y in zip(xs, ys) if x != 0.0 and y != 0.0)
        return both / len(xs)

    # ------------------------------------------------------------------
    # Bulk & query
    # ------------------------------------------------------------------

    def compute_all_correlations(self) -> list[Correlation]:
        """Recompute all correlations from observations."""
        with self._lock:
            results: list[Correlation] = []
            for pair_key in list(self._observations):
                parts = pair_key.split("|", 1)
                if len(parts) != 2:
                    continue
                corr = self.compute_correlation(parts[0], parts[1])
                if corr is not None:
                    results.append(corr)

            results.sort(key=lambda c: c.strength, reverse=True)
            self._correlations = results[: self._max_correlations]
            return list(self._correlations)

    def get_correlations(
        self,
        product_id: Optional[str] = None,
        min_strength: float = 0.0,
    ) -> list[Correlation]:
        """Get correlations, optionally filtered by product and minimum strength."""
        with self._lock:
            results: list[Correlation] = []
            for c in self._correlations:
                if c.strength < min_strength:
                    continue
                if product_id is not None:
                    prefix = f"{product_id}:"
                    if not c.signal_a.startswith(prefix) and not c.signal_b.startswith(prefix):
                        continue
                results.append(c)
            return results

    def get_strongest_correlations(self, top_n: int = 10) -> list[Correlation]:
        """Get top N strongest correlations sorted by strength."""
        with self._lock:
            top_n = max(0, top_n)
            ranked = sorted(self._correlations, key=lambda c: c.strength, reverse=True)
            return ranked[:top_n]

    def find_temporal_correlations(
        self,
        signal_key: str,
        time_window_seconds: float = 3600,
    ) -> list[Correlation]:
        """Find signals that typically appear within *time_window* of the given signal.

        Creates TEMPORAL correlations for pairs whose observations cluster
        within the specified window.
        """
        with self._lock:
            results: list[Correlation] = []
            for pair_key, obs in self._observations.items():
                parts = pair_key.split("|", 1)
                if len(parts) != 2:
                    continue
                if signal_key not in parts:
                    continue

                # Count observations within the time window of now
                within = 0
                now = time.time()
                for _, _, ts in obs:
                    if (now - ts) <= time_window_seconds:
                        within += 1

                if within < self._min_evidence:
                    continue

                other = parts[1] if parts[0] == signal_key else parts[0]
                confidence = min(1.0, within / 20.0)
                results.append(
                    Correlation(
                        signal_a=signal_key,
                        signal_b=other,
                        correlation_type=CorrelationType.TEMPORAL,
                        strength=min(1.0, within / len(obs)),
                        confidence=confidence,
                        evidence_count=within,
                        description=(
                            f"Temporal correlation: '{signal_key}' and '{other}' "
                            f"co-occur within {time_window_seconds}s "
                            f"({within}/{len(obs)} observations)"
                        ),
                    )
                )
            return results
