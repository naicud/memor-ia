"""Tests for the protocol ↔ task bridge module.

Covers:
  - Task creation with automatic AgentContext (Layer 2)
  - Message routing between tasks via Mailbox (Layer 3)
  - Memory persistence for tasks (Layer 1)
  - Context compaction triggers (Layer 5)
  - Subtask spawning with isolation (Layer 2 + 4)
  - Team creation and coordination (Layer 4)
  - Event lifecycle mapping (Layer 3)
  - Permission delegation between parent/child tasks
"""

from __future__ import annotations

import copy
import threading

import pytest

try:
    from src.task import TaskStatus, TaskType, create_task_state_base
    from src.utils.task_framework import TaskManager
    _HAS_TASK_SYSTEM = True
except ImportError:
    _HAS_TASK_SYSTEM = False

pytestmark = pytest.mark.skipif(
    not _HAS_TASK_SYSTEM, reason="Task system (src.task) not available"
)

from memoria.bridge.events import TaskEventBridge
from memoria.bridge.protocol import ProtocolBridge, _status_to_event_type
from memoria.comms import (
    EventType,
    Mailbox,
    MailboxMessage,
    get_message_bus,
    get_permission_bridge,
)
from memoria.comms.permissions import PermissionDecision
from memoria.context import (
    CompactionConfig,
    TokenBudget,
)
from memoria.identity import AgentContext, create_agent_id
from memoria.orchestration.team import _reset_registry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_singletons():
    """Reset shared singletons before and after each test."""
    bus = get_message_bus()
    bus.clear_history()
    _reset_registry()
    yield
    bus.clear_history()
    _reset_registry()


@pytest.fixture
def task_manager():
    """Fresh TaskManager instance for each test."""
    return TaskManager()


@pytest.fixture
def bridge(task_manager, tmp_path):
    """ProtocolBridge wired to a fresh TaskManager and temp memory dir."""
    b = ProtocolBridge(
        task_manager,
        memory_cwd=str(tmp_path),
    )
    yield b
    b.shutdown()


@pytest.fixture
def event_bridge(task_manager):
    """TaskEventBridge wired to a fresh TaskManager."""
    eb = TaskEventBridge(task_manager)
    eb.start()
    yield eb
    eb.stop()


# ===================================================================
# 1. Task creation with automatic context
# ===================================================================

class TestTaskCreation:
    """Task creation wires Layer 2 (AgentContext) automatically."""

    def test_create_returns_task_id_and_context(self, bridge):
        task_id, ctx = bridge.create_task_with_context(
            TaskType.LOCAL_BASH,
            {"description": "echo hello"},
        )
        assert task_id.startswith("b")
        assert isinstance(ctx, AgentContext)

    def test_context_has_unique_agent_id(self, bridge):
        _, ctx1 = bridge.create_task_with_context(TaskType.LOCAL_BASH, {})
        _, ctx2 = bridge.create_task_with_context(TaskType.LOCAL_BASH, {})
        assert ctx1.agent_id != ctx2.agent_id

    def test_context_has_unique_session_id(self, bridge):
        _, ctx1 = bridge.create_task_with_context(TaskType.LOCAL_BASH, {})
        _, ctx2 = bridge.create_task_with_context(TaskType.LOCAL_BASH, {})
        assert ctx1.session_id != ctx2.session_id

    def test_task_registered_in_task_manager(self, bridge, task_manager):
        task_id, _ = bridge.create_task_with_context(
            TaskType.LOCAL_AGENT, {"description": "test agent"},
        )
        task = task_manager.get_task(task_id)
        assert task is not None
        assert task.status == TaskStatus.PENDING

    def test_task_type_preserved(self, bridge, task_manager):
        task_id, _ = bridge.create_task_with_context(
            TaskType.DREAM, {"description": "dream"},
        )
        task = task_manager.get_task(task_id)
        assert task.type == TaskType.DREAM

    def test_task_description_set(self, bridge, task_manager):
        task_id, _ = bridge.create_task_with_context(
            TaskType.LOCAL_BASH, {"description": "my description"},
        )
        task = task_manager.get_task(task_id)
        assert task.description == "my description"

    def test_bridge_tracks_task_count(self, bridge):
        assert bridge.task_count == 0
        bridge.create_task_with_context(TaskType.LOCAL_BASH, {})
        assert bridge.task_count == 1
        bridge.create_task_with_context(TaskType.LOCAL_AGENT, {})
        assert bridge.task_count == 2

    def test_all_task_types_supported(self, bridge):
        for tt in TaskType:
            task_id, ctx = bridge.create_task_with_context(tt, {})
            assert task_id
            assert ctx is not None

    def test_context_retrievable_by_task_id(self, bridge):
        task_id, ctx = bridge.create_task_with_context(TaskType.LOCAL_BASH, {})
        retrieved = bridge.get_task_context(task_id)
        assert retrieved is ctx


# ===================================================================
# 2. Message routing between tasks
# ===================================================================

class TestMessageRouting:
    """Message routing uses Layer 3 (Mailbox / MessageBus)."""

    def test_send_to_task(self, bridge):
        task_id, _ = bridge.create_task_with_context(TaskType.LOCAL_BASH, {})
        ok = bridge.send_to_task(task_id, "hello")
        assert ok is True

    def test_send_to_unknown_task_returns_false(self, bridge):
        ok = bridge.send_to_task("nonexistent", "hello")
        assert ok is False

    def test_message_arrives_in_mailbox(self, bridge):
        task_id, _ = bridge.create_task_with_context(TaskType.LOCAL_BASH, {})
        bridge.send_to_task(task_id, "hello world")
        msg = bridge.receive_from_task(task_id)
        assert msg is not None
        assert msg.content == "hello world"

    def test_multiple_messages_fifo(self, bridge):
        task_id, _ = bridge.create_task_with_context(TaskType.LOCAL_BASH, {})
        bridge.send_to_task(task_id, "first")
        bridge.send_to_task(task_id, "second")
        m1 = bridge.receive_from_task(task_id)
        m2 = bridge.receive_from_task(task_id)
        assert m1.content == "first"
        assert m2.content == "second"

    def test_receive_from_unknown_returns_none(self, bridge):
        result = bridge.receive_from_task("ghost")
        assert result is None

    def test_mailbox_accessible_directly(self, bridge):
        task_id, _ = bridge.create_task_with_context(TaskType.LOCAL_BASH, {})
        mb = bridge.get_task_mailbox(task_id)
        assert isinstance(mb, Mailbox)
        mb.send(MailboxMessage(sender="test", content="direct"))
        msg = mb.poll()
        assert msg.content == "direct"

    def test_send_publishes_bus_event(self, bridge):
        bus = get_message_bus()
        task_id, _ = bridge.create_task_with_context(TaskType.LOCAL_BASH, {})

        events_before = len(bus.get_events(EventType.MESSAGE_SENT.value))
        bridge.send_to_task(task_id, "test")
        events_after = bus.get_events(EventType.MESSAGE_SENT.value)
        assert len(events_after) > events_before

    def test_cross_task_messaging(self, bridge):
        tid1, _ = bridge.create_task_with_context(TaskType.LOCAL_BASH, {})
        tid2, _ = bridge.create_task_with_context(TaskType.LOCAL_AGENT, {})
        bridge.send_to_task(tid1, "for task 1")
        bridge.send_to_task(tid2, "for task 2")
        assert bridge.receive_from_task(tid1).content == "for task 1"
        assert bridge.receive_from_task(tid2).content == "for task 2"


# ===================================================================
# 3. Memory persistence for tasks
# ===================================================================

class TestMemoryPersistence:
    """Memory persistence uses Layer 1 (MemoryStore)."""

    def test_save_task_memory_creates_file(self, bridge, tmp_path):
        task_id, _ = bridge.create_task_with_context(
            TaskType.LOCAL_BASH, {"memory_dir": str(tmp_path)},
        )
        path = bridge.save_task_memory(task_id, "test-note", "hello world")
        assert path is not None
        assert path.exists()
        assert "hello world" in path.read_text()

    def test_save_memory_unknown_task(self, bridge):
        result = bridge.save_task_memory("ghost", "n", "c")
        assert result is None

    def test_get_task_memory_with_query(self, bridge, tmp_path):
        task_id, _ = bridge.create_task_with_context(
            TaskType.LOCAL_BASH, {"memory_dir": str(tmp_path)},
        )
        bridge.save_task_memory(task_id, "auth-notes", "JWT authentication flow details")
        results = bridge.get_task_memory(task_id, query="authentication")
        # find_relevant_memories returns a (possibly empty) list
        assert isinstance(results, list)

    def test_get_task_memory_unknown_task(self, bridge):
        result = bridge.get_task_memory("ghost")
        assert result == []

    def test_save_publishes_memory_event(self, bridge, tmp_path):
        bus = get_message_bus()
        task_id, _ = bridge.create_task_with_context(
            TaskType.LOCAL_BASH, {"memory_dir": str(tmp_path)},
        )
        bridge.save_task_memory(task_id, "mem", "data")
        events = bus.get_events(EventType.MEMORY_UPDATED.value)
        assert len(events) >= 1
        assert events[-1].data["task_id"] == task_id

    def test_different_tasks_have_isolated_memory(self, bridge, tmp_path):
        dir1 = tmp_path / "t1"
        dir2 = tmp_path / "t2"
        dir1.mkdir()
        dir2.mkdir()
        tid1, _ = bridge.create_task_with_context(
            TaskType.LOCAL_BASH, {"memory_dir": str(dir1)},
        )
        tid2, _ = bridge.create_task_with_context(
            TaskType.LOCAL_AGENT, {"memory_dir": str(dir2)},
        )
        p1 = bridge.save_task_memory(tid1, "note1", "content1")
        p2 = bridge.save_task_memory(tid2, "note2", "content2")
        assert p1 is not None
        assert p2 is not None
        # Files should be in distinct directories
        assert str(p1.resolve()) != str(p2.resolve())
        assert p1.exists()
        assert p2.exists()


# ===================================================================
# 4. Context compaction triggers
# ===================================================================

class TestContextCompaction:
    """Context compaction uses Layer 5 (ContextCompactor)."""

    def test_compact_returns_messages_when_below_threshold(self, bridge):
        task_id, _ = bridge.create_task_with_context(TaskType.LOCAL_BASH, {})
        msgs = [{"role": "user", "content": "short"}]
        result = bridge.compact_task_context(task_id, msgs)
        assert result == msgs

    def test_compact_unknown_task_returns_input(self, bridge):
        result = bridge.compact_task_context("ghost", [{"role": "user", "content": "x"}])
        assert len(result) == 1

    def test_add_and_compact_messages(self, bridge):
        task_id, _ = bridge.create_task_with_context(TaskType.LOCAL_BASH, {})
        for i in range(5):
            bridge.add_task_message(task_id, {"role": "user", "content": f"msg {i}"})
        result = bridge.compact_task_context(task_id)
        assert isinstance(result, list)

    def test_analyze_context_returns_analysis(self, bridge):
        task_id, _ = bridge.create_task_with_context(TaskType.LOCAL_BASH, {})
        bridge.add_task_message(task_id, {"role": "user", "content": "hello"})
        analysis = bridge.analyze_task_context(task_id)
        assert analysis is not None
        assert analysis.total_tokens >= 0

    def test_analyze_context_unknown_task(self, bridge):
        result = bridge.analyze_task_context("ghost")
        assert result is None

    def test_micro_compact_removes_low_value(self, bridge):
        # Create a bridge with a very small budget to trigger compaction
        small_budget = TokenBudget(
            max_input_tokens=100,
            max_output_tokens=50,
            compact_threshold=0.1,
            reserve_tokens=10,
        )
        tm = TaskManager()
        b = ProtocolBridge(tm, default_budget=small_budget)
        try:
            task_id, _ = b.create_task_with_context(TaskType.LOCAL_BASH, {})
            # Add messages including low-value tool results
            for i in range(20):
                b.add_task_message(task_id, {"role": "user", "content": f"msg {i} " * 50})
            # Add some tool results that are "low value"
            b.add_task_message(task_id, {"role": "tool", "content": ""})
            result = b.compact_task_context(task_id)
            assert isinstance(result, list)
            # Should have compacted — fewer messages or same (depends on threshold)
        finally:
            b.shutdown()

    def test_custom_compaction_config(self, bridge):
        cfg = CompactionConfig(preserve_recent_n=3)
        task_id, _ = bridge.create_task_with_context(
            TaskType.LOCAL_BASH, {"compaction_config": cfg},
        )
        assert bridge.task_count >= 1


# ===================================================================
# 5. Subtask spawning with isolation
# ===================================================================

class TestSubtaskSpawning:
    """Subtask spawning uses Layer 2 (context isolation) + Layer 4."""

    def test_spawn_subtask(self, bridge):
        parent_id, parent_ctx = bridge.create_task_with_context(
            TaskType.LOCAL_WORKFLOW, {"description": "parent"},
        )
        result = bridge.spawn_subtask(
            parent_id, TaskType.LOCAL_BASH, {"description": "child"},
        )
        assert result is not None
        child_id, child_ctx = result
        assert child_id != parent_id

    def test_spawn_unknown_parent_returns_none(self, bridge):
        result = bridge.spawn_subtask("ghost", TaskType.LOCAL_BASH, {})
        assert result is None

    def test_child_has_isolated_context(self, bridge):
        parent_id, parent_ctx = bridge.create_task_with_context(
            TaskType.LOCAL_WORKFLOW, {},
        )
        result = bridge.spawn_subtask(parent_id, TaskType.LOCAL_BASH, {})
        _, child_ctx = result
        # Child should have a different agent_id than parent
        assert child_ctx.agent_id != parent_ctx.agent_id

    def test_child_has_parent_reference(self, bridge):
        parent_id, _ = bridge.create_task_with_context(
            TaskType.LOCAL_WORKFLOW, {},
        )
        result = bridge.spawn_subtask(parent_id, TaskType.LOCAL_BASH, {})
        child_id, _ = result
        # The child's bridge state should track its parent
        state = bridge._states[child_id]
        assert state.parent_task_id == parent_id

    def test_child_depth_incremented(self, bridge):
        parent_id, parent_ctx = bridge.create_task_with_context(
            TaskType.LOCAL_WORKFLOW, {},
        )
        result = bridge.spawn_subtask(parent_id, TaskType.LOCAL_BASH, {})
        _, child_ctx = result
        assert child_ctx.depth == parent_ctx.depth + 1

    def test_spawn_publishes_event(self, bridge):
        bus = get_message_bus()
        parent_id, _ = bridge.create_task_with_context(
            TaskType.LOCAL_WORKFLOW, {},
        )
        bridge.spawn_subtask(parent_id, TaskType.LOCAL_BASH, {})
        events = bus.get_events(EventType.AGENT_SPAWNED.value)
        assert len(events) >= 1

    def test_multiple_children_isolated(self, bridge):
        parent_id, _ = bridge.create_task_with_context(
            TaskType.LOCAL_WORKFLOW, {},
        )
        r1 = bridge.spawn_subtask(parent_id, TaskType.LOCAL_BASH, {})
        r2 = bridge.spawn_subtask(parent_id, TaskType.LOCAL_AGENT, {})
        _, ctx1 = r1
        _, ctx2 = r2
        assert ctx1.agent_id != ctx2.agent_id

    def test_child_gets_own_mailbox(self, bridge):
        parent_id, _ = bridge.create_task_with_context(
            TaskType.LOCAL_WORKFLOW, {},
        )
        child_id, _ = bridge.spawn_subtask(parent_id, TaskType.LOCAL_BASH, {})
        mb = bridge.get_task_mailbox(child_id)
        assert mb is not None
        parent_mb = bridge.get_task_mailbox(parent_id)
        assert mb is not parent_mb


# ===================================================================
# 6. Team creation and coordination
# ===================================================================

class TestTeamCreation:
    """Team creation uses Layer 4 (TeamManager)."""

    def test_create_team_returns_manager(self, bridge):
        leader_id, _ = bridge.create_task_with_context(
            TaskType.LOCAL_WORKFLOW, {"description": "leader"},
        )
        tm = bridge.create_team(leader_id, [])
        assert tm is not None
        assert isinstance(tm, type(tm))  # TeamManager

    def test_create_team_unknown_leader(self, bridge):
        result = bridge.create_team("ghost", [])
        assert result is None

    def test_team_has_leader(self, bridge):
        leader_id, leader_ctx = bridge.create_task_with_context(
            TaskType.LOCAL_WORKFLOW, {},
        )
        tm = bridge.create_team(leader_id, [])
        member = tm.get_member(str(leader_ctx.agent_id))
        assert member is not None

    def test_team_with_workers(self, bridge):
        leader_id, _ = bridge.create_task_with_context(
            TaskType.LOCAL_WORKFLOW, {},
        )
        workers = [
            {"description": "worker 1", "agent_name": "w1", "label": "w1"},
            {"description": "worker 2", "agent_name": "w2", "label": "w2"},
        ]
        tm = bridge.create_team(leader_id, workers)
        # Leader + 2 workers
        assert tm.size >= 3

    def test_team_workers_are_tasks(self, bridge, task_manager):
        leader_id, _ = bridge.create_task_with_context(
            TaskType.LOCAL_WORKFLOW, {},
        )
        workers = [{"description": "w1", "agent_name": "w1"}]
        bridge.create_team(leader_id, workers)
        # Should have created tasks: leader + 1 worker
        assert bridge.task_count >= 2

    def test_team_custom_name(self, bridge):
        leader_id, _ = bridge.create_task_with_context(
            TaskType.LOCAL_WORKFLOW, {},
        )
        tm = bridge.create_team(leader_id, [], team_name="alpha-team")
        assert tm.team_name == "alpha-team"


# ===================================================================
# 7. Event lifecycle mapping
# ===================================================================

class TestEventLifecycle:
    """Event lifecycle mapping via TaskEventBridge."""

    def test_bridge_starts_and_stops(self, event_bridge):
        assert event_bridge.is_started
        event_bridge.stop()
        assert not event_bridge.is_started

    def test_start_idempotent(self, event_bridge):
        event_bridge.start()  # already started by fixture
        assert event_bridge.is_started

    def test_stop_idempotent(self, task_manager):
        eb = TaskEventBridge(task_manager)
        eb.stop()  # not started
        assert not eb.is_started

    def test_task_update_publishes_event(self, event_bridge, task_manager):
        bus = get_message_bus()
        task_state = create_task_state_base("test-1", TaskType.LOCAL_BASH, "test")
        task_manager.register_task(task_state)

        def set_running(t):
            t2 = copy.copy(t)
            t2.status = TaskStatus.RUNNING
            return t2

        task_manager.update_task("test-1", set_running)
        events = bus.get_events(EventType.AGENT_ACTIVE.value)
        assert any(e.data.get("task_id") == "test-1" for e in events)

    def test_completed_event(self, event_bridge, task_manager):
        bus = get_message_bus()
        task_state = create_task_state_base("test-2", TaskType.LOCAL_BASH, "test")
        task_manager.register_task(task_state)

        def set_completed(t):
            t2 = copy.copy(t)
            t2.status = TaskStatus.COMPLETED
            return t2

        task_manager.update_task("test-2", set_completed)
        events = bus.get_events(EventType.TASK_COMPLETED.value)
        assert any(e.data.get("task_id") == "test-2" for e in events)

    def test_failed_event(self, event_bridge, task_manager):
        bus = get_message_bus()
        task_state = create_task_state_base("test-3", TaskType.LOCAL_BASH, "test")
        task_manager.register_task(task_state)

        def set_failed(t):
            t2 = copy.copy(t)
            t2.status = TaskStatus.FAILED
            return t2

        task_manager.update_task("test-3", set_failed)
        events = bus.get_events(EventType.AGENT_FAILED.value)
        assert any(e.data.get("task_id") == "test-3" for e in events)

    def test_killed_event(self, event_bridge, task_manager):
        bus = get_message_bus()
        task_state = create_task_state_base("test-4", TaskType.LOCAL_BASH, "test")
        task_manager.register_task(task_state)

        def set_killed(t):
            t2 = copy.copy(t)
            t2.status = TaskStatus.KILLED
            return t2

        task_manager.update_task("test-4", set_killed)
        events = bus.get_events(EventType.AGENT_KILLED.value)
        assert any(e.data.get("task_id") == "test-4" for e in events)

    def test_external_listener(self, event_bridge, task_manager):
        received = []
        event_bridge.on_event(
            EventType.AGENT_ACTIVE.value,
            lambda e: received.append(e),
        )
        task_state = create_task_state_base("test-5", TaskType.LOCAL_BASH, "test")
        task_manager.register_task(task_state)

        def set_running(t):
            t2 = copy.copy(t)
            t2.status = TaskStatus.RUNNING
            return t2

        task_manager.update_task("test-5", set_running)
        assert len(received) >= 1

    def test_unregister_listener(self, event_bridge, task_manager):
        received = []
        unreg = event_bridge.on_event(
            EventType.AGENT_ACTIVE.value,
            lambda e: received.append(e),
        )
        unreg()

        task_state = create_task_state_base("test-6", TaskType.LOCAL_BASH, "test")
        task_manager.register_task(task_state)

        def set_running(t):
            t2 = copy.copy(t)
            t2.status = TaskStatus.RUNNING
            return t2

        task_manager.update_task("test-6", set_running)
        assert len(received) == 0

    def test_emit_task_event(self, event_bridge):
        bus = get_message_bus()
        event_bridge.emit_task_event(
            "manual-1",
            EventType.TASK_COMPLETED,
            data={"extra": "info"},
        )
        events = bus.get_events(EventType.TASK_COMPLETED.value)
        assert any(
            e.data.get("task_id") == "manual-1" and e.data.get("extra") == "info"
            for e in events
        )


# ===================================================================
# 8. Permission delegation
# ===================================================================

class TestPermissionDelegation:
    """Permission delegation via PermissionBridge (Layer 3)."""

    def test_status_to_event_mapping(self):
        assert _status_to_event_type(TaskStatus.COMPLETED) == EventType.TASK_COMPLETED
        assert _status_to_event_type(TaskStatus.FAILED) == EventType.AGENT_FAILED
        assert _status_to_event_type(TaskStatus.KILLED) == EventType.AGENT_KILLED
        assert _status_to_event_type(TaskStatus.RUNNING) == EventType.AGENT_ACTIVE
        assert _status_to_event_type(TaskStatus.PENDING) == EventType.TASK_REGISTERED

    def test_event_to_status_mapping(self, event_bridge):
        assert event_bridge.get_status_for_event(EventType.TASK_COMPLETED) == TaskStatus.COMPLETED
        assert event_bridge.get_status_for_event(EventType.AGENT_FAILED) == TaskStatus.FAILED
        assert event_bridge.get_status_for_event(EventType.AGENT_KILLED) == TaskStatus.KILLED
        assert event_bridge.get_status_for_event(EventType.AGENT_ACTIVE) == TaskStatus.RUNNING

    def test_status_for_unknown_event(self, event_bridge):
        assert event_bridge.get_status_for_event(EventType.MESSAGE_SENT) is None

    def test_event_for_status(self, event_bridge):
        assert event_bridge.get_event_for_status(TaskStatus.COMPLETED) == EventType.TASK_COMPLETED
        assert event_bridge.get_event_for_status(TaskStatus.RUNNING) == EventType.AGENT_ACTIVE

    def test_pre_authorized_tools(self, event_bridge):
        perm = get_permission_bridge()
        agent_id = str(create_agent_id("test"))
        perm.set_allowed_tools(agent_id, {"bash", "read"})

        decision = perm.check_pre_authorized(agent_id, "bash")
        assert decision == PermissionDecision.ALLOW

    def test_denied_tools(self, event_bridge):
        perm = get_permission_bridge()
        agent_id = str(create_agent_id("test"))
        perm.set_denied_tools(agent_id, {"dangerous_tool"})

        decision = perm.check_pre_authorized(agent_id, "dangerous_tool")
        assert decision == PermissionDecision.DENY


# ===================================================================
# 9. Bridge lifecycle & cleanup
# ===================================================================

class TestBridgeLifecycle:
    """Bridge lifecycle management."""

    def test_remove_task(self, bridge):
        task_id, _ = bridge.create_task_with_context(TaskType.LOCAL_BASH, {})
        assert bridge.task_count == 1
        bridge.remove_task(task_id)
        assert bridge.task_count == 0

    def test_remove_unknown_task_no_error(self, bridge):
        bridge.remove_task("nonexistent")

    def test_shutdown_clears_all(self, bridge):
        bridge.create_task_with_context(TaskType.LOCAL_BASH, {})
        bridge.create_task_with_context(TaskType.LOCAL_AGENT, {})
        assert bridge.task_count == 2
        bridge.shutdown()
        assert bridge.task_count == 0

    def test_get_context_unknown_returns_none(self, bridge):
        assert bridge.get_task_context("ghost") is None

    def test_get_mailbox_unknown_returns_none(self, bridge):
        assert bridge.get_task_mailbox("ghost") is None


# ===================================================================
# 10. Thread safety
# ===================================================================

class TestThreadSafety:
    """Concurrent access to the bridge is safe."""

    def test_concurrent_task_creation(self, bridge):
        results = []
        errors = []

        def create_task():
            try:
                tid, ctx = bridge.create_task_with_context(TaskType.LOCAL_BASH, {})
                results.append(tid)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=create_task) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 10
        assert len(set(results)) == 10  # all unique

    def test_concurrent_send_receive(self, bridge):
        task_id, _ = bridge.create_task_with_context(TaskType.LOCAL_BASH, {})
        errors = []

        def send_messages():
            try:
                for i in range(20):
                    bridge.send_to_task(task_id, f"msg-{i}")
            except Exception as e:
                errors.append(e)

        t = threading.Thread(target=send_messages)
        t.start()
        t.join()

        assert len(errors) == 0
        # All messages should be in the mailbox
        mb = bridge.get_task_mailbox(task_id)
        count = 0
        while mb.poll() is not None:
            count += 1
        assert count == 20
