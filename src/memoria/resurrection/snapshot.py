from __future__ import annotations

import threading
import time
import uuid
from collections import Counter

from .types import (
    CognitiveState,
    ResumeContext,
    ResumptionHint,
    SessionOutcome,
    SessionSnapshot,
    WorkItem,
)


_FRUSTRATION_KEYWORDS = {
    "broken", "error", "fail", "failed", "bug", "crash", "wrong",
    "doesn't work", "does not work", "not working", "impossible",
}
_FRUSTRATION_PUNCTUATION = {"!!!", "???"}

_SATISFACTION_KEYWORDS = {
    "perfect", "thanks", "thank you", "great", "works", "awesome",
    "excellent", "amazing", "nice", "good job", "well done", "love it",
}

_CONFUSION_KEYWORDS = {
    "don't understand", "do not understand", "confused", "confusing",
    "what do you mean", "unclear", "makes no sense", "lost",
}

_GOAL_KEYWORDS = {
    "working on", "need to", "todo", "want to", "trying to",
    "have to", "must", "goal is", "plan to", "should",
}


class SnapshotManager:
    """Manages session snapshots — capture, restore, list."""

    def __init__(self, max_snapshots_per_user: int = 50):
        self._snapshots: dict[str, list[SessionSnapshot]] = {}
        self._max = max_snapshots_per_user
        self._lock = threading.RLock()

    def capture(
        self,
        user_id: str,
        session_id: str,
        messages: list[dict] | None = None,
        duration_minutes: float = 0.0,
        outcome: SessionOutcome = SessionOutcome.UNKNOWN,
        working_files: list[str] | None = None,
        branch: str = "",
        project: str = "",
    ) -> SessionSnapshot:
        """Capture a session snapshot. Analyzes messages to build cognitive state."""
        messages = messages or []
        working_files = working_files or []

        cognitive = self._analyze_messages(messages)
        cognitive.working_files = list(working_files)
        cognitive.branch = branch
        cognitive.project = project

        snapshot = SessionSnapshot(
            snapshot_id=uuid.uuid4().hex[:12],
            user_id=user_id,
            session_id=session_id,
            created_at=time.time(),
            outcome=outcome,
            cognitive_state=cognitive,
            message_count=len(messages),
            duration_minutes=duration_minutes,
            key_decisions=[],
            last_messages_summary=self._summarize_messages(messages),
        )

        with self._lock:
            if user_id not in self._snapshots:
                self._snapshots[user_id] = []
            self._snapshots[user_id].append(snapshot)
            if len(self._snapshots[user_id]) > self._max:
                self._snapshots[user_id] = self._snapshots[user_id][-self._max :]

        return snapshot

    def get_latest(self, user_id: str) -> SessionSnapshot | None:
        """Get the most recent snapshot for a user."""
        with self._lock:
            snaps = self._snapshots.get(user_id, [])
            return snaps[-1] if snaps else None

    def get_snapshot(self, snapshot_id: str) -> SessionSnapshot | None:
        """Get a specific snapshot by ID."""
        with self._lock:
            for snaps in self._snapshots.values():
                for s in snaps:
                    if s.snapshot_id == snapshot_id:
                        return s
        return None

    def get_history(self, user_id: str, limit: int = 10) -> list[SessionSnapshot]:
        """Get snapshot history for user, newest first."""
        with self._lock:
            snaps = self._snapshots.get(user_id, [])
            return list(reversed(snaps[-limit:]))

    def generate_resume_context(
        self, user_id: str, now: float | None = None
    ) -> ResumeContext:
        """Generate a full resumption context for a user starting a new session."""
        if now is None:
            now = time.time()
        latest = self.get_latest(user_id)

        if latest is None:
            return ResumeContext(
                user_id=user_id,
                greeting_suggestion="Welcome! What would you like to work on today?",
            )

        days_since = (now - latest.created_at) / 86400.0
        hints: list[ResumptionHint] = []

        # Incomplete tasks → pending_task hints
        for goal in latest.cognitive_state.active_goals:
            if goal.status in ("in_progress", "blocked"):
                hints.append(
                    ResumptionHint(
                        hint_type="pending_task",
                        title=f"Pending: {goal.description[:60]}",
                        description=goal.description,
                        priority=goal.priority,
                        source_snapshot_id=latest.snapshot_id,
                        suggested_action=f"Continue working on: {goal.description}",
                        context=goal.context,
                    )
                )

        # Open questions → open_question hints
        for q in latest.cognitive_state.open_questions:
            hints.append(
                ResumptionHint(
                    hint_type="open_question",
                    title=f"Open question: {q[:60]}",
                    description=q,
                    priority=0.6,
                    source_snapshot_id=latest.snapshot_id,
                    suggested_action=f"Address the question: {q}",
                )
            )

        # Interrupted sessions → session_resume hints
        if latest.outcome == SessionOutcome.INTERRUPTED:
            hints.append(
                ResumptionHint(
                    hint_type="session_resume",
                    title="Resume interrupted session",
                    description=latest.last_messages_summary or "Session was interrupted",
                    priority=0.9,
                    source_snapshot_id=latest.snapshot_id,
                    suggested_action="Pick up where you left off",
                    context=latest.cognitive_state.context_summary,
                )
            )

        # Generate greeting
        greeting = self._generate_greeting(latest, days_since)

        return ResumeContext(
            user_id=user_id,
            last_session_outcome=latest.outcome,
            hints=sorted(hints, key=lambda h: h.priority, reverse=True),
            days_since_last_session=days_since,
            greeting_suggestion=greeting,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _analyze_messages(self, messages: list[dict]) -> CognitiveState:
        """Analyze messages to build cognitive state."""
        if not messages:
            return CognitiveState()

        user_messages = [
            m for m in messages
            if isinstance(m, dict) and m.get("role") == "user" and m.get("content")
        ]
        all_contents = [
            m.get("content", "")
            for m in messages
            if isinstance(m, dict) and m.get("content")
        ]

        # Active goals
        goals: list[WorkItem] = []
        for msg in user_messages:
            content = msg.get("content", "").lower()
            for kw in _GOAL_KEYWORDS:
                if kw in content:
                    goals.append(
                        WorkItem(
                            item_id=uuid.uuid4().hex[:8],
                            description=msg["content"].strip()[:120],
                        )
                    )
                    break

        # Open questions
        questions: list[str] = []
        for msg in user_messages:
            content = msg.get("content", "").strip()
            if content.endswith("?"):
                questions.append(content[:200])

        # Recent topics (frequent words ≥4 chars)
        word_counter: Counter[str] = Counter()
        for c in all_contents:
            for w in c.lower().split():
                cleaned = w.strip(".,!?;:\"'()[]{}#")
                if len(cleaned) >= 4:
                    word_counter[cleaned] += 1
        topics = [w for w, _ in word_counter.most_common(10)]

        # Emotional state
        emotional = self._detect_emotional_state(messages)

        # Last error
        last_error = ""
        for msg in reversed(messages):
            if not isinstance(msg, dict):
                continue
            c = msg.get("content", "").lower()
            if "error" in c or "traceback" in c or "exception" in c:
                last_error = msg.get("content", "")[:200]
                break

        # Context summary
        summary = self._summarize_messages(messages, last_n=3)

        # Momentum — rough heuristic based on message count and emotional state
        momentum = 0.5
        if len(messages) > 10:
            momentum = 0.7
        if emotional == "frustrated":
            momentum = max(0.2, momentum - 0.3)
        elif emotional == "satisfied":
            momentum = min(1.0, momentum + 0.2)

        return CognitiveState(
            active_goals=goals,
            open_questions=questions,
            recent_topics=topics,
            emotional_state=emotional,
            focus_level=min(1.0, 0.5 + len(messages) * 0.02),
            context_summary=summary,
            last_error=last_error,
            momentum=momentum,
        )

    def _detect_emotional_state(self, messages: list[dict]) -> str:
        """Detect emotional state from message patterns."""
        if not messages:
            return "neutral"

        user_texts: list[str] = []
        for m in messages:
            if isinstance(m, dict) and m.get("role") == "user" and m.get("content"):
                user_texts.append(m["content"])

        if not user_texts:
            return "neutral"

        combined = " ".join(user_texts).lower()

        # Check frustration
        for kw in _FRUSTRATION_KEYWORDS:
            if kw in combined:
                return "frustrated"
        for p in _FRUSTRATION_PUNCTUATION:
            if p in " ".join(user_texts):
                return "frustrated"

        # Check satisfaction
        for kw in _SATISFACTION_KEYWORDS:
            if kw in combined:
                return "satisfied"

        # Check confusion
        for kw in _CONFUSION_KEYWORDS:
            if kw in combined:
                return "confused"

        return "neutral"

    def _summarize_messages(self, messages: list[dict], last_n: int = 3) -> str:
        """Create brief summary of last N messages."""
        if not messages:
            return ""

        recent = messages[-last_n:]
        parts: list[str] = []
        for m in recent:
            if not isinstance(m, dict):
                continue
            role = m.get("role", "unknown")
            content = m.get("content", "")
            if not content:
                continue
            truncated = content[:100] + ("..." if len(content) > 100 else "")
            parts.append(f"[{role}] {truncated}")

        return " | ".join(parts)

    def _generate_greeting(
        self, snapshot: SessionSnapshot, days_since: float
    ) -> str:
        """Generate a greeting suggestion based on context."""
        outcome = snapshot.outcome
        goals = snapshot.cognitive_state.active_goals

        if days_since > 7:
            return "Welcome back! It's been a while. Would you like to review where you left off?"
        if days_since > 1:
            base = "Welcome back!"
        else:
            base = "Hey again!"

        if outcome == SessionOutcome.INTERRUPTED:
            return f"{base} Looks like your last session was interrupted. Want to pick up where you left off?"
        if outcome == SessionOutcome.PAUSED:
            return f"{base} Ready to continue where you paused?"
        if outcome == SessionOutcome.ABANDONED:
            return f"{base} You left some work in progress last time. Want to revisit it?"
        if goals:
            goal_desc = goals[0].description[:60]
            return f"{base} Last time you were working on: {goal_desc}"

        return f"{base} What would you like to work on?"

    def stats(self) -> dict:
        """Return snapshot statistics."""
        with self._lock:
            total = sum(len(v) for v in self._snapshots.values())
            return {
                "total_snapshots": total,
                "users": len(self._snapshots),
                "max_per_user": self._max,
            }
