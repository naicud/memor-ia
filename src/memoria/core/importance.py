"""Memory importance scoring — multi-signal importance computation.

Computes importance score (0-1) for memories using:
- Frequency: how often the memory is accessed/recalled
- Recency: when was the memory last accessed
- Relevance: semantic similarity to current context
- Connections: how many graph connections this memory has
- Explicit boost: user/agent manually marked as important
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field


@dataclass
class ImportanceSignals:
    """Raw signals used to compute importance."""

    access_count: int = 0
    last_accessed: float = 0.0
    created_at: float = field(default_factory=time.time)
    connection_count: int = 0
    explicit_boost: float = 0.0  # -1 to +1 manual adjustment
    relevance_score: float = 0.0  # 0-1 from last search
    word_count: int = 0
    has_entities: bool = False
    referenced_by_count: int = 0


class ImportanceScorer:
    """Multi-signal importance scorer for memories.

    Combines multiple signals into a single 0-1 importance score.
    Configurable weights allow tuning for different use cases.
    """

    def __init__(
        self,
        frequency_weight: float = 0.25,
        recency_weight: float = 0.30,
        relevance_weight: float = 0.25,
        connectivity_weight: float = 0.10,
        richness_weight: float = 0.10,
        recency_half_life_days: float = 14.0,
    ):
        total = (
            frequency_weight
            + recency_weight
            + relevance_weight
            + connectivity_weight
            + richness_weight
        )
        if total <= 0:
            raise ValueError("Weights must sum to a positive value")
        # Normalise so weights always sum to 1.0
        self._weights = {
            "frequency": frequency_weight / total,
            "recency": recency_weight / total,
            "relevance": relevance_weight / total,
            "connectivity": connectivity_weight / total,
            "richness": richness_weight / total,
        }
        self._half_life = recency_half_life_days

    # -- public API ----------------------------------------------------------

    def score(self, signals: ImportanceSignals) -> float:
        """Compute composite importance score (0-1)."""
        freq = self._frequency_score(signals.access_count)
        rec = self._recency_score(signals.last_accessed)
        rel = signals.relevance_score
        conn = self._connectivity_score(
            signals.connection_count, signals.referenced_by_count
        )
        rich = self._richness_score(
            signals.word_count, signals.has_entities, signals.referenced_by_count
        )

        composite = (
            self._weights["frequency"] * freq
            + self._weights["recency"] * rec
            + self._weights["relevance"] * rel
            + self._weights["connectivity"] * conn
            + self._weights["richness"] * rich
        )

        # Apply explicit boost and clamp
        composite += signals.explicit_boost * 0.3
        # Guard against NaN/Inf (max/min don't clamp NaN in Python)
        if not math.isfinite(composite):
            composite = 0.0
        return max(0.0, min(1.0, composite))

    def score_batch(self, signals_list: list[ImportanceSignals]) -> list[float]:
        """Score multiple memories efficiently."""
        return [self.score(s) for s in signals_list]

    def should_forget(
        self, signals: ImportanceSignals, threshold: float = 0.05
    ) -> bool:
        """Determine if a memory should be forgotten (below threshold)."""
        return self.score(signals) < threshold

    def should_compress(
        self, signals: ImportanceSignals, threshold: float = 0.15
    ) -> bool:
        """Determine if a memory should be compressed (low but not forgettable)."""
        s = self.score(signals)
        return s >= 0.05 and s < threshold

    def should_promote(
        self, signals: ImportanceSignals, threshold: float = 0.7
    ) -> bool:
        """Determine if a memory should be promoted to a higher tier."""
        return self.score(signals) >= threshold

    # -- internal scoring components -----------------------------------------

    @staticmethod
    def _frequency_score(access_count: int) -> float:
        """Logarithmic frequency: saturates around 20 accesses."""
        if access_count <= 0:
            return 0.0
        return min(1.0, math.log(1 + access_count) / math.log(1 + 20))

    def _recency_score(self, last_accessed: float) -> float:
        """Exponential decay with configurable half-life."""
        if last_accessed <= 0:
            return 0.0
        age_seconds = max(0.0, time.time() - last_accessed)
        age_days = age_seconds / 86400.0
        if self._half_life <= 0:
            return 0.0
        decay = math.exp(-0.693 * age_days / self._half_life)
        return decay

    @staticmethod
    def _connectivity_score(connection_count: int, referenced_by: int = 0) -> float:
        """Logarithmic connectivity score."""
        total = connection_count + referenced_by
        if total <= 0:
            return 0.0
        return min(1.0, math.log(1 + total) / math.log(1 + 10))

    @staticmethod
    def _richness_score(
        word_count: int, has_entities: bool, referenced_by_count: int
    ) -> float:
        """Content richness based on size, entities, and references."""
        # word_count contribution: 0-1, saturates around 200 words
        wc = min(1.0, word_count / 200.0) if word_count > 0 else 0.0
        ent = 0.3 if has_entities else 0.0
        ref = min(0.3, referenced_by_count * 0.1)
        return min(1.0, wc * 0.4 + ent + ref)


@dataclass
class ImportanceTracker:
    """Track importance signals for memories over time."""

    _signals: dict[str, ImportanceSignals] = field(default_factory=dict)

    def record_access(self, memory_id: str) -> None:
        """Record that a memory was accessed."""
        sig = self._ensure(memory_id)
        sig.access_count += 1
        sig.last_accessed = time.time()

    def record_creation(
        self, memory_id: str, word_count: int = 0, has_entities: bool = False
    ) -> None:
        """Record memory creation."""
        now = time.time()
        self._signals[memory_id] = ImportanceSignals(
            access_count=0,
            last_accessed=now,
            created_at=now,
            word_count=word_count,
            has_entities=has_entities,
        )

    def set_explicit_boost(self, memory_id: str, boost: float) -> None:
        """Set explicit importance boost (-1 to +1)."""
        sig = self._ensure(memory_id)
        sig.explicit_boost = max(-1.0, min(1.0, boost))

    def set_relevance(self, memory_id: str, relevance: float) -> None:
        """Update relevance score from last search."""
        sig = self._ensure(memory_id)
        sig.relevance_score = max(0.0, min(1.0, relevance))

    def set_connections(self, memory_id: str, count: int) -> None:
        """Update connection count from knowledge graph."""
        sig = self._ensure(memory_id)
        sig.connection_count = max(0, count)

    def get_signals(self, memory_id: str) -> ImportanceSignals:
        """Get signals for a memory (creates default if not tracked)."""
        return self._ensure(memory_id)

    def get_all_signals(self) -> dict[str, ImportanceSignals]:
        """Get all tracked signals."""
        return dict(self._signals)

    def remove(self, memory_id: str) -> None:
        """Stop tracking a memory."""
        self._signals.pop(memory_id, None)

    # -- internal ------------------------------------------------------------

    def _ensure(self, memory_id: str) -> ImportanceSignals:
        if memory_id not in self._signals:
            self._signals[memory_id] = ImportanceSignals()
        return self._signals[memory_id]
