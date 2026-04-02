"""Tests for the Context Resurrection module."""

from __future__ import annotations

import time

import pytest

from memoria.resurrection import (
    CognitiveState,
    ResumeContext,
    ResumptionHint,
    SessionOutcome,
    SessionSnapshot,
    SnapshotManager,
    ThreadStatus,
    ThreadTracker,
    WorkItem,
    WorkThread,
)


# ── 1. TestSessionOutcome ────────────────────────────────────────────


class TestSessionOutcome:
    def test_all_values(self):
        assert SessionOutcome.COMPLETED.value == "completed"
        assert SessionOutcome.INTERRUPTED.value == "interrupted"
        assert SessionOutcome.PAUSED.value == "paused"
        assert SessionOutcome.ABANDONED.value == "abandoned"
        assert SessionOutcome.UNKNOWN.value == "unknown"

    def test_member_count(self):
        assert len(SessionOutcome) == 5


# ── 2. TestThreadStatus ──────────────────────────────────────────────


class TestThreadStatus:
    def test_all_values(self):
        assert ThreadStatus.ACTIVE.value == "active"
        assert ThreadStatus.PAUSED.value == "paused"
        assert ThreadStatus.COMPLETED.value == "completed"
        assert ThreadStatus.STALE.value == "stale"

    def test_member_count(self):
        assert len(ThreadStatus) == 4


# ── 3. TestWorkItem ──────────────────────────────────────────────────


class TestWorkItem:
    def test_creation(self):
        w = WorkItem(item_id="w1", description="Fix the bug")
        assert w.item_id == "w1"
        assert w.description == "Fix the bug"

    def test_defaults(self):
        w = WorkItem(item_id="w2", description="x")
        assert w.status == "in_progress"
        assert w.context == ""
        assert w.files_involved == []
        assert w.started_at == 0.0
        assert w.priority == 0.5


# ── 4. TestCognitiveState ────────────────────────────────────────────


class TestCognitiveState:
    def test_defaults(self):
        cs = CognitiveState()
        assert cs.emotional_state == "neutral"
        assert cs.focus_level == 0.7
        assert cs.momentum == 0.5
        assert cs.active_goals == []
        assert cs.open_questions == []

    def test_custom_emotional_state(self):
        cs = CognitiveState(emotional_state="frustrated")
        assert cs.emotional_state == "frustrated"


# ── 5. TestSessionSnapshot ───────────────────────────────────────────


class TestSessionSnapshot:
    def test_creation(self):
        snap = SessionSnapshot(
            snapshot_id="snap1",
            user_id="u1",
            session_id="s1",
            created_at=1000.0,
            outcome=SessionOutcome.COMPLETED,
            message_count=10,
            duration_minutes=30.0,
        )
        assert snap.snapshot_id == "snap1"
        assert snap.outcome == SessionOutcome.COMPLETED
        assert snap.message_count == 10

    def test_defaults(self):
        snap = SessionSnapshot(snapshot_id="s", user_id="u", session_id="ss")
        assert snap.outcome == SessionOutcome.UNKNOWN
        assert snap.duration_minutes == 0.0
        assert snap.key_decisions == []
        assert snap.metadata == {}
        assert isinstance(snap.cognitive_state, CognitiveState)


# ── 6. TestWorkThread ────────────────────────────────────────────────


class TestWorkThread:
    def test_creation(self):
        t = WorkThread(thread_id="t1", user_id="u1", title="Auth refactor")
        assert t.thread_id == "t1"
        assert t.title == "Auth refactor"
        assert t.status == ThreadStatus.ACTIVE

    def test_status_transitions(self):
        t = WorkThread(thread_id="t1", user_id="u1", title="x")
        t.status = ThreadStatus.PAUSED
        assert t.status == ThreadStatus.PAUSED
        t.status = ThreadStatus.COMPLETED
        assert t.status == ThreadStatus.COMPLETED


# ── 7. TestResumptionHint ────────────────────────────────────────────


class TestResumptionHint:
    def test_session_resume(self):
        h = ResumptionHint(hint_type="session_resume", title="Resume", description="d")
        assert h.hint_type == "session_resume"

    def test_pending_task(self):
        h = ResumptionHint(hint_type="pending_task", title="Task", description="d")
        assert h.priority == 0.5

    def test_all_fields(self):
        h = ResumptionHint(
            hint_type="open_question",
            title="Q",
            description="d",
            priority=0.9,
            source_snapshot_id="snap1",
            source_thread_id="t1",
            suggested_action="answer it",
            context="ctx",
        )
        assert h.source_thread_id == "t1"


# ── 8. TestResumeContext ─────────────────────────────────────────────


class TestResumeContext:
    def test_defaults(self):
        rc = ResumeContext(user_id="u1")
        assert rc.last_session_outcome == SessionOutcome.UNKNOWN
        assert rc.hints == []
        assert rc.active_threads == []
        assert rc.days_since_last_session == 0.0

    def test_full_assembly(self):
        rc = ResumeContext(
            user_id="u1",
            last_session_outcome=SessionOutcome.INTERRUPTED,
            hints=[ResumptionHint(hint_type="session_resume", title="R", description="d")],
            active_threads=[WorkThread(thread_id="t1", user_id="u1", title="T")],
            days_since_last_session=2.5,
            greeting_suggestion="Hey!",
        )
        assert len(rc.hints) == 1
        assert len(rc.active_threads) == 1
        assert rc.greeting_suggestion == "Hey!"


# ── 9. TestSnapshotCapture ───────────────────────────────────────────


class TestSnapshotCapture:
    def test_basic_capture(self):
        mgr = SnapshotManager()
        snap = mgr.capture("u1", "s1")
        assert snap.user_id == "u1"
        assert snap.session_id == "s1"
        assert len(snap.snapshot_id) == 12

    def test_capture_with_messages(self):
        mgr = SnapshotManager()
        msgs = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        snap = mgr.capture("u1", "s1", messages=msgs)
        assert snap.message_count == 2
        assert snap.last_messages_summary != ""

    def test_capture_with_files(self):
        mgr = SnapshotManager()
        snap = mgr.capture(
            "u1", "s1",
            working_files=["main.py", "test.py"],
            branch="feature/auth",
            project="myapp",
        )
        assert snap.cognitive_state.working_files == ["main.py", "test.py"]
        assert snap.cognitive_state.branch == "feature/auth"
        assert snap.cognitive_state.project == "myapp"

    def test_capture_outcome(self):
        mgr = SnapshotManager()
        snap = mgr.capture("u1", "s1", outcome=SessionOutcome.COMPLETED)
        assert snap.outcome == SessionOutcome.COMPLETED


# ── 10. TestSnapshotCaptureAnalysis ──────────────────────────────────


class TestSnapshotCaptureAnalysis:
    def test_extracts_goals(self):
        mgr = SnapshotManager()
        msgs = [{"role": "user", "content": "I need to fix the login page"}]
        snap = mgr.capture("u1", "s1", messages=msgs)
        assert len(snap.cognitive_state.active_goals) >= 1

    def test_extracts_questions(self):
        mgr = SnapshotManager()
        msgs = [
            {"role": "user", "content": "How does authentication work?"},
            {"role": "user", "content": "Why is this broken?"},
        ]
        snap = mgr.capture("u1", "s1", messages=msgs)
        assert len(snap.cognitive_state.open_questions) == 2

    def test_extracts_topics(self):
        mgr = SnapshotManager()
        msgs = [
            {"role": "user", "content": "authentication module refactor"},
            {"role": "user", "content": "authentication tests failing"},
        ]
        snap = mgr.capture("u1", "s1", messages=msgs)
        assert "authentication" in snap.cognitive_state.recent_topics

    def test_detects_error(self):
        mgr = SnapshotManager()
        msgs = [
            {"role": "assistant", "content": "Error: connection refused on port 5432"},
        ]
        snap = mgr.capture("u1", "s1", messages=msgs)
        assert "Error" in snap.cognitive_state.last_error or "error" in snap.cognitive_state.last_error.lower()


# ── 11. TestSnapshotEmotionalDetection ───────────────────────────────


class TestSnapshotEmotionalDetection:
    def setup_method(self):
        self.mgr = SnapshotManager()

    def test_frustration_keywords(self):
        msgs = [{"role": "user", "content": "This is broken and doesn't work"}]
        snap = self.mgr.capture("u1", "s1", messages=msgs)
        assert snap.cognitive_state.emotional_state == "frustrated"

    def test_frustration_punctuation(self):
        msgs = [{"role": "user", "content": "Why is this happening!!!"}]
        snap = self.mgr.capture("u1", "s1", messages=msgs)
        assert snap.cognitive_state.emotional_state == "frustrated"

    def test_satisfaction(self):
        msgs = [{"role": "user", "content": "This is perfect, thanks!"}]
        snap = self.mgr.capture("u1", "s1", messages=msgs)
        assert snap.cognitive_state.emotional_state == "satisfied"

    def test_confusion(self):
        msgs = [{"role": "user", "content": "I don't understand this at all"}]
        snap = self.mgr.capture("u1", "s1", messages=msgs)
        assert snap.cognitive_state.emotional_state == "confused"

    def test_neutral(self):
        msgs = [{"role": "user", "content": "Please update the config file"}]
        snap = self.mgr.capture("u1", "s1", messages=msgs)
        assert snap.cognitive_state.emotional_state == "neutral"


# ── 12. TestSnapshotMessageSummary ───────────────────────────────────


class TestSnapshotMessageSummary:
    def test_summarizes_last_messages(self):
        mgr = SnapshotManager()
        msgs = [
            {"role": "user", "content": "Message one"},
            {"role": "assistant", "content": "Response one"},
            {"role": "user", "content": "Message two"},
        ]
        snap = mgr.capture("u1", "s1", messages=msgs)
        assert "[user]" in snap.last_messages_summary
        assert "Message" in snap.last_messages_summary

    def test_empty_messages(self):
        mgr = SnapshotManager()
        snap = mgr.capture("u1", "s1", messages=[])
        assert snap.last_messages_summary == ""

    def test_truncates_long_content(self):
        mgr = SnapshotManager()
        long_text = "x" * 200
        msgs = [{"role": "user", "content": long_text}]
        snap = mgr.capture("u1", "s1", messages=msgs)
        assert "..." in snap.last_messages_summary


# ── 13. TestSnapshotHistory ──────────────────────────────────────────


class TestSnapshotHistory:
    def test_get_latest(self):
        mgr = SnapshotManager()
        mgr.capture("u1", "s1")
        mgr.capture("u1", "s2")
        latest = mgr.get_latest("u1")
        assert latest is not None
        assert latest.session_id == "s2"

    def test_get_latest_no_data(self):
        mgr = SnapshotManager()
        assert mgr.get_latest("u1") is None

    def test_get_history(self):
        mgr = SnapshotManager()
        for i in range(5):
            mgr.capture("u1", f"s{i}")
        history = mgr.get_history("u1", limit=3)
        assert len(history) == 3
        # Newest first
        assert history[0].session_id == "s4"

    def test_rotation(self):
        mgr = SnapshotManager(max_snapshots_per_user=3)
        for i in range(5):
            mgr.capture("u1", f"s{i}")
        history = mgr.get_history("u1", limit=10)
        assert len(history) == 3
        assert history[0].session_id == "s4"
        assert history[-1].session_id == "s2"

    def test_get_snapshot_by_id(self):
        mgr = SnapshotManager()
        snap = mgr.capture("u1", "s1")
        found = mgr.get_snapshot(snap.snapshot_id)
        assert found is not None
        assert found.snapshot_id == snap.snapshot_id

    def test_get_snapshot_not_found(self):
        mgr = SnapshotManager()
        assert mgr.get_snapshot("nonexistent") is None

    def test_stats(self):
        mgr = SnapshotManager()
        mgr.capture("u1", "s1")
        mgr.capture("u2", "s2")
        st = mgr.stats()
        assert st["total_snapshots"] == 2
        assert st["users"] == 2


# ── 14. TestResumeContextGeneration ──────────────────────────────────


class TestResumeContextGeneration:
    def test_no_snapshots(self):
        mgr = SnapshotManager()
        ctx = mgr.generate_resume_context("u1")
        assert ctx.user_id == "u1"
        assert "Welcome" in ctx.greeting_suggestion

    def test_hints_from_incomplete_tasks(self):
        mgr = SnapshotManager()
        msgs = [{"role": "user", "content": "I need to fix the login page"}]
        mgr.capture("u1", "s1", messages=msgs)
        ctx = mgr.generate_resume_context("u1")
        pending = [h for h in ctx.hints if h.hint_type == "pending_task"]
        assert len(pending) >= 1

    def test_hints_from_open_questions(self):
        mgr = SnapshotManager()
        msgs = [{"role": "user", "content": "How does the cache work?"}]
        mgr.capture("u1", "s1", messages=msgs)
        ctx = mgr.generate_resume_context("u1")
        q_hints = [h for h in ctx.hints if h.hint_type == "open_question"]
        assert len(q_hints) >= 1

    def test_hints_from_interrupted(self):
        mgr = SnapshotManager()
        mgr.capture("u1", "s1", outcome=SessionOutcome.INTERRUPTED)
        ctx = mgr.generate_resume_context("u1")
        resume_hints = [h for h in ctx.hints if h.hint_type == "session_resume"]
        assert len(resume_hints) == 1

    def test_days_since_last_session(self):
        mgr = SnapshotManager()
        snap = mgr.capture("u1", "s1")
        future = snap.created_at + 86400.0 * 3  # 3 days later
        ctx = mgr.generate_resume_context("u1", now=future)
        assert 2.9 < ctx.days_since_last_session < 3.1


# ── 15. TestResumeContextGreeting ────────────────────────────────────


class TestResumeContextGreeting:
    def test_long_absence(self):
        mgr = SnapshotManager()
        snap = mgr.capture("u1", "s1")
        future = snap.created_at + 86400.0 * 10
        ctx = mgr.generate_resume_context("u1", now=future)
        assert "been a while" in ctx.greeting_suggestion.lower()

    def test_interrupted_greeting(self):
        mgr = SnapshotManager()
        snap = mgr.capture("u1", "s1", outcome=SessionOutcome.INTERRUPTED)
        future = snap.created_at + 86400.0 * 2
        ctx = mgr.generate_resume_context("u1", now=future)
        assert "interrupted" in ctx.greeting_suggestion.lower()

    def test_paused_greeting(self):
        mgr = SnapshotManager()
        snap = mgr.capture("u1", "s1", outcome=SessionOutcome.PAUSED)
        future = snap.created_at + 3600.0
        ctx = mgr.generate_resume_context("u1", now=future)
        assert "continue" in ctx.greeting_suggestion.lower() or "paused" in ctx.greeting_suggestion.lower()

    def test_abandoned_greeting(self):
        mgr = SnapshotManager()
        snap = mgr.capture("u1", "s1", outcome=SessionOutcome.ABANDONED)
        future = snap.created_at + 86400.0 * 2
        ctx = mgr.generate_resume_context("u1", now=future)
        assert "left" in ctx.greeting_suggestion.lower() or "progress" in ctx.greeting_suggestion.lower()

    def test_same_day_greeting(self):
        mgr = SnapshotManager()
        snap = mgr.capture("u1", "s1")
        future = snap.created_at + 3600.0  # 1 hour
        ctx = mgr.generate_resume_context("u1", now=future)
        assert "again" in ctx.greeting_suggestion.lower() or "Hey" in ctx.greeting_suggestion


# ── 16. TestThreadCreation ───────────────────────────────────────────


class TestThreadCreation:
    def test_basic_create(self):
        tracker = ThreadTracker()
        t = tracker.create_thread("u1", "Auth refactor")
        assert t.title == "Auth refactor"
        assert t.user_id == "u1"
        assert len(t.thread_id) == 12
        assert t.status == ThreadStatus.ACTIVE

    def test_create_with_session(self):
        tracker = ThreadTracker()
        t = tracker.create_thread("u1", "T", session_id="s1")
        assert "s1" in t.session_ids

    def test_create_with_files_and_tags(self):
        tracker = ThreadTracker()
        t = tracker.create_thread("u1", "T", files=["a.py"], tags=["auth"])
        assert "a.py" in t.related_files
        assert "auth" in t.tags


# ── 17. TestThreadUpdate ─────────────────────────────────────────────


class TestThreadUpdate:
    def test_update_progress(self):
        tracker = ThreadTracker()
        t = tracker.create_thread("u1", "T")
        updated = tracker.update_thread("u1", t.thread_id, progress=0.5)
        assert updated is not None
        assert updated.progress == 0.5

    def test_update_context(self):
        tracker = ThreadTracker()
        t = tracker.create_thread("u1", "T")
        updated = tracker.update_thread("u1", t.thread_id, context="working on tests")
        assert updated is not None
        assert updated.last_context == "working on tests"

    def test_update_status(self):
        tracker = ThreadTracker()
        t = tracker.create_thread("u1", "T")
        updated = tracker.update_thread("u1", t.thread_id, status=ThreadStatus.PAUSED)
        assert updated is not None
        assert updated.status == ThreadStatus.PAUSED

    def test_update_files(self):
        tracker = ThreadTracker()
        t = tracker.create_thread("u1", "T", files=["a.py"])
        updated = tracker.update_thread("u1", t.thread_id, files=["b.py"])
        assert updated is not None
        assert "a.py" in updated.related_files
        assert "b.py" in updated.related_files

    def test_update_adds_session(self):
        tracker = ThreadTracker()
        t = tracker.create_thread("u1", "T", session_id="s1")
        updated = tracker.update_thread("u1", t.thread_id, session_id="s2")
        assert updated is not None
        assert "s1" in updated.session_ids
        assert "s2" in updated.session_ids

    def test_update_nonexistent(self):
        tracker = ThreadTracker()
        assert tracker.update_thread("u1", "nope") is None

    def test_progress_clamped(self):
        tracker = ThreadTracker()
        t = tracker.create_thread("u1", "T")
        updated = tracker.update_thread("u1", t.thread_id, progress=1.5)
        assert updated is not None
        assert updated.progress == 1.0

    def test_duplicate_session_not_added(self):
        tracker = ThreadTracker()
        t = tracker.create_thread("u1", "T", session_id="s1")
        tracker.update_thread("u1", t.thread_id, session_id="s1")
        assert t.session_ids.count("s1") == 1


# ── 18. TestThreadCompletion ─────────────────────────────────────────


class TestThreadCompletion:
    def test_complete(self):
        tracker = ThreadTracker()
        t = tracker.create_thread("u1", "T")
        assert tracker.complete_thread("u1", t.thread_id)
        thread = tracker.get_thread("u1", t.thread_id)
        assert thread is not None
        assert thread.status == ThreadStatus.COMPLETED
        assert thread.progress == 1.0

    def test_complete_nonexistent(self):
        tracker = ThreadTracker()
        assert not tracker.complete_thread("u1", "nope")


# ── 19. TestThreadStale ──────────────────────────────────────────────


class TestThreadStale:
    def test_mark_stale(self):
        tracker = ThreadTracker(stale_days=7.0)
        t = tracker.create_thread("u1", "Old thread")
        # Force old timestamp
        t.updated_at = time.time() - 86400.0 * 10
        marked = tracker.mark_stale("u1")
        assert t.thread_id in marked
        assert t.status == ThreadStatus.STALE

    def test_does_not_mark_recent(self):
        tracker = ThreadTracker(stale_days=7.0)
        tracker.create_thread("u1", "Fresh thread")
        marked = tracker.mark_stale("u1")
        assert marked == []

    def test_does_not_mark_completed(self):
        tracker = ThreadTracker(stale_days=7.0)
        t = tracker.create_thread("u1", "Done thread")
        tracker.complete_thread("u1", t.thread_id)
        t.updated_at = time.time() - 86400.0 * 10
        marked = tracker.mark_stale("u1")
        assert t.thread_id not in marked


# ── 20. TestThreadRelevance ──────────────────────────────────────────


class TestThreadRelevance:
    def test_find_by_keyword(self):
        tracker = ThreadTracker()
        tracker.create_thread("u1", "Authentication refactor", description="JWT tokens")
        tracker.create_thread("u1", "Database migration", description="Postgres upgrade")
        results = tracker.find_relevant("u1", "authentication tokens")
        assert len(results) >= 1
        assert results[0].title == "Authentication refactor"

    def test_find_empty_context(self):
        tracker = ThreadTracker()
        tracker.create_thread("u1", "T")
        assert tracker.find_relevant("u1", "") == []

    def test_find_no_match(self):
        tracker = ThreadTracker()
        tracker.create_thread("u1", "Auth refactor")
        results = tracker.find_relevant("u1", "completely unrelated zebra")
        assert results == []

    def test_find_respects_limit(self):
        tracker = ThreadTracker()
        for i in range(10):
            tracker.create_thread("u1", f"Thread about python {i}", description="python code")
        results = tracker.find_relevant("u1", "python code", limit=3)
        assert len(results) <= 3


# ── 21. TestThreadHistory ────────────────────────────────────────────


class TestThreadHistory:
    def test_get_history(self):
        tracker = ThreadTracker()
        t = tracker.create_thread("u1", "T", session_id="s1", files=["a.py"])
        tracker.update_thread("u1", t.thread_id, session_id="s2", progress=0.5)
        history = tracker.get_thread_history("u1", t.thread_id)
        assert history["thread_id"] == t.thread_id
        assert "s1" in history["sessions"]
        assert "s2" in history["sessions"]
        assert history["progress"] == 0.5

    def test_history_nonexistent(self):
        tracker = ThreadTracker()
        assert tracker.get_thread_history("u1", "nope") == {}

    def test_stats_per_user(self):
        tracker = ThreadTracker()
        tracker.create_thread("u1", "T1")
        tracker.create_thread("u1", "T2")
        st = tracker.stats("u1")
        assert st["total_threads"] == 2

    def test_stats_global(self):
        tracker = ThreadTracker()
        tracker.create_thread("u1", "T1")
        tracker.create_thread("u2", "T2")
        st = tracker.stats()
        assert st["total_threads"] == 2
        assert st["users"] == 2


# ── 22. TestEndToEnd ─────────────────────────────────────────────────


class TestEndToEnd:
    def test_capture_resume_cycle(self):
        mgr = SnapshotManager()
        tracker = ThreadTracker()

        # Session 1: user starts work
        msgs1 = [
            {"role": "user", "content": "I need to refactor the authentication module"},
            {"role": "assistant", "content": "Sure, let's start with the login handler."},
            {"role": "user", "content": "How does the JWT validation work?"},
        ]
        snap1 = mgr.capture("u1", "s1", messages=msgs1, outcome=SessionOutcome.PAUSED,
                            working_files=["auth.py"], branch="feature/auth")
        thread = tracker.create_thread("u1", "Auth refactor",
                                       description="Refactor authentication module",
                                       session_id="s1", files=["auth.py"], tags=["auth"])

        # Session 2: user comes back
        future = snap1.created_at + 86400.0 * 2
        ctx = mgr.generate_resume_context("u1", now=future)

        assert ctx.last_session_outcome == SessionOutcome.PAUSED
        assert ctx.days_since_last_session > 1.0
        assert len(ctx.hints) > 0

        # Thread is still active
        active = tracker.get_active_threads("u1")
        assert len(active) == 1
        assert active[0].thread_id == thread.thread_id

        # Relevant threads found
        relevant = tracker.find_relevant("u1", "authentication refactor")
        assert len(relevant) >= 1

    def test_interrupted_session_flow(self):
        mgr = SnapshotManager()

        msgs = [
            {"role": "user", "content": "This error is really frustrating!!!"},
            {"role": "assistant", "content": "Let me help debug that error."},
        ]
        snap = mgr.capture("u1", "s1", messages=msgs, outcome=SessionOutcome.INTERRUPTED)

        future = snap.created_at + 3600.0
        ctx = mgr.generate_resume_context("u1", now=future)

        assert ctx.last_session_outcome == SessionOutcome.INTERRUPTED
        resume_hints = [h for h in ctx.hints if h.hint_type == "session_resume"]
        assert len(resume_hints) == 1
        assert "interrupted" in ctx.greeting_suggestion.lower()

    def test_multi_session_thread_tracking(self):
        tracker = ThreadTracker()

        t = tracker.create_thread("u1", "API Design", session_id="s1")
        tracker.update_thread("u1", t.thread_id, session_id="s2", progress=0.3)
        tracker.update_thread("u1", t.thread_id, session_id="s3", progress=0.7,
                             context="finalizing endpoints")

        history = tracker.get_thread_history("u1", t.thread_id)
        assert len(history["sessions"]) == 3
        assert history["progress"] == 0.7


# ── 23. TestEdgeCases ────────────────────────────────────────────────


class TestEdgeCases:
    def test_no_snapshots_resume(self):
        mgr = SnapshotManager()
        ctx = mgr.generate_resume_context("unknown_user")
        assert ctx.user_id == "unknown_user"
        assert ctx.hints == []

    def test_empty_messages(self):
        mgr = SnapshotManager()
        snap = mgr.capture("u1", "s1", messages=[])
        assert snap.message_count == 0
        assert snap.cognitive_state.emotional_state == "neutral"

    def test_none_messages(self):
        mgr = SnapshotManager()
        snap = mgr.capture("u1", "s1", messages=None)
        assert snap.message_count == 0

    def test_malformed_messages(self):
        mgr = SnapshotManager()
        msgs = [
            {"role": "user"},  # missing content
            {"content": "no role"},  # missing role
            {},  # empty
        ]
        snap = mgr.capture("u1", "s1", messages=msgs)
        assert snap.message_count == 3

    def test_max_snapshots_rotation(self):
        mgr = SnapshotManager(max_snapshots_per_user=5)
        for i in range(10):
            mgr.capture("u1", f"s{i}")
        history = mgr.get_history("u1", limit=100)
        assert len(history) == 5

    def test_max_threads_rotation(self):
        tracker = ThreadTracker(max_threads_per_user=3)
        ids = []
        for i in range(5):
            t = tracker.create_thread("u1", f"Thread {i}")
            ids.append(t.thread_id)
        # Only 3 should remain
        active = tracker.stats("u1")
        assert active["total_threads"] == 3

    def test_get_active_threads_empty(self):
        tracker = ThreadTracker()
        assert tracker.get_active_threads("u1") == []

    def test_get_thread_not_found(self):
        tracker = ThreadTracker()
        assert tracker.get_thread("u1", "nope") is None

    def test_mark_stale_no_threads(self):
        tracker = ThreadTracker()
        assert tracker.mark_stale("u1") == []

    def test_snapshot_manager_stats_empty(self):
        mgr = SnapshotManager()
        st = mgr.stats()
        assert st["total_snapshots"] == 0
        assert st["users"] == 0
