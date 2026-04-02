"""Consolidation lock — multi-process file lock with mtime-based tracking.

The lock file serves two purposes:
1. **Mutual exclusion** — prevents concurrent dream agents from running.
2. **Timestamp tracking** — ``mtime`` records when the last consolidation
   finished so gating logic can check ``min_hours`` without extra state.

Ported from ``src_origin/src/tasks/DreamTask/consolidationLock.ts``.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOCK_FILE_NAME: str = ".consolidate-lock"
"""Name of the lock file placed inside the lock directory."""

HOLDER_STALE_S: float = 3600.0
"""A lock held longer than this (seconds) is considered stale and reclaimable."""

# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def read_last_consolidated_at(lock_dir: str) -> float:
    """Return the ``mtime`` of the lock file, or ``0.0`` if absent.

    The mtime represents the last time consolidation completed successfully.
    """
    lock_path = Path(lock_dir) / LOCK_FILE_NAME
    try:
        return lock_path.stat().st_mtime
    except FileNotFoundError:
        return 0.0
    except OSError:
        logger.debug("Cannot stat lock file %s", lock_path)
        return 0.0


# ---------------------------------------------------------------------------
# Acquire
# ---------------------------------------------------------------------------


def try_acquire_consolidation_lock(lock_dir: str) -> Optional[float]:
    """Attempt to acquire the consolidation lock.

    Returns the **prior mtime** on success (``0.0`` if the file did not
    exist), or ``None`` if the lock is already held by another process.

    Acquisition strategy:
    1. Read current mtime (if file exists).
    2. Write our PID to the file.
    3. Re-read the file to verify we are the holder (race check).
    4. If another process won, return ``None``.
    """
    lock_path = Path(lock_dir) / LOCK_FILE_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    prior_mtime = 0.0
    try:
        stat = lock_path.stat()
        prior_mtime = stat.st_mtime
        # Check for stale lock
        age = time.time() - stat.st_mtime
        if age < HOLDER_STALE_S:
            # File exists and is fresh — check if it's actively held.
            try:
                content = lock_path.read_text().strip()
                if content:
                    pid = int(content)
                    # Check if the holder process is still alive
                    try:
                        os.kill(pid, 0)
                        # Process is alive — lock is held
                        logger.debug("Lock held by living process %d", pid)
                        return None
                    except (ProcessLookupError, PermissionError):
                        # Process is dead — stale lock, we can reclaim
                        logger.debug("Reclaiming lock from dead process %d", pid)
            except (ValueError, OSError):
                pass
    except FileNotFoundError:
        pass
    except OSError:
        logger.debug("Cannot stat lock file %s", lock_path)
        return None

    # Write our PID
    my_pid = str(os.getpid())
    try:
        lock_path.write_text(my_pid)
    except OSError:
        logger.warning("Cannot write lock file %s", lock_path)
        return None

    # Race check — re-read to confirm we are the holder
    try:
        content = lock_path.read_text().strip()
        if content != my_pid:
            logger.debug("Lost lock race to another process")
            return None
    except OSError:
        return None

    logger.info("Acquired consolidation lock (prior_mtime=%.1f)", prior_mtime)
    return prior_mtime


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


def rollback_consolidation_lock(lock_dir: str, prior_mtime: float) -> None:
    """Rewind the lock file mtime to *prior_mtime*.

    If *prior_mtime* is ``0.0`` (no prior lock existed), the lock file is
    deleted entirely so gating logic treats the state as "never consolidated".
    """
    lock_path = Path(lock_dir) / LOCK_FILE_NAME
    if prior_mtime == 0.0:
        try:
            lock_path.unlink(missing_ok=True)
            logger.debug("Removed lock file (rollback to epoch)")
        except OSError:
            logger.warning("Cannot remove lock file %s", lock_path)
        return

    try:
        os.utime(lock_path, (prior_mtime, prior_mtime))
        logger.debug("Rolled back lock mtime to %.1f", prior_mtime)
    except OSError:
        logger.warning("Cannot rollback lock mtime on %s", lock_path)


# ---------------------------------------------------------------------------
# Session scanning
# ---------------------------------------------------------------------------


def list_sessions_touched_since(
    sessions_dir: str,
    since_ts: float,
) -> list[str]:
    """Return paths of ``.jsonl`` session files modified after *since_ts*.

    Only files directly inside *sessions_dir* are considered (no recursion).
    """
    result: list[str] = []
    sessions_path = Path(sessions_dir)
    if not sessions_path.is_dir():
        return result

    for entry in sessions_path.iterdir():
        if not entry.is_file() or entry.suffix != ".jsonl":
            continue
        try:
            if entry.stat().st_mtime > since_ts:
                result.append(str(entry))
        except OSError:
            continue
    return result


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------


def record_consolidation(lock_dir: str) -> None:
    """Stamp the lock file with the current time.

    Called after a manual ``/dream`` command or when the dream agent
    finishes successfully.  The mtime update resets the time-gate for
    :func:`auto_dream`.
    """
    lock_path = Path(lock_dir) / LOCK_FILE_NAME
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_path.touch()
        logger.debug("Recorded consolidation at %.1f", time.time())
    except OSError:
        logger.warning("Cannot touch lock file %s", lock_path)


__all__ = [
    "HOLDER_STALE_S",
    "LOCK_FILE_NAME",
    "list_sessions_touched_since",
    "read_last_consolidated_at",
    "record_consolidation",
    "rollback_consolidation_lock",
    "try_acquire_consolidation_lock",
]
