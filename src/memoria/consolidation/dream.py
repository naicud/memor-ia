"""DREAM task — background memory consolidation via forked subagent.

DREAM periodically synthesizes recent session activity into durable memory
files.  It operates as a background task that reads recent conversation
transcripts and updates a structured memory index.

Ported from ``src_origin/src/tasks/DreamTask/DreamTask.tsx``.
"""

from __future__ import annotations

import copy
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

try:
    from src.task import (
        Task,
        TaskStateBase,
        TaskStatus,
        TaskType,
        generate_task_id,
        is_terminal_task_status,
    )
    from src.utils.task_framework import (
        get_task,
        register_task,
        update_task,
    )
except ImportError:
    # Task system not available — stub essentials for standalone use
    Task = None  # type: ignore[assignment,misc]
    TaskStateBase = object  # type: ignore[assignment,misc]
    TaskStatus = None  # type: ignore[assignment,misc]
    TaskType = None  # type: ignore[assignment,misc]
    generate_task_id = None  # type: ignore[assignment]
    is_terminal_task_status = None  # type: ignore[assignment]
    get_task = None  # type: ignore[assignment]
    register_task = None  # type: ignore[assignment]
    update_task = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_TURNS: int = 30
"""Maximum number of assistant turns retained in task state."""

MAX_FILES_TOUCHED: int = 500
"""Maximum number of touched file paths retained in task state."""

DREAM_DESCRIPTION: str = "Memory consolidation"
"""Default task description shown in the coordinator panel."""

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DreamTurn:
    """Record of a single assistant turn during dream execution."""

    text: str
    tool_use_count: int


if TaskStateBase is not object:
    @dataclass
    class DreamTaskState(TaskStateBase):
        """Extended state for dream (memory consolidation) tasks.

        ``phase`` tracks UI display state:
        - ``'starting'`` — dream agent launched, no files touched yet
        - ``'updating'`` — at least one memory file has been modified
        """

        phase: str = "starting"
        sessions_reviewing: int = 0
        files_touched: list[str] = field(default_factory=list)
        turns: list[DreamTurn] = field(default_factory=list)
        abort_event: threading.Event | None = field(default=None, repr=False)
        prior_mtime: float = 0.0
else:
    @dataclass
    class DreamTaskState:  # type: ignore[no-redef]
        """Stub when task system is not available."""

        phase: str = "starting"
        sessions_reviewing: int = 0
        files_touched: list[str] = field(default_factory=list)
        turns: list[DreamTurn] = field(default_factory=list)
        abort_event: threading.Event | None = field(default=None, repr=False)
        prior_mtime: float = 0.0


# ---------------------------------------------------------------------------
# Type guard
# ---------------------------------------------------------------------------


def is_dream_task(task: Any) -> bool:
    """Return ``True`` if *task* is a :class:`DreamTaskState`."""
    return isinstance(task, DreamTaskState)


# ---------------------------------------------------------------------------
# Lifecycle — register
# ---------------------------------------------------------------------------


def register_dream_task(
    sessions_reviewing: int,
    abort_event: threading.Event | None = None,
) -> str:
    """Create and register a new dream task.

    Returns the generated task ID (prefix ``'d'``).
    """
    task_id = generate_task_id(TaskType.DREAM)
    if abort_event is None:
        abort_event = threading.Event()

    state = DreamTaskState(
        id=task_id,
        type=TaskType.DREAM,
        status=TaskStatus.RUNNING,
        description=DREAM_DESCRIPTION,
        tool_use_id=None,
        start_time=time.time(),
        end_time=None,
        total_paused_ms=None,
        output_file=f"{task_id}.output",
        output_offset=0,
        notified=False,
        phase="starting",
        sessions_reviewing=sessions_reviewing,
        files_touched=[],
        turns=[],
        abort_event=abort_event,
        prior_mtime=0.0,
    )
    register_task(state)
    logger.info(
        "Registered dream task %s (reviewing %d sessions)",
        task_id,
        sessions_reviewing,
    )
    return task_id


# ---------------------------------------------------------------------------
# Lifecycle — add turn
# ---------------------------------------------------------------------------


def add_dream_turn(
    task_id: str,
    turn: DreamTurn,
    touched_paths: list[str] | None = None,
) -> None:
    """Append an assistant turn and update ``files_touched``.

    The turn list is capped at :data:`MAX_TURNS` (oldest evicted first).
    When the first file path is touched the phase flips from ``'starting'``
    to ``'updating'``.
    """

    def _updater(t: Any) -> Any:
        if not is_dream_task(t) or is_terminal_task_status(t.status):
            return t
        u = copy.copy(t)
        u.turns = list(t.turns)
        u.turns.append(turn)
        if len(u.turns) > MAX_TURNS:
            u.turns = u.turns[-MAX_TURNS:]

        if touched_paths:
            u.files_touched = list(t.files_touched)
            for p in touched_paths:
                if p not in u.files_touched:
                    u.files_touched.append(p)
            if len(u.files_touched) > MAX_FILES_TOUCHED:
                u.files_touched = u.files_touched[-MAX_FILES_TOUCHED:]
            if t.phase == "starting":
                u.phase = "updating"
        return u

    update_task(task_id, _updater)


# ---------------------------------------------------------------------------
# Lifecycle — complete / fail / kill
# ---------------------------------------------------------------------------


def complete_dream_task(task_id: str) -> None:
    """Mark a dream task as completed."""

    def _complete(t: Any) -> Any:
        if not is_dream_task(t) or is_terminal_task_status(t.status):
            return t
        u = copy.copy(t)
        u.status = TaskStatus.COMPLETED
        u.end_time = time.time()
        u.notified = True
        return u

    update_task(task_id, _complete)
    logger.info("Dream task %s completed", task_id)


def fail_dream_task(task_id: str) -> None:
    """Mark a dream task as failed."""

    def _fail(t: Any) -> Any:
        if not is_dream_task(t) or is_terminal_task_status(t.status):
            return t
        u = copy.copy(t)
        u.status = TaskStatus.FAILED
        u.end_time = time.time()
        u.notified = True
        return u

    update_task(task_id, _fail)
    logger.info("Dream task %s failed", task_id)


def kill_dream_task(task_id: str) -> None:
    """Kill a running dream task, signalling abort and rolling back lock mtime."""
    task = get_task(task_id)
    if task is None or not is_dream_task(task):
        return
    if is_terminal_task_status(task.status):
        return

    # Signal abort
    abort = getattr(task, "abort_event", None)
    if abort is not None:
        abort.set()

    # Rollback consolidation lock if prior_mtime was captured
    prior_mtime = getattr(task, "prior_mtime", 0.0)
    if prior_mtime > 0.0:
        try:
            from memoria.consolidation.lock import rollback_consolidation_lock
            import os

            lock_dir = os.path.expanduser("~/.claude")
            rollback_consolidation_lock(lock_dir, prior_mtime)
        except Exception:
            logger.exception("Failed to rollback consolidation lock for %s", task_id)

    def _kill(t: Any) -> Any:
        if is_terminal_task_status(t.status):
            return t
        u = copy.copy(t)
        u.status = TaskStatus.KILLED
        u.end_time = time.time()
        u.notified = True
        u.abort_event = None
        return u

    update_task(task_id, _kill)
    logger.info("Dream task %s killed", task_id)


# ---------------------------------------------------------------------------
# Task registration
# ---------------------------------------------------------------------------

if Task is not None:
    DREAM_TASK = Task(
        name="DreamTask",
        type=TaskType.DREAM,
        kill=kill_dream_task,
    )
else:
    DREAM_TASK = None

__all__ = [
    "DREAM_DESCRIPTION",
    "DREAM_TASK",
    "DreamTaskState",
    "DreamTurn",
    "MAX_TURNS",
    "add_dream_turn",
    "complete_dream_task",
    "fail_dream_task",
    "is_dream_task",
    "kill_dream_task",
    "register_dream_task",
]
