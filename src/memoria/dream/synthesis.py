from __future__ import annotations

from collections import Counter

from .types import InsightSeed, MemoryCandidate

_STOP_WORDS = frozenset(
    {"a", "the", "is", "in", "to", "of", "and", "or", "for", "with", "on", "at", "by"}
)


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from text, removing stop words."""
    words = text.lower().split()
    return [w for w in words if w not in _STOP_WORDS and len(w) > 1]


class InsightSynthesizer:
    """Discovers connections and patterns across memories during dream."""

    def __init__(self, max_insights: int = 10):
        self._max = max_insights

    def synthesize(
        self,
        memories: list[MemoryCandidate],
        scores: dict[str, float],
    ) -> list[InsightSeed]:
        """Generate insights from memory collection."""
        if not memories:
            return []
        insights: list[InsightSeed] = []
        insights.extend(self._find_topic_clusters(memories))
        insights.extend(self._find_knowledge_gaps(memories, scores))
        insights.extend(self._find_temporal_patterns(memories))
        insights.extend(self._generate_predictions(memories, scores))
        return insights[: self._max]

    def _find_topic_clusters(
        self, memories: list[MemoryCandidate]
    ) -> list[InsightSeed]:
        """Find groups of memories about the same topic via keyword co-occurrence."""
        if len(memories) < 2:
            return []

        # Map keywords → memory ids
        keyword_to_ids: dict[str, list[str]] = {}
        for m in memories:
            for kw in _extract_keywords(m.content):
                keyword_to_ids.setdefault(kw, []).append(m.memory_id)

        insights: list[InsightSeed] = []
        seen_groups: set[frozenset[str]] = set()
        for kw, ids in sorted(keyword_to_ids.items(), key=lambda x: -len(x[1])):
            if len(ids) < 2:
                continue
            group = frozenset(ids)
            if group in seen_groups:
                continue
            seen_groups.add(group)
            insights.append(
                InsightSeed(
                    title=f"Topic cluster: '{kw}'",
                    description=f"{len(ids)} memories share the keyword '{kw}'",
                    insight_type="connection",
                    confidence=min(1.0, len(ids) / 5.0),
                    source_memories=list(ids),
                    suggested_action=f"Review cluster around '{kw}'",
                )
            )
        return insights

    def _find_knowledge_gaps(
        self,
        memories: list[MemoryCandidate],
        scores: dict[str, float],
    ) -> list[InsightSeed]:
        """Identify topics with few memories or consistently low scores."""
        if not memories:
            return []

        # Group by tier
        tier_counts: Counter[str] = Counter()
        tier_scores: dict[str, list[float]] = {}
        for m in memories:
            tier_counts[m.tier] += 1
            tier_scores.setdefault(m.tier, []).append(scores.get(m.memory_id, 0.0))

        insights: list[InsightSeed] = []
        for tier, score_list in tier_scores.items():
            avg = sum(score_list) / len(score_list)
            if avg < 0.4:
                ids = [m.memory_id for m in memories if m.tier == tier]
                insights.append(
                    InsightSeed(
                        title=f"Knowledge gap in tier '{tier}'",
                        description=(
                            f"Average score {avg:.2f} across {len(score_list)} memories "
                            f"in tier '{tier}' is below threshold"
                        ),
                        insight_type="gap",
                        confidence=min(1.0, 1.0 - avg),
                        source_memories=ids,
                        suggested_action=f"Add more high-quality memories to tier '{tier}'",
                    )
                )
        return insights

    def _find_temporal_patterns(
        self, memories: list[MemoryCandidate]
    ) -> list[InsightSeed]:
        """Detect time-based patterns in memory creation."""
        dated = [m for m in memories if m.created_at > 0]
        if len(dated) < 2:
            return []

        sorted_mems = sorted(dated, key=lambda m: m.created_at)

        # Look for bursts: multiple memories created close together
        burst_threshold = 3600.0  # 1 hour
        bursts: list[list[MemoryCandidate]] = []
        current_burst: list[MemoryCandidate] = [sorted_mems[0]]

        for m in sorted_mems[1:]:
            if m.created_at - current_burst[-1].created_at <= burst_threshold:
                current_burst.append(m)
            else:
                if len(current_burst) >= 2:
                    bursts.append(current_burst)
                current_burst = [m]
        if len(current_burst) >= 2:
            bursts.append(current_burst)

        insights: list[InsightSeed] = []
        for burst in bursts:
            ids = [m.memory_id for m in burst]
            insights.append(
                InsightSeed(
                    title=f"Activity burst: {len(burst)} memories",
                    description=(
                        f"{len(burst)} memories created within a short time window"
                    ),
                    insight_type="pattern",
                    confidence=min(1.0, len(burst) / 5.0),
                    source_memories=ids,
                    suggested_action="Review burst for related context",
                )
            )
        return insights

    def _generate_predictions(
        self,
        memories: list[MemoryCandidate],
        scores: dict[str, float],
    ) -> list[InsightSeed]:
        """Predict what user might need next based on high-scoring patterns."""
        if not memories:
            return []

        # Find top keywords from high-scoring memories
        high_score = [m for m in memories if scores.get(m.memory_id, 0) >= 0.7]
        if not high_score:
            return []

        kw_counter: Counter[str] = Counter()
        for m in high_score:
            kw_counter.update(_extract_keywords(m.content))

        insights: list[InsightSeed] = []
        for kw, count in kw_counter.most_common(3):
            if count < 2:
                continue
            ids = [
                m.memory_id
                for m in high_score
                if kw in _extract_keywords(m.content)
            ]
            insights.append(
                InsightSeed(
                    title=f"Predicted focus: '{kw}'",
                    description=(
                        f"Keyword '{kw}' appears in {count} high-scoring memories"
                    ),
                    insight_type="prediction",
                    confidence=min(1.0, count / 5.0),
                    source_memories=ids,
                    suggested_action=f"Prepare resources related to '{kw}'",
                )
            )
        return insights
