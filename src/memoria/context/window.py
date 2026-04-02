"""Token counting, budgeting, and threshold management.

Provides approximate token estimation, per-model budgets, and context
window analysis to drive compaction decisions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# Approximate token estimation (4 chars ≈ 1 token)
CHARS_PER_TOKEN = 4


@dataclass
class TokenBudget:
    """Token budget for a context window."""

    max_input_tokens: int = 200_000
    max_output_tokens: int = 8_192
    compact_threshold: float = 0.85
    reserve_tokens: int = 10_000

    @property
    def available_tokens(self) -> int:
        return self.max_input_tokens - self.reserve_tokens

    @property
    def compact_trigger(self) -> int:
        return int(self.available_tokens * self.compact_threshold)


@dataclass
class TokenUsage:
    """Track token usage for a conversation."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def total_with_cache(self) -> int:
        return self.total + self.cache_creation_tokens + self.cache_read_tokens


@dataclass
class ContextAnalysis:
    """Analysis of context window composition."""

    total_tokens: int = 0
    system_prompt_tokens: int = 0
    memory_tokens: int = 0
    message_tokens: int = 0
    tool_result_tokens: int = 0
    file_content_tokens: int = 0
    compacted_summary_tokens: int = 0
    utilization: float = 0.0
    needs_compaction: bool = False


# ---------------------------------------------------------------------------
# Token estimation helpers
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """Estimate token count from text (fast approximation)."""
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


def estimate_message_tokens(message: dict) -> int:
    """Estimate tokens for a single message."""
    total = 4  # Message overhead
    role = message.get("role", "")
    total += estimate_tokens(role)

    content = message.get("content", "")
    if isinstance(content, str):
        total += estimate_tokens(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    total += estimate_tokens(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    total += estimate_tokens(str(block.get("input", {})))
                elif block.get("type") == "tool_result":
                    total += estimate_tokens(str(block.get("content", "")))

    return total


def estimate_messages_tokens(messages: list[dict]) -> int:
    """Estimate total tokens for a list of messages."""
    return sum(estimate_message_tokens(m) for m in messages)


def analyze_context(messages: list[dict], budget: TokenBudget) -> ContextAnalysis:
    """Analyze context window composition and utilization."""
    analysis = ContextAnalysis()

    for msg in messages:
        tokens = estimate_message_tokens(msg)
        analysis.total_tokens += tokens

        role = msg.get("role", "")
        if role == "system":
            analysis.system_prompt_tokens += tokens
        elif msg.get("type") == "tool_result":
            analysis.tool_result_tokens += tokens
        else:
            analysis.message_tokens += tokens

    analysis.utilization = (
        analysis.total_tokens / budget.available_tokens
        if budget.available_tokens > 0
        else 0
    )
    analysis.needs_compaction = analysis.total_tokens >= budget.compact_trigger

    return analysis


# ---------------------------------------------------------------------------
# Model-specific budgets
# ---------------------------------------------------------------------------

MODEL_BUDGETS = {
    "opus": TokenBudget(max_input_tokens=200_000, max_output_tokens=16_384),
    "sonnet": TokenBudget(max_input_tokens=200_000, max_output_tokens=8_192),
    "haiku": TokenBudget(max_input_tokens=200_000, max_output_tokens=8_192),
}


def get_budget(model: str = "sonnet") -> TokenBudget:
    """Get token budget for model."""
    return MODEL_BUDGETS.get(model, MODEL_BUDGETS["sonnet"])
