"""Protocol bridge — thin coordination layer between the 5-layer unified
protocol and the 7-task system.

Provides a single entry-point (``ProtocolBridge``) that wraps a
``TaskManager`` and wires every task lifecycle event through the
appropriate protocol layer:

    Layer 1 (memdir)        → persistent memory per task
    Layer 2 (agent)         → ``AgentContext`` creation / isolation
    Layer 3 (comms)         → ``MessageBus`` events, ``Mailbox`` routing
    Layer 4 (orchestration) → ``AgentSpawner``, ``TeamManager`` integration
    Layer 5 (context_mgmt)  → ``ContextCompactor`` per task
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    from src.task import (
        TaskStatus,
        TaskType,
        create_task_state_base,
        generate_task_id,
    )
except ImportError:
    TaskStatus = None  # type: ignore[assignment,misc]
    TaskType = None  # type: ignore[assignment,misc]
    create_task_state_base = None  # type: ignore[assignment]
    generate_task_id = None  # type: ignore[assignment]

# Layer 1 — memory
from memoria.core import (
    MemoryType,
    create_memory_file,
    find_relevant_memories,
    read_memory_file,
    write_memory_file,
)
from memoria.core.types import MemoryFrontmatter

# Layer 2 — agent identity & context
from memoria.identity import (
    AgentContext,
    AgentId,
    SessionId,
    create_agent_id,
    create_session_id,
    create_subagent_context,
)

# Layer 3 — comms
from memoria.comms import (
    Event,
    EventType,
    Mailbox,
    MailboxMessage,
    get_message_bus,
    get_permission_bridge,
)

# Layer 4 — orchestration
from memoria.orchestration import (
    AgentSpawner,
    SpawnConfig,
    TeamConfig,
    TeamManager,
    create_team,
    disband_team,
    get_team,
)

# Layer 5 — context management
from memoria.context import (
    CompactionConfig,
    ContextCompactor,
    TokenBudget,
    analyze_context,
    get_budget,
)

# Task framework
try:
    from src.utils.task_framework import TaskManager
except ImportError:
    TaskManager = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

@dataclass
class _TaskBridgeState:
    """Per-task bookkeeping managed by the bridge."""

    task_id: str
    agent_context: AgentContext
    mailbox: Mailbox = field(default_factory=Mailbox)
    compactor: ContextCompactor = field(default_factory=ContextCompactor)
    messages: list[dict] = field(default_factory=list)
    memory_dir: Optional[str] = None
    parent_task_id: Optional[str] = None


# ---------------------------------------------------------------------------
# ProtocolBridge
# ---------------------------------------------------------------------------

class ProtocolBridge:
    """Bridge between the unified protocol layers and the task system.

    Thread-safe — all mutable state is protected by ``_lock``.
    """

    def __init__(
        self,
        task_manager: TaskManager,
        *,
        memory_cwd: str = ".",
        default_budget: TokenBudget | None = None,
    ) -> None:
        self._tm = task_manager
        self._memory_cwd = memory_cwd
        self._budget = default_budget or get_budget()
        self._lock = threading.Lock()

        # task_id → _TaskBridgeState
        self._states: dict[str, _TaskBridgeState] = {}

        # Keep a reference to the bus subscription so we can unsubscribe
        self._bus = get_message_bus()
        self._permission_bridge = get_permission_bridge()

        # Subscribe to task manager updates
        self._unsub_tm = self._tm.subscribe(self._on_task_updated)

    # -- public API ---------------------------------------------------------

    def create_task_with_context(
        self,
        task_type: TaskType,
        config: dict[str, Any],
    ) -> tuple[str, AgentContext]:
        """Create a task and its associated ``AgentContext`` (Layer 2).

        *config* may contain:
            description  — human-readable task description
            tool_use_id  — optional tool-use identifier
            label        — optional label for the agent id
            memory_dir   — optional per-task memory directory

        Returns ``(task_id, agent_context)``.
        """
        description = config.get("description", "")
        tool_use_id = config.get("tool_use_id")
        label = config.get("label", task_type.value)
        memory_dir = config.get("memory_dir", self._memory_cwd)

        task_id = generate_task_id(task_type)
        task_state = create_task_state_base(task_id, task_type, description, tool_use_id)

        # Layer 2 — create agent context
        agent_id = create_agent_id(label)
        session_id = create_session_id()
        agent_ctx = AgentContext(
            agent_id=agent_id,
            session_id=session_id,
        )

        # Layer 5 — per-task compactor
        compactor = ContextCompactor(
            config=config.get("compaction_config", CompactionConfig()),
        )

        bridge_state = _TaskBridgeState(
            task_id=task_id,
            agent_context=agent_ctx,
            memory_dir=memory_dir,
            compactor=compactor,
        )

        with self._lock:
            self._states[task_id] = bridge_state

        # Register with the task manager
        self._tm.register_task(task_state)

        # Layer 3 — publish event on the bus
        self._bus.publish(Event(
            type=EventType.TASK_REGISTERED,
            source=str(agent_id),
            data={"task_id": task_id, "task_type": task_type.value},
        ))

        logger.debug("Created task %s with agent %s", task_id, agent_id)
        return task_id, agent_ctx

    def send_to_task(self, task_id: str, message: str) -> bool:
        """Route *message* to *task_id* via its ``Mailbox`` (Layer 3).

        Returns ``True`` if the message was delivered, ``False`` if the
        task is unknown.
        """
        with self._lock:
            state = self._states.get(task_id)

        if state is None:
            logger.warning("send_to_task: unknown task %s", task_id)
            return False

        mailbox_msg = MailboxMessage(
            sender="bridge",
            content=message,
        )
        state.mailbox.send(mailbox_msg)

        # Also publish on the bus
        self._bus.publish(Event(
            type=EventType.MESSAGE_SENT,
            source="bridge",
            data={"task_id": task_id, "content": message},
            target=str(state.agent_context.agent_id),
        ))

        return True

    def receive_from_task(
        self, task_id: str, *, timeout: float | None = None
    ) -> MailboxMessage | None:
        """Receive a message from a task's mailbox (Layer 3)."""
        with self._lock:
            state = self._states.get(task_id)

        if state is None:
            return None

        return state.mailbox.receive(timeout=timeout)

    def get_task_memory(
        self, task_id: str, query: str = ""
    ) -> list[Any]:
        """Read memory for the task's agent (Layer 1).

        If *query* is provided, returns relevant memories via recall.
        Otherwise returns all memories in the task's memory directory.
        """
        with self._lock:
            state = self._states.get(task_id)

        if state is None:
            return []

        mem_dir = state.memory_dir or self._memory_cwd

        if query:
            return find_relevant_memories(query, mem_dir)

        # Return the memory dir path so callers can inspect
        mem_path = Path(mem_dir)
        if not mem_path.exists():
            return []

        from memoria.core import list_memory_files
        return list(list_memory_files(mem_dir))

    def save_task_memory(
        self,
        task_id: str,
        name: str,
        content: str,
        *,
        description: str = "",
        memory_type: MemoryType = MemoryType.PROJECT,
    ) -> Path | None:
        """Persist a memory file for the task (Layer 1).

        Returns the file path or ``None`` if the task is unknown.
        """
        with self._lock:
            state = self._states.get(task_id)

        if state is None:
            return None

        mem_dir = state.memory_dir or self._memory_cwd
        path = create_memory_file(
            cwd=mem_dir,
            name=name,
            memory_type=memory_type,
            description=description,
            content=content,
        )

        # Publish memory event
        self._bus.publish(Event(
            type=EventType.MEMORY_UPDATED,
            source=str(state.agent_context.agent_id),
            data={"task_id": task_id, "path": str(path)},
        ))

        return path

    def compact_task_context(
        self, task_id: str, messages: list[dict] | None = None,
    ) -> list[dict]:
        """Run context compaction for a task (Layer 5).

        If *messages* is ``None``, uses the task's internal message list.
        Returns the (possibly compacted) message list.
        """
        with self._lock:
            state = self._states.get(task_id)

        if state is None:
            return messages or []

        msgs = messages if messages is not None else state.messages
        compactor = state.compactor

        if compactor.should_compact(msgs, self._budget):
            compacted = compactor.micro_compact(msgs)
            logger.debug(
                "Compacted task %s: %d → %d messages",
                task_id, len(msgs), len(compacted),
            )
            # Update stored messages
            with self._lock:
                state.messages = compacted
            return compacted

        return msgs

    def add_task_message(self, task_id: str, message: dict) -> None:
        """Append a message to the task's context (Layer 5)."""
        with self._lock:
            state = self._states.get(task_id)

        if state is None:
            return

        with self._lock:
            state.messages.append(message)

    def analyze_task_context(self, task_id: str) -> Any | None:
        """Analyze token usage for a task's context (Layer 5)."""
        with self._lock:
            state = self._states.get(task_id)

        if state is None:
            return None

        return analyze_context(state.messages, self._budget)

    def spawn_subtask(
        self,
        parent_id: str,
        task_type: TaskType,
        config: dict[str, Any],
    ) -> tuple[str, AgentContext] | None:
        """Spawn a subtask with proper parent→child isolation (Layer 2 + 4).

        Returns ``(child_task_id, child_agent_context)`` or ``None`` if
        the parent is unknown.
        """
        with self._lock:
            parent_state = self._states.get(parent_id)

        if parent_state is None:
            logger.warning("spawn_subtask: unknown parent %s", parent_id)
            return None

        # Create child task
        child_task_id, child_ctx = self.create_task_with_context(task_type, config)

        # Layer 2 — create isolated subagent context from parent
        isolated_ctx = create_subagent_context(
            parent_state.agent_context,
            label=config.get("label", "subtask"),
        )

        # Update the child's bridge state with the isolated context
        with self._lock:
            child_state = self._states.get(child_task_id)
            if child_state is not None:
                child_state.agent_context = isolated_ctx
                child_state.parent_task_id = parent_id

        # Publish spawn event
        self._bus.publish(Event(
            type=EventType.AGENT_SPAWNED,
            source=str(parent_state.agent_context.agent_id),
            data={
                "parent_task_id": parent_id,
                "child_task_id": child_task_id,
                "task_type": task_type.value,
            },
        ))

        logger.debug(
            "Spawned subtask %s from parent %s", child_task_id, parent_id,
        )
        return child_task_id, isolated_ctx

    def create_team(
        self,
        leader_task_id: str,
        worker_configs: list[dict[str, Any]],
        *,
        team_name: str = "",
    ) -> TeamManager | None:
        """Create a team via ``TeamManager`` (Layer 4).

        The *leader_task_id* must be a known task.  Each entry in
        *worker_configs* is passed to ``create_task_with_context`` and
        the resulting task is added to the team.

        Returns the ``TeamManager`` or ``None`` on failure.
        """
        with self._lock:
            leader_state = self._states.get(leader_task_id)

        if leader_state is None:
            logger.warning("create_team: unknown leader %s", leader_task_id)
            return None

        name = team_name or f"team-{leader_task_id}"
        leader_ctx = leader_state.agent_context

        tm_config = TeamConfig(
            team_name=name,
            leader_agent_id=str(leader_ctx.agent_id),
            leader_session_id=str(leader_ctx.session_id),
        )
        manager = create_team(tm_config)
        manager.add_member(
            str(leader_ctx.agent_id),
            config.get("agent_name", "leader") if (config := {}) else "leader",
            role="leader",
        )

        # Spawn workers
        for wcfg in worker_configs:
            task_type = wcfg.pop("task_type", TaskType.IN_PROCESS_TEAMMATE)
            if isinstance(task_type, str):
                task_type = TaskType(task_type)

            result = self.spawn_subtask(leader_task_id, task_type, wcfg)
            if result is not None:
                child_id, child_ctx = result
                agent_name = wcfg.get("agent_name", wcfg.get("label", child_id))
                manager.add_member(
                    str(child_ctx.agent_id),
                    agent_name,
                    role="worker",
                    task_id=child_id,
                )

        return manager

    def get_task_context(self, task_id: str) -> AgentContext | None:
        """Return the ``AgentContext`` for *task_id*, or ``None``."""
        with self._lock:
            state = self._states.get(task_id)
        return state.agent_context if state is not None else None

    def get_task_mailbox(self, task_id: str) -> Mailbox | None:
        """Return the ``Mailbox`` for *task_id*, or ``None``."""
        with self._lock:
            state = self._states.get(task_id)
        return state.mailbox if state is not None else None

    # -- lifecycle management -----------------------------------------------

    def remove_task(self, task_id: str) -> None:
        """Clean up bridge state for a task."""
        with self._lock:
            state = self._states.pop(task_id, None)

        if state is not None:
            state.mailbox.clear()
            logger.debug("Removed bridge state for task %s", task_id)

    def shutdown(self) -> None:
        """Unsubscribe from the task manager and clean up."""
        self._unsub_tm()
        with self._lock:
            for state in self._states.values():
                state.mailbox.clear()
            self._states.clear()

    # -- internal -----------------------------------------------------------

    def _on_task_updated(self, task_id: str, task_state: Any) -> None:
        """Callback from ``TaskManager.subscribe``."""
        with self._lock:
            state = self._states.get(task_id)

        if state is None:
            return

        status = getattr(task_state, "status", None)
        if status is None:
            return

        # Map status to EventType
        event_type = _status_to_event_type(status)
        if event_type is not None:
            self._bus.publish(Event(
                type=event_type,
                source=str(state.agent_context.agent_id),
                data={"task_id": task_id, "status": str(status)},
            ))

    @property
    def task_count(self) -> int:
        """Number of tasks tracked by the bridge."""
        with self._lock:
            return len(self._states)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _status_to_event_type(status: Any) -> EventType | None:
    """Map a ``TaskStatus`` to the corresponding ``EventType``."""
    status_str = status.value if hasattr(status, "value") else str(status)
    mapping = {
        "completed": EventType.TASK_COMPLETED,
        "failed": EventType.AGENT_FAILED,
        "killed": EventType.AGENT_KILLED,
        "running": EventType.AGENT_ACTIVE,
        "pending": EventType.TASK_REGISTERED,
    }
    return mapping.get(status_str)
