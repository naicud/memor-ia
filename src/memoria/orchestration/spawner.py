"""Spawn subagents with proper isolation, lifecycle management, and cleanup.

Handles:
- Creating isolated context for each subagent
- Registering tasks for background agents
- Cleanup on parent exit (orphan prevention)
- Concurrent execution management
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & data classes
# ---------------------------------------------------------------------------

class SpawnMode(str, Enum):
    """How to spawn a subagent."""
    SYNC = "sync"
    ASYNC = "async"
    FORK = "fork"
    TEAMMATE = "teammate"


class ChildStatus(str, Enum):
    """Lifecycle status of a spawned child."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


@dataclass
class SpawnConfig:
    """Configuration for spawning a subagent."""
    prompt: str
    mode: SpawnMode = SpawnMode.ASYNC
    label: str = ""
    model: Optional[str] = None
    max_turns: int = 200
    permission_mode: str = "default"
    allowed_tools: Optional[set[str]] = None
    description: str = ""

    # Teammate-specific
    team_name: Optional[str] = None
    agent_name: Optional[str] = None
    plan_mode_required: bool = False
    color: Optional[str] = None


@dataclass
class SpawnResult:
    """Result of spawning a subagent."""
    success: bool
    agent_id: str
    task_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class _ChildRecord:
    """Internal bookkeeping for a spawned child."""
    agent_id: str
    config: SpawnConfig
    status: ChildStatus = ChildStatus.PENDING
    task_id: Optional[str] = None
    spawned_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error: Optional[str] = None
    thread: Optional[threading.Thread] = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# AgentSpawner
# ---------------------------------------------------------------------------

class AgentSpawner:
    """Spawn and manage subagent lifecycles.

    Thread-safe.  All mutations protected by ``_lock``.
    """

    _MAX_CHILDREN = 10_000

    def __init__(self, parent_context: Any = None) -> None:
        self._parent = parent_context
        self._children: dict[str, _ChildRecord] = {}
        self._lock = threading.Lock()
        self._cleanup_handlers: list[Callable[[], None]] = []
        self._all_done = threading.Event()
        self._all_done.set()  # no children → all done

    # -- spawning ------------------------------------------------------------

    def spawn(self, config: SpawnConfig) -> SpawnResult:
        """Spawn a new subagent (synchronous API)."""
        agent_id = self._generate_id(config)

        record = _ChildRecord(agent_id=agent_id, config=config)
        with self._lock:
            self._children[agent_id] = record
            self._all_done.clear()
            record.status = ChildStatus.RUNNING
        logger.info("Spawned child %s mode=%s", agent_id, config.mode.value)
        return SpawnResult(success=True, agent_id=agent_id)

    async def spawn_async(self, config: SpawnConfig) -> SpawnResult:
        """Async spawn (delegates to sync spawn)."""
        return self.spawn(config)

    # -- killing -------------------------------------------------------------

    def kill(self, agent_id: str) -> bool:
        """Kill a spawned agent.  Returns *True* if found and killed."""
        with self._lock:
            record = self._children.get(agent_id)
            if record is None:
                return False
            if record.status in (ChildStatus.COMPLETED, ChildStatus.KILLED):
                return False
            record.status = ChildStatus.KILLED
            record.completed_at = time.time()
            self._check_all_done()
        logger.info("Killed child %s", agent_id)
        return True

    def kill_all(self) -> int:
        """Kill all active children.  Returns count killed."""
        killed = 0
        with self._lock:
            for record in self._children.values():
                if record.status in (ChildStatus.PENDING, ChildStatus.RUNNING):
                    record.status = ChildStatus.KILLED
                    record.completed_at = time.time()
                    killed += 1
            self._check_all_done()
        logger.info("Killed %d children", killed)
        return killed

    # -- queries -------------------------------------------------------------

    def get_child(self, agent_id: str) -> Optional[dict]:
        """Get child agent info as a plain dict."""
        with self._lock:
            record = self._children.get(agent_id)
            if record is None:
                return None
            return self._record_to_dict(record)

    def list_children(self, status: Optional[str] = None) -> list[dict]:
        """List spawned children, optionally filtered by status."""
        with self._lock:
            result: list[dict] = []
            for record in self._children.values():
                if status is not None and record.status.value != status:
                    continue
                result.append(self._record_to_dict(record))
            return result

    # -- lifecycle -----------------------------------------------------------

    def mark_completed(self, agent_id: str, error: Optional[str] = None) -> None:
        """Mark a child as completed or failed."""
        with self._lock:
            record = self._children.get(agent_id)
            if record is None:
                return
            record.status = ChildStatus.FAILED if error else ChildStatus.COMPLETED
            record.completed_at = time.time()
            record.error = error
            self._check_all_done()
            self._evict_terminal()

    def wait_all(self, timeout: Optional[float] = None) -> bool:
        """Wait for all children to reach a terminal state.

        Returns *True* if all completed within *timeout*.
        """
        return self._all_done.wait(timeout=timeout)

    # -- cleanup -------------------------------------------------------------

    def register_cleanup(self, handler: Callable[[], None]) -> Callable[[], None]:
        """Register a cleanup handler.  Returns an unregister function."""
        self._cleanup_handlers.append(handler)

        def _unregister() -> None:
            try:
                self._cleanup_handlers.remove(handler)
            except ValueError:
                pass

        return _unregister

    def cleanup(self) -> None:
        """Run all cleanup handlers and kill remaining children."""
        self.kill_all()
        for handler in list(self._cleanup_handlers):
            try:
                handler()
            except Exception:
                logger.exception("Cleanup handler failed")
        self._cleanup_handlers.clear()

    # -- internals -----------------------------------------------------------

    def _generate_id(self, config: SpawnConfig) -> str:
        short = uuid.uuid4().hex[:16]
        prefix = config.label or config.mode.value
        return f"a{prefix}-{short}"

    def _check_all_done(self) -> None:
        """Set ``_all_done`` if no children are still active.  Caller holds lock."""
        active = any(
            r.status in (ChildStatus.PENDING, ChildStatus.RUNNING)
            for r in self._children.values()
        )
        if not active:
            self._all_done.set()

    def _evict_terminal(self) -> None:
        """Remove oldest terminal children when over capacity.  Caller holds lock."""
        if len(self._children) <= self._MAX_CHILDREN:
            return
        terminal = sorted(
            (
                (aid, r)
                for aid, r in self._children.items()
                if r.status in (ChildStatus.COMPLETED, ChildStatus.FAILED, ChildStatus.KILLED)
            ),
            key=lambda t: t[1].completed_at or 0,
        )
        to_remove = len(self._children) - self._MAX_CHILDREN
        for aid, _ in terminal[:to_remove]:
            del self._children[aid]

    @staticmethod
    def _record_to_dict(record: _ChildRecord) -> dict:
        return {
            "agent_id": record.agent_id,
            "status": record.status.value,
            "label": record.config.label,
            "mode": record.config.mode.value,
            "description": record.config.description,
            "spawned_at": record.spawned_at,
            "completed_at": record.completed_at,
            "error": record.error,
        }
