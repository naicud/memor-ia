"""Comprehensive tests for the MEMORIA versioning module."""

from __future__ import annotations

import time

import pytest

from memoria.versioning.history import VersionEntry, VersionHistory
from memoria.versioning.diff import DiffEntry, MemoryDiff
from memoria.versioning.audit import AuditEvent, AuditTrail
from memoria.versioning.snapshots import Snapshot, SnapshotStore


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture()
def vh() -> VersionHistory:
    return VersionHistory()


@pytest.fixture()
def audit() -> AuditTrail:
    return AuditTrail()


@pytest.fixture()
def snaps() -> SnapshotStore:
    return SnapshotStore()


# ===================================================================
# 1. VersionHistory
# ===================================================================


class TestVersionHistory:
    def test_record_creates_first_version(self, vh: VersionHistory) -> None:
        entry = vh.record("m1", "hello", change_type="create")
        assert entry.version == 1
        assert entry.memory_id == "m1"
        assert entry.content == "hello"
        assert entry.change_type == "create"

    def test_record_auto_increments(self, vh: VersionHistory) -> None:
        vh.record("m1", "v1")
        vh.record("m1", "v2")
        e3 = vh.record("m1", "v3")
        assert e3.version == 3

    def test_record_independent_memories(self, vh: VersionHistory) -> None:
        e1 = vh.record("m1", "a")
        e2 = vh.record("m2", "b")
        assert e1.version == 1
        assert e2.version == 1

    def test_record_with_metadata(self, vh: VersionHistory) -> None:
        entry = vh.record("m1", "data", metadata={"tag": "important"})
        assert entry.metadata == {"tag": "important"}

    def test_record_default_changed_by(self, vh: VersionHistory) -> None:
        entry = vh.record("m1", "content")
        assert entry.changed_by == "system"

    def test_record_custom_changed_by(self, vh: VersionHistory) -> None:
        entry = vh.record("m1", "content", changed_by="agent-007")
        assert entry.changed_by == "agent-007"

    def test_get_version_existing(self, vh: VersionHistory) -> None:
        vh.record("m1", "first")
        vh.record("m1", "second")
        v1 = vh.get_version("m1", 1)
        assert v1 is not None
        assert v1.content == "first"

    def test_get_version_missing(self, vh: VersionHistory) -> None:
        assert vh.get_version("m1", 99) is None

    def test_get_latest(self, vh: VersionHistory) -> None:
        vh.record("m1", "old")
        vh.record("m1", "new")
        latest = vh.get_latest("m1")
        assert latest is not None
        assert latest.content == "new"
        assert latest.version == 2

    def test_get_latest_no_versions(self, vh: VersionHistory) -> None:
        assert vh.get_latest("nonexistent") is None

    def test_get_history_order(self, vh: VersionHistory) -> None:
        vh.record("m1", "a")
        vh.record("m1", "b")
        vh.record("m1", "c")
        history = vh.get_history("m1")
        assert len(history) == 3
        assert [e.content for e in history] == ["a", "b", "c"]
        assert [e.version for e in history] == [1, 2, 3]

    def test_get_history_empty(self, vh: VersionHistory) -> None:
        assert vh.get_history("nonexistent") == []

    def test_version_count(self, vh: VersionHistory) -> None:
        assert vh.version_count("m1") == 0
        vh.record("m1", "a")
        vh.record("m1", "b")
        assert vh.version_count("m1") == 2

    def test_get_state_at(self, vh: VersionHistory) -> None:
        vh.record("m1", "content-v1", metadata={"k": "v1"})
        vh.record("m1", "content-v2", metadata={"k": "v2"})
        state = vh.get_state_at("m1", 1)
        assert state == {"content": "content-v1", "metadata": {"k": "v1"}}

    def test_get_state_at_missing(self, vh: VersionHistory) -> None:
        assert vh.get_state_at("m1", 1) is None

    def test_rollback(self, vh: VersionHistory) -> None:
        vh.record("m1", "original", metadata={"v": 1})
        vh.record("m1", "modified", metadata={"v": 2})
        restored = vh.rollback("m1", to_version=1)
        assert restored.content == "original"
        assert restored.metadata == {"v": 1}
        assert restored.change_type == "restore"
        assert restored.version == 3

    def test_rollback_invalid_version(self, vh: VersionHistory) -> None:
        with pytest.raises(ValueError, match="does not exist"):
            vh.rollback("m1", to_version=99)

    def test_changed_at_is_iso(self, vh: VersionHistory) -> None:
        entry = vh.record("m1", "test")
        # Should contain 'T' as ISO separator
        assert "T" in entry.changed_at


# ===================================================================
# 2. MemoryDiff
# ===================================================================


class TestMemoryDiff:
    @staticmethod
    def _entry(
        content: str = "text",
        metadata: dict | None = None,
        changed_by: str = "system",
        version: int = 1,
    ) -> VersionEntry:
        return VersionEntry(
            version=version,
            memory_id="m1",
            content=content,
            metadata=metadata or {},
            changed_by=changed_by,
            changed_at="2025-01-01T00:00:00",
            change_type="update",
        )

    def test_compute_no_changes(self) -> None:
        e = self._entry()
        assert MemoryDiff.compute(e, e) == []

    def test_compute_content_change(self) -> None:
        old = self._entry(content="old")
        new = self._entry(content="new")
        diffs = MemoryDiff.compute(old, new)
        assert len(diffs) == 1
        assert diffs[0].field == "content"
        assert diffs[0].old_value == "old"
        assert diffs[0].new_value == "new"

    def test_compute_metadata_added(self) -> None:
        old = self._entry(metadata={})
        new = self._entry(metadata={"tag": "urgent"})
        diffs = MemoryDiff.compute(old, new)
        assert any(d.field == "metadata.tag" and d.old_value is None for d in diffs)

    def test_compute_metadata_removed(self) -> None:
        old = self._entry(metadata={"tag": "urgent"})
        new = self._entry(metadata={})
        diffs = MemoryDiff.compute(old, new)
        assert any(d.field == "metadata.tag" and d.new_value is None for d in diffs)

    def test_compute_metadata_modified(self) -> None:
        old = self._entry(metadata={"priority": "low"})
        new = self._entry(metadata={"priority": "high"})
        diffs = MemoryDiff.compute(old, new)
        assert any(d.field == "metadata.priority" for d in diffs)

    def test_compute_changed_by(self) -> None:
        old = self._entry(changed_by="alice")
        new = self._entry(changed_by="bob")
        diffs = MemoryDiff.compute(old, new)
        assert any(d.field == "changed_by" for d in diffs)

    def test_compute_multiple_changes(self) -> None:
        old = self._entry(content="a", metadata={"x": 1}, changed_by="alice")
        new = self._entry(content="b", metadata={"x": 2, "y": 3}, changed_by="bob")
        diffs = MemoryDiff.compute(old, new)
        fields = {d.field for d in diffs}
        assert "content" in fields
        assert "metadata.x" in fields
        assert "metadata.y" in fields
        assert "changed_by" in fields

    def test_content_diff_unified(self) -> None:
        lines = MemoryDiff.content_diff("line1\nline2\n", "line1\nline3\n")
        assert any("line2" in l for l in lines)
        assert any("line3" in l for l in lines)

    def test_content_diff_identical(self) -> None:
        assert MemoryDiff.content_diff("same", "same") == []

    def test_summarize_no_changes(self) -> None:
        assert MemoryDiff.summarize([]) == "No changes"

    def test_summarize_content_only(self) -> None:
        diffs = [DiffEntry(field="content", old_value="a", new_value="b")]
        summary = MemoryDiff.summarize(diffs)
        assert "Content changed" in summary

    def test_summarize_metadata_only(self) -> None:
        diffs = [
            DiffEntry(field="metadata.x", old_value=1, new_value=2),
            DiffEntry(field="metadata.y", old_value=None, new_value=3),
        ]
        summary = MemoryDiff.summarize(diffs)
        assert "2 metadata fields updated" in summary

    def test_summarize_single_metadata(self) -> None:
        diffs = [DiffEntry(field="metadata.x", old_value=1, new_value=2)]
        summary = MemoryDiff.summarize(diffs)
        assert "1 metadata field updated" in summary

    def test_has_content_change_true(self) -> None:
        diffs = [DiffEntry(field="content", old_value="a", new_value="b")]
        assert MemoryDiff.has_content_change(diffs) is True

    def test_has_content_change_false(self) -> None:
        diffs = [DiffEntry(field="metadata.x", old_value=1, new_value=2)]
        assert MemoryDiff.has_content_change(diffs) is False

    def test_has_metadata_change_true(self) -> None:
        diffs = [DiffEntry(field="metadata.tag", old_value=None, new_value="a")]
        assert MemoryDiff.has_metadata_change(diffs) is True

    def test_has_metadata_change_false(self) -> None:
        diffs = [DiffEntry(field="content", old_value="a", new_value="b")]
        assert MemoryDiff.has_metadata_change(diffs) is False


# ===================================================================
# 3. AuditTrail
# ===================================================================


class TestAuditTrail:
    def test_log_returns_event_id(self, audit: AuditTrail) -> None:
        eid = audit.log("m1", "create", "agent-1")
        assert isinstance(eid, str)
        assert len(eid) > 0

    def test_log_with_namespace_and_details(self, audit: AuditTrail) -> None:
        eid = audit.log("m1", "update", "agent-1", namespace="acme/team", details={"reason": "fix"})
        events = audit.get_events("m1")
        assert len(events) == 1
        assert events[0].namespace == "acme/team"
        assert events[0].details == {"reason": "fix"}

    def test_get_events_returns_all(self, audit: AuditTrail) -> None:
        audit.log("m1", "create", "a1")
        audit.log("m1", "update", "a2")
        audit.log("m2", "create", "a1")
        events = audit.get_events("m1")
        assert len(events) == 2

    def test_get_agent_activity(self, audit: AuditTrail) -> None:
        audit.log("m1", "create", "a1")
        audit.log("m2", "update", "a1")
        audit.log("m3", "delete", "a2")
        activity = audit.get_agent_activity("a1")
        assert len(activity) == 2
        assert all(e.agent_id == "a1" for e in activity)

    def test_get_agent_activity_limit(self, audit: AuditTrail) -> None:
        for i in range(10):
            audit.log(f"m{i}", "update", "a1")
        assert len(audit.get_agent_activity("a1", limit=3)) == 3

    def test_get_events_in_range(self, audit: AuditTrail) -> None:
        audit.log("m1", "create", "a1")
        time.sleep(0.01)
        audit.log("m2", "update", "a1")
        events = audit.get_events("m1")
        ts = events[0].timestamp
        # Range covering all events
        result = audit.get_events_in_range("2020-01-01T00:00:00", "2099-01-01T00:00:00")
        assert len(result) == 2

    def test_get_events_in_range_empty(self, audit: AuditTrail) -> None:
        audit.log("m1", "create", "a1")
        result = audit.get_events_in_range("2099-01-01T00:00:00", "2099-12-31T00:00:00")
        assert result == []

    def test_get_events_by_action(self, audit: AuditTrail) -> None:
        audit.log("m1", "create", "a1")
        audit.log("m2", "delete", "a1")
        audit.log("m3", "create", "a2")
        creates = audit.get_events_by_action("create")
        assert len(creates) == 2
        assert all(e.action == "create" for e in creates)

    def test_count_all(self, audit: AuditTrail) -> None:
        assert audit.count() == 0
        audit.log("m1", "create", "a1")
        audit.log("m2", "update", "a1")
        assert audit.count() == 2

    def test_count_per_memory(self, audit: AuditTrail) -> None:
        audit.log("m1", "create", "a1")
        audit.log("m1", "update", "a1")
        audit.log("m2", "create", "a1")
        assert audit.count("m1") == 2
        assert audit.count("m2") == 1

    def test_purge_before(self, audit: AuditTrail) -> None:
        audit.log("m1", "create", "a1")
        time.sleep(0.01)
        # Get current time to use as cutoff
        from datetime import datetime, timezone
        cutoff = datetime.now(timezone.utc).isoformat()
        time.sleep(0.01)
        audit.log("m2", "update", "a1")
        deleted = audit.purge_before(cutoff)
        assert deleted == 1
        assert audit.count() == 1


# ===================================================================
# 4. SnapshotStore
# ===================================================================


class TestSnapshotStore:
    @staticmethod
    def _memories() -> list[dict]:
        return [
            {"id": "m1", "content": "Memory one", "metadata": {}},
            {"id": "m2", "content": "Memory two", "metadata": {"tag": "a"}},
        ]

    def test_create_snapshot(self, snaps: SnapshotStore) -> None:
        snap = snaps.create_snapshot("acme", self._memories())
        assert snap.namespace == "acme"
        assert snap.memory_count == 2
        assert snap.created_by == "system"
        assert len(snap.data) == 2

    def test_create_snapshot_custom_author(self, snaps: SnapshotStore) -> None:
        snap = snaps.create_snapshot("acme", [], created_by="admin")
        assert snap.created_by == "admin"

    def test_get_snapshot(self, snaps: SnapshotStore) -> None:
        created = snaps.create_snapshot("acme", self._memories())
        fetched = snaps.get_snapshot(created.snapshot_id)
        assert fetched is not None
        assert fetched.snapshot_id == created.snapshot_id
        assert fetched.data == self._memories()

    def test_get_snapshot_missing(self, snaps: SnapshotStore) -> None:
        assert snaps.get_snapshot("nonexistent") is None

    def test_list_snapshots_lightweight(self, snaps: SnapshotStore) -> None:
        snaps.create_snapshot("acme", self._memories())
        snaps.create_snapshot("acme", [])
        snaps.create_snapshot("other", self._memories())
        listed = snaps.list_snapshots("acme")
        assert len(listed) == 2
        # Lightweight — data should be empty list
        assert all(s.data == [] for s in listed)

    def test_diff_snapshots_added(self, snaps: SnapshotStore) -> None:
        s1 = snaps.create_snapshot("ns", [{"id": "m1", "content": "a"}])
        s2 = snaps.create_snapshot("ns", [{"id": "m1", "content": "a"}, {"id": "m2", "content": "b"}])
        diff = snaps.diff_snapshots(s1.snapshot_id, s2.snapshot_id)
        assert len(diff["added"]) == 1
        assert diff["added"][0]["id"] == "m2"
        assert diff["removed"] == []

    def test_diff_snapshots_removed(self, snaps: SnapshotStore) -> None:
        s1 = snaps.create_snapshot("ns", [{"id": "m1", "content": "a"}, {"id": "m2", "content": "b"}])
        s2 = snaps.create_snapshot("ns", [{"id": "m1", "content": "a"}])
        diff = snaps.diff_snapshots(s1.snapshot_id, s2.snapshot_id)
        assert len(diff["removed"]) == 1
        assert diff["removed"][0]["id"] == "m2"

    def test_diff_snapshots_modified(self, snaps: SnapshotStore) -> None:
        s1 = snaps.create_snapshot("ns", [{"id": "m1", "content": "old"}])
        s2 = snaps.create_snapshot("ns", [{"id": "m1", "content": "new"}])
        diff = snaps.diff_snapshots(s1.snapshot_id, s2.snapshot_id)
        assert len(diff["modified"]) == 1

    def test_diff_snapshots_invalid_id(self, snaps: SnapshotStore) -> None:
        s1 = snaps.create_snapshot("ns", [])
        with pytest.raises(ValueError):
            snaps.diff_snapshots(s1.snapshot_id, "bad-id")

    def test_delete_snapshot(self, snaps: SnapshotStore) -> None:
        snap = snaps.create_snapshot("acme", self._memories())
        assert snaps.delete_snapshot(snap.snapshot_id) is True
        assert snaps.get_snapshot(snap.snapshot_id) is None

    def test_delete_snapshot_missing(self, snaps: SnapshotStore) -> None:
        assert snaps.delete_snapshot("nonexistent") is False

    def test_restore_snapshot(self, snaps: SnapshotStore) -> None:
        mems = self._memories()
        snap = snaps.create_snapshot("acme", mems)
        restored = snaps.restore_snapshot(snap.snapshot_id)
        assert restored == mems

    def test_restore_snapshot_missing(self, snaps: SnapshotStore) -> None:
        with pytest.raises(ValueError, match="not found"):
            snaps.restore_snapshot("nonexistent")
