from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SessionOutcome(Enum):
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    PAUSED = "paused"
    ABANDONED = "abandoned"
    UNKNOWN = "unknown"


class ThreadStatus(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    STALE = "stale"


@dataclass
class WorkItem:
    """A specific task or goal being worked on."""

    item_id: str
    description: str
    status: str = "in_progress"
    context: str = ""
    files_involved: list[str] = field(default_factory=list)
    started_at: float = 0.0
    priority: float = 0.5


@dataclass
class CognitiveState:
    """The cognitive state of the user at a point in time."""

    active_goals: list[WorkItem] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    recent_topics: list[str] = field(default_factory=list)
    emotional_state: str = "neutral"
    focus_level: float = 0.7
    context_summary: str = ""
    working_files: list[str] = field(default_factory=list)
    branch: str = ""
    project: str = ""
    last_error: str = ""
    momentum: float = 0.5


@dataclass
class SessionSnapshot:
    """Complete snapshot of a session at its end."""

    snapshot_id: str
    user_id: str
    session_id: str
    created_at: float = 0.0
    outcome: SessionOutcome = SessionOutcome.UNKNOWN
    cognitive_state: CognitiveState = field(default_factory=CognitiveState)
    message_count: int = 0
    duration_minutes: float = 0.0
    key_decisions: list[str] = field(default_factory=list)
    last_messages_summary: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class WorkThread:
    """A conversation thread that spans multiple sessions."""

    thread_id: str
    user_id: str
    title: str
    description: str = ""
    status: ThreadStatus = ThreadStatus.ACTIVE
    created_at: float = 0.0
    updated_at: float = 0.0
    session_ids: list[str] = field(default_factory=list)
    related_files: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    progress: float = 0.0
    last_context: str = ""


@dataclass
class ResumptionHint:
    """A hint for resuming a previous session or thread."""

    hint_type: str
    title: str
    description: str
    priority: float = 0.5
    source_snapshot_id: str = ""
    source_thread_id: str = ""
    suggested_action: str = ""
    context: str = ""


@dataclass
class ResumeContext:
    """Complete resumption context for a user."""

    user_id: str
    last_session_outcome: SessionOutcome = SessionOutcome.UNKNOWN
    hints: list[ResumptionHint] = field(default_factory=list)
    active_threads: list[WorkThread] = field(default_factory=list)
    days_since_last_session: float = 0.0
    greeting_suggestion: str = ""
