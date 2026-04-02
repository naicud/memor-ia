"""LLM provider base class and factory."""
from __future__ import annotations

import os
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Abstract base for LLM-powered text operations."""

    @abstractmethod
    async def summarize(self, content: str, *, max_tokens: int = 200) -> str:
        """Produce a concise summary of *content*."""

    @abstractmethod
    async def extract_key_facts(self, content: str) -> list[str]:
        """Extract discrete key facts from *content*."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider identifier."""


class NoneProvider(LLMProvider):
    """No-op provider — returns content unchanged (default)."""

    async def summarize(self, content: str, *, max_tokens: int = 200) -> str:
        # Simple truncation when no LLM is available
        if len(content) <= max_tokens * 4:  # rough chars-to-tokens
            return content
        return content[: max_tokens * 4] + "..."

    async def extract_key_facts(self, content: str) -> list[str]:
        # Split on sentences as a rough approximation
        sentences = [s.strip() for s in content.replace("\n", ". ").split(". ") if s.strip()]
        return sentences[:5]

    @property
    def provider_name(self) -> str:
        return "none"


def create_provider(
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> LLMProvider:
    """Factory to create an LLM provider from config or env vars.

    Provider resolution order:
    1. Explicit *provider* argument
    2. ``MEMORIA_LLM_PROVIDER`` env var
    3. Default: ``"none"``
    """
    name = (provider or os.environ.get("MEMORIA_LLM_PROVIDER", "none")).lower()

    if name == "none":
        return NoneProvider()

    if name == "ollama":
        from memoria.intelligence.providers.ollama import OllamaProvider
        return OllamaProvider(
            model=model or os.environ.get("MEMORIA_LLM_MODEL", "llama3.2:3b"),
            base_url=base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        )

    if name == "openai":
        from memoria.intelligence.providers.openai import OpenAIProvider
        return OpenAIProvider(
            model=model or os.environ.get("MEMORIA_LLM_MODEL", "gpt-4o-mini"),
            api_key=api_key or os.environ.get("MEMORIA_LLM_API_KEY", ""),
        )

    if name == "anthropic":
        from memoria.intelligence.providers.anthropic import AnthropicProvider
        return AnthropicProvider(
            model=model or os.environ.get("MEMORIA_LLM_MODEL", "claude-haiku-4-20250514"),
            api_key=api_key or os.environ.get("MEMORIA_LLM_API_KEY", ""),
        )

    raise ValueError(f"Unknown LLM provider: {name!r}. Use 'none', 'ollama', 'openai', or 'anthropic'.")
