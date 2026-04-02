"""Rank-fusion algorithms for combining multi-strategy recall results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .strategies import RecallResult

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

_DEFAULT_WEIGHTS: dict[str, float] = {
    "keyword": 1.0,
    "vector": 1.0,
    "graph": 1.0,
}


@dataclass
class RankedResult:
    """Final ranked result after fusion."""

    id: str
    content: str
    final_score: float
    sources: list[str]  # Which strategies found this
    strategy_scores: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------


def reciprocal_rank_fusion(
    result_lists: list[list[RecallResult]],
    k: int | None = None,
    weights: dict[str, float] | None = None,
) -> list[RankedResult]:
    """Combine multiple ranked lists using Reciprocal Rank Fusion (RRF).

    RRF score = sum(weight_i / (k + rank_i)) for each strategy i

    Args:
        result_lists: List of result lists from different strategies.
        k: RRF constant. If *None* (default), an adaptive value is computed
           as ``max(60, int(avg_results * 0.5))`` where *avg_results* is the
           average length of non-empty result lists.
        weights: Optional per-strategy weights (default: equal).

    Returns:
        Merged and re-ranked results.
    """
    if k is None:
        non_empty = [r for r in result_lists if r]
        avg_results = sum(len(r) for r in non_empty) / len(non_empty) if non_empty else 0
        k = max(60, int(avg_results * 0.5))

    w = {**_DEFAULT_WEIGHTS, **(weights or {})}

    # Accumulate scores per item id
    items: dict[str, _FusionAccum] = {}

    for results in result_lists:
        for rank, r in enumerate(results, start=1):
            if r.id not in items:
                items[r.id] = _FusionAccum(
                    id=r.id, content=r.content, metadata=r.metadata
                )
            acc = items[r.id]
            strategy_weight = w.get(r.source, 1.0)
            acc.rrf_score += strategy_weight / (k + rank)
            acc.sources.add(r.source)
            acc.strategy_scores[r.source] = r.score

    ranked = [
        RankedResult(
            id=acc.id,
            content=acc.content,
            final_score=acc.rrf_score,
            sources=sorted(acc.sources),
            strategy_scores=acc.strategy_scores,
            metadata=acc.metadata,
        )
        for acc in items.values()
    ]
    ranked.sort(key=lambda r: r.final_score, reverse=True)
    return ranked


# ---------------------------------------------------------------------------
# Weighted Score Fusion
# ---------------------------------------------------------------------------


def weighted_score_fusion(
    result_lists: list[list[RecallResult]],
    weights: dict[str, float] | None = None,
) -> list[RankedResult]:
    """Simple weighted average of scores (alternative to RRF).

    For items found by multiple strategies, average their weighted scores.
    For items found by one strategy, use that score × weight.
    """
    w = {**_DEFAULT_WEIGHTS, **(weights or {})}

    items: dict[str, _FusionAccum] = {}

    for results in result_lists:
        for r in results:
            if r.id not in items:
                items[r.id] = _FusionAccum(
                    id=r.id, content=r.content, metadata=r.metadata
                )
            acc = items[r.id]
            strategy_weight = w.get(r.source, 1.0)
            acc.weighted_sum += r.score * strategy_weight
            acc.weight_total += strategy_weight
            acc.sources.add(r.source)
            acc.strategy_scores[r.source] = r.score

    ranked = [
        RankedResult(
            id=acc.id,
            content=acc.content,
            final_score=(acc.weighted_sum / acc.weight_total)
            if acc.weight_total > 0
            else 0.0,
            sources=sorted(acc.sources),
            strategy_scores=acc.strategy_scores,
            metadata=acc.metadata,
        )
        for acc in items.values()
    ]
    ranked.sort(key=lambda r: r.final_score, reverse=True)
    return ranked


# ---------------------------------------------------------------------------
# Result diversification
# ---------------------------------------------------------------------------


def diversify_results(
    ranked: list[RankedResult],
    limit: int = 5,
    min_sources: int = 2,
) -> list[RankedResult]:
    """Ensure result diversity across sources.

    Reorders results so that:
    - Top results include at least *min_sources* different sources when possible
    - Results from underrepresented sources get a small boost
    """
    if len(ranked) <= limit:
        return ranked

    # Count source representation in top results
    selected: list[RankedResult] = []
    source_counts: dict[str, int] = {}
    remaining = list(ranked)

    while len(selected) < limit and remaining:
        # Find the best candidate, preferring underrepresented sources
        best_idx = 0
        best_score = -1.0

        for i, r in enumerate(remaining):
            diversity_bonus = 0.0
            for src in r.sources:
                if source_counts.get(src, 0) == 0:
                    diversity_bonus += 0.01  # Small boost for new source

            adjusted = r.final_score + diversity_bonus
            if adjusted > best_score:
                best_score = adjusted
                best_idx = i

        chosen = remaining.pop(best_idx)
        selected.append(chosen)
        for src in chosen.sources:
            source_counts[src] = source_counts.get(src, 0) + 1

    return selected


# ---------------------------------------------------------------------------
# Internal accumulator
# ---------------------------------------------------------------------------


@dataclass
class _FusionAccum:
    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    rrf_score: float = 0.0
    weighted_sum: float = 0.0
    weight_total: float = 0.0
    sources: set[str] = field(default_factory=set)
    strategy_scores: dict[str, float] = field(default_factory=dict)
