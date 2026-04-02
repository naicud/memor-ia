"""Semantic search operations for MEMORIA vector layer."""

from __future__ import annotations

from dataclasses import dataclass, field

from .client import VectorClient
from .embeddings import EmbeddingProvider


@dataclass
class SearchResult:
    id: str
    content: str
    score: float  # 0.0–1.0 similarity (higher = more similar)
    metadata: dict = field(default_factory=dict)


class SemanticSearch:
    """Semantic search over indexed content."""

    def __init__(self, client: VectorClient, embedder: EmbeddingProvider):
        self.client = client
        self.embedder = embedder

    def search(
        self,
        query: str,
        limit: int = 5,
        offset: int = 0,
        user_id: str | None = None,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        """Search for semantically similar content."""
        embedding = self.embedder.embed(query)
        return self.search_by_embedding(
            embedding,
            limit=limit,
            offset=offset,
            user_id=user_id,
            min_score=min_score,
        )

    def search_by_embedding(
        self,
        embedding: list[float],
        limit: int = 5,
        offset: int = 0,
        user_id: str | None = None,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        """Search using a pre-computed embedding."""
        records = self.client.search(
            embedding,
            limit=(limit + offset) * 2,  # over-fetch to allow min_score filtering
            user_id=user_id,
        )

        results: list[SearchResult] = []
        for rec in records:
            score = max(0.0, min(1.0, 1.0 - rec.distance))
            if score < min_score:
                continue
            results.append(
                SearchResult(
                    id=rec.id,
                    content=rec.content,
                    score=score,
                    metadata=rec.metadata,
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[offset:offset + limit]

    def find_similar(self, text_id: str, limit: int = 5, offset: int = 0) -> list[SearchResult]:
        """Find content similar to an existing indexed text."""
        record = self.client.get(text_id)
        if record is None:
            return []
        results = self.search_by_embedding(record.embedding, limit=limit + offset + 1)
        # Exclude the source document itself
        return [r for r in results if r.id != text_id][offset:offset + limit]
