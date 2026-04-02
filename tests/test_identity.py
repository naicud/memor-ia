"""Tests for the Agent Identity & Context Layer (Layer 2)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from memoria.identity.agent_id import (
    AGENT_ID_PATTERN,
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
from memoria.identity.context import (
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
from memoria.identity.factory import (
    SubagentOverrides,
    create_fork_context,
    create_subagent_context,
    create_teammate_context,
)

# ===================================================================
# identity.py — create_agent_id
# ===================================================================


class TestCreateAgentId:
    def test_no_label_matches_pattern(self):
        aid = create_agent_id()
        assert AGENT_ID_PATTERN.match(aid)

    def test_no_label_length(self):
        aid = create_agent_id()
        # 'a' + 16 hex chars = 17 chars
        assert len(aid) == 17

    def test_with_label_format(self):
        aid = create_agent_id("worker")
        assert aid.startswith("a-worker-")
        assert AGENT_ID_PATTERN.match(aid)

    def test_label_special_chars_sanitised(self):
        aid = create_agent_id("hello world!")
        assert " " not in aid
        assert "!" not in aid
        assert AGENT_ID_PATTERN.match(aid)

    def test_uniqueness(self):
        ids = {create_agent_id() for _ in range(100)}
        assert len(ids) == 100

    def test_is_valid_agent_id_hex(self):
        aid = create_agent_id()
        assert is_valid_agent_id(aid)

    def test_is_valid_agent_id_labelled(self):
        aid = create_agent_id("test")
        assert is_valid_agent_id(aid)

    def test_invalid_agent_id(self):
        assert not is_valid_agent_id("not-an-id")
        assert not is_valid_agent_id("")


# ===================================================================
# identity.py — create_session_id
# ===================================================================


class TestCreateSessionId:
    def test_length(self):
        sid = create_session_id()
        assert len(sid) == 32

    def test_hex(self):
        sid = create_session_id()
        int(sid, 16)  # Should not raise

    def test_uniqueness(self):
        ids = {create_session_id() for _ in range(100)}
        assert len(ids) == 100


# ===================================================================
# identity.py — format / parse agent id round-trip
# ===================================================================


class TestTeammateIdRoundTrip:
    def test_format(self):
        assert format_agent_id("researcher", "my-team") == "researcher@my-team"

    def test_parse(self):
        result = parse_agent_id("researcher@my-team")
        assert result == ("researcher", "my-team")

    def test_parse_invalid(self):
        assert parse_agent_id("nope") is None

    def test_round_trip(self):
        formatted = format_agent_id("coder", "alpha")
        parsed = parse_agent_id(formatted)
        assert parsed == ("coder", "alpha")

    def test_is_valid_teammate_id(self):
        assert is_valid_agent_id("researcher@my-team")


# ===================================================================
# identity.py — format_request_id
# ===================================================================


class TestFormatRequestId:
    def test_format(self):
        aid = create_agent_id("x")
        rid = format_request_id("tool", aid)
        assert rid.startswith("tool-")
        assert rid.endswith(f"@{aid}")


# ===================================================================
# identity.py — TeammateIdentity
# ===================================================================


class TestTeammateIdentity:
    def test_creation(self):
        ti = TeammateIdentity(
            agent_id="r@t", agent_name="r", team_name="t"
        )
        assert ti.agent_name == "r"

    def test_frozen(self):
        ti = TeammateIdentity(agent_id="r@t", agent_name="r", team_name="t")
        with pytest.raises(FrozenInstanceError):
            ti.agent_name = "changed"  # type: ignore[misc]

    def test_defaults(self):
        ti = TeammateIdentity(agent_id="r@t", agent_name="r", team_name="t")
        assert ti.color is None
        assert ti.plan_mode_required is False
        assert ti.parent_session_id == ""


# ===================================================================
# identity.py — AgentProgress
# ===================================================================


class TestAgentProgress:
    def test_total_tokens(self):
        p = AgentProgress(input_tokens=10, output_tokens=20, cache_read_tokens=5, cache_creation_tokens=3)
        assert p.total_tokens == 38

    def test_add_activity_within_limit(self):
        p = AgentProgress()
        for i in range(3):
            p.add_activity(f"act-{i}")
        assert len(p.recent_activities) == 3

    def test_sliding_window(self):
        p = AgentProgress()
        for i in range(10):
            p.add_activity(f"act-{i}")
        assert len(p.recent_activities) == 5
        assert p.recent_activities[0] == "act-5"
        assert p.recent_activities[-1] == "act-9"

    def test_tool_use_count(self):
        p = AgentProgress()
        p.tool_use_count += 3
        assert p.tool_use_count == 3


# ===================================================================
# agent_context.py — contextvars isolation
# ===================================================================


class TestContextVars:
    def test_default_is_none(self):
        assert get_current_agent() is None
        assert get_current_session() is None

    def test_set_get_agent(self):
        ctx = AgentContext(agent_id=AgentId("a" + "0" * 16), session_id=SessionId("s" * 32))
        set_current_agent(ctx)
        assert get_current_agent() is ctx
        set_current_agent(None)
        # Clean reset
        from memoria.identity.context import _current_agent
        _current_agent.set(None)

    def test_set_get_session(self):
        sid = SessionId("f" * 32)
        set_current_session(sid)
        assert get_current_session() == sid
        from memoria.identity.context import _current_session
        _current_session.set(None)

    def test_token_reset(self):
        ctx = AgentContext(agent_id=AgentId("a" + "0" * 16), session_id=SessionId("s" * 32))
        token = set_current_agent(ctx)
        assert get_current_agent() is ctx
        from memoria.identity.context import _current_agent
        _current_agent.reset(token)
        assert get_current_agent() is None


# ===================================================================
# agent_context.py — run_in_agent_context
# ===================================================================


class TestRunInAgentContext:
    def test_sets_and_resets(self):
        ctx = AgentContext(agent_id=create_agent_id(), session_id=create_session_id())
        captured = []

        def fn():
            captured.append(get_current_agent())

        run_in_agent_context(ctx, fn)
        assert captured[0] is ctx
        assert get_current_agent() is None

    def test_nesting(self):
        outer = AgentContext(agent_id=create_agent_id("outer"), session_id=create_session_id(), depth=0)
        inner = AgentContext(agent_id=create_agent_id("inner"), session_id=outer.session_id, depth=1)
        results: list[str] = []

        def inner_fn():
            results.append(get_current_agent().agent_id)  # type: ignore[union-attr]

        def outer_fn():
            results.append(get_current_agent().agent_id)  # type: ignore[union-attr]
            run_in_agent_context(inner, inner_fn)
            results.append(get_current_agent().agent_id)  # type: ignore[union-attr]

        run_in_agent_context(outer, outer_fn)
        assert results[0] == outer.agent_id
        assert results[1] == inner.agent_id
        assert results[2] == outer.agent_id  # restored

    def test_exception_still_resets(self):
        ctx = AgentContext(agent_id=create_agent_id(), session_id=create_session_id())

        def bad():
            raise ValueError("boom")

        with pytest.raises(ValueError):
            run_in_agent_context(ctx, bad)
        assert get_current_agent() is None

    @pytest.mark.asyncio
    async def test_async_version(self):
        ctx = AgentContext(agent_id=create_agent_id(), session_id=create_session_id())

        async def afn():
            return get_current_agent()

        result = await run_in_agent_context_async(ctx, afn)
        assert result is ctx
        assert get_current_agent() is None


# ===================================================================
# agent_context.py — is_subagent / is_teammate
# ===================================================================


class TestQueryHelpers:
    def test_is_subagent_false_when_none(self):
        assert not is_subagent()

    def test_is_subagent_false_at_root(self):
        ctx = AgentContext(agent_id=create_agent_id(), session_id=create_session_id(), depth=0)

        def check():
            return is_subagent()

        assert not run_in_agent_context(ctx, check)

    def test_is_subagent_true_at_depth_1(self):
        ctx = AgentContext(agent_id=create_agent_id(), session_id=create_session_id(), depth=1)

        def check():
            return is_subagent()

        assert run_in_agent_context(ctx, check)

    def test_is_teammate_false_when_no_identity(self):
        ctx = AgentContext(agent_id=create_agent_id(), session_id=create_session_id())

        def check():
            return is_teammate()

        assert not run_in_agent_context(ctx, check)

    def test_is_teammate_true_with_identity(self):
        ti = TeammateIdentity(agent_id="r@t", agent_name="r", team_name="t")
        ctx = AgentContext(
            agent_id=AgentId("r@t"),
            session_id=create_session_id(),
            teammate_identity=ti,
        )

        def check():
            return is_teammate()

        assert run_in_agent_context(ctx, check)


# ===================================================================
# context_factory.py — create_subagent_context
# ===================================================================


class TestCreateSubagentContext:
    def _parent(self) -> AgentContext:
        return AgentContext(
            agent_id=create_agent_id("parent"),
            session_id=create_session_id(),
            depth=0,
            permission_mode="default",
        )

    def test_depth_incremented(self):
        child = create_subagent_context(self._parent())
        assert child.depth == 1

    def test_session_inherited(self):
        parent = self._parent()
        child = create_subagent_context(parent)
        assert child.session_id == parent.session_id

    def test_parent_agent_id_set(self):
        parent = self._parent()
        child = create_subagent_context(parent)
        assert child.parent_agent_id == parent.agent_id

    def test_fresh_abort(self):
        parent = self._parent()
        child = create_subagent_context(parent)
        assert child.abort_event is not parent.abort_event

    def test_shared_abort(self):
        parent = self._parent()
        child = create_subagent_context(parent, overrides=SubagentOverrides(share_abort_controller=True))
        assert child.abort_event is parent.abort_event

    def test_fresh_progress(self):
        parent = self._parent()
        parent.progress.tool_use_count = 42
        child = create_subagent_context(parent)
        assert child.progress.tool_use_count == 0

    def test_fresh_messages(self):
        parent = self._parent()
        parent.pending_messages.append("hello")
        child = create_subagent_context(parent)
        assert child.pending_messages == []

    def test_permission_inherited(self):
        parent = self._parent()
        parent.permission_mode = "plan"
        child = create_subagent_context(parent)
        assert child.permission_mode == "plan"

    def test_permission_override(self):
        parent = self._parent()
        child = create_subagent_context(parent, overrides=SubagentOverrides(permission_mode="bubble"))
        assert child.permission_mode == "bubble"


# ===================================================================
# context_factory.py — create_teammate_context
# ===================================================================


class TestCreateTeammateContext:
    def test_independent_abort(self):
        parent = AgentContext(agent_id=create_agent_id(), session_id=create_session_id())
        ti = TeammateIdentity(agent_id="r@t", agent_name="r", team_name="t")
        child = create_teammate_context(parent, ti)
        assert child.abort_event is not parent.abort_event

    def test_identity_set(self):
        parent = AgentContext(agent_id=create_agent_id(), session_id=create_session_id())
        ti = TeammateIdentity(agent_id="r@t", agent_name="r", team_name="t")
        child = create_teammate_context(parent, ti)
        assert child.teammate_identity is ti

    def test_never_shares_app_state(self):
        parent = AgentContext(agent_id=create_agent_id(), session_id=create_session_id(), share_app_state=True)
        ti = TeammateIdentity(agent_id="r@t", agent_name="r", team_name="t")
        child = create_teammate_context(parent, ti)
        assert child.share_app_state is False

    def test_own_permission_mode(self):
        parent = AgentContext(agent_id=create_agent_id(), session_id=create_session_id(), permission_mode="plan")
        ti = TeammateIdentity(agent_id="r@t", agent_name="r", team_name="t")
        child = create_teammate_context(parent, ti, permission_mode="bubble")
        assert child.permission_mode == "bubble"


# ===================================================================
# context_factory.py — create_fork_context
# ===================================================================


class TestCreateForkContext:
    def test_same_depth(self):
        parent = AgentContext(agent_id=create_agent_id(), session_id=create_session_id(), depth=2)
        fork = create_fork_context(parent, "fork-1")
        assert fork.depth == 2

    def test_independent_abort(self):
        parent = AgentContext(agent_id=create_agent_id(), session_id=create_session_id())
        fork = create_fork_context(parent, "fork-1")
        assert fork.abort_event is not parent.abort_event

    def test_bubble_permission(self):
        parent = AgentContext(agent_id=create_agent_id(), session_id=create_session_id())
        fork = create_fork_context(parent, "fork-1")
        assert fork.permission_mode == "bubble"

    def test_session_inherited(self):
        parent = AgentContext(agent_id=create_agent_id(), session_id=create_session_id())
        fork = create_fork_context(parent, "fork-1")
        assert fork.session_id == parent.session_id


# ===================================================================
# context_factory.py — SubagentOverrides defaults
# ===================================================================


class TestSubagentOverrides:
    def test_defaults(self):
        ovr = SubagentOverrides()
        assert ovr.agent_id is None
        assert ovr.share_app_state is False
        assert ovr.share_abort_controller is False
        assert ovr.permission_mode is None
        assert ovr.can_use_tool is None
        assert ovr.is_background is True
