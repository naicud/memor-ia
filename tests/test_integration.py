"""Cross-layer integration tests for the 5-layer unified agent/memory protocol.

Groups:
  1. Memory → Context Pipeline (L1 → L5)
  2. Identity → Communication Flow (L2 → L3)
  3. Communication → Orchestration Pipeline (L3 → L4)
  4. Full Pipeline (all 5 layers)
  5. Concurrency & Edge Cases
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

# Layer 1 — Memory
from memoria.core.paths import (
    ensure_memory_dir_exists,
    get_auto_mem_entrypoint,
    get_auto_mem_path,
    get_transcript_path,
)
from memoria.core.types import (
    MemoryFrontmatter,
    MemoryType,
    format_frontmatter,
    parse_frontmatter,
)
from memoria.core.store import (
    create_memory_file,
    delete_memory_file,
    list_memory_files,
    read_memory_file,
    update_entrypoint,
    write_memory_file,
)
from memoria.core.scanner import format_memory_manifest, scan_memory_files
from memoria.core.recall import find_relevant_memories
from memoria.core.transcript import (
    append_message,
    create_session,
    read_transcript,
)

# Layer 2 — Identity
from memoria.identity.agent_id import (
    AgentId,
    AgentProgress,
    SessionId,
    TeammateIdentity,
    create_agent_id,
    create_session_id,
    format_agent_id,
)
from memoria.identity.context import (
    AgentContext,
    get_current_agent,
    is_subagent,
    is_teammate,
    run_in_agent_context,
    set_current_agent,
)
from memoria.identity.factory import (
    SubagentOverrides,
    create_fork_context,
    create_subagent_context,
    create_teammate_context,
)

# Layer 3 — Communication
from memoria.comms.mailbox import Mailbox, MailboxMessage
from memoria.comms.bus import Event, EventType, MessageBus
from memoria.comms.permissions import (
    PermissionBridge,
    PermissionDecision,
)

# Layer 4 — Orchestration
from memoria.orchestration.runner import (
    AgentResult,
    AgentRunner,
    RunnerConfig,
    StopReason,
    TurnResult,
)
from memoria.orchestration.spawner import (
    AgentSpawner,
    ChildStatus,
    SpawnConfig,
    SpawnMode,
)
from memoria.orchestration.team import (
    TeamConfig,
    TeamManager,
    TeamMember,
    _reset_registry,
    create_team,
    disband_team,
    get_team,
)
from memoria.orchestration.fork import ForkAgent, ForkConfig

# Layer 5 — Context Management
from memoria.context.window import (
    TokenBudget,
    analyze_context,
    estimate_messages_tokens,
    estimate_tokens,
    get_budget,
)
from memoria.context.compaction import CompactionConfig, ContextCompactor
from memoria.context.prompt import (
    PromptBuilder,
    PromptConfig,
    PromptSection,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


async def _collect(runner: AgentRunner, msgs: list[dict]) -> list[TurnResult]:
    """Collect all TurnResult from an AgentRunner."""
    results = []
    async for turn in runner.run(msgs):
        results.append(turn)
    return results


def _make_memory_dir(tmp_path: Path) -> str:
    """Create a mock CWD with .claude/projects/<hash>/memory/ structure."""
    cwd = str(tmp_path / "project")
    os.makedirs(cwd, exist_ok=True)
    return cwd


def _write_test_memory(mem_dir: Path, name: str, mtype: MemoryType, body: str) -> Path:
    """Write a test memory file into *mem_dir*."""
    fm = MemoryFrontmatter(name=name, description=f"About {name}", type=mtype)
    p = mem_dir / f"{name.lower().replace(' ', '_')}.md"
    write_memory_file(p, fm, body)
    return p


# ═══════════════════════════════════════════════════════════════════════════
# GROUP 1: Memory → Context Pipeline (L1 → L5)
# ═══════════════════════════════════════════════════════════════════════════


class TestMemoryToContextPipeline:
    """L1 memory_store → memory_scanner → prompt_builder (L5)."""

    def test_write_scan_inject(self, tmp_path: Path):
        """Write memories → scan → format manifest → inject into prompt."""
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()

        _write_test_memory(mem_dir, "Auth Config", MemoryType.PROJECT, "OAuth2 with PKCE")
        _write_test_memory(mem_dir, "Team Prefs", MemoryType.USER, "Prefer async/await")

        headers = scan_memory_files(str(mem_dir))
        assert len(headers) == 2

        manifest = format_memory_manifest(headers)
        assert "Auth Config" in manifest or "auth_config" in manifest
        assert "Team Prefs" in manifest or "team_prefs" in manifest

        builder = PromptBuilder(PromptConfig(
            include_memory=True, include_git_context=False, include_date=False,
            memory_dir=str(mem_dir),
        ))
        prompt = builder.build()
        assert "Memory System" in prompt

    def test_entrypoint_in_prompt(self, tmp_path: Path):
        """MEMORY.md entrypoint content appears in the built prompt."""
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        ep = mem_dir / "MEMORY.md"
        ep.write_text("# Project Notes\n- Use pytest fixtures\n")

        builder = PromptBuilder(PromptConfig(
            include_memory=True, include_git_context=False, include_date=False,
            memory_dir=str(mem_dir),
        ))
        prompt = builder.build()
        assert "Use pytest fixtures" in prompt

    def test_session_transcript_roundtrip(self, tmp_path: Path):
        """Create transcript → append → read back intact."""
        cwd = str(tmp_path / "proj")
        os.makedirs(cwd, exist_ok=True)
        sid = create_session_id()

        with mock.patch("memoria.core.transcript.get_session_dir", return_value=tmp_path / "sessions"):
            sess = create_session(cwd, sid)
            append_message(sess, {"role": "user", "content": "hello"})
            append_message(sess, {"role": "assistant", "content": "hi"})
            sess.close()
            msgs = read_transcript(sess.path)

        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["content"] == "hi"

    def test_recall_scoring_feeds_prompt(self, tmp_path: Path):
        """Recall top memories → inject via custom memory loader."""
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()

        _write_test_memory(mem_dir, "Python Style", MemoryType.FEEDBACK, "Use type hints everywhere")
        _write_test_memory(mem_dir, "Docker Setup", MemoryType.PROJECT, "Use docker compose v2")
        _write_test_memory(mem_dir, "JS Config", MemoryType.REFERENCE, "ESLint flat config")

        relevant = find_relevant_memories("python type hints", str(mem_dir))
        assert len(relevant) > 0
        assert any("python_style" in r.path for r in relevant)

        recall_text = "\n".join(
            f"- [{Path(r.path).name}] (score={r.score:.2f})"
            for r in relevant
        )

        builder = PromptBuilder(PromptConfig(
            include_memory=True, include_git_context=False, include_date=False,
        ))
        builder.set_memory_loader(lambda: f"## Recalled Memories\n{recall_text}")
        prompt = builder.build()
        assert "Recalled Memories" in prompt
        assert "python_style" in prompt

    def test_memory_manifest_token_estimate(self, tmp_path: Path):
        """Manifest text token estimate integrates with budget analysis."""
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        for i in range(5):
            _write_test_memory(mem_dir, f"Item {i}", MemoryType.USER, f"Content {i}")

        headers = scan_memory_files(str(mem_dir))
        manifest = format_memory_manifest(headers)

        tokens = estimate_tokens(manifest)
        budget = get_budget("sonnet")
        assert tokens < budget.available_tokens

    def test_memory_type_filter_then_inject(self, tmp_path: Path):
        """Scan → filter by type → format only matching → inject."""
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()

        _write_test_memory(mem_dir, "UserPref", MemoryType.USER, "dark mode")
        _write_test_memory(mem_dir, "ProjGoal", MemoryType.PROJECT, "ship v2")
        _write_test_memory(mem_dir, "FBNote", MemoryType.FEEDBACK, "avoid globals")

        headers = scan_memory_files(str(mem_dir))
        project_only = [h for h in headers if h.type == MemoryType.PROJECT]
        assert len(project_only) == 1

        manifest = format_memory_manifest(project_only)
        assert "ProjGoal" in manifest or "projgoal" in manifest

        builder = PromptBuilder(PromptConfig(
            include_memory=True, include_git_context=False, include_date=False,
        ))
        builder.set_memory_loader(lambda: f"## Project Context\n{manifest}")
        prompt = builder.build()
        assert "Project Context" in prompt

    def test_write_delete_scan_consistency(self, tmp_path: Path):
        """Create → scan → delete → scan shows removal."""
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()

        p = _write_test_memory(mem_dir, "Temp", MemoryType.REFERENCE, "temp data")
        assert len(scan_memory_files(str(mem_dir))) == 1

        delete_memory_file(p)
        assert len(scan_memory_files(str(mem_dir))) == 0


# ═══════════════════════════════════════════════════════════════════════════
# GROUP 2: Identity → Communication Flow (L2 → L3)
# ═══════════════════════════════════════════════════════════════════════════


class TestIdentityToCommunicationFlow:
    """L2 agent_context → L3 mailbox / message_bus / permission_bridge."""

    def test_agent_context_mailbox_send(self):
        """Create agent context → send message in that context → verify sender."""
        parent = AgentContext(agent_id=create_agent_id("parent"), session_id=create_session_id())
        mbox = Mailbox()

        def send_fn():
            ctx = get_current_agent()
            assert ctx is not None
            mbox.send(MailboxMessage(sender=ctx.agent_id, content="hello from agent"))

        run_in_agent_context(parent, send_fn)
        msg = mbox.poll()
        assert msg is not None
        assert msg.sender == parent.agent_id
        assert msg.content == "hello from agent"

    def test_parent_child_bus_communication(self):
        """Parent & child agents communicate via message bus events."""
        parent_ctx = AgentContext(agent_id=create_agent_id("parent"), session_id=create_session_id())
        child_ctx = create_subagent_context(parent_ctx, label="child")

        bus = MessageBus()
        received: list[Event] = []
        bus.subscribe(EventType.AGENT_COMPLETED.value, lambda e: received.append(e))

        def child_work():
            ctx = get_current_agent()
            assert ctx is not None
            assert is_subagent()
            bus.publish(Event(
                type=EventType.AGENT_COMPLETED,
                source=ctx.agent_id,
                data={"result": "done"},
            ))

        run_in_agent_context(child_ctx, child_work)

        assert len(received) == 1
        assert received[0].source == child_ctx.agent_id
        assert received[0].data["result"] == "done"

    def test_targeted_event_routing(self):
        """Events with target field only handled by matching agent."""
        parent = AgentContext(agent_id=create_agent_id("leader"), session_id=create_session_id())
        child1 = create_subagent_context(parent, label="w1")
        child2 = create_subagent_context(parent, label="w2")

        bus = MessageBus()
        c1_received: list[Event] = []
        c2_received: list[Event] = []

        bus.subscribe(EventType.TASK_UPDATED.value,
                      lambda e: c1_received.append(e) if e.target == child1.agent_id else None)
        bus.subscribe(EventType.TASK_UPDATED.value,
                      lambda e: c2_received.append(e) if e.target == child2.agent_id else None)

        bus.publish(Event(
            type=EventType.TASK_UPDATED,
            source=parent.agent_id,
            target=child1.agent_id,
            data={"task": "only for child1"},
        ))

        assert len(c1_received) == 1
        assert len(c2_received) == 0

    def test_permission_bridge_parent_child(self):
        """Parent authorizes child tool request via handler."""
        parent = AgentContext(agent_id=create_agent_id("parent"), session_id=create_session_id())
        child = create_subagent_context(parent, label="child")

        bridge = PermissionBridge()

        def parent_handler(req):
            if req.tool_name == "read_file":
                req.respond(PermissionDecision.ALLOW)
            else:
                req.respond(PermissionDecision.DENY)

        bridge.register_handler(parent_handler)

        result = bridge.request_permission(child.agent_id, "read_file", timeout=2.0)
        assert result == PermissionDecision.ALLOW

        result2 = bridge.request_permission(child.agent_id, "exec_cmd", timeout=2.0)
        assert result2 == PermissionDecision.DENY

    def test_permission_pre_auth_from_context(self):
        """Pre-authorize tools for child based on spawn config."""
        parent = AgentContext(agent_id=create_agent_id("parent"), session_id=create_session_id())
        child = create_subagent_context(parent, label="child")

        bridge = PermissionBridge()
        bridge.set_allowed_tools(child.agent_id, {"read_file", "list_dir"})
        bridge.set_denied_tools(child.agent_id, {"exec_cmd"})

        assert bridge.check_pre_authorized(child.agent_id, "read_file") == PermissionDecision.ALLOW
        assert bridge.check_pre_authorized(child.agent_id, "exec_cmd") == PermissionDecision.DENY
        assert bridge.check_pre_authorized(child.agent_id, "unknown") is None

    def test_permission_allow_always_remembered(self):
        """ALLOW_ALWAYS is remembered for subsequent requests."""
        child_id = create_agent_id("child")
        bridge = PermissionBridge()

        def handler(req):
            req.respond(PermissionDecision.ALLOW_ALWAYS)

        bridge.register_handler(handler)

        result1 = bridge.request_permission(child_id, "write_file", timeout=2.0)
        assert result1 == PermissionDecision.ALLOW_ALWAYS

        # Second request should be pre-authorized (no handler needed)
        pre = bridge.check_pre_authorized(child_id, "write_file")
        assert pre == PermissionDecision.ALLOW

    def test_teammate_identity_bus_events(self):
        """Teammate agent publishes events with correct identity."""
        parent = AgentContext(agent_id=create_agent_id("leader"), session_id=create_session_id())
        identity = TeammateIdentity(
            agent_id=format_agent_id("researcher", "my-team"),
            agent_name="researcher",
            team_name="my-team",
        )
        teammate_ctx = create_teammate_context(parent, identity)

        bus = MessageBus()
        events: list[Event] = []
        bus.subscribe("*", lambda e: events.append(e))

        def teammate_work():
            ctx = get_current_agent()
            assert is_teammate()
            bus.publish(Event(
                type=EventType.AGENT_ACTIVE,
                source=ctx.agent_id,
                data={"status": "researching"},
            ))

        run_in_agent_context(teammate_ctx, teammate_work)

        assert len(events) == 1
        assert events[0].source == "researcher@my-team"

    def test_contextvars_isolation_concurrent_agents(self):
        """Two agents in parallel threads have isolated contexts."""
        ctx_a = AgentContext(agent_id=create_agent_id("A"), session_id=create_session_id())
        ctx_b = AgentContext(agent_id=create_agent_id("B"), session_id=create_session_id())

        results: dict[str, str] = {}
        barrier = threading.Barrier(2)

        def worker(ctx, key):
            def fn():
                barrier.wait(timeout=5)
                agent = get_current_agent()
                results[key] = agent.agent_id
            run_in_agent_context(ctx, fn)

        t1 = threading.Thread(target=worker, args=(ctx_a, "a"))
        t2 = threading.Thread(target=worker, args=(ctx_b, "b"))
        t1.start(); t2.start()
        t1.join(5); t2.join(5)

        assert results["a"] == ctx_a.agent_id
        assert results["b"] == ctx_b.agent_id
        assert results["a"] != results["b"]

    def test_fork_context_bus_isolation(self):
        """Fork context has independent identity on bus."""
        parent = AgentContext(agent_id=create_agent_id("parent"), session_id=create_session_id())
        fork = create_fork_context(parent, "summarizer")

        assert fork.agent_id != parent.agent_id
        assert fork.session_id == parent.session_id
        assert fork.permission_mode == "bubble"

        bus = MessageBus()
        events: list[Event] = []
        bus.subscribe("*", lambda e: events.append(e))

        bus.publish(Event(type=EventType.AGENT_SPAWNED, source=fork.agent_id))
        assert events[0].source == fork.agent_id


# ═══════════════════════════════════════════════════════════════════════════
# GROUP 3: Communication → Orchestration Pipeline (L3 → L4)
# ═══════════════════════════════════════════════════════════════════════════


class TestCommunicationToOrchestrationPipeline:
    """L3 mailbox/bus → L4 spawner/team/fork."""

    def test_spawner_mailbox_communication(self):
        """Spawn subagent → communicate via mailbox."""
        parent = AgentContext(agent_id=create_agent_id("parent"), session_id=create_session_id())
        spawner = AgentSpawner(parent)

        cfg = SpawnConfig(prompt="Analyze code", mode=SpawnMode.ASYNC, label="analyzer")
        result = spawner.spawn(cfg)
        assert result.success

        mbox = Mailbox()
        mbox.send(MailboxMessage(sender=result.agent_id, content="analysis complete"))

        msg = mbox.poll()
        assert msg is not None
        assert msg.sender == result.agent_id
        assert msg.content == "analysis complete"

        spawner.mark_completed(result.agent_id)
        child = spawner.get_child(result.agent_id)
        assert child["status"] == "completed"

    def test_spawner_bus_lifecycle_events(self):
        """Spawner lifecycle events published on bus."""
        parent = AgentContext(agent_id=create_agent_id("parent"), session_id=create_session_id())
        spawner = AgentSpawner(parent)
        bus = MessageBus()
        events: list[Event] = []
        bus.subscribe("*", lambda e: events.append(e))

        cfg = SpawnConfig(prompt="work", mode=SpawnMode.ASYNC, label="worker")
        result = spawner.spawn(cfg)

        bus.publish(Event(type=EventType.AGENT_SPAWNED, source=result.agent_id))
        spawner.mark_completed(result.agent_id)
        bus.publish(Event(type=EventType.AGENT_COMPLETED, source=result.agent_id))

        assert len(events) == 2
        assert events[0].type == EventType.AGENT_SPAWNED
        assert events[1].type == EventType.AGENT_COMPLETED

    def test_team_workers_exchange_via_bus(self):
        """Team workers exchange messages via bus."""
        _reset_registry()
        config = TeamConfig(
            team_name="test-team",
            leader_agent_id=create_agent_id("leader"),
            leader_session_id=create_session_id(),
        )
        team = TeamManager(config)

        w1_id = create_agent_id("w1")
        w2_id = create_agent_id("w2")
        team.add_member(w1_id, "worker-1", role="worker")
        team.add_member(w2_id, "worker-2", role="worker")

        bus = MessageBus()
        w2_msgs: list[Event] = []
        bus.subscribe(EventType.TASK_UPDATED.value,
                      lambda e: w2_msgs.append(e) if e.target == w2_id else None)

        bus.publish(Event(
            type=EventType.TASK_UPDATED,
            source=w1_id,
            target=w2_id,
            data={"task": "review file.py"},
        ))

        assert len(w2_msgs) == 1
        assert w2_msgs[0].data["task"] == "review file.py"

    def test_team_idle_detection_with_bus(self):
        """Team idle detection triggers bus event."""
        _reset_registry()
        config = TeamConfig(
            team_name="idle-test",
            leader_agent_id=create_agent_id("leader"),
            leader_session_id=create_session_id(),
        )
        team = TeamManager(config)
        bus = MessageBus()

        w_id = create_agent_id("w")
        team.add_member(w_id, "worker")

        idle_events: list[Event] = []

        def on_idle(member):
            bus.publish(Event(
                type=EventType.AGENT_IDLE,
                source=member.agent_id,
            ))

        team.on_member_idle(on_idle)
        bus.subscribe(EventType.AGENT_IDLE.value, lambda e: idle_events.append(e))

        team.mark_idle(w_id)
        assert len(idle_events) == 1
        assert idle_events[0].source == w_id
        assert team.all_idle

    def test_fork_agent_with_context_isolation(self):
        """Fork shares parent messages but has isolated context."""
        parent = AgentContext(agent_id=create_agent_id("parent"), session_id=create_session_id())
        fork_ctx = create_fork_context(parent, "summarizer")

        parent_msgs = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Analyze this code"},
        ]
        forked = ForkAgent.build_forked_messages(parent_msgs, "Summarize the above")
        assert len(forked) == 3
        assert forked[-1]["role"] == "user"

        # Verify context isolation
        seen_ids: list[str] = []

        def in_fork():
            ctx = get_current_agent()
            seen_ids.append(ctx.agent_id)

        run_in_agent_context(fork_ctx, in_fork)
        assert seen_ids[0] == fork_ctx.agent_id
        assert seen_ids[0] != parent.agent_id

    def test_spawner_kill_all_with_bus_notification(self):
        """Kill all children → bus events for each."""
        parent = AgentContext(agent_id=create_agent_id("parent"), session_id=create_session_id())
        spawner = AgentSpawner(parent)
        bus = MessageBus()
        kill_events: list[Event] = []
        bus.subscribe(EventType.AGENT_KILLED.value, lambda e: kill_events.append(e))

        ids = []
        for i in range(3):
            r = spawner.spawn(SpawnConfig(prompt=f"task {i}", label=f"w{i}"))
            ids.append(r.agent_id)

        killed = spawner.kill_all()
        for aid in ids:
            bus.publish(Event(type=EventType.AGENT_KILLED, source=aid))

        assert killed == 3
        assert len(kill_events) == 3

    def test_permission_bridge_with_spawned_agent(self):
        """Spawned agent requests permission via bridge."""
        parent = AgentContext(agent_id=create_agent_id("parent"), session_id=create_session_id())
        spawner = AgentSpawner(parent)
        bridge = PermissionBridge()

        result = spawner.spawn(SpawnConfig(prompt="work", label="child"))
        child_id = result.agent_id

        bridge.set_allowed_tools(child_id, {"read_file"})
        assert bridge.request_permission(child_id, "read_file", timeout=1.0) == PermissionDecision.ALLOW

    def test_team_manager_with_spawner_coordination(self):
        """TeamManager tracks members while spawner handles lifecycle."""
        _reset_registry()
        parent = AgentContext(agent_id=create_agent_id("leader"), session_id=create_session_id())
        spawner = AgentSpawner(parent)
        config = TeamConfig(
            team_name="coord-team",
            leader_agent_id=parent.agent_id,
            leader_session_id=parent.session_id,
        )
        team = TeamManager(config)

        r1 = spawner.spawn(SpawnConfig(prompt="task1", label="w1"))
        r2 = spawner.spawn(SpawnConfig(prompt="task2", label="w2"))

        team.add_member(r1.agent_id, "worker-1")
        team.add_member(r2.agent_id, "worker-2")
        assert team.size == 2

        spawner.mark_completed(r1.agent_id)
        team.mark_completed(r1.agent_id)
        assert len(team.get_active_members()) == 1

        spawner.mark_completed(r2.agent_id)
        team.mark_completed(r2.agent_id)
        assert team.all_idle  # All terminal → considered "idle"


# ═══════════════════════════════════════════════════════════════════════════
# GROUP 4: Full Pipeline (all 5 layers)
# ═══════════════════════════════════════════════════════════════════════════


class TestFullPipeline:
    """End-to-end tests spanning all 5 layers."""

    def test_agent_spawns_reads_memory_builds_prompt_runs(self, tmp_path: Path):
        """Agent spawns → identity → reads memory → builds prompt → runs loop."""
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        _write_test_memory(mem_dir, "Coding Style", MemoryType.USER, "Use type hints")

        parent = AgentContext(agent_id=create_agent_id("main"), session_id=create_session_id())
        child = create_subagent_context(parent, label="coder")

        relevant = find_relevant_memories("type hints style", str(mem_dir))
        recall_text = "\n".join(f"- {Path(r.path).name}" for r in relevant)

        builder = PromptBuilder(PromptConfig(
            include_memory=True, include_git_context=False, include_date=False,
        ))
        builder.set_memory_loader(lambda: f"## Recalled\n{recall_text}")
        system_prompt = builder.build()
        assert "coding_style" in system_prompt

        # Run agent loop with mock model
        call_count = 0
        async def mock_model(msgs):
            nonlocal call_count
            call_count += 1
            return {"role": "assistant", "content": f"I'll follow type hints. (turn {call_count})"}

        async def mock_tool(tc):
            return {"role": "tool", "content": "ok"}

        runner = AgentRunner(
            config=RunnerConfig(max_turns=5),
            call_model=mock_model,
            execute_tool=mock_tool,
            agent_context=child,
        )

        initial = [{"role": "system", "content": system_prompt}, {"role": "user", "content": "fix code"}]
        turns = _run(_collect(runner, initial))

        assert len(turns) == 1
        assert turns[0].stop_reason == StopReason.END_TURN
        result = runner.get_result(child.agent_id)
        assert "type hints" in result.content
        assert result.turns == 1

    def test_agent_runs_sends_result_via_bus(self, tmp_path: Path):
        """Agent runs → result published on bus → parent receives."""
        parent = AgentContext(agent_id=create_agent_id("parent"), session_id=create_session_id())
        child = create_subagent_context(parent, label="analyzer")
        bus = MessageBus()
        results: list[Event] = []
        bus.subscribe(EventType.AGENT_COMPLETED.value, lambda e: results.append(e))

        async def mock_model(msgs):
            return {"role": "assistant", "content": "Analysis: all good"}

        runner = AgentRunner(
            config=RunnerConfig(max_turns=5),
            call_model=mock_model,
            execute_tool=mock.AsyncMock(),
            agent_context=child,
        )

        turns = _run(_collect(runner, [{"role": "user", "content": "analyze"}]))
        agent_result = runner.get_result(child.agent_id)

        bus.publish(Event(
            type=EventType.AGENT_COMPLETED,
            source=child.agent_id,
            data={"content": agent_result.content, "tokens": agent_result.total_tokens},
        ))

        assert len(results) == 1
        assert results[0].data["content"] == "Analysis: all good"

    def test_team_workers_read_different_memories(self, tmp_path: Path):
        """Leader spawns 2 workers, each reads different memory, coordinates via bus."""
        _reset_registry()
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        _write_test_memory(mem_dir, "Auth Setup", MemoryType.PROJECT, "JWT tokens required")
        _write_test_memory(mem_dir, "DB Schema", MemoryType.PROJECT, "PostgreSQL with migrations")

        leader = AgentContext(agent_id=create_agent_id("leader"), session_id=create_session_id())
        bus = MessageBus()
        worker_results: list[dict] = []
        bus.subscribe(EventType.TASK_COMPLETED.value,
                      lambda e: worker_results.append(e.data))

        team_cfg = TeamConfig(
            team_name="research-team",
            leader_agent_id=leader.agent_id,
            leader_session_id=leader.session_id,
        )
        team = TeamManager(team_cfg)

        w1_ctx = create_subagent_context(leader, label="auth-worker")
        w2_ctx = create_subagent_context(leader, label="db-worker")
        team.add_member(w1_ctx.agent_id, "auth-worker")
        team.add_member(w2_ctx.agent_id, "db-worker")

        # Worker 1 reads auth memory
        def w1_work():
            relevant = find_relevant_memories("auth JWT", str(mem_dir))
            content = Path(relevant[0].path).read_text() if relevant else ""
            bus.publish(Event(
                type=EventType.TASK_COMPLETED,
                source=get_current_agent().agent_id,
                data={"topic": "auth", "content": content},
            ))

        # Worker 2 reads db memory
        def w2_work():
            relevant = find_relevant_memories("database schema", str(mem_dir))
            content = Path(relevant[0].path).read_text() if relevant else ""
            bus.publish(Event(
                type=EventType.TASK_COMPLETED,
                source=get_current_agent().agent_id,
                data={"topic": "db", "content": content},
            ))

        run_in_agent_context(w1_ctx, w1_work)
        run_in_agent_context(w2_ctx, w2_work)

        assert len(worker_results) == 2
        topics = {r["topic"] for r in worker_results}
        assert topics == {"auth", "db"}
        assert any("JWT" in r["content"] for r in worker_results)
        assert any("PostgreSQL" in r["content"] for r in worker_results)

        team.mark_completed(w1_ctx.agent_id)
        team.mark_completed(w2_ctx.agent_id)
        assert team.all_idle

    def test_leader_compacts_after_workers_report(self, tmp_path: Path):
        """Workers report → leader collects → compacts context."""
        leader = AgentContext(agent_id=create_agent_id("leader"), session_id=create_session_id())
        bus = MessageBus()
        reports: list[str] = []
        bus.subscribe(EventType.TASK_COMPLETED.value,
                      lambda e: reports.append(e.data.get("summary", "")))

        # Workers publish summaries
        for i in range(3):
            bus.publish(Event(
                type=EventType.TASK_COMPLETED,
                source=create_agent_id(f"w{i}"),
                data={"summary": f"Worker {i} found {i*10} issues"},
            ))

        # Leader builds context from reports
        messages = [{"role": "system", "content": "You are a leader agent."}]
        for report in reports:
            messages.append({"role": "user", "content": report})
            messages.append({"role": "assistant", "content": f"Noted: {report}"})

        compactor = ContextCompactor(CompactionConfig(preserve_recent_n=2))
        budget = get_budget("sonnet")

        # Micro compact (non-destructive)
        compacted = compactor.micro_compact(messages)
        assert len(compacted) <= len(messages)

        # Full compact
        compacted_full, boundary = _run(compactor.full_compact(messages))
        if boundary:
            assert boundary.original_message_count > 0
            assert compactor.compact_count > 0

    def test_fork_reads_memory_parent_gets_result(self, tmp_path: Path):
        """Fork reads memory → parent receives result."""
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        _write_test_memory(mem_dir, "API Docs", MemoryType.REFERENCE, "REST API v3 endpoints")

        parent = AgentContext(agent_id=create_agent_id("parent"), session_id=create_session_id())
        fork_ctx = create_fork_context(parent, "doc-reader")

        # Fork reads memory and builds messages
        relevant = find_relevant_memories("API endpoints REST", str(mem_dir))
        memory_text = Path(relevant[0].path).read_text() if relevant else ""

        parent_msgs = [
            {"role": "system", "content": "Analyze the API"},
            {"role": "user", "content": memory_text},
        ]
        forked_msgs = ForkAgent.build_forked_messages(parent_msgs, "Summarize the API")

        fork = ForkAgent(parent_context=parent)
        result = _run(fork.run(ForkConfig(
            fork_label="doc-reader",
            prompt_messages=forked_msgs,
        )))

        assert len(result.messages) == 3  # parent msgs + directive
        assert result.messages[-1]["role"] == "user"

    def test_full_lifecycle_spawn_run_permission_complete(self):
        """Full lifecycle: spawn → permission check → run → complete → bus notification."""
        parent = AgentContext(agent_id=create_agent_id("orchestrator"), session_id=create_session_id())
        spawner = AgentSpawner(parent)
        bridge = PermissionBridge()
        bus = MessageBus()
        lifecycle: list[str] = []

        bus.subscribe("*", lambda e: lifecycle.append(
            f"{e.type.value if hasattr(e.type, 'value') else e.type}:{e.source}"
        ))

        # Spawn child
        result = spawner.spawn(SpawnConfig(prompt="fix bugs", label="fixer"))
        child_id = result.agent_id
        bus.publish(Event(type=EventType.AGENT_SPAWNED, source=child_id))

        # Permission check
        bridge.set_allowed_tools(child_id, {"edit_file"})
        assert bridge.request_permission(child_id, "edit_file", timeout=1.0) == PermissionDecision.ALLOW

        # Mark complete
        spawner.mark_completed(child_id)
        bus.publish(Event(type=EventType.AGENT_COMPLETED, source=child_id))

        assert len(lifecycle) == 2
        assert "agent.spawned" in lifecycle[0]
        assert "agent.completed" in lifecycle[1]

    def test_context_analysis_with_memory_loaded_prompt(self, tmp_path: Path):
        """Build prompt with memory → analyze context window usage."""
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        for i in range(10):
            _write_test_memory(mem_dir, f"Item{i}", MemoryType.USER, f"Detail {i} " * 50)

        builder = PromptBuilder(PromptConfig(
            include_memory=True, include_git_context=False, include_date=False,
            memory_dir=str(mem_dir),
        ))
        system_prompt = builder.build()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "do work"},
        ]

        budget = get_budget("sonnet")
        analysis = analyze_context(messages, budget)
        assert analysis.total_tokens > 0
        assert analysis.system_prompt_tokens > 0
        assert 0 < analysis.utilization < 1.0

    def test_prompt_sections_priority_ordering_with_memory(self, tmp_path: Path):
        """Priority sections + memory injection ordered correctly in prompt."""
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        ep = mem_dir / "MEMORY.md"
        ep.write_text("# Quick Notes\n- Always test edge cases\n")

        builder = PromptBuilder(PromptConfig(
            include_memory=True, include_git_context=False, include_date=False,
            memory_dir=str(mem_dir),
        ))
        builder.add_section(PromptSection(name="rules", content="Follow PEP8", priority=100, cacheable=True))
        builder.add_section(PromptSection(name="tools", content="Available: read, write", priority=50, cacheable=True))
        builder.add_section(PromptSection(name="session", content="Session: abc123", priority=10, cacheable=False))

        prompt = builder.build()
        # High priority cacheable sections first
        assert prompt.index("Follow PEP8") < prompt.index("Available: read, write")
        # Memory after dynamic boundary
        assert "Memory System" in prompt
        assert "Always test edge cases" in prompt


# ═══════════════════════════════════════════════════════════════════════════
# GROUP 5: Concurrency & Edge Cases
# ═══════════════════════════════════════════════════════════════════════════


class TestConcurrencyAndEdgeCases:
    """Stress tests and edge-case handling across layers."""

    def test_concurrent_memory_writes_no_corruption(self, tmp_path: Path):
        """Multiple threads writing memory files → no corruption."""
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        errors: list[str] = []

        def writer(idx: int):
            try:
                fm = MemoryFrontmatter(
                    name=f"Thread{idx}",
                    description=f"Written by thread {idx}",
                    type=MemoryType.USER,
                )
                p = mem_dir / f"thread_{idx}.md"
                write_memory_file(p, fm, f"Content from thread {idx}\n" * 10)
                # Read back and verify
                fm_read, body = read_memory_file(p)
                assert fm_read.name == f"Thread{idx}"
                assert f"Content from thread {idx}" in body
            except Exception as e:
                errors.append(f"Thread {idx}: {e}")

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)

        assert not errors, f"Errors: {errors}"
        assert len(list(mem_dir.glob("*.md"))) == 20

        headers = scan_memory_files(str(mem_dir))
        assert len(headers) == 20

    def test_bus_under_load(self):
        """100 events with 10 subscribers → all delivered correctly."""
        bus = MessageBus()
        counters: dict[int, int] = {i: 0 for i in range(10)}

        def make_handler(idx):
            def handler(e):
                counters[idx] += 1
            return handler

        for i in range(10):
            bus.subscribe(EventType.TASK_UPDATED.value, make_handler(i))

        for i in range(100):
            bus.publish(Event(
                type=EventType.TASK_UPDATED,
                source=f"agent-{i}",
                data={"seq": i},
            ))

        for idx, count in counters.items():
            assert count == 100, f"Subscriber {idx} got {count} events"

        history = bus.get_events(event_type=EventType.TASK_UPDATED.value)
        assert len(history) == 100

    def test_bus_concurrent_publish_subscribe(self):
        """Concurrent publishers and subscribers on bus."""
        bus = MessageBus()
        received = []
        lock = threading.Lock()

        def subscriber(event):
            with lock:
                received.append(event)

        bus.subscribe(EventType.MESSAGE_SENT.value, subscriber)

        def publisher(idx):
            for j in range(10):
                bus.publish(Event(
                    type=EventType.MESSAGE_SENT,
                    source=f"pub-{idx}",
                    data={"seq": j},
                ))

        threads = [threading.Thread(target=publisher, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)

        assert len(received) == 100

    def test_permission_timeout_graceful_deny(self):
        """Permission request with no handler → timeout → DENY."""
        bridge = PermissionBridge()
        # No handler registered — request will timeout
        result = bridge.request_permission(
            agent_id=create_agent_id("child"),
            tool_name="dangerous_tool",
            timeout=0.1,
        )
        assert result == PermissionDecision.DENY

    def test_permission_concurrent_requests(self):
        """Multiple concurrent permission requests handled correctly."""
        bridge = PermissionBridge()
        results: dict[int, PermissionDecision] = {}

        def handler(req):
            # Simulate processing delay
            time.sleep(0.01)
            req.respond(PermissionDecision.ALLOW)

        bridge.register_handler(handler)

        def requester(idx):
            r = bridge.request_permission(
                agent_id=create_agent_id(f"agent-{idx}"),
                tool_name=f"tool-{idx}",
                timeout=5.0,
            )
            results[idx] = r

        threads = [threading.Thread(target=requester, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)

        assert len(results) == 10
        assert all(r == PermissionDecision.ALLOW for r in results.values())

    def test_compaction_during_active_communication(self):
        """Context compaction while messages are being added."""
        messages = [{"role": "system", "content": "You are helpful."}]
        for i in range(30):
            messages.append({"role": "user", "content": f"Question {i}: " + "x" * 200})
            messages.append({"role": "assistant", "content": f"Answer {i}: " + "y" * 200})

        compactor = ContextCompactor(CompactionConfig(preserve_recent_n=5))
        budget = get_budget("sonnet")

        # Micro compact preserves recent and system
        micro = compactor.micro_compact(messages)
        assert micro[0]["role"] == "system"
        assert len(micro) <= len(messages)

        # Full compact
        compacted, boundary = _run(compactor.full_compact(messages))
        assert boundary is not None
        assert boundary.original_message_count > 0
        # System msg + boundary + recent preserved
        assert len(compacted) < len(messages)
        assert any(m.get("_compact_boundary") for m in compacted)

    def test_mailbox_concurrent_send_receive(self):
        """Multiple senders and receivers on same mailbox."""
        mbox = Mailbox()
        received: list[str] = []
        lock = threading.Lock()

        def sender(idx):
            for j in range(10):
                mbox.send(MailboxMessage(sender=f"s{idx}", content=f"{idx}-{j}"))

        def receiver():
            for _ in range(20):
                msg = mbox.receive(timeout=2.0)
                if msg:
                    with lock:
                        received.append(msg.content)

        senders = [threading.Thread(target=sender, args=(i,)) for i in range(5)]
        receivers = [threading.Thread(target=receiver) for _ in range(2)]

        for t in senders + receivers:
            t.start()
        for t in senders:
            t.join(10)

        # Wait for receivers to drain
        time.sleep(0.5)
        for t in receivers:
            t.join(5)

        # All 50 messages should be received (5 senders × 10 msgs each,
        # 2 receivers × 20 attempts = 40 attempts, but drain remainder)
        remaining = mbox.drain()
        total = len(received) + len(remaining)
        assert total == 50

    def test_agent_abort_during_runner(self):
        """Abort event set during runner → stops cleanly."""
        ctx = AgentContext(agent_id=create_agent_id("abortable"), session_id=create_session_id())

        call_count = 0
        async def mock_model(msgs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                ctx.abort_event.set()
            return {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "t1", "name": "read", "input": {}},
                ],
            }

        async def mock_tool(tc):
            return {"role": "tool", "content": "ok"}

        runner = AgentRunner(
            config=RunnerConfig(max_turns=10),
            call_model=mock_model,
            execute_tool=mock_tool,
            agent_context=ctx,
        )

        turns = _run(_collect(runner, [{"role": "user", "content": "go"}]))
        result = runner.get_result(ctx.agent_id)
        assert result.stop_reason == StopReason.ABORT
        assert result.turns <= 3

    def test_spawner_cleanup_kills_active(self):
        """Spawner cleanup kills all active children."""
        parent = AgentContext(agent_id=create_agent_id("p"), session_id=create_session_id())
        spawner = AgentSpawner(parent)

        cleanup_ran = []
        spawner.register_cleanup(lambda: cleanup_ran.append(True))

        for i in range(5):
            spawner.spawn(SpawnConfig(prompt=f"task {i}", label=f"c{i}"))

        assert len(spawner.list_children(status="running")) == 5

        spawner.cleanup()
        assert len(spawner.list_children(status="killed")) == 5
        assert len(cleanup_ran) == 1

    def test_memory_recall_empty_query(self, tmp_path: Path):
        """Empty query → no crash, returns empty."""
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        _write_test_memory(mem_dir, "Item", MemoryType.USER, "something")

        result = find_relevant_memories("", str(mem_dir))
        assert isinstance(result, list)

    def test_nested_subagent_depth_tracking(self):
        """Root → sub → sub-sub tracks depth correctly."""
        root = AgentContext(agent_id=create_agent_id("root"), session_id=create_session_id())
        assert root.depth == 0

        child = create_subagent_context(root, label="child")
        assert child.depth == 1
        assert child.parent_agent_id == root.agent_id

        grandchild = create_subagent_context(child, label="grandchild")
        assert grandchild.depth == 2
        assert grandchild.parent_agent_id == child.agent_id

        # All share same session
        assert root.session_id == child.session_id == grandchild.session_id

    def test_bus_wildcard_receives_all_event_types(self):
        """Wildcard subscriber receives events of all types."""
        bus = MessageBus()
        all_events: list[Event] = []
        bus.subscribe("*", lambda e: all_events.append(e))

        bus.publish(Event(type=EventType.AGENT_SPAWNED, source="a1"))
        bus.publish(Event(type=EventType.TASK_COMPLETED, source="a2"))
        bus.publish(Event(type=EventType.MEMORY_UPDATED, source="a3"))

        assert len(all_events) == 3
        types = {e.type for e in all_events}
        assert EventType.AGENT_SPAWNED in types
        assert EventType.TASK_COMPLETED in types
        assert EventType.MEMORY_UPDATED in types

    def test_team_max_capacity_enforced(self):
        """Team rejects members beyond max_members."""
        _reset_registry()
        config = TeamConfig(
            team_name="tiny-team",
            leader_agent_id=create_agent_id("leader"),
            leader_session_id=create_session_id(),
            max_members=2,
        )
        team = TeamManager(config)
        team.add_member(create_agent_id("w1"), "w1")
        team.add_member(create_agent_id("w2"), "w2")

        with pytest.raises(ValueError, match="max capacity"):
            team.add_member(create_agent_id("w3"), "w3")

    def test_compaction_preserves_system_message(self):
        """Full compaction always preserves system message."""
        messages = [{"role": "system", "content": "Core instructions: be helpful"}]
        for i in range(20):
            messages.append({"role": "user", "content": f"msg {i}"})
            messages.append({"role": "assistant", "content": f"reply {i}"})

        compactor = ContextCompactor(CompactionConfig(preserve_recent_n=3))
        compacted, boundary = _run(compactor.full_compact(messages))

        system_msgs = [m for m in compacted if m.get("role") == "system"]
        assert len(system_msgs) == 1
        assert "Core instructions" in system_msgs[0]["content"]

    def test_context_analysis_needs_compaction_flag(self):
        """Analyze context → needs_compaction when over threshold."""
        budget = TokenBudget(max_input_tokens=1000, reserve_tokens=100, compact_threshold=0.5)
        # Available = 900, trigger = 450
        # Each message ~50+ chars = ~13+ tokens, plus overhead
        messages = [
            {"role": "user", "content": "x" * 2000},
        ]
        analysis = analyze_context(messages, budget)
        assert analysis.needs_compaction is True

    def test_runner_max_turns_enforced(self):
        """Runner stops at max_turns."""
        async def mock_model(msgs):
            return {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "t1", "name": "read", "input": {}}],
            }

        async def mock_tool(tc):
            return {"role": "tool", "content": "ok"}

        runner = AgentRunner(
            config=RunnerConfig(max_turns=3),
            call_model=mock_model,
            execute_tool=mock_tool,
        )

        turns = _run(_collect(runner, [{"role": "user", "content": "go"}]))
        # 3 tool turns + 1 max_turns sentinel
        result = runner.get_result("test")
        assert result.stop_reason == StopReason.MAX_TURNS
        assert result.turns == 3

    def test_runner_stop_hook_halts_loop(self):
        """Stop hook returning True halts the runner."""
        call_count = 0

        async def mock_model(msgs):
            nonlocal call_count
            call_count += 1
            return {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": f"t{call_count}", "name": "read", "input": {}}],
            }

        async def mock_tool(tc):
            return {"role": "tool", "content": "ok"}

        runner = AgentRunner(
            config=RunnerConfig(max_turns=100),
            call_model=mock_model,
            execute_tool=mock_tool,
        )
        runner.add_stop_hook(lambda msgs, turn: len(turn.tool_calls) > 0)

        turns = _run(_collect(runner, [{"role": "user", "content": "go"}]))
        result = runner.get_result("test")
        assert result.stop_reason == StopReason.STOP_HOOK
        assert result.turns == 1

    def test_multiple_memory_types_recall_ranking(self, tmp_path: Path):
        """Recall correctly ranks memories across types by keyword relevance."""
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()

        # Recall uses filename + description for scoring (not body).
        # "Python Type Hints" description has all 3 query tokens in filename.
        fm1 = MemoryFrontmatter(name="Python Type Hints", description="Python type hints guide", type=MemoryType.FEEDBACK)
        p1 = mem_dir / "python_type_hints.md"
        write_memory_file(p1, fm1, "Always use type hints everywhere")

        fm2 = MemoryFrontmatter(name="Docker Guide", description="Docker compose networking", type=MemoryType.REFERENCE)
        p2 = mem_dir / "docker_guide.md"
        write_memory_file(p2, fm2, "Docker compose networking setup")

        fm3 = MemoryFrontmatter(name="Python Config", description="Project config settings", type=MemoryType.PROJECT)
        p3 = mem_dir / "python_config.md"
        write_memory_file(p3, fm3, "Uses pyproject.toml and pytest")

        relevant = find_relevant_memories("python type hints", str(mem_dir))
        assert len(relevant) >= 1
        # "python_type_hints.md" matches all 3 query tokens in filename
        assert "python_type_hints" in relevant[0].path

    def test_team_shutdown_with_bus_and_spawner(self):
        """Team shutdown coordinates across bus and spawner."""
        _reset_registry()
        parent = AgentContext(agent_id=create_agent_id("leader"), session_id=create_session_id())
        spawner = AgentSpawner(parent)
        bus = MessageBus()
        shutdown_events: list[Event] = []
        bus.subscribe(EventType.SHUTDOWN_REQUESTED.value, lambda e: shutdown_events.append(e))

        config = TeamConfig(
            team_name="shutdown-team",
            leader_agent_id=parent.agent_id,
            leader_session_id=parent.session_id,
        )
        team = TeamManager(config)

        r1 = spawner.spawn(SpawnConfig(prompt="t1", label="w1"))
        team.add_member(r1.agent_id, "w1")

        # Request shutdown
        bus.publish(Event(type=EventType.SHUTDOWN_REQUESTED, source=parent.agent_id))
        team.request_shutdown()
        spawner.kill_all()

        assert len(shutdown_events) == 1
        assert team.shutdown_requested
        member = team.get_member(r1.agent_id)
        assert member.status == "killed"

    def test_entrypoint_truncation_with_token_budget(self, tmp_path: Path):
        """Large MEMORY.md truncated, still fits in token budget."""
        from memoria.core.store import truncate_entrypoint

        huge_content = "Important note\n" * 500
        trunc = truncate_entrypoint(huge_content)
        assert trunc.was_line_truncated or trunc.was_byte_truncated

        tokens = estimate_tokens(trunc.content)
        budget = get_budget("sonnet")
        assert tokens < budget.available_tokens
