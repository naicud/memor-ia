"""Agent and session identity management.

Provides branded types (AgentId, SessionId) and utilities for creating,
parsing, and validating agent identifiers.  Mirrors the TypeScript codebase's
branded-type pattern translated to Python's ``NewType``.
"""

from __future__ import annotations

import re
import secrets
import time
from dataclasses import dataclass, field
from typing import NewType, Optional

# ---------------------------------------------------------------------------
# Branded types
# ---------------------------------------------------------------------------

AgentId = NewType("AgentId", str)
SessionId = NewType("SessionId", str)

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Agent ID pattern: a(?:.+-)?[0-9a-f]{16}
AGENT_ID_PATTERN = re.compile(r"^a(?:.+-)?[0-9a-f]{16}$")
# Teammate pattern: name@team
TEAMMATE_ID_PATTERN = re.compile(r"^(.+)@(.+)$")

# ---------------------------------------------------------------------------
# ID factories
# ---------------------------------------------------------------------------


def create_agent_id(label: str = "") -> AgentId:
    """Generate unique agent ID: ``a-{label}-{16 hex chars}``."""
    hex_suffix = secrets.token_hex(8)
    if label:
        safe_label = re.sub(r"[^a-zA-Z0-9_-]", "_", label)
        return AgentId(f"a-{safe_label}-{hex_suffix}")
    return AgentId(f"a{hex_suffix}")


def create_session_id() -> SessionId:
    """Generate unique session ID (32 hex chars)."""
    return SessionId(secrets.token_hex(16))


# ---------------------------------------------------------------------------
# Teammate helpers
# ---------------------------------------------------------------------------


def format_agent_id(agent_name: str, team_name: str) -> str:
    """Format deterministic teammate ID: ``name@team``."""
    return f"{agent_name}@{team_name}"


def parse_agent_id(agent_id: str) -> Optional[tuple[str, str]]:
    """Parse teammate ID.  Returns ``(agent_name, team_name)`` or ``None``."""
    match = TEAMMATE_ID_PATTERN.match(agent_id)
    if match:
        return (match.group(1), match.group(2))
    return None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def is_valid_agent_id(agent_id: str) -> bool:
    """Check if *agent_id* matches either the hex or teammate pattern."""
    return bool(AGENT_ID_PATTERN.match(agent_id)) or bool(
        TEAMMATE_ID_PATTERN.match(agent_id)
    )


# ---------------------------------------------------------------------------
# Request IDs
# ---------------------------------------------------------------------------


def format_request_id(request_type: str, agent_id: str) -> str:
    """Format request ID: ``{type}-{timestamp_ms}@{agentId}``."""
    return f"{request_type}-{int(time.time() * 1000)}@{agent_id}"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TeammateIdentity:
    """Persistent teammate identity stored in task state."""

    agent_id: str  # "researcher@my-team"
    agent_name: str  # "researcher"
    team_name: str  # "my-team"
    color: Optional[str] = None
    plan_mode_required: bool = False
    parent_session_id: str = ""


@dataclass
class AgentProgress:
    """Track agent execution progress with a sliding-window activity log."""

    tool_use_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    recent_activities: list[str] = field(default_factory=list)
    MAX_ACTIVITIES: int = 5

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_creation_tokens
        )

    def add_activity(self, activity: str) -> None:
        self.recent_activities.append(activity)
        if len(self.recent_activities) > self.MAX_ACTIVITIES:
            self.recent_activities = self.recent_activities[-self.MAX_ACTIVITIES :]
