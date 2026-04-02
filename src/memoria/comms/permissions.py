"""Permission delegation between parent and child agents.

Manages the handshake for tool-use permissions:
1. **Direct (in-process):** Child queues request → parent callback resolves.
2. **Pre-authorization:** Parent pre-authorises a set of tools for a child.
3. **Timeout:** Child blocks up to a configurable deadline; returns ``DENY``
   on timeout so the agent never hangs indefinitely.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Enums & data
# ---------------------------------------------------------------------------

class PermissionDecision(str, Enum):
    """Possible outcomes of a permission request."""

    ALLOW = "allow"
    DENY = "deny"
    ALLOW_ALWAYS = "allow_always"  # Remember for the rest of the session


@dataclass
class PermissionRequest:
    """A tool-use permission request from child to parent."""

    request_id: str
    agent_id: str  # Requesting agent
    tool_name: str
    tool_input: dict = field(default_factory=dict)
    description: str = ""
    timestamp: float = field(default_factory=time.time)

    # Response tracking (internal)
    _response: Optional[PermissionDecision] = field(default=None, repr=False)
    _response_event: threading.Event = field(
        default_factory=threading.Event, repr=False,
    )

    def respond(self, decision: PermissionDecision) -> None:
        """Respond to this permission request."""
        self._response = decision
        self._response_event.set()

    def wait_for_response(
        self,
        timeout: Optional[float] = None,
    ) -> Optional[PermissionDecision]:
        """Block until response arrives or *timeout* expires."""
        self._response_event.wait(timeout=timeout)
        return self._response


# ---------------------------------------------------------------------------
# PermissionBridge
# ---------------------------------------------------------------------------

class PermissionBridge:
    """Manages permission delegation between parent and child agents.

    Patterns:
    1. Direct (in-process): Child queues request → parent callback resolves.
    2. Pre-authorization: Parent pre-authorises a set of tools for a child.
    3. Bubble mode: Child inherits parent's permission context.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, PermissionRequest] = {}
        self._allowed_tools: dict[str, set[str]] = {}  # agent_id → allowed tools
        self._denied_tools: dict[str, set[str]] = {}   # agent_id → denied tools
        self._handlers: list[Callable[[PermissionRequest], None]] = []

    # ------------------------------------------------------------------
    # Request flow
    # ------------------------------------------------------------------

    def request_permission(
        self,
        agent_id: str,
        tool_name: str,
        tool_input: Optional[dict] = None,
        description: str = "",
        timeout: float = 30.0,
    ) -> PermissionDecision:
        """Request tool-use permission.  Blocks until response or *timeout*.

        If the tool is pre-authorised the call returns immediately without
        invoking any handler.  On timeout the request is removed from the
        pending set and ``DENY`` is returned.
        """
        # Fast path: check pre-authorization
        pre = self.check_pre_authorized(agent_id, tool_name)
        if pre is not None:
            return pre

        request_id = uuid.uuid4().hex[:12]
        req = PermissionRequest(
            request_id=request_id,
            agent_id=agent_id,
            tool_name=tool_name,
            tool_input=tool_input or {},
            description=description,
        )

        with self._lock:
            self._pending[request_id] = req
            handlers = list(self._handlers)

        # Notify handlers (parent side)
        for handler in handlers:
            try:
                handler(req)
            except Exception:
                pass

        # Wait for response
        decision = req.wait_for_response(timeout=timeout)

        # Cleanup
        with self._lock:
            self._pending.pop(request_id, None)

        if decision is None:
            return PermissionDecision.DENY  # Timeout → deny

        # Remember ALLOW_ALWAYS decisions
        if decision == PermissionDecision.ALLOW_ALWAYS:
            self.set_allowed_tools(
                agent_id,
                self._allowed_tools.get(agent_id, set()) | {tool_name},
            )

        return decision

    # ------------------------------------------------------------------
    # Handler registration (parent side)
    # ------------------------------------------------------------------

    def register_handler(
        self,
        handler: Callable[[PermissionRequest], None],
    ) -> Callable[[], None]:
        """Register a permission request handler.  Returns unregister fn."""
        with self._lock:
            self._handlers.append(handler)

        def unregister() -> None:
            with self._lock:
                try:
                    self._handlers.remove(handler)
                except ValueError:
                    pass

        return unregister

    # ------------------------------------------------------------------
    # Pre-authorization
    # ------------------------------------------------------------------

    def set_allowed_tools(self, agent_id: str, tools: set[str]) -> None:
        """Pre-authorise *tools* for *agent_id* (no prompt needed)."""
        with self._lock:
            self._allowed_tools[agent_id] = set(tools)

    def set_denied_tools(self, agent_id: str, tools: set[str]) -> None:
        """Explicitly deny *tools* for *agent_id*."""
        with self._lock:
            self._denied_tools[agent_id] = set(tools)

    def check_pre_authorized(
        self,
        agent_id: str,
        tool_name: str,
    ) -> Optional[PermissionDecision]:
        """Check if *tool_name* is pre-authorised for *agent_id*.

        Returns ``ALLOW`` / ``DENY`` if a pre-authorization exists, or
        ``None`` if the tool must be evaluated at runtime.
        """
        with self._lock:
            denied = self._denied_tools.get(agent_id, set())
            if tool_name in denied:
                return PermissionDecision.DENY
            allowed = self._allowed_tools.get(agent_id, set())
            if tool_name in allowed:
                return PermissionDecision.ALLOW
        return None

    # ------------------------------------------------------------------
    # Pending request management
    # ------------------------------------------------------------------

    def get_pending_requests(
        self,
        agent_id: Optional[str] = None,
    ) -> list[PermissionRequest]:
        """Get pending permission requests, optionally filtered by agent."""
        with self._lock:
            pending = list(self._pending.values())
        if agent_id is not None:
            pending = [r for r in pending if r.agent_id == agent_id]
        return pending

    def respond_to_request(
        self,
        request_id: str,
        decision: PermissionDecision,
    ) -> bool:
        """Respond to a pending request by *request_id*.

        Returns ``True`` if the request was found and responded to.
        """
        with self._lock:
            req = self._pending.get(request_id)
        if req is None:
            return False
        req.respond(decision)
        return True


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_bridge = PermissionBridge()


def get_permission_bridge() -> PermissionBridge:
    """Return the module-level singleton ``PermissionBridge``."""
    return _bridge


__all__ = [
    "PermissionBridge",
    "PermissionDecision",
    "PermissionRequest",
    "get_permission_bridge",
]
