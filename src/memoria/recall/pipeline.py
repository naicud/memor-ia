"""Hybrid recall pipeline combining keyword, vector, and graph strategies."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .context_filter import RecallContext, deduplicate, filter_by_context
from .ranker import RankedResult, diversify_results, reciprocal_rank_fusion, weighted_score_fusion
from .strategies import RecallResult, RecallStrategy

if TYPE_CHECKING:
    from memoria.cache.backend import CacheBackend
    from memoria.graph.knowledge import KnowledgeGraph
    from memoria.vector.client import VectorClient
    from memoria.vector.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class RecallCache:
    """TTL cache for recall results — pluggable backend.

    When *cache_backend* is provided, uses the shared :class:`CacheBackend`
    (in-memory or Redis).  Otherwise falls back to the original internal dict.
    """

    def __init__(
        self,
        ttl_seconds: float = 300.0,
        max_size: int = 128,
        cache_backend: "CacheBackend | None" = None,
    ):
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._backend = cache_backend
        # Legacy fallback
        self._legacy_cache: dict[str, tuple[float, list[RankedResult]]] | None = (
            None if cache_backend else {}
        )

    def get(self, key: str) -> list[RankedResult] | None:
        if self._backend is not None:
            result = self._backend.get(f"recall:{key}")
            if result is None:
                return None
            # Deserialize RankedResult dicts back to objects
            return [
                RankedResult(
                    id=r["id"],
                    content=r.get("content", ""),
                    final_score=r.get("final_score", 0.0),
                    sources=r.get("sources", []),
                    strategy_scores=r.get("strategy_scores", {}),
                    metadata=r.get("metadata", {}),
                )
                for r in result
            ]

        # Legacy path
        assert self._legacy_cache is not None
        entry = self._legacy_cache.get(key)
        if entry is None:
            return None
        ts, results = entry
        import time
        if time.time() - ts > self._ttl:
            del self._legacy_cache[key]
            return None
        return results

    def put(self, key: str, results: list[RankedResult]) -> None:
        if self._backend is not None:
            serializable = [
                {
                    "id": r.id,
                    "content": r.content,
                    "final_score": r.final_score,
                    "sources": r.sources,
                    "strategy_scores": r.strategy_scores,
                    "metadata": r.metadata,
                }
                for r in results
            ]
            self._backend.set(f"recall:{key}", serializable, ttl=int(self._ttl))
            return

        # Legacy path
        assert self._legacy_cache is not None
        import time
        if len(self._legacy_cache) >= self._max_size:
            oldest_key = min(self._legacy_cache, key=lambda k: self._legacy_cache[k][0])  # type: ignore[union-attr]
            del self._legacy_cache[oldest_key]
        self._legacy_cache[key] = (time.time(), results)

    def invalidate(self, key: str | None = None) -> None:
        if self._backend is not None:
            if key is None:
                self._backend.invalidate_pattern("recall:*")
            else:
                self._backend.delete(f"recall:{key}")
            return

        # Legacy path
        assert self._legacy_cache is not None
        if key is None:
            self._legacy_cache.clear()
        else:
            self._legacy_cache.pop(key, None)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class RecallPipeline:
    """Hybrid recall pipeline combining keyword, vector, and graph strategies."""

    def __init__(
        self,
        strategies: list[RecallStrategy] | None = None,
        weights: dict[str, float] | None = None,
        fusion_method: str = "rrf",  # "rrf" or "weighted"
        cache: RecallCache | None = None,
    ) -> None:
        self.strategies: list[RecallStrategy] = strategies or []
        self.weights: dict[str, float] = weights or {}
        self.fusion_method = fusion_method
        self._cache = cache

    def add_strategy(
        self, strategy: RecallStrategy, weight: float = 1.0
    ) -> None:
        """Add a retrieval strategy with optional weight."""
        self.strategies.append(strategy)
        self.weights[strategy.name] = weight

    def recall(
        self,
        query: str,
        limit: int = 5,
        context: RecallContext | None = None,
        **kwargs: Any,
    ) -> list[RankedResult]:
        """Execute hybrid recall.

        1. Run all strategies in parallel (using threads).
        2. Fuse results with RRF or weighted scoring.
        3. Apply context filtering.
        4. Deduplicate.
        5. Return top-k.
        """
        if not self.strategies:
            return []

        if not query or not query.strip():
            return []

        # 0. Check cache
        cache_key = f"{query}:{limit}:{sorted(kwargs.items())}"
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        # 1. Gather results from each strategy (parallel)
        result_lists = self._run_strategies(query, limit, **kwargs)

        if not any(result_lists):
            return []

        # 2. Fuse
        if self.fusion_method == "weighted":
            fused = weighted_score_fusion(result_lists, weights=self.weights)
        else:
            fused = reciprocal_rank_fusion(result_lists, weights=self.weights)

        # 3. Context filter
        if context is not None:
            fused = filter_by_context(fused, context)

        # 4. Deduplicate
        fused = deduplicate(fused)

        # 4.5. Diversify
        fused = diversify_results(fused, limit=limit)

        # 5. Top-k
        results = fused[:limit]

        # 6. Store in cache
        if self._cache is not None:
            self._cache.put(cache_key, results)

        return results

    def _run_strategies(
        self, query: str, limit: int, **kwargs: Any
    ) -> list[list[RecallResult]]:
        """Run all strategies, using threads when multiple are present."""
        if len(self.strategies) == 1:
            try:
                return [self.strategies[0].retrieve(query, limit=limit, **kwargs)]
            except Exception:
                logger.exception(
                    "Strategy %s failed", self.strategies[0].name
                )
                return [[]]

        result_lists: list[list[RecallResult]] = [[] for _ in self.strategies]

        with ThreadPoolExecutor(
            max_workers=len(self.strategies)
        ) as executor:
            future_to_idx = {
                executor.submit(s.retrieve, query, limit, **kwargs): i
                for i, s in enumerate(self.strategies)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    result_lists[idx] = future.result()
                except Exception:
                    logger.exception(
                        "Strategy %s failed", self.strategies[idx].name
                    )

        return result_lists

    # -- factory ------------------------------------------------------------

    @classmethod
    def create_default(
        cls,
        memory_dir: Path | str | None = None,
        vector_client: VectorClient | None = None,
        embedder: EmbeddingProvider | None = None,
        knowledge_graph: KnowledgeGraph | None = None,
    ) -> RecallPipeline:
        """Create a pipeline with all available strategies.

        Only adds strategies for which backends are provided.
        Always includes keyword if memory_dir is given.
        """
        pipeline = cls()

        if memory_dir is not None:
            from .strategies import KeywordStrategy

            pipeline.add_strategy(KeywordStrategy(memory_dir), weight=1.0)

        if vector_client is not None and embedder is not None:
            from memoria.vector.search import SemanticSearch

            from .strategies import VectorStrategy

            search = SemanticSearch(client=vector_client, embedder=embedder)
            pipeline.add_strategy(VectorStrategy(search), weight=1.2)

        if knowledge_graph is not None:
            from .strategies import GraphStrategy

            pipeline.add_strategy(GraphStrategy(knowledge_graph), weight=0.8)

        return pipeline
