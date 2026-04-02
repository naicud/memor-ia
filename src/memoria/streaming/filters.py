"""Client-side event filters for streaming subscriptions.

Allows clients to subscribe to a subset of events based on event type,
user ID, namespace, or a custom predicate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class EventFilter:
    """Declarative filter for stream subscriptions.

    All criteria are AND-combined:
    - ``event_types``: allow only these event types (empty = all)
    - ``user_ids``: allow only events whose data contains one of these user IDs
    - ``namespaces``: allow only events whose data contains one of these namespaces
    - ``custom_predicate``: optional callable ``(event_data) -> bool``
    """

    event_types: tuple[str, ...] = ()
    user_ids: tuple[str, ...] = ()
    namespaces: tuple[str, ...] = ()
    custom_predicate: Optional[Callable[[dict[str, Any]], bool]] = None

    @classmethod
    def from_params(
        cls,
        event_types: list[str] | None = None,
        user_ids: list[str] | None = None,
        namespaces: list[str] | None = None,
    ) -> EventFilter:
        """Build a filter from query-parameter lists."""
        return cls(
            event_types=tuple(event_types or []),
            user_ids=tuple(user_ids or []),
            namespaces=tuple(namespaces or []),
        )

    def matches(self, event_type: str, event_data: dict[str, Any]) -> bool:
        """Return ``True`` if the event passes all filter criteria."""
        if self.event_types and event_type not in self.event_types:
            return False

        if self.user_ids:
            ev_user = event_data.get("user_id") or event_data.get("agent_id")
            if ev_user not in self.user_ids:
                return False

        if self.namespaces:
            ev_ns = event_data.get("namespace")
            if ev_ns not in self.namespaces:
                return False

        if self.custom_predicate is not None:
            try:
                if not self.custom_predicate(event_data):
                    return False
            except Exception:
                return False

        return True

    def __hash__(self) -> int:
        return hash((self.event_types, self.user_ids, self.namespaces))
