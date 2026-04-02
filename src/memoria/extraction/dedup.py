"""Memory deduplication using Jaccard word-overlap similarity."""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Similarity helpers
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> set[str]:
    """Lowercase word-tokenize, stripping punctuation."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def jaccard_similarity(text1: str, text2: str) -> float:
    """Compute Jaccard similarity between two texts (word-level)."""
    tokens1 = _tokenize(text1)
    tokens2 = _tokenize(text2)
    if not tokens1 and not tokens2:
        return 1.0
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1 & tokens2
    union = tokens1 | tokens2
    return len(intersection) / len(union)


# ---------------------------------------------------------------------------
# MemoryDeduplicator
# ---------------------------------------------------------------------------


class MemoryDeduplicator:
    """Detect and remove duplicate memories using word-overlap similarity."""

    def __init__(self, similarity_threshold: float = 0.85):
        self._threshold = similarity_threshold

    def is_duplicate(self, content1: str, content2: str) -> bool:
        """Check if two memories are semantically similar."""
        return jaccard_similarity(content1, content2) >= self._threshold

    def find_duplicates(
        self, memories: list[dict]
    ) -> list[tuple[str, str, float]]:
        """Find all duplicate pairs with similarity scores.

        Returns a list of (memory_id_1, memory_id_2, similarity) tuples.
        """
        duplicates: list[tuple[str, str, float]] = []
        n = len(memories)
        for i in range(n):
            for j in range(i + 1, n):
                c1 = memories[i].get("content", "")
                c2 = memories[j].get("content", "")
                sim = jaccard_similarity(c1, c2)
                if sim >= self._threshold:
                    id1 = memories[i].get("id", str(i))
                    id2 = memories[j].get("id", str(j))
                    duplicates.append((id1, id2, sim))
        return duplicates

    def merge_memories(self, mem1: dict, mem2: dict) -> dict:
        """Merge two memories keeping the richer content.

        Picks the memory with more content as the base, then merges metadata.
        """
        c1 = mem1.get("content", "")
        c2 = mem2.get("content", "")
        # Base is the one with longer content
        if len(c2) > len(c1):
            base, other = mem2.copy(), mem1
        else:
            base, other = mem1.copy(), mem2

        # Merge metadata
        base_meta = dict(base.get("metadata") or {})
        other_meta = dict(other.get("metadata") or {})
        for k, v in other_meta.items():
            if k not in base_meta:
                base_meta[k] = v
        base["metadata"] = base_meta

        # Keep the earlier created_at
        ts1 = mem1.get("created_at", "")
        ts2 = mem2.get("created_at", "")
        if ts1 and ts2:
            base["created_at"] = min(ts1, ts2)
        elif ts1 or ts2:
            base["created_at"] = ts1 or ts2

        return base

    def deduplicate(self, memories: list[dict]) -> list[dict]:
        """Remove duplicates from a list, keeping the best version.

        Uses a greedy approach: iterate through memories, merging duplicates
        into the first occurrence.
        """
        if not memories:
            return []

        # Track which indices have been consumed by a merge
        consumed: set[int] = set()
        result: list[dict] = []

        for i in range(len(memories)):
            if i in consumed:
                continue
            merged = memories[i].copy()
            for j in range(i + 1, len(memories)):
                if j in consumed:
                    continue
                c1 = merged.get("content", "")
                c2 = memories[j].get("content", "")
                if jaccard_similarity(c1, c2) >= self._threshold:
                    merged = self.merge_memories(merged, memories[j])
                    consumed.add(j)
            result.append(merged)

        return result
