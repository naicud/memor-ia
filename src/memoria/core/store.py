"""Read/write/update memory files and MEMORY.md index management."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .paths import ensure_memory_dir_exists, get_auto_mem_entrypoint, get_auto_mem_path
from .types import MemoryFrontmatter, MemoryType, format_frontmatter, parse_frontmatter

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MAX_LINES = 200
DEFAULT_MAX_BYTES = 25_000

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class EntrypointTruncation:
    content: str
    line_count: int
    byte_count: int
    was_line_truncated: bool
    was_byte_truncated: bool


# ---------------------------------------------------------------------------
# Low-level read / write
# ---------------------------------------------------------------------------


def read_memory_file(path: str | Path) -> tuple[MemoryFrontmatter, str]:
    """Read a memory file and return ``(frontmatter, body)``."""
    text = Path(path).read_text(encoding="utf-8")
    return parse_frontmatter(text)


def write_memory_file(
    path: str | Path,
    frontmatter: MemoryFrontmatter,
    body: str,
) -> None:
    """Write a memory file with frontmatter + body."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    header = format_frontmatter(frontmatter)
    # Ensure single blank line between frontmatter and body
    content = f"{header}\n\n{body}" if body else f"{header}\n"
    p.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Entrypoint (MEMORY.md) management
# ---------------------------------------------------------------------------


def read_entrypoint(cwd: str) -> tuple[str, EntrypointTruncation]:
    """Read MEMORY.md, returning ``(raw_content, truncation_info)``."""
    ep = get_auto_mem_entrypoint(cwd)
    if not ep.exists():
        trunc = EntrypointTruncation(
            content="",
            line_count=0,
            byte_count=0,
            was_line_truncated=False,
            was_byte_truncated=False,
        )
        return "", trunc

    raw = ep.read_text(encoding="utf-8")
    trunc = truncate_entrypoint(raw)
    return raw, trunc


def update_entrypoint(cwd: str, content: str) -> None:
    """Write/overwrite MEMORY.md."""
    ensure_memory_dir_exists(cwd)
    ep = get_auto_mem_entrypoint(cwd)
    ep.write_text(content, encoding="utf-8")


def truncate_entrypoint(
    content: str,
    max_lines: int = DEFAULT_MAX_LINES,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> EntrypointTruncation:
    """Truncate entrypoint content to fit within limits."""
    lines = content.splitlines(keepends=True)
    total_lines = len(lines)
    _total_bytes = len(content.encode("utf-8"))

    was_line_truncated = total_lines > max_lines
    if was_line_truncated:
        lines = lines[:max_lines]

    truncated = "".join(lines)
    byte_count = len(truncated.encode("utf-8"))
    was_byte_truncated = byte_count > max_bytes

    if was_byte_truncated:
        encoded = truncated.encode("utf-8")[:max_bytes]
        truncated = encoded.decode("utf-8", errors="ignore")
        byte_count = len(truncated.encode("utf-8"))

    return EntrypointTruncation(
        content=truncated,
        line_count=min(total_lines, max_lines),
        byte_count=byte_count,
        was_line_truncated=was_line_truncated,
        was_byte_truncated=was_byte_truncated,
    )


# ---------------------------------------------------------------------------
# High-level helpers
# ---------------------------------------------------------------------------


def create_memory_file(
    cwd: str,
    name: str,
    memory_type: MemoryType,
    description: str = "",
    content: str = "",
) -> Path:
    """Create a new memory file inside the memory directory.

    Returns the path to the created file.
    """
    mem_dir = ensure_memory_dir_exists(cwd)

    # Build safe filename from name
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", name.strip())
    if not safe_name.endswith(".md"):
        safe_name += ".md"

    path = mem_dir / safe_name

    fm = MemoryFrontmatter(
        name=name,
        description=description,
        type=memory_type,
    )
    write_memory_file(path, fm, content)
    return path


def delete_memory_file(path: str | Path) -> bool:
    """Delete a memory file. Returns True if the file existed and was deleted."""
    p = Path(path)
    if p.exists():
        p.unlink()
        return True
    return False


def list_memory_files(cwd: str) -> list[Path]:
    """List all .md files in the memory directory."""
    mem_dir = get_auto_mem_path(cwd)
    if not mem_dir.exists():
        return []
    return sorted(mem_dir.glob("*.md"))
