"""Auto-dream orchestration — gated background memory consolidation.

Implements the 5-gate sequence that decides whether to launch a dream
agent after a session ends.  Gates are evaluated cheapest-first:

1. **Enabled** — is auto-dream turned on?
2. **Time** — has enough time elapsed since the last consolidation?
3. **Throttle** — have we scanned too recently?
4. **Sessions** — are there enough new session files?
5. **Lock** — can we acquire the consolidation lock?

Ported from ``src_origin/src/tasks/DreamTask/autoDream.ts``.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .lock import (
    list_sessions_touched_since,
    read_last_consolidated_at,
    record_consolidation,
    rollback_consolidation_lock,
    try_acquire_consolidation_lock,
)
from .prompt_template import build_consolidation_prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SESSION_SCAN_INTERVAL: float = 600.0
"""Minimum seconds between session directory scans (10 minutes)."""


@dataclass
class AutoDreamConfig:
    """Tuning knobs for the auto-dream feature."""

    enabled: bool = True
    min_hours: float = 24.0
    min_sessions: int = 5


def is_auto_dream_enabled() -> bool:
    """Check whether auto-dream is enabled via environment variable."""
    val = os.environ.get("CLAUDE_AUTO_DREAM", "1")
    return val not in ("0", "false", "no", "off")


def get_dream_config() -> AutoDreamConfig:
    """Build an :class:`AutoDreamConfig` from environment / defaults."""
    config = AutoDreamConfig(enabled=is_auto_dream_enabled())
    try:
        config.min_hours = float(os.environ.get("CLAUDE_DREAM_MIN_HOURS", "24"))
    except (ValueError, TypeError):
        pass
    try:
        config.min_sessions = int(os.environ.get("CLAUDE_DREAM_MIN_SESSIONS", "5"))
    except (ValueError, TypeError):
        pass
    return config


# ---------------------------------------------------------------------------
# Runner state (closure-based, mirrors TS pattern)
# ---------------------------------------------------------------------------


@dataclass
class _RunnerState:
    """Internal state held by the auto-dream runner closure."""

    last_scan_time: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)


def init_auto_dream() -> Callable[..., Optional[str]]:
    """Initialise auto-dream and return a runner callable.

    The returned callable has the signature::

        runner(lock_dir: str, sessions_dir: str, memory_root: str,
               transcript_dir: str, *, config: AutoDreamConfig | None = None,
               agent_fn: Callable | None = None) -> str | None

    It returns the dream task ID on success, or ``None`` if gated out.
    """
    state = _RunnerState()

    def runner(
        lock_dir: str,
        sessions_dir: str,
        memory_root: str,
        transcript_dir: str,
        *,
        config: AutoDreamConfig | None = None,
        agent_fn: Callable[..., None] | None = None,
    ) -> Optional[str]:
        return _run_auto_dream(
            state,
            lock_dir=lock_dir,
            sessions_dir=sessions_dir,
            memory_root=memory_root,
            transcript_dir=transcript_dir,
            config=config,
            agent_fn=agent_fn,
        )

    return runner


# ---------------------------------------------------------------------------
# Gate sequence
# ---------------------------------------------------------------------------


def _run_auto_dream(
    state: _RunnerState,
    *,
    lock_dir: str,
    sessions_dir: str,
    memory_root: str,
    transcript_dir: str,
    config: AutoDreamConfig | None = None,
    agent_fn: Callable[..., None] | None = None,
) -> Optional[str]:
    """Execute the 5-gate sequence and optionally launch a dream agent.

    Returns the task ID if a dream was started, otherwise ``None``.
    """
    if config is None:
        config = get_dream_config()

    # Gate 1: enabled
    if not config.enabled:
        logger.debug("Auto-dream gate: disabled")
        return None

    # Gate 2: time — enough hours since last consolidation?
    last_consolidated = read_last_consolidated_at(lock_dir)
    if last_consolidated > 0:
        elapsed_hours = (time.time() - last_consolidated) / 3600.0
        if elapsed_hours < config.min_hours:
            logger.debug(
                "Auto-dream gate: time (%.1fh < %.1fh)",
                elapsed_hours,
                config.min_hours,
            )
            return None

    # Gate 3: throttle — don't scan too frequently
    now = time.time()
    with state.lock:
        if (now - state.last_scan_time) < SESSION_SCAN_INTERVAL:
            logger.debug("Auto-dream gate: throttle")
            return None
        state.last_scan_time = now

    # Gate 4: sessions — enough new sessions?
    sessions = list_sessions_touched_since(sessions_dir, last_consolidated)
    if len(sessions) < config.min_sessions:
        logger.debug(
            "Auto-dream gate: sessions (%d < %d)",
            len(sessions),
            config.min_sessions,
        )
        return None

    # Gate 5: lock — can we acquire?
    prior_mtime = try_acquire_consolidation_lock(lock_dir)
    if prior_mtime is None:
        logger.debug("Auto-dream gate: lock held")
        return None

    # All gates passed — launch dream
    logger.info(
        "All auto-dream gates passed (sessions=%d, prior_mtime=%.1f)",
        len(sessions),
        prior_mtime,
    )

    from memoria.consolidation.dream import (
        complete_dream_task,
        fail_dream_task,
        register_dream_task,
    )
    try:
        from src.utils.task_framework import get_task as _get_task
        from src.utils.task_framework import update_task
    except ImportError:
        _get_task = None  # type: ignore[assignment]
        update_task = None  # type: ignore[assignment]

    abort_event = threading.Event()
    task_id = register_dream_task(
        sessions_reviewing=len(sessions),
        abort_event=abort_event,
    )

    # Store prior_mtime on the task for rollback on kill
    if update_task is not None:

        def _set_prior_mtime(t: Any) -> Any:
            import copy

            u = copy.copy(t)
            u.prior_mtime = prior_mtime
            return u

        update_task(task_id, _set_prior_mtime)

    # Execute the dream agent (synchronous — caller is expected to run
    # this on a background thread or after the main session ends).
    try:
        if agent_fn is not None:
            prompt = build_consolidation_prompt(memory_root, transcript_dir)
            agent_fn(
                task_id=task_id,
                prompt=prompt,
                abort_event=abort_event,
                sessions=sessions,
            )
        complete_dream_task(task_id)
        record_consolidation(lock_dir)
    except Exception:
        logger.exception("Dream agent failed for task %s", task_id)
        fail_dream_task(task_id)
        rollback_consolidation_lock(lock_dir, prior_mtime)

    return task_id


def execute_auto_dream(
    runner: Callable[..., Optional[str]],
    *,
    lock_dir: str,
    sessions_dir: str,
    memory_root: str,
    transcript_dir: str,
    config: AutoDreamConfig | None = None,
    agent_fn: Callable[..., None] | None = None,
) -> Optional[str]:
    """Public entry point for triggering auto-dream from stop hooks.

    Delegates to the *runner* closure returned by :func:`init_auto_dream`.
    """
    return runner(
        lock_dir,
        sessions_dir,
        memory_root,
        transcript_dir,
        config=config,
        agent_fn=agent_fn,
    )


__all__ = [
    "AutoDreamConfig",
    "SESSION_SCAN_INTERVAL",
    "execute_auto_dream",
    "get_dream_config",
    "init_auto_dream",
    "is_auto_dream_enabled",
]
