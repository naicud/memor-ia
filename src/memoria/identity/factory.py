"""Factory for creating subagent contexts with proper isolation.

Each factory function enforces specific isolation semantics that mirror the
TypeScript ``createSubagentContext`` / teammate / fork patterns.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .context import AgentContext
from .agent_id import AgentId, SessionId, TeammateIdentity, create_agent_id

# ---------------------------------------------------------------------------
# Override spec
# ---------------------------------------------------------------------------


@dataclass
class SubagentOverrides:
    """Override specific isolation defaults when spawning subagents."""

    agent_id: Optional[AgentId] = None
    share_app_state: bool = False
    share_abort_controller: bool = False
    permission_mode: Optional[str] = None
    can_use_tool: Optional[Callable[..., Any]] = None
    is_background: bool = True


# ---------------------------------------------------------------------------
# Subagent
# ---------------------------------------------------------------------------


def create_subagent_context(
    parent: AgentContext,
    label: str = "",
    overrides: Optional[SubagentOverrides] = None,
) -> AgentContext:
    """Create an isolated subagent context from *parent*.

    Isolation behaviour (matches TypeScript ``createSubagentContext``):
    - AbortController: New by default (parent abort ≠ child abort)
    - Permissions: Independent by default
    - Depth: ``parent.depth + 1``
    - Progress: Fresh (no inheritance)
    - Messages: Fresh queue
    """
    ovr = overrides or SubagentOverrides()

    agent_id = ovr.agent_id or create_agent_id(label)

    # Abort event: share parent's or create new
    if ovr.share_abort_controller:
        abort_event = parent.abort_event
    else:
        abort_event = threading.Event()

    return AgentContext(
        agent_id=agent_id,
        session_id=parent.session_id,
        parent_agent_id=parent.agent_id,
        abort_event=abort_event,
        is_background=ovr.is_background,
        depth=parent.depth + 1,
        permission_mode=ovr.permission_mode or parent.permission_mode,
        can_use_tool=ovr.can_use_tool,
        share_app_state=ovr.share_app_state,
        share_abort_controller=ovr.share_abort_controller,
    )


# ---------------------------------------------------------------------------
# Teammate
# ---------------------------------------------------------------------------


def create_teammate_context(
    parent: AgentContext,
    identity: TeammateIdentity,
    permission_mode: str = "default",
) -> AgentContext:
    """Create context for an in-process teammate.

    Teammates are special:
    - Independent abort controller (leader abort ≠ teammate abort)
    - Own permission mode (not inherited from parent)
    - Teammate identity set (affects tool access, UI display)
    """
    return AgentContext(
        agent_id=AgentId(identity.agent_id),
        session_id=parent.session_id,
        parent_agent_id=parent.agent_id,
        teammate_identity=identity,
        abort_event=threading.Event(),
        is_background=True,
        depth=parent.depth + 1,
        permission_mode=permission_mode,
        share_app_state=False,  # Teammates never share
    )


# ---------------------------------------------------------------------------
# Fork
# ---------------------------------------------------------------------------


def create_fork_context(
    parent: AgentContext,
    fork_label: str,
) -> AgentContext:
    """Create context for a forked subagent (cache-sharing).

    Forks share parent's context for cache-hit optimisation:
    - Independent abort
    - Fresh progress
    - Same depth (forks are lightweight)
    """
    return AgentContext(
        agent_id=create_agent_id(fork_label),
        session_id=parent.session_id,
        parent_agent_id=parent.agent_id,
        abort_event=threading.Event(),
        is_background=True,
        depth=parent.depth,  # Same depth (lightweight)
        permission_mode="bubble",  # Forks bubble permissions
    )
