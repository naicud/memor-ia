"""Scan memory directory, parse headers, build manifest."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .types import MemoryType, parse_frontmatter
from .paths import AUTO_MEM_ENTRYPOINT_NAME

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_MEMORY_FILES = 200
FRONTMATTER_MAX_LINES = 30

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class MemoryHeader:
    filename: str
    file_path: str
    mtime_ms: float
    description: Optional[str]
    type: Optional[MemoryType]


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


def scan_memory_files(memory_dir: str | Path) -> list[MemoryHeader]:
    """Scan directory for memory files, parse frontmatter, sort newest first.

    Returns at most ``MAX_MEMORY_FILES`` entries.  The entrypoint
    (``MEMORY.md``) is excluded because it is handled separately.
    """
    md = Path(memory_dir)
    if not md.is_dir():
        return []

    headers: list[MemoryHeader] = []
    for entry in md.iterdir():
        if not entry.is_file() or not entry.suffix == ".md":
            continue
        if entry.name == AUTO_MEM_ENTRYPOINT_NAME:
            continue

        fm = _parse_header_fast(entry)
        stat = entry.stat()
        headers.append(
            MemoryHeader(
                filename=entry.name,
                file_path=str(entry.resolve()),
                mtime_ms=stat.st_mtime * 1000,
                description=fm.description or None,
                type=fm.type,
            )
        )

    # Sort newest first
    headers.sort(key=lambda h: h.mtime_ms, reverse=True)
    return headers[:MAX_MEMORY_FILES]


def format_memory_manifest(memories: list[MemoryHeader]) -> str:
    """Format memory headers as a manifest list.

    Each line: ``- [type] filename (timestamp): description``
    """
    if not memories:
        return "(no memory files)"

    lines: list[str] = []
    for m in memories:
        type_tag = f"[{m.type.value}]" if m.type else "[unknown]"
        ts = f"{m.mtime_ms:.0f}"
        desc = m.description or "no description"
        lines.append(f"- {type_tag} {m.filename} ({ts}): {desc}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_header_fast(path: Path):
    """Read only the first FRONTMATTER_MAX_LINES lines to extract frontmatter."""
    from .types import MemoryFrontmatter

    try:
        with path.open("r", encoding="utf-8") as f:
            head_lines: list[str] = []
            for i, line in enumerate(f):
                if i >= FRONTMATTER_MAX_LINES:
                    break
                head_lines.append(line)
        head = "".join(head_lines)
        fm, _ = parse_frontmatter(head)
        return fm
    except (OSError, UnicodeDecodeError):
        return MemoryFrontmatter()
