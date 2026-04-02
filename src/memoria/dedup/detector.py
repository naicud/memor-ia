"""Duplicate detection via cosine similarity on embeddings."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memoria.vector.client import VectorClient
    from memoria.vector.embeddings import EmbeddingProvider

log = logging.getLogger(__name__)

_DEFAULT_THRESHOLD = 0.92


@dataclass
class DuplicateMatch:
    """A candidate duplicate memory."""

    memory_id: str
    content: str
    similarity: float
    metadata: dict


class DuplicateDetector:
    """Detect near-duplicate memories using embedding similarity.

    Cosine similarity > *threshold* flags a duplicate.
    ``VectorClient.search`` returns cosine **distance** (0 = identical),
    so similarity = 1 − distance.
    """

    def __init__(
        self,
        embedder: EmbeddingProvider,
        vector_client: VectorClient,
        *,
        threshold: float = _DEFAULT_THRESHOLD,
    ) -> None:
        self._embedder = embedder
        self._vc = vector_client
        self._threshold = threshold

    @property
    def threshold(self) -> float:
        return self._threshold

    @threshold.setter
    def threshold(self, value: float) -> None:
        if not 0.0 <= value <= 1.0:
            raise ValueError("threshold must be between 0.0 and 1.0")
        self._threshold = value

    def find_duplicates(
        self,
        content: str,
        *,
        limit: int = 10,
        user_id: str | None = None,
    ) -> list[DuplicateMatch]:
        """Return existing memories similar to *content* above threshold.

        Results are sorted by similarity (highest first).
        """
        if not content or not content.strip():
            return []

        embedding = self._embedder.embed(content)
        results = self._vc.search(embedding, limit=limit, user_id=user_id)

        matches: list[DuplicateMatch] = []
        for record in results:
            similarity = 1.0 - record.distance
            if similarity >= self._threshold:
                matches.append(
                    DuplicateMatch(
                        memory_id=record.id,
                        content=record.content,
                        similarity=round(similarity, 4),
                        metadata=record.metadata,
                    )
                )

        matches.sort(key=lambda m: m.similarity, reverse=True)
        log.debug(
            "dedup check: %d candidates above threshold %.2f",
            len(matches),
            self._threshold,
        )
        return matches

    def is_duplicate(
        self,
        content: str,
        *,
        user_id: str | None = None,
    ) -> DuplicateMatch | None:
        """Quick check — return the best match if duplicate, else ``None``."""
        matches = self.find_duplicates(content, limit=1, user_id=user_id)
        return matches[0] if matches else None
