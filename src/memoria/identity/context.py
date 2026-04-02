"""Isolated per-agent context using ``contextvars``.

Python's :mod:`contextvars` serves the same role as Node's
``AsyncLocalStorage``: each agent (or subagent) gets its own copy of
the context variables, ensuring true isolation even under concurrency.
"""

from __future__ import annotations

import contextvars
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, TypeVar

from .agent_id import AgentId, AgentProgress, SessionId, TeammateIdentity

T = TypeVar("T")

# ---------------------------------------------------------------------------
# AgentContext
# ---------------------------------------------------------------------------


@dataclass
class AgentContext:
    """Runtime context for an agent — isolated via contextvars."""

    agent_id: AgentId
    session_id: SessionId
    parent_agent_id: Optional[AgentId] = None
    teammate_identity: Optional[TeammateIdentity] = None

    # Lifecycle
    abort_event: threading.Event = field(default_factory=threading.Event)
    is_background: bool = False
    depth: int = 0  # Nesting depth (0=root, 1=subagent, …)

    # Progress
    progress: AgentProgress = field(default_factory=AgentProgress)

    # Messages
    pending_messages: list[str] = field(default_factory=list)

    # Permissions
    permission_mode: str = "default"  # "default" | "plan" | "bubble"
    can_use_tool: Optional[Callable[..., Any]] = None

    # Isolation flags
    share_app_state: bool = False
    share_abort_controller: bool = False


# ---------------------------------------------------------------------------
# contextvars for agent isolation
# ---------------------------------------------------------------------------

_current_agent: contextvars.ContextVar[Optional[AgentContext]] = contextvars.ContextVar(
    "current_agent", default=None
)

_current_session: contextvars.ContextVar[Optional[SessionId]] = contextvars.ContextVar(
    "current_session", default=None
)

# ---------------------------------------------------------------------------
# Accessors
# ---------------------------------------------------------------------------


def get_current_agent() -> Optional[AgentContext]:
    """Get the current agent context (``None`` if root)."""
    return _current_agent.get()


def set_current_agent(ctx: Optional[AgentContext]) -> contextvars.Token:
    """Set the current agent context.  Returns token for reset."""
    return _current_agent.set(ctx)


def get_current_session() -> Optional[SessionId]:
    """Get the current session ID."""
    return _current_session.get()


def set_current_session(session_id: SessionId) -> contextvars.Token:
    """Set the current session ID."""
    return _current_session.set(session_id)


# ---------------------------------------------------------------------------
# Context runners
# ---------------------------------------------------------------------------


def run_in_agent_context(ctx: AgentContext, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Execute *fn* with *ctx* set in contextvars."""
    token = set_current_agent(ctx)
    try:
        return fn(*args, **kwargs)
    finally:
        _current_agent.reset(token)


async def run_in_agent_context_async(
    ctx: AgentContext, fn: Callable[..., T], *args: Any, **kwargs: Any
) -> T:
    """Async version of :func:`run_in_agent_context`."""
    token = set_current_agent(ctx)
    try:
        return await fn(*args, **kwargs)  # type: ignore[misc]
    finally:
        _current_agent.reset(token)


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def is_subagent() -> bool:
    """``True`` if currently executing in a subagent context."""
    ctx = get_current_agent()
    return ctx is not None and ctx.depth > 0


def is_teammate() -> bool:
    """``True`` if currently executing as an in-process teammate."""
    ctx = get_current_agent()
    return ctx is not None and ctx.teammate_identity is not None
