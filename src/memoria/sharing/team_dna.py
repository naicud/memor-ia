"""MEMORIA TeamDNASync — aggregate and synchronise DNA profiles across a team."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from memoria.sharing.types import TeamDNAProfile


class TeamDNASync:
    """Manages team-wide DNA aggregation, diversity analysis, and expertise gap detection."""

    _EXPERTISE_GAP_THRESHOLD = 0.3
    _EXPERTISE_STRENGTH_THRESHOLD = 0.7

    def __init__(self, team_id: str) -> None:
        self._team_id = team_id
        self._lock = threading.RLock()
        self._members: Dict[str, Dict[str, Any]] = {}
        self._cached_profile: Optional[TeamDNAProfile] = None

    @property
    def team_id(self) -> str:
        return self._team_id

    def register_member(
        self, agent_id: str, dna_snapshot: Optional[Dict[str, Any]] = None
    ) -> None:
        with self._lock:
            self._members[agent_id] = dict(dna_snapshot) if dna_snapshot else {}
            self._cached_profile = None

    def unregister_member(self, agent_id: str) -> None:
        with self._lock:
            self._members.pop(agent_id, None)
            self._cached_profile = None

    def update_member_dna(self, agent_id: str, dna_snapshot: Dict[str, Any]) -> None:
        with self._lock:
            if agent_id not in self._members:
                self._members[agent_id] = {}
            self._members[agent_id] = dict(dna_snapshot)
            self._cached_profile = None

    def aggregate_team_dna(self) -> TeamDNAProfile:
        with self._lock:
            snapshots = list(self._members.values())
            expertise = self._aggregate_expertise(snapshots)
            preferences = self._find_common_preferences(snapshots)
            diversity = self._compute_diversity(snapshots)

            profile = TeamDNAProfile(
                team_id=self._team_id,
                member_count=len(self._members),
                aggregated_expertise=expertise,
                common_preferences=preferences,
                diversity_score=diversity,
                last_updated=time.time(),
            )
            self._cached_profile = profile
            return profile

    def get_team_profile(self) -> Dict[str, Any]:
        with self._lock:
            if self._cached_profile is None:
                self.aggregate_team_dna()
            assert self._cached_profile is not None
            return self._cached_profile.to_dict()

    def compute_diversity_score(self) -> float:
        with self._lock:
            snapshots = list(self._members.values())
            return self._compute_diversity(snapshots)

    def find_expertise_gaps(self) -> List[str]:
        """Return topics where the team average expertise is below the gap threshold."""
        with self._lock:
            expertise = self._aggregate_expertise(list(self._members.values()))
            return [topic for topic, score in expertise.items() if score < self._EXPERTISE_GAP_THRESHOLD]

    def find_common_strengths(self) -> List[str]:
        """Return topics where the team average expertise meets the strength threshold."""
        with self._lock:
            expertise = self._aggregate_expertise(list(self._members.values()))
            return [topic for topic, score in expertise.items() if score >= self._EXPERTISE_STRENGTH_THRESHOLD]

    def get_member_dna(self, agent_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if agent_id not in self._members:
                return None
            return dict(self._members[agent_id])

    def get_member_ids(self) -> List[str]:
        with self._lock:
            return list(self._members.keys())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_expertise(
        dna_snapshots: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        if not dna_snapshots:
            return {}

        topic_scores: Dict[str, List[float]] = defaultdict(list)
        for snap in dna_snapshots:
            expertise = snap.get("expertise", {})
            for topic, score in expertise.items():
                if isinstance(score, (int, float)):
                    topic_scores[topic].append(float(score))

        return {
            topic: round(sum(scores) / len(scores), 4)
            for topic, scores in topic_scores.items()
            if scores
        }

    @staticmethod
    def _find_common_preferences(
        dna_snapshots: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not dna_snapshots:
            return {}

        # Collect all preference keys across members
        pref_values: Dict[str, List[Any]] = defaultdict(list)
        for snap in dna_snapshots:
            prefs = snap.get("preferences", {})
            for key, val in prefs.items():
                pref_values[key].append(val)

        # A preference is "common" if all members share the same value
        common: Dict[str, Any] = {}
        for key, vals in pref_values.items():
            if len(vals) == len(dna_snapshots) and len(set(str(v) for v in vals)) == 1:
                common[key] = vals[0]
        return common

    @staticmethod
    def _compute_diversity(dna_snapshots: List[Dict[str, Any]]) -> float:
        if len(dna_snapshots) <= 1:
            return 0.0

        all_topics: set[str] = set()
        per_member_topics: List[set[str]] = []
        for snap in dna_snapshots:
            topics = set(snap.get("expertise", {}).keys())
            all_topics |= topics
            per_member_topics.append(topics)

        if not all_topics:
            return 0.0

        # Diversity = 1 - (average Jaccard similarity between pairs)
        pair_count = 0
        total_jaccard = 0.0
        for i in range(len(per_member_topics)):
            for j in range(i + 1, len(per_member_topics)):
                a, b = per_member_topics[i], per_member_topics[j]
                union = a | b
                if union:
                    total_jaccard += len(a & b) / len(union)
                pair_count += 1

        if pair_count == 0:
            return 0.0
        avg_jaccard = total_jaccard / pair_count
        return round(1.0 - avg_jaccard, 4)
