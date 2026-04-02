"""4-type memory taxonomy and frontmatter parser."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# ---------------------------------------------------------------------------
# Memory taxonomy
# ---------------------------------------------------------------------------


class MemoryType(str, Enum):
    USER = "user"
    FEEDBACK = "feedback"
    PROJECT = "project"
    REFERENCE = "reference"


MEMORY_TYPE_DESCRIPTIONS: dict[MemoryType, str] = {
    MemoryType.USER: "Information about user's role, goals, knowledge, preferences",
    MemoryType.FEEDBACK: "Guidance about approach (avoid & keep doing) with Why + How to apply",
    MemoryType.PROJECT: "Ongoing work, goals, initiatives, bugs NOT derivable from code/git",
    MemoryType.REFERENCE: "Pointers to external systems (Linear, Grafana, Slack)",
}

# ---------------------------------------------------------------------------
# Frontmatter
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_KV_RE = re.compile(r'^(\w+)\s*:\s*"?([^"\n]*)"?\s*$')


@dataclass
class MemoryFrontmatter:
    name: str = ""
    description: str = ""
    type: Optional[MemoryType] = None
    raw: dict = field(default_factory=dict)


def parse_frontmatter(content: str) -> tuple[MemoryFrontmatter, str]:
    """Parse YAML-like frontmatter from memory file.

    Returns ``(frontmatter, body)`` where *body* is everything after the
    closing ``---``.
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return MemoryFrontmatter(), content

    raw_block = match.group(1)
    body = content[match.end():]

    raw: dict[str, str] = {}
    for line in raw_block.splitlines():
        kv = _KV_RE.match(line.strip())
        if kv:
            raw[kv.group(1)] = kv.group(2).strip()

    fm = MemoryFrontmatter(
        name=raw.get("name", ""),
        description=raw.get("description", ""),
        type=parse_memory_type(raw["type"]) if "type" in raw else None,
        raw=raw,
    )
    return fm, body


def parse_memory_type(value: str) -> Optional[MemoryType]:
    """Parse memory type string, returning ``None`` for invalid values."""
    try:
        return MemoryType(value.lower())
    except ValueError:
        return None


def format_frontmatter(fm: MemoryFrontmatter) -> str:
    """Format frontmatter as a YAML block."""
    lines = ["---"]
    if fm.name:
        lines.append(f'name: "{fm.name}"')
    if fm.description:
        lines.append(f'description: "{fm.description}"')
    if fm.type:
        lines.append(f'type: "{fm.type.value}"')
    lines.append("---")
    return "\n".join(lines)
