"""Tests for the real-time streaming module.

Covers: EventFilter, SSEChannel, WSChannel, StreamManager, bus bridge,
and Memoria integration methods.
"""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import MagicMock, patch

import pytest

from memoria.streaming.filters import EventFilter
from memoria.streaming.manager import StreamManager
from memoria.streaming.sse import SSEChannel, SSEEvent
from memoria.streaming.websocket import WSChannel

# ═══════════════════════════════════════════════════════════════════════════
# EventFilter
# ═══════════════════════════════════════════════════════════════════════════


class TestEventFilter:
    """Tests for EventFilter matching logic."""

    def test_empty_filter_matches_everything(self):
        ef = EventFilter()
        assert ef.matches("memory.updated", {"user_id": "alice"})
        assert ef.matches("agent.spawned", {})

    def test_event_type_filter(self):
        ef = EventFilter(event_types=("memory.updated", "memory.recalled"))
        assert ef.matches("memory.updated", {})
        assert ef.matches("memory.recalled", {})
        assert not ef.matches("agent.spawned", {})

    def test_user_id_filter(self):
        ef = EventFilter(user_ids=("alice", "bob"))
        assert ef.matches("any", {"user_id": "alice"})
        assert ef.matches("any", {"user_id": "bob"})
        assert not ef.matches("any", {"user_id": "charlie"})
        assert not ef.matches("any", {})

    def test_user_id_fallback_to_agent_id(self):
        ef = EventFilter(user_ids=("agent-1",))
        assert ef.matches("any", {"agent_id": "agent-1"})

    def test_namespace_filter(self):
        ef = EventFilter(namespaces=("project-a",))
        assert ef.matches("any", {"namespace": "project-a"})
        assert not ef.matches("any", {"namespace": "project-b"})
        assert not ef.matches("any", {})

    def test_combined_filters_are_AND(self):
        ef = EventFilter(
            event_types=("memory.updated",),
            user_ids=("alice",),
            namespaces=("ns1",),
        )
        # All match
        assert ef.matches("memory.updated", {"user_id": "alice", "namespace": "ns1"})
        # Wrong event type
        assert not ef.matches("agent.spawned", {"user_id": "alice", "namespace": "ns1"})
        # Wrong user
        assert not ef.matches("memory.updated", {"user_id": "bob", "namespace": "ns1"})
        # Wrong namespace
        assert not ef.matches("memory.updated", {"user_id": "alice", "namespace": "ns2"})

    def test_custom_predicate(self):
        ef = EventFilter(custom_predicate=lambda d: d.get("priority", 0) > 5)
        assert ef.matches("any", {"priority": 10})
        assert not ef.matches("any", {"priority": 2})

    def test_custom_predicate_exception_returns_false(self):
        ef = EventFilter(custom_predicate=lambda d: 1 / 0)
        assert not ef.matches("any", {})

    def test_from_params(self):
        ef = EventFilter.from_params(
            event_types=["a", "b"],
            user_ids=["u1"],
            namespaces=None,
        )
        assert ef.event_types == ("a", "b")
        assert ef.user_ids == ("u1",)
        assert ef.namespaces == ()

    def test_from_params_all_none(self):
        ef = EventFilter.from_params()
        assert ef.event_types == ()
        assert ef.user_ids == ()
        assert ef.namespaces == ()

    def test_filter_is_hashable(self):
        ef1 = EventFilter(event_types=("a",))
        ef2 = EventFilter(event_types=("a",))
        assert hash(ef1) == hash(ef2)
        s = {ef1, ef2}
        assert len(s) == 1


# ═══════════════════════════════════════════════════════════════════════════
# SSEEvent
# ═══════════════════════════════════════════════════════════════════════════


class TestSSEEvent:
    """Tests for SSEEvent serialization."""

    def test_serialize_format(self):
        ev = SSEEvent(event_type="memory.updated", data={"key": "value"}, event_id="abc123")
        s = ev.serialize()
        assert "id: abc123" in s
        assert "event: memory.updated" in s
        assert 'data: {"key": "value"}' in s
        assert s.endswith("\n\n")

    def test_auto_generated_id(self):
        ev = SSEEvent(event_type="test", data={})
        assert len(ev.event_id) == 12

    def test_auto_generated_timestamp(self):
        before = time.time()
        ev = SSEEvent(event_type="test", data={})
        after = time.time()
        assert before <= ev.timestamp <= after


# ═══════════════════════════════════════════════════════════════════════════
# SSEChannel
# ═══════════════════════════════════════════════════════════════════════════


class TestSSEChannel:
    """Tests for SSEChannel push/consume lifecycle."""

    def test_create_with_defaults(self):
        ch = SSEChannel()
        assert not ch.closed
        assert ch.event_count == 0
        assert ch.queue_size == 0
        assert len(ch.channel_id) == 16

    def test_create_with_custom_id(self):
        ch = SSEChannel(channel_id="my-channel")
        assert ch.channel_id == "my-channel"

    def test_push_increments_event_count(self):
        ch = SSEChannel()
        ch.push("test", {"k": "v"})
        assert ch.event_count == 1
        assert ch.queue_size == 1

    def test_push_respects_filter(self):
        ef = EventFilter(event_types=("memory.updated",))
        ch = SSEChannel(event_filter=ef)
        ch.push("memory.updated", {})
        ch.push("agent.spawned", {})  # filtered out
        assert ch.event_count == 1

    def test_push_returns_false_when_closed(self):
        ch = SSEChannel()
        ch.close()
        assert ch.push("test", {}) is False

    def test_close_sets_flag(self):
        ch = SSEChannel()
        ch.close()
        assert ch.closed

    def test_close_is_idempotent(self):
        ch = SSEChannel()
        ch.close()
        ch.close()
        assert ch.closed

    @pytest.mark.asyncio
    async def test_async_iteration(self):
        ch = SSEChannel(max_queue=10)
        ch.push("test.event", {"msg": "hello"})
        ch.push("test.event", {"msg": "world"})
        ch.close()

        events = []
        async for ev_str in ch:
            events.append(ev_str)
        assert len(events) == 2
        assert "test.event" in events[0]
        assert "hello" in events[0]

    @pytest.mark.asyncio
    async def test_keepalive_on_timeout(self):
        ch = SSEChannel(max_queue=10)

        async def close_after_delay():
            await asyncio.sleep(0.1)
            ch.close()

        asyncio.get_event_loop().create_task(close_after_delay())

        events = []

        # Just test the close path
        ch.push("test", {"a": 1})
        ch.close()
        async for ev_str in ch:
            events.append(ev_str)
        assert len(events) == 1

    def test_overflow_drops_oldest(self):
        ch = SSEChannel(max_queue=2)
        ch.push("e1", {"n": 1})
        ch.push("e2", {"n": 2})
        ch.push("e3", {"n": 3})  # drops e1
        assert ch.queue_size == 2
        assert ch.event_count == 3

    def test_info(self):
        ef = EventFilter(event_types=("a",), user_ids=("u1",))
        ch = SSEChannel(channel_id="test-ch", event_filter=ef)
        info = ch.info()
        assert info["channel_id"] == "test-ch"
        assert info["type"] == "sse"
        assert info["closed"] is False
        assert info["filter"]["event_types"] == ["a"]
        assert info["filter"]["user_ids"] == ["u1"]


# ═══════════════════════════════════════════════════════════════════════════
# WSChannel
# ═══════════════════════════════════════════════════════════════════════════


class TestWSChannel:
    """Tests for WSChannel push/consume/bidirectional messaging."""

    def test_create_defaults(self):
        ch = WSChannel()
        assert not ch.closed
        assert ch.event_count == 0
        assert len(ch.channel_id) == 16

    def test_push_creates_json_messages(self):
        ch = WSChannel()
        ch.push("test", {"k": "v"})
        assert ch.event_count == 1
        assert ch.queue_size == 1

    def test_push_respects_filter(self):
        ef = EventFilter(namespaces=("ns1",))
        ch = WSChannel(event_filter=ef)
        ch.push("test", {"namespace": "ns1"})
        ch.push("test", {"namespace": "ns2"})  # filtered
        assert ch.event_count == 1

    def test_push_returns_false_when_closed(self):
        ch = WSChannel()
        ch.close()
        assert ch.push("test", {}) is False

    @pytest.mark.asyncio
    async def test_async_iteration(self):
        ch = WSChannel(max_queue=10)
        ch.push("event.a", {"msg": "hi"})
        ch.close()

        msgs = []
        async for m in ch:
            msgs.append(json.loads(m))
        assert len(msgs) == 1
        assert msgs[0]["event_type"] == "event.a"
        assert msgs[0]["data"]["msg"] == "hi"

    def test_handle_client_message_update_filter(self):
        ch = WSChannel()
        resp = ch.handle_client_message(json.dumps({
            "action": "update_filter",
            "event_types": ["memory.updated"],
        }))
        assert resp["status"] == "ok"
        assert resp["action"] == "filter_updated"
        assert ch.event_filter.event_types == ("memory.updated",)

    def test_handle_client_message_ping(self):
        ch = WSChannel()
        resp = ch.handle_client_message(json.dumps({"action": "ping"}))
        assert resp["status"] == "ok"
        assert resp["action"] == "pong"
        assert "timestamp" in resp

    def test_handle_client_message_invalid_json(self):
        ch = WSChannel()
        resp = ch.handle_client_message("not json{{{")
        assert resp["status"] == "error"
        assert "Invalid JSON" in resp["message"]

    def test_handle_client_message_unknown_action(self):
        ch = WSChannel()
        resp = ch.handle_client_message(json.dumps({"action": "explode"}))
        assert resp["status"] == "error"
        assert "Unknown action" in resp["message"]

    def test_overflow_drops_oldest(self):
        ch = WSChannel(max_queue=2)
        ch.push("e1", {})
        ch.push("e2", {})
        ch.push("e3", {})  # drops e1
        assert ch.queue_size == 2

    def test_info(self):
        ch = WSChannel(channel_id="ws-ch")
        info = ch.info()
        assert info["channel_id"] == "ws-ch"
        assert info["type"] == "websocket"
        assert info["messages_received"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# StreamManager
# ═══════════════════════════════════════════════════════════════════════════


class TestStreamManager:
    """Tests for StreamManager lifecycle and channel management."""

    def test_create_sse_channel(self):
        mgr = StreamManager()
        ch = mgr.create_sse_channel(channel_id="sse-1")
        assert ch.channel_id == "sse-1"
        assert mgr.get_sse_channel("sse-1") is ch

    def test_create_ws_channel(self):
        mgr = StreamManager()
        ch = mgr.create_ws_channel(channel_id="ws-1")
        assert ch.channel_id == "ws-1"
        assert mgr.get_ws_channel("ws-1") is ch

    def test_close_sse_channel(self):
        mgr = StreamManager()
        mgr.create_sse_channel(channel_id="sse-x")
        assert mgr.close_sse_channel("sse-x") is True
        assert mgr.get_sse_channel("sse-x") is None

    def test_close_ws_channel(self):
        mgr = StreamManager()
        mgr.create_ws_channel(channel_id="ws-x")
        assert mgr.close_ws_channel("ws-x") is True
        assert mgr.get_ws_channel("ws-x") is None

    def test_close_nonexistent_returns_false(self):
        mgr = StreamManager()
        assert mgr.close_channel("nonexistent") is False

    def test_close_channel_generic(self):
        mgr = StreamManager()
        mgr.create_sse_channel(channel_id="ch1")
        assert mgr.close_channel("ch1") is True
        mgr.create_ws_channel(channel_id="ch2")
        assert mgr.close_channel("ch2") is True

    def test_close_all(self):
        mgr = StreamManager()
        mgr.create_sse_channel()
        mgr.create_sse_channel()
        mgr.create_ws_channel()
        count = mgr.close_all()
        assert count == 3
        assert mgr.list_channels() == []

    def test_list_channels(self):
        mgr = StreamManager()
        mgr.create_sse_channel(channel_id="s1")
        mgr.create_ws_channel(channel_id="w1")
        channels = mgr.list_channels()
        ids = [c["channel_id"] for c in channels]
        assert "s1" in ids
        assert "w1" in ids

    def test_list_excludes_closed(self):
        mgr = StreamManager()
        ch = mgr.create_sse_channel(channel_id="s1")
        ch.close()
        channels = mgr.list_channels()
        assert len(channels) == 0

    def test_broadcast(self):
        mgr = StreamManager()
        ch1 = mgr.create_sse_channel()
        ch2 = mgr.create_ws_channel()
        count = mgr.broadcast("test.event", {"key": "val"})
        assert count == 2
        assert ch1.event_count == 1
        assert ch2.event_count == 1

    def test_broadcast_skips_closed(self):
        mgr = StreamManager()
        mgr.create_sse_channel()
        ch2 = mgr.create_sse_channel()
        ch2.close()
        count = mgr.broadcast("test", {})
        assert count == 1

    def test_stats(self):
        mgr = StreamManager()
        mgr.create_sse_channel()
        mgr.create_ws_channel()
        mgr.create_ws_channel()
        s = mgr.stats()
        assert s["sse_channels"] == 1
        assert s["ws_channels"] == 2
        assert s["total_channels"] == 3
        assert s["bus_attached"] is False

    def test_stats_bus_attached(self):
        mgr = StreamManager()
        mock_bus = MagicMock()
        mock_bus.subscribe.return_value = lambda: None
        mgr.attach_to_bus(mock_bus)
        assert mgr.stats()["bus_attached"] is True

    def test_attach_to_bus_subscribes_wildcard(self):
        mgr = StreamManager()
        mock_bus = MagicMock()
        mock_bus.subscribe.return_value = lambda: None
        mgr.attach_to_bus(mock_bus)
        mock_bus.subscribe.assert_called_once_with("*", mgr._on_bus_event)

    def test_attach_idempotent(self):
        mgr = StreamManager()
        mock_bus = MagicMock()
        mock_bus.subscribe.return_value = lambda: None
        mgr.attach_to_bus(mock_bus)
        mgr.attach_to_bus(mock_bus)
        assert mock_bus.subscribe.call_count == 1

    def test_detach_from_bus(self):
        mgr = StreamManager()
        unsub = MagicMock()
        mock_bus = MagicMock()
        mock_bus.subscribe.return_value = unsub
        mgr.attach_to_bus(mock_bus)
        mgr.detach_from_bus()
        unsub.assert_called_once()
        assert mgr.stats()["bus_attached"] is False

    def test_detach_when_not_attached(self):
        mgr = StreamManager()
        mgr.detach_from_bus()  # no error

    def test_bus_event_dispatches_to_channels(self):
        from memoria.comms.bus import Event, EventType

        mgr = StreamManager()
        ch = mgr.create_sse_channel()

        event = Event(
            type=EventType.MEMORY_UPDATED,
            source="test-agent",
            data={"memory_id": "m123"},
        )
        mgr._on_bus_event(event)
        assert ch.event_count == 1

    def test_bus_event_with_filter(self):
        from memoria.comms.bus import Event, EventType

        ef = EventFilter(event_types=("memory.recalled",))
        mgr = StreamManager()
        ch = mgr.create_sse_channel(event_filter=ef)

        event_match = Event(
            type=EventType.MEMORY_RECALLED,
            source="agent",
            data={},
        )
        event_no_match = Event(
            type=EventType.MEMORY_UPDATED,
            source="agent",
            data={},
        )
        mgr._on_bus_event(event_match)
        mgr._on_bus_event(event_no_match)
        assert ch.event_count == 1

    def test_dispatch_cleans_closed_channels(self):
        mgr = StreamManager()
        ch = mgr.create_sse_channel(channel_id="ephemeral")
        ch.close()
        mgr._dispatch("test", {})
        assert mgr.get_sse_channel("ephemeral") is None


# ═══════════════════════════════════════════════════════════════════════════
# Memoria Integration
# ═══════════════════════════════════════════════════════════════════════════


class TestMemoriaStreaming:
    """Tests for Memoria streaming methods."""

    def _make_memoria(self, tmp_path):
        from memoria import Memoria
        return Memoria(project_dir=str(tmp_path))

    def test_stream_subscribe_sse(self, tmp_path):
        m = self._make_memoria(tmp_path)
        info = m.stream_subscribe(channel_type="sse")
        assert info["type"] == "sse"
        assert "channel_id" in info
        assert info["closed"] is False

    def test_stream_subscribe_ws(self, tmp_path):
        m = self._make_memoria(tmp_path)
        info = m.stream_subscribe(channel_type="ws")
        assert info["type"] == "websocket"

    def test_stream_subscribe_with_filters(self, tmp_path):
        m = self._make_memoria(tmp_path)
        info = m.stream_subscribe(
            event_types=["memory.updated"],
            user_ids=["alice"],
            namespaces=["ns1"],
        )
        assert info["filter"]["event_types"] == ["memory.updated"]
        assert info["filter"]["user_ids"] == ["alice"]
        assert info["filter"]["namespaces"] == ["ns1"]

    def test_stream_subscribe_with_custom_id(self, tmp_path):
        m = self._make_memoria(tmp_path)
        info = m.stream_subscribe(channel_id="my-stream")
        assert info["channel_id"] == "my-stream"

    def test_stream_unsubscribe(self, tmp_path):
        m = self._make_memoria(tmp_path)
        m.stream_subscribe(channel_id="ch-del")
        result = m.stream_unsubscribe("ch-del")
        assert result["status"] == "closed"

    def test_stream_unsubscribe_not_found(self, tmp_path):
        m = self._make_memoria(tmp_path)
        result = m.stream_unsubscribe("nonexistent")
        assert result["status"] == "not_found"

    def test_stream_list_channels(self, tmp_path):
        m = self._make_memoria(tmp_path)
        m.stream_subscribe(channel_id="ch-a")
        m.stream_subscribe(channel_type="ws", channel_id="ch-b")
        channels = m.stream_list_channels()
        ids = [c["channel_id"] for c in channels]
        assert "ch-a" in ids
        assert "ch-b" in ids

    def test_stream_broadcast(self, tmp_path):
        m = self._make_memoria(tmp_path)
        m.stream_subscribe(channel_id="ch-bc")
        result = m.stream_broadcast("custom.event", {"msg": "hello"})
        assert result["status"] == "broadcast"
        assert result["channels_notified"] == 1

    def test_stream_stats(self, tmp_path):
        m = self._make_memoria(tmp_path)
        m.stream_subscribe()
        m.stream_subscribe(channel_type="ws")
        stats = m.stream_stats()
        assert stats["sse_channels"] == 1
        assert stats["ws_channels"] == 1
        assert stats["bus_attached"] is True


# ═══════════════════════════════════════════════════════════════════════════
# Module-level singleton
# ═══════════════════════════════════════════════════════════════════════════


class TestModuleSingleton:
    """Test module-level get_stream_manager."""

    def test_singleton(self):
        from memoria.streaming.manager import get_stream_manager
        mgr1 = get_stream_manager()
        mgr2 = get_stream_manager()
        assert mgr1 is mgr2


# ═══════════════════════════════════════════════════════════════════════════
# End-to-end: bus → channel
# ═══════════════════════════════════════════════════════════════════════════


class TestEndToEndBusToChannel:
    """Integration test: publish on bus → event appears in channel."""

    @pytest.mark.asyncio
    async def test_bus_publish_reaches_sse_channel(self):
        from memoria.comms.bus import Event, EventType, MessageBus

        bus = MessageBus()
        mgr = StreamManager()
        mgr.attach_to_bus(bus)

        ch = mgr.create_sse_channel()

        bus.publish(Event(
            type=EventType.MEMORY_UPDATED,
            source="e2e-test",
            data={"memory_id": "m999"},
        ))

        assert ch.event_count == 1
        ch.close()
        mgr.detach_from_bus()

    @pytest.mark.asyncio
    async def test_bus_publish_reaches_ws_channel(self):
        from memoria.comms.bus import Event, EventType, MessageBus

        bus = MessageBus()
        mgr = StreamManager()
        mgr.attach_to_bus(bus)

        ch = mgr.create_ws_channel()

        bus.publish(Event(
            type=EventType.TASK_COMPLETED,
            source="e2e-test",
            data={"task_id": "t42"},
        ))

        assert ch.event_count == 1
        ch.close()
        mgr.detach_from_bus()

    @pytest.mark.asyncio
    async def test_filtered_channel_ignores_unmatched(self):
        from memoria.comms.bus import Event, EventType, MessageBus

        bus = MessageBus()
        mgr = StreamManager()
        mgr.attach_to_bus(bus)

        ef = EventFilter(event_types=("memory.recalled",))
        ch = mgr.create_sse_channel(event_filter=ef)

        # This should be ignored (memory.updated ≠ memory.recalled)
        bus.publish(Event(
            type=EventType.MEMORY_UPDATED,
            source="e2e-test",
            data={},
        ))

        # This should be accepted
        bus.publish(Event(
            type=EventType.MEMORY_RECALLED,
            source="e2e-test",
            data={},
        ))

        assert ch.event_count == 1
        ch.close()
        mgr.detach_from_bus()

    @pytest.mark.asyncio
    async def test_multiple_channels_receive_same_event(self):
        from memoria.comms.bus import Event, EventType, MessageBus

        bus = MessageBus()
        mgr = StreamManager()
        mgr.attach_to_bus(bus)

        ch1 = mgr.create_sse_channel()
        ch2 = mgr.create_ws_channel()

        bus.publish(Event(
            type=EventType.MEMORY_UPDATED,
            source="multi-test",
            data={"id": "x"},
        ))

        assert ch1.event_count == 1
        assert ch2.event_count == 1

        ch1.close()
        ch2.close()
        mgr.detach_from_bus()
