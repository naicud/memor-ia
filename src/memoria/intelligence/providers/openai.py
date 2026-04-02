"""OpenAI LLM provider."""
from __future__ import annotations

from memoria.intelligence.providers.base import LLMProvider


class OpenAIProvider(LLMProvider):
    """OpenAI API (GPT-4o-mini for cost efficiency)."""

    def __init__(self, model: str = "gpt-4o-mini", api_key: str = "") -> None:
        self._model = model
        self._api_key = api_key

    async def summarize(self, content: str, *, max_tokens: int = 200) -> str:
        messages = [
            {"role": "system", "content": "You are a concise summarizer. Preserve key facts."},
            {"role": "user", "content": f"Summarize this text in roughly {max_tokens} tokens:\n\n{content}"},
        ]
        return await self._chat(messages, max_tokens=max_tokens)

    async def extract_key_facts(self, content: str) -> list[str]:
        messages = [
            {"role": "system", "content": "Extract key facts as a plain numbered list."},
            {"role": "user", "content": f"Extract key facts:\n\n{content}"},
        ]
        response = await self._chat(messages, max_tokens=500)
        lines = [line.strip().lstrip("0123456789.-) ") for line in response.strip().split("\n")]
        return [line for line in lines if line]

    async def _chat(self, messages: list[dict], *, max_tokens: int = 200) -> str:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.3,
                },
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

    @property
    def provider_name(self) -> str:
        return f"openai:{self._model}"
