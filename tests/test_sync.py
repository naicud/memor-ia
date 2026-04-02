"""Comprehensive tests for the MEMORIA sync module."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path

import pytest

from memoria.namespace.store import SharedMemoryStore
from memoria.sync.conflicts import (
    ConflictStrategy,
    SyncConflict,
    SyncConflictResolver,
)
from memoria.sync.federation import FederationManager
from memoria.sync.protocol import SyncProtocol, SyncResult
from memoria.sync.transport import FileTransport, InMemoryTransport, SyncTransport

# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture()
def store() -> SharedMemoryStore:
    return SharedMemoryStore()


@pytest.fixture()
def transport() -> InMemoryTransport:
    return InMemoryTransport()


@pytest.fixture()
def resolver() -> SyncConflictResolver:
    return SyncConflictResolver()


@pytest.fixture()
def protocol(store: SharedMemoryStore, transport: InMemoryTransport) -> SyncProtocol:
    return SyncProtocol(store, transport)


@pytest.fixture()
def federation(store: SharedMemoryStore) -> FederationManager:
    return FederationManager(instance_id="test-instance", local_store=store)


@pytest.fixture()
def file_transport_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ===================================================================
# 1. SyncConflictResolver
# ===================================================================


class TestSyncConflictResolver:
    def test_no_conflict_identical_content(self, resolver: SyncConflictResolver) -> None:
        local = {"id": "m1", "content": "hello", "updated_at": "2024-01-01T00:00:00"}
        remote = {"id": "m1", "content": "hello", "updated_at": "2024-01-02T00:00:00"}
        assert resolver.detect(local, remote) is None

    def test_detect_update_conflict(self, resolver: SyncConflictResolver) -> None:
        local = {"id": "m1", "content": "local text", "updated_at": "2024-01-01T10:00:00"}
        remote = {"id": "m1", "content": "remote text", "updated_at": "2024-01-01T12:00:00"}
        conflict = resolver.detect(local, remote)
        assert conflict is not None
        assert conflict.conflict_type == "update"
        assert conflict.memory_id == "m1"

    def test_detect_delete_conflict_local_deleted(self, resolver: SyncConflictResolver) -> None:
        local = {"id": "m1", "content": "x", "_deleted": True}
        remote = {"id": "m1", "content": "alive", "_deleted": False}
        conflict = resolver.detect(local, remote)
        assert conflict is not None
        assert conflict.conflict_type == "delete"

    def test_detect_delete_conflict_remote_deleted(self, resolver: SyncConflictResolver) -> None:
        local = {"id": "m1", "content": "alive"}
        remote = {"id": "m1", "content": "x", "_deleted": True}
        conflict = resolver.detect(local, remote)
        assert conflict is not None
        assert conflict.conflict_type == "delete"

    def test_detect_create_conflict(self, resolver: SyncConflictResolver) -> None:
        local = {"id": "m1", "content": "local ver"}
        remote = {"id": "m1", "content": "remote ver"}
        conflict = resolver.detect(local, remote)
        assert conflict is not None
        assert conflict.conflict_type == "create"

    def test_no_conflict_both_deleted(self, resolver: SyncConflictResolver) -> None:
        local = {"id": "m1", "content": "x", "_deleted": True}
        remote = {"id": "m1", "content": "x", "_deleted": True}
        assert resolver.detect(local, remote) is None

    def test_resolve_last_writer_wins_remote_newer(self, resolver: SyncConflictResolver) -> None:
        conflict = SyncConflict(
            memory_id="m1",
            local_version={"content": "old", "updated_at": "2024-01-01T00:00:00"},
            remote_version={"content": "new", "updated_at": "2024-01-02T00:00:00"},
            conflict_type="update",
        )
        res = resolver.resolve(conflict, ConflictStrategy.LAST_WRITER_WINS)
        assert res.winner == "remote"
        assert res.resolved_content["content"] == "new"
        assert res.strategy_used == "last_writer_wins"

    def test_resolve_last_writer_wins_local_newer(self, resolver: SyncConflictResolver) -> None:
        conflict = SyncConflict(
            memory_id="m1",
            local_version={"content": "newer", "updated_at": "2024-01-03T00:00:00"},
            remote_version={"content": "older", "updated_at": "2024-01-02T00:00:00"},
            conflict_type="update",
        )
        res = resolver.resolve(conflict, ConflictStrategy.LAST_WRITER_WINS)
        assert res.winner == "local"
        assert res.resolved_content["content"] == "newer"

    def test_resolve_local_wins(self, resolver: SyncConflictResolver) -> None:
        conflict = SyncConflict(
            memory_id="m1",
            local_version={"content": "local"},
            remote_version={"content": "remote"},
            conflict_type="update",
        )
        res = resolver.resolve(conflict, ConflictStrategy.LOCAL_WINS)
        assert res.winner == "local"
        assert res.resolved_content["content"] == "local"

    def test_resolve_remote_wins(self, resolver: SyncConflictResolver) -> None:
        conflict = SyncConflict(
            memory_id="m1",
            local_version={"content": "local"},
            remote_version={"content": "remote"},
            conflict_type="update",
        )
        res = resolver.resolve(conflict, ConflictStrategy.REMOTE_WINS)
        assert res.winner == "remote"
        assert res.resolved_content["content"] == "remote"

    def test_resolve_merge(self, resolver: SyncConflictResolver) -> None:
        conflict = SyncConflict(
            memory_id="m1",
            local_version={"content": "AAA"},
            remote_version={"content": "BBB"},
            conflict_type="update",
        )
        res = resolver.resolve(conflict, ConflictStrategy.MERGE)
        assert res.winner == "merged"
        assert "AAA" in res.resolved_content["content"]
        assert "BBB" in res.resolved_content["content"]
        assert "---" in res.resolved_content["content"]

    def test_resolve_manual(self, resolver: SyncConflictResolver) -> None:
        conflict = SyncConflict(
            memory_id="m1",
            local_version={"content": "L"},
            remote_version={"content": "R"},
            conflict_type="update",
        )
        res = resolver.resolve(conflict, ConflictStrategy.MANUAL)
        assert res.strategy_used == "manual"
        assert "local" in res.resolved_content
        assert "remote" in res.resolved_content

    def test_resolve_batch(self, resolver: SyncConflictResolver) -> None:
        conflicts = [
            SyncConflict("m1", {"content": "a"}, {"content": "b"}, "update"),
            SyncConflict("m2", {"content": "c"}, {"content": "d"}, "update"),
        ]
        resolutions = resolver.resolve_batch(conflicts)
        assert len(resolutions) == 2
        assert resolutions[0].memory_id == "m1"
        assert resolutions[1].memory_id == "m2"

    def test_conflict_log(self, resolver: SyncConflictResolver) -> None:
        resolver.detect(
            {"id": "m1", "content": "a", "updated_at": "2024-01-01"},
            {"id": "m1", "content": "b", "updated_at": "2024-01-02"},
        )
        resolver.detect(
            {"id": "m2", "content": "c", "updated_at": "2024-01-01"},
            {"id": "m2", "content": "d", "updated_at": "2024-01-02"},
        )
        log = resolver.conflict_log()
        assert len(log) == 2
        assert log[0].memory_id == "m1"

    def test_default_strategy_used(self) -> None:
        resolver = SyncConflictResolver(default_strategy=ConflictStrategy.REMOTE_WINS)
        conflict = SyncConflict("m1", {"content": "L"}, {"content": "R"}, "update")
        res = resolver.resolve(conflict)
        assert res.winner == "remote"


# ===================================================================
# 2. InMemoryTransport
# ===================================================================


class TestInMemoryTransport:
    def test_send_and_receive(self, transport: InMemoryTransport) -> None:
        data = [{"id": "m1", "content": "hello"}]
        result = transport.send(data)
        assert result["accepted"] == 1
        assert result["rejected"] == 0

        received = transport.receive()
        assert len(received) == 1
        assert received[0]["content"] == "hello"

    def test_send_with_namespace(self, transport: InMemoryTransport) -> None:
        transport.send([{"id": "m1", "content": "A"}], namespace="ns1")
        transport.send([{"id": "m2", "content": "B"}], namespace="ns2")
        assert len(transport.receive(namespace="ns1")) == 1
        assert len(transport.receive(namespace="ns2")) == 1
        assert transport.receive(namespace="ns1")[0]["content"] == "A"

    def test_receive_empty_namespace(self, transport: InMemoryTransport) -> None:
        assert transport.receive(namespace="nonexistent") == []

    def test_receive_with_since_filter(self, transport: InMemoryTransport) -> None:
        transport.send([
            {"id": "m1", "content": "old", "updated_at": "2024-01-01T00:00:00"},
            {"id": "m2", "content": "new", "updated_at": "2024-06-01T00:00:00"},
        ])
        recent = transport.receive(since="2024-03-01T00:00:00")
        assert len(recent) == 1
        assert recent[0]["id"] == "m2"

    def test_ping(self, transport: InMemoryTransport) -> None:
        assert transport.ping() is True

    def test_clear(self, transport: InMemoryTransport) -> None:
        transport.send([{"id": "m1", "content": "x"}])
        transport.clear()
        assert transport.receive() == []

    def test_send_overwrites_previous(self, transport: InMemoryTransport) -> None:
        transport.send([{"id": "m1", "content": "first"}])
        transport.send([{"id": "m2", "content": "second"}])
        received = transport.receive()
        assert len(received) == 1
        assert received[0]["id"] == "m2"


# ===================================================================
# 3. FileTransport
# ===================================================================


class TestFileTransport:
    def test_send_creates_file(self, file_transport_dir: str) -> None:
        ft = FileTransport(file_transport_dir)
        result = ft.send([{"id": "m1", "content": "hi"}])
        assert result["accepted"] == 1
        exports = ft.list_exports()
        assert len(exports) == 1

    def test_send_with_namespace(self, file_transport_dir: str) -> None:
        ft = FileTransport(file_transport_dir)
        ft.send([{"id": "m1"}], namespace="proj/alpha")
        exports = ft.list_exports(namespace="proj/alpha")
        assert len(exports) == 1
        assert "proj_alpha_export_" in exports[0].name

    def test_receive_reads_latest(self, file_transport_dir: str) -> None:
        ft = FileTransport(file_transport_dir)
        ft.send([{"id": "m1", "content": "first"}])
        time.sleep(1.1)  # ensure different timestamps
        ft.send([{"id": "m2", "content": "second"}])
        received = ft.receive()
        assert len(received) == 1
        assert received[0]["id"] == "m2"

    def test_receive_empty(self, file_transport_dir: str) -> None:
        ft = FileTransport(file_transport_dir)
        assert ft.receive(namespace="nothing") == []

    def test_receive_with_since(self, file_transport_dir: str) -> None:
        ft = FileTransport(file_transport_dir)
        ft.send([
            {"id": "m1", "updated_at": "2024-01-01"},
            {"id": "m2", "updated_at": "2024-06-01"},
        ])
        recent = ft.receive(since="2024-03-01")
        assert len(recent) == 1
        assert recent[0]["id"] == "m2"

    def test_ping(self, file_transport_dir: str) -> None:
        ft = FileTransport(file_transport_dir)
        assert ft.ping() is True

    def test_list_exports(self, file_transport_dir: str) -> None:
        ft = FileTransport(file_transport_dir)
        ft.send([{"id": "m1"}])
        time.sleep(1.1)
        ft.send([{"id": "m2"}])
        exports = ft.list_exports()
        assert len(exports) == 2

    def test_cleanup(self, file_transport_dir: str) -> None:
        ft = FileTransport(file_transport_dir)
        for i in range(7):
            ft.send([{"id": f"m{i}"}])
            time.sleep(0.05)
        # all files get same second-level timestamp, create manually
        d = Path(file_transport_dir)
        for f in d.glob("*.json"):
            f.unlink()
        for i in range(7):
            (d / f"all_export_2024010{i}T120000.json").write_text("[]")
        deleted = ft.cleanup(keep_latest=3)
        assert deleted == 4
        remaining = ft.list_exports()
        assert len(remaining) == 3

    def test_file_content_is_valid_json(self, file_transport_dir: str) -> None:
        ft = FileTransport(file_transport_dir)
        ft.send([{"id": "m1", "content": "hello world"}])
        exports = ft.list_exports()
        data = json.loads(exports[0].read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert data[0]["content"] == "hello world"


# ===================================================================
# 4. SyncProtocol
# ===================================================================


class TestSyncProtocol:
    def test_push_sends_memories(
        self, store: SharedMemoryStore, transport: InMemoryTransport,
    ) -> None:
        store.add("ns1", "memory A")
        proto = SyncProtocol(store, transport)
        result = proto.push()
        assert result.pushed == 1
        assert result.errors == []

    def test_push_namespace_filter(
        self, store: SharedMemoryStore, transport: InMemoryTransport,
    ) -> None:
        store.add("ns1", "A")
        store.add("ns2", "B")
        proto = SyncProtocol(store, transport)
        result = proto.push(namespace="ns1")
        assert result.pushed == 1

    def test_push_no_transport_returns_error(self, store: SharedMemoryStore) -> None:
        proto = SyncProtocol(store)
        result = proto.push()
        assert len(result.errors) == 1
        assert "no transport" in result.errors[0]

    def test_pull_imports_new_memories(
        self, store: SharedMemoryStore, transport: InMemoryTransport,
    ) -> None:
        transport.send([
            {"id": "remote-1", "content": "from remote", "namespace": "ns1"},
        ])
        proto = SyncProtocol(store, transport)
        result = proto.pull()
        assert result.pulled == 1

    def test_pull_detects_and_resolves_conflicts(
        self, store: SharedMemoryStore, transport: InMemoryTransport,
    ) -> None:
        mid = store.add("ns1", "local version")
        store.get(mid)
        transport.send([{
            "id": mid,
            "content": "remote version",
            "namespace": "ns1",
            "updated_at": "2099-01-01T00:00:00",
        }])
        proto = SyncProtocol(store, transport)
        result = proto.pull()
        assert result.conflicts == 1
        assert result.resolved == 1

    def test_pull_no_conflict_identical(
        self, store: SharedMemoryStore, transport: InMemoryTransport,
    ) -> None:
        mid = store.add("ns1", "same content")
        local_mem = store.get(mid)
        transport.send([{
            "id": mid,
            "content": "same content",
            "namespace": "ns1",
            "updated_at": local_mem["updated_at"],
        }])
        proto = SyncProtocol(store, transport)
        result = proto.pull()
        assert result.conflicts == 0
        assert result.pulled == 0

    def test_sync_bidirectional(
        self, store: SharedMemoryStore, transport: InMemoryTransport,
    ) -> None:
        store.add("ns1", "local data")
        proto = SyncProtocol(store, transport)
        result = proto.sync()
        assert result.pushed >= 1
        assert result.errors == []

    def test_sync_state_tracking(
        self, store: SharedMemoryStore, transport: InMemoryTransport,
    ) -> None:
        proto = SyncProtocol(store, transport)
        state = proto.get_state()
        assert state.sync_count == 0
        assert state.last_sync_at == ""

        store.add("ns1", "data")
        proto.push()
        state = proto.get_state()
        assert state.sync_count == 1
        assert state.last_sync_at != ""

    def test_reset_state(
        self, store: SharedMemoryStore, transport: InMemoryTransport,
    ) -> None:
        proto = SyncProtocol(store, transport)
        store.add("ns1", "data")
        proto.push()
        proto.reset_state()
        state = proto.get_state()
        assert state.sync_count == 0
        assert state.last_sync_at == ""

    def test_pending_changes(
        self, store: SharedMemoryStore, transport: InMemoryTransport,
    ) -> None:
        proto = SyncProtocol(store, transport)
        proto.record_change("m1", "ns1", "create")
        proto.record_change("m2", "ns2", "update")
        assert len(proto.get_pending_changes()) == 2
        assert len(proto.get_pending_changes(namespace="ns1")) == 1

    def test_push_clears_pending_changes(
        self, store: SharedMemoryStore, transport: InMemoryTransport,
    ) -> None:
        proto = SyncProtocol(store, transport)
        proto.record_change("m1", "ns1", "create")
        proto.push()
        assert len(proto.get_pending_changes()) == 0

    def test_push_clears_only_namespace_changes(
        self, store: SharedMemoryStore, transport: InMemoryTransport,
    ) -> None:
        store.add("ns1", "A")
        proto = SyncProtocol(store, transport)
        proto.record_change("m1", "ns1", "create")
        proto.record_change("m2", "ns2", "create")
        proto.push(namespace="ns1")
        remaining = proto.get_pending_changes()
        assert len(remaining) == 1
        assert remaining[0]["namespace"] == "ns2"


# ===================================================================
# 5. FederationManager
# ===================================================================


class TestFederationManager:
    def test_instance_id_default(self) -> None:
        fm = FederationManager()
        assert fm.instance_id  # non-empty uuid

    def test_instance_id_custom(self) -> None:
        fm = FederationManager(instance_id="my-node")
        assert fm.instance_id == "my-node"

    def test_register_peer(self, federation: FederationManager) -> None:
        t = InMemoryTransport()
        pid = federation.register_peer("peer-A", t, endpoint="http://a")
        assert pid
        assert federation.peer_count() == 1

    def test_remove_peer(self, federation: FederationManager) -> None:
        t = InMemoryTransport()
        pid = federation.register_peer("peer-A", t)
        assert federation.remove_peer(pid) is True
        assert federation.peer_count() == 0

    def test_remove_nonexistent_peer(self, federation: FederationManager) -> None:
        assert federation.remove_peer("nope") is False

    def test_list_peers(self, federation: FederationManager) -> None:
        t1 = InMemoryTransport()
        t2 = InMemoryTransport()
        federation.register_peer("A", t1)
        federation.register_peer("B", t2)
        peers = federation.list_peers()
        assert len(peers) == 2
        names = {p.name for p in peers}
        assert names == {"A", "B"}

    def test_get_peer(self, federation: FederationManager) -> None:
        t = InMemoryTransport()
        pid = federation.register_peer("peer-X", t, endpoint="ws://x")
        peer = federation.get_peer(pid)
        assert peer is not None
        assert peer.name == "peer-X"
        assert peer.endpoint == "ws://x"
        assert peer.status == "active"

    def test_get_peer_missing(self, federation: FederationManager) -> None:
        assert federation.get_peer("missing") is None

    def test_sync_with_peer(
        self, store: SharedMemoryStore, federation: FederationManager,
    ) -> None:
        store.add("ns1", "hello")
        t = InMemoryTransport()
        pid = federation.register_peer("peer-1", t)
        result = federation.sync_with_peer(pid)
        assert isinstance(result, SyncResult)
        assert result.pushed >= 1

    def test_sync_with_unknown_peer(self, federation: FederationManager) -> None:
        result = federation.sync_with_peer("no-such-peer")
        assert len(result.errors) == 1

    def test_sync_all(self, store: SharedMemoryStore) -> None:
        fm = FederationManager(local_store=store)
        store.add("ns1", "data")
        t1 = InMemoryTransport()
        t2 = InMemoryTransport()
        fm.register_peer("A", t1)
        fm.register_peer("B", t2)
        results = fm.sync_all()
        assert len(results) == 2
        for r in results.values():
            assert isinstance(r, SyncResult)

    def test_sync_all_skips_inactive(self, store: SharedMemoryStore) -> None:
        fm = FederationManager(local_store=store)
        t = InMemoryTransport()
        pid = fm.register_peer("A", t)
        fm.get_peer(pid).status = "inactive"
        results = fm.sync_all()
        assert len(results) == 0

    def test_health_check(self, federation: FederationManager) -> None:
        t = InMemoryTransport()
        pid = federation.register_peer("peer-H", t)
        status = federation.health_check()
        assert status[pid] is True
        peer = federation.get_peer(pid)
        assert peer.status == "active"

    def test_health_check_unreachable(self, federation: FederationManager) -> None:
        class DeadTransport(SyncTransport):
            def send(self, memories, namespace=None):
                return {"accepted": 0, "rejected": 0, "errors": []}
            def receive(self, namespace=None, since=None):
                return []
            def ping(self):
                raise ConnectionError("offline")

        pid = federation.register_peer("dead", DeadTransport())
        status = federation.health_check()
        assert status[pid] is False
        assert federation.get_peer(pid).status == "error"

    def test_sync_with_namespace(
        self, store: SharedMemoryStore, federation: FederationManager,
    ) -> None:
        store.add("ns1", "A")
        store.add("ns2", "B")
        t = InMemoryTransport()
        pid = federation.register_peer("P", t)
        result = federation.sync_with_peer(pid, namespace="ns1")
        assert result.pushed == 1
