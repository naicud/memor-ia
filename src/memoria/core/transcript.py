"""JSONL transcript management for agent sessions."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Optional

from .paths import get_session_dir, get_transcript_path

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SessionTranscript:
    session_id: str
    path: Path
    _file: Optional[IO] = field(default=None, repr=False)

    def close(self) -> None:
        if self._file and not self._file.closed:
            self._file.close()
            self._file = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


@dataclass
class SessionInfo:
    session_id: str
    path: str
    mtime: float
    size: int


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


def create_session(cwd: str, session_id: str) -> SessionTranscript:
    """Create a new session transcript file, returning a handle for appending."""
    path = get_transcript_path(cwd, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = path.open("a", encoding="utf-8")
    return SessionTranscript(session_id=session_id, path=path, _file=fh)


def append_message(session: SessionTranscript, message: dict) -> None:
    """Append a JSON message as a single line to the transcript."""
    if session._file is None or session._file.closed:
        session._file = session.path.open("a", encoding="utf-8")
    line = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
    session._file.write(line + "\n")
    session._file.flush()


# ---------------------------------------------------------------------------
# Reading transcripts
# ---------------------------------------------------------------------------


def read_transcript(path: str | Path) -> list[dict]:
    """Read all messages from a JSONL transcript."""
    p = Path(path)
    if not p.exists():
        return []

    messages: list[dict] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                try:
                    messages.append(json.loads(stripped))
                except json.JSONDecodeError:
                    continue
    return messages


def read_head_and_tail(
    path: str | Path,
    head_n: int = 10,
    tail_n: int = 20,
) -> tuple[list[dict], list[dict]]:
    """Read the first *head_n* and last *tail_n* messages from a transcript.

    Useful for summarising long sessions without reading the entire file.
    """
    all_msgs = read_transcript(path)
    if not all_msgs:
        return [], []

    head = all_msgs[:head_n]
    tail = all_msgs[-tail_n:] if len(all_msgs) > head_n else []
    # Avoid overlap when transcript is short
    if len(all_msgs) <= head_n + tail_n:
        tail = all_msgs[head_n:]
    return head, tail


# ---------------------------------------------------------------------------
# Session listing / querying
# ---------------------------------------------------------------------------


def list_sessions(cwd: str) -> list[SessionInfo]:
    """List all session transcripts in the project directory."""
    session_dir = get_session_dir(cwd)
    if not session_dir.exists():
        return []

    sessions: list[SessionInfo] = []
    for entry in session_dir.iterdir():
        if entry.suffix != ".jsonl" or not entry.is_file():
            continue
        stat = entry.stat()
        sessions.append(
            SessionInfo(
                session_id=entry.stem,
                path=str(entry),
                mtime=stat.st_mtime,
                size=stat.st_size,
            )
        )
    sessions.sort(key=lambda s: s.mtime, reverse=True)
    return sessions


def list_sessions_touched_since(cwd: str, since_ts: float) -> list[str]:
    """Return session IDs modified after *since_ts* (epoch seconds)."""
    return [
        s.session_id
        for s in list_sessions(cwd)
        if s.mtime >= since_ts
    ]
