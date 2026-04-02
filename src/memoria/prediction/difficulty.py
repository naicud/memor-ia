"""Task difficulty estimation based on user history."""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from .types import DifficultyEstimate, DifficultyLevel

_DIFFICULTY_ORDER = [
    DifficultyLevel.TRIVIAL,
    DifficultyLevel.EASY,
    DifficultyLevel.MODERATE,
    DifficultyLevel.HARD,
    DifficultyLevel.EXPERT,
]
_DIFFICULTY_INDEX = {d: i for i, d in enumerate(_DIFFICULTY_ORDER)}


class DifficultyEstimator:
    """Estimates the difficulty of a task *for the current user*.

    Maintains a history of completed tasks annotated with keywords, observed
    difficulty, duration, and whether the user struggled.  Uses keyword overlap
    to estimate new tasks.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._max_tasks: int = 500
        self._max_keywords: int = 500
        self._tasks: List[Dict[str, Any]] = []
        # keyword -> {total, struggled, durations, difficulties}
        self._keyword_stats: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_task(
        self,
        description: str,
        keywords: List[str],
        difficulty: DifficultyLevel,
        duration_minutes: float,
        struggled: bool = False,
    ) -> None:
        """Record a completed task."""
        duration_minutes = max(0.0, duration_minutes)
        with self._lock:
            self._tasks.append(
                {
                    "description": description,
                    "keywords": list(keywords),
                    "difficulty": difficulty,
                    "duration_minutes": duration_minutes,
                    "struggled": struggled,
                }
            )
            if len(self._tasks) > self._max_tasks:
                self._tasks = self._tasks[-self._max_tasks:]
            for kw in keywords:
                kw_lower = kw.lower()
                if kw_lower not in self._keyword_stats:
                    self._keyword_stats[kw_lower] = {
                        "total": 0,
                        "struggled": 0,
                        "durations": [],
                        "difficulties": [],
                    }
                st = self._keyword_stats[kw_lower]
                st["total"] += 1
                if struggled:
                    st["struggled"] += 1
                st["durations"].append(duration_minutes)
                st["difficulties"].append(difficulty)
                st["durations"] = st["durations"][-100:]
                st["difficulties"] = st["difficulties"][-100:]
            # Cap keyword stats to prevent unbounded growth
            if len(self._keyword_stats) > self._max_keywords:
                # Evict least-used keywords
                sorted_kws = sorted(
                    self._keyword_stats.items(),
                    key=lambda kv: kv[1]["total"],
                )
                for kw_key, _ in sorted_kws[: len(self._keyword_stats) - self._max_keywords]:
                    del self._keyword_stats[kw_key]

    # ------------------------------------------------------------------
    # Estimation
    # ------------------------------------------------------------------

    def estimate_difficulty(
        self, description: str, keywords: List[str]
    ) -> DifficultyEstimate:
        """Estimate how difficult *description* will be for the user."""
        with self._lock:
            matching_stats = self._matching_keyword_stats(keywords)

            if not matching_stats:
                return DifficultyEstimate(
                    task_description=description,
                    estimated_difficulty=DifficultyLevel.MODERATE,
                    user_competence=0.5,
                    struggle_probability=0.5,
                    reasoning="No historical data for these keywords",
                )

            # Aggregate across matching keywords
            total_tasks = sum(s["total"] for s in matching_stats.values())
            total_struggled = sum(s["struggled"] for s in matching_stats.values())
            all_durations: List[float] = []
            all_difficulties: List[DifficultyLevel] = []
            for s in matching_stats.values():
                all_durations.extend(s["durations"])
                all_difficulties.extend(s["difficulties"])

            struggle_prob = total_struggled / total_tasks if total_tasks else 0.5
            competence = self._compute_competence(matching_stats)
            avg_duration = sum(all_durations) / len(all_durations) if all_durations else 0.0
            difficulty = self._weighted_difficulty(all_difficulties)

            suggestions: List[str] = []
            if struggle_prob > 0.5:
                suggestions.append("Break the task into smaller steps")
                suggestions.append("Review similar past solutions first")
            if struggle_prob > 0.7:
                suggestions.append("Consider pairing with a more experienced collaborator")

            return DifficultyEstimate(
                task_description=description,
                estimated_difficulty=difficulty,
                user_competence=competence,
                struggle_probability=struggle_prob,
                estimated_time_minutes=avg_duration,
                reasoning=(
                    f"Based on {total_tasks} historical tasks matching keywords "
                    f"{list(matching_stats.keys())}; struggle rate "
                    f"{struggle_prob:.0%}, competence {competence:.2f}"
                ),
                suggestions=suggestions,
            )

    # ------------------------------------------------------------------
    # Competence
    # ------------------------------------------------------------------

    def get_user_competence(self, keywords: List[str]) -> float:
        """Return a 0.0–1.0 competence score for the given keywords."""
        with self._lock:
            matching = self._matching_keyword_stats(keywords)
            if not matching:
                return 0.5
            return self._compute_competence(matching)

    # ------------------------------------------------------------------
    # History & analysis
    # ------------------------------------------------------------------

    def get_task_history(
        self, keyword: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return past tasks, optionally filtered to those containing *keyword*."""
        with self._lock:
            if keyword is None:
                return [self._task_to_dict(t) for t in self._tasks]
            kw_lower = keyword.lower()
            return [
                self._task_to_dict(t)
                for t in self._tasks
                if kw_lower in [k.lower() for k in t["keywords"]]
            ]

    def get_strength_areas(self) -> List[str]:
        """Keywords where the user rarely struggles (competence ≥ 0.7)."""
        with self._lock:
            return [
                kw
                for kw, st in self._keyword_stats.items()
                if st["total"] >= 2 and self._kw_competence(st) >= 0.7
            ]

    def get_weakness_areas(self) -> List[str]:
        """Keywords where the user struggles frequently (competence < 0.4)."""
        with self._lock:
            return [
                kw
                for kw, st in self._keyword_stats.items()
                if st["total"] >= 2 and self._kw_competence(st) < 0.4
            ]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _matching_keyword_stats(
        self, keywords: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        return {
            kw.lower(): self._keyword_stats[kw.lower()]
            for kw in keywords
            if kw.lower() in self._keyword_stats
        }

    @staticmethod
    def _kw_competence(st: Dict[str, Any]) -> float:
        if st["total"] == 0:
            return 0.5
        succeeded = st["total"] - st["struggled"]
        return max(0.0, min(1.0, succeeded / st["total"]))

    def _compute_competence(
        self, stats: Dict[str, Dict[str, Any]]
    ) -> float:
        if not stats:
            return 0.5
        competences = [self._kw_competence(s) for s in stats.values()]
        return sum(competences) / len(competences)

    @staticmethod
    def _weighted_difficulty(
        difficulties: List[DifficultyLevel],
    ) -> DifficultyLevel:
        if not difficulties:
            return DifficultyLevel.MODERATE
        avg_idx = sum(_DIFFICULTY_INDEX[d] for d in difficulties) / len(difficulties)
        rounded = round(avg_idx)
        rounded = max(0, min(rounded, len(_DIFFICULTY_ORDER) - 1))
        return _DIFFICULTY_ORDER[rounded]

    @staticmethod
    def _task_to_dict(task: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "description": task["description"],
            "keywords": list(task["keywords"]),
            "difficulty": task["difficulty"].value,
            "duration_minutes": task["duration_minutes"],
            "struggled": task["struggled"],
        }
