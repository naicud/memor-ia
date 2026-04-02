"""Proactive suggestion generation based on profile, patterns, and memory."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memoria.proactive.analyzer import PatternAnalyzer
    from memoria.proactive.profiler import Profiler
    from memoria.recall.pipeline import RecallPipeline


# ---------------------------------------------------------------------------
# Suggestion dataclass
# ---------------------------------------------------------------------------

@dataclass
class Suggestion:
    """A proactive suggestion for the user."""

    id: str
    title: str
    description: str
    suggestion_type: str  # "optimization", "reminder", "learning", "automation", "insight"
    priority: float  # 0.0 to 1.0
    source: str  # What triggered this suggestion
    action: str | None = None
    cooldown_s: float = 3600


# ---------------------------------------------------------------------------
# SuggestionEngine
# ---------------------------------------------------------------------------

_DISMISSED = float("inf")
_MAX_EMITTED_PER_USER = 500
_MAX_USERS_EMITTED = 10_000


class SuggestionEngine:
    """Generates proactive suggestions based on profile, patterns, and memory."""

    def __init__(
        self,
        profiler: Profiler | None = None,
        analyzer: PatternAnalyzer | None = None,
        pipeline: RecallPipeline | None = None,
    ) -> None:
        self._profiler = profiler
        self._analyzer = analyzer
        self._pipeline = pipeline
        self._emitted: dict[str, dict[str, float]] = {}  # user_id → {suggestion_id → timestamp}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        user_id: str,
        current_context: str = "",
        limit: int = 3,
    ) -> list[Suggestion]:
        """Generate suggestions from all available signals."""
        candidates: list[Suggestion] = []

        candidates.extend(self._generate_pattern_suggestions(user_id))
        candidates.extend(self._generate_profile_suggestions(user_id))
        candidates.extend(self._generate_memory_suggestions(user_id, current_context))

        # Filter out cooled-down suggestions (per-user, per-suggestion cooldown)
        now = time.time()
        active = [s for s in candidates if self._check_cooldown(user_id, s)]

        # Minimum priority threshold
        active = [s for s in active if s.priority >= 0.2]

        # Deduplicate by suggestion type + source
        active = self._deduplicate(active)

        # Sort by priority descending
        active.sort(key=lambda s: s.priority, reverse=True)

        # Mark as emitted (per-user)
        result = active[:limit]
        user_emitted = self._emitted.setdefault(user_id, {})
        for s in result:
            user_emitted[s.id] = now
        # Cap emitted entries per user
        if len(user_emitted) > _MAX_EMITTED_PER_USER:
            sorted_items = sorted(user_emitted.items(), key=lambda kv: kv[1])
            to_remove = sorted_items[: len(user_emitted) - _MAX_EMITTED_PER_USER]
            for k, _ in to_remove:
                del user_emitted[k]
        # Cap total user count
        if len(self._emitted) > _MAX_USERS_EMITTED:
            oldest_user = min(
                self._emitted,
                key=lambda u: max(self._emitted[u].values()) if self._emitted[u] else 0.0,
            )
            del self._emitted[oldest_user]

        return result

    # ------------------------------------------------------------------
    # Pattern-based suggestions
    # ------------------------------------------------------------------

    def _generate_pattern_suggestions(self, user_id: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        if not self._analyzer:
            return suggestions

        patterns = self._analyzer.get_patterns(min_confidence=0.4)

        for pat in patterns:
            if pat.pattern_type == "repetition":
                sid = _make_id("pattern", pat.name)
                suggestions.append(Suggestion(
                    id=sid,
                    title=f"Frequent action: {pat.examples[0][:40] if pat.examples else pat.name}",
                    description=pat.description,
                    suggestion_type="automation",
                    priority=min(1.0, pat.confidence * 0.8),
                    source=f"pattern:{pat.name}",
                    action=f"Consider automating this repeated action ({pat.frequency}x)",
                ))
            elif pat.pattern_type == "sequence":
                sid = _make_id("sequence", pat.name)
                suggestions.append(Suggestion(
                    id=sid,
                    title=f"Workflow pattern: {pat.examples[0][:40] if pat.examples else pat.name}",
                    description=pat.description,
                    suggestion_type="optimization",
                    priority=min(1.0, pat.confidence * 0.7),
                    source=f"pattern:{pat.name}",
                    action="You could chain these steps into a single command or script",
                ))
            elif pat.pattern_type == "temporal":
                sid = _make_id("temporal", pat.name)
                suggestions.append(Suggestion(
                    id=sid,
                    title=f"Routine: {pat.description[:50]}",
                    description=pat.description,
                    suggestion_type="reminder",
                    priority=0.4,
                    source=f"pattern:{pat.name}",
                ))

        return suggestions

    # ------------------------------------------------------------------
    # Profile-based suggestions
    # ------------------------------------------------------------------

    def _generate_profile_suggestions(self, user_id: str) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        if not self._profiler:
            return suggestions

        profile = self._profiler.get_profile(user_id)

        # Suggest learning based on expertise gaps
        if profile.areas_for_growth:
            for area in profile.areas_for_growth[:2]:
                sid = _make_id("growth", area)
                suggestions.append(Suggestion(
                    id=sid,
                    title=f"Learn more about {area}",
                    description=f"Based on your profile, deepening knowledge of '{area}' "
                                "could strengthen your workflow.",
                    suggestion_type="learning",
                    priority=0.5,
                    source="profile:areas_for_growth",
                ))

        # Expertise-level suggestions
        if profile.expertise_level == "beginner" and profile.interaction_count > 5:
            sid = _make_id("expertise", "beginner_tips")
            suggestions.append(Suggestion(
                id=sid,
                title="Explore guided tutorials",
                description="You're building foundational skills — interactive tutorials "
                            "can accelerate your learning.",
                suggestion_type="learning",
                priority=0.6,
                source="profile:expertise_level",
            ))

        # Preferences reminder
        if profile.preferences and profile.interaction_count > 10:
            top_pref = next(iter(profile.preferences))
            sid = _make_id("pref", top_pref)
            suggestions.append(Suggestion(
                id=sid,
                title=f"Preference noted: {top_pref}",
                description=f"You prefer '{top_pref}'. I'll prioritise this in recommendations.",
                suggestion_type="insight",
                priority=0.3,
                source="profile:preferences",
            ))

        return suggestions

    # ------------------------------------------------------------------
    # Memory-based suggestions
    # ------------------------------------------------------------------

    def _generate_memory_suggestions(
        self, user_id: str, context: str
    ) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        if not self._pipeline or not context:
            return suggestions

        try:
            from memoria.recall.context_filter import RecallContext
            ctx = RecallContext(user_id=user_id) if user_id else None
            results = self._pipeline.recall(context, limit=3, context=ctx)
        except Exception:
            return suggestions

        for r in results:
            if r.final_score >= 0.5:
                sid = _make_id("memory", r.id)
                suggestions.append(Suggestion(
                    id=sid,
                    title=f"Related memory: {r.content[:50]}",
                    description=f"Found relevant info from a previous session "
                                f"(score {r.final_score:.2f}): {r.content[:100]}",
                    suggestion_type="reminder",
                    priority=r.final_score * 0.8,
                    source=f"memory:{r.id}",
                ))

        return suggestions

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def _deduplicate(self, suggestions: list[Suggestion]) -> list[Suggestion]:
        """Remove duplicate suggestions by type+source, keeping highest priority."""
        seen: dict[tuple[str, str], Suggestion] = {}
        for s in suggestions:
            key = (s.suggestion_type, s.source)
            if key not in seen or s.priority > seen[key].priority:
                seen[key] = s
        return list(seen.values())

    # ------------------------------------------------------------------
    # Cooldown management
    # ------------------------------------------------------------------

    def _check_cooldown(self, user_id: str, suggestion: Suggestion) -> bool:
        """Return True if the suggestion is NOT in cooldown for this user."""
        user_emitted = self._emitted.get(user_id)
        if user_emitted is None:
            return True
        last = user_emitted.get(suggestion.id)
        if last is None:
            return True
        if last == _DISMISSED:
            return False
        return (time.time() - last) > suggestion.cooldown_s

    def acknowledge(self, suggestion_id: str, user_id: str = "") -> None:
        """Mark suggestion as acknowledged (resets cooldown timer)."""
        user_emitted = self._emitted.setdefault(user_id, {})
        user_emitted[suggestion_id] = time.time()

    def dismiss(self, suggestion_id: str, user_id: str = "") -> None:
        """Mark suggestion as permanently dismissed."""
        user_emitted = self._emitted.setdefault(user_id, {})
        user_emitted[suggestion_id] = _DISMISSED

    def reset_dismissals(self, user_id: str, suggestion_id: str | None = None) -> None:
        """Re-enable dismissed suggestions for a user."""
        user_emitted = self._emitted.get(user_id)
        if user_emitted is None:
            return
        if suggestion_id:
            user_emitted.pop(suggestion_id, None)
        else:
            # Reset all dismissals, keep active cooldowns
            to_remove = [k for k, v in user_emitted.items() if v == _DISMISSED]
            for k in to_remove:
                del user_emitted[k]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_id(prefix: str, key: str) -> str:
    h = hashlib.md5(key.encode()).hexdigest()[:8]
    return f"sug_{prefix}_{h}"
