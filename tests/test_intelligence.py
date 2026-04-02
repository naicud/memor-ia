"""Tests for the intelligence layer: summarizer, chunker, providers."""
from __future__ import annotations

import asyncio

import pytest

from memoria.intelligence.chunker import TokenChunker
from memoria.intelligence.providers.base import LLMProvider, NoneProvider, create_provider
from memoria.intelligence.summarizer import SummarizationResult, Summarizer

# ===================================================================
# NoneProvider
# ===================================================================

class TestNoneProvider:
    def setup_method(self):
        self.provider = NoneProvider()

    def test_provider_name(self):
        assert self.provider.provider_name == "none"

    @pytest.mark.asyncio
    async def test_summarize_short_text(self):
        result = await self.provider.summarize("Short text", max_tokens=200)
        assert result == "Short text"  # no change, under threshold

    @pytest.mark.asyncio
    async def test_summarize_long_text_truncates(self):
        long_text = "A" * 5000
        result = await self.provider.summarize(long_text, max_tokens=100)
        assert result.endswith("...")
        assert len(result) <= 100 * 4 + 3  # max_tokens * chars_per_token + "..."

    @pytest.mark.asyncio
    async def test_extract_key_facts(self):
        text = "First fact. Second fact. Third fact. Fourth fact. Fifth fact. Sixth fact."
        facts = await self.provider.extract_key_facts(text)
        assert len(facts) <= 5
        assert all(isinstance(f, str) for f in facts)


# ===================================================================
# create_provider factory
# ===================================================================

class TestCreateProvider:
    def test_none_default(self):
        p = create_provider()
        assert isinstance(p, NoneProvider)

    def test_none_explicit(self):
        p = create_provider("none")
        assert isinstance(p, NoneProvider)

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            create_provider("invalid_provider")

    def test_ollama_creates(self):
        from memoria.intelligence.providers.ollama import OllamaProvider
        p = create_provider("ollama", model="test-model")
        assert isinstance(p, OllamaProvider)
        assert p.provider_name == "ollama:test-model"

    def test_openai_creates(self):
        from memoria.intelligence.providers.openai import OpenAIProvider
        p = create_provider("openai", model="gpt-4", api_key="test")
        assert isinstance(p, OpenAIProvider)
        assert p.provider_name == "openai:gpt-4"

    def test_anthropic_creates(self):
        from memoria.intelligence.providers.anthropic import AnthropicProvider
        p = create_provider("anthropic", model="claude-haiku", api_key="test")
        assert isinstance(p, AnthropicProvider)
        assert p.provider_name == "anthropic:claude-haiku"

    def test_case_insensitive(self):
        p = create_provider("NONE")
        assert isinstance(p, NoneProvider)

    def test_env_var_fallback(self, monkeypatch):
        monkeypatch.setenv("MEMORIA_LLM_PROVIDER", "none")
        p = create_provider()
        assert isinstance(p, NoneProvider)


# ===================================================================
# TokenChunker
# ===================================================================

class TestTokenChunker:
    def setup_method(self):
        self.chunker = TokenChunker(max_tokens=100, chars_per_token=4.0)

    def test_short_text_no_chunking(self):
        assert not self.chunker.needs_chunking("Short text")
        chunks = self.chunker.chunk("Short text")
        assert len(chunks) == 1
        assert chunks[0] == "Short text"

    def test_long_text_chunked(self):
        long_text = "Word " * 200  # 1000 chars, > 100 tokens * 4 cpt = 400
        assert self.chunker.needs_chunking(long_text)
        chunks = self.chunker.chunk(long_text)
        assert len(chunks) > 1
        # All chunks within budget
        for chunk in chunks:
            assert len(chunk) <= self.chunker.max_chars + 10  # small tolerance

    def test_estimate_tokens(self):
        assert self.chunker.estimate_tokens("A" * 400) == 100
        assert self.chunker.estimate_tokens("A" * 800) == 200

    def test_max_chars(self):
        assert self.chunker.max_chars == 400  # 100 tokens * 4 cpt

    def test_chunking_preserves_content(self):
        # All content should be preserved across chunks (with overlap)
        text = "Sentence one. Sentence two. Sentence three. Sentence four. " * 10
        chunker = TokenChunker(max_tokens=50, chars_per_token=4.0, overlap_tokens=10)
        chunks = chunker.chunk(text)
        # Rejoined should contain all original content (overlap means some duplication)
        combined = " ".join(chunks)
        for sentence in ["Sentence one", "Sentence two", "Sentence three", "Sentence four"]:
            assert sentence in combined

    def test_break_at_paragraph(self):
        text = "A" * 300 + "\n\n" + "B" * 300
        chunker = TokenChunker(max_tokens=100, chars_per_token=4.0)
        chunks = chunker.chunk(text)
        # Should break at the paragraph boundary
        assert len(chunks) >= 2

    def test_break_at_sentence(self):
        text = "A" * 300 + ". B" + "C" * 300
        chunker = TokenChunker(max_tokens=100, chars_per_token=4.0)
        chunks = chunker.chunk(text)
        assert len(chunks) >= 2

    def test_empty_text(self):
        chunks = self.chunker.chunk("")
        assert chunks == [""]

    def test_overlap_produces_shared_content(self):
        text = "A" * 600
        chunker = TokenChunker(max_tokens=100, chars_per_token=4.0, overlap_tokens=25)
        chunks = chunker.chunk(text)
        assert len(chunks) >= 2
        # Overlap means chunks share some content at boundaries
        if len(chunks) >= 2:
            # The end of chunk 0 should overlap with the start of chunk 1
            end_of_first = chunks[0][-50:]
            start_of_second = chunks[1][:50]
            # At least some characters should match
            assert any(c in start_of_second for c in end_of_first)


# ===================================================================
# SummarizationResult
# ===================================================================

class TestSummarizationResult:
    def test_compression_ratio(self):
        r = SummarizationResult(
            original_length=1000,
            summary_length=200,
            summary="short",
        )
        assert abs(r.compression_ratio - 0.8) < 0.01

    def test_zero_length_no_crash(self):
        r = SummarizationResult(original_length=0, summary_length=0, summary="")
        assert r.compression_ratio == 0.0

    def test_no_compression(self):
        r = SummarizationResult(original_length=100, summary_length=100, summary="same")
        assert r.compression_ratio == 0.0


# ===================================================================
# Summarizer with NoneProvider
# ===================================================================

class TestSummarizer:
    def setup_method(self):
        self.provider = NoneProvider()
        self.summarizer = Summarizer(self.provider, threshold=100)

    @pytest.mark.asyncio
    async def test_short_text_not_summarized(self):
        result = await self.summarizer.summarize("Short")
        assert result.summary == "Short"
        assert result.chunks_processed == 0  # skipped

    @pytest.mark.asyncio
    async def test_long_text_summarized(self):
        text = "Important fact. " * 50  # > 100 chars threshold
        result = await self.summarizer.summarize(text)
        assert result.original_length > 100
        assert result.provider == "none"

    @pytest.mark.asyncio
    async def test_should_summarize(self):
        assert not self.summarizer.should_summarize("Short")
        assert self.summarizer.should_summarize("X" * 200)

    @pytest.mark.asyncio
    async def test_batch_summarize(self):
        items = [
            {"content": "Short text"},
            {"content": "A longer text. " * 50},
        ]
        results = await self.summarizer.summarize_batch(items)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_chunked_summarization(self):
        # Create text that exceeds chunk limit (3 chunks with max 100 tokens)
        text = "Important fact number one. " * 60  # ~1620 chars → 3+ chunks at 400 chars/chunk
        summarizer = Summarizer(self.provider, threshold=100, chunk_max_tokens=100)
        result = await summarizer.summarize(text)
        assert result.chunks_processed > 1

    def test_provider_name(self):
        assert self.summarizer.provider_name == "none"


# ===================================================================
# Integration via Memoria class
# ===================================================================

class TestMemoriaSummarizationIntegration:
    def test_summarize_text(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        result = m.summarize("This is a test text to summarize.")
        assert "summary" in result
        assert "provider" in result
        assert result["provider"] == "none"

    def test_summarize_short_text_passthrough(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        result = m.summarize("Short")
        assert result["summary"] == "Short"
        assert result["compression_ratio"] == 0.0

    def test_summarize_memories_empty(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        result = m.summarize_memories()
        assert result["summarized"] == 0

    def test_summarizer_lazy_init(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        s1 = m._get_summarizer()
        s2 = m._get_summarizer()
        assert s1 is s2

    def test_summarize_with_config(self, tmp_path):
        from memoria import Memoria
        m = Memoria(
            project_dir=str(tmp_path),
            config={"llm_provider": "none", "summarize_threshold": "100"},
        )
        result = m.summarize("X" * 200)
        assert result["provider"] == "none"
