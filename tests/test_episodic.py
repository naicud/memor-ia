"""Comprehensive tests for the MEMORIA episodic memory layer."""

from __future__ import annotations

import time

import pytest

from memoria.episodic import EpisodicMemory, Episode, EpisodicEvent, EventType


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture()
def mem() -> EpisodicMemory:
    """Fresh episodic memory store."""
    return EpisodicMemory()


@pytest.fixture()
def active_mem(mem: EpisodicMemory) -> EpisodicMemory:
    """Memory with one active episode and a few events."""
    mem.start_episode(agent_id="a1", session_id="s1", title="test episode")
    mem.record_event("hello", event_type=EventType.INTERACTION, importance=0.3)
    mem.record_event("observed X", event_type=EventType.OBSERVATION, importance=0.9)
    mem.record_event("decided Y", event_type=EventType.DECISION, importance=0.5)
    return mem


# ═══════════════════════════════════════════════════════════════════
# EventType enum
# ═══════════════════════════════════════════════════════════════════


class TestEventType:
    def test_values(self) -> None:
        assert EventType.INTERACTION.value == "interaction"
        assert EventType.TOOL_USE.value == "tool_use"

    def test_str_enum(self) -> None:
        assert str(EventType.DECISION) == "EventType.DECISION"
        assert EventType("error") is EventType.ERROR


# ═══════════════════════════════════════════════════════════════════
# Episode dataclass
# ═══════════════════════════════════════════════════════════════════


class TestEpisode:
    def test_is_active_when_not_ended(self) -> None:
        ep = Episode(episode_id="ep1")
        assert ep.is_active()

    def test_is_not_active_when_ended(self) -> None:
        ep = Episode(episode_id="ep1", ended_at=time.time())
        assert not ep.is_active()

    def test_event_count(self) -> None:
        ep = Episode(episode_id="ep1")
        assert ep.event_count == 0
        ep.events.append(
            EpisodicEvent(event_id="e1", event_type=EventType.INSIGHT, content="x")
        )
        assert ep.event_count == 1

    def test_duration_s_active(self) -> None:
        ep = Episode(episode_id="ep1", started_at=time.time() - 10)
        assert ep.duration_s >= 10

    def test_duration_s_ended(self) -> None:
        t = time.time()
        ep = Episode(episode_id="ep1", started_at=t, ended_at=t + 5)
        assert ep.duration_s == pytest.approx(5.0)


# ═══════════════════════════════════════════════════════════════════
# Episode lifecycle
# ═══════════════════════════════════════════════════════════════════


class TestEpisodeLifecycle:
    def test_start_episode(self, mem: EpisodicMemory) -> None:
        ep = mem.start_episode(agent_id="a1", title="first")
        assert ep.title == "first"
        assert ep.agent_id == "a1"
        assert ep.is_active()
        assert mem.get_active_episode() is ep

    def test_end_episode(self, mem: EpisodicMemory) -> None:
        ep = mem.start_episode()
        ended = mem.end_episode(summary="done", outcome="success")
        assert ended is not None
        assert not ended.is_active()
        assert ended.summary == "done"
        assert ended.outcome == "success"
        assert mem.get_active_episode() is None

    def test_start_auto_closes_previous(self, mem: EpisodicMemory) -> None:
        ep1 = mem.start_episode(title="first")
        ep2 = mem.start_episode(title="second")
        assert not ep1.is_active()
        assert ep2.is_active()
        assert mem.get_active_episode() is ep2

    def test_end_specific_episode(self, mem: EpisodicMemory) -> None:
        ep1 = mem.start_episode(title="one")
        eid = ep1.episode_id
        mem.end_episode(episode_id=eid)
        assert not ep1.is_active()
        assert mem.get_active_episode() is None

    def test_end_nonexistent_returns_none(self, mem: EpisodicMemory) -> None:
        assert mem.end_episode(episode_id="nope") is None

    def test_get_active_episode_none(self, mem: EpisodicMemory) -> None:
        assert mem.get_active_episode() is None


# ═══════════════════════════════════════════════════════════════════
# Event recording
# ═══════════════════════════════════════════════════════════════════


class TestEventRecording:
    def test_record_event_basic(self, mem: EpisodicMemory) -> None:
        mem.start_episode()
        ev = mem.record_event("hi", event_type=EventType.INTERACTION)
        assert ev.content == "hi"
        assert ev.event_type == EventType.INTERACTION

    def test_record_auto_creates_episode(self, mem: EpisodicMemory) -> None:
        ev = mem.record_event("auto")
        assert mem.get_active_episode() is not None
        assert ev in mem.get_active_episode().events

    def test_record_into_specific_episode(self, mem: EpisodicMemory) -> None:
        ep = mem.start_episode(title="target")
        mem.end_episode()
        ev = mem.record_event("late", episode_id=ep.episode_id)
        assert ev in ep.events

    def test_record_interaction_shorthand(self, mem: EpisodicMemory) -> None:
        mem.start_episode()
        ev = mem.record_interaction("hello", role="assistant")
        assert ev.event_type == EventType.INTERACTION
        assert ev.metadata["role"] == "assistant"

    def test_record_tool_use_shorthand(self, mem: EpisodicMemory) -> None:
        mem.start_episode()
        ev = mem.record_tool_use("grep", "pattern", "3 matches")
        assert ev.event_type == EventType.TOOL_USE
        assert ev.metadata["tool"] == "grep"
        assert "grep" in ev.content

    def test_record_decision_shorthand(self, mem: EpisodicMemory) -> None:
        mem.start_episode()
        ev = mem.record_decision("chose A", reasoning="faster")
        assert ev.event_type == EventType.DECISION
        assert ev.metadata["reasoning"] == "faster"

    def test_event_counter_increments(self, mem: EpisodicMemory) -> None:
        mem.start_episode()
        for i in range(5):
            mem.record_event(f"event {i}")
        assert mem._event_counter == 5

    def test_max_events_per_episode(self) -> None:
        mem = EpisodicMemory(max_events_per_episode=3)
        mem.start_episode()
        for i in range(5):
            mem.record_event(f"ev{i}")
        ep = mem.get_active_episode()
        assert ep is not None
        assert ep.event_count == 3

    def test_max_events_returns_dropped_metadata(self) -> None:
        """When max_events is reached, returned event has _dropped metadata."""
        mem = EpisodicMemory(max_events_per_episode=2)
        mem.start_episode()
        mem.record_event("ev0")
        mem.record_event("ev1")
        dropped = mem.record_event("ev2")
        assert dropped.metadata.get("_dropped") is True
        assert "max_events" in dropped.metadata.get("_reason", "")
        assert dropped.event_id  # valid ID even though dropped
        assert dropped.content == "ev2"
        ep = mem.get_active_episode()
        assert ep is not None
        assert ep.event_count == 2  # dropped event NOT stored


# ═══════════════════════════════════════════════════════════════════
# Timeline queries
# ═══════════════════════════════════════════════════════════════════


class TestTimelineQueries:
    def test_query_all(self, active_mem: EpisodicMemory) -> None:
        events = active_mem.query_timeline()
        assert len(events) == 3

    def test_query_by_type(self, active_mem: EpisodicMemory) -> None:
        events = active_mem.query_timeline(event_types=[EventType.OBSERVATION])
        assert len(events) == 1
        assert events[0].content == "observed X"

    def test_query_by_importance(self, active_mem: EpisodicMemory) -> None:
        events = active_mem.query_timeline(min_importance=0.8)
        assert len(events) == 1
        assert events[0].importance == 0.9

    def test_query_time_range(self, mem: EpisodicMemory) -> None:
        t0 = time.time()
        mem.start_episode()
        ev1 = mem.record_event("early")
        ev1.timestamp = t0 - 100
        ev2 = mem.record_event("middle")
        ev2.timestamp = t0
        ev3 = mem.record_event("late")
        ev3.timestamp = t0 + 100

        events = mem.query_timeline(start_time=t0 - 50, end_time=t0 + 50)
        assert len(events) == 1
        assert events[0].content == "middle"

    def test_query_limit(self, mem: EpisodicMemory) -> None:
        mem.start_episode()
        for i in range(20):
            mem.record_event(f"ev{i}")
        events = mem.query_timeline(limit=5)
        assert len(events) == 5

    def test_get_recent_events(self, active_mem: EpisodicMemory) -> None:
        events = active_mem.get_recent_events(n=2)
        assert len(events) == 2
        # Most recent first
        assert events[0].timestamp >= events[1].timestamp

    def test_get_recent_events_with_type(self, active_mem: EpisodicMemory) -> None:
        events = active_mem.get_recent_events(
            n=10, event_types=[EventType.DECISION]
        )
        assert len(events) == 1


# ═══════════════════════════════════════════════════════════════════
# Episode search
# ═══════════════════════════════════════════════════════════════════


class TestEpisodeSearch:
    def test_search_by_title(self, mem: EpisodicMemory) -> None:
        mem.start_episode(title="deploy pipeline")
        mem.end_episode()
        mem.start_episode(title="debug auth")
        mem.end_episode()

        results = mem.search_episodes("deploy")
        assert len(results) == 1
        assert results[0].title == "deploy pipeline"

    def test_search_by_event_content(self, mem: EpisodicMemory) -> None:
        mem.start_episode(title="session")
        mem.record_event("kubernetes pod restarted")
        mem.end_episode()

        results = mem.search_episodes("kubernetes")
        assert len(results) == 1

    def test_search_empty_query(self, mem: EpisodicMemory) -> None:
        mem.start_episode()
        mem.end_episode()
        assert mem.search_episodes("") == []

    def test_search_no_match(self, mem: EpisodicMemory) -> None:
        mem.start_episode(title="abc")
        mem.end_episode()
        assert mem.search_episodes("zzz") == []

    def test_search_limit(self, mem: EpisodicMemory) -> None:
        for i in range(10):
            mem.start_episode(title=f"deploy {i}")
            mem.end_episode()
        results = mem.search_episodes("deploy", limit=3)
        assert len(results) == 3


# ═══════════════════════════════════════════════════════════════════
# Episode queries
# ═══════════════════════════════════════════════════════════════════


class TestEpisodeQueries:
    def test_get_episode(self, mem: EpisodicMemory) -> None:
        ep = mem.start_episode(title="x")
        assert mem.get_episode(ep.episode_id) is ep

    def test_get_episode_missing(self, mem: EpisodicMemory) -> None:
        assert mem.get_episode("nope") is None

    def test_list_episodes_order(self, mem: EpisodicMemory) -> None:
        ep1 = mem.start_episode(title="first")
        ep1.started_at = 100
        mem.end_episode()
        ep2 = mem.start_episode(title="second")
        ep2.started_at = 200

        eps = mem.list_episodes()
        assert eps[0].title == "second"
        assert eps[1].title == "first"

    def test_list_episodes_by_agent(self, mem: EpisodicMemory) -> None:
        mem.start_episode(agent_id="a1")
        mem.end_episode()
        mem.start_episode(agent_id="a2")
        mem.end_episode()

        eps = mem.list_episodes(agent_id="a1")
        assert len(eps) == 1
        assert eps[0].agent_id == "a1"

    def test_list_episodes_exclude_active(self, mem: EpisodicMemory) -> None:
        mem.start_episode(title="done")
        mem.end_episode()
        mem.start_episode(title="running")

        eps = mem.list_episodes(include_active=False)
        assert len(eps) == 1
        assert eps[0].title == "done"

    def test_get_episode_summary_generated(self, active_mem: EpisodicMemory) -> None:
        ep = active_mem.get_active_episode()
        assert ep is not None
        summary = active_mem.get_episode_summary(ep.episode_id)
        assert "Events: 3" in summary

    def test_get_episode_summary_explicit(self, mem: EpisodicMemory) -> None:
        ep = mem.start_episode()
        mem.end_episode(summary="custom summary")
        assert mem.get_episode_summary(ep.episode_id) == "custom summary"

    def test_get_episode_summary_missing(self, mem: EpisodicMemory) -> None:
        assert mem.get_episode_summary("nope") == ""


# ═══════════════════════════════════════════════════════════════════
# Statistics
# ═══════════════════════════════════════════════════════════════════


class TestStats:
    def test_empty_stats(self, mem: EpisodicMemory) -> None:
        s = mem.stats()
        assert s["total_episodes"] == 0
        assert s["total_events"] == 0
        assert s["active_episode"] is None

    def test_stats_with_data(self, active_mem: EpisodicMemory) -> None:
        s = active_mem.stats()
        assert s["total_episodes"] == 1
        assert s["total_events"] == 3
        assert s["active_episode"] is not None
        assert "interaction" in s["event_type_distribution"]
        assert "observation" in s["event_type_distribution"]

    def test_stats_outcome_tracking(self, mem: EpisodicMemory) -> None:
        mem.start_episode()
        mem.end_episode(outcome="success")
        mem.start_episode()
        mem.end_episode(outcome="failure")
        mem.start_episode()
        mem.end_episode(outcome="success")

        s = mem.stats()
        assert s["episodes_by_outcome"]["success"] == 2
        assert s["episodes_by_outcome"]["failure"] == 1


# ═══════════════════════════════════════════════════════════════════
# Episode compaction
# ═══════════════════════════════════════════════════════════════════


class TestCompaction:
    def test_compact_keeps_important(self, active_mem: EpisodicMemory) -> None:
        ep = active_mem.get_active_episode()
        assert ep is not None
        active_mem.compact_episode(ep.episode_id)
        # Only the event with importance > 0.7 survives (0.9)
        assert ep.event_count == 1
        assert ep.events[0].importance == 0.9

    def test_compact_generates_summary(self, active_mem: EpisodicMemory) -> None:
        ep = active_mem.get_active_episode()
        assert ep is not None
        active_mem.compact_episode(ep.episode_id)
        assert "Compacted events" in ep.summary
        assert "hello" in ep.summary
        assert "decided Y" in ep.summary

    def test_compact_nonexistent(self, mem: EpisodicMemory) -> None:
        assert mem.compact_episode("nope") is None

    def test_compact_decrements_counter(self, active_mem: EpisodicMemory) -> None:
        ep = active_mem.get_active_episode()
        assert ep is not None
        before = active_mem._event_counter
        active_mem.compact_episode(ep.episode_id)
        assert active_mem._event_counter == before - 2  # removed 2 events


# ═══════════════════════════════════════════════════════════════════
# Episode rotation
# ═══════════════════════════════════════════════════════════════════


class TestRotation:
    def test_rotation_removes_oldest(self) -> None:
        mem = EpisodicMemory(max_episodes=3)
        ids = []
        for i in range(5):
            ep = mem.start_episode(title=f"ep{i}")
            ep.started_at = float(i)
            mem.end_episode()
            ids.append(ep.episode_id)

        # Only the 3 most recently created should remain
        assert len(mem._episodes) == 3
        assert ids[0] not in mem._episodes
        assert ids[1] not in mem._episodes
        assert ids[4] in mem._episodes

    def test_rotation_preserves_active(self) -> None:
        mem = EpisodicMemory(max_episodes=2)
        ep1 = mem.start_episode(title="old")
        ep1.started_at = 1.0
        mem.end_episode()

        ep2 = mem.start_episode(title="current")
        ep2.started_at = 2.0
        # ep2 is active — should not be evicted

        ep3 = mem.start_episode(title="new")
        # starting ep3 closes ep2, but rotation only removes completed
        assert len(mem._episodes) == 2


# ═══════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_record_event_no_active_episode(self, mem: EpisodicMemory) -> None:
        ev = mem.record_event("orphan")
        assert mem.get_active_episode() is not None
        assert ev.content == "orphan"

    def test_empty_episode(self, mem: EpisodicMemory) -> None:
        ep = mem.start_episode()
        assert ep.event_count == 0
        mem.end_episode()
        assert not ep.is_active()

    def test_multiple_episode_cycles(self, mem: EpisodicMemory) -> None:
        for i in range(10):
            mem.start_episode(title=f"cycle-{i}")
            mem.record_event(f"event in cycle {i}")
            mem.end_episode()
        assert mem.stats()["total_episodes"] == 10
        assert mem.stats()["total_events"] == 10

    def test_end_already_ended(self, mem: EpisodicMemory) -> None:
        ep = mem.start_episode()
        mem.end_episode()
        result = mem.end_episode(episode_id=ep.episode_id)
        # Ending an already-ended episode still succeeds (updates timestamp)
        assert result is not None

    def test_query_timeline_empty(self, mem: EpisodicMemory) -> None:
        assert mem.query_timeline() == []

    def test_get_recent_events_empty(self, mem: EpisodicMemory) -> None:
        assert mem.get_recent_events() == []
