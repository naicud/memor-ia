"""Pub/sub event system for agent coordination.

Central event bus that supports broadcast events, targeted events
(specific agent_id), wildcard subscriptions, and type-specific
subscriptions.  Thread-safe with bounded event history.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    """Agent coordination events."""

    AGENT_SPAWNED = "agent.spawned"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    AGENT_KILLED = "agent.killed"
    AGENT_IDLE = "agent.idle"
    AGENT_ACTIVE = "agent.active"

    TASK_REGISTERED = "task.registered"
    TASK_UPDATED = "task.updated"
    TASK_COMPLETED = "task.completed"

    MESSAGE_SENT = "message.sent"
    MESSAGE_RECEIVED = "message.received"

    PERMISSION_REQUEST = "permission.request"
    PERMISSION_RESPONSE = "permission.response"

    MEMORY_UPDATED = "memory.updated"
    MEMORY_RECALLED = "memory.recalled"

    SHUTDOWN_REQUESTED = "shutdown.requested"


# ---------------------------------------------------------------------------
# Event data
# ---------------------------------------------------------------------------

@dataclass
class Event:
    """An event on the message bus."""

    type: EventType
    source: str  # Agent ID of emitter
    data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    target: Optional[str] = None  # Specific recipient (None = broadcast)


# ---------------------------------------------------------------------------
# MessageBus
# ---------------------------------------------------------------------------

_MAX_LOG_SIZE = 1000


class MessageBus:
    """Central pub/sub event bus for agent coordination.

    Thread-safe.  Supports:
    - Broadcast events (all subscribers)
    - Targeted events (specific agent_id)
    - Wildcard subscriptions (``"*"`` for all events)
    - Type-specific subscriptions
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key: EventType.value or "*" for wildcard
        self._subscribers: dict[str, list[Callable[[Event], None]]] = {}
        self._event_log: list[Event] = []
        self._max_log_size = _MAX_LOG_SIZE

    # ------------------------------------------------------------------
    # Subscribe / unsubscribe
    # ------------------------------------------------------------------

    def subscribe(
        self,
        event_type: str,
        callback: Callable[[Event], None],
    ) -> Callable[[], None]:
        """Subscribe to events of *event_type*.  Use ``"*"`` for all events.

        Returns an unsubscribe function.
        """
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(callback)

        def unsubscribe() -> None:
            with self._lock:
                try:
                    self._subscribers[event_type].remove(callback)
                except (KeyError, ValueError):
                    pass

        return unsubscribe

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    def publish(self, event: Event) -> None:
        """Publish event to all matching subscribers."""
        with self._lock:
            # Record in bounded history
            self._event_log.append(event)
            if len(self._event_log) > self._max_log_size:
                self._event_log[:] = self._event_log[-self._max_log_size:]

            # Collect matching callbacks
            callbacks: list[Callable[[Event], None]] = []
            # Type-specific subscribers
            type_key = event.type.value if isinstance(event.type, Enum) else event.type
            callbacks.extend(self._subscribers.get(type_key, []))
            # Wildcard subscribers
            callbacks.extend(self._subscribers.get("*", []))

        # Invoke outside lock
        for cb in callbacks:
            try:
                cb(event)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Event history queries
    # ------------------------------------------------------------------

    def get_events(
        self,
        event_type: Optional[str] = None,
        source: Optional[str] = None,
        since: Optional[float] = None,
    ) -> list[Event]:
        """Query event history with optional filters."""
        with self._lock:
            results = list(self._event_log)

        if event_type is not None:
            results = [
                e for e in results
                if (e.type.value if isinstance(e.type, Enum) else e.type) == event_type
            ]
        if source is not None:
            results = [e for e in results if e.source == source]
        if since is not None:
            results = [e for e in results if e.timestamp >= since]
        return results

    def clear_history(self) -> None:
        """Clear event log."""
        with self._lock:
            self._event_log.clear()


# ---------------------------------------------------------------------------
# Module-level singleton + convenience functions
# ---------------------------------------------------------------------------

_bus = MessageBus()


def get_message_bus() -> MessageBus:
    """Return the module-level singleton ``MessageBus``."""
    return _bus


def publish(event: Event) -> None:
    """Publish an event on the default bus."""
    _bus.publish(event)


def subscribe(
    event_type: str,
    callback: Callable[[Event], None],
) -> Callable[[], None]:
    """Subscribe on the default bus."""
    return _bus.subscribe(event_type, callback)


__all__ = [
    "Event",
    "EventType",
    "MessageBus",
    "get_message_bus",
    "publish",
    "subscribe",
]
