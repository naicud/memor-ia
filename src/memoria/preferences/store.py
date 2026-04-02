"""Persistent preference storage with confidence evolution."""
from __future__ import annotations

import threading
import time

from .types import (
    Preference,
    PreferenceCategory,
    PreferenceConflict,
    PreferenceEvidence,
    PreferenceQuery,
    PreferenceSource,
)

_MAX_CONFLICTS = 500
_MAX_EVIDENCE_PER_PREF = 100
_MAX_PREFS_PER_USER = 1000


class PreferenceStore:
    """Persistent preference storage with confidence evolution."""

    def __init__(
        self, confidence_growth: float = 0.1, confidence_decay: float = 0.05,
    ) -> None:
        self._preferences: dict[str, dict[str, Preference]] = {}
        self._growth = confidence_growth
        self._decay = confidence_decay
        self._lock = threading.RLock()
        self._conflicts: list[PreferenceConflict] = []

    def get(self, user_id: str, preference_id: str) -> Preference | None:
        """Get a specific preference."""
        with self._lock:
            user_prefs = self._preferences.get(user_id, {})
            return user_prefs.get(preference_id)

    def query(self, q: PreferenceQuery) -> list[Preference]:
        """Query preferences with filters."""
        with self._lock:
            user_prefs = self._preferences.get(q.user_id, {})
            results: list[Preference] = []
            for pref in user_prefs.values():
                if q.active_only and not pref.active:
                    continue
                if q.category is not None and pref.category != q.category:
                    continue
                if q.key and pref.key != q.key:
                    continue
                if q.context and q.context.lower() not in (pref.context or "").lower():
                    continue
                if pref.confidence < q.min_confidence:
                    continue
                results.append(pref)
            results.sort(key=lambda p: p.confidence, reverse=True)
            return results

    def upsert(self, pref: Preference) -> Preference:
        """Insert or update a preference. If exists, boost confidence."""
        with self._lock:
            if pref.user_id not in self._preferences:
                self._preferences[pref.user_id] = {}
            user_prefs = self._preferences[pref.user_id]

            existing = user_prefs.get(pref.preference_id)
            if existing is None:
                # Check for conflicts: same category+key but different ID/value
                for other in user_prefs.values():
                    if (
                        other.active
                        and other.category == pref.category
                        and other.key == pref.key
                        and other.value != pref.value
                    ):
                        conflict = PreferenceConflict(
                            preference_a=other,
                            preference_b=pref,
                        )
                        self._conflicts.append(conflict)
                        if len(self._conflicts) > _MAX_CONFLICTS:
                            self._conflicts = [c for c in self._conflicts if not c.resolution]
                            if len(self._conflicts) > _MAX_CONFLICTS:
                                self._conflicts = self._conflicts[-_MAX_CONFLICTS:]
                        pref.contradicted_by = other.preference_id
                        other.contradicted_by = pref.preference_id

                user_prefs[pref.preference_id] = pref
                return pref

            # Existing with same ID — boost confidence
            if existing.value == pref.value:
                existing.observation_count += 1
                existing.evidence.extend(pref.evidence)
                if len(existing.evidence) > _MAX_EVIDENCE_PER_PREF:
                    existing.evidence = existing.evidence[-_MAX_EVIDENCE_PER_PREF:]
                existing.updated_at = pref.updated_at or time.time()
                self._boost_confidence(existing)
                return existing

            # Same ID but different value — conflict
            conflict = PreferenceConflict(
                preference_a=existing,
                preference_b=pref,
            )
            self._conflicts.append(conflict)
            if len(self._conflicts) > _MAX_CONFLICTS:
                self._conflicts = [c for c in self._conflicts if not c.resolution]
                if len(self._conflicts) > _MAX_CONFLICTS:
                    self._conflicts = self._conflicts[-_MAX_CONFLICTS:]
            existing.contradicted_by = pref.preference_id
            pref.contradicted_by = existing.preference_id
            user_prefs[pref.preference_id] = pref
            # Cap preferences per user
            if len(user_prefs) > _MAX_PREFS_PER_USER:
                # Evict lowest-confidence inactive prefs first, then lowest-confidence active
                sorted_prefs = sorted(
                    user_prefs.items(),
                    key=lambda kv: (kv[1].active, kv[1].confidence),
                )
                for k, _ in sorted_prefs[: len(user_prefs) - _MAX_PREFS_PER_USER]:
                    del user_prefs[k]
            return pref

    def boost(self, user_id: str, preference_id: str, amount: float = 0.0) -> float:
        """Boost confidence of a preference. Returns new confidence."""
        with self._lock:
            pref = self.get(user_id, preference_id)
            if pref is None:
                return 0.0
            if amount > 0:
                pref.confidence = min(0.99, pref.confidence + amount)
            else:
                self._boost_confidence(pref)
            return pref.confidence

    def _boost_confidence(self, pref: Preference) -> None:
        """Apply growth formula to confidence."""
        pref.confidence = min(0.99, pref.confidence + self._growth * (1 - pref.confidence))

    def decay_all(self, user_id: str) -> int:
        """Decay confidence of all preferences for user. Returns count affected."""
        with self._lock:
            user_prefs = self._preferences.get(user_id, {})
            count = 0
            for pref in user_prefs.values():
                if not pref.active:
                    continue
                pref.confidence *= (1 - self._decay)
                count += 1
                if pref.confidence < 0.05:
                    pref.active = False
            return count

    def deactivate(self, user_id: str, preference_id: str) -> bool:
        """Deactivate a preference."""
        with self._lock:
            pref = self.get(user_id, preference_id)
            if pref is None:
                return False
            pref.active = False
            return True

    def teach(
        self, user_id: str, category: PreferenceCategory, key: str,
        value: str, context: str = "",
    ) -> Preference:
        """Explicitly teach a preference (high confidence)."""
        ts = time.time()
        pref_id = f"pref-{user_id}-{category.value}-{key}"
        pref = Preference(
            preference_id=pref_id,
            user_id=user_id,
            category=category,
            key=key,
            value=value,
            confidence=0.9,
            observation_count=1,
            evidence=[PreferenceEvidence(
                source=PreferenceSource.EXPLICIT,
                signal=f"taught: {key}={value}",
                timestamp=ts,
                context=context,
            )],
            created_at=ts,
            updated_at=ts,
            context=context,
        )
        return self.upsert(pref)

    def get_for_context(
        self, user_id: str, context: str, min_confidence: float = 0.3,
    ) -> list[Preference]:
        """Get preferences relevant to a context string."""
        if not context:
            return []
        with self._lock:
            user_prefs = self._preferences.get(user_id, {})
            results: list[Preference] = []
            ctx_lower = context.lower()
            for pref in user_prefs.values():
                if not pref.active or pref.confidence < min_confidence:
                    continue
                # Match by context field
                if pref.context and pref.context.lower() in ctx_lower:
                    results.append(pref)
                    continue
                # Match by key or value appearing in context
                if pref.key.lower() in ctx_lower or pref.value.lower() in ctx_lower:
                    results.append(pref)
                    continue
            results.sort(key=lambda p: p.confidence, reverse=True)
            return results

    def export(self, user_id: str) -> list[dict]:
        """Export all preferences for user as serializable dicts."""
        with self._lock:
            user_prefs = self._preferences.get(user_id, {})
            exported: list[dict] = []
            for pref in user_prefs.values():
                exported.append({
                    "preference_id": pref.preference_id,
                    "user_id": pref.user_id,
                    "category": pref.category.value,
                    "key": pref.key,
                    "value": pref.value,
                    "confidence": pref.confidence,
                    "observation_count": pref.observation_count,
                    "evidence": [
                        {
                            "source": e.source.value,
                            "signal": e.signal,
                            "timestamp": e.timestamp,
                            "context": e.context,
                        }
                        for e in pref.evidence
                    ],
                    "created_at": pref.created_at,
                    "updated_at": pref.updated_at,
                    "contradicted_by": pref.contradicted_by,
                    "active": pref.active,
                    "context": pref.context,
                })
            return exported

    def stats(self) -> dict:
        """Store statistics."""
        with self._lock:
            total = 0
            active = 0
            by_category: dict[str, int] = {}
            users = len(self._preferences)
            for user_prefs in self._preferences.values():
                for pref in user_prefs.values():
                    total += 1
                    if pref.active:
                        active += 1
                    cat = pref.category.value
                    by_category[cat] = by_category.get(cat, 0) + 1
            return {
                "total_preferences": total,
                "active_preferences": active,
                "users": users,
                "by_category": by_category,
                "conflicts": len(self._conflicts),
            }

    def get_conflicts(self) -> list[PreferenceConflict]:
        """Get all unresolved conflicts."""
        with self._lock:
            return [c for c in self._conflicts if not c.resolution]
