"""Tests for the Communication Layer (src/comms/).

Covers Mailbox, MessageBus, and PermissionBridge with thread-safety tests.
"""

from __future__ import annotations

import threading
import time
import unittest

from memoria.comms.bus import (
    Event,
    EventType,
    MessageBus,
    get_message_bus,
)
from memoria.comms.mailbox import Mailbox, MailboxMessage
from memoria.comms.permissions import (
    PermissionBridge,
    PermissionDecision,
    PermissionRequest,
)

# ======================================================================
# Mailbox tests
# ======================================================================


class TestMailboxMessage(unittest.TestCase):
    """MailboxMessage dataclass basics."""

    def test_defaults(self) -> None:
        msg = MailboxMessage(sender="a1", content="hello")
        self.assertEqual(msg.sender, "a1")
        self.assertEqual(msg.content, "hello")
        self.assertEqual(msg.message_type, "text")
        self.assertIsInstance(msg.timestamp, float)
        self.assertEqual(msg.metadata, {})

    def test_custom_fields(self) -> None:
        msg = MailboxMessage(
            sender="a2",
            content={"key": "val"},
            message_type="tool_result",
            metadata={"rid": "123"},
        )
        self.assertEqual(msg.message_type, "tool_result")
        self.assertEqual(msg.metadata["rid"], "123")


class TestMailboxSendPoll(unittest.TestCase):
    """Send and poll (non-blocking)."""

    def setUp(self) -> None:
        self.mb = Mailbox()

    def test_send_increments_size(self) -> None:
        self.assertEqual(self.mb.size, 0)
        self.mb.send(MailboxMessage(sender="a", content="m1"))
        self.assertEqual(self.mb.size, 1)

    def test_poll_returns_message(self) -> None:
        self.mb.send(MailboxMessage(sender="a", content="m1"))
        msg = self.mb.poll()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.content, "m1")
        self.assertEqual(self.mb.size, 0)

    def test_poll_empty_returns_none(self) -> None:
        self.assertIsNone(self.mb.poll())

    def test_poll_with_filter(self) -> None:
        self.mb.send(MailboxMessage(sender="a", content="m1", message_type="text"))
        self.mb.send(MailboxMessage(sender="b", content="m2", message_type="system"))
        self.mb.send(MailboxMessage(sender="a", content="m3", message_type="text"))

        msg = self.mb.poll(filter_fn=lambda m: m.message_type == "system")
        self.assertIsNotNone(msg)
        self.assertEqual(msg.content, "m2")
        self.assertEqual(self.mb.size, 2)  # m1 and m3 remain

    def test_poll_filter_no_match(self) -> None:
        self.mb.send(MailboxMessage(sender="a", content="m1"))
        msg = self.mb.poll(filter_fn=lambda m: m.sender == "nonexistent")
        self.assertIsNone(msg)
        self.assertEqual(self.mb.size, 1)

    def test_fifo_order(self) -> None:
        for i in range(5):
            self.mb.send(MailboxMessage(sender="a", content=f"m{i}"))
        for i in range(5):
            msg = self.mb.poll()
            self.assertEqual(msg.content, f"m{i}")


class TestMailboxReceive(unittest.TestCase):
    """Blocking receive with timeout."""

    def setUp(self) -> None:
        self.mb = Mailbox()

    def test_receive_immediate(self) -> None:
        self.mb.send(MailboxMessage(sender="a", content="ready"))
        msg = self.mb.receive(timeout=1.0)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.content, "ready")

    def test_receive_timeout_empty(self) -> None:
        start = time.time()
        msg = self.mb.receive(timeout=0.1)
        elapsed = time.time() - start
        self.assertIsNone(msg)
        self.assertGreaterEqual(elapsed, 0.05)

    def test_receive_blocks_until_send(self) -> None:

        def delayed_send() -> None:
            time.sleep(0.05)
            self.mb.send(MailboxMessage(sender="bg", content="delayed"))

        t = threading.Thread(target=delayed_send)
        t.start()
        msg = self.mb.receive(timeout=2.0)
        t.join()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.content, "delayed")

    def test_receive_with_filter_blocks(self) -> None:
        """Receive skips non-matching messages and waits for a match."""
        def delayed_send() -> None:
            time.sleep(0.02)
            self.mb.send(MailboxMessage(sender="a", content="skip", message_type="text"))
            time.sleep(0.02)
            self.mb.send(MailboxMessage(sender="b", content="want", message_type="system"))

        t = threading.Thread(target=delayed_send)
        t.start()
        msg = self.mb.receive(timeout=2.0, filter_fn=lambda m: m.message_type == "system")
        t.join()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.content, "want")
        # The non-matching "skip" message should still be in the queue
        self.assertEqual(self.mb.size, 1)


class TestMailboxDrainClear(unittest.TestCase):
    """Drain and clear operations."""

    def setUp(self) -> None:
        self.mb = Mailbox()

    def test_drain_returns_all(self) -> None:
        for i in range(3):
            self.mb.send(MailboxMessage(sender="a", content=f"m{i}"))
        msgs = self.mb.drain()
        self.assertEqual(len(msgs), 3)
        self.assertEqual(self.mb.size, 0)

    def test_drain_empty(self) -> None:
        msgs = self.mb.drain()
        self.assertEqual(msgs, [])

    def test_clear(self) -> None:
        for i in range(3):
            self.mb.send(MailboxMessage(sender="a", content=f"m{i}"))
        self.mb.clear()
        self.assertEqual(self.mb.size, 0)
        self.assertIsNone(self.mb.poll())


class TestMailboxPeek(unittest.TestCase):
    """Non-destructive peek."""

    def setUp(self) -> None:
        self.mb = Mailbox()

    def test_peek_returns_first(self) -> None:
        self.mb.send(MailboxMessage(sender="a", content="first"))
        self.mb.send(MailboxMessage(sender="a", content="second"))
        msg = self.mb.peek()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.content, "first")
        self.assertEqual(self.mb.size, 2)  # Not removed

    def test_peek_empty(self) -> None:
        self.assertIsNone(self.mb.peek())


class TestMailboxSubscribe(unittest.TestCase):
    """Subscriber notifications."""

    def setUp(self) -> None:
        self.mb = Mailbox()

    def test_subscribe_called_on_send(self) -> None:
        calls: list[int] = []
        self.mb.subscribe(lambda: calls.append(1))
        self.mb.send(MailboxMessage(sender="a", content="m"))
        self.assertEqual(len(calls), 1)

    def test_unsubscribe(self) -> None:
        calls: list[int] = []
        unsub = self.mb.subscribe(lambda: calls.append(1))
        self.mb.send(MailboxMessage(sender="a", content="m1"))
        unsub()
        self.mb.send(MailboxMessage(sender="a", content="m2"))
        self.assertEqual(len(calls), 1)

    def test_subscriber_exception_does_not_propagate(self) -> None:
        def bad_sub() -> None:
            raise RuntimeError("boom")

        self.mb.subscribe(bad_sub)
        # Should not raise
        self.mb.send(MailboxMessage(sender="a", content="m"))
        self.assertEqual(self.mb.size, 1)


class TestMailboxRevision(unittest.TestCase):
    """Revision counter."""

    def test_revision_increments(self) -> None:
        mb = Mailbox()
        self.assertEqual(mb.revision, 0)
        mb.send(MailboxMessage(sender="a", content="m1"))
        self.assertEqual(mb.revision, 1)
        mb.send(MailboxMessage(sender="a", content="m2"))
        self.assertEqual(mb.revision, 2)


class TestMailboxConcurrency(unittest.TestCase):
    """Thread-safety under concurrent access."""

    def test_concurrent_send_receive(self) -> None:
        mb = Mailbox()
        num_messages = 200
        received: list[MailboxMessage] = []
        lock = threading.Lock()

        def sender() -> None:
            for i in range(num_messages):
                mb.send(MailboxMessage(sender="s", content=f"m{i}"))

        def receiver() -> None:
            count = 0
            while count < num_messages:
                msg = mb.receive(timeout=2.0)
                if msg is not None:
                    with lock:
                        received.append(msg)
                    count += 1

        t_send = threading.Thread(target=sender)
        t_recv = threading.Thread(target=receiver)
        t_recv.start()
        t_send.start()
        t_send.join()
        t_recv.join()

        self.assertEqual(len(received), num_messages)

    def test_multiple_senders(self) -> None:
        mb = Mailbox()
        per_sender = 50
        num_senders = 4

        def sender(sid: int) -> None:
            for i in range(per_sender):
                mb.send(MailboxMessage(sender=f"s{sid}", content=f"m{i}"))

        threads = [threading.Thread(target=sender, args=(s,)) for s in range(num_senders)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(mb.size, per_sender * num_senders)


# ======================================================================
# MessageBus tests
# ======================================================================


class TestMessageBusSubscribe(unittest.TestCase):
    """Publish / subscribe / unsubscribe."""

    def setUp(self) -> None:
        self.bus = MessageBus()

    def test_subscribe_receives_event(self) -> None:
        events: list[Event] = []
        self.bus.subscribe(EventType.AGENT_SPAWNED.value, events.append)
        self.bus.publish(Event(type=EventType.AGENT_SPAWNED, source="a1"))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].source, "a1")

    def test_unsubscribe(self) -> None:
        events: list[Event] = []
        unsub = self.bus.subscribe(EventType.AGENT_SPAWNED.value, events.append)
        self.bus.publish(Event(type=EventType.AGENT_SPAWNED, source="a1"))
        unsub()
        self.bus.publish(Event(type=EventType.AGENT_SPAWNED, source="a2"))
        self.assertEqual(len(events), 1)

    def test_typed_subscription_ignores_other_types(self) -> None:
        events: list[Event] = []
        self.bus.subscribe(EventType.AGENT_SPAWNED.value, events.append)
        self.bus.publish(Event(type=EventType.AGENT_FAILED, source="a1"))
        self.assertEqual(len(events), 0)

    def test_callback_exception_does_not_propagate(self) -> None:
        def bad_cb(e: Event) -> None:
            raise RuntimeError("boom")

        self.bus.subscribe(EventType.AGENT_SPAWNED.value, bad_cb)
        # Should not raise
        self.bus.publish(Event(type=EventType.AGENT_SPAWNED, source="a1"))


class TestMessageBusWildcard(unittest.TestCase):
    """Wildcard subscriptions."""

    def setUp(self) -> None:
        self.bus = MessageBus()

    def test_wildcard_receives_all(self) -> None:
        events: list[Event] = []
        self.bus.subscribe("*", events.append)
        self.bus.publish(Event(type=EventType.AGENT_SPAWNED, source="a1"))
        self.bus.publish(Event(type=EventType.TASK_COMPLETED, source="a2"))
        self.assertEqual(len(events), 2)

    def test_wildcard_and_typed_both_fire(self) -> None:
        wild: list[Event] = []
        typed: list[Event] = []
        self.bus.subscribe("*", wild.append)
        self.bus.subscribe(EventType.AGENT_SPAWNED.value, typed.append)
        self.bus.publish(Event(type=EventType.AGENT_SPAWNED, source="a1"))
        self.assertEqual(len(wild), 1)
        self.assertEqual(len(typed), 1)


class TestMessageBusTargetedEvents(unittest.TestCase):
    """Targeted events (target field)."""

    def setUp(self) -> None:
        self.bus = MessageBus()

    def test_targeted_event_published(self) -> None:
        events: list[Event] = []
        self.bus.subscribe(EventType.MESSAGE_SENT.value, events.append)
        self.bus.publish(Event(
            type=EventType.MESSAGE_SENT,
            source="a1",
            target="a2",
            data={"text": "hi"},
        ))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].target, "a2")

    def test_broadcast_event_has_no_target(self) -> None:
        events: list[Event] = []
        self.bus.subscribe(EventType.AGENT_IDLE.value, events.append)
        self.bus.publish(Event(type=EventType.AGENT_IDLE, source="a1"))
        self.assertIsNone(events[0].target)


class TestMessageBusEventHistory(unittest.TestCase):
    """Event history queries."""

    def setUp(self) -> None:
        self.bus = MessageBus()

    def test_get_all_events(self) -> None:
        self.bus.publish(Event(type=EventType.AGENT_SPAWNED, source="a1"))
        self.bus.publish(Event(type=EventType.AGENT_FAILED, source="a2"))
        events = self.bus.get_events()
        self.assertEqual(len(events), 2)

    def test_get_events_by_type(self) -> None:
        self.bus.publish(Event(type=EventType.AGENT_SPAWNED, source="a1"))
        self.bus.publish(Event(type=EventType.AGENT_FAILED, source="a2"))
        events = self.bus.get_events(event_type=EventType.AGENT_SPAWNED.value)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].source, "a1")

    def test_get_events_by_source(self) -> None:
        self.bus.publish(Event(type=EventType.AGENT_SPAWNED, source="a1"))
        self.bus.publish(Event(type=EventType.AGENT_SPAWNED, source="a2"))
        events = self.bus.get_events(source="a1")
        self.assertEqual(len(events), 1)

    def test_get_events_since(self) -> None:
        self.bus.publish(Event(type=EventType.AGENT_SPAWNED, source="a1"))
        cutoff = time.time()
        time.sleep(0.01)
        self.bus.publish(Event(type=EventType.AGENT_SPAWNED, source="a2"))
        events = self.bus.get_events(since=cutoff)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].source, "a2")

    def test_clear_history(self) -> None:
        self.bus.publish(Event(type=EventType.AGENT_SPAWNED, source="a1"))
        self.bus.clear_history()
        self.assertEqual(len(self.bus.get_events()), 0)

    def test_history_bounded(self) -> None:
        bus = MessageBus()
        bus._max_log_size = 10
        for i in range(20):
            bus.publish(Event(type=EventType.AGENT_SPAWNED, source=f"a{i}"))
        self.assertLessEqual(len(bus.get_events()), 10)


class TestMessageBusSingleton(unittest.TestCase):
    """Module-level singleton."""

    def test_get_message_bus_returns_same(self) -> None:
        bus1 = get_message_bus()
        bus2 = get_message_bus()
        self.assertIs(bus1, bus2)


# ======================================================================
# PermissionBridge tests
# ======================================================================


class TestPermissionRequest(unittest.TestCase):
    """PermissionRequest dataclass."""

    def test_respond_and_wait(self) -> None:
        req = PermissionRequest(
            request_id="r1",
            agent_id="child-1",
            tool_name="bash",
        )

        def responder() -> None:
            time.sleep(0.02)
            req.respond(PermissionDecision.ALLOW)

        t = threading.Thread(target=responder)
        t.start()
        decision = req.wait_for_response(timeout=2.0)
        t.join()
        self.assertEqual(decision, PermissionDecision.ALLOW)

    def test_wait_timeout(self) -> None:
        req = PermissionRequest(
            request_id="r2",
            agent_id="child-1",
            tool_name="bash",
        )
        decision = req.wait_for_response(timeout=0.05)
        self.assertIsNone(decision)


class TestPermissionBridgePreAuth(unittest.TestCase):
    """Pre-authorization checks."""

    def setUp(self) -> None:
        self.bridge = PermissionBridge()

    def test_no_preauth_returns_none(self) -> None:
        self.assertIsNone(self.bridge.check_pre_authorized("a1", "bash"))

    def test_allowed_tools(self) -> None:
        self.bridge.set_allowed_tools("a1", {"bash", "read_file"})
        self.assertEqual(
            self.bridge.check_pre_authorized("a1", "bash"),
            PermissionDecision.ALLOW,
        )
        self.assertIsNone(self.bridge.check_pre_authorized("a1", "write_file"))

    def test_denied_tools(self) -> None:
        self.bridge.set_denied_tools("a1", {"rm"})
        self.assertEqual(
            self.bridge.check_pre_authorized("a1", "rm"),
            PermissionDecision.DENY,
        )

    def test_deny_takes_precedence(self) -> None:
        self.bridge.set_allowed_tools("a1", {"bash"})
        self.bridge.set_denied_tools("a1", {"bash"})
        self.assertEqual(
            self.bridge.check_pre_authorized("a1", "bash"),
            PermissionDecision.DENY,
        )


class TestPermissionBridgeRequestRespond(unittest.TestCase):
    """Full request/respond round-trip."""

    def setUp(self) -> None:
        self.bridge = PermissionBridge()

    def test_round_trip_allow(self) -> None:
        def handler(req: PermissionRequest) -> None:
            req.respond(PermissionDecision.ALLOW)

        self.bridge.register_handler(handler)
        decision = self.bridge.request_permission("child-1", "bash", timeout=2.0)
        self.assertEqual(decision, PermissionDecision.ALLOW)

    def test_round_trip_deny(self) -> None:
        def handler(req: PermissionRequest) -> None:
            req.respond(PermissionDecision.DENY)

        self.bridge.register_handler(handler)
        decision = self.bridge.request_permission("child-1", "bash", timeout=2.0)
        self.assertEqual(decision, PermissionDecision.DENY)

    def test_preauth_bypasses_handler(self) -> None:
        handler_called = []

        def handler(req: PermissionRequest) -> None:
            handler_called.append(True)
            req.respond(PermissionDecision.ALLOW)

        self.bridge.register_handler(handler)
        self.bridge.set_allowed_tools("child-1", {"bash"})
        decision = self.bridge.request_permission("child-1", "bash", timeout=2.0)
        self.assertEqual(decision, PermissionDecision.ALLOW)
        self.assertEqual(len(handler_called), 0)

    def test_allow_always_remembers(self) -> None:
        call_count = []

        def handler(req: PermissionRequest) -> None:
            call_count.append(1)
            req.respond(PermissionDecision.ALLOW_ALWAYS)

        self.bridge.register_handler(handler)

        # First call goes through handler
        d1 = self.bridge.request_permission("child-1", "bash", timeout=2.0)
        self.assertEqual(d1, PermissionDecision.ALLOW_ALWAYS)
        self.assertEqual(len(call_count), 1)

        # Second call is pre-authorized
        d2 = self.bridge.request_permission("child-1", "bash", timeout=2.0)
        self.assertEqual(d2, PermissionDecision.ALLOW)
        self.assertEqual(len(call_count), 1)  # Handler not called again

    def test_respond_to_request_by_id(self) -> None:
        captured: list[PermissionRequest] = []

        def handler(req: PermissionRequest) -> None:
            captured.append(req)
            # Don't respond immediately — let the test do it

        self.bridge.register_handler(handler)

        result = [None]

        def requester() -> None:
            result[0] = self.bridge.request_permission(
                "child-1", "bash", timeout=2.0,
            )

        t = threading.Thread(target=requester)
        t.start()
        time.sleep(0.05)  # Let the request be filed

        # Respond via bridge API
        pending = self.bridge.get_pending_requests()
        self.assertEqual(len(pending), 1)
        ok = self.bridge.respond_to_request(
            pending[0].request_id, PermissionDecision.ALLOW,
        )
        self.assertTrue(ok)

        t.join()
        self.assertEqual(result[0], PermissionDecision.ALLOW)

    def test_respond_to_unknown_request(self) -> None:
        self.assertFalse(
            self.bridge.respond_to_request("nonexistent", PermissionDecision.ALLOW),
        )


class TestPermissionBridgeTimeout(unittest.TestCase):
    """Timeout handling."""

    def setUp(self) -> None:
        self.bridge = PermissionBridge()

    def test_timeout_returns_deny(self) -> None:
        # No handler → nobody responds → timeout
        decision = self.bridge.request_permission(
            "child-1", "bash", timeout=0.1,
        )
        self.assertEqual(decision, PermissionDecision.DENY)

    def test_timeout_cleans_up_pending(self) -> None:
        self.bridge.request_permission("child-1", "bash", timeout=0.05)
        self.assertEqual(len(self.bridge.get_pending_requests()), 0)


class TestPermissionBridgeHandlers(unittest.TestCase):
    """Handler registration / unregistration."""

    def setUp(self) -> None:
        self.bridge = PermissionBridge()

    def test_unregister_handler(self) -> None:
        calls: list[int] = []

        def handler(req: PermissionRequest) -> None:
            calls.append(1)
            req.respond(PermissionDecision.ALLOW)

        unreg = self.bridge.register_handler(handler)
        self.bridge.request_permission("child-1", "bash", timeout=1.0)
        self.assertEqual(len(calls), 1)

        unreg()
        # No handler → timeout
        decision = self.bridge.request_permission("child-1", "bash", timeout=0.05)
        self.assertEqual(decision, PermissionDecision.DENY)
        self.assertEqual(len(calls), 1)


class TestPermissionBridgeConcurrency(unittest.TestCase):
    """Concurrent permission requests."""

    def test_concurrent_requests(self) -> None:
        bridge = PermissionBridge()

        def handler(req: PermissionRequest) -> None:
            time.sleep(0.01)
            req.respond(PermissionDecision.ALLOW)

        bridge.register_handler(handler)
        results: list[PermissionDecision] = [None] * 10  # type: ignore[list-item]

        def request(idx: int) -> None:
            results[idx] = bridge.request_permission(
                f"child-{idx}", "bash", timeout=2.0,
            )

        threads = [threading.Thread(target=request, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertTrue(all(r == PermissionDecision.ALLOW for r in results))


class TestPermissionBridgePendingFilter(unittest.TestCase):
    """Pending request filtering."""

    def setUp(self) -> None:
        self.bridge = PermissionBridge()

    def test_get_pending_by_agent(self) -> None:
        captured: list[PermissionRequest] = []

        def handler(req: PermissionRequest) -> None:
            captured.append(req)

        self.bridge.register_handler(handler)

        threads = []
        for agent in ["a1", "a2", "a1"]:
            t = threading.Thread(
                target=self.bridge.request_permission,
                args=(agent, "bash"),
                kwargs={"timeout": 1.0},
            )
            t.start()
            threads.append(t)

        time.sleep(0.1)  # Let requests arrive

        all_pending = self.bridge.get_pending_requests()
        a1_pending = self.bridge.get_pending_requests(agent_id="a1")
        self.assertEqual(len(all_pending), 3)
        self.assertEqual(len(a1_pending), 2)

        # Clean up — respond to all
        for req in captured:
            req.respond(PermissionDecision.DENY)
        for t in threads:
            t.join()


if __name__ == "__main__":
    unittest.main()
