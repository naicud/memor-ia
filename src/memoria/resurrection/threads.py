from __future__ import annotations

import threading
import time
import uuid

from .types import ThreadStatus, WorkThread

_MAX_SESSION_IDS = 200
_MAX_RELATED_FILES = 100


class ThreadTracker:
    """Tracks conversation threads across sessions."""

    def __init__(
        self, stale_days: float = 14.0, max_threads_per_user: int = 100
    ):
        self._threads: dict[str, dict[str, WorkThread]] = {}
        self._stale_days = stale_days
        self._max = max_threads_per_user
        self._lock = threading.RLock()

    def create_thread(
        self,
        user_id: str,
        title: str,
        description: str = "",
        session_id: str = "",
        files: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> WorkThread:
        """Create a new work thread."""
        now = time.time()
        thread = WorkThread(
            thread_id=uuid.uuid4().hex[:12],
            user_id=user_id,
            title=title,
            description=description,
            status=ThreadStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            session_ids=[session_id] if session_id else [],
            related_files=list(files) if files else [],
            tags=list(tags) if tags else [],
        )

        with self._lock:
            if user_id not in self._threads:
                self._threads[user_id] = {}
            user_threads = self._threads[user_id]

            # Enforce max limit — remove oldest completed first, then oldest overall
            if len(user_threads) >= self._max:
                self._evict_one(user_id)

            user_threads[thread.thread_id] = thread

        return thread

    def update_thread(
        self,
        user_id: str,
        thread_id: str,
        session_id: str = "",
        progress: float | None = None,
        context: str = "",
        status: ThreadStatus | None = None,
        files: list[str] | None = None,
    ) -> WorkThread | None:
        """Update an existing thread. Returns updated thread or None if not found."""
        with self._lock:
            thread = self._get_locked(user_id, thread_id)
            if thread is None:
                return None

            thread.updated_at = time.time()

            if session_id and session_id not in thread.session_ids:
                thread.session_ids.append(session_id)
                if len(thread.session_ids) > _MAX_SESSION_IDS:
                    thread.session_ids = thread.session_ids[-_MAX_SESSION_IDS:]
            if progress is not None:
                thread.progress = max(0.0, min(1.0, progress))
            if context:
                thread.last_context = context
            if status is not None:
                thread.status = status
            if files:
                for f in files:
                    if f not in thread.related_files:
                        thread.related_files.append(f)
                if len(thread.related_files) > _MAX_RELATED_FILES:
                    thread.related_files = thread.related_files[-_MAX_RELATED_FILES:]

            return thread

    def get_thread(self, user_id: str, thread_id: str) -> WorkThread | None:
        """Get a specific thread."""
        with self._lock:
            return self._get_locked(user_id, thread_id)

    def get_active_threads(self, user_id: str) -> list[WorkThread]:
        """Get all active/paused threads for user, sorted by updated_at desc."""
        with self._lock:
            user_threads = self._threads.get(user_id, {})
            active = [
                t
                for t in user_threads.values()
                if t.status in (ThreadStatus.ACTIVE, ThreadStatus.PAUSED)
            ]
            return sorted(active, key=lambda t: t.updated_at, reverse=True)

    def complete_thread(self, user_id: str, thread_id: str) -> bool:
        """Mark a thread as completed."""
        with self._lock:
            thread = self._get_locked(user_id, thread_id)
            if thread is None:
                return False
            thread.status = ThreadStatus.COMPLETED
            thread.progress = 1.0
            thread.updated_at = time.time()
            return True

    def mark_stale(self, user_id: str, now: float | None = None) -> list[str]:
        """Mark threads not updated in stale_days as stale. Returns IDs marked."""
        if now is None:
            now = time.time()
        cutoff = now - self._stale_days * 86400.0
        marked: list[str] = []

        with self._lock:
            user_threads = self._threads.get(user_id, {})
            for t in user_threads.values():
                if t.status in (ThreadStatus.ACTIVE, ThreadStatus.PAUSED):
                    if t.updated_at < cutoff:
                        t.status = ThreadStatus.STALE
                        marked.append(t.thread_id)

        return marked

    def find_relevant(
        self, user_id: str, context: str, limit: int = 5
    ) -> list[WorkThread]:
        """Find threads relevant to a context string (keyword matching)."""
        if not context:
            return []

        context_words = set(
            w.strip(".,!?;:\"'()[]{}#").lower()
            for w in context.split()
            if len(w.strip(".,!?;:\"'()[]{}#")) >= 3
        )

        if not context_words:
            return []

        with self._lock:
            user_threads = self._threads.get(user_id, {})
            scored: list[tuple[float, WorkThread]] = []

            for t in user_threads.values():
                thread_text = f"{t.title} {t.description} {t.last_context} {' '.join(t.tags)}"
                thread_words = set(
                    w.strip(".,!?;:\"'()[]{}#").lower()
                    for w in thread_text.split()
                    if len(w.strip(".,!?;:\"'()[]{}#")) >= 3
                )
                overlap = len(context_words & thread_words)
                if overlap > 0:
                    scored.append((overlap, t))

            scored.sort(key=lambda x: x[0], reverse=True)
            return [t for _, t in scored[:limit]]

    def get_thread_history(self, user_id: str, thread_id: str) -> dict:
        """Get thread timeline: sessions, progress, files."""
        with self._lock:
            thread = self._get_locked(user_id, thread_id)
            if thread is None:
                return {}
            return {
                "thread_id": thread.thread_id,
                "title": thread.title,
                "status": thread.status.value,
                "sessions": list(thread.session_ids),
                "progress": thread.progress,
                "files": list(thread.related_files),
                "created_at": thread.created_at,
                "updated_at": thread.updated_at,
            }

    def stats(self, user_id: str = "") -> dict:
        """Thread statistics."""
        with self._lock:
            if user_id:
                user_threads = self._threads.get(user_id, {})
                by_status: dict[str, int] = {}
                for t in user_threads.values():
                    by_status[t.status.value] = by_status.get(t.status.value, 0) + 1
                return {
                    "total_threads": len(user_threads),
                    "by_status": by_status,
                }

            total = sum(len(v) for v in self._threads.values())
            return {
                "total_threads": total,
                "users": len(self._threads),
                "max_per_user": self._max,
            }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_locked(self, user_id: str, thread_id: str) -> WorkThread | None:
        """Get thread while already holding the lock."""
        return self._threads.get(user_id, {}).get(thread_id)

    def _evict_one(self, user_id: str) -> None:
        """Remove oldest completed thread, or oldest overall if none completed."""
        user_threads = self._threads.get(user_id, {})
        if not user_threads:
            return

        completed = [
            t for t in user_threads.values() if t.status == ThreadStatus.COMPLETED
        ]
        if completed:
            oldest = min(completed, key=lambda t: t.updated_at)
        else:
            oldest = min(user_threads.values(), key=lambda t: t.updated_at)

        del user_threads[oldest.thread_id]
