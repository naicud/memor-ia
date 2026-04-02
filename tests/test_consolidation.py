"""Tests for memoria.consolidation (dream task and related dream services)."""

from __future__ import annotations

import os
import threading
import time
from unittest import mock

import pytest

try:
    from src.task import TaskStatus, TaskType
    from src.utils.task_framework import _manager, get_task
    _HAS_TASK_SYSTEM = True
except ImportError:
    _HAS_TASK_SYSTEM = False

pytestmark = pytest.mark.skipif(
    not _HAS_TASK_SYSTEM, reason="Task system (src.task) not available"
)

from memoria.consolidation.auto import (
    SESSION_SCAN_INTERVAL,
    AutoDreamConfig,
    execute_auto_dream,
    get_dream_config,
    init_auto_dream,
    is_auto_dream_enabled,
)
from memoria.consolidation.dream import (
    DREAM_DESCRIPTION,
    DREAM_TASK,
    MAX_TURNS,
    DreamTurn,
    add_dream_turn,
    complete_dream_task,
    fail_dream_task,
    is_dream_task,
    kill_dream_task,
    register_dream_task,
)
from memoria.consolidation.lock import (
    LOCK_FILE_NAME,
    list_sessions_touched_since,
    read_last_consolidated_at,
    record_consolidation,
    rollback_consolidation_lock,
    try_acquire_consolidation_lock,
)
from memoria.consolidation.prompt_template import (
    ENTRYPOINT_NAME,
    MAX_ENTRYPOINT_BYTES,
    MAX_ENTRYPOINT_LINES,
    build_consolidation_prompt,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_task_manager():
    """Clear all tasks before and after each test."""
    _manager._tasks.clear()
    _manager._task_offsets.clear()
    yield
    _manager._tasks.clear()
    _manager._task_offsets.clear()


# ===========================================================================
# DreamTask lifecycle
# ===========================================================================


class TestRegisterDreamTask:
    """Tests for register_dream_task."""

    def test_creates_task_with_running_status(self):
        task_id = register_dream_task(sessions_reviewing=3)
        task = get_task(task_id)
        assert task is not None
        assert task.status == TaskStatus.RUNNING

    def test_task_id_starts_with_d(self):
        task_id = register_dream_task(sessions_reviewing=1)
        assert task_id.startswith("d")

    def test_task_type_is_dream(self):
        task_id = register_dream_task(sessions_reviewing=2)
        task = get_task(task_id)
        assert task.type == TaskType.DREAM

    def test_sessions_reviewing_stored(self):
        task_id = register_dream_task(sessions_reviewing=7)
        task = get_task(task_id)
        assert task.sessions_reviewing == 7

    def test_initial_phase_is_starting(self):
        task_id = register_dream_task(sessions_reviewing=1)
        task = get_task(task_id)
        assert task.phase == "starting"

    def test_initial_turns_empty(self):
        task_id = register_dream_task(sessions_reviewing=1)
        task = get_task(task_id)
        assert task.turns == []

    def test_initial_files_touched_empty(self):
        task_id = register_dream_task(sessions_reviewing=1)
        task = get_task(task_id)
        assert task.files_touched == []

    def test_description_is_memory_consolidation(self):
        task_id = register_dream_task(sessions_reviewing=1)
        task = get_task(task_id)
        assert task.description == DREAM_DESCRIPTION

    def test_custom_abort_event(self):
        evt = threading.Event()
        task_id = register_dream_task(sessions_reviewing=1, abort_event=evt)
        task = get_task(task_id)
        assert task.abort_event is evt

    def test_creates_default_abort_event(self):
        task_id = register_dream_task(sessions_reviewing=1)
        task = get_task(task_id)
        assert task.abort_event is not None
        assert isinstance(task.abort_event, threading.Event)


class TestIsDreamTask:
    """Tests for is_dream_task type guard."""

    def test_dream_task_returns_true(self):
        task_id = register_dream_task(sessions_reviewing=1)
        task = get_task(task_id)
        assert is_dream_task(task) is True

    def test_non_dream_returns_false(self):
        assert is_dream_task({"type": "local_bash"}) is False

    def test_none_returns_false(self):
        assert is_dream_task(None) is False


class TestAddDreamTurn:
    """Tests for add_dream_turn."""

    def test_appends_turn(self):
        task_id = register_dream_task(sessions_reviewing=1)
        turn = DreamTurn(text="analyzing sessions", tool_use_count=2)
        add_dream_turn(task_id, turn)
        task = get_task(task_id)
        assert len(task.turns) == 1
        assert task.turns[0].text == "analyzing sessions"
        assert task.turns[0].tool_use_count == 2

    def test_caps_at_max_turns(self):
        task_id = register_dream_task(sessions_reviewing=1)
        for i in range(MAX_TURNS + 5):
            add_dream_turn(task_id, DreamTurn(text=f"turn-{i}", tool_use_count=0))
        task = get_task(task_id)
        assert len(task.turns) == MAX_TURNS
        # Oldest turns evicted — last turn should be the most recent
        assert task.turns[-1].text == f"turn-{MAX_TURNS + 4}"
        assert task.turns[0].text == "turn-5"

    def test_files_touched_accumulated(self):
        task_id = register_dream_task(sessions_reviewing=1)
        add_dream_turn(
            task_id,
            DreamTurn(text="t1", tool_use_count=1),
            touched_paths=["MEMORY.md"],
        )
        add_dream_turn(
            task_id,
            DreamTurn(text="t2", tool_use_count=1),
            touched_paths=["MEMORY.md", "notes.md"],
        )
        task = get_task(task_id)
        assert task.files_touched == ["MEMORY.md", "notes.md"]

    def test_phase_flips_on_first_file_touch(self):
        task_id = register_dream_task(sessions_reviewing=1)
        task = get_task(task_id)
        assert task.phase == "starting"

        add_dream_turn(
            task_id,
            DreamTurn(text="t1", tool_use_count=1),
            touched_paths=["MEMORY.md"],
        )
        task = get_task(task_id)
        assert task.phase == "updating"

    def test_no_phase_flip_without_files(self):
        task_id = register_dream_task(sessions_reviewing=1)
        add_dream_turn(task_id, DreamTurn(text="thinking", tool_use_count=0))
        task = get_task(task_id)
        assert task.phase == "starting"

    def test_noop_on_terminal_task(self):
        task_id = register_dream_task(sessions_reviewing=1)
        complete_dream_task(task_id)
        add_dream_turn(task_id, DreamTurn(text="late", tool_use_count=0))
        task = get_task(task_id)
        assert len(task.turns) == 0


class TestCompleteDreamTask:
    """Tests for complete_dream_task."""

    def test_sets_completed_status(self):
        task_id = register_dream_task(sessions_reviewing=1)
        complete_dream_task(task_id)
        task = get_task(task_id)
        assert task.status == TaskStatus.COMPLETED

    def test_sets_notified(self):
        task_id = register_dream_task(sessions_reviewing=1)
        complete_dream_task(task_id)
        task = get_task(task_id)
        assert task.notified is True

    def test_sets_end_time(self):
        task_id = register_dream_task(sessions_reviewing=1)
        before = time.time()
        complete_dream_task(task_id)
        task = get_task(task_id)
        assert task.end_time is not None
        assert task.end_time >= before

    def test_noop_on_already_terminal(self):
        task_id = register_dream_task(sessions_reviewing=1)
        complete_dream_task(task_id)
        t1 = get_task(task_id).end_time
        complete_dream_task(task_id)
        assert get_task(task_id).end_time == t1


class TestFailDreamTask:
    """Tests for fail_dream_task."""

    def test_sets_failed_status(self):
        task_id = register_dream_task(sessions_reviewing=1)
        fail_dream_task(task_id)
        task = get_task(task_id)
        assert task.status == TaskStatus.FAILED

    def test_sets_notified(self):
        task_id = register_dream_task(sessions_reviewing=1)
        fail_dream_task(task_id)
        task = get_task(task_id)
        assert task.notified is True

    def test_sets_end_time(self):
        task_id = register_dream_task(sessions_reviewing=1)
        fail_dream_task(task_id)
        task = get_task(task_id)
        assert task.end_time is not None


class TestKillDreamTask:
    """Tests for kill_dream_task."""

    def test_sets_killed_status(self):
        task_id = register_dream_task(sessions_reviewing=1)
        kill_dream_task(task_id)
        task = get_task(task_id)
        assert task.status == TaskStatus.KILLED

    def test_signals_abort_event(self):
        evt = threading.Event()
        task_id = register_dream_task(sessions_reviewing=1, abort_event=evt)
        assert not evt.is_set()
        kill_dream_task(task_id)
        assert evt.is_set()

    def test_sets_notified(self):
        task_id = register_dream_task(sessions_reviewing=1)
        kill_dream_task(task_id)
        task = get_task(task_id)
        assert task.notified is True

    def test_noop_on_nonexistent_task(self):
        kill_dream_task("d_nonexistent")  # Should not raise

    def test_noop_on_terminal_task(self):
        task_id = register_dream_task(sessions_reviewing=1)
        complete_dream_task(task_id)
        kill_dream_task(task_id)
        task = get_task(task_id)
        assert task.status == TaskStatus.COMPLETED  # Unchanged


class TestDreamTaskRegistration:
    """Tests for the DREAM_TASK registration constant."""

    def test_task_name(self):
        assert DREAM_TASK.name == "DreamTask"

    def test_task_type(self):
        assert DREAM_TASK.type == TaskType.DREAM

    def test_kill_callable(self):
        assert DREAM_TASK.kill is kill_dream_task


# ===========================================================================
# ConsolidationLock
# ===========================================================================


class TestReadLastConsolidatedAt:
    """Tests for read_last_consolidated_at."""

    def test_returns_zero_when_no_file(self, tmp_path):
        assert read_last_consolidated_at(str(tmp_path)) == 0.0

    def test_returns_mtime_when_file_exists(self, tmp_path):
        lock = tmp_path / LOCK_FILE_NAME
        lock.write_text("1234")
        mtime = lock.stat().st_mtime
        assert read_last_consolidated_at(str(tmp_path)) == mtime


class TestTryAcquireConsolidationLock:
    """Tests for try_acquire_consolidation_lock."""

    def test_acquires_when_no_file(self, tmp_path):
        result = try_acquire_consolidation_lock(str(tmp_path))
        assert result is not None
        assert result == 0.0
        lock = tmp_path / LOCK_FILE_NAME
        assert lock.exists()
        assert lock.read_text().strip() == str(os.getpid())

    def test_acquires_when_holder_dead(self, tmp_path):
        lock = tmp_path / LOCK_FILE_NAME
        lock.write_text("999999999")  # Nonexistent PID
        result = try_acquire_consolidation_lock(str(tmp_path))
        assert result is not None

    def test_blocked_when_holder_alive(self, tmp_path):
        lock = tmp_path / LOCK_FILE_NAME
        lock.write_text(str(os.getpid()))  # Current process — alive
        result = try_acquire_consolidation_lock(str(tmp_path))
        assert result is None


class TestRollbackConsolidationLock:
    """Tests for rollback_consolidation_lock."""

    def test_removes_file_when_prior_zero(self, tmp_path):
        lock = tmp_path / LOCK_FILE_NAME
        lock.write_text("1234")
        rollback_consolidation_lock(str(tmp_path), 0.0)
        assert not lock.exists()

    def test_rewinds_mtime_when_prior_nonzero(self, tmp_path):
        lock = tmp_path / LOCK_FILE_NAME
        lock.write_text("1234")
        prior = time.time() - 3600
        rollback_consolidation_lock(str(tmp_path), prior)
        assert abs(lock.stat().st_mtime - prior) < 1.0


class TestListSessionsTouchedSince:
    """Tests for list_sessions_touched_since."""

    def test_returns_empty_for_nonexistent_dir(self, tmp_path):
        result = list_sessions_touched_since(str(tmp_path / "nope"), 0.0)
        assert result == []

    def test_returns_jsonl_files_after_timestamp(self, tmp_path):
        old_file = tmp_path / "old.jsonl"
        old_file.write_text("{}")
        old_time = time.time() - 7200
        os.utime(old_file, (old_time, old_time))

        new_file = tmp_path / "new.jsonl"
        new_file.write_text("{}")

        cutoff = time.time() - 3600
        result = list_sessions_touched_since(str(tmp_path), cutoff)
        assert len(result) == 1
        assert "new.jsonl" in result[0]

    def test_ignores_non_jsonl_files(self, tmp_path):
        (tmp_path / "data.txt").write_text("hi")
        result = list_sessions_touched_since(str(tmp_path), 0.0)
        assert result == []


class TestRecordConsolidation:
    """Tests for record_consolidation."""

    def test_creates_lock_file(self, tmp_path):
        record_consolidation(str(tmp_path))
        assert (tmp_path / LOCK_FILE_NAME).exists()

    def test_updates_mtime(self, tmp_path):
        lock = tmp_path / LOCK_FILE_NAME
        lock.write_text("old")
        old_mtime = lock.stat().st_mtime
        time.sleep(0.05)
        record_consolidation(str(tmp_path))
        new_mtime = lock.stat().st_mtime
        assert new_mtime >= old_mtime


# ===========================================================================
# ConsolidationPrompt
# ===========================================================================


class TestBuildConsolidationPrompt:
    """Tests for build_consolidation_prompt."""

    def test_contains_all_phases(self):
        prompt = build_consolidation_prompt("/mem", "/transcripts")
        assert "Phase 1: Read" in prompt
        assert "Phase 2: Scan" in prompt
        assert "Phase 3: Synthesize" in prompt
        assert "Phase 4: Write" in prompt

    def test_includes_memory_root_path(self):
        prompt = build_consolidation_prompt("/my/mem", "/tx")
        assert "/my/mem/MEMORY.md" in prompt

    def test_includes_transcript_dir(self):
        prompt = build_consolidation_prompt("/mem", "/my/transcripts")
        assert "/my/transcripts" in prompt

    def test_extra_appended(self):
        prompt = build_consolidation_prompt("/m", "/t", extra="Focus on auth changes")
        assert "Focus on auth changes" in prompt

    def test_no_extra_when_empty(self):
        prompt = build_consolidation_prompt("/m", "/t", extra="")
        # Should not end with empty extra section
        assert prompt.endswith(f"Stay within {MAX_ENTRYPOINT_LINES} lines and {MAX_ENTRYPOINT_BYTES} bytes.")

    def test_constants(self):
        assert ENTRYPOINT_NAME == "MEMORY.md"
        assert MAX_ENTRYPOINT_LINES == 200
        assert MAX_ENTRYPOINT_BYTES == 25_000


# ===========================================================================
# AutoDream
# ===========================================================================


class TestAutoDreamConfig:
    """Tests for AutoDreamConfig defaults."""

    def test_defaults(self):
        cfg = AutoDreamConfig()
        assert cfg.enabled is True
        assert cfg.min_hours == 24.0
        assert cfg.min_sessions == 5

    def test_session_scan_interval(self):
        assert SESSION_SCAN_INTERVAL == 600.0


class TestIsAutoDreamEnabled:
    """Tests for is_auto_dream_enabled."""

    def test_enabled_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CLAUDE_AUTO_DREAM", None)
            assert is_auto_dream_enabled() is True

    def test_disabled_with_zero(self):
        with mock.patch.dict(os.environ, {"CLAUDE_AUTO_DREAM": "0"}):
            assert is_auto_dream_enabled() is False

    def test_disabled_with_false(self):
        with mock.patch.dict(os.environ, {"CLAUDE_AUTO_DREAM": "false"}):
            assert is_auto_dream_enabled() is False


class TestGetDreamConfig:
    """Tests for get_dream_config."""

    def test_returns_config(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("CLAUDE_AUTO_DREAM", None)
            os.environ.pop("CLAUDE_DREAM_MIN_HOURS", None)
            os.environ.pop("CLAUDE_DREAM_MIN_SESSIONS", None)
            cfg = get_dream_config()
            assert isinstance(cfg, AutoDreamConfig)
            assert cfg.min_hours == 24.0
            assert cfg.min_sessions == 5


class TestGateSequence:
    """Tests for the auto-dream gate logic."""

    def test_disabled_gate_blocks(self, tmp_path):
        runner = init_auto_dream()
        config = AutoDreamConfig(enabled=False)
        result = runner(
            str(tmp_path), str(tmp_path / "sessions"),
            str(tmp_path / "mem"), str(tmp_path / "tx"),
            config=config,
        )
        assert result is None

    def test_time_gate_blocks_when_recent(self, tmp_path):
        lock_dir = tmp_path / "lock"
        lock_dir.mkdir()
        lock_file = lock_dir / LOCK_FILE_NAME
        lock_file.write_text("")  # Fresh mtime = now

        runner = init_auto_dream()
        config = AutoDreamConfig(enabled=True, min_hours=24, min_sessions=1)
        result = runner(
            str(lock_dir), str(tmp_path / "sessions"),
            str(tmp_path / "mem"), str(tmp_path / "tx"),
            config=config,
        )
        assert result is None

    def test_session_gate_blocks_when_few(self, tmp_path):
        lock_dir = tmp_path / "lock"
        lock_dir.mkdir()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        # Only 2 sessions (need 5)
        for i in range(2):
            (sessions_dir / f"s{i}.jsonl").write_text("{}")

        runner = init_auto_dream()
        config = AutoDreamConfig(enabled=True, min_hours=0, min_sessions=5)
        result = runner(
            str(lock_dir), str(sessions_dir),
            str(tmp_path / "mem"), str(tmp_path / "tx"),
            config=config,
        )
        assert result is None

    def test_all_gates_pass(self, tmp_path):
        lock_dir = tmp_path / "lock"
        lock_dir.mkdir()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        for i in range(5):
            (sessions_dir / f"s{i}.jsonl").write_text("{}")

        agent_called = {"count": 0}

        def mock_agent(**kwargs):
            agent_called["count"] += 1

        runner = init_auto_dream()
        config = AutoDreamConfig(enabled=True, min_hours=0, min_sessions=5)
        result = runner(
            str(lock_dir), str(sessions_dir),
            str(tmp_path / "mem"), str(tmp_path / "tx"),
            config=config, agent_fn=mock_agent,
        )
        assert result is not None
        assert result.startswith("d")
        assert agent_called["count"] == 1
        task = get_task(result)
        assert task.status == TaskStatus.COMPLETED

    def test_agent_failure_rolls_back(self, tmp_path):
        lock_dir = tmp_path / "lock"
        lock_dir.mkdir()
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        for i in range(5):
            (sessions_dir / f"s{i}.jsonl").write_text("{}")

        def failing_agent(**kwargs):
            raise RuntimeError("agent crashed")

        runner = init_auto_dream()
        config = AutoDreamConfig(enabled=True, min_hours=0, min_sessions=5)
        result = runner(
            str(lock_dir), str(sessions_dir),
            str(tmp_path / "mem"), str(tmp_path / "tx"),
            config=config, agent_fn=failing_agent,
        )
        assert result is not None
        task = get_task(result)
        assert task.status == TaskStatus.FAILED


class TestExecuteAutoDream:
    """Tests for execute_auto_dream entry point."""

    def test_delegates_to_runner(self, tmp_path):
        runner = init_auto_dream()
        config = AutoDreamConfig(enabled=False)
        result = execute_auto_dream(
            runner,
            lock_dir=str(tmp_path),
            sessions_dir=str(tmp_path),
            memory_root=str(tmp_path),
            transcript_dir=str(tmp_path),
            config=config,
        )
        assert result is None


# ===========================================================================
# Registry integration
# ===========================================================================


class TestRegistryIntegration:
    """Test that DreamTask is properly registered."""

    def test_dream_in_registry(self):
        try:
            from src.tasks import get_task_by_type
        except ImportError:
            pytest.skip("Task system (src.tasks) not available")
        task = get_task_by_type(TaskType.DREAM)
        assert task is not None
        assert task.name == "DreamTask"
        assert task.type == TaskType.DREAM
