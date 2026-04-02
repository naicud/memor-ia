"""Vector index lifecycle management."""

from __future__ import annotations

from .client import VectorClient, VectorRecord
from .embeddings import EmbeddingProvider


class VectorIndex:
    """Manages vector index lifecycle — indexing, removal, re-indexing."""

    def __init__(self, client: VectorClient, embedder: EmbeddingProvider):
        self.client = client
        self.embedder = embedder

    def index_text(
        self,
        text_id: str,
        text: str,
        metadata: dict | None = None,
        user_id: str | None = None,
        memory_type: str | None = None,
    ) -> str:
        """Embed and index a text.  Returns the record id."""
        embedding = self.embedder.embed(text)
        meta = dict(metadata or {})
        if user_id:
            meta["user_id"] = user_id
        if memory_type:
            meta["memory_type"] = memory_type

        record = VectorRecord(
            id=text_id,
            embedding=embedding,
            content=text,
            metadata=meta,
        )
        self.client.insert(record)
        return text_id

    def index_batch(self, items: list[dict]) -> list[str]:
        """Index multiple items.

        Each dict must contain ``id`` and ``text``, plus optional
        ``metadata``, ``user_id``, and ``memory_type``.
        """
        texts = [item["text"] for item in items]
        embeddings = self.embedder.embed_batch(texts)
        records: list[VectorRecord] = []
        ids: list[str] = []
        for item, embedding in zip(items, embeddings):
            meta = dict(item.get("metadata") or {})
            if item.get("user_id"):
                meta["user_id"] = item["user_id"]
            if item.get("memory_type"):
                meta["memory_type"] = item["memory_type"]

            records.append(VectorRecord(
                id=item["id"],
                embedding=embedding,
                content=item["text"],
                metadata=meta,
            ))
            ids.append(item["id"])
        self.client.insert_batch(records)
        return ids

    def reindex_all(self) -> int:
        """Re-embed every stored text.  Returns number of records updated."""
        rows = self.client.conn.execute(
            "SELECT id, content FROM vec_metadata"
        ).fetchall()
        count = 0
        for rid, content in rows:
            existing = self.client.get(rid)
            if existing is None:
                continue
            embedding = self.embedder.embed(content)
            existing.embedding = embedding
            self.client.insert(existing)
            count += 1
        return count

    def remove(self, text_id: str) -> None:
        """Remove a text from the index."""
        self.client.delete(text_id)

    def stats(self) -> dict:
        """Return index statistics."""
        return {
            "count": self.client.count(),
            "dimension": self.client.dimension,
            "backend": "sqlite-vec" if self.client._use_vec else "pure-python",
            "embedder": type(self.embedder).__name__,
        }
