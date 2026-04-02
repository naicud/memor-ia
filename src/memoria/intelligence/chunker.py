"""Token-aware text chunking for long memories."""
from __future__ import annotations


class TokenChunker:
    """Split text into chunks that respect a token budget.

    Uses a rough chars-to-tokens ratio (4 chars ≈ 1 token) by default.
    Override *chars_per_token* for more precision.
    """

    def __init__(self, max_tokens: int = 2000, chars_per_token: float = 4.0, overlap_tokens: int = 50) -> None:
        self._max_tokens = max_tokens
        self._cpt = chars_per_token
        self._overlap_chars = int(overlap_tokens * chars_per_token)

    @property
    def max_chars(self) -> int:
        return int(self._max_tokens * self._cpt)

    def needs_chunking(self, text: str) -> bool:
        """Return True if *text* exceeds the token budget."""
        return len(text) > self.max_chars

    def chunk(self, text: str) -> list[str]:
        """Split *text* into overlapping chunks within the token budget.

        Returns a list of text chunks. Short texts return a single-element list.
        """
        if not self.needs_chunking(text):
            return [text]

        chunks: list[str] = []
        start = 0
        max_c = self.max_chars

        while start < len(text):
            end = start + max_c
            if end >= len(text):
                chunks.append(text[start:])
                break

            # Try to break at a paragraph or sentence boundary
            break_at = self._find_break(text, start, end)
            chunks.append(text[start:break_at])
            start = break_at - self._overlap_chars
            if start < 0:
                start = 0

        return chunks

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for *text*."""
        return int(len(text) / self._cpt)

    @staticmethod
    def _find_break(text: str, start: int, end: int) -> int:
        """Find the best break point near *end*."""
        # Prefer paragraph break
        para = text.rfind("\n\n", start + (end - start) // 2, end)
        if para != -1:
            return para + 2

        # Prefer sentence break
        for sep in (". ", "! ", "? ", ".\n"):
            sent = text.rfind(sep, start + (end - start) // 2, end)
            if sent != -1:
                return sent + len(sep)

        # Prefer word break
        space = text.rfind(" ", start + (end - start) // 2, end)
        if space != -1:
            return space + 1

        # Hard break
        return end
