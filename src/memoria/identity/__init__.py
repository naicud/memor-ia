"""MEMORIA identity — agent IDs, context isolation, and context factories."""

from .agent_id import (
    AgentId,
    AgentProgress,
    SessionId,
    TeammateIdentity,
    create_agent_id,
    create_session_id,
    format_agent_id,
    format_request_id,
    is_valid_agent_id,
    parse_agent_id,
)
from .context import (
    AgentContext,
    get_current_agent,
    get_current_session,
    is_subagent,
    is_teammate,
    run_in_agent_context,
    run_in_agent_context_async,
    set_current_agent,
    set_current_session,
)
from .factory import (
    SubagentOverrides,
    create_fork_context,
    create_subagent_context,
    create_teammate_context,
)

__all__ = [
    # agent_id
    "AgentId",
    "AgentProgress",
    "SessionId",
    "TeammateIdentity",
    "create_agent_id",
    "create_session_id",
    "format_agent_id",
    "format_request_id",
    "is_valid_agent_id",
    "parse_agent_id",
    # context
    "AgentContext",
    "get_current_agent",
    "get_current_session",
    "is_subagent",
    "is_teammate",
    "run_in_agent_context",
    "run_in_agent_context_async",
    "set_current_agent",
    "set_current_session",
    # factory
    "SubagentOverrides",
    "create_fork_context",
    "create_subagent_context",
    "create_teammate_context",
]
