"""MEMORIA context — token budgeting, compaction, and prompt building."""

from .window import (
    CHARS_PER_TOKEN,
    ContextAnalysis,
    MODEL_BUDGETS,
    TokenBudget,
    TokenUsage,
    analyze_context,
    estimate_message_tokens,
    estimate_messages_tokens,
    estimate_tokens,
    get_budget,
)
from .compaction import (
    CompactBoundary,
    CompactionConfig,
    ContextCompactor,
)
from .prompt import (
    SYSTEM_PROMPT_DYNAMIC_BOUNDARY,
    PromptBuilder,
    PromptConfig,
    PromptSection,
    build_system_prompt,
)

__all__ = [
    "CHARS_PER_TOKEN",
    "CompactBoundary",
    "CompactionConfig",
    "ContextAnalysis",
    "ContextCompactor",
    "MODEL_BUDGETS",
    "PromptBuilder",
    "PromptConfig",
    "PromptSection",
    "SYSTEM_PROMPT_DYNAMIC_BOUNDARY",
    "TokenBudget",
    "TokenUsage",
    "analyze_context",
    "build_system_prompt",
    "estimate_message_tokens",
    "estimate_messages_tokens",
    "estimate_tokens",
    "get_budget",
]
