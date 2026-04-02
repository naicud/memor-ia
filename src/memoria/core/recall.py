"""Query-time relevant memory retrieval using keyword matching."""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .scanner import MemoryHeader, scan_memory_files
from .paths import AUTO_MEM_ENTRYPOINT_NAME

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_RELEVANT = 5

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RelevantMemory:
    path: str
    mtime_ms: float
    score: float


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_relevant_memories(
    query: str,
    memory_dir: str | Path,
    already_surfaced: Optional[set[str]] = None,
) -> list[RelevantMemory]:
    """Find memory files most relevant to *query* via keyword overlap.

    * Excludes ``MEMORY.md`` (already in system prompt).
    * Filters out paths in *already_surfaced*.
    * Returns at most ``MAX_RELEVANT`` results, sorted by score descending.

    For collections with ≥50 headers an inverted index with BM25 scoring is
    used instead of the original Jaccard scan.  The index is cached per
    *memory_dir* and invalidated when any file mtime changes.
    """
    if not query.strip():
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    already = already_surfaced or set()
    headers = scan_memory_files(memory_dir)

    # Filter out entrypoint and already-surfaced before scoring
    eligible = [
        h
        for h in headers
        if h.filename != AUTO_MEM_ENTRYPOINT_NAME and h.file_path not in already
    ]

    if len(headers) >= _INDEX_THRESHOLD:
        return _search_with_index(
            query_tokens, eligible, str(memory_dir), headers
        )

    return _search_jaccard(query_tokens, eligible)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    """Extract lowercase alphanumeric tokens, ignoring short noise words."""
    words = set(_WORD_RE.findall(text.lower()))
    # Filter out very short tokens (≤2 chars) to reduce noise
    return {w for w in words if len(w) > 2}


# Threshold above which we switch from Jaccard to the inverted index.
_INDEX_THRESHOLD = 50

# Module-level index cache keyed by memory_dir path string.
# Typed as Any here; actual values are (fingerprint_dict, InvertedKeywordIndex).
_index_cache: dict[str, tuple] = {}
_INDEX_CACHE_MAX = 16


def _search_jaccard(
    query_tokens: set[str],
    eligible: list[MemoryHeader],
) -> list[RelevantMemory]:
    """Original O(n×m) Jaccard scan — used for small collections."""
    scored: list[RelevantMemory] = []
    for header in eligible:
        candidate_text = f"{header.filename} {header.description or ''}"
        candidate_tokens = _tokenize(candidate_text)
        if not candidate_tokens:
            continue

        overlap = query_tokens & candidate_tokens
        if not overlap:
            continue

        score = len(overlap) / len(query_tokens)
        scored.append(
            RelevantMemory(
                path=header.file_path,
                mtime_ms=header.mtime_ms,
                score=score,
            )
        )

    scored.sort(key=lambda r: r.score, reverse=True)
    return scored[:MAX_RELEVANT]


def _mtime_fingerprint(headers: list[MemoryHeader]) -> dict[str, float]:
    """Return {file_path: mtime_ms} for cache invalidation."""
    return {h.file_path: h.mtime_ms for h in headers}


def _search_with_index(
    query_tokens: set[str],
    eligible: list[MemoryHeader],
    cache_key: str,
    all_headers: list[MemoryHeader],
) -> list[RelevantMemory]:
    """Build (or reuse) an inverted index and search with BM25."""
    fingerprint = _mtime_fingerprint(all_headers)

    cached = _index_cache.get(cache_key)
    if cached is not None:
        old_fp, idx = cached
        if old_fp != fingerprint:
            cached = None

    if cached is None:
        idx = InvertedKeywordIndex()
        idx.build(all_headers)
        # Evict oldest entry if cache is full
        if len(_index_cache) >= _INDEX_CACHE_MAX:
            oldest_key = next(iter(_index_cache))
            del _index_cache[oldest_key]
        _index_cache[cache_key] = (fingerprint, idx)

    # Eligible doc_ids for filtering
    eligible_ids = {h.file_path for h in eligible}
    return idx.search(query_tokens, limit=MAX_RELEVANT, eligible=eligible_ids)


# ---------------------------------------------------------------------------
# InvertedKeywordIndex with BM25 scoring
# ---------------------------------------------------------------------------


class InvertedKeywordIndex:
    """Pre-built inverted index for fast keyword search with BM25 scoring."""

    def __init__(self) -> None:
        self._index: dict[str, list[tuple[str, float]]] = {}  # token → [(doc_id, tf)]
        self._doc_lengths: dict[str, int] = {}
        self._doc_data: dict[str, tuple[float, str]] = {}  # doc_id → (mtime_ms, file_path)
        self._filename_tokens: dict[str, set[str]] = {}  # doc_id → filename tokens
        self._avg_doc_len: float = 0.0
        self._doc_count: int = 0

    # BM25 tuning parameters
    _K1 = 1.5
    _B = 0.75

    def build(self, headers: list[MemoryHeader]) -> None:
        """Build index from a list of :class:`MemoryHeader` objects."""
        self._index.clear()
        self._doc_lengths.clear()
        self._doc_data.clear()
        self._filename_tokens.clear()

        total_len = 0
        for header in headers:
            doc_id = header.file_path
            self._doc_data[doc_id] = (header.mtime_ms, header.file_path)

            candidate_text = f"{header.filename} {header.description or ''}"
            tokens_list = _WORD_RE.findall(candidate_text.lower())
            tokens_list = [t for t in tokens_list if len(t) > 2]

            self._filename_tokens[doc_id] = _tokenize(header.filename)

            doc_len = len(tokens_list)
            self._doc_lengths[doc_id] = doc_len
            total_len += doc_len

            # Compute term frequencies
            tf_map: dict[str, int] = {}
            for token in tokens_list:
                tf_map[token] = tf_map.get(token, 0) + 1

            for token, count in tf_map.items():
                tf = count / doc_len if doc_len > 0 else 0.0
                if token not in self._index:
                    self._index[token] = []
                self._index[token].append((doc_id, tf))

        self._doc_count = len(headers)
        self._avg_doc_len = total_len / self._doc_count if self._doc_count > 0 else 0.0

    def search(
        self,
        query_tokens: set[str],
        limit: int = MAX_RELEVANT,
        recency_weight: float = 0.1,
        eligible: set[str] | None = None,
    ) -> list[RelevantMemory]:
        """BM25 search with filename boost and recency boost."""
        if not query_tokens or self._doc_count == 0:
            return []

        now_ms = time.time() * 1000.0
        scores: dict[str, float] = {}
        N = self._doc_count
        k1 = self._K1
        b = self._B
        avgdl = self._avg_doc_len

        for token in query_tokens:
            postings = self._index.get(token)
            if postings is None:
                continue

            n_t = len(postings)
            idf = math.log((N - n_t + 0.5) / (n_t + 0.5) + 1.0)

            for doc_id, tf in postings:
                if eligible is not None and doc_id not in eligible:
                    continue
                dl = self._doc_lengths.get(doc_id, 0)
                denom = tf + k1 * (1.0 - b + b * dl / avgdl) if avgdl > 0 else tf + k1
                term_score = idf * (tf * (k1 + 1.0)) / (denom if denom != 0 else 1.0)

                # Filename boost
                fn_tokens = self._filename_tokens.get(doc_id, set())
                if token in fn_tokens:
                    term_score *= 1.3

                scores[doc_id] = scores.get(doc_id, 0.0) + term_score

        # Recency boost
        results: list[RelevantMemory] = []
        for doc_id, score in scores.items():
            mtime_ms, file_path = self._doc_data[doc_id]
            age_days = max((now_ms - mtime_ms) / 86_400_000.0, 0.0)
            boosted = score * (1.0 + recency_weight * math.exp(-age_days / 30.0))
            results.append(
                RelevantMemory(path=file_path, mtime_ms=mtime_ms, score=boosted)
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]
