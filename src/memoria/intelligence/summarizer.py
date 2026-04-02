"""Summarization orchestrator — connects chunking, LLM, and validation."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memoria.intelligence.providers.base import LLMProvider

log = logging.getLogger(__name__)


@dataclass
class SummarizationResult:
    """Result of a summarization operation."""

    original_length: int
    summary_length: int
    summary: str
    key_facts: list[str] = field(default_factory=list)
    chunks_processed: int = 1
    compression_ratio: float = 0.0
    provider: str = ""

    def __post_init__(self):
        if self.original_length > 0:
            self.compression_ratio = 1 - (self.summary_length / self.original_length)


class Summarizer:
    """Orchestrates LLM-powered summarization with chunking support.

    Usage::

        from memoria.intelligence.providers.base import create_provider
        provider = create_provider("ollama")
        summarizer = Summarizer(provider)
        result = await summarizer.summarize("long text...")
    """

    def __init__(
        self,
        provider: "LLMProvider",
        *,
        max_tokens: int = 200,
        chunk_max_tokens: int = 2000,
        threshold: int = 500,
    ) -> None:
        self._provider = provider
        self._max_tokens = max_tokens
        self._chunk_max_tokens = chunk_max_tokens
        self._threshold = threshold  # char count below which we skip summarization

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    def should_summarize(self, content: str) -> bool:
        """Return True if *content* is long enough to benefit from summarization."""
        return len(content) > self._threshold

    async def summarize(self, content: str, *, max_tokens: int | None = None) -> SummarizationResult:
        """Summarize *content*, chunking if necessary."""
        mt = max_tokens or self._max_tokens

        if not self.should_summarize(content):
            return SummarizationResult(
                original_length=len(content),
                summary_length=len(content),
                summary=content,
                chunks_processed=0,
                provider=self.provider_name,
            )

        from memoria.intelligence.chunker import TokenChunker
        chunker = TokenChunker(max_tokens=self._chunk_max_tokens)

        if not chunker.needs_chunking(content):
            summary = await self._provider.summarize(content, max_tokens=mt)
            facts = await self._provider.extract_key_facts(content)
            return SummarizationResult(
                original_length=len(content),
                summary_length=len(summary),
                summary=summary,
                key_facts=facts,
                chunks_processed=1,
                provider=self.provider_name,
            )

        # Multi-chunk summarization
        chunks = chunker.chunk(content)
        chunk_summaries: list[str] = []
        all_facts: list[str] = []

        for chunk in chunks:
            s = await self._provider.summarize(chunk, max_tokens=mt)
            chunk_summaries.append(s)
            facts = await self._provider.extract_key_facts(chunk)
            all_facts.extend(facts)

        # Combine chunk summaries
        combined = "\n\n".join(chunk_summaries)

        # If combined is still long, do a final pass
        if len(combined) > mt * 4:
            final = await self._provider.summarize(combined, max_tokens=mt)
        else:
            final = combined

        return SummarizationResult(
            original_length=len(content),
            summary_length=len(final),
            summary=final,
            key_facts=list(dict.fromkeys(all_facts)),  # deduplicate preserving order
            chunks_processed=len(chunks),
            provider=self.provider_name,
        )

    async def summarize_batch(self, items: list[dict]) -> list[SummarizationResult]:
        """Summarize a batch of items. Each item needs a ``content`` key."""
        results = []
        for item in items:
            content = item.get("content", "")
            result = await self.summarize(content)
            results.append(result)
        return results
