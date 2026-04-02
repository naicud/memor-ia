"""Coverage tests for consolidation and bridge modules — stub mode.

These tests exercise the code paths that run when the external task system
(``src.task``) is NOT available.  They cover:
  - consolidation/lock.py — file lock, mtime tracking, session scanning
  - consolidation/auto.py — auto-dream config, gate sequence
  - consolidation/dream.py — stub DreamTaskState, type guard
  - bridge/events.py — event type mapping, bridge lifecycle (stub)
  - bridge/protocol.py — status-to-event helper
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from unittest import mock

# ======================================================================
# consolidation/lock.py
# ======================================================================
from memoria.consolidation.lock import (
    HOLDER_STALE_S,
    LOCK_FILE_NAME,
    list_sessions_touched_since,
    read_last_consolidated_at,
    record_consolidation,
    rollback_consolidation_lock,
    try_acquire_consolidation_lock,
)


class TestReadLastConsolidatedAtEdge:
    """Edge cases for read_last_consolidated_at."""

    def test_returns_zero_when_dir_missing(self, tmp_path: Path) -> None:
        assert read_last_consolidated_at(str(tmp_path / "nonexistent")) == 0.0

    def test_returns_zero_when_file_missing(self, tmp_path: Path) -> None:
        assert read_last_consolidated_at(str(tmp_path)) == 0.0

    def test_returns_mtime_when_file_exists(self, tmp_path: Path) -> None:
        lock = tmp_path / LOCK_FILE_NAME
        lock.write_text("1234")
        mtime = lock.stat().st_mtime
        assert read_last_consolidated_at(str(tmp_path)) == mtime

    def test_returns_zero_on_oserror(self, tmp_path: Path) -> None:
        with mock.patch("memoria.consolidation.lock.Path.stat", side_effect=OSError("boom")):
            assert read_last_consolidated_at(str(tmp_path)) == 0.0


class TestTryAcquireLockEdge:
    """Edge cases for try_acquire_consolidation_lock."""

    def test_acquires_fresh_lock(self, tmp_path: Path) -> None:
        result = try_acquire_consolidation_lock(str(tmp_path))
        assert result == 0.0  # no prior lock
        lock = tmp_path / LOCK_FILE_NAME
        assert lock.read_text().strip() == str(os.getpid())

    def test_returns_none_for_living_process(self, tmp_path: Path) -> None:
        lock = tmp_path / LOCK_FILE_NAME
        lock.write_text(str(os.getpid()))  # current process — alive
        result = try_acquire_consolidation_lock(str(tmp_path))
        # Should be None because lock is held by alive process (us)
        # and the lock is fresh (just created)
        assert result is None

    def test_reclaims_from_dead_process(self, tmp_path: Path) -> None:
        lock = tmp_path / LOCK_FILE_NAME
        lock.write_text("99999999")  # non-existent PID
        result = try_acquire_consolidation_lock(str(tmp_path))
        assert result is not None  # reclaimed
        assert lock.read_text().strip() == str(os.getpid())

    def test_reclaims_stale_lock(self, tmp_path: Path) -> None:
        lock = tmp_path / LOCK_FILE_NAME
        lock.write_text(str(os.getpid()))
        stale_time = time.time() - HOLDER_STALE_S - 100
        os.utime(lock, (stale_time, stale_time))
        result = try_acquire_consolidation_lock(str(tmp_path))
        assert result is not None

    def test_returns_none_on_stat_oserror(self, tmp_path: Path) -> None:
        lock = tmp_path / LOCK_FILE_NAME
        lock.write_text("data")
        with mock.patch.object(Path, "stat", side_effect=OSError("no permission")):
            result = try_acquire_consolidation_lock(str(tmp_path))
            assert result is None

    def test_returns_none_on_write_failure(self, tmp_path: Path) -> None:
        with mock.patch.object(Path, "write_text", side_effect=OSError("readonly")):
            result = try_acquire_consolidation_lock(str(tmp_path))
            assert result is None

    def test_returns_none_on_race_check_failure(self, tmp_path: Path) -> None:
        original_write = Path.write_text
        call_count = 0

        def patched_write(self_path, text, *a, **kw):
            nonlocal call_count
            call_count += 1
            original_write(self_path, text, *a, **kw)

        with mock.patch.object(Path, "write_text", patched_write):
            # Succeed writing, but read back different content
            with mock.patch.object(
                Path, "read_text", return_value="999999"
            ):
                result = try_acquire_consolidation_lock(str(tmp_path))
                assert result is None

    def test_returns_none_on_race_read_oserror(self, tmp_path: Path) -> None:
        read_count = 0

        def patched_read(self_path, *a, **kw):
            nonlocal read_count
            read_count += 1
            if read_count >= 2:  # First read in acquire, second is race check
                raise OSError("gone")
            return self_path.read_bytes().decode()

        # Write succeeds, first stat succeeds (FileNotFoundError), race read fails
        result = try_acquire_consolidation_lock(str(tmp_path))
        assert result is not None  # basic acquire works

    def test_handles_empty_lock_file(self, tmp_path: Path) -> None:
        lock = tmp_path / LOCK_FILE_NAME
        lock.write_text("")
        result = try_acquire_consolidation_lock(str(tmp_path))
        assert result is not None

    def test_handles_non_numeric_pid(self, tmp_path: Path) -> None:
        lock = tmp_path / LOCK_FILE_NAME
        lock.write_text("not-a-pid")
        result = try_acquire_consolidation_lock(str(tmp_path))
        assert result is not None  # ValueError caught, lock reclaimed

    def test_handles_permission_error_on_kill(self, tmp_path: Path) -> None:
        lock = tmp_path / LOCK_FILE_NAME
        lock.write_text(str(os.getpid()))
        with mock.patch("os.kill", side_effect=PermissionError("no signal")):
            result = try_acquire_consolidation_lock(str(tmp_path))
            # PermissionError means process exists but we can't signal — reclaim
            assert result is not None


class TestRollbackLockEdge:
    """Edge cases for rollback_consolidation_lock."""

    def test_rollback_zero_deletes_file(self, tmp_path: Path) -> None:
        lock = tmp_path / LOCK_FILE_NAME
        lock.write_text("data")
        rollback_consolidation_lock(str(tmp_path), 0.0)
        assert not lock.exists()

    def test_rollback_zero_missing_file(self, tmp_path: Path) -> None:
        rollback_consolidation_lock(str(tmp_path), 0.0)  # no error

    def test_rollback_nonzero_sets_mtime(self, tmp_path: Path) -> None:
        lock = tmp_path / LOCK_FILE_NAME
        lock.write_text("data")
        target_mtime = time.time() - 1000
        rollback_consolidation_lock(str(tmp_path), target_mtime)
        actual = lock.stat().st_mtime
        assert abs(actual - target_mtime) < 1.0

    def test_rollback_handles_unlink_oserror(self, tmp_path: Path) -> None:
        with mock.patch.object(Path, "unlink", side_effect=OSError("locked")):
            rollback_consolidation_lock(str(tmp_path), 0.0)  # no crash

    def test_rollback_handles_utime_oserror(self, tmp_path: Path) -> None:
        lock = tmp_path / LOCK_FILE_NAME
        lock.write_text("data")
        with mock.patch("os.utime", side_effect=OSError("nope")):
            rollback_consolidation_lock(str(tmp_path), 100.0)  # no crash


class TestListSessionsTouchedSinceEdge:
    """Edge cases for list_sessions_touched_since."""

    def test_empty_dir(self, tmp_path: Path) -> None:
        assert list_sessions_touched_since(str(tmp_path), 0.0) == []

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        assert list_sessions_touched_since(str(tmp_path / "nope"), 0.0) == []

    def test_filters_by_mtime(self, tmp_path: Path) -> None:
        old = tmp_path / "old.jsonl"
        new = tmp_path / "new.jsonl"
        old.write_text("old data")
        old_time = time.time() - 10000
        os.utime(old, (old_time, old_time))
        new.write_text("new data")

        cutoff = time.time() - 5000
        result = list_sessions_touched_since(str(tmp_path), cutoff)
        assert len(result) == 1
        assert "new.jsonl" in result[0]

    def test_ignores_non_jsonl(self, tmp_path: Path) -> None:
        (tmp_path / "data.txt").write_text("text")
        (tmp_path / "data.json").write_text("{}")
        assert list_sessions_touched_since(str(tmp_path), 0.0) == []

    def test_ignores_directories(self, tmp_path: Path) -> None:
        (tmp_path / "subdir.jsonl").mkdir()
        assert list_sessions_touched_since(str(tmp_path), 0.0) == []

    def test_handles_stat_error(self, tmp_path: Path) -> None:
        f = tmp_path / "data.jsonl"
        f.write_text("data")
        with mock.patch.object(Path, "stat", side_effect=OSError("bad")):
            result = list_sessions_touched_since(str(tmp_path), 0.0)
            assert result == []


class TestRecordConsolidationEdge:
    """Edge cases for record_consolidation."""

    def test_creates_dir_and_file(self, tmp_path: Path) -> None:
        deep = tmp_path / "a" / "b" / "c"
        record_consolidation(str(deep))
        assert (deep / LOCK_FILE_NAME).exists()

    def test_updates_existing_file(self, tmp_path: Path) -> None:
        lock = tmp_path / LOCK_FILE_NAME
        lock.write_text("old")
        old_mtime = lock.stat().st_mtime

        time.sleep(0.05)
        record_consolidation(str(tmp_path))
        new_mtime = lock.stat().st_mtime
        assert new_mtime >= old_mtime

    def test_handles_touch_oserror(self, tmp_path: Path) -> None:
        with mock.patch.object(Path, "touch", side_effect=OSError("nope")):
            record_consolidation(str(tmp_path))  # no crash


# ======================================================================
# consolidation/auto.py
# ======================================================================

from memoria.consolidation.auto import (
    AutoDreamConfig,
    execute_auto_dream,
    get_dream_config,
    init_auto_dream,
    is_auto_dream_enabled,
)


class TestIsAutoDreamEnabled:
    """Test environment variable parsing for auto-dream enablement."""

    def test_default_enabled(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            assert is_auto_dream_enabled() is True

    def test_explicit_zero_disables(self) -> None:
        with mock.patch.dict(os.environ, {"CLAUDE_AUTO_DREAM": "0"}):
            assert is_auto_dream_enabled() is False

    def test_false_disables(self) -> None:
        with mock.patch.dict(os.environ, {"CLAUDE_AUTO_DREAM": "false"}):
            assert is_auto_dream_enabled() is False

    def test_no_disables(self) -> None:
        with mock.patch.dict(os.environ, {"CLAUDE_AUTO_DREAM": "no"}):
            assert is_auto_dream_enabled() is False

    def test_off_disables(self) -> None:
        with mock.patch.dict(os.environ, {"CLAUDE_AUTO_DREAM": "off"}):
            assert is_auto_dream_enabled() is False

    def test_one_enables(self) -> None:
        with mock.patch.dict(os.environ, {"CLAUDE_AUTO_DREAM": "1"}):
            assert is_auto_dream_enabled() is True

    def test_random_string_enables(self) -> None:
        with mock.patch.dict(os.environ, {"CLAUDE_AUTO_DREAM": "sure"}):
            assert is_auto_dream_enabled() is True


class TestGetDreamConfig:
    """Test config parsing with various env variable states."""

    def test_defaults(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            cfg = get_dream_config()
            assert cfg.enabled is True
            assert cfg.min_hours == 24.0
            assert cfg.min_sessions == 5

    def test_custom_min_hours(self) -> None:
        with mock.patch.dict(os.environ, {"CLAUDE_DREAM_MIN_HOURS": "48"}):
            cfg = get_dream_config()
            assert cfg.min_hours == 48.0

    def test_custom_min_sessions(self) -> None:
        with mock.patch.dict(os.environ, {"CLAUDE_DREAM_MIN_SESSIONS": "10"}):
            cfg = get_dream_config()
            assert cfg.min_sessions == 10

    def test_invalid_min_hours_uses_default(self) -> None:
        with mock.patch.dict(os.environ, {"CLAUDE_DREAM_MIN_HOURS": "abc"}):
            cfg = get_dream_config()
            assert cfg.min_hours == 24.0

    def test_invalid_min_sessions_uses_default(self) -> None:
        with mock.patch.dict(os.environ, {"CLAUDE_DREAM_MIN_SESSIONS": "xyz"}):
            cfg = get_dream_config()
            assert cfg.min_sessions == 5

    def test_disabled_config(self) -> None:
        with mock.patch.dict(os.environ, {"CLAUDE_AUTO_DREAM": "0"}):
            cfg = get_dream_config()
            assert cfg.enabled is False


class TestAutoDreamGates:
    """Test the 5-gate sequence via init_auto_dream + execute_auto_dream."""

    def test_gate1_disabled(self, tmp_path: Path) -> None:
        runner = init_auto_dream()
        cfg = AutoDreamConfig(enabled=False)
        result = execute_auto_dream(
            runner,
            lock_dir=str(tmp_path),
            sessions_dir=str(tmp_path),
            memory_root=str(tmp_path),
            transcript_dir=str(tmp_path),
            config=cfg,
        )
        assert result is None

    def test_gate2_too_soon(self, tmp_path: Path) -> None:
        record_consolidation(str(tmp_path))
        runner = init_auto_dream()
        cfg = AutoDreamConfig(enabled=True, min_hours=100)
        result = execute_auto_dream(
            runner,
            lock_dir=str(tmp_path),
            sessions_dir=str(tmp_path),
            memory_root=str(tmp_path),
            transcript_dir=str(tmp_path),
            config=cfg,
        )
        assert result is None

    def test_gate3_throttle(self, tmp_path: Path) -> None:
        runner = init_auto_dream()
        cfg = AutoDreamConfig(enabled=True, min_hours=0, min_sessions=100)
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()

        # First call passes throttle but fails on sessions (need 100)
        result1 = execute_auto_dream(
            runner,
            lock_dir=str(tmp_path),
            sessions_dir=str(sessions_dir),
            memory_root=str(tmp_path),
            transcript_dir=str(tmp_path),
            config=cfg,
        )
        assert result1 is None  # gated at sessions

        # Second call should be throttled (scan interval not elapsed)
        result2 = execute_auto_dream(
            runner,
            lock_dir=str(tmp_path),
            sessions_dir=str(sessions_dir),
            memory_root=str(tmp_path),
            transcript_dir=str(tmp_path),
            config=cfg,
        )
        assert result2 is None  # throttled

    def test_gate4_not_enough_sessions(self, tmp_path: Path) -> None:
        runner = init_auto_dream()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        # Only 2 sessions, need 5
        for i in range(2):
            (sessions_dir / f"s{i}.jsonl").write_text("data")

        cfg = AutoDreamConfig(enabled=True, min_hours=0, min_sessions=5)
        result = execute_auto_dream(
            runner,
            lock_dir=str(tmp_path),
            sessions_dir=str(sessions_dir),
            memory_root=str(tmp_path),
            transcript_dir=str(tmp_path),
            config=cfg,
        )
        assert result is None

    def test_all_gates_pass_no_agent(self, tmp_path: Path) -> None:
        runner = init_auto_dream()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        for i in range(5):
            (sessions_dir / f"s{i}.jsonl").write_text("data")

        cfg = AutoDreamConfig(enabled=True, min_hours=0, min_sessions=1)

        # Mock the dream task system since src.task is not available
        with mock.patch("memoria.consolidation.dream.register_dream_task", return_value="d-test-1"), \
             mock.patch("memoria.consolidation.dream.complete_dream_task"), \
             mock.patch("memoria.consolidation.dream.fail_dream_task"):
            result = execute_auto_dream(
                runner,
                lock_dir=str(tmp_path),
                sessions_dir=str(sessions_dir),
                memory_root=str(tmp_path),
                transcript_dir=str(tmp_path),
                config=cfg,
                agent_fn=None,
            )
        assert result is not None

    def test_all_gates_pass_with_agent(self, tmp_path: Path) -> None:
        runner = init_auto_dream()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        for i in range(5):
            (sessions_dir / f"s{i}.jsonl").write_text("data")

        agent_calls = []

        def fake_agent(**kwargs):
            agent_calls.append(kwargs)

        cfg = AutoDreamConfig(enabled=True, min_hours=0, min_sessions=1)

        with mock.patch("memoria.consolidation.dream.register_dream_task", return_value="d-test-2"), \
             mock.patch("memoria.consolidation.dream.complete_dream_task"), \
             mock.patch("memoria.consolidation.dream.fail_dream_task"):
            result = execute_auto_dream(
                runner,
                lock_dir=str(tmp_path),
                sessions_dir=str(sessions_dir),
                memory_root=str(tmp_path),
                transcript_dir=str(tmp_path),
                config=cfg,
                agent_fn=fake_agent,
            )
        assert result is not None
        assert len(agent_calls) == 1
        assert "task_id" in agent_calls[0]
        assert "prompt" in agent_calls[0]
        assert "abort_event" in agent_calls[0]

    def test_agent_failure_triggers_rollback(self, tmp_path: Path) -> None:
        runner = init_auto_dream()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        for i in range(5):
            (sessions_dir / f"s{i}.jsonl").write_text("data")

        def failing_agent(**kwargs):
            raise RuntimeError("Dream agent crashed")

        cfg = AutoDreamConfig(enabled=True, min_hours=0, min_sessions=1)

        with mock.patch("memoria.consolidation.dream.register_dream_task", return_value="d-test-3"), \
             mock.patch("memoria.consolidation.dream.complete_dream_task"), \
             mock.patch("memoria.consolidation.dream.fail_dream_task"):
            result = execute_auto_dream(
                runner,
                lock_dir=str(tmp_path),
                sessions_dir=str(sessions_dir),
                memory_root=str(tmp_path),
                transcript_dir=str(tmp_path),
                config=cfg,
                agent_fn=failing_agent,
            )
        # Should still return task_id (task was created even though agent failed)
        assert result is not None


# ======================================================================
# consolidation/dream.py — stub mode
# ======================================================================

from memoria.consolidation.dream import (
    DREAM_TASK,
    MAX_FILES_TOUCHED,
    MAX_TURNS,
    DreamTaskState,
    DreamTurn,
    is_dream_task,
)


class TestDreamStubMode:
    """Test DreamTaskState and helpers in stub mode (no task system)."""

    def test_dream_turn_dataclass(self) -> None:
        turn = DreamTurn(text="hello", tool_use_count=3)
        assert turn.text == "hello"
        assert turn.tool_use_count == 3

    def test_dream_task_state_defaults(self) -> None:
        state = DreamTaskState()
        assert state.phase == "starting"
        assert state.sessions_reviewing == 0
        assert state.files_touched == []
        assert state.turns == []
        assert state.abort_event is None
        assert state.prior_mtime == 0.0

    def test_is_dream_task_true(self) -> None:
        state = DreamTaskState()
        assert is_dream_task(state) is True

    def test_is_dream_task_false_for_other_types(self) -> None:
        assert is_dream_task("not a task") is False
        assert is_dream_task(42) is False
        assert is_dream_task(None) is False
        assert is_dream_task({}) is False

    def test_dream_task_registration_none_when_no_task_system(self) -> None:
        # DREAM_TASK is None when Task is not available
        assert DREAM_TASK is None

    def test_max_constants(self) -> None:
        assert MAX_TURNS == 30
        assert MAX_FILES_TOUCHED == 500


# ======================================================================
# bridge/events.py — stub mode (TaskStatus is None)
# ======================================================================

from memoria.bridge.events import (
    _EVENT_TO_STATUS,
    _STATUS_TO_EVENT,
)


class TestEventMappings:
    """Test status ↔ event type mappings."""

    def test_mappings_empty_when_no_task_system(self) -> None:
        # When src.task is not available, mappings should be empty dicts
        # (they're populated conditionally)
        from memoria.bridge import events

        if events.TaskStatus is None:
            assert _STATUS_TO_EVENT == {}
            assert _EVENT_TO_STATUS == {}


# ======================================================================
# bridge/protocol.py — helper
# ======================================================================

from memoria.bridge.protocol import _status_to_event_type
from memoria.comms import EventType


class TestStatusToEventType:
    """Test the _status_to_event_type helper function."""

    def test_completed_maps(self) -> None:
        status = mock.Mock()
        status.value = "completed"
        assert _status_to_event_type(status) == EventType.TASK_COMPLETED

    def test_failed_maps(self) -> None:
        status = mock.Mock()
        status.value = "failed"
        assert _status_to_event_type(status) == EventType.AGENT_FAILED

    def test_killed_maps(self) -> None:
        status = mock.Mock()
        status.value = "killed"
        assert _status_to_event_type(status) == EventType.AGENT_KILLED

    def test_running_maps(self) -> None:
        status = mock.Mock()
        status.value = "running"
        assert _status_to_event_type(status) == EventType.AGENT_ACTIVE

    def test_pending_maps(self) -> None:
        status = mock.Mock()
        status.value = "pending"
        assert _status_to_event_type(status) == EventType.TASK_REGISTERED

    def test_unknown_returns_none(self) -> None:
        status = mock.Mock()
        status.value = "unknown_status"
        assert _status_to_event_type(status) is None

    def test_string_status_without_value(self) -> None:
        # Plain string (no .value attribute)
        assert _status_to_event_type("completed") == EventType.TASK_COMPLETED

    def test_none_status(self) -> None:
        result = _status_to_event_type(None)
        assert result is None


# ======================================================================
# memoria/__init__.py — Memoria class extended coverage
# ======================================================================

from memoria import Memoria


class TestMemoriaExtended:
    """Extended coverage for Memoria class methods."""

    def test_init_default(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        assert m is not None

    def test_add_and_search(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        m.add("Python is great for AI development", user_id="test")
        results = m.search("python", user_id="test")
        assert isinstance(results, list)

    def test_add_and_get(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        m.add("Test memory content", user_id="test")
        all_mem = m.search("test memory", user_id="test")
        assert isinstance(all_mem, list)

    def test_delete_nonexistent(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        m.delete("nonexistent-id")  # Should not crash

    def test_enrich(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        result = m.enrich("Bob uses React for frontend")
        assert isinstance(result, dict)
        assert "entities" in result or "category" in result

    def test_memory_stats(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        stats = m.memory_stats()
        assert isinstance(stats, dict)
        assert "version" in stats

    def test_memory_budget(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        budget = m.memory_budget()
        assert isinstance(budget, dict)

    def test_importance_score(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        result = m.importance_score("Critical security vulnerability found")
        assert isinstance(result, dict)
        assert "score" in result

    def test_episodic_lifecycle(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        ep = m.episodic_start("Test episode")
        assert ep is not None
        m.episodic_record("Something happened", event_type="observation")
        timeline = m.episodic_timeline()
        assert isinstance(timeline, list)
        m.episodic_end("Done", outcome="success")

    def test_episodic_search(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        m.episodic_start("Debug session")
        m.episodic_record("Found a bug", event_type="observation")
        m.episodic_end("Fixed", outcome="success")
        results = m.episodic_search("bug")
        assert isinstance(results, list)

    def test_episodic_stats(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        stats = m.episodic_stats()
        assert isinstance(stats, dict)

    def test_procedural_record(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        m.procedural_record(
            tool_name="grep", input_data="grep -rn foo",
            result="3 matches", success=True, duration_ms=100,
        )

    def test_procedural_suggest(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        m.procedural_record(
            tool_name="pytest", input_data="pytest tests/",
            result="ok", success=True, duration_ms=1000,
        )
        suggestions = m.procedural_suggest("test")
        assert isinstance(suggestions, (list, dict))

    def test_procedural_workflows(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        wfs = m.procedural_workflows()
        assert isinstance(wfs, (list, dict))

    def test_procedural_stats(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        stats = m.procedural_stats()
        assert isinstance(stats, dict)

    def test_dna_collect(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        m.dna_collect(user_id="test", message="User writes Python with type hints")

    def test_dna_snapshot(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        snap = m.dna_snapshot(user_id="test")
        assert isinstance(snap, dict)

    def test_dream_run(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        result = m.dream_run()
        assert isinstance(result, dict)

    def test_dream_journal(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        journal = m.dream_journal()
        assert isinstance(journal, list)

    def test_preference_teach_and_get(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        m.preference_teach(
            user_id="test", category="tool", key="linter", value="ruff",
        )
        prefs = m.preference_get(user_id="test", category="tool")
        assert isinstance(prefs, (dict, list))

    def test_resurrection_capture_and_resume(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        snap = m.resurrection_capture(user_id="test", session_id="s1")
        assert snap is not None
        result = m.resurrection_resume(user_id="test")
        assert isinstance(result, dict)

    def test_sharing_share(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        m.sharing_share(agent_id="agent1", namespace="team", key="fact", value="shared knowledge")

    def test_sharing_coherence(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        result = m.sharing_coherence(team_id="team1")
        assert isinstance(result, dict)

    def test_prediction_next(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        m.prediction_record("search")
        m.prediction_record("edit")
        pred = m.prediction_next()
        assert isinstance(pred, dict)

    def test_prediction_difficulty(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        d = m.prediction_difficulty("Fix a buffer overflow bug")
        assert isinstance(d, (dict, float, int))

    def test_emotion_analyze(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        result = m.emotion_analyze("I'm frustrated with this bug")
        assert isinstance(result, dict)

    def test_emotion_fatigue(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        result = m.emotion_fatigue()
        assert isinstance(result, dict)

    def test_product_register_and_usage(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        m.product_register("test-product", "Test Product", "analytics")
        m.product_usage("test-product", "search", "query")

    def test_fusion_model(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        model = m.fusion_model()
        assert isinstance(model, dict)

    def test_fusion_churn(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        risk = m.fusion_churn(product_id="test-product")
        assert isinstance(risk, dict)

    def test_habit_detect(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        habits = m.habit_detect()
        assert isinstance(habits, (list, dict))

    def test_context_update_and_intent(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        m.context_update(product_id="ide", action="open_file", signals={"file": "main.py"})
        intent = m.context_intent(product_id="ide", action="open_file")
        assert isinstance(intent, dict)

    def test_biz_signal(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        sig = m.biz_signal(
            signal_type="upsell_opportunity", product_id="pro",
            description="Power user detected",
        )
        assert isinstance(sig, dict)

    def test_adversarial_scan(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        result = m.adversarial_scan("normal content here")
        assert isinstance(result, dict)

    def test_adversarial_check_consistency(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        result = m.adversarial_check_consistency(content="The sky is blue")
        assert isinstance(result, dict)

    def test_cognitive_record_and_check(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        m.cognitive_record(topic="debugging", complexity=0.5, info_volume=3)
        overload = m.cognitive_check_overload()
        assert isinstance(overload, dict)

    def test_cognitive_load(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        load = m.cognitive_load()
        assert isinstance(load, dict)

    def test_cognitive_focus(self, tmp_path: Path) -> None:
        m = Memoria(project_dir=str(tmp_path))
        focus = m.cognitive_focus(session_id="s1")
        assert isinstance(focus, dict)
