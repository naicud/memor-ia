"""Context-aware filtering and deduplication of recall results."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from .ranker import RankedResult

# ---------------------------------------------------------------------------
# Context descriptor
# ---------------------------------------------------------------------------


@dataclass
class RecallContext:
    """Context for filtering recall results."""

    user_id: str | None = None
    session_id: str | None = None
    agent_id: str | None = None
    project_path: str | None = None
    current_topic: str | None = None
    excluded_ids: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

# 30 days in milliseconds
_STALE_MS = 30 * 24 * 60 * 60 * 1000

_PROJECT_BOOST = 1.15
_USER_BOOST = 1.10
_STALE_PENALTY = 0.80


def filter_by_context(
    results: list[RankedResult],
    context: RecallContext,
) -> list[RankedResult]:
    """Filter and re-score results based on context.

    Rules:
    - Remove excluded_ids
    - Boost results matching current project
    - Boost results from same user_id
    - Demote stale results (older than 30 days)
    """
    if not results:
        return []

    now_ms = time.time() * 1000
    filtered: list[RankedResult] = []

    for r in results:
        if r.id in context.excluded_ids:
            continue

        score = r.final_score

        # Boost for matching project path
        if context.project_path:
            item_project = r.metadata.get("project_path", "")
            if item_project and context.project_path in str(item_project):
                score *= _PROJECT_BOOST

        # Boost for matching user
        if context.user_id:
            item_user = r.metadata.get("user_id", "")
            if item_user and item_user == context.user_id:
                score *= _USER_BOOST

        # Demote stale items
        mtime = r.metadata.get("mtime_ms")
        if mtime is not None:
            try:
                age_ms = now_ms - float(mtime)
                if age_ms > _STALE_MS:
                    score *= _STALE_PENALTY
            except (TypeError, ValueError):
                pass

        filtered.append(
            RankedResult(
                id=r.id,
                content=r.content,
                final_score=score,
                sources=r.sources,
                strategy_scores=r.strategy_scores,
                metadata=r.metadata,
            )
        )

    filtered.sort(key=lambda r: r.final_score, reverse=True)
    return filtered


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def deduplicate(
    results: list[RankedResult],
    similarity_threshold: float = 0.9,
) -> list[RankedResult]:
    """Remove near-duplicate results based on content similarity.

    Uses token-level Jaccard similarity for lightweight dedup.
    Keeps the first (highest-scored) occurrence.
    """
    if not results:
        return []

    kept: list[RankedResult] = []
    kept_tokens: list[set[str]] = []

    for r in results:
        tokens = _tokenize(r.content)
        is_dup = False
        for existing in kept_tokens:
            sim = _jaccard(tokens, existing)
            if sim >= similarity_threshold:
                is_dup = True
                break
        if not is_dup:
            kept.append(r)
            kept_tokens.append(tokens)

    return kept


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
