"""Contextual Intelligence Engine — proactive assistant."""

import threading
import time
import uuid
from typing import Any, Optional

from .types import AssistanceType, ProactiveAssistance


class ProactiveAssistant:
    """Generates proactive assistance suggestions based on cross-product context."""

    def __init__(
        self,
        max_suggestions: int = 200,
        cooldown_seconds: float = 300.0,
    ) -> None:
        self._lock = threading.RLock()
        self._suggestions: list[ProactiveAssistance] = []
        self._rules: list[dict[str, Any]] = []
        self._last_suggested: dict[str, float] = {}
        self._dismissed: set[str] = set()
        self._max_suggestions = max_suggestions
        self._cooldown = cooldown_seconds
        self._max_dismissed = max_suggestions * 2

    def add_rule(
        self,
        name: str,
        condition_keywords: list[str],
        assistance_type: AssistanceType,
        title: str,
        description: str,
        target_product: str = "",
    ) -> None:
        """Add an assistance rule."""
        with self._lock:
            self._rules.append({
                "name": name,
                "condition_keywords": [kw.lower() for kw in condition_keywords],
                "assistance_type": assistance_type,
                "title": title,
                "description": description,
                "target_product": target_product,
            })

    def evaluate(self, context: dict[str, Any]) -> list[ProactiveAssistance]:
        """Evaluate all rules against current context.

        Returns matching suggestions sorted by relevance_score (descending).
        Respects cooldown per assistance type.
        """
        now = time.time()
        context_text = " ".join(
            str(v).lower() for v in context.values() if v is not None
        )

        with self._lock:
            results: list[ProactiveAssistance] = []

            for rule in self._rules:
                atype: AssistanceType = rule["assistance_type"]
                type_key = atype.value

                # Cooldown check
                last = self._last_suggested.get(type_key, 0.0)
                if (now - last) < self._cooldown:
                    continue

                keywords: list[str] = rule["condition_keywords"]
                if not keywords:
                    continue

                matches = sum(1 for kw in keywords if kw in context_text)
                if matches == 0:
                    continue

                relevance = matches / len(keywords)
                aid = uuid.uuid4().hex

                suggestion = ProactiveAssistance(
                    assistance_id=aid,
                    assistance_type=atype,
                    title=rule["title"],
                    description=rule["description"],
                    relevance_score=relevance,
                    target_product=rule.get("target_product", ""),
                    action_url="",
                    expires_at=now + 3600,
                    metadata={"rule_name": rule["name"]},
                )

                results.append(suggestion)
                self._last_suggested[type_key] = now

            results.sort(key=lambda s: s.relevance_score, reverse=True)

            for s in results:
                self._suggestions.append(s)

            if len(self._suggestions) > self._max_suggestions:
                self._suggestions = self._suggestions[-self._max_suggestions:]

            return results

    def get_suggestions(
        self,
        limit: int = 10,
        assistance_type: Optional[AssistanceType] = None,
    ) -> list[ProactiveAssistance]:
        """Get recent suggestions, optionally filtered by type."""
        with self._lock:
            active = [
                s for s in self._suggestions if s.assistance_id not in self._dismissed
            ]
            if assistance_type is not None:
                active = [s for s in active if s.assistance_type == assistance_type]
            return active[-limit:]

    def dismiss_suggestion(self, assistance_id: str) -> bool:
        """Mark a suggestion as dismissed."""
        with self._lock:
            for s in self._suggestions:
                if s.assistance_id == assistance_id:
                    self._dismissed.add(assistance_id)
                    if len(self._dismissed) > self._max_dismissed:
                        active_ids = {s.assistance_id for s in self._suggestions}
                        self._dismissed = self._dismissed & active_ids
                    return True
            return False

    def get_suggestion_stats(self) -> dict[str, Any]:
        """Stats: total generated, by type, dismissal rate."""
        with self._lock:
            total = len(self._suggestions)
            dismissed = len(self._dismissed)
            by_type: dict[str, int] = {}
            for s in self._suggestions:
                key = s.assistance_type.value
                by_type[key] = by_type.get(key, 0) + 1

            return {
                "total": total,
                "dismissed": dismissed,
                "dismissal_rate": dismissed / total if total > 0 else 0.0,
                "by_type": by_type,
            }
