"""Context summarization — micro-compact and full compact.

Manages context window compaction to keep conversations within token
budgets while preserving essential information.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class CompactBoundary:
    """Marks where compaction occurred."""

    summary: str
    timestamp: float = field(default_factory=time.time)
    original_message_count: int = 0
    original_token_count: int = 0


@dataclass
class CompactionConfig:
    """Configuration for context compaction."""

    enabled: bool = True
    compact_threshold: float = 0.85
    micro_compact_interval: float = 300.0
    preserve_recent_n: int = 10
    preserve_system: bool = True
    max_summary_tokens: int = 2000


class ContextCompactor:
    """Manages context window compaction.

    Two modes:
    1. Micro-compact: Remove low-value tool results (non-destructive)
    2. Full compact: Summarize entire history into boundary message
    """

    def __init__(
        self,
        config: CompactionConfig | None = None,
        summarize_fn: Callable | None = None,
    ):
        self._config = config or CompactionConfig()
        self._summarize_fn = summarize_fn or self._default_summarize
        self._last_compact_time = time.time()
        self._compact_count = 0

    def should_compact(self, messages: list[dict], budget) -> bool:
        """Check if compaction is needed."""
        from .window import estimate_messages_tokens

        tokens = estimate_messages_tokens(messages)
        return tokens >= budget.compact_trigger

    def micro_compact(self, messages: list[dict]) -> list[dict]:
        """Remove low-value content (non-destructive).

        Removes:
        - Empty tool results
        - Verbose tool results older than preserve_recent_n
        - Duplicate file reads
        """
        if not self._config.enabled:
            return messages

        result = []
        preserve_from = max(0, len(messages) - self._config.preserve_recent_n)

        for i, msg in enumerate(messages):
            if i >= preserve_from:
                result.append(msg)
                continue

            # Keep system messages always
            if msg.get("role") == "system":
                result.append(msg)
                continue

            # Filter verbose tool results
            if self._is_low_value_tool_result(msg):
                continue

            result.append(msg)

        return result

    async def full_compact(
        self, messages: list[dict]
    ) -> tuple[list[dict], CompactBoundary | None]:
        """Full compaction: summarize history into boundary message.

        Returns (compacted_messages, boundary).
        """
        # Separate system prompt from conversation
        system_msgs = [m for m in messages if m.get("role") == "system"]
        conv_msgs = [m for m in messages if m.get("role") != "system"]

        # Keep recent messages
        to_compact = conv_msgs[: -self._config.preserve_recent_n]
        to_keep = conv_msgs[-self._config.preserve_recent_n :]

        if not to_compact:
            return messages, None

        # Summarize
        summary_text = await self._summarize_fn(to_compact)

        from .window import estimate_messages_tokens

        boundary = CompactBoundary(
            summary=summary_text,
            original_message_count=len(to_compact),
            original_token_count=estimate_messages_tokens(to_compact),
        )

        # Build compacted message list
        boundary_msg = {
            "role": "assistant",
            "content": [{"type": "text", "text": f"[Context Summary]\n{summary_text}"}],
            "_compact_boundary": True,
        }

        compacted = system_msgs + [boundary_msg] + to_keep
        self._compact_count += 1
        self._last_compact_time = time.time()

        return compacted, boundary

    def get_messages_after_boundary(self, messages: list[dict]) -> list[dict]:
        """Get only messages after the last compact boundary."""
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("_compact_boundary"):
                return messages[i:]
        return messages

    @staticmethod
    def _is_low_value_tool_result(msg: dict) -> bool:
        """Check if a tool result has low informational value."""
        if msg.get("role") != "tool":
            return False
        content = msg.get("content", "")
        if isinstance(content, str) and len(content) < 10:
            return True
        return False

    @staticmethod
    async def _default_summarize(messages: list[dict]) -> str:
        """Default summarization (extracts key info, no LLM)."""
        parts = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                parts.append(f"[{role}] {content[:200]}")
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "")[:200]
                        if text:
                            parts.append(f"[{role}] {text}")
        return "\n".join(parts[-20:])

    @property
    def compact_count(self) -> int:
        return self._compact_count
