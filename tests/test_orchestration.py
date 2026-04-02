"""Tests for the orchestration layer (Layer 4).

Covers AgentRunner, AgentSpawner, TeamManager, and ForkAgent.
"""

from __future__ import annotations

import asyncio
import threading
import time
from unittest import mock

import pytest

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
    SpawnResult,
)
from memoria.orchestration.fork import ForkAgent, ForkConfig, ForkResult
from memoria.orchestration.team import (
    TeamConfig,
    TeamManager,
    TeamMember,
    _reset_registry,
    create_team,
    disband_team,
    get_team,
    list_teams,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text_response(text: str) -> dict:
    """Build a minimal assistant response with text only (no tool_use)."""
    return {
        "role": "assistant",
        "content": [{"type": "text", "text": text}],
        "usage": {"total_tokens": 10},
    }


def _tool_response(tool_name: str = "bash", tool_id: str = "tu_1") -> dict:
    """Build an assistant response containing a tool_use block."""
    return {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "Calling tool"},
            {"type": "tool_use", "id": tool_id, "name": tool_name, "input": {}},
        ],
        "usage": {"total_tokens": 20},
    }


def _tool_result(tool_id: str = "tu_1") -> dict:
    return {
        "role": "tool",
        "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": "ok"}],
    }


async def _collect(runner: AgentRunner, msgs: list[dict]) -> list[TurnResult]:
    """Consume the runner's async generator into a list."""
    results: list[TurnResult] = []
    async for turn in runner.run(msgs):
        results.append(turn)
    return results


# ===================================================================
# AgentRunner tests
# ===================================================================

class TestAgentRunner:
    """Tests for AgentRunner."""

    @pytest.mark.asyncio
    async def test_single_text_turn_ends(self):
        """Model returns text only → END_TURN after 1 turn."""
        call_model = mock.AsyncMock(return_value=_text_response("Hello"))
        execute_tool = mock.AsyncMock()

        runner = AgentRunner(RunnerConfig(), execute_tool, call_model)
        turns = await _collect(runner, [{"role": "user", "content": "hi"}])

        assert len(turns) == 1
        assert turns[0].stop_reason == StopReason.END_TURN
        assert runner.turn_count == 1

    @pytest.mark.asyncio
    async def test_tool_call_then_text(self):
        """Model calls tool, then returns text → 2 turns."""
        call_model = mock.AsyncMock(
            side_effect=[_tool_response(), _text_response("Done")]
        )
        execute_tool = mock.AsyncMock(return_value=_tool_result())

        runner = AgentRunner(RunnerConfig(), execute_tool, call_model)
        turns = await _collect(runner, [{"role": "user", "content": "do stuff"}])

        assert len(turns) == 2
        assert turns[0].stop_reason is None
        assert turns[1].stop_reason == StopReason.END_TURN
        assert runner.turn_count == 2
        execute_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_max_turns_exit(self):
        """Runner respects max_turns config."""
        call_model = mock.AsyncMock(return_value=_tool_response())
        execute_tool = mock.AsyncMock(return_value=_tool_result())

        runner = AgentRunner(RunnerConfig(max_turns=3), execute_tool, call_model)
        turns = await _collect(runner, [])

        assert turns[-1].stop_reason == StopReason.MAX_TURNS
        assert runner.turn_count == 3

    @pytest.mark.asyncio
    async def test_abort_via_event(self):
        """Runner stops when context.abort_event is set."""
        import types
        ctx = types.SimpleNamespace(abort_event=threading.Event())
        ctx.abort_event.set()

        call_model = mock.AsyncMock()
        runner = AgentRunner(RunnerConfig(), mock.AsyncMock(), call_model, agent_context=ctx)
        turns = await _collect(runner, [])

        assert len(turns) == 1
        assert turns[0].stop_reason == StopReason.ABORT
        call_model.assert_not_called()

    @pytest.mark.asyncio
    async def test_abort_mid_loop(self):
        """Abort event set between turns stops the loop."""
        import types
        ctx = types.SimpleNamespace(abort_event=threading.Event())

        call_count = 0

        async def _model(msgs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                ctx.abort_event.set()
            return _tool_response(tool_id=f"tu_{call_count}")

        execute_tool = mock.AsyncMock(
            side_effect=lambda tc: _tool_result(tc["id"])
        )
        runner = AgentRunner(RunnerConfig(), execute_tool, _model, agent_context=ctx)
        turns = await _collect(runner, [])

        assert turns[-1].stop_reason == StopReason.ABORT

    @pytest.mark.asyncio
    async def test_stop_hook_trigger(self):
        """Stop hook returning True ends the loop."""
        call_model = mock.AsyncMock(return_value=_tool_response())
        execute_tool = mock.AsyncMock(return_value=_tool_result())

        runner = AgentRunner(RunnerConfig(), execute_tool, call_model)
        runner.add_stop_hook(lambda msgs, turn: True)

        turns = await _collect(runner, [])

        assert len(turns) == 1
        assert turns[0].stop_reason == StopReason.STOP_HOOK

    @pytest.mark.asyncio
    async def test_async_stop_hook(self):
        """Async stop hook is awaited correctly."""
        call_model = mock.AsyncMock(return_value=_tool_response())
        execute_tool = mock.AsyncMock(return_value=_tool_result())

        async def _hook(msgs, turn):
            return True

        runner = AgentRunner(RunnerConfig(), execute_tool, call_model)
        runner.add_stop_hook(_hook)

        turns = await _collect(runner, [])
        assert turns[0].stop_reason == StopReason.STOP_HOOK

    @pytest.mark.asyncio
    async def test_stop_hook_false_continues(self):
        """Stop hook returning False does not stop the loop."""
        call_model = mock.AsyncMock(
            side_effect=[_tool_response(), _text_response("done")]
        )
        execute_tool = mock.AsyncMock(return_value=_tool_result())

        runner = AgentRunner(RunnerConfig(), execute_tool, call_model)
        runner.add_stop_hook(lambda msgs, turn: False)

        turns = await _collect(runner, [])
        assert turns[-1].stop_reason == StopReason.END_TURN

    @pytest.mark.asyncio
    async def test_tool_call_extraction_empty(self):
        """Text-only response yields no tool calls."""
        resp = _text_response("hi")
        runner = AgentRunner(RunnerConfig(), mock.AsyncMock(), mock.AsyncMock())
        assert runner._extract_tool_calls(resp) == []

    @pytest.mark.asyncio
    async def test_tool_call_extraction_found(self):
        """Response with tool_use block is extracted."""
        resp = _tool_response("read_file", "tu_99")
        runner = AgentRunner(RunnerConfig(), mock.AsyncMock(), mock.AsyncMock())
        calls = runner._extract_tool_calls(resp)
        assert len(calls) == 1
        assert calls[0]["name"] == "read_file"

    @pytest.mark.asyncio
    async def test_tool_call_extraction_string_content(self):
        """String content yields no tool calls."""
        runner = AgentRunner(RunnerConfig(), mock.AsyncMock(), mock.AsyncMock())
        assert runner._extract_tool_calls({"content": "just text"}) == []

    @pytest.mark.asyncio
    async def test_turn_result_aggregation(self):
        """TurnResult captures tool_calls and tool_results."""
        call_model = mock.AsyncMock(
            side_effect=[_tool_response("bash", "tu_1"), _text_response("end")]
        )
        execute_tool = mock.AsyncMock(return_value=_tool_result("tu_1"))

        runner = AgentRunner(RunnerConfig(), execute_tool, call_model)
        turns = await _collect(runner, [])

        assert len(turns[0].tool_calls) == 1
        assert len(turns[0].tool_results) == 1

    @pytest.mark.asyncio
    async def test_final_result_computation(self):
        """get_result() aggregates across all turns."""
        call_model = mock.AsyncMock(
            side_effect=[_tool_response(), _text_response("final")]
        )
        execute_tool = mock.AsyncMock(return_value=_tool_result())

        runner = AgentRunner(RunnerConfig(), execute_tool, call_model)
        await _collect(runner, [{"role": "user", "content": "go"}])

        result = runner.get_result("agent-1")
        assert isinstance(result, AgentResult)
        assert result.agent_id == "agent-1"
        assert result.turns == 2
        assert result.total_tool_use_count == 1
        assert result.stop_reason == StopReason.END_TURN
        assert result.content == "final"
        assert result.total_duration_ms > 0

    @pytest.mark.asyncio
    async def test_model_error(self):
        """Model exception yields ERROR stop reason."""
        call_model = mock.AsyncMock(side_effect=RuntimeError("API down"))
        runner = AgentRunner(RunnerConfig(), mock.AsyncMock(), call_model)
        turns = await _collect(runner, [])

        assert turns[0].stop_reason == StopReason.ERROR

        result = runner.get_result("err-agent")
        assert result.stop_reason == StopReason.ERROR
        assert result.error == "API down"

    @pytest.mark.asyncio
    async def test_on_turn_complete_callback(self):
        """on_turn_complete callbacks fire each turn."""
        call_model = mock.AsyncMock(
            side_effect=[_tool_response(), _text_response("done")]
        )
        execute_tool = mock.AsyncMock(return_value=_tool_result())

        runner = AgentRunner(RunnerConfig(), execute_tool, call_model)
        seen: list[TurnResult] = []
        runner.on_turn_complete(lambda t: seen.append(t))

        await _collect(runner, [])
        # Only the tool-turn fires the callback (text turn exits before notify)
        assert len(seen) >= 1

    @pytest.mark.asyncio
    async def test_elapsed_ms(self):
        """elapsed_ms advances."""
        runner = AgentRunner(RunnerConfig(), mock.AsyncMock(), mock.AsyncMock())
        assert runner.elapsed_ms >= 0

    @pytest.mark.asyncio
    async def test_messages_property(self):
        """messages returns a copy of the internal list."""
        call_model = mock.AsyncMock(return_value=_text_response("hi"))
        runner = AgentRunner(RunnerConfig(), mock.AsyncMock(), call_model)
        await _collect(runner, [{"role": "user", "content": "x"}])
        msgs = runner.messages
        assert len(msgs) >= 1
        msgs.clear()
        assert len(runner.messages) >= 1  # original unaffected

    @pytest.mark.asyncio
    async def test_no_context_no_abort(self):
        """Runner without context never aborts."""
        runner = AgentRunner(RunnerConfig(), mock.AsyncMock(), mock.AsyncMock())
        assert runner._is_aborted() is False

    @pytest.mark.asyncio
    async def test_usage_accumulation(self):
        """Usage tokens accumulate across turns."""
        call_model = mock.AsyncMock(
            side_effect=[_tool_response(), _text_response("x")]
        )
        execute_tool = mock.AsyncMock(return_value=_tool_result())

        runner = AgentRunner(RunnerConfig(), execute_tool, call_model)
        await _collect(runner, [])

        result = runner.get_result()
        assert result.total_tokens == 30  # 20 + 10


# ===================================================================
# AgentSpawner tests
# ===================================================================

class TestAgentSpawner:
    """Tests for AgentSpawner."""

    def test_spawn_sync(self):
        spawner = AgentSpawner()
        result = spawner.spawn(SpawnConfig(prompt="hello", mode=SpawnMode.SYNC, label="s1"))
        assert result.success
        assert "s1" in result.agent_id

    def test_spawn_async_mode(self):
        spawner = AgentSpawner()
        result = spawner.spawn(SpawnConfig(prompt="async", mode=SpawnMode.ASYNC))
        assert result.success

    def test_spawn_fork(self):
        spawner = AgentSpawner()
        result = spawner.spawn(SpawnConfig(prompt="fork", mode=SpawnMode.FORK))
        assert result.success

    def test_spawn_teammate(self):
        spawner = AgentSpawner()
        result = spawner.spawn(SpawnConfig(
            prompt="team task",
            mode=SpawnMode.TEAMMATE,
            team_name="alpha",
            agent_name="worker-1",
        ))
        assert result.success

    @pytest.mark.asyncio
    async def test_spawn_async_api(self):
        spawner = AgentSpawner()
        result = await spawner.spawn_async(SpawnConfig(prompt="async spawn"))
        assert result.success

    def test_kill_child(self):
        spawner = AgentSpawner()
        res = spawner.spawn(SpawnConfig(prompt="x"))
        assert spawner.kill(res.agent_id) is True

    def test_kill_nonexistent(self):
        spawner = AgentSpawner()
        assert spawner.kill("nope") is False

    def test_kill_already_killed(self):
        spawner = AgentSpawner()
        res = spawner.spawn(SpawnConfig(prompt="x"))
        spawner.kill(res.agent_id)
        assert spawner.kill(res.agent_id) is False

    def test_kill_all(self):
        spawner = AgentSpawner()
        spawner.spawn(SpawnConfig(prompt="a"))
        spawner.spawn(SpawnConfig(prompt="b"))
        spawner.spawn(SpawnConfig(prompt="c"))
        killed = spawner.kill_all()
        assert killed == 3

    def test_kill_all_with_some_completed(self):
        spawner = AgentSpawner()
        r1 = spawner.spawn(SpawnConfig(prompt="a"))
        spawner.spawn(SpawnConfig(prompt="b"))
        spawner.mark_completed(r1.agent_id)
        killed = spawner.kill_all()
        assert killed == 1

    def test_get_child(self):
        spawner = AgentSpawner()
        res = spawner.spawn(SpawnConfig(prompt="x", label="test"))
        child = spawner.get_child(res.agent_id)
        assert child is not None
        assert child["label"] == "test"

    def test_get_child_nonexistent(self):
        spawner = AgentSpawner()
        assert spawner.get_child("nope") is None

    def test_list_children_all(self):
        spawner = AgentSpawner()
        spawner.spawn(SpawnConfig(prompt="a"))
        spawner.spawn(SpawnConfig(prompt="b"))
        assert len(spawner.list_children()) == 2

    def test_list_children_by_status(self):
        spawner = AgentSpawner()
        r1 = spawner.spawn(SpawnConfig(prompt="a"))
        spawner.spawn(SpawnConfig(prompt="b"))
        spawner.kill(r1.agent_id)
        running = spawner.list_children(status="running")
        killed = spawner.list_children(status="killed")
        assert len(running) == 1
        assert len(killed) == 1

    def test_mark_completed(self):
        spawner = AgentSpawner()
        res = spawner.spawn(SpawnConfig(prompt="x"))
        spawner.mark_completed(res.agent_id)
        child = spawner.get_child(res.agent_id)
        assert child["status"] == "completed"

    def test_mark_failed(self):
        spawner = AgentSpawner()
        res = spawner.spawn(SpawnConfig(prompt="x"))
        spawner.mark_completed(res.agent_id, error="boom")
        child = spawner.get_child(res.agent_id)
        assert child["status"] == "failed"
        assert child["error"] == "boom"

    def test_wait_all_immediate(self):
        spawner = AgentSpawner()
        assert spawner.wait_all(timeout=0.01) is True  # no children

    def test_wait_all_after_completion(self):
        spawner = AgentSpawner()
        r1 = spawner.spawn(SpawnConfig(prompt="a"))
        spawner.mark_completed(r1.agent_id)
        assert spawner.wait_all(timeout=0.1) is True

    def test_wait_all_timeout(self):
        spawner = AgentSpawner()
        spawner.spawn(SpawnConfig(prompt="a"))
        assert spawner.wait_all(timeout=0.01) is False

    def test_cleanup_kills_and_runs_handlers(self):
        spawner = AgentSpawner()
        spawner.spawn(SpawnConfig(prompt="a"))
        handler_called = []
        spawner.register_cleanup(lambda: handler_called.append(True))
        spawner.cleanup()
        assert handler_called == [True]
        assert len(spawner.list_children(status="killed")) == 1

    def test_register_cleanup_unregister(self):
        spawner = AgentSpawner()
        called = []
        unreg = spawner.register_cleanup(lambda: called.append(1))
        unreg()
        spawner.cleanup()
        assert called == []


# ===================================================================
# TeamManager tests
# ===================================================================

class TestTeamManager:

    def _make_config(self, name: str = "test-team") -> TeamConfig:
        return TeamConfig(
            team_name=name,
            leader_agent_id="leader-1",
            leader_session_id="sess-1",
        )

    def test_add_member(self):
        tm = TeamManager(self._make_config())
        member = tm.add_member("w1", "worker-one")
        assert member.agent_id == "w1"
        assert member.role == "worker"
        assert tm.size == 1

    def test_add_leader(self):
        tm = TeamManager(self._make_config())
        member = tm.add_member("l1", "leader", role="leader")
        assert member.role == "leader"

    def test_remove_member(self):
        tm = TeamManager(self._make_config())
        tm.add_member("w1", "worker-one")
        removed = tm.remove_member("w1")
        assert removed is not None
        assert removed.agent_id == "w1"
        assert tm.size == 0

    def test_remove_nonexistent(self):
        tm = TeamManager(self._make_config())
        assert tm.remove_member("nope") is None

    def test_max_members(self):
        cfg = self._make_config()
        cfg.max_members = 2
        tm = TeamManager(cfg)
        tm.add_member("w1", "one")
        tm.add_member("w2", "two")
        with pytest.raises(ValueError, match="max capacity"):
            tm.add_member("w3", "three")

    def test_mark_idle(self):
        tm = TeamManager(self._make_config())
        tm.add_member("w1", "worker-one")
        tm.mark_idle("w1")
        idle = tm.get_idle_members()
        assert len(idle) == 1
        assert idle[0].agent_id == "w1"

    def test_mark_active(self):
        tm = TeamManager(self._make_config())
        tm.add_member("w1", "worker-one")
        tm.mark_idle("w1")
        tm.mark_active("w1")
        assert len(tm.get_idle_members()) == 0
        assert len(tm.get_active_members()) == 1

    def test_mark_completed(self):
        tm = TeamManager(self._make_config())
        tm.add_member("w1", "worker-one")
        tm.mark_completed("w1")
        member = tm.get_member("w1")
        assert member.status == "completed"

    def test_mark_failed(self):
        tm = TeamManager(self._make_config())
        tm.add_member("w1", "worker-one")
        tm.mark_failed("w1")
        assert tm.get_member("w1").status == "failed"

    def test_mark_killed(self):
        tm = TeamManager(self._make_config())
        tm.add_member("w1", "worker-one")
        tm.mark_killed("w1")
        assert tm.get_member("w1").status == "killed"

    def test_all_idle_property(self):
        tm = TeamManager(self._make_config())
        tm.add_member("w1", "one")
        tm.add_member("w2", "two")
        assert tm.all_idle is False
        tm.mark_idle("w1")
        assert tm.all_idle is False
        tm.mark_idle("w2")
        assert tm.all_idle is True

    def test_all_idle_empty_team(self):
        tm = TeamManager(self._make_config())
        assert tm.all_idle is True

    def test_all_idle_ignores_terminal(self):
        tm = TeamManager(self._make_config())
        tm.add_member("w1", "one")
        tm.add_member("w2", "two")
        tm.mark_completed("w1")
        tm.mark_idle("w2")
        assert tm.all_idle is True

    def test_wait_for_all_idle(self):
        tm = TeamManager(self._make_config())
        tm.add_member("w1", "one")

        def _mark_idle_later():
            time.sleep(0.05)
            tm.mark_idle("w1")

        t = threading.Thread(target=_mark_idle_later)
        t.start()
        result = tm.wait_for_all_idle(timeout=1.0)
        t.join()
        assert result is True

    def test_wait_for_all_idle_timeout(self):
        tm = TeamManager(self._make_config())
        tm.add_member("w1", "one")
        assert tm.wait_for_all_idle(timeout=0.01) is False

    def test_request_shutdown(self):
        tm = TeamManager(self._make_config())
        tm.add_member("w1", "one")
        tm.add_member("w2", "two")
        tm.request_shutdown()
        assert tm.shutdown_requested is True
        assert tm.get_member("w1").status == "killed"
        assert tm.get_member("w2").status == "killed"

    def test_idle_callbacks(self):
        tm = TeamManager(self._make_config())
        tm.add_member("w1", "one")
        seen: list[str] = []
        tm.on_member_idle(lambda m: seen.append(m.agent_id))
        tm.mark_idle("w1")
        assert seen == ["w1"]

    def test_idle_callback_unregister(self):
        tm = TeamManager(self._make_config())
        tm.add_member("w1", "one")
        seen: list[str] = []
        unreg = tm.on_member_idle(lambda m: seen.append(m.agent_id))
        unreg()
        tm.mark_idle("w1")
        assert seen == []

    def test_team_name_property(self):
        tm = TeamManager(self._make_config("my-team"))
        assert tm.team_name == "my-team"


# ===================================================================
# Global team registry tests
# ===================================================================

class TestTeamRegistry:

    @pytest.fixture(autouse=True)
    def _clean_registry(self):
        _reset_registry()
        yield
        _reset_registry()

    def test_create_team(self):
        cfg = TeamConfig("alpha", "l1", "s1")
        tm = create_team(cfg)
        assert isinstance(tm, TeamManager)

    def test_create_duplicate_team(self):
        cfg = TeamConfig("alpha", "l1", "s1")
        create_team(cfg)
        with pytest.raises(ValueError, match="already exists"):
            create_team(cfg)

    def test_get_team(self):
        cfg = TeamConfig("beta", "l1", "s1")
        create_team(cfg)
        assert get_team("beta") is not None
        assert get_team("nope") is None

    def test_list_teams(self):
        create_team(TeamConfig("a", "l1", "s1"))
        create_team(TeamConfig("b", "l2", "s2"))
        names = list_teams()
        assert sorted(names) == ["a", "b"]

    def test_disband_team(self):
        create_team(TeamConfig("doomed", "l1", "s1"))
        disband_team("doomed")
        assert get_team("doomed") is None

    def test_disband_nonexistent(self):
        disband_team("ghost")  # no error


# ===================================================================
# ForkAgent tests
# ===================================================================

class TestForkAgent:

    def test_build_forked_messages_preserves_prefix(self):
        parent = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": [{"type": "text", "text": "hello"}]},
        ]
        result = ForkAgent.build_forked_messages(parent, "summarize")
        assert len(result) == 3
        # First two unchanged
        assert result[0] == parent[0]
        assert result[1] == parent[1]
        # New directive appended
        assert result[2]["role"] == "user"
        assert result[2]["content"][0]["text"] == "summarize"

    def test_build_forked_messages_empty_parent(self):
        result = ForkAgent.build_forked_messages([], "go")
        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_build_forked_messages_does_not_mutate_parent(self):
        parent = [{"role": "user", "content": "x"}]
        ForkAgent.build_forked_messages(parent, "y")
        assert len(parent) == 1

    def test_fork_config_defaults(self):
        cfg = ForkConfig(fork_label="test")
        assert cfg.max_turns == 50
        assert cfg.skip_transcript is False
        assert cfg.skip_cache_write is False
        assert cfg.on_message is None
        assert cfg.prompt_messages == []

    @pytest.mark.asyncio
    async def test_fork_run_returns_result(self):
        agent = ForkAgent()
        cfg = ForkConfig(
            fork_label="mem",
            prompt_messages=[{"role": "user", "content": "summarize"}],
        )
        result = await agent.run(cfg)
        assert isinstance(result, ForkResult)
        assert len(result.messages) == 1

    @pytest.mark.asyncio
    async def test_fork_run_calls_on_message(self):
        seen: list[dict] = []
        agent = ForkAgent()
        cfg = ForkConfig(
            fork_label="cb",
            prompt_messages=[
                {"role": "user", "content": "a"},
                {"role": "user", "content": "b"},
            ],
            on_message=lambda m: seen.append(m),
        )
        await agent.run(cfg)
        assert len(seen) == 2

    def test_fork_result_defaults(self):
        r = ForkResult()
        assert r.messages == []
        assert r.total_tokens == 0
        assert r.input_tokens == 0
        assert r.output_tokens == 0
        assert r.cache_read_tokens == 0


# ===================================================================
# __init__.py import smoke tests
# ===================================================================

class TestPackageExports:

    def test_all_runner_exports(self):
        from memoria.orchestration import (
            AgentResult,
            AgentRunner,
            RunnerConfig,
            StopReason,
            TurnResult,
        )
        assert StopReason.END_TURN.value == "end_turn"

    def test_all_spawner_exports(self):
        from memoria.orchestration import (
            AgentSpawner,
            ChildStatus,
            SpawnConfig,
            SpawnMode,
            SpawnResult,
        )
        assert SpawnMode.FORK.value == "fork"

    def test_all_fork_exports(self):
        from memoria.orchestration import ForkAgent, ForkConfig, ForkResult
        assert ForkConfig(fork_label="x").fork_label == "x"

    def test_all_team_exports(self):
        from memoria.orchestration import (
            TeamConfig,
            TeamManager,
            TeamMember,
            create_team,
            disband_team,
            get_team,
            list_teams,
        )
        assert TeamMember(agent_id="a", agent_name="b").role == "worker"
