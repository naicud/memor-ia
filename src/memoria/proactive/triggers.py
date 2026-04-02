"""Event-driven proactive trigger system."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from memoria.comms.bus import Event, MessageBus


# ---------------------------------------------------------------------------
# Trigger dataclass
# ---------------------------------------------------------------------------

@dataclass
class Trigger:
    """An event-driven trigger rule."""

    name: str
    event_type: str  # EventType value or custom string
    condition: Callable[[dict], bool]
    action: Callable[[dict], None]
    cooldown_s: float = 60.0
    enabled: bool = True


# ---------------------------------------------------------------------------
# TriggerSystem
# ---------------------------------------------------------------------------

class TriggerSystem:
    """Event-driven proactive trigger system.

    Registers triggers (condition + action pairs) that fire automatically
    when matching events appear on the MessageBus.
    """

    def __init__(self, bus: MessageBus | None = None) -> None:
        self._lock = threading.RLock()
        self._triggers: dict[str, Trigger] = {}
        self._last_fired: dict[str, float] = {}
        self._fire_counts: dict[str, int] = {}
        self._bus = bus
        self._unsub: Callable[[], None] | None = None

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, trigger: Trigger) -> None:
        """Register a new trigger."""
        with self._lock:
            self._triggers[trigger.name] = trigger
            self._fire_counts.setdefault(trigger.name, 0)

    def unregister(self, name: str) -> None:
        """Remove a trigger."""
        with self._lock:
            self._triggers.pop(name, None)
            self._last_fired.pop(name, None)
            self._fire_counts.pop(name, None)

    def enable(self, name: str) -> None:
        """Enable a trigger."""
        with self._lock:
            if name in self._triggers:
                self._triggers[name].enabled = True

    def disable(self, name: str) -> None:
        """Disable a trigger."""
        with self._lock:
            if name in self._triggers:
                self._triggers[name].enabled = False

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(self, event_type: str, event_data: dict) -> list[str]:
        """Evaluate all triggers for an event. Returns names of fired triggers."""
        with self._lock:
            now = time.time()
            fired: list[str] = []

            for name, trigger in self._triggers.items():
                if not trigger.enabled:
                    continue

                # Match event type
                etype = trigger.event_type
                if isinstance(etype, Enum):
                    etype = etype.value
                if etype != "*" and etype != event_type:
                    continue

                # Check cooldown
                last = self._last_fired.get(name, 0.0)
                if (now - last) < trigger.cooldown_s:
                    continue

                # Check condition
                try:
                    if not trigger.condition(event_data):
                        continue
                except Exception:
                    continue

                # Fire
                try:
                    trigger.action(event_data)
                except Exception:
                    pass

                self._last_fired[name] = now
                self._fire_counts[name] = self._fire_counts.get(name, 0) + 1
                fired.append(name)

            return fired

    # ------------------------------------------------------------------
    # MessageBus integration
    # ------------------------------------------------------------------

    def _on_event(self, event: Event) -> None:
        """Internal callback for MessageBus events."""
        etype = event.type.value if isinstance(event.type, Enum) else event.type
        self.evaluate(etype, event.data)

    def start(self) -> None:
        """Subscribe to MessageBus and auto-evaluate triggers."""
        if self._bus and not self._unsub:
            self._unsub = self._bus.subscribe("*", self._on_event)

    def stop(self) -> None:
        """Unsubscribe from MessageBus."""
        if self._unsub:
            self._unsub()
            self._unsub = None

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_active_triggers(self) -> list[Trigger]:
        """Get all enabled triggers."""
        with self._lock:
            return [t for t in self._triggers.values() if t.enabled]

    def get_fire_history(self) -> dict[str, int]:
        """Get count of times each trigger has fired."""
        with self._lock:
            return dict(self._fire_counts)

    # ------------------------------------------------------------------
    # Built-in trigger factories
    # ------------------------------------------------------------------

    @staticmethod
    def repetition_trigger(threshold: int = 5) -> Trigger:
        """Trigger when user repeats same query N times."""
        counts: dict[str, int] = {}

        def condition(data: dict) -> bool:
            query = data.get("query", "")
            if not query:
                return False
            key = query.strip().lower()
            counts[key] = counts.get(key, 0) + 1
            # Cap the counts dict to prevent unbounded growth
            if len(counts) > 10_000:
                min_key = min(counts, key=counts.get)  # type: ignore[arg-type]
                del counts[min_key]
            return counts.get(key, 0) >= threshold

        def action(data: dict) -> None:
            pass  # Override or attach custom logic

        return Trigger(
            name="builtin_repetition",
            event_type="memory.recalled",
            condition=condition,
            action=action,
            cooldown_s=300,
        )

    @staticmethod
    def idle_trigger(timeout_s: float = 300) -> Trigger:
        """Trigger when user is idle for N seconds."""
        state: dict[str, float] = {"last_activity": time.time()}

        def condition(data: dict) -> bool:
            now = time.time()
            elapsed = now - state["last_activity"]
            state["last_activity"] = now
            return elapsed >= timeout_s

        def action(data: dict) -> None:
            pass

        return Trigger(
            name="builtin_idle",
            event_type="*",
            condition=condition,
            action=action,
            cooldown_s=timeout_s,
        )

    @staticmethod
    def context_overflow_trigger(threshold: float = 0.8) -> Trigger:
        """Trigger when context window usage exceeds threshold."""

        def condition(data: dict) -> bool:
            usage = data.get("context_usage", 0.0)
            return usage >= threshold

        def action(data: dict) -> None:
            pass

        return Trigger(
            name="builtin_context_overflow",
            event_type="memory.updated",
            condition=condition,
            action=action,
            cooldown_s=120,
        )
