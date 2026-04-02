"""Episodic memory data types — events, episodes, and enumerations."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class EventType(str, Enum):
    """Types of episodic events an agent can record."""

    INTERACTION = "interaction"
    DECISION = "decision"
    OBSERVATION = "observation"
    TOOL_USE = "tool_use"
    ERROR = "error"
    MILESTONE = "milestone"
    CONTEXT_SWITCH = "context_switch"
    INSIGHT = "insight"


@dataclass
class EpisodicEvent:
    """A single event in an episode."""

    event_id: str
    event_type: EventType
    content: str
    timestamp: float = field(default_factory=time.time)
    agent_id: str = ""
    user_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5
    embedding: Optional[list[float]] = None


@dataclass
class Episode:
    """A coherent sequence of events forming a narrative unit."""

    episode_id: str
    title: str = ""
    events: list[EpisodicEvent] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    agent_id: str = ""
    session_id: str = ""
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    outcome: str = ""

    @property
    def duration_s(self) -> float:
        """Elapsed seconds since episode started (or total if ended)."""
        end = self.ended_at or time.time()
        return end - self.started_at

    @property
    def event_count(self) -> int:
        return len(self.events)

    def is_active(self) -> bool:
        """True when the episode has not been closed."""
        return self.ended_at is None
