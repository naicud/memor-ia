"""Hybrid recall pipeline combining keyword, vector, and graph strategies."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .context_filter import RecallContext, deduplicate, filter_by_context
from .ranker import RankedResult, reciprocal_rank_fusion, weighted_score_fusion, diversify_results
from .strategies import RecallResult, RecallStrategy

if TYPE_CHECKING:
    from memoria.graph.knowledge import KnowledgeGraph
    from memoria.vector.client import VectorClient
    from memoria.vector.embeddings import EmbeddingProvider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class RecallCache:
    """Simple TTL cache for recall results."""

    def __init__(self, ttl_seconds: float = 300.0, max_size: int = 128):
        self._cache: dict[str, tuple[float, list[RankedResult]]] = {}
        self._ttl = ttl_seconds
        self._max_size = max_size

    def get(self, key: str) -> list[RankedResult] | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        ts, results = entry
        import time
        if time.time() - ts > self._ttl:
            del self._cache[key]
            return None
        return results

    def put(self, key: str, results: list[RankedResult]) -> None:
        import time
        if len(self._cache) >= self._max_size:
            # Evict oldest
            oldest_key = min(self._cache, key=lambda k: self._cache[k][0])
            del self._cache[oldest_key]
        self._cache[key] = (time.time(), results)

    def invalidate(self, key: str | None = None) -> None:
        if key is None:
            self._cache.clear()
        else:
            self._cache.pop(key, None)


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
