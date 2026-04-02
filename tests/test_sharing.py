"""Comprehensive tests for the MEMORIA multi-agent memory sharing module."""

from __future__ import annotations

import threading
import time
import uuid

import pytest

from memoria.sharing.types import (
    BroadcastPolicy,
    CoherenceReport,
    ConflictStrategy,
    MemorySubscription,
    SharedMemoryEvent,
    SubscriptionFilter,
    TeamDNAProfile,
    TeamMemoryView,
)
from memoria.sharing.broadcaster import MemoryBroadcaster
from memoria.sharing.watcher import MemoryWatcher
from memoria.sharing.team_dna import TeamDNASync
from memoria.sharing.coordinator import MemoryCoordinator


# ======================================================================
# Type Tests
# ======================================================================


class TestSharedMemoryEvent:
    """Tests for SharedMemoryEvent dataclass."""

    def test_creation_with_defaults(self):
        evt = SharedMemoryEvent(
            event_id="e1",
            source_agent_id="agent-a",
            target_namespace="ns1",
            memory_key="k1",
            memory_value="v1",
        )
        assert evt.event_id == "e1"
        assert evt.source_agent_id == "agent-a"
        assert evt.topics == []
        assert evt.ttl is None
        assert evt.provenance == {}
        assert isinstance(evt.timestamp, float)

    def test_creation_with_all_fields(self):
        evt = SharedMemoryEvent(
            event_id="e2",
            source_agent_id="agent-b",
            target_namespace="ns2",
            memory_key="k2",
            memory_value={"nested": True},
            timestamp=100.0,
            topics=["ml", "nlp"],
            ttl=60.0,
            provenance={"source": "test"},
        )
        assert evt.memory_value == {"nested": True}
        assert evt.topics == ["ml", "nlp"]
        assert evt.ttl == 60.0

    def test_to_dict(self):
        evt = SharedMemoryEvent(
            event_id="e3",
            source_agent_id="a",
            target_namespace="ns",
            memory_key="k",
            memory_value=42,
            topics=["t1"],
        )
        d = evt.to_dict()
        assert d["event_id"] == "e3"
        assert d["memory_value"] == 42
        assert d["topics"] == ["t1"]
        assert "timestamp" in d

    def test_is_expired_no_ttl(self):
        evt = SharedMemoryEvent(
            event_id="e4", source_agent_id="a",
            target_namespace="ns", memory_key="k", memory_value="v",
        )
        assert evt.is_expired() is False

    def test_is_expired_with_ttl(self):
        evt = SharedMemoryEvent(
            event_id="e5", source_agent_id="a",
            target_namespace="ns", memory_key="k", memory_value="v",
            timestamp=time.time() - 100, ttl=1.0,
        )
        assert evt.is_expired() is True

    def test_not_expired_within_ttl(self):
        evt = SharedMemoryEvent(
            event_id="e6", source_agent_id="a",
            target_namespace="ns", memory_key="k", memory_value="v",
            ttl=9999.0,
        )
        assert evt.is_expired() is False

    def test_provenance_preserved(self):
        evt = SharedMemoryEvent(
            event_id="e7", source_agent_id="a",
            target_namespace="ns", memory_key="k", memory_value="v",
            provenance={"author": "user1", "version": 3},
        )
        d = evt.to_dict()
        assert d["provenance"]["author"] == "user1"
        assert d["provenance"]["version"] == 3


class TestMemorySubscription:
    """Tests for MemorySubscription dataclass."""

    def test_creation_defaults(self):
        sub = MemorySubscription(subscriber_id="s1", filter_type=SubscriptionFilter.ALL)
        assert sub.subscriber_id == "s1"
        assert sub.filter_value == ""
        assert sub.active is True

    def test_creation_full(self):
        sub = MemorySubscription(
            subscriber_id="s2",
            filter_type=SubscriptionFilter.BY_NAMESPACE,
            filter_value="project-x",
            callback_id="cb1",
            active=False,
        )
        assert sub.filter_type == SubscriptionFilter.BY_NAMESPACE
        assert sub.filter_value == "project-x"
        assert sub.active is False

    def test_to_dict(self):
        sub = MemorySubscription(
            subscriber_id="s3",
            filter_type=SubscriptionFilter.BY_TOPIC,
            filter_value="ml",
        )
        d = sub.to_dict()
        assert d["filter_type"] == "by_topic"
        assert d["filter_value"] == "ml"

    def test_active_toggle(self):
        sub = MemorySubscription(subscriber_id="s4", filter_type=SubscriptionFilter.ALL)
        assert sub.active is True
        sub.active = False
        assert sub.active is False

    def test_by_agent_filter(self):
        sub = MemorySubscription(
            subscriber_id="s5",
            filter_type=SubscriptionFilter.BY_AGENT,
            filter_value="agent-x",
        )
        assert sub.filter_type == SubscriptionFilter.BY_AGENT
        assert sub.filter_value == "agent-x"


class TestTeamMemoryView:
    """Tests for TeamMemoryView dataclass."""

    def test_creation_defaults(self):
        v = TeamMemoryView(team_id="team1")
        assert v.team_id == "team1"
        assert v.agent_memories == {}
        assert v.shared_memories == []
        assert v.total_memories == 0

    def test_creation_with_data(self):
        v = TeamMemoryView(
            team_id="team2",
            agent_memories={"a1": [{"k": "v"}]},
            shared_memories=[{"k": "shared"}],
            total_memories=2,
        )
        assert len(v.agent_memories["a1"]) == 1
        assert v.total_memories == 2

    def test_to_dict(self):
        v = TeamMemoryView(team_id="t1", total_memories=5)
        d = v.to_dict()
        assert d["team_id"] == "t1"
        assert d["total_memories"] == 5

    def test_empty_team(self):
        v = TeamMemoryView(team_id="empty")
        d = v.to_dict()
        assert d["agent_memories"] == {}
        assert d["shared_memories"] == []


class TestTeamDNAProfile:
    """Tests for TeamDNAProfile dataclass."""

    def test_creation_defaults(self):
        p = TeamDNAProfile(team_id="team1")
        assert p.member_count == 0
        assert p.diversity_score == 0.0

    def test_creation_with_data(self):
        p = TeamDNAProfile(
            team_id="team2",
            member_count=3,
            aggregated_expertise={"python": 0.9},
            diversity_score=0.5,
        )
        assert p.aggregated_expertise["python"] == 0.9

    def test_to_dict(self):
        p = TeamDNAProfile(team_id="t", member_count=2)
        d = p.to_dict()
        assert d["member_count"] == 2
        assert "last_updated" in d

    def test_diversity_score_range(self):
        p = TeamDNAProfile(team_id="t", diversity_score=0.75)
        assert 0.0 <= p.diversity_score <= 1.0


class TestCoherenceReport:
    """Tests for CoherenceReport dataclass."""

    def test_creation_defaults(self):
        r = CoherenceReport(team_id="team1")
        assert r.total_checked == 0
        assert r.conflicts_found == 0

    def test_conflict_tracking(self):
        r = CoherenceReport(
            team_id="team2",
            total_checked=10,
            conflicts_found=2,
            resolved=1,
            unresolved=1,
        )
        assert r.conflicts_found == 2
        assert r.resolved + r.unresolved == r.conflicts_found

    def test_to_dict(self):
        r = CoherenceReport(team_id="t", total_checked=5, conflicts_found=1)
        d = r.to_dict()
        assert d["total_checked"] == 5

    def test_details_list(self):
        r = CoherenceReport(
            team_id="t",
            details=[{"key": "k1", "type": "value_mismatch"}],
        )
        assert len(r.details) == 1
        assert r.details[0]["type"] == "value_mismatch"


class TestBroadcastPolicy:
    """Tests for BroadcastPolicy enum."""

    def test_all_values_exist(self):
        assert BroadcastPolicy.ALL.value == "all"
        assert BroadcastPolicy.NAMESPACE.value == "namespace"
        assert BroadcastPolicy.TOPIC.value == "topic"
        assert BroadcastPolicy.NONE.value == "none"

    def test_from_value(self):
        assert BroadcastPolicy("all") == BroadcastPolicy.ALL

    def test_enum_members_count(self):
        assert len(BroadcastPolicy) == 4


# ======================================================================
# Broadcaster Tests
# ======================================================================


class TestMemoryBroadcaster:
    """Tests for MemoryBroadcaster."""

    def setup_method(self):
        self.broadcaster = MemoryBroadcaster()

    def _make_event(self, source="agent-a", ns="ns1", key="k1", value="v1",
                    topics=None) -> SharedMemoryEvent:
        return SharedMemoryEvent(
            event_id=str(uuid.uuid4()),
            source_agent_id=source,
            target_namespace=ns,
            memory_key=key,
            memory_value=value,
            topics=topics or [],
        )

    def test_default_policy(self):
        assert self.broadcaster.policy == BroadcastPolicy.ALL

    def test_set_policy(self):
        self.broadcaster.set_policy(BroadcastPolicy.NAMESPACE)
        assert self.broadcaster.policy == BroadcastPolicy.NAMESPACE

    def test_register_agent(self):
        self.broadcaster.register_agent("a1", namespaces=["ns1"])
        agents = self.broadcaster.get_registered_agents()
        assert "a1" in agents
        assert "ns1" in agents["a1"]["namespaces"]

    def test_unregister_agent(self):
        self.broadcaster.register_agent("a1")
        self.broadcaster.unregister_agent("a1")
        assert "a1" not in self.broadcaster.get_registered_agents()

    def test_unregister_nonexistent(self):
        self.broadcaster.unregister_agent("ghost")  # no error

    def test_broadcast_all_policy(self):
        self.broadcaster.register_agent("a1")
        self.broadcaster.register_agent("a2")
        evt = self._make_event(source="a0")
        result = self.broadcaster.broadcast(evt)
        assert result["recipient_count"] == 2
        assert "a1" in result["recipients"]
        assert "a2" in result["recipients"]

    def test_broadcast_excludes_source(self):
        self.broadcaster.register_agent("a1")
        self.broadcaster.register_agent("a2")
        evt = self._make_event(source="a1")
        result = self.broadcaster.broadcast(evt)
        assert "a1" not in result["recipients"]
        assert "a2" in result["recipients"]

    def test_broadcast_none_policy(self):
        self.broadcaster.set_policy(BroadcastPolicy.NONE)
        self.broadcaster.register_agent("a1")
        evt = self._make_event(source="a0")
        result = self.broadcaster.broadcast(evt)
        assert result["recipient_count"] == 0

    def test_broadcast_to_empty(self):
        evt = self._make_event()
        result = self.broadcaster.broadcast(evt)
        assert result["recipient_count"] == 0

    def test_broadcast_history(self):
        self.broadcaster.register_agent("a1")
        evt = self._make_event(source="a0")
        self.broadcaster.broadcast(evt)
        history = self.broadcaster.get_broadcast_history()
        assert len(history) == 1
        assert history[0]["policy"] == "all"

    def test_broadcast_history_limit(self):
        self.broadcaster.register_agent("a1")
        for i in range(10):
            self.broadcaster.broadcast(self._make_event(source="a0"))
        history = self.broadcaster.get_broadcast_history(limit=3)
        assert len(history) == 3

    def test_stats(self):
        self.broadcaster.register_agent("a1")
        self.broadcaster.register_agent("a2")
        self.broadcaster.broadcast(self._make_event(source="a0"))
        stats = self.broadcaster.get_stats()
        assert stats["total_broadcasts"] == 1
        assert stats["total_events"] == 1
        assert stats["registered_agents"] == 2

    def test_events_per_agent_tracking(self):
        self.broadcaster.register_agent("a1")
        self.broadcaster.register_agent("a2")
        self.broadcaster.broadcast(self._make_event(source="a0"))
        self.broadcaster.broadcast(self._make_event(source="a0"))
        stats = self.broadcaster.get_stats()
        assert stats["events_per_agent"]["a1"] == 2
        assert stats["events_per_agent"]["a2"] == 2

    def test_register_with_topics(self):
        self.broadcaster.register_agent("a1", topics=["ml", "nlp"])
        agents = self.broadcaster.get_registered_agents()
        assert agents["a1"]["topics"] == ["ml", "nlp"]

    def test_thread_safety(self):
        errors = []

        def register_many(start):
            try:
                for i in range(20):
                    self.broadcaster.register_agent(f"thread-{start}-{i}")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=register_many, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        agents = self.broadcaster.get_registered_agents()
        assert len(agents) == 80

    def test_broadcast_returns_broadcast_id(self):
        evt = self._make_event()
        result = self.broadcaster.broadcast(evt)
        assert "broadcast_id" in result
        assert isinstance(result["broadcast_id"], str)


class TestMemoryBroadcasterPolicies:
    """Tests for specific broadcast policy filtering."""

    def setup_method(self):
        self.broadcaster = MemoryBroadcaster()

    def _make_event(self, source="src", ns="ns1", topics=None):
        return SharedMemoryEvent(
            event_id=str(uuid.uuid4()),
            source_agent_id=source,
            target_namespace=ns,
            memory_key="k",
            memory_value="v",
            topics=topics or [],
        )

    def test_namespace_policy_match(self):
        self.broadcaster.set_policy(BroadcastPolicy.NAMESPACE)
        self.broadcaster.register_agent("a1", namespaces=["ns1"])
        self.broadcaster.register_agent("a2", namespaces=["ns2"])
        result = self.broadcaster.broadcast(self._make_event(ns="ns1"))
        assert "a1" in result["recipients"]
        assert "a2" not in result["recipients"]

    def test_namespace_policy_no_match(self):
        self.broadcaster.set_policy(BroadcastPolicy.NAMESPACE)
        self.broadcaster.register_agent("a1", namespaces=["ns-other"])
        result = self.broadcaster.broadcast(self._make_event(ns="ns1"))
        assert result["recipient_count"] == 0

    def test_topic_policy_match(self):
        self.broadcaster.set_policy(BroadcastPolicy.TOPIC)
        self.broadcaster.register_agent("a1", topics=["ml"])
        self.broadcaster.register_agent("a2", topics=["web"])
        result = self.broadcaster.broadcast(self._make_event(topics=["ml"]))
        assert "a1" in result["recipients"]
        assert "a2" not in result["recipients"]

    def test_topic_policy_no_topics(self):
        self.broadcaster.set_policy(BroadcastPolicy.TOPIC)
        self.broadcaster.register_agent("a1", topics=["ml"])
        result = self.broadcaster.broadcast(self._make_event(topics=[]))
        assert result["recipient_count"] == 0

    def test_topic_policy_agent_no_topics(self):
        self.broadcaster.set_policy(BroadcastPolicy.TOPIC)
        self.broadcaster.register_agent("a1")  # no topics
        result = self.broadcaster.broadcast(self._make_event(topics=["ml"]))
        assert result["recipient_count"] == 0

    def test_namespace_policy_empty_namespaces(self):
        self.broadcaster.set_policy(BroadcastPolicy.NAMESPACE)
        self.broadcaster.register_agent("a1")  # no namespaces
        result = self.broadcaster.broadcast(self._make_event(ns="ns1"))
        assert result["recipient_count"] == 0


# ======================================================================
# Watcher Tests
# ======================================================================


class TestMemoryWatcher:
    """Tests for MemoryWatcher."""

    def setup_method(self):
        self.watcher = MemoryWatcher()

    def _make_event(self, source="agent-a", ns="ns1", topics=None):
        return SharedMemoryEvent(
            event_id=str(uuid.uuid4()),
            source_agent_id=source,
            target_namespace=ns,
            memory_key="k",
            memory_value="v",
            topics=topics or [],
        )

    def _make_sub(self, subscriber="s1", filter_type=SubscriptionFilter.ALL,
                  filter_value=""):
        return MemorySubscription(
            subscriber_id=subscriber,
            filter_type=filter_type,
            filter_value=filter_value,
        )

    def test_subscribe_returns_id(self):
        sub_id = self.watcher.subscribe(self._make_sub())
        assert isinstance(sub_id, str)
        assert len(sub_id) > 0

    def test_subscribe_with_callback_id(self):
        sub = self._make_sub()
        sub.callback_id = "my-cb"
        sub_id = self.watcher.subscribe(sub)
        assert sub_id == "my-cb"

    def test_unsubscribe_existing(self):
        sub_id = self.watcher.subscribe(self._make_sub())
        assert self.watcher.unsubscribe(sub_id) is True

    def test_unsubscribe_nonexistent(self):
        assert self.watcher.unsubscribe("ghost") is False

    def test_notify_all_filter(self):
        self.watcher.subscribe(self._make_sub())
        count = self.watcher.notify(self._make_event())
        assert count == 1

    def test_notify_multiple_subscribers(self):
        self.watcher.subscribe(self._make_sub("s1"))
        self.watcher.subscribe(self._make_sub("s2"))
        count = self.watcher.notify(self._make_event())
        assert count == 2

    def test_notify_inactive_subscription(self):
        sub = self._make_sub()
        sub.active = False
        self.watcher.subscribe(sub)
        count = self.watcher.notify(self._make_event())
        assert count == 0

    def test_get_notifications(self):
        self.watcher.subscribe(self._make_sub("s1"))
        self.watcher.notify(self._make_event())
        notifs = self.watcher.get_notifications("s1")
        assert len(notifs) == 1
        assert "event" in notifs[0]

    def test_get_notifications_empty(self):
        notifs = self.watcher.get_notifications("nobody")
        assert notifs == []

    def test_get_notifications_limit(self):
        self.watcher.subscribe(self._make_sub("s1"))
        for _ in range(10):
            self.watcher.notify(self._make_event())
        notifs = self.watcher.get_notifications("s1", limit=3)
        assert len(notifs) == 3

    def test_clear_notifications(self):
        self.watcher.subscribe(self._make_sub("s1"))
        self.watcher.notify(self._make_event())
        cleared = self.watcher.clear_notifications("s1")
        assert cleared == 1
        assert self.watcher.get_notifications("s1") == []

    def test_clear_notifications_empty(self):
        cleared = self.watcher.clear_notifications("nobody")
        assert cleared == 0

    def test_get_active_subscriptions(self):
        self.watcher.subscribe(self._make_sub("s1"))
        self.watcher.subscribe(self._make_sub("s2"))
        subs = self.watcher.get_active_subscriptions()
        assert len(subs) == 2

    def test_get_active_subscriptions_filtered(self):
        self.watcher.subscribe(self._make_sub("s1"))
        self.watcher.subscribe(self._make_sub("s2"))
        subs = self.watcher.get_active_subscriptions("s1")
        assert len(subs) == 1
        assert subs[0]["subscriber_id"] == "s1"

    def test_stats(self):
        self.watcher.subscribe(self._make_sub("s1"))
        self.watcher.notify(self._make_event())
        stats = self.watcher.get_stats()
        assert stats["total_subscriptions"] == 1
        assert stats["total_notifications"] == 1

    def test_thread_safety(self):
        errors = []

        def subscribe_many(prefix):
            try:
                for i in range(20):
                    self.watcher.subscribe(self._make_sub(f"{prefix}-{i}"))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=subscribe_many, args=(f"t{t}",))
                   for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        subs = self.watcher.get_active_subscriptions()
        assert len(subs) == 80


class TestMemoryWatcherFilters:
    """Tests for MemoryWatcher filter matching."""

    def setup_method(self):
        self.watcher = MemoryWatcher()

    def _make_event(self, source="agent-a", ns="ns1", topics=None):
        return SharedMemoryEvent(
            event_id=str(uuid.uuid4()),
            source_agent_id=source,
            target_namespace=ns,
            memory_key="k",
            memory_value="v",
            topics=topics or [],
        )

    def test_by_namespace_match(self):
        sub = MemorySubscription(
            subscriber_id="s1",
            filter_type=SubscriptionFilter.BY_NAMESPACE,
            filter_value="ns1",
        )
        self.watcher.subscribe(sub)
        count = self.watcher.notify(self._make_event(ns="ns1"))
        assert count == 1

    def test_by_namespace_no_match(self):
        sub = MemorySubscription(
            subscriber_id="s1",
            filter_type=SubscriptionFilter.BY_NAMESPACE,
            filter_value="ns-other",
        )
        self.watcher.subscribe(sub)
        count = self.watcher.notify(self._make_event(ns="ns1"))
        assert count == 0

    def test_by_topic_match(self):
        sub = MemorySubscription(
            subscriber_id="s1",
            filter_type=SubscriptionFilter.BY_TOPIC,
            filter_value="ml",
        )
        self.watcher.subscribe(sub)
        count = self.watcher.notify(self._make_event(topics=["ml", "nlp"]))
        assert count == 1

    def test_by_topic_no_match(self):
        sub = MemorySubscription(
            subscriber_id="s1",
            filter_type=SubscriptionFilter.BY_TOPIC,
            filter_value="web",
        )
        self.watcher.subscribe(sub)
        count = self.watcher.notify(self._make_event(topics=["ml"]))
        assert count == 0

    def test_by_agent_match(self):
        sub = MemorySubscription(
            subscriber_id="s1",
            filter_type=SubscriptionFilter.BY_AGENT,
            filter_value="agent-a",
        )
        self.watcher.subscribe(sub)
        count = self.watcher.notify(self._make_event(source="agent-a"))
        assert count == 1

    def test_by_agent_no_match(self):
        sub = MemorySubscription(
            subscriber_id="s1",
            filter_type=SubscriptionFilter.BY_AGENT,
            filter_value="agent-b",
        )
        self.watcher.subscribe(sub)
        count = self.watcher.notify(self._make_event(source="agent-a"))
        assert count == 0


# ======================================================================
# TeamDNASync Tests
# ======================================================================


class TestTeamDNASync:
    """Tests for TeamDNASync."""

    def setup_method(self):
        self.sync = TeamDNASync("team-alpha")

    def test_team_id(self):
        assert self.sync.team_id == "team-alpha"

    def test_register_member(self):
        self.sync.register_member("a1", {"expertise": {"python": 0.9}})
        dna = self.sync.get_member_dna("a1")
        assert dna is not None
        assert dna["expertise"]["python"] == 0.9

    def test_register_member_no_snapshot(self):
        self.sync.register_member("a1")
        dna = self.sync.get_member_dna("a1")
        assert dna == {}

    def test_unregister_member(self):
        self.sync.register_member("a1")
        self.sync.unregister_member("a1")
        assert self.sync.get_member_dna("a1") is None

    def test_update_member_dna(self):
        self.sync.register_member("a1", {"expertise": {"python": 0.5}})
        self.sync.update_member_dna("a1", {"expertise": {"python": 0.9}})
        dna = self.sync.get_member_dna("a1")
        assert dna["expertise"]["python"] == 0.9

    def test_update_nonexistent_creates(self):
        self.sync.update_member_dna("new-agent", {"expertise": {"go": 0.8}})
        dna = self.sync.get_member_dna("new-agent")
        assert dna["expertise"]["go"] == 0.8

    def test_aggregate_team_dna_empty(self):
        profile = self.sync.aggregate_team_dna()
        assert profile.member_count == 0
        assert profile.aggregated_expertise == {}

    def test_aggregate_team_dna_single(self):
        self.sync.register_member("a1", {"expertise": {"python": 0.8}})
        profile = self.sync.aggregate_team_dna()
        assert profile.member_count == 1
        assert profile.aggregated_expertise["python"] == 0.8

    def test_aggregate_team_dna_multiple(self):
        self.sync.register_member("a1", {"expertise": {"python": 0.8, "rust": 0.6}})
        self.sync.register_member("a2", {"expertise": {"python": 0.6, "go": 0.9}})
        profile = self.sync.aggregate_team_dna()
        assert profile.member_count == 2
        assert profile.aggregated_expertise["python"] == 0.7
        assert "rust" in profile.aggregated_expertise
        assert "go" in profile.aggregated_expertise

    def test_get_team_profile(self):
        self.sync.register_member("a1", {"expertise": {"python": 0.9}})
        profile = self.sync.get_team_profile()
        assert profile["team_id"] == "team-alpha"
        assert profile["member_count"] == 1

    def test_compute_diversity_empty(self):
        score = self.sync.compute_diversity_score()
        assert score == 0.0

    def test_compute_diversity_single(self):
        self.sync.register_member("a1", {"expertise": {"python": 0.9}})
        score = self.sync.compute_diversity_score()
        assert score == 0.0

    def test_compute_diversity_diverse_team(self):
        self.sync.register_member("a1", {"expertise": {"python": 0.9}})
        self.sync.register_member("a2", {"expertise": {"rust": 0.8}})
        score = self.sync.compute_diversity_score()
        assert score > 0.5  # very different expertise

    def test_compute_diversity_identical_team(self):
        self.sync.register_member("a1", {"expertise": {"python": 0.9}})
        self.sync.register_member("a2", {"expertise": {"python": 0.8}})
        score = self.sync.compute_diversity_score()
        assert score == 0.0  # same topic

    def test_find_expertise_gaps(self):
        self.sync.register_member("a1", {"expertise": {"python": 0.9, "rust": 0.1}})
        self.sync.register_member("a2", {"expertise": {"python": 0.8, "rust": 0.2}})
        gaps = self.sync.find_expertise_gaps()
        assert "rust" in gaps
        assert "python" not in gaps

    def test_find_common_strengths(self):
        self.sync.register_member("a1", {"expertise": {"python": 0.9, "rust": 0.1}})
        self.sync.register_member("a2", {"expertise": {"python": 0.8, "rust": 0.2}})
        strengths = self.sync.find_common_strengths()
        assert "python" in strengths
        assert "rust" not in strengths

    def test_find_common_preferences(self):
        self.sync.register_member("a1", {
            "expertise": {}, "preferences": {"theme": "dark", "lang": "en"}
        })
        self.sync.register_member("a2", {
            "expertise": {}, "preferences": {"theme": "dark", "lang": "fr"}
        })
        profile = self.sync.aggregate_team_dna()
        assert profile.common_preferences.get("theme") == "dark"
        assert "lang" not in profile.common_preferences

    def test_get_member_ids(self):
        self.sync.register_member("a1")
        self.sync.register_member("a2")
        ids = self.sync.get_member_ids()
        assert set(ids) == {"a1", "a2"}

    def test_thread_safety(self):
        errors = []

        def register_many(prefix):
            try:
                for i in range(20):
                    self.sync.register_member(
                        f"{prefix}-{i}",
                        {"expertise": {f"topic-{prefix}": 0.5}},
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=register_many, args=(f"t{t}",))
                   for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(self.sync.get_member_ids()) == 80


# ======================================================================
# Coordinator Tests
# ======================================================================


class TestMemoryCoordinator:
    """Tests for MemoryCoordinator."""

    def setup_method(self):
        self.coord = MemoryCoordinator()

    def test_default_broadcaster_watcher(self):
        assert self.coord.broadcaster is not None
        assert self.coord.watcher is not None

    def test_custom_broadcaster_watcher(self):
        b = MemoryBroadcaster(BroadcastPolicy.NONE)
        w = MemoryWatcher()
        coord = MemoryCoordinator(broadcaster=b, watcher=w)
        assert coord.broadcaster is b
        assert coord.watcher is w

    def test_register_team(self):
        self.coord.register_team("team1", ["a1", "a2"])
        status = self.coord.get_team_status("team1")
        assert status["agent_count"] == 2
        assert set(status["agents"]) == {"a1", "a2"}

    def test_share_memory(self):
        self.coord.register_team("team1", ["a1", "a2"])
        result = self.coord.share_memory("a1", "ns1", "key1", "value1")
        assert result["stored"] is True
        assert "event_id" in result

    def test_share_memory_with_topics(self):
        self.coord.register_team("team1", ["a1", "a2"])
        result = self.coord.share_memory(
            "a1", "ns1", "key1", "value1", topics=["ml"]
        )
        assert result["stored"] is True

    def test_query_team_memories(self):
        self.coord.register_team("team1", ["a1", "a2"])
        self.coord.share_memory("a1", "ns1", "k1", "v1")
        self.coord.share_memory("a2", "ns1", "k2", "v2")
        view = self.coord.query_team_memories("team1")
        assert view.total_memories == 2

    def test_query_team_memories_by_namespace(self):
        self.coord.register_team("team1", ["a1", "a2"])
        self.coord.share_memory("a1", "ns1", "k1", "v1")
        self.coord.share_memory("a1", "ns2", "k2", "v2")
        view = self.coord.query_team_memories("team1", namespace="ns1")
        assert view.total_memories == 1

    def test_query_team_memories_by_topic(self):
        self.coord.register_team("team1", ["a1"])
        self.coord.share_memory("a1", "ns1", "k1", "v1", topics=["ml"])
        self.coord.share_memory("a1", "ns1", "k2", "v2", topics=["web"])
        view = self.coord.query_team_memories("team1", topic="ml")
        assert view.total_memories == 1

    def test_query_nonexistent_team(self):
        view = self.coord.query_team_memories("ghost")
        assert view.total_memories == 0

    def test_check_coherence_no_conflicts(self):
        self.coord.register_team("team1", ["a1", "a2"])
        self.coord.share_memory("a1", "ns1", "k1", "v1")
        self.coord.share_memory("a2", "ns1", "k2", "v2")
        report = self.coord.check_coherence("team1")
        assert report.conflicts_found == 0
        assert report.total_checked == 2

    def test_check_coherence_with_conflicts(self):
        self.coord.register_team("team1", ["a1", "a2"])
        self.coord.share_memory("a1", "ns1", "k1", "value-A")
        self.coord.share_memory("a2", "ns1", "k1", "value-B")
        report = self.coord.check_coherence("team1")
        assert report.conflicts_found == 1

    def test_get_memory_timeline(self):
        self.coord.register_team("team1", ["a1", "a2"])
        self.coord.share_memory("a1", "ns1", "k1", "v1")
        self.coord.share_memory("a2", "ns1", "k2", "v2")
        timeline = self.coord.get_memory_timeline("team1")
        assert len(timeline) == 2
        assert timeline[0]["timestamp"] <= timeline[1]["timestamp"]

    def test_get_memory_timeline_limit(self):
        self.coord.register_team("team1", ["a1"])
        for i in range(10):
            self.coord.share_memory("a1", "ns1", f"k{i}", f"v{i}")
        timeline = self.coord.get_memory_timeline("team1", limit=3)
        assert len(timeline) == 3

    def test_get_team_status(self):
        self.coord.register_team("team1", ["a1", "a2"])
        self.coord.share_memory("a1", "ns1", "k1", "v1")
        status = self.coord.get_team_status("team1")
        assert status["total_memories"] == 1
        assert "broadcaster_stats" in status
        assert "watcher_stats" in status

    def test_get_team_status_nonexistent(self):
        status = self.coord.get_team_status("ghost")
        assert status["agent_count"] == 0

    def test_share_memory_broadcasts(self):
        self.coord.register_team("team1", ["a1", "a2"])
        result = self.coord.share_memory("a1", "ns1", "k", "v")
        assert result["broadcast"]["recipient_count"] == 1  # a2

    def test_coordinator_thread_safety(self):
        self.coord.register_team("team1", ["a1", "a2", "a3"])
        errors = []

        def share_many(agent_id):
            try:
                for i in range(10):
                    self.coord.share_memory(agent_id, "ns1", f"k-{agent_id}-{i}", i)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=share_many, args=(f"a{t}",))
                   for t in range(1, 4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        view = self.coord.query_team_memories("team1")
        assert view.total_memories == 30


class TestConflictResolution:
    """Tests for conflict resolution strategies."""

    def setup_method(self):
        self.coord = MemoryCoordinator()
        self.coord.register_team("team1", ["a1", "a2"])

    def _create_conflict(self):
        self.coord.share_memory("a1", "ns1", "k1", "value-A", confidence=0.7)
        time.sleep(0.01)
        self.coord.share_memory("a2", "ns1", "k1", "value-B", confidence=0.9)
        report = self.coord.check_coherence("team1")
        assert report.conflicts_found == 1
        return report.details[0]

    def test_latest_wins(self):
        conflict = self._create_conflict()
        result = self.coord.resolve_conflict(conflict, ConflictStrategy.LATEST_WINS)
        assert result["resolved"] is True
        assert result["strategy"] == "latest_wins"
        assert result["winner"]["value"] == "value-B"

    def test_highest_confidence(self):
        conflict = self._create_conflict()
        result = self.coord.resolve_conflict(
            conflict, ConflictStrategy.HIGHEST_CONFIDENCE
        )
        assert result["resolved"] is True
        assert result["winner"]["confidence"] == 0.9

    def test_manual_not_resolved(self):
        conflict = self._create_conflict()
        result = self.coord.resolve_conflict(conflict, ConflictStrategy.MANUAL)
        assert result["resolved"] is False
        assert "manual" in result["reason"]

    def test_merge_strategy(self):
        conflict = self._create_conflict()
        result = self.coord.resolve_conflict(conflict, ConflictStrategy.MERGE)
        assert result["resolved"] is True
        assert result["strategy"] == "merge"
        assert set(result["merged_value"]) == {"value-A", "value-B"}

    def test_resolve_empty_conflict(self):
        result = self.coord.resolve_conflict(
            {"key": "k", "entries": []}, ConflictStrategy.LATEST_WINS
        )
        assert result["resolved"] is False

    def test_conflict_detection_same_value(self):
        """Same key, same value = no conflict."""
        self.coord.share_memory("a1", "ns1", "k1", "same")
        self.coord.share_memory("a2", "ns1", "k1", "same")
        report = self.coord.check_coherence("team1")
        assert report.conflicts_found == 0


# ======================================================================
# Integration Tests
# ======================================================================


class TestSharingIntegration:
    """Integration tests combining multiple sharing components."""

    def test_full_workflow(self):
        """End-to-end: register team, subscribe, share, query, check coherence."""
        coord = MemoryCoordinator()
        coord.register_team("team1", ["a1", "a2", "a3"])

        sub = MemorySubscription(
            subscriber_id="a2",
            filter_type=SubscriptionFilter.ALL,
        )
        coord.watcher.subscribe(sub)

        coord.share_memory("a1", "ns1", "finding", "result-A", topics=["ml"])
        coord.share_memory("a3", "ns1", "finding", "result-B", topics=["ml"])

        notifs = coord.watcher.get_notifications("a2")
        assert len(notifs) == 2

        view = coord.query_team_memories("team1", topic="ml")
        assert view.total_memories == 2

        report = coord.check_coherence("team1")
        assert report.conflicts_found == 1

    def test_broadcaster_watcher_integration(self):
        """Broadcaster and watcher work together through coordinator."""
        broadcaster = MemoryBroadcaster(BroadcastPolicy.TOPIC)
        watcher = MemoryWatcher()
        coord = MemoryCoordinator(broadcaster=broadcaster, watcher=watcher)

        coord.register_team("t1", ["a1", "a2"])
        broadcaster.register_agent("a1", topics=["ml"])
        broadcaster.register_agent("a2", topics=["web"])

        result = coord.share_memory("a1", "ns1", "k", "v", topics=["ml"])
        # a2 not interested in "ml" topic
        assert "a2" not in result["broadcast"]["recipients"]

    def test_team_dna_with_coordinator(self):
        """TeamDNASync and coordinator can work together."""
        coord = MemoryCoordinator()
        dna_sync = TeamDNASync("team1")

        coord.register_team("team1", ["a1", "a2"])
        dna_sync.register_member("a1", {"expertise": {"python": 0.9}})
        dna_sync.register_member("a2", {"expertise": {"rust": 0.8}})

        profile = dna_sync.aggregate_team_dna()
        assert profile.member_count == 2
        assert profile.diversity_score > 0

        coord.share_memory("a1", "ns1", "k1", "v1")
        view = coord.query_team_memories("team1")
        assert view.total_memories == 1

    def test_imports_from_package(self):
        """Verify all public symbols are importable from the package."""
        from memoria.sharing import (
            BroadcastPolicy,
            CoherenceReport,
            ConflictStrategy,
            MemoryBroadcaster,
            MemoryCoordinator,
            MemorySubscription,
            MemoryWatcher,
            SharedMemoryEvent,
            SubscriptionFilter,
            TeamDNAProfile,
            TeamDNASync,
            TeamMemoryView,
        )
        assert BroadcastPolicy is not None
        assert MemoryCoordinator is not None
