"""ConsistencyVerifier — cross-references new entries against existing knowledge."""

import re
import threading
import time
from collections import deque
from typing import Any, Dict, List

from .types import VerificationStatus

_MAX_VERIFICATIONS = 10000


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


def _keyword_overlap(tokens_a: List[str], tokens_b: List[str]) -> float:
    if not tokens_a or not tokens_b:
        return 0.0
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    inter = set_a & set_b
    union = set_a | set_b
    return len(inter) / len(union) if union else 0.0


class ConsistencyVerifier:
    """Cross-references new entries against a knowledge base and computes trust scores."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._verifications: deque = deque(maxlen=_MAX_VERIFICATIONS)
        self._stats: Dict[str, int] = {
            "total_verifications": 0,
            "verified": 0,
            "suspicious": 0,
            "rejected": 0,
            "pending": 0,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def verify(self, content: str, knowledge_base: List[str]) -> VerificationStatus:
        """Verify *content* against a knowledge base and return a status."""
        knowledge_base = list(knowledge_base)

        with self._lock:
            self._stats["total_verifications"] += 1

        if not content:
            status = VerificationStatus.PENDING
            self._record(content, status)
            return status

        if not knowledge_base:
            status = VerificationStatus.PENDING
            self._record(content, status)
            return status

        content_tokens = _tokenize(content)
        max_overlap = 0.0
        supporting = 0

        for entry in knowledge_base:
            entry_tokens = _tokenize(entry)
            overlap = _keyword_overlap(content_tokens, entry_tokens)
            if overlap > max_overlap:
                max_overlap = overlap
            if overlap >= 0.3:
                supporting += 1

        if max_overlap >= 0.5 and supporting >= 1:
            status = VerificationStatus.VERIFIED
        elif max_overlap >= 0.2:
            status = VerificationStatus.SUSPICIOUS
        elif max_overlap > 0.0:
            status = VerificationStatus.SUSPICIOUS
        else:
            status = VerificationStatus.REJECTED

        self._record(content, status)
        return status

    def bulk_verify(
        self, contents: List[str], knowledge_base: List[str]
    ) -> Dict[str, VerificationStatus]:
        """Verify multiple content strings against a knowledge base."""
        contents = list(contents)
        knowledge_base = list(knowledge_base)
        results: Dict[str, VerificationStatus] = {}
        for c in contents:
            results[c] = self.verify(c, knowledge_base)
        return results

    def compute_trust_score(
        self, content: str, sources: List[Dict[str, Any]]
    ) -> float:
        """Compute a trust score ∈ [0, 1] based on source reliability.

        Trust factors
        -------------
        - Source count: more sources → higher base score
        - Source agreement: consensus among sources raises score
        - Source freshness: newer sources get a slight bonus
        - Content specificity: vague / very short claims get a penalty
        """
        sources = list(sources)
        if not sources:
            return 0.0
        if not content:
            return 0.0

        # --- source count factor (log-ish) ---
        count_score = min(1.0, len(sources) / 5.0)

        # --- agreement factor ---
        content_tokens = set(_tokenize(content))
        agreeing = 0
        for src in sources:
            src_text = str(src.get("text", src.get("content", "")))
            src_tokens = set(_tokenize(src_text))
            if content_tokens and src_tokens:
                overlap = len(content_tokens & src_tokens) / len(content_tokens | src_tokens)
                if overlap >= 0.3:
                    agreeing += 1
        agreement_score = agreeing / len(sources) if sources else 0.0

        # --- freshness factor ---
        now = time.time()
        freshness_scores: List[float] = []
        for src in sources:
            ts = src.get("timestamp", src.get("created_at", 0.0))
            if isinstance(ts, (int, float)) and ts > 0:
                age = max(0.0, now - ts)
                freshness_scores.append(max(0.0, 1.0 - age / (365.0 * 86400.0)))
            else:
                freshness_scores.append(0.5)
        freshness_score = sum(freshness_scores) / len(freshness_scores) if freshness_scores else 0.5

        # --- specificity factor ---
        word_count = len(content.split())
        if word_count <= 2:
            specificity_score = 0.3
        elif word_count <= 5:
            specificity_score = 0.6
        else:
            specificity_score = 1.0

        # weighted combination
        score = (
            0.30 * count_score
            + 0.30 * agreement_score
            + 0.15 * freshness_score
            + 0.25 * specificity_score
        )
        return max(0.0, min(1.0, score))

    def get_verification_stats(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._stats)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "verifications": [dict(v) for v in self._verifications],
                "stats": dict(self._stats),
            }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConsistencyVerifier":
        obj = cls()
        for v in data.get("verifications", []):
            obj._verifications.append(dict(v))
        s = data.get("stats", {})
        for k in obj._stats:
            if k in s:
                obj._stats[k] = s[k]
        return obj

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _record(self, content: str, status: VerificationStatus) -> None:
        entry = {
            "content": content[:500] if content else "",
            "status": status.value,
            "timestamp": time.time(),
        }
        with self._lock:
            self._verifications.append(entry)
            self._stats[status.value] = self._stats.get(status.value, 0) + 1
