"""Tests for the Memoria Federation Protocol module."""

import time
from unittest.mock import MagicMock

import pytest

from memoria.federation.conflict import ConflictResolver, MemoryVersion, VectorClock
from memoria.federation.protocol import FederationMessage, FederationPeer, FederationProtocol
from memoria.federation.sync import SyncEngine, SyncResult
from memoria.federation.trust import TRUST_LEVELS, TrustEntry, TrustRegistry

# ── VectorClock Tests ─────────────────────────────────────

class TestVectorClock:

    def test_increment(self):
        vc = VectorClock()
        vc.increment("node-a")
        assert vc.clocks["node-a"] == 1
        vc.increment("node-a")
        assert vc.clocks["node-a"] == 2

    def test_merge(self):
        vc1 = VectorClock(clocks={"a": 3, "b": 1})
        vc2 = VectorClock(clocks={"a": 1, "b": 5, "c": 2})
        merged = vc1.merge(vc2)
        assert merged.clocks == {"a": 3, "b": 5, "c": 2}

    def test_dominates(self):
        vc1 = VectorClock(clocks={"a": 3, "b": 2})
        vc2 = VectorClock(clocks={"a": 1, "b": 1})
        assert vc1 > vc2
        assert not vc2 > vc1

    def test_concurrent(self):
        vc1 = VectorClock(clocks={"a": 3, "b": 1})
        vc2 = VectorClock(clocks={"a": 1, "b": 3})
        assert vc1.is_concurrent(vc2)
        assert not vc1 > vc2
        assert not vc2 > vc1

    def test_equal(self):
        vc1 = VectorClock(clocks={"a": 1, "b": 2})
        vc2 = VectorClock(clocks={"a": 1, "b": 2})
        assert vc1 == vc2
        assert not vc1.is_concurrent(vc2)

    def test_empty_gt(self):
        vc1 = VectorClock(clocks={"a": 1})
        vc2 = VectorClock()
        assert vc1 > vc2

    def test_to_from_dict(self):
        vc = VectorClock(clocks={"a": 5})
        d = vc.to_dict()
        vc2 = VectorClock.from_dict(d)
        assert vc == vc2


# ── ConflictResolver Tests ────────────────────────────────

class TestConflictResolver:

    def test_local_dominates(self):
        resolver = ConflictResolver()
        local = MemoryVersion("m1", "local content", vector_clock=VectorClock(clocks={"a": 3}))
        remote = MemoryVersion("m1", "remote content", vector_clock=VectorClock(clocks={"a": 1}))
        result = resolver.resolve(local, remote)
        assert result.content == "local content"

    def test_remote_dominates(self):
        resolver = ConflictResolver()
        local = MemoryVersion("m1", "local", vector_clock=VectorClock(clocks={"a": 1}))
        remote = MemoryVersion("m1", "remote", vector_clock=VectorClock(clocks={"a": 5}))
        result = resolver.resolve(local, remote)
        assert result.content == "remote"

    def test_identical_clocks(self):
        resolver = ConflictResolver()
        local = MemoryVersion("m1", "local", vector_clock=VectorClock(clocks={"a": 1}))
        remote = MemoryVersion("m1", "remote", vector_clock=VectorClock(clocks={"a": 1}))
        result = resolver.resolve(local, remote)
        assert result.content == "local"  # identical → keep local

    def test_concurrent_lww_importance(self):
        resolver = ConflictResolver(strategy="lww")
        local = MemoryVersion("m1", "local", importance=0.9,
                              vector_clock=VectorClock(clocks={"a": 3, "b": 1}))
        remote = MemoryVersion("m1", "remote", importance=0.3,
                               vector_clock=VectorClock(clocks={"a": 1, "b": 3}))
        result = resolver.resolve(local, remote)
        assert result.content == "local"

    def test_concurrent_lww_timestamp(self):
        resolver = ConflictResolver(strategy="lww")
        local = MemoryVersion("m1", "local", importance=0.5,
                              updated_at=100.0,
                              vector_clock=VectorClock(clocks={"a": 2, "b": 1}))
        remote = MemoryVersion("m1", "remote", importance=0.5,
                               updated_at=200.0,
                               vector_clock=VectorClock(clocks={"a": 1, "b": 2}))
        result = resolver.resolve(local, remote)
        assert result.content == "remote"

    def test_concurrent_local_first(self):
        resolver = ConflictResolver(strategy="local_first")
        local = MemoryVersion("m1", "local", vector_clock=VectorClock(clocks={"a": 2, "b": 1}))
        remote = MemoryVersion("m1", "remote", vector_clock=VectorClock(clocks={"a": 1, "b": 2}))
        result = resolver.resolve(local, remote)
        assert result.content == "local"

    def test_concurrent_remote_first(self):
        resolver = ConflictResolver(strategy="remote_first")
        local = MemoryVersion("m1", "local", vector_clock=VectorClock(clocks={"a": 2, "b": 1}))
        remote = MemoryVersion("m1", "remote", vector_clock=VectorClock(clocks={"a": 1, "b": 2}))
        result = resolver.resolve(local, remote)
        assert result.content == "remote"

    def test_concurrent_merge(self):
        resolver = ConflictResolver(strategy="merge")
        local = MemoryVersion("m1", "local", importance=0.8,
                              metadata={"source": "A"},
                              vector_clock=VectorClock(clocks={"a": 2, "b": 1}))
        remote = MemoryVersion("m1", "remote", importance=0.6,
                               metadata={"tag": "important"},
                               vector_clock=VectorClock(clocks={"a": 1, "b": 2}))
        result = resolver.resolve(local, remote)
        assert result.importance == 0.8
        assert result.metadata["source"] == "A"
        assert result.metadata["tag"] == "important"

    def test_resolution_log(self):
        resolver = ConflictResolver()
        local = MemoryVersion("m1", "a", vector_clock=VectorClock(clocks={"a": 2}))
        remote = MemoryVersion("m1", "b", vector_clock=VectorClock(clocks={"a": 1}))
        resolver.resolve(local, remote)
        log = resolver.get_resolution_log()
        assert len(log) == 1
        assert log[0]["reason"] == "local_dominates"

    def test_clear_log(self):
        resolver = ConflictResolver()
        local = MemoryVersion("m1", "a", vector_clock=VectorClock(clocks={"a": 2}))
        remote = MemoryVersion("m1", "b", vector_clock=VectorClock(clocks={"a": 1}))
        resolver.resolve(local, remote)
        resolver.clear_log()
        assert len(resolver.get_resolution_log()) == 0


# ── MemoryVersion Tests ──────────────────────────────────

class TestMemoryVersion:

    def test_to_from_dict(self):
        mv = MemoryVersion("m1", "hello", namespace="work", importance=0.9)
        mv.vector_clock.increment("node-a")
        d = mv.to_dict()
        mv2 = MemoryVersion.from_dict(d)
        assert mv2.memory_id == "m1"
        assert mv2.content == "hello"
        assert mv2.vector_clock.clocks == {"node-a": 1}


# ── FederationProtocol Tests ─────────────────────────────

class TestFederationProtocol:

    def test_init(self):
        fp = FederationProtocol(instance_id="test-node")
        assert fp.instance_id == "test-node"
        assert len(fp.peers) == 0

    def test_connect(self):
        fp = FederationProtocol()
        peer = fp.connect("https://peer.example.com", instance_id="peer-1")
        assert peer.instance_id == "peer-1"
        assert peer.status == "connected"
        assert len(fp.peers) == 1

    def test_connect_auto_id(self):
        fp = FederationProtocol()
        peer = fp.connect("https://peer.example.com")
        assert peer.instance_id  # auto-generated
        assert peer.status == "connected"

    def test_reconnect(self):
        fp = FederationProtocol()
        fp.connect("https://peer.example.com", instance_id="peer-1")
        fp.disconnect("peer-1")
        peer = fp.connect("https://peer.example.com", instance_id="peer-1")
        assert peer.status == "connected"
        assert len(fp.peers) == 1  # same peer, not duplicated

    def test_disconnect(self):
        fp = FederationProtocol()
        fp.connect("https://peer.example.com", instance_id="peer-1")
        ok = fp.disconnect("peer-1")
        assert ok
        assert fp.peers["peer-1"].status == "disconnected"

    def test_disconnect_unknown(self):
        fp = FederationProtocol()
        assert not fp.disconnect("unknown")

    def test_remove_peer(self):
        fp = FederationProtocol()
        fp.connect("https://peer.example.com", instance_id="peer-1")
        ok = fp.remove_peer("peer-1")
        assert ok
        assert len(fp.peers) == 0

    def test_get_peer(self):
        fp = FederationProtocol()
        fp.connect("https://peer.example.com", instance_id="peer-1")
        peer = fp.get_peer("peer-1")
        assert peer is not None
        assert fp.get_peer("unknown") is None

    def test_list_peers(self):
        fp = FederationProtocol()
        fp.connect("https://a.com", instance_id="a")
        fp.connect("https://b.com", instance_id="b")
        peers = fp.list_peers()
        assert len(peers) == 2

    def test_send_message(self):
        fp = FederationProtocol()
        fp.connect("https://peer.com", instance_id="peer-1")
        msg = fp.send_message("peer-1", "heartbeat", {"ping": True})
        assert msg.message_type == "heartbeat"
        assert msg.source_instance == fp.instance_id

    def test_send_message_unknown_peer(self):
        fp = FederationProtocol()
        with pytest.raises(ValueError):
            fp.send_message("unknown", "heartbeat", {})

    def test_message_signature(self):
        msg = FederationMessage(
            source_instance="a", target_instance="b",
            message_type="sync", payload={"data": 1})
        sig = msg.compute_signature("secret123")
        assert sig
        assert msg.verify_signature("secret123")
        assert not msg.verify_signature("wrong")

    def test_receive_message(self):
        fp = FederationProtocol()
        msg_data = {
            "source_instance": "remote",
            "target_instance": fp.instance_id,
            "message_type": "heartbeat",
            "payload": {"ping": True},
        }
        msg = fp.receive_message(msg_data)
        assert msg.message_type == "heartbeat"

    def test_on_message_handler(self):
        fp = FederationProtocol()
        fp.connect("https://peer.com", instance_id="peer-1")
        received = []
        fp.on_message("test", lambda m: received.append(m))
        fp.send_message("peer-1", "test", {"hello": True})
        assert len(received) == 1

    def test_message_log(self):
        fp = FederationProtocol()
        fp.connect("https://peer.com", instance_id="peer-1")
        fp.send_message("peer-1", "heartbeat", {})
        log = fp.get_message_log()
        assert len(log) >= 2  # connect + heartbeat

    def test_status(self):
        fp = FederationProtocol()
        fp.connect("https://a.com", instance_id="a")
        fp.connect("https://b.com", instance_id="b")
        fp.disconnect("b")
        status = fp.status()
        assert status["total_peers"] == 2
        assert status["connected_peers"] == 1


# ── TrustRegistry Tests ──────────────────────────────────

class TestTrustRegistry:

    def test_add_trust(self):
        tr = TrustRegistry()
        entry = tr.add_trust("peer-1", "pubkey123")
        assert entry.instance_id == "peer-1"
        assert entry.trust_level == "standard"

    def test_invalid_trust_level(self):
        tr = TrustRegistry()
        with pytest.raises(ValueError):
            tr.add_trust("peer-1", "pubkey", trust_level="invalid")

    def test_is_trusted(self):
        tr = TrustRegistry()
        tr.add_trust("peer-1", "pubkey")
        assert tr.is_trusted("peer-1")
        assert not tr.is_trusted("unknown")

    def test_revoke_trust(self):
        tr = TrustRegistry()
        tr.add_trust("peer-1", "pubkey")
        ok = tr.revoke_trust("peer-1")
        assert ok
        assert not tr.is_trusted("peer-1")

    def test_revoke_unknown(self):
        tr = TrustRegistry()
        assert not tr.revoke_trust("unknown")

    def test_get_permissions(self):
        tr = TrustRegistry()
        tr.add_trust("peer-1", "pubkey", trust_level="standard")
        perms = tr.get_permissions("peer-1")
        assert perms["can_read"] is True
        assert perms["can_write"] is False

    def test_elevated_permissions(self):
        tr = TrustRegistry()
        tr.add_trust("peer-1", "pubkey", trust_level="elevated")
        perms = tr.get_permissions("peer-1")
        assert perms["can_write"] is True

    def test_untrusted_permissions(self):
        tr = TrustRegistry()
        perms = tr.get_permissions("unknown")
        assert perms["can_read"] is False

    def test_namespace_access(self):
        tr = TrustRegistry()
        tr.add_trust("peer-1", "pubkey", allowed_namespaces=["shared"])
        assert tr.can_access_namespace("peer-1", "shared")
        assert not tr.can_access_namespace("peer-1", "private")

    def test_namespace_access_all(self):
        tr = TrustRegistry()
        tr.add_trust("peer-1", "pubkey")  # no namespace restriction
        assert tr.can_access_namespace("peer-1", "anything")

    def test_shared_secret(self):
        tr = TrustRegistry()
        tr.set_shared_secret("peer-1", "mysecret")
        assert tr.get_shared_secret("peer-1") == "mysecret"

    def test_sign_verify(self):
        tr = TrustRegistry()
        tr.set_shared_secret("peer-1", "secret")
        sig = tr.sign_payload("peer-1", {"data": 42})
        assert tr.verify_payload("peer-1", {"data": 42}, sig)
        assert not tr.verify_payload("peer-1", {"data": 99}, sig)

    def test_sign_no_secret(self):
        tr = TrustRegistry()
        with pytest.raises(ValueError):
            tr.sign_payload("unknown", {"data": 1})

    def test_expired_trust(self):
        tr = TrustRegistry()
        tr.add_trust("peer-1", "pubkey", expires_at=time.time() - 100)
        assert not tr.is_trusted("peer-1")

    def test_cleanup_expired(self):
        tr = TrustRegistry()
        tr.add_trust("peer-1", "pubkey", expires_at=time.time() - 100)
        tr.add_trust("peer-2", "pubkey2")
        removed = tr.cleanup_expired()
        assert removed == 1

    def test_list_trusted(self):
        tr = TrustRegistry()
        tr.add_trust("peer-1", "pubkey")
        tr.add_trust("peer-2", "pubkey2")
        tr.revoke_trust("peer-2")
        trusted = tr.list_trusted()
        assert len(trusted) == 1

    def test_status(self):
        tr = TrustRegistry()
        tr.add_trust("a", "k1")
        tr.add_trust("b", "k2")
        tr.revoke_trust("b")
        status = tr.status()
        assert status["valid"] == 1
        assert status["revoked"] == 1


# ── SyncEngine Tests ──────────────────────────────────────

class TestSyncEngine:

    def test_add_local(self):
        engine = SyncEngine("node-a")
        mv = MemoryVersion("m1", "hello", namespace="general")
        engine.add_local(mv)
        result = engine.get_local("general")
        assert len(result) == 1
        assert result[0].vector_clock.clocks["node-a"] == 1

    def test_get_local_empty(self):
        engine = SyncEngine("node-a")
        assert engine.get_local("empty") == []

    def test_prepare_push(self):
        engine = SyncEngine("node-a")
        engine.add_local(MemoryVersion("m1", "hello"))
        engine.add_local(MemoryVersion("m2", "world"))
        pushed = engine.prepare_push("general")
        assert len(pushed) == 2

    def test_receive_pull_new(self):
        engine = SyncEngine("node-a")
        remote = [MemoryVersion("m1", "from-b", origin_instance="node-b").to_dict()]
        result = engine.receive_pull("general", remote, "node-b")
        assert result.memories_received == 1
        assert result.status == "completed"

    def test_receive_pull_conflict(self):
        engine = SyncEngine("node-a")
        engine.add_local(MemoryVersion("m1", "local-version"))
        remote = [MemoryVersion("m1", "remote-version",
                                vector_clock=VectorClock(clocks={"node-b": 5})).to_dict()]
        result = engine.receive_pull("general", remote, "node-b")
        assert result.conflicts_resolved == 1

    def test_bidirectional_sync(self):
        engine = SyncEngine("node-a")
        engine.add_local(MemoryVersion("m1", "local"))
        remote = [MemoryVersion("m2", "from-b").to_dict()]
        result, to_push = engine.sync_bidirectional("general", remote, "node-b")
        assert result.memories_received == 1
        assert len(to_push) == 2  # m1 + m2

    def test_sync_history(self):
        engine = SyncEngine("node-a")
        remote = [MemoryVersion("m1", "data").to_dict()]
        engine.receive_pull("general", remote, "node-b")
        history = engine.get_sync_history()
        assert len(history) == 1

    def test_namespace_stats(self):
        engine = SyncEngine("node-a")
        engine.add_local(MemoryVersion("m1", "hello"))
        stats = engine.get_namespace_stats("general")
        assert stats["memory_count"] == 1
        assert "node-a" in stats["origins"]

    def test_list_synced_namespaces(self):
        engine = SyncEngine("node-a")
        engine.add_local(MemoryVersion("m1", "a", namespace="ns1"))
        engine.add_local(MemoryVersion("m2", "b", namespace="ns2"))
        ns = engine.list_synced_namespaces()
        assert set(ns) == {"ns1", "ns2"}

    def test_status(self):
        engine = SyncEngine("node-a")
        engine.add_local(MemoryVersion("m1", "hello"))
        status = engine.status()
        assert status["instance_id"] == "node-a"
        assert status["total_memories"] == 1


# ── Memoria Integration Tests ─────────────────────────────

class TestMemoriaFederation:

    def _make_memoria(self, tmp_path):
        from memoria import Memoria
        return Memoria(project_dir=str(tmp_path))

    def test_federation_connect(self, tmp_path):
        m = self._make_memoria(tmp_path)
        result = m.federation_connect("https://peer.example.com",
                                       instance_id="peer-1",
                                       shared_namespaces=["shared"])
        assert result["instance_id"] == "peer-1"
        assert result["status"] == "connected"

    def test_federation_disconnect(self, tmp_path):
        m = self._make_memoria(tmp_path)
        m.federation_connect("https://peer.com", instance_id="peer-1")
        result = m.federation_disconnect("peer-1")
        assert result["status"] == "disconnected"

    def test_federation_disconnect_unknown(self, tmp_path):
        m = self._make_memoria(tmp_path)
        result = m.federation_disconnect("unknown")
        assert result["status"] == "not_found"

    def test_federation_status(self, tmp_path):
        m = self._make_memoria(tmp_path)
        status = m.federation_status()
        assert "protocol" in status
        assert "trust" in status
        assert "sync" in status

    def test_federation_list_peers(self, tmp_path):
        m = self._make_memoria(tmp_path)
        m.federation_connect("https://a.com", instance_id="a")
        peers = m.federation_list_peers()
        assert len(peers) == 1

    def test_federation_trust_add(self, tmp_path):
        m = self._make_memoria(tmp_path)
        result = m.federation_trust_add("peer-1", "pubkey123", "elevated")
        assert result["trust_level"] == "elevated"

    def test_federation_trust_revoke(self, tmp_path):
        m = self._make_memoria(tmp_path)
        m.federation_trust_add("peer-1", "pubkey123")
        result = m.federation_trust_revoke("peer-1")
        assert result["status"] == "revoked"

    def test_federation_sync_push(self, tmp_path):
        m = self._make_memoria(tmp_path)
        m.federation_connect("https://peer.com", instance_id="peer-1")
        result = m.federation_sync("peer-1", "general")
        assert result["direction"] == "push"

    def test_federation_sync_unknown_peer(self, tmp_path):
        m = self._make_memoria(tmp_path)
        result = m.federation_sync("unknown", "general")
        assert "error" in result
