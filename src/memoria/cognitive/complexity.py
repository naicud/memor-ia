"""Cognitive Load Management — complexity adaptation."""

from __future__ import annotations

import re
import threading
from typing import Any, Dict, List, Optional

from .types import (
    CognitiveSnapshot,
    ComplexityAssessment,
    ComplexityLevel,
    LoadLevel,
)

# Small built-in list of technical / specialised terms
_TECHNICAL_TERMS: frozenset = frozenset(
    [
        "algorithm", "api", "async", "authentication", "authorization",
        "binary", "buffer", "cache", "callback", "cipher",
        "compilation", "concurrency", "constructor", "coroutine", "cryptography",
        "daemon", "database", "deadlock", "debugging", "decryption",
        "dependency", "deployment", "deserialization", "distributed", "docker",
        "encryption", "endpoint", "exception", "framework", "function",
        "garbage", "git", "hash", "heap", "http",
        "idempotent", "index", "inheritance", "injection", "interface",
        "iterator", "json", "kernel", "kubernetes", "lambda",
        "latency", "linked", "logging", "malloc", "memory",
        "microservice", "middleware", "mutex", "namespace", "node",
        "object", "optimization", "orchestration", "overflow", "parallelism",
        "parser", "pipeline", "pointer", "polymorphism", "protocol",
        "proxy", "queue", "recursion", "refactoring", "regex",
        "replication", "runtime", "schema", "serialization", "server",
        "sharding", "singleton", "socket", "stack", "synchronization",
        "tcp", "template", "thread", "throughput", "token",
        "transaction", "tree", "tuple", "typescript", "udp",
        "variable", "vector", "virtualization", "webhook", "websocket",
    ]
)

_COMPLEXITY_ORDER: List[ComplexityLevel] = [
    ComplexityLevel.TRIVIAL,
    ComplexityLevel.SIMPLE,
    ComplexityLevel.MODERATE,
    ComplexityLevel.COMPLEX,
    ComplexityLevel.EXPERT,
]


class ComplexityAdapter:
    """Assesses and adapts content complexity based on user capacity."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._history: List[ComplexityAssessment] = []
        self._max_history = 1000

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assess_complexity(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ComplexityAssessment:
        """Assess content complexity using heuristics."""
        content = str(content)
        metadata = dict(metadata) if metadata else {}

        words = re.findall(r"[A-Za-z0-9_]+", content)
        word_count = len(words)

        # Length factor
        length_norm = min(1.0, word_count / 500.0)

        # Vocabulary richness
        unique_words = set(w.lower() for w in words)
        vocab_norm = (len(unique_words) / word_count) if word_count > 0 else 0.0

        # Technical terms
        lower_words = [w.lower() for w in words]
        tech_count = sum(1 for w in lower_words if w in _TECHNICAL_TERMS)
        tech_norm = min(1.0, tech_count / 10.0)

        # Nesting depth (parentheses, brackets, braces)
        nesting = content.count("(") + content.count("[") + content.count("{")
        nesting_norm = min(1.0, nesting / 20.0)

        score = (
            0.25 * length_norm
            + 0.25 * vocab_norm
            + 0.30 * tech_norm
            + 0.20 * nesting_norm
        )
        score = max(0.0, min(1.0, score))

        level = self._score_to_level(score)

        factors = {
            "length": round(length_norm, 4),
            "vocabulary": round(vocab_norm, 4),
            "technical": round(tech_norm, 4),
            "nesting": round(nesting_norm, 4),
        }

        assessment = ComplexityAssessment(
            level=level,
            score=round(score, 4),
            factors=factors,
        )

        with self._lock:
            self._history.append(assessment)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

        return assessment

    def adapt_to_user(
        self,
        assessment: ComplexityAssessment,
        user_load: CognitiveSnapshot,
    ) -> ComplexityAssessment:
        """Adapt complexity level based on current cognitive load."""
        idx = _COMPLEXITY_ORDER.index(assessment.level)

        if user_load.load_level in (LoadLevel.HIGH, LoadLevel.OVERLOADED):
            new_idx = max(0, idx - 1)
        elif user_load.load_level in (LoadLevel.MINIMAL, LoadLevel.LOW):
            new_idx = min(len(_COMPLEXITY_ORDER) - 1, idx + 1)
        else:
            new_idx = idx

        adapted_level = _COMPLEXITY_ORDER[new_idx]

        return ComplexityAssessment(
            level=assessment.level,
            score=assessment.score,
            factors=dict(assessment.factors),
            adapted_level=adapted_level,
            timestamp=assessment.timestamp,
        )

    def get_user_capacity(self, load: CognitiveSnapshot) -> float:
        """Estimate remaining cognitive capacity (0.0 = none, 1.0 = full)."""
        return max(0.0, min(1.0, 1.0 - load.load_score))

    def suggest_simplification(
        self,
        content: str,
        target_level: ComplexityLevel,
    ) -> Dict[str, Any]:
        """Suggest ways to simplify content to reach *target_level*."""
        current = self.assess_complexity(content)
        current_idx = _COMPLEXITY_ORDER.index(current.level)
        target_idx = _COMPLEXITY_ORDER.index(target_level)

        suggestions: List[str] = []
        if current_idx <= target_idx:
            return {
                "current_level": current.level.value,
                "target_level": target_level.value,
                "already_at_target": True,
                "suggestions": [],
                "score": current.score,
            }

        if current.factors.get("length", 0) > 0.5:
            suggestions.append("Shorten the content — remove redundant sections.")
        if current.factors.get("technical", 0) > 0.3:
            suggestions.append("Replace technical jargon with plain language.")
        if current.factors.get("nesting", 0) > 0.3:
            suggestions.append("Flatten nested structures — reduce indentation depth.")
        if current.factors.get("vocabulary", 0) > 0.7:
            suggestions.append("Simplify vocabulary — use more common words.")
        if not suggestions:
            suggestions.append("Break the content into smaller, focused sections.")

        return {
            "current_level": current.level.value,
            "target_level": target_level.value,
            "already_at_target": False,
            "suggestions": suggestions,
            "score": current.score,
        }

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "history": [a._to_dict() for a in self._history],
                "max_history": self._max_history,
            }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ComplexityAdapter:
        adapter = cls()
        adapter._max_history = data.get("max_history", 1000)
        for a in data.get("history", []):
            adapter._history.append(ComplexityAssessment._from_dict(a))
        if len(adapter._history) > adapter._max_history:
            adapter._history = adapter._history[-adapter._max_history:]
        return adapter

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _score_to_level(score: float) -> ComplexityLevel:
        if score < 0.2:
            return ComplexityLevel.TRIVIAL
        if score < 0.4:
            return ComplexityLevel.SIMPLE
        if score < 0.6:
            return ComplexityLevel.MODERATE
        if score < 0.8:
            return ComplexityLevel.COMPLEX
        return ComplexityLevel.EXPERT
