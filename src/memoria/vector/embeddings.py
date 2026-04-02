"""Pluggable embedding providers for MEMORIA vector layer."""

from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Abstract embedding provider."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Embed a single text."""

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Embedding dimension."""


class TFIDFEmbedder(EmbeddingProvider):
    """TF-IDF based embedder using the hash-trick projection.

    Works without any ML dependencies.  Not as accurate as
    sentence-transformers but always available.
    """

    def __init__(self, dimension: int = 384):
        self._dimension = dimension
        self._vocab: dict[str, int] = {}

    def embed(self, text: str) -> list[float]:
        tokens = self._tokenize(text)
        if not tokens:
            return [0.0] * self._dimension

        for t in tokens:
            if t not in self._vocab:
                self._vocab[t] = len(self._vocab)

        return self._embed_with_tokens(tokens)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch embed using shared vocabulary build."""
        if not texts:
            return []
        # Build vocab from all texts first
        all_token_lists = [self._tokenize(t) for t in texts]
        for tokens in all_token_lists:
            for t in tokens:
                if t not in self._vocab:
                    self._vocab[t] = len(self._vocab)
        # Now embed each using shared vocab
        return [self._embed_with_tokens(tokens) for tokens in all_token_lists]

    def _embed_with_tokens(self, tokens: list[str]) -> list[float]:
        """Core embedding logic operating on pre-tokenized input."""
        if not tokens:
            return [0.0] * self._dimension

        sparse: dict[int, int] = {}
        for t in tokens:
            idx = self._vocab[t]
            sparse[idx] = sparse.get(idx, 0) + 1

        dense = [0.0] * self._dimension
        for idx, count in sparse.items():
            bucket = idx % self._dimension
            sign = 1 if (idx // self._dimension) % 2 == 0 else -1
            dense[bucket] += sign * count

        norm = math.sqrt(sum(x * x for x in dense)) or 1.0
        return [x / norm for x in dense]

    @property
    def dimension(self) -> int:
        return self._dimension

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [w for w in re.findall(r"[a-z0-9_]+", text.lower()) if len(w) > 1]


class SentenceTransformerEmbedder(EmbeddingProvider):
    """High-quality embeddings via sentence-transformers.

    Requires: ``pip install sentence-transformers``
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer(model_name)
            self._dimension: int = self.model.get_sentence_embedding_dimension()
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )

    def embed(self, text: str) -> list[float]:
        return self.model.encode(text).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts).tolist()

    @property
    def dimension(self) -> int:
        return self._dimension


class EmbedderRegistry:
    """Registry for embedding providers with dimension validation."""

    _providers: dict[str, type[EmbeddingProvider]] = {}

    @classmethod
    def register(cls, name: str, provider_class: type[EmbeddingProvider]) -> None:
        cls._providers[name] = provider_class

    @classmethod
    def get(cls, name: str, **kwargs) -> EmbeddingProvider:
        if name not in cls._providers:
            raise KeyError(f"Unknown embedder: {name}. Available: {sorted(cls._providers)}")
        return cls._providers[name](**kwargs)

    @classmethod
    def available(cls) -> list[str]:
        return sorted(cls._providers.keys())


# Auto-register built-in providers
EmbedderRegistry.register("tfidf", TFIDFEmbedder)
EmbedderRegistry.register("sentence-transformer", SentenceTransformerEmbedder)


def validate_dimension(embedder: EmbeddingProvider, expected: int) -> None:
    """Raise ValueError if embedder dimension doesn't match expected."""
    if embedder.dimension != expected:
        raise ValueError(
            f"Dimension mismatch: embedder produces {embedder.dimension}D "
            f"vectors but storage expects {expected}D"
        )


class CachedEmbedder(EmbeddingProvider):
    """Wraps an embedder with an LRU content-hash cache."""

    def __init__(self, inner: EmbeddingProvider, max_size: int = 1024):
        self._inner = inner
        self._cache: dict[str, list[float]] = {}
        self._max_size = max_size

    def embed(self, text: str) -> list[float]:
        key = text  # use text itself as key (could use hash for large texts)
        if key in self._cache:
            return list(self._cache[key])
        result = self._inner.embed(text)
        if len(self._cache) >= self._max_size:
            # Evict oldest entry
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        self._cache[key] = result
        return list(result)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        results = []
        uncached_texts = []
        uncached_indices = []
        for i, text in enumerate(texts):
            if text in self._cache:
                results.append(list(self._cache[text]))
            else:
                results.append([])  # placeholder
                uncached_texts.append(text)
                uncached_indices.append(i)
        if uncached_texts:
            new_embeddings = self._inner.embed_batch(uncached_texts)
            for idx, emb in zip(uncached_indices, new_embeddings):
                results[idx] = emb
                text = texts[idx]
                if len(self._cache) >= self._max_size:
                    oldest = next(iter(self._cache))
                    del self._cache[oldest]
                self._cache[text] = emb
        return results

    @property
    def dimension(self) -> int:
        return self._inner.dimension

    def clear_cache(self) -> None:
        self._cache.clear()


def get_default_embedder(dimension: int = 384) -> EmbeddingProvider:
    """Return the best available embedder."""
    try:
        return SentenceTransformerEmbedder()
    except ImportError:
        return TFIDFEmbedder(dimension=dimension)
