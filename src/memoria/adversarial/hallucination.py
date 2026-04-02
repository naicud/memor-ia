"""HallucinationGuard — detects hallucinated / fabricated content."""

import re
import threading
import time
from collections import deque
from typing import Any, Dict, List, Optional

from .types import ConsistencyReport

_MAX_FACTS = 5000
_MAX_HISTORY = 10000

_ANTONYM_PAIRS = [
    ("good", "bad"),
    ("true", "false"),
    ("yes", "no"),
    ("increase", "decrease"),
    ("up", "down"),
    ("open", "close"),
    ("hot", "cold"),
    ("fast", "slow"),
    ("big", "small"),
    ("high", "low"),
    ("start", "stop"),
    ("begin", "end"),
    ("success", "failure"),
    ("win", "lose"),
    ("positive", "negative"),
    ("accept", "reject"),
    ("allow", "deny"),
    ("enable", "disable"),
    ("include", "exclude"),
    ("safe", "dangerous"),
]

_ANTONYM_MAP: Dict[str, str] = {}
for a, b in _ANTONYM_PAIRS:
    _ANTONYM_MAP[a] = b
    _ANTONYM_MAP[b] = a


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


def _extract_numbers(text: str) -> List[str]:
    return re.findall(r"\b\d+(?:\.\d+)?\b", text)


def _keyword_overlap(tokens_a: List[str], tokens_b: List[str]) -> float:
    if not tokens_a or not tokens_b:
        return 0.0
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


class HallucinationGuard:
    """Detects hallucinated / fabricated content by checking consistency with known facts."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._facts: deque = deque(maxlen=_MAX_FACTS)
        self._contradiction_history: deque = deque(maxlen=_MAX_HISTORY)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_consistency(
        self, new_content: str, existing_facts: List[str]
    ) -> ConsistencyReport:
        """Check whether *new_content* contradicts any of *existing_facts*."""
        existing_facts = list(existing_facts)
        contradictions: List[Dict[str, Any]] = []

        if not new_content or not existing_facts:
            return ConsistencyReport(
                is_consistent=True,
                contradictions=[],
                confidence=1.0,
                checked_against=len(existing_facts),
            )

        new_tokens = _tokenize(new_content)

        for fact in existing_facts:
            fact_tokens = _tokenize(fact)
            overlap = _keyword_overlap(new_tokens, fact_tokens)
            if overlap < 0.15:
                continue

            cinfo = self._detect_contradiction(new_content, fact, new_tokens, fact_tokens)
            if cinfo is not None:
                contradictions.append(cinfo)

        is_consistent = len(contradictions) == 0
        confidence = max(0.0, 1.0 - len(contradictions) * 0.25)

        report = ConsistencyReport(
            is_consistent=is_consistent,
            contradictions=list(contradictions),
            confidence=confidence,
            checked_against=len(existing_facts),
        )

        if contradictions:
            with self._lock:
                for c in contradictions:
                    self._contradiction_history.append(c)

        return report

    def register_fact(
        self, fact: str, source: str = "", confidence: float = 1.0
    ) -> None:
        """Register a known fact."""
        entry = {
            "fact": fact,
            "source": source,
            "confidence": confidence,
            "registered_at": time.time(),
        }
        with self._lock:
            self._facts.append(entry)

    def check_against_facts(self, content: str) -> ConsistencyReport:
        """Check *content* against all registered facts."""
        with self._lock:
            facts = [f["fact"] for f in self._facts]
        return self.check_consistency(content, facts)

    def get_contradiction_history(self) -> List[Dict]:
        """Return the history of detected contradictions."""
        with self._lock:
            return [dict(c) for c in self._contradiction_history]

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            facts_list = [dict(f) for f in self._facts]
            history_list = [dict(c) for c in self._contradiction_history]
        return {
            "facts": facts_list,
            "contradiction_history": history_list,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HallucinationGuard":
        obj = cls()
        for f in data.get("facts", []):
            obj._facts.append(dict(f))
        for c in data.get("contradiction_history", []):
            obj._contradiction_history.append(dict(c))
        return obj

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect_contradiction(
        self,
        new_text: str,
        fact_text: str,
        new_tokens: List[str],
        fact_tokens: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Return a contradiction dict if *new_text* contradicts *fact_text*, else None."""

        # 1. Negation detection  ("X is Y" vs "X is not Y")
        neg = self._check_negation(new_text, fact_text)
        if neg:
            return neg

        # 2. Temporal contradiction  ("X in 2020" vs "X in 2019") — before numeric
        temp = self._check_temporal(new_text, fact_text, new_tokens, fact_tokens)
        if temp:
            return temp

        # 3. Numeric contradiction  ("X is 5" vs "X is 10")
        num = self._check_numeric(new_text, fact_text, new_tokens, fact_tokens)
        if num:
            return num

        # 4. Antonym detection
        ant = self._check_antonyms(new_text, fact_text, new_tokens, fact_tokens)
        if ant:
            return ant

        return None

    @staticmethod
    def _check_negation(new_text: str, fact_text: str) -> Optional[Dict[str, Any]]:
        new_lower = new_text.lower().strip()
        fact_lower = fact_text.lower().strip()

        # "X is not Y" vs "X is Y"  or  "X isn't Y" vs "X is Y"
        neg_patterns = [
            (r"(.+?)\s+is\s+not\s+(.+)", r"(.+?)\s+is\s+(.+)"),
            (r"(.+?)\s+isn'?t\s+(.+)", r"(.+?)\s+is\s+(.+)"),
            (r"(.+?)\s+does\s+not\s+(.+)", r"(.+?)\s+does\s+(.+)"),
            (r"(.+?)\s+doesn'?t\s+(.+)", r"(.+?)\s+does\s+(.+)"),
        ]

        for neg_pat, pos_pat in neg_patterns:
            m_neg_new = re.match(neg_pat, new_lower)
            m_pos_fact = re.match(pos_pat, fact_lower)
            if m_neg_new and m_pos_fact:
                subj_new = m_neg_new.group(1).strip()
                subj_fact = m_pos_fact.group(1).strip()
                if _keyword_overlap(_tokenize(subj_new), _tokenize(subj_fact)) >= 0.5:
                    return {
                        "type": "negation",
                        "new_content": new_text,
                        "existing_fact": fact_text,
                        "description": "Negation contradiction detected",
                        "timestamp": time.time(),
                    }

            m_neg_fact = re.match(neg_pat, fact_lower)
            m_pos_new = re.match(pos_pat, new_lower)
            if m_neg_fact and m_pos_new:
                subj_new = m_pos_new.group(1).strip()
                subj_fact = m_neg_fact.group(1).strip()
                if _keyword_overlap(_tokenize(subj_new), _tokenize(subj_fact)) >= 0.5:
                    return {
                        "type": "negation",
                        "new_content": new_text,
                        "existing_fact": fact_text,
                        "description": "Negation contradiction detected",
                        "timestamp": time.time(),
                    }

        return None

    @staticmethod
    def _check_numeric(
        new_text: str,
        fact_text: str,
        new_tokens: List[str],
        fact_tokens: List[str],
    ) -> Optional[Dict[str, Any]]:
        new_nums = _extract_numbers(new_text)
        fact_nums = _extract_numbers(fact_text)
        if not new_nums or not fact_nums:
            return None

        # Filter out year-like numbers (4-digit starting with 1 or 2)
        year_re = re.compile(r"^[12]\d{3}$")
        new_nums = [n for n in new_nums if not year_re.match(n)]
        fact_nums = [n for n in fact_nums if not year_re.match(n)]
        if not new_nums or not fact_nums:
            return None

        # Require substantial keyword overlap (same subject)
        non_num_new = [t for t in new_tokens if not re.match(r"^\d+$", t)]
        non_num_fact = [t for t in fact_tokens if not re.match(r"^\d+$", t)]
        if _keyword_overlap(non_num_new, non_num_fact) < 0.4:
            return None

        for nn in new_nums:
            for fn in fact_nums:
                try:
                    if abs(float(nn) - float(fn)) > 1e-9:
                        return {
                            "type": "numeric",
                            "new_content": new_text,
                            "existing_fact": fact_text,
                            "description": f"Numeric contradiction: {nn} vs {fn}",
                            "timestamp": time.time(),
                        }
                except ValueError:
                    continue
        return None

    @staticmethod
    def _check_temporal(
        new_text: str,
        fact_text: str,
        new_tokens: List[str],
        fact_tokens: List[str],
    ) -> Optional[Dict[str, Any]]:
        year_pat = r"\b(1\d{3}|2\d{3})\b"
        new_years = re.findall(year_pat, new_text)
        fact_years = re.findall(year_pat, fact_text)
        if not new_years or not fact_years:
            return None

        _stopwords = {
            "a", "an", "the", "is", "are", "was", "were", "in", "on", "at",
            "to", "for", "of", "and", "or", "but", "it", "its", "has", "had",
            "be", "been", "being", "that", "this", "with", "from", "by",
        }
        non_year_new = [t for t in new_tokens
                        if not re.match(r"^(1\d{3}|2\d{3})$", t) and t not in _stopwords]
        non_year_fact = [t for t in fact_tokens
                         if not re.match(r"^(1\d{3}|2\d{3})$", t) and t not in _stopwords]
        if _keyword_overlap(non_year_new, non_year_fact) < 0.4:
            return None

        for ny in new_years:
            for fy in fact_years:
                if ny != fy:
                    return {
                        "type": "temporal",
                        "new_content": new_text,
                        "existing_fact": fact_text,
                        "description": f"Temporal contradiction: {ny} vs {fy}",
                        "timestamp": time.time(),
                    }
        return None

    @staticmethod
    def _check_antonyms(
        new_text: str,
        fact_text: str,
        new_tokens: List[str],
        fact_tokens: List[str],
    ) -> Optional[Dict[str, Any]]:
        # Require reasonable subject overlap
        if _keyword_overlap(new_tokens, fact_tokens) < 0.2:
            return None

        new_set = set(new_tokens)
        fact_set = set(fact_tokens)
        shared = new_set & fact_set

        for tok in new_set - shared:
            antonym = _ANTONYM_MAP.get(tok)
            if antonym and antonym in fact_set:
                return {
                    "type": "antonym",
                    "new_content": new_text,
                    "existing_fact": fact_text,
                    "description": f"Antonym contradiction: '{tok}' vs '{antonym}'",
                    "timestamp": time.time(),
                }
        return None
