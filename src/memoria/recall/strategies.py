"""Retrieval strategies for the hybrid recall pipeline."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from memoria.graph.knowledge import KnowledgeGraph
    from memoria.vector.search import SemanticSearch

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RecallResult:
    """A single recall result from any strategy."""

    id: str
    content: str
    score: float  # 0.0 to 1.0
    source: str  # "keyword", "vector", "graph"
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract strategy
# ---------------------------------------------------------------------------


class RecallStrategy(ABC):
    """Abstract retrieval strategy."""

    @abstractmethod
    def retrieve(
        self, query: str, limit: int = 10, offset: int = 0, **kwargs: Any
    ) -> list[RecallResult]:
        """Retrieve relevant results for a query."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name."""


# ---------------------------------------------------------------------------
# Keyword strategy
# ---------------------------------------------------------------------------


class KeywordStrategy(RecallStrategy):
    """Keyword-based recall using existing memory_recall logic."""

    def __init__(self, memory_dir: str | Path) -> None:
        self.memory_dir = Path(memory_dir)

    def retrieve(
        self, query: str, limit: int = 10, offset: int = 0, **kwargs: Any
    ) -> list[RecallResult]:
        """Use find_relevant_memories from core.recall."""
        from memoria.core.recall import find_relevant_memories

        memories = find_relevant_memories(query, str(self.memory_dir))

        results: list[RecallResult] = []
        for m in memories[offset:offset + limit]:
            # Read file content when available
            content = _read_file_content(m.path)
            results.append(
                RecallResult(
                    id=m.path,
                    content=content,
                    score=m.score,
                    source="keyword",
                    metadata={"mtime_ms": m.mtime_ms},
                )
            )
        return results

    @property
    def name(self) -> str:
        return "keyword"


# ---------------------------------------------------------------------------
# Vector strategy
# ---------------------------------------------------------------------------


class VectorStrategy(RecallStrategy):
    """Vector similarity search using SemanticSearch."""

    def __init__(self, search: SemanticSearch) -> None:
        self._search = search

    def retrieve(
        self, query: str, limit: int = 10, offset: int = 0, **kwargs: Any
    ) -> list[RecallResult]:
        """Use SemanticSearch.search()."""
        search_kwargs: dict[str, Any] = {}
        if "user_id" in kwargs:
            search_kwargs["user_id"] = kwargs["user_id"]
        if "min_score" in kwargs:
            search_kwargs["min_score"] = kwargs["min_score"]

        results = self._search.search(query, limit=limit, offset=offset, **search_kwargs)
        return [
            RecallResult(
                id=r.id,
                content=r.content,
                score=r.score,
                source="vector",
                metadata=r.metadata,
            )
            for r in results
        ]

    @property
    def name(self) -> str:
        return "vector"


# ---------------------------------------------------------------------------
# Graph strategy
# ---------------------------------------------------------------------------


class GraphStrategy(RecallStrategy):
    """Graph-based recall using knowledge graph traversal."""

    def __init__(self, kg: KnowledgeGraph) -> None:
        self._kg = kg

    def retrieve(
        self, query: str, limit: int = 10, offset: int = 0, **kwargs: Any
    ) -> list[RecallResult]:
        """Extract entities from query, find related entities in graph."""
        from memoria.graph.entities import extract_entities

        entities = extract_entities(query)
        if not entities:
            return []

        results: list[RecallResult] = []
        seen: set[str] = set()
        depth = kwargs.get("depth", 2)

        for entity in entities:
            related = self._kg.get_related(entity.name, depth=depth)
            for item in related:
                item_id = item.get("name", str(item.get("id", id(item))))
                if item_id in seen:
                    continue
                seen.add(item_id)

                # Score based on entity confidence; decay with depth
                item_depth = item.get("depth", 1)
                score = entity.confidence * (1.0 / (1 + item_depth))
                score = max(0.0, min(1.0, score))

                results.append(
                    RecallResult(
                        id=item_id,
                        content=str(item),
                        score=score,
                        source="graph",
                        metadata=item,
                    )
                )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[offset:offset + limit]

    @property
    def name(self) -> str:
        return "graph"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_file_content(path: str) -> str:
    """Read file content, returning path as fallback."""
    try:
        from memoria.core.store import read_memory_file

        _, body = read_memory_file(path)
        return body.strip()
    except Exception:
        return path
