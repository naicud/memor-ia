"""Memory path resolution — where memory files live."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import date
from pathlib import Path

# Constants
AUTO_MEM_DIRNAME = "memory"
AUTO_MEM_ENTRYPOINT_NAME = "MEMORY.md"
CLAUDE_CONFIG_DIR = ".claude"


def get_claude_config_home() -> Path:
    """~/.claude/ or CLAUDE_CODE_CONFIG_DIR override."""
    override = os.environ.get("CLAUDE_CODE_CONFIG_DIR")
    if override:
        return Path(override)
    return Path.home() / CLAUDE_CONFIG_DIR


def get_project_dir(cwd: str) -> Path:
    """~/.claude/projects/{sanitized-cwd}/"""
    sanitized = _sanitize_path(cwd)
    return get_claude_config_home() / "projects" / sanitized


def get_auto_mem_path(cwd: str) -> Path:
    """~/.claude/projects/{cwd}/memory/"""
    return get_project_dir(cwd) / AUTO_MEM_DIRNAME


def get_auto_mem_entrypoint(cwd: str) -> Path:
    """~/.claude/projects/{cwd}/memory/MEMORY.md"""
    return get_auto_mem_path(cwd) / AUTO_MEM_ENTRYPOINT_NAME


def get_session_dir(cwd: str) -> Path:
    """Where session .jsonl files live."""
    return get_project_dir(cwd)


def get_transcript_path(cwd: str, session_id: str) -> Path:
    """Path for a specific session transcript."""
    return get_session_dir(cwd) / f"{session_id}.jsonl"


def get_session_memory_path(session_id: str) -> Path:
    """~/.claude/.session_memory/{session_id}.md"""
    return get_claude_config_home() / ".session_memory" / f"{session_id}.md"


def get_daily_log_path(cwd: str) -> Path:
    """memory/logs/YYYY/MM/YYYY-MM-DD.md"""
    today = date.today()
    return (
        get_auto_mem_path(cwd)
        / "logs"
        / str(today.year)
        / f"{today.month:02d}"
        / f"{today.strftime('%Y-%m-%d')}.md"
    )


def is_auto_mem_path(file_path: str, cwd: str) -> bool:
    """Check if path is within auto-memory directory (prevents traversal)."""
    try:
        mem_path = get_auto_mem_path(cwd).resolve()
        target = Path(file_path).resolve()
        return str(target).startswith(str(mem_path))
    except (ValueError, OSError):
        return False


def is_auto_memory_enabled() -> bool:
    """Check if auto-memory feature is enabled."""
    env_disable = os.environ.get("CLAUDE_CODE_DISABLE_AUTO_MEMORY", "").lower()
    if env_disable in ("1", "true"):
        return False
    if env_disable in ("0", "false"):
        return True
    if os.environ.get("CLAUDE_CODE_SIMPLE"):
        return False
    return True


def ensure_memory_dir_exists(cwd: str) -> Path:
    """Create memory directory if it doesn't exist."""
    mem_path = get_auto_mem_path(cwd)
    mem_path.mkdir(parents=True, exist_ok=True)
    return mem_path


def _sanitize_path(path: str) -> str:
    """Sanitize filesystem path for use as directory name.

    Uses a hash suffix for safety — prevents directory traversal while
    keeping the last path component for human readability.
    """
    normalized = os.path.normpath(os.path.abspath(path))
    h = hashlib.sha256(normalized.encode()).hexdigest()[:16]
    basename = Path(normalized).name or "root"
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", basename)
    return f"{safe}-{h}"
