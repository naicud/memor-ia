"""MEMORIA vector layer — semantic search powered by SQLite."""

from __future__ import annotations

from .chunking import TextChunk, chunk_code, chunk_markdown, chunk_text
from .client import HAS_SQLITE_VEC, VectorClient, VectorRecord
from .embeddings import (
    EmbeddingProvider,
    SentenceTransformerEmbedder,
    TFIDFEmbedder,
    get_default_embedder,
)
from .index import VectorIndex
from .search import SearchResult, SemanticSearch

__all__ = [
    # client
    "HAS_SQLITE_VEC",
    "VectorClient",
    "VectorRecord",
    # embeddings
    "EmbeddingProvider",
    "SentenceTransformerEmbedder",
    "TFIDFEmbedder",
    "get_default_embedder",
    # index
    "VectorIndex",
    # search
    "SearchResult",
    "SemanticSearch",
    # chunking
    "TextChunk",
    "chunk_code",
    "chunk_markdown",
    "chunk_text",
]
