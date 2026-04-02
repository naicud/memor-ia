"""Event integration between task lifecycle and the MessageBus.

Maps task lifecycle events (created, running, completed, failed, killed)
to ``MessageBus`` events and vice-versa.  Provides a ``TaskEventBridge``
that can be started/stopped independently of the ``ProtocolBridge``.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

try:
    from src.task import TaskStatus, is_terminal_task_status
except ImportError:
    TaskStatus = None  # type: ignore[assignment,misc]
    is_terminal_task_status = None  # type: ignore[assignment]
from memoria.comms import (
    Event,
    EventType,
    get_message_bus,
    get_permission_bridge,
)

try:
    from src.utils.task_framework import TaskManager
except ImportError:
    TaskManager = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Status ↔ EventType mapping
# ---------------------------------------------------------------------------

_STATUS_TO_EVENT: dict[str, EventType] = {}
_EVENT_TO_STATUS: dict = {}

if TaskStatus is not None:
    _STATUS_TO_EVENT = {
        TaskStatus.COMPLETED.value: EventType.TASK_COMPLETED,
        TaskStatus.FAILED.value: EventType.AGENT_FAILED,
        TaskStatus.KILLED.value: EventType.AGENT_KILLED,
        TaskStatus.RUNNING.value: EventType.AGENT_ACTIVE,
        TaskStatus.PENDING.value: EventType.TASK_REGISTERED,
    }

    _EVENT_TO_STATUS = {
        EventType.TASK_COMPLETED: TaskStatus.COMPLETED,
        EventType.AGENT_FAILED: TaskStatus.FAILED,
        EventType.AGENT_KILLED: TaskStatus.KILLED,
        EventType.AGENT_ACTIVE: TaskStatus.RUNNING,
    }


# ---------------------------------------------------------------------------
# TaskEventBridge
# ---------------------------------------------------------------------------

class TaskEventBridge:
    """Bi-directional mapping between task lifecycle and MessageBus events.

    When started:
      1. Subscribes to ``TaskManager`` state changes and publishes
         corresponding events on the ``MessageBus``.
      2. Subscribes to bus events and applies status updates back to
         the ``TaskManager`` (guarded against echo loops).
      3. Routes permission requests from child tasks through the
         ``PermissionBridge``.

    Thread-safe.
    """

    def __init__(self, task_manager: TaskManager) -> None:
        self._tm = task_manager
        self._bus = get_message_bus()
        self._perm = get_permission_bridge()
        self._lock = threading.Lock()

        # Unsubscribe handles
        self._unsubs: list[Callable[[], None]] = []
        self._started = False

        # Guard: ignore bus→task updates that we ourselves published.
        self._publishing: set[str] = set()

        # Registered event listeners (external)
        self._listeners: dict[str, list[Callable[[Event], None]]] = {}

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        """Begin forwarding events.  Idempotent."""
        with self._lock:
            if self._started:
                return
            self._started = True

        # task manager → bus
        unsub_tm = self._tm.subscribe(self._on_task_state_change)
        self._unsubs.append(unsub_tm)

        # bus → task manager (listen to all events we care about)
        for event_type in _EVENT_TO_STATUS:
            unsub_bus = self._bus.subscribe(
                event_type.value,
                self._on_bus_event,
            )
            self._unsubs.append(unsub_bus)

        # permission events
        unsub_perm = self._bus.subscribe(
            EventType.PERMISSION_REQUEST.value,
            self._on_permission_request,
        )
        self._unsubs.append(unsub_perm)

        logger.debug("TaskEventBridge started")

    def stop(self) -> None:
        """Stop forwarding events and clean up subscriptions."""
        with self._lock:
            if not self._started:
                return
            self._started = False

        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

        with self._lock:
            self._listeners.clear()

        logger.debug("TaskEventBridge stopped")

    @property
    def is_started(self) -> bool:
        with self._lock:
            return self._started

    # -- public helpers -----------------------------------------------------

    def on_event(
        self, event_type: str, callback: Callable[[Event], None]
    ) -> Callable[[], None]:
        """Register an external listener for a specific event type.

        Returns an unregister callable.
        """
        with self._lock:
            self._listeners.setdefault(event_type, []).append(callback)

        def _unreg() -> None:
            with self._lock:
                lst = self._listeners.get(event_type, [])
                try:
                    lst.remove(callback)
                except ValueError:
                    pass

        return _unreg

    def emit_task_event(
        self,
        task_id: str,
        event_type: EventType,
        *,
        source: str = "bridge",
        data: dict | None = None,
    ) -> None:
        """Manually publish a task event on the bus."""
        payload = {"task_id": task_id}
        if data:
            payload.update(data)
        self._bus.publish(Event(
            type=event_type,
            source=source,
            data=payload,
        ))

    def get_status_for_event(self, event_type: EventType) -> TaskStatus | None:
        """Return the ``TaskStatus`` mapped to *event_type*, or ``None``."""
        return _EVENT_TO_STATUS.get(event_type)

    def get_event_for_status(self, status: TaskStatus) -> EventType | None:
        """Return the ``EventType`` mapped to *status*, or ``None``."""
        return _STATUS_TO_EVENT.get(status.value)

    # -- internal: task → bus -----------------------------------------------

    def _on_task_state_change(self, task_id: str, task_state: Any) -> None:
        """Forward task status changes to the MessageBus."""
        status = getattr(task_state, "status", None)
        if status is None:
            return

        status_str = status.value if hasattr(status, "value") else str(status)
        event_type = _STATUS_TO_EVENT.get(status_str)
        if event_type is None:
            return

        # Guard against echo loop
        guard_key = f"{task_id}:{status_str}"
        with self._lock:
            if guard_key in self._publishing:
                return
            self._publishing.add(guard_key)

        try:
            agent_id = getattr(task_state, "agent_id", task_id)
            self._bus.publish(Event(
                type=event_type,
                source=str(agent_id),
                data={
                    "task_id": task_id,
                    "status": status_str,
                    "description": getattr(task_state, "description", ""),
                },
            ))

            # Notify external listeners
            self._dispatch_to_listeners(event_type.value, Event(
                type=event_type,
                source=str(agent_id),
                data={"task_id": task_id, "status": status_str},
            ))
        finally:
            with self._lock:
                self._publishing.discard(guard_key)

    # -- internal: bus → task -----------------------------------------------

    def _on_bus_event(self, event: Event) -> None:
        """Apply bus events back to the task manager."""
        task_id = event.data.get("task_id")
        if not task_id:
            return

        target_status = _EVENT_TO_STATUS.get(event.type)
        if target_status is None:
            return

        # Guard against echo loop
        guard_key = f"{task_id}:{target_status.value}"
        with self._lock:
            if guard_key in self._publishing:
                return

        task = self._tm.get_task(task_id)
        if task is None:
            return

        current = getattr(task, "status", None)
        if current is not None:
            current_str = current.value if hasattr(current, "value") else str(current)
            if current_str == target_status.value:
                return
            # Don't transition from terminal states
            try:
                if is_terminal_task_status(current):
                    return
            except (TypeError, ValueError):
                if current_str in {"completed", "failed", "killed"}:
                    return

    # -- internal: permissions ----------------------------------------------

    def _on_permission_request(self, event: Event) -> None:
        """Route permission request events to the PermissionBridge."""
        agent_id = event.data.get("agent_id", "")
        tool_name = event.data.get("tool_name", "")
        if not agent_id or not tool_name:
            return

        # Check pre-authorization first
        decision = self._perm.check_pre_authorized(agent_id, tool_name)
        if decision is not None:
            self._bus.publish(Event(
                type=EventType.PERMISSION_RESPONSE,
                source="bridge",
                data={
                    "agent_id": agent_id,
                    "tool_name": tool_name,
                    "decision": decision.value,
                },
                target=agent_id,
            ))

    # -- internal: listener dispatch ----------------------------------------

    def _dispatch_to_listeners(self, event_type: str, event: Event) -> None:
        with self._lock:
            callbacks = list(self._listeners.get(event_type, []))
        for cb in callbacks:
            try:
                cb(event)
            except Exception:
                logger.exception("Listener raised for event %s", event_type)
