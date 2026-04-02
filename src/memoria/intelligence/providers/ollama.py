"""Ollama LLM provider — local, zero-cost, private."""
from __future__ import annotations

from memoria.intelligence.providers.base import LLMProvider


class OllamaProvider(LLMProvider):
    """Local LLM via Ollama REST API."""

    def __init__(self, model: str = "llama3.2:3b", base_url: str = "http://localhost:11434") -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")

    async def summarize(self, content: str, *, max_tokens: int = 200) -> str:
        prompt = (
            "Summarize the following text concisely. Keep the most important facts "
            f"and limit your response to roughly {max_tokens} tokens.\n\n"
            f"Text:\n{content}\n\nSummary:"
        )
        return await self._generate(prompt, max_tokens=max_tokens)

    async def extract_key_facts(self, content: str) -> list[str]:
        prompt = (
            "Extract the key facts from the following text as a numbered list. "
            "Return only the facts, one per line.\n\n"
            f"Text:\n{content}\n\nKey facts:"
        )
        response = await self._generate(prompt, max_tokens=500)
        lines = [line.strip().lstrip("0123456789.-) ") for line in response.strip().split("\n")]
        return [line for line in lines if line]

    async def _generate(self, prompt: str, *, max_tokens: int = 200) -> str:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": max_tokens},
                },
                timeout=60,
            )
            resp.raise_for_status()
            return resp.json().get("response", "").strip()

    @property
    def provider_name(self) -> str:
        return f"ollama:{self._model}"
