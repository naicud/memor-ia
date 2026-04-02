from __future__ import annotations

import math
import time

from .types import MemoryCandidate

_SECONDS_PER_DAY = 86400.0


class MemoryReplay:
    """Replays and scores memories for consolidation decisions."""

    def __init__(
        self,
        recency_halflife_days: float = 14.0,
        access_weight: float = 0.3,
        recency_weight: float = 0.3,
        importance_weight: float = 0.25,
        richness_weight: float = 0.15,
    ):
        self._halflife = recency_halflife_days
        self._w_access = access_weight
        self._w_recency = recency_weight
        self._w_importance = importance_weight
        self._w_richness = richness_weight

    def score(self, memory: MemoryCandidate, now: float = 0.0) -> float:
        """Score a single memory for consolidation. Returns 0.0-1.0."""
        if now <= 0.0:
            now = time.time()

        # Access frequency score (saturates at 10)
        access_score = min(1.0, memory.access_count / 10.0)

        # Recency decay: exp(-ln2 * age_days / halflife)
        last = memory.last_accessed if memory.last_accessed > 0 else memory.created_at
        age_days = max(0.0, (now - last) / _SECONDS_PER_DAY)
        if self._halflife > 0:
            recency = math.exp(-math.log(2) * age_days / self._halflife)
        else:
            recency = 0.0

        # Base importance
        importance = max(0.0, min(1.0, memory.importance))

        # Content richness (word count / 100, capped at 1)
        word_count = len(memory.content.split()) if memory.content else 0
        richness = min(1.0, word_count / 100.0)

        raw = (
            self._w_access * access_score
            + self._w_recency * recency
            + self._w_importance * importance
            + self._w_richness * richness
        )
        return max(0.0, min(1.0, raw))

    def score_batch(
        self, memories: list[MemoryCandidate], now: float = 0.0
    ) -> list[tuple[MemoryCandidate, float]]:
        """Score all memories. Returns list of (memory, score) sorted by score ascending."""
        if now <= 0.0:
            now = time.time()
        scored = [(m, self.score(m, now)) for m in memories]
        scored.sort(key=lambda x: x[1])
        return scored

    def find_similar_pairs(
        self, memories: list[MemoryCandidate], threshold: float = 0.85
    ) -> list[tuple[str, str, float]]:
        """Find pairs of similar memories using Jaccard similarity on words.
        Returns [(id1, id2, similarity), ...] sorted by similarity descending.
        """
        if len(memories) < 2:
            return []

        word_sets: list[tuple[str, set[str]]] = []
        for m in memories:
            words = set(m.content.lower().split()) if m.content else set()
            word_sets.append((m.memory_id, words))

        pairs: list[tuple[str, str, float]] = []
        for i in range(len(word_sets)):
            for j in range(i + 1, len(word_sets)):
                id_a, set_a = word_sets[i]
                id_b, set_b = word_sets[j]
                union_size = len(set_a | set_b)
                if union_size == 0:
                    sim = 0.0
                else:
                    sim = len(set_a & set_b) / union_size
                if sim >= threshold:
                    pairs.append((id_a, id_b, sim))

        pairs.sort(key=lambda x: x[2], reverse=True)
        return pairs
