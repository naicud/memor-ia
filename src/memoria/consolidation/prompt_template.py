"""Consolidation prompt — 4-phase template for memory synthesis.

Produces the system prompt used by the dream agent to read recent session
transcripts and update the structured memory index.

Ported from ``src_origin/src/tasks/DreamTask/consolidationPrompt.ts``.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENTRYPOINT_NAME: str = "MEMORY.md"
"""Top-level memory index filename."""

MAX_ENTRYPOINT_LINES: int = 200
"""Maximum lines read from the existing entrypoint for context."""

MAX_ENTRYPOINT_BYTES: int = 25_000
"""Maximum bytes read from the existing entrypoint for context."""

# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def build_consolidation_prompt(
    memory_root: str,
    transcript_dir: str,
    extra: str = "",
) -> str:
    """Build the 4-phase consolidation prompt.

    Phases:
    1. **Read** — Load the current memory index (``MEMORY.md``).
    2. **Scan** — Review recent session transcripts in *transcript_dir*.
    3. **Synthesize** — Extract durable facts, conventions, and decisions.
    4. **Write** — Update the memory index with new knowledge.

    Parameters
    ----------
    memory_root:
        Directory containing (or that will contain) ``MEMORY.md``.
    transcript_dir:
        Directory with ``.jsonl`` session transcript files.
    extra:
        Optional additional instructions appended to the prompt.
    """
    entrypoint = os.path.join(memory_root, ENTRYPOINT_NAME)
    lines = [
        "You are performing a dream — a reflective pass over your memory files.",
        "Synthesize what you've learned recently into durable, well-organized memories",
        "so that future sessions can orient quickly.",
        "",
        "## Phase 1: Read",
        f"Read the current memory index at `{entrypoint}` to understand what's already indexed.",
        f"If the file does not exist, you will create it. Max {MAX_ENTRYPOINT_LINES} lines / {MAX_ENTRYPOINT_BYTES} bytes.",
        "",
        "## Phase 2: Scan",
        f"Review recent session transcripts in `{transcript_dir}`.",
        "Focus on the most recent sessions first. Look for:",
        "- Key decisions made",
        "- Conventions established or confirmed",
        "- Important facts about the codebase",
        "- Patterns the user prefers",
        "",
        "## Phase 3: Synthesize",
        "Extract durable knowledge from the transcripts:",
        "- Merge new facts with existing memories (avoid duplicates)",
        "- Resolve any contradictions (newer information wins)",
        "- Discard ephemeral details (temporary debugging, one-off questions)",
        "- Organize by topic, not by session",
        "",
        "## Phase 4: Write",
        f"Update `{entrypoint}` with the synthesized knowledge.",
        "Keep the file well-structured with clear headings.",
        f"Stay within {MAX_ENTRYPOINT_LINES} lines and {MAX_ENTRYPOINT_BYTES} bytes.",
    ]

    if extra:
        lines.append("")
        lines.append(extra)

    return "\n".join(lines)


__all__ = [
    "ENTRYPOINT_NAME",
    "MAX_ENTRYPOINT_BYTES",
    "MAX_ENTRYPOINT_LINES",
    "build_consolidation_prompt",
]
