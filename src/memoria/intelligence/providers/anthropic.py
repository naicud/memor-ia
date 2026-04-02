"""Anthropic LLM provider."""
from __future__ import annotations

from memoria.intelligence.providers.base import LLMProvider


class AnthropicProvider(LLMProvider):
    """Anthropic API (Haiku for summarization)."""

    def __init__(self, model: str = "claude-haiku-4-20250514", api_key: str = "") -> None:
        self._model = model
        self._api_key = api_key

    async def summarize(self, content: str, *, max_tokens: int = 200) -> str:
        prompt = f"Summarize this text concisely in roughly {max_tokens} tokens:\n\n{content}"
        return await self._message(prompt, max_tokens=max_tokens)

    async def extract_key_facts(self, content: str) -> list[str]:
        prompt = f"Extract the key facts as a plain numbered list:\n\n{content}"
        response = await self._message(prompt, max_tokens=500)
        lines = [line.strip().lstrip("0123456789.-) ") for line in response.strip().split("\n")]
        return [line for line in lines if line]

    async def _message(self, content: str, *, max_tokens: int = 200) -> str:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": content}],
                },
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["content"][0]["text"].strip()

    @property
    def provider_name(self) -> str:
        return f"anthropic:{self._model}"
