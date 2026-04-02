"""Tests for src.context_mgmt — token budgeting, compaction, and prompt building."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest import mock

import pytest

from memoria.context.window import (
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
from memoria.context.compaction import (
    CompactBoundary,
    CompactionConfig,
    ContextCompactor,
)
from memoria.context.prompt import (
    SYSTEM_PROMPT_DYNAMIC_BOUNDARY,
    PromptBuilder,
    PromptConfig,
    PromptSection,
    build_system_prompt,
)


# ── helpers ──────────────────────────────────────────────────────────────


def _run(coro):
    """Run an async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_messages(n: int, role: str = "user", content: str = "hello") -> list[dict]:
    return [{"role": role, "content": content} for _ in range(n)]


# ═════════════════════════════════════════════════════════════════════════
# TokenBudget / TokenUsage
# ═════════════════════════════════════════════════════════════════════════


class TestTokenBudget:
    def test_defaults(self):
        b = TokenBudget()
        assert b.max_input_tokens == 200_000
        assert b.max_output_tokens == 8_192
        assert b.compact_threshold == 0.85
        assert b.reserve_tokens == 10_000

    def test_available_tokens(self):
        b = TokenBudget(max_input_tokens=100_000, reserve_tokens=5_000)
        assert b.available_tokens == 95_000

    def test_compact_trigger(self):
        b = TokenBudget(max_input_tokens=200_000, reserve_tokens=10_000,
                        compact_threshold=0.85)
        assert b.compact_trigger == int(190_000 * 0.85)

    def test_custom_budget(self):
        b = TokenBudget(max_input_tokens=50_000, max_output_tokens=4_096,
                        compact_threshold=0.5, reserve_tokens=2_000)
        assert b.available_tokens == 48_000
        assert b.compact_trigger == 24_000


class TestTokenUsage:
    def test_total(self):
        u = TokenUsage(input_tokens=100, output_tokens=50)
        assert u.total == 150

    def test_total_with_cache(self):
        u = TokenUsage(input_tokens=100, output_tokens=50,
                       cache_creation_tokens=20, cache_read_tokens=30)
        assert u.total_with_cache == 200

    def test_defaults_zero(self):
        u = TokenUsage()
        assert u.total == 0
        assert u.total_with_cache == 0


# ═════════════════════════════════════════════════════════════════════════
# Token estimation
# ═════════════════════════════════════════════════════════════════════════


class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_short_string(self):
        assert estimate_tokens("hi") == 1  # max(1, 2//4)

    def test_known_length(self):
        text = "a" * 100
        assert estimate_tokens(text) == 25

    def test_minimum_one(self):
        assert estimate_tokens("a") == 1

    def test_chars_per_token_constant(self):
        assert CHARS_PER_TOKEN == 4


class TestEstimateMessageTokens:
    def test_text_message(self):
        msg = {"role": "user", "content": "Hello, world!"}
        tokens = estimate_message_tokens(msg)
        assert tokens > 4  # overhead + role + content

    def test_empty_content(self):
        msg = {"role": "user", "content": ""}
        tokens = estimate_message_tokens(msg)
        assert tokens >= 4  # at least overhead

    def test_content_list_text(self):
        msg = {"role": "assistant", "content": [
            {"type": "text", "text": "Response text here"}
        ]}
        tokens = estimate_message_tokens(msg)
        assert tokens > 4

    def test_content_list_tool_use(self):
        msg = {"role": "assistant", "content": [
            {"type": "tool_use", "input": {"query": "test"}}
        ]}
        tokens = estimate_message_tokens(msg)
        assert tokens > 4

    def test_content_list_tool_result(self):
        msg = {"role": "tool", "content": [
            {"type": "tool_result", "content": "result data"}
        ]}
        tokens = estimate_message_tokens(msg)
        assert tokens > 4

    def test_mixed_content_blocks(self):
        msg = {"role": "assistant", "content": [
            {"type": "text", "text": "Thinking..."},
            {"type": "tool_use", "input": {"file": "test.py"}},
        ]}
        tokens = estimate_message_tokens(msg)
        text_only = estimate_message_tokens(
            {"role": "assistant", "content": [{"type": "text", "text": "Thinking..."}]}
        )
        assert tokens > text_only


class TestEstimateMessagesTokens:
    def test_empty_list(self):
        assert estimate_messages_tokens([]) == 0

    def test_sums_correctly(self):
        msgs = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        total = estimate_messages_tokens(msgs)
        individual = sum(estimate_message_tokens(m) for m in msgs)
        assert total == individual

    def test_multiple_messages(self):
        msgs = _make_messages(5, content="test content")
        assert estimate_messages_tokens(msgs) > 0


# ═════════════════════════════════════════════════════════════════════════
# Context analysis
# ═════════════════════════════════════════════════════════════════════════


class TestAnalyzeContext:
    def test_composition(self):
        msgs = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        budget = TokenBudget()
        analysis = analyze_context(msgs, budget)
        assert analysis.total_tokens > 0
        assert analysis.system_prompt_tokens > 0
        assert analysis.message_tokens > 0

    def test_utilization(self):
        budget = TokenBudget(max_input_tokens=100, reserve_tokens=0)
        msgs = [{"role": "user", "content": "a" * 200}]  # ~50 tokens
        analysis = analyze_context(msgs, budget)
        assert 0 < analysis.utilization <= 1.0

    def test_needs_compaction_false(self):
        budget = TokenBudget(max_input_tokens=1_000_000, reserve_tokens=0)
        msgs = [{"role": "user", "content": "short"}]
        analysis = analyze_context(msgs, budget)
        assert analysis.needs_compaction is False

    def test_needs_compaction_true(self):
        budget = TokenBudget(max_input_tokens=100, reserve_tokens=0,
                             compact_threshold=0.1)
        # Trigger = 10 tokens; message will exceed that
        msgs = [{"role": "user", "content": "a" * 200}]
        analysis = analyze_context(msgs, budget)
        assert analysis.needs_compaction is True

    def test_zero_available(self):
        budget = TokenBudget(max_input_tokens=0, reserve_tokens=0)
        analysis = analyze_context([], budget)
        assert analysis.utilization == 0

    def test_tool_result_tracking(self):
        msgs = [{"role": "tool", "type": "tool_result", "content": "data"}]
        budget = TokenBudget()
        analysis = analyze_context(msgs, budget)
        assert analysis.tool_result_tokens > 0


# ═════════════════════════════════════════════════════════════════════════
# Model budgets
# ═════════════════════════════════════════════════════════════════════════


class TestModelBudgets:
    def test_opus_budget(self):
        b = get_budget("opus")
        assert b.max_output_tokens == 16_384

    def test_sonnet_budget(self):
        b = get_budget("sonnet")
        assert b.max_output_tokens == 8_192

    def test_haiku_budget(self):
        b = get_budget("haiku")
        assert b.max_output_tokens == 8_192

    def test_unknown_defaults_to_sonnet(self):
        b = get_budget("unknown-model")
        assert b == MODEL_BUDGETS["sonnet"]


# ═════════════════════════════════════════════════════════════════════════
# ContextCompactor
# ═════════════════════════════════════════════════════════════════════════


class TestContextCompactor:
    def test_should_compact_false(self):
        compactor = ContextCompactor()
        budget = TokenBudget(max_input_tokens=1_000_000, reserve_tokens=0)
        msgs = _make_messages(3, content="short")
        assert compactor.should_compact(msgs, budget) is False

    def test_should_compact_true(self):
        compactor = ContextCompactor()
        budget = TokenBudget(max_input_tokens=50, reserve_tokens=0,
                             compact_threshold=0.1)
        msgs = _make_messages(5, content="a" * 200)
        assert compactor.should_compact(msgs, budget) is True

    def test_micro_compact_removes_low_value(self):
        compactor = ContextCompactor(CompactionConfig(preserve_recent_n=2))
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "tool", "content": "ok"},       # low value (< 10 chars)
            {"role": "user", "content": "important"},
            {"role": "user", "content": "recent1"},
            {"role": "user", "content": "recent2"},
        ]
        result = compactor.micro_compact(msgs)
        # System kept, low-value tool removed, recent 2 kept, "important" kept
        assert len(result) < len(msgs)
        assert result[0]["role"] == "system"

    def test_micro_compact_preserves_recent_n(self):
        config = CompactionConfig(preserve_recent_n=3)
        compactor = ContextCompactor(config)
        msgs = _make_messages(10, content="msg")
        result = compactor.micro_compact(msgs)
        # Last 3 always preserved
        assert result[-3:] == msgs[-3:]

    def test_micro_compact_disabled(self):
        config = CompactionConfig(enabled=False)
        compactor = ContextCompactor(config)
        msgs = [
            {"role": "tool", "content": "ok"},
            {"role": "user", "content": "hi"},
        ]
        result = compactor.micro_compact(msgs)
        assert result == msgs

    def test_micro_compact_keeps_system(self):
        compactor = ContextCompactor(CompactionConfig(preserve_recent_n=1))
        msgs = [
            {"role": "system", "content": "system prompt"},
            {"role": "tool", "content": "ok"},
            {"role": "user", "content": "last"},
        ]
        result = compactor.micro_compact(msgs)
        roles = [m["role"] for m in result]
        assert "system" in roles

    def test_full_compact_creates_boundary(self):
        compactor = ContextCompactor(CompactionConfig(preserve_recent_n=2))
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "reply1"},
            {"role": "user", "content": "msg2"},
            {"role": "assistant", "content": "reply2"},
            {"role": "user", "content": "recent1"},
            {"role": "assistant", "content": "recent2"},
        ]
        compacted, boundary = _run(compactor.full_compact(msgs))
        assert boundary is not None
        assert boundary.original_message_count > 0
        assert boundary.summary != ""
        assert any(m.get("_compact_boundary") for m in compacted)

    def test_full_compact_preserves_system(self):
        compactor = ContextCompactor(CompactionConfig(preserve_recent_n=2))
        msgs = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old reply"},
            {"role": "user", "content": "recent1"},
            {"role": "assistant", "content": "recent2"},
        ]
        compacted, _ = _run(compactor.full_compact(msgs))
        assert compacted[0]["role"] == "system"
        assert compacted[0]["content"] == "system prompt"

    def test_full_compact_no_compact_when_few_messages(self):
        compactor = ContextCompactor(CompactionConfig(preserve_recent_n=10))
        msgs = _make_messages(5, content="msg")
        compacted, boundary = _run(compactor.full_compact(msgs))
        assert boundary is None
        assert compacted == msgs

    def test_full_compact_increments_count(self):
        compactor = ContextCompactor(CompactionConfig(preserve_recent_n=1))
        msgs = [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old reply"},
            {"role": "user", "content": "recent"},
        ]
        assert compactor.compact_count == 0
        _run(compactor.full_compact(msgs))
        assert compactor.compact_count == 1

    def test_full_compact_custom_summarize_fn(self):
        async def custom_summarize(messages):
            return "CUSTOM SUMMARY"

        compactor = ContextCompactor(
            CompactionConfig(preserve_recent_n=1),
            summarize_fn=custom_summarize,
        )
        msgs = [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old reply"},
            {"role": "user", "content": "recent"},
        ]
        compacted, boundary = _run(compactor.full_compact(msgs))
        assert "CUSTOM SUMMARY" in boundary.summary

    def test_get_messages_after_boundary(self):
        compactor = ContextCompactor()
        msgs = [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "summary", "_compact_boundary": True},
            {"role": "user", "content": "new"},
        ]
        after = compactor.get_messages_after_boundary(msgs)
        assert len(after) == 2
        assert after[0].get("_compact_boundary") is True

    def test_get_messages_after_boundary_no_boundary(self):
        compactor = ContextCompactor()
        msgs = _make_messages(3)
        after = compactor.get_messages_after_boundary(msgs)
        assert after == msgs

    def test_is_low_value_tool_result_true(self):
        assert ContextCompactor._is_low_value_tool_result(
            {"role": "tool", "content": "ok"}
        ) is True

    def test_is_low_value_tool_result_false_long(self):
        assert ContextCompactor._is_low_value_tool_result(
            {"role": "tool", "content": "This is a substantial result"}
        ) is False

    def test_is_low_value_tool_result_false_non_tool(self):
        assert ContextCompactor._is_low_value_tool_result(
            {"role": "user", "content": "ok"}
        ) is False


# ═════════════════════════════════════════════════════════════════════════
# PromptBuilder
# ═════════════════════════════════════════════════════════════════════════


class TestPromptBuilder:
    def test_build_with_sections(self):
        builder = PromptBuilder(PromptConfig(
            include_memory=False, include_git_context=False, include_date=False
        ))
        builder.add_section(PromptSection("intro", "You are helpful.", priority=10))
        builder.add_section(PromptSection("rules", "Be concise.", priority=5))
        prompt = builder.build()
        assert "You are helpful." in prompt
        assert "Be concise." in prompt
        # Higher priority first
        assert prompt.index("You are helpful.") < prompt.index("Be concise.")

    def test_dynamic_boundary_placement(self):
        builder = PromptBuilder(PromptConfig(
            include_memory=False, include_git_context=False, include_date=False
        ))
        builder.add_section(PromptSection("static", "STATIC", cacheable=True))
        builder.add_section(PromptSection("dynamic", "DYNAMIC", cacheable=False))
        prompt = builder.build()
        assert SYSTEM_PROMPT_DYNAMIC_BOUNDARY in prompt
        parts = prompt.split(SYSTEM_PROMPT_DYNAMIC_BOUNDARY)
        assert "STATIC" in parts[0]
        assert "DYNAMIC" in parts[1]

    def test_override_system_prompt(self):
        config = PromptConfig(override_system_prompt="OVERRIDE ONLY")
        builder = PromptBuilder(config)
        builder.add_section(PromptSection("ignored", "should not appear"))
        assert builder.build() == "OVERRIDE ONLY"

    def test_append_system_prompt(self):
        config = PromptConfig(
            append_system_prompt="APPENDED",
            include_memory=False, include_git_context=False, include_date=False,
        )
        builder = PromptBuilder(config)
        prompt = builder.build()
        assert prompt.endswith("APPENDED")

    def test_date_included(self):
        config = PromptConfig(
            include_memory=False, include_git_context=False, include_date=True
        )
        builder = PromptBuilder(config)
        prompt = builder.build()
        assert "Current date:" in prompt

    def test_custom_memory_loader(self):
        config = PromptConfig(
            include_memory=True, include_git_context=False, include_date=False
        )
        builder = PromptBuilder(config)
        builder.set_memory_loader(lambda: "MEMORY INJECTED")
        prompt = builder.build()
        assert "MEMORY INJECTED" in prompt

    def test_memory_from_directory(self, tmp_path):
        mem_dir = tmp_path / "memory"
        mem_dir.mkdir()
        (mem_dir / "MEMORY.md").write_text("# Index\n- item1\n- item2")
        config = PromptConfig(
            include_memory=True, include_git_context=False, include_date=False,
            memory_dir=str(mem_dir),
        )
        builder = PromptBuilder(config)
        prompt = builder.build()
        assert "Memory System" in prompt
        assert "item1" in prompt

    def test_memory_no_entrypoint(self, tmp_path):
        mem_dir = tmp_path / "empty_memory"
        mem_dir.mkdir()
        config = PromptConfig(
            include_memory=True, include_git_context=False, include_date=False,
            memory_dir=str(mem_dir),
        )
        builder = PromptBuilder(config)
        prompt = builder.build()
        assert "Memory System" in prompt
        assert "MEMORY.md" not in prompt or "Current MEMORY.md" not in prompt

    def test_build_memory_prompt_structure(self):
        builder = PromptBuilder()
        prompt = builder.build_memory_prompt("/mem", "# Index\n- foo")
        assert "## Memory System" in prompt
        assert "Memory directory: /mem" in prompt
        assert "4 types" in prompt
        assert "### What NOT to save" in prompt
        assert "### How to save" in prompt
        assert "### Current MEMORY.md" in prompt
        assert "# Index" in prompt

    def test_build_memory_prompt_no_entrypoint(self):
        builder = PromptBuilder()
        prompt = builder.build_memory_prompt("/mem")
        assert "## Memory System" in prompt
        assert "Current MEMORY.md" not in prompt

    def test_git_context_loading(self):
        config = PromptConfig(
            include_memory=False, include_git_context=True, include_date=False,
        )
        builder = PromptBuilder(config)
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value = mock.Mock(returncode=0, stdout="main\n")
            prompt = builder.build()
        assert "Current git branch: main" in prompt

    def test_git_context_failure(self):
        config = PromptConfig(
            include_memory=False, include_git_context=True, include_date=False,
        )
        builder = PromptBuilder(config)
        with mock.patch("subprocess.run", side_effect=FileNotFoundError):
            prompt = builder.build()
        assert "git branch" not in prompt

    def test_build_system_prompt_convenience(self):
        config = PromptConfig(
            include_memory=False, include_git_context=False, include_date=False
        )
        prompt = build_system_prompt(config)
        assert SYSTEM_PROMPT_DYNAMIC_BOUNDARY in prompt


# ═════════════════════════════════════════════════════════════════════════
# Package __init__ re-exports
# ═════════════════════════════════════════════════════════════════════════


class TestPackageExports:
    def test_all_exports(self):
        import memoria.context as cm
        expected = [
            "TokenBudget", "TokenUsage", "ContextAnalysis",
            "estimate_tokens", "estimate_message_tokens", "estimate_messages_tokens",
            "analyze_context", "get_budget",
            "CompactBoundary", "CompactionConfig", "ContextCompactor",
            "PromptBuilder", "PromptConfig", "PromptSection",
            "build_system_prompt", "SYSTEM_PROMPT_DYNAMIC_BOUNDARY",
        ]
        for name in expected:
            assert hasattr(cm, name), f"Missing export: {name}"
