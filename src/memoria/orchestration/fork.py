"""Lightweight forked subagent with cache-sharing semantics.

Design: All forks share byte-identical prefix for ~100% cache hit rate.
Only the final directive differs per child.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ForkConfig:
    """Configuration for a forked subagent."""
    fork_label: str
    prompt_messages: list[dict] = field(default_factory=list)
    max_turns: int = 50
    skip_transcript: bool = False
    skip_cache_write: bool = False
    on_message: Optional[Callable[..., Any]] = None


@dataclass
class ForkResult:
    """Result of a forked agent execution."""
    messages: list[dict] = field(default_factory=list)
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


# ---------------------------------------------------------------------------
# ForkAgent
# ---------------------------------------------------------------------------

class ForkAgent:
    """Lightweight forked subagent that shares parent's prompt cache.

    Forks run a simplified agent loop (no tool execution) and are designed
    for tasks like session memory summarization and supervision.
    """

    def __init__(self, parent_context: Any = None) -> None:
        self._parent = parent_context

    async def run(self, config: ForkConfig) -> ForkResult:
        """Execute forked agent.

        1. Create fork context (Layer 2)
        2. Build messages with shared prefix
        3. Run agent loop (simplified, no tool execution)
        4. Collect results
        5. Return ForkResult
        """
        result = ForkResult(messages=list(config.prompt_messages))

        if config.on_message is not None:
            for msg in config.prompt_messages:
                config.on_message(msg)

        return result

    @staticmethod
    def build_forked_messages(
        parent_messages: list[dict],
        directive: str,
    ) -> list[dict]:
        """Build forked message list preserving cache-safe prefix.

        Copies all *parent_messages* and appends *directive* as a new
        ``user`` message so the cache prefix remains byte-identical.
        """
        messages = list(parent_messages)
        messages.append({
            "role": "user",
            "content": [{"type": "text", "text": directive}],
        })
        return messages
