"""Conflict detection and resolution for memories."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .dedup import jaccard_similarity

# ---------------------------------------------------------------------------
# Enums & data classes
# ---------------------------------------------------------------------------


class ConflictType(str, Enum):
    CONTRADICTION = "contradiction"
    OUTDATED = "outdated"
    REDUNDANT = "redundant"


class ResolutionStrategy(str, Enum):
    LATEST_WINS = "latest_wins"
    CONFIDENCE_WEIGHTED = "confidence_weighted"
    MANUAL = "manual"
    MERGE = "merge"


@dataclass
class Conflict:
    memory_id_1: str
    memory_id_2: str
    conflict_type: ConflictType
    confidence: float
    description: str


# ---------------------------------------------------------------------------
# Sentiment / preference keyword sets
# ---------------------------------------------------------------------------

_POSITIVE_KEYWORDS = {"likes", "loves", "prefers", "enjoys", "recommends", "uses"}
_NEGATIVE_KEYWORDS = {"hates", "dislikes", "avoids", "refuses", "rejects", "stopped using"}

_SENTIMENT_RE = re.compile(
    r"(?:^|\b)(\w+)\s+("
    + "|".join(re.escape(k) for k in sorted(_POSITIVE_KEYWORDS | _NEGATIVE_KEYWORDS, key=len, reverse=True))
    + r")\s+(.+?)(?:\.|,|$)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_subject_sentiment(text: str) -> list[tuple[str, str, str]]:
    """Extract (subject, verb, object) triples expressing sentiment/preference.

    Returns tuples of (subject_or_actor, sentiment_keyword, object).
    """
    results: list[tuple[str, str, str]] = []
    for m in _SENTIMENT_RE.finditer(text):
        actor = m.group(1).strip().lower()
        verb = m.group(2).strip().lower()
        obj = m.group(3).strip().lower().rstrip(".,;:!?")
        results.append((actor, verb, obj))
    return results


def _sentiment_polarity(verb: str) -> str:
    """Return 'positive' or 'negative' for a sentiment keyword."""
    if verb.lower() in _NEGATIVE_KEYWORDS or verb.lower().startswith("stopped"):
        return "negative"
    return "positive"


def _extract_subject(text: str) -> Optional[str]:
    """Extract a rough 'subject' from text for outdated-info comparison."""
    # Use the first noun-phrase-like segment (before a verb/preposition)
    text = text.strip().lower()
    # Simple heuristic: first N significant words
    words = re.findall(r"[a-z0-9]+", text)
    if len(words) >= 2:
        return " ".join(words[:3])
    return text if text else None


# ---------------------------------------------------------------------------
# ConflictDetector
# ---------------------------------------------------------------------------


class ConflictDetector:
    """Detect contradictions, outdated info, and redundancies among memories."""

    def __init__(self, redundancy_threshold: float = 0.9):
        self._redundancy_threshold = redundancy_threshold

    def detect_conflicts(self, memories: list[dict]) -> list[Conflict]:
        """Find contradictions, outdated info, and redundancies."""
        conflicts: list[Conflict] = []
        n = len(memories)

        # Pre-extract sentiments for contradiction detection
        sentiments: list[list[tuple[str, str, str]]] = [
            _extract_subject_sentiment(m.get("content", "")) for m in memories
        ]

        for i in range(n):
            for j in range(i + 1, n):
                id1 = memories[i].get("id", str(i))
                id2 = memories[j].get("id", str(j))
                c1 = memories[i].get("content", "")
                c2 = memories[j].get("content", "")

                # --- CONTRADICTION ---
                contradiction = self._check_contradiction(
                    sentiments[i], sentiments[j], id1, id2
                )
                if contradiction:
                    conflicts.append(contradiction)
                    continue  # don't double-flag

                # --- REDUNDANT (very high similarity) ---
                sim = jaccard_similarity(c1, c2)
                if sim >= self._redundancy_threshold:
                    conflicts.append(
                        Conflict(
                            memory_id_1=id1,
                            memory_id_2=id2,
                            conflict_type=ConflictType.REDUNDANT,
                            confidence=sim,
                            description=f"Memories are {sim:.0%} similar",
                        )
                    )
                    continue

                # --- OUTDATED ---
                outdated = self._check_outdated(memories[i], memories[j], id1, id2)
                if outdated:
                    conflicts.append(outdated)

        return conflicts

    def resolve(
        self,
        conflict: Conflict,
        strategy: ResolutionStrategy,
        memories: dict[str, dict],
    ) -> dict:
        """Resolve a conflict and return the winning memory."""
        mem1 = memories.get(conflict.memory_id_1, {})
        mem2 = memories.get(conflict.memory_id_2, {})

        if strategy == ResolutionStrategy.LATEST_WINS:
            ts1 = mem1.get("created_at", "")
            ts2 = mem2.get("created_at", "")
            return mem2 if ts2 > ts1 else mem1

        if strategy == ResolutionStrategy.CONFIDENCE_WEIGHTED:
            meta1 = mem1.get("metadata") or {}
            meta2 = mem2.get("metadata") or {}
            c1 = float(meta1.get("confidence", 0.5))
            c2 = float(meta2.get("confidence", 0.5))
            return mem2 if c2 > c1 else mem1

        if strategy == ResolutionStrategy.MERGE:
            from .dedup import MemoryDeduplicator

            dedup = MemoryDeduplicator()
            return dedup.merge_memories(mem1, mem2)

        # MANUAL — return both as a merged dict signalling manual review
        return {
            "id": conflict.memory_id_1,
            "content": mem1.get("content", ""),
            "metadata": {
                **(mem1.get("metadata") or {}),
                "needs_review": True,
                "conflict_with": conflict.memory_id_2,
            },
        }

    # ------------------------------------------------------------------
    # Internal checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_contradiction(
        sents1: list[tuple[str, str, str]],
        sents2: list[tuple[str, str, str]],
        id1: str,
        id2: str,
    ) -> Optional[Conflict]:
        """Check if two memories express opposing sentiments about the same object."""
        for actor1, verb1, obj1 in sents1:
            pol1 = _sentiment_polarity(verb1)
            for actor2, verb2, obj2 in sents2:
                pol2 = _sentiment_polarity(verb2)
                if obj1 == obj2 and pol1 != pol2:
                    return Conflict(
                        memory_id_1=id1,
                        memory_id_2=id2,
                        conflict_type=ConflictType.CONTRADICTION,
                        confidence=0.8,
                        description=(
                            f"Opposing sentiments about '{obj1}': "
                            f"'{verb1}' vs '{verb2}'"
                        ),
                    )
        return None

    @staticmethod
    def _check_outdated(
        mem1: dict, mem2: dict, id1: str, id2: str
    ) -> Optional[Conflict]:
        """Check if one memory supersedes the other (same subject, different timestamps)."""
        ts1 = mem1.get("created_at", "")
        ts2 = mem2.get("created_at", "")
        if not ts1 or not ts2 or ts1 == ts2:
            return None

        subj1 = _extract_subject(mem1.get("content", ""))
        subj2 = _extract_subject(mem2.get("content", ""))
        if not subj1 or not subj2:
            return None

        # Subjects must overlap significantly
        sim = jaccard_similarity(subj1, subj2)
        if sim < 0.5:
            return None

        older_id = id1 if ts1 < ts2 else id2
        newer_id = id2 if ts1 < ts2 else id1
        return Conflict(
            memory_id_1=older_id,
            memory_id_2=newer_id,
            conflict_type=ConflictType.OUTDATED,
            confidence=sim,
            description=f"Memory '{older_id}' may be outdated by '{newer_id}'",
        )
