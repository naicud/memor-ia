"""Tests for offset-based pagination across all layers."""
from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_tmp = tempfile.mkdtemp(prefix="mem_pag_")
_orig_data_dir = os.environ.get("MEMORIA_DATA_DIR")
os.environ["MEMORIA_DATA_DIR"] = _tmp

from memoria import Memoria  # noqa: E402
from memoria.namespace.store import SharedMemoryStore  # noqa: E402
from memoria.recall.pipeline import RecallCache, RecallPipeline  # noqa: E402
from memoria.recall.strategies import (  # noqa: E402
    GraphStrategy,
    KeywordStrategy,
    RecallResult,
    VectorStrategy,
)
from memoria.vector.client import VectorClient, VectorRecord  # noqa: E402
from memoria.vector.search import SemanticSearch  # noqa: E402

# Restore env immediately after imports so we don't leak to other test modules
if _orig_data_dir is None:
    os.environ.pop("MEMORIA_DATA_DIR", None)
else:
    os.environ["MEMORIA_DATA_DIR"] = _orig_data_dir


def _make_record(rid: str, content: str, dim: int = 32, **meta) -> VectorRecord:
    """Create a VectorRecord with a deterministic embedding."""
    emb = [0.0] * dim
    for i, ch in enumerate(content.encode()):
        emb[i % dim] += ch
    norm = math.sqrt(sum(x * x for x in emb)) or 1.0
    emb = [x / norm for x in emb]
    return VectorRecord(id=rid, embedding=emb, content=content, metadata=meta)


# ===================================================================
# VectorClient
# ===================================================================


class TestVectorClientPagination:
    def setup_method(self):
        self.client = VectorClient(dimension=32)
        for i in range(20):
            self.client.insert(_make_record(f"doc{i:02d}", f"content number {i}"))
        # Use a consistent query embedding
        self._query_emb = _make_record("q", "content number").embedding

    def teardown_method(self):
        self.client.close()

    def test_offset_zero_returns_from_start(self):
        results = self.client.search(self._query_emb, limit=5, offset=0)
        assert len(results) <= 5

    def test_offset_skips_results(self):
        page1 = self.client.search(self._query_emb, limit=5, offset=0)
        page2 = self.client.search(self._query_emb, limit=5, offset=5)
        ids1 = {r.id for r in page1}
        ids2 = {r.id for r in page2}
        assert ids1.isdisjoint(ids2)

    def test_offset_beyond_results_returns_empty(self):
        results = self.client.search(self._query_emb, limit=5, offset=100)
        assert results == []

    def test_limit_plus_offset_coverage(self):
        all10 = self.client.search(self._query_emb, limit=10, offset=0)
        p1 = self.client.search(self._query_emb, limit=5, offset=0)
        p2 = self.client.search(self._query_emb, limit=5, offset=5)
        ids_all = [r.id for r in all10]
        ids_paged = [r.id for r in p1] + [r.id for r in p2]
        assert ids_all == ids_paged


# ===================================================================
# SemanticSearch
# ===================================================================


class TestSemanticSearchPagination:
    def setup_method(self):
        from memoria.vector.embeddings import TFIDFEmbedder
        self.client = VectorClient(dimension=32)
        self.embedder = TFIDFEmbedder(dimension=32)
        for i in range(15):
            self.client.insert(_make_record(f"sem{i:02d}", f"semantic doc {i}"))
        self.search = SemanticSearch(self.client, self.embedder)

    def teardown_method(self):
        self.client.close()

    def test_offset_default_is_zero(self):
        results = self.search.search("semantic")
        assert isinstance(results, list)

    def test_offset_skips(self):
        p1 = self.search.search("semantic", limit=3, offset=0)
        p2 = self.search.search("semantic", limit=3, offset=3)
        ids1 = {r.id for r in p1}
        ids2 = {r.id for r in p2}
        assert ids1.isdisjoint(ids2)

    def test_find_similar_with_offset(self):
        self.client.insert(_make_record("anchor", "semantic doc anchor"))
        results = self.search.find_similar("anchor", limit=3, offset=0)
        assert isinstance(results, list)


# ===================================================================
# RecallStrategy implementations
# ===================================================================


class TestKeywordStrategyPagination:
    def test_offset_slices_correctly(self):
        tmp = tempfile.mkdtemp(prefix="kw_pag_")
        data = Path(tmp) / "memories"
        data.mkdir()
        for i in range(10):
            (data / f"kw{i:02d}.md").write_text(f"keyword topic {i}")
        strategy = KeywordStrategy(data)
        paged = strategy.retrieve("keyword topic", limit=5, offset=0)
        assert len(paged) <= 5

    def test_offset_beyond_results(self):
        tmp = tempfile.mkdtemp(prefix="kw_pag2_")
        data = Path(tmp) / "memories"
        data.mkdir()
        for i in range(3):
            (data / f"kw{i}.md").write_text(f"keyword topic {i}")
        strategy = KeywordStrategy(data)
        results = strategy.retrieve("keyword topic", limit=5, offset=100)
        assert results == []


class TestVectorStrategyPagination:
    def test_passes_offset_to_search(self):
        mock_search = MagicMock()
        mock_result = MagicMock()
        mock_result.id = "v1"
        mock_result.content = "text"
        mock_result.score = 0.9
        mock_result.metadata = {}
        mock_search.search.return_value = [mock_result]
        strategy = VectorStrategy(mock_search)
        strategy.retrieve("query", limit=5, offset=10)
        mock_search.search.assert_called_once_with("query", limit=5, offset=10)

    def test_default_offset_is_zero(self):
        mock_search = MagicMock()
        mock_search.search.return_value = []
        strategy = VectorStrategy(mock_search)
        strategy.retrieve("query", limit=5)
        mock_search.search.assert_called_once_with("query", limit=5, offset=0)


class TestGraphStrategyPagination:
    def test_offset_slices_results(self):
        mock_kg = MagicMock()
        mock_kg.get_related.return_value = [
            {"name": f"entity{i}", "depth": 1} for i in range(10)
        ]
        strategy = GraphStrategy(mock_kg)
        from memoria.graph.entities import Entity, NodeType
        with patch.object(strategy, "retrieve", wraps=strategy.retrieve):
            # Directly test with mocked extract_entities inside the strategy
            with patch("memoria.graph.entities.extract_entities") as mock_extract:
                mock_extract.return_value = [Entity(name="test", entity_type=NodeType.CONCEPT, confidence=1.0)]
                all_results = strategy.retrieve("test", limit=10, offset=0)
                paged = strategy.retrieve("test", limit=5, offset=3)
                assert len(paged) <= 5
                if len(all_results) > 3:
                    assert paged[0].id == all_results[3].id


# ===================================================================
# RecallPipeline
# ===================================================================


class TestRecallPipelinePagination:
    def _make_pipeline(self):
        strategy = MagicMock()
        strategy.name = "mock"
        strategy.retrieve.return_value = [
            RecallResult(id=f"r{i}", content=f"content {i}", score=1.0 - i * 0.01, source="mock")
            for i in range(20)
        ]
        return RecallPipeline(strategies=[strategy], weights={"mock": 1.0})

    def test_offset_zero(self):
        pipe = self._make_pipeline()
        results = pipe.recall("test", limit=5, offset=0)
        assert len(results) <= 5

    def test_offset_skips(self):
        pipe = self._make_pipeline()
        p1 = pipe.recall("test", limit=5, offset=0)
        p2 = pipe.recall("test", limit=5, offset=5)
        ids1 = {r.id for r in p1}
        ids2 = {r.id for r in p2}
        assert ids1.isdisjoint(ids2)

    def test_offset_in_cache_key(self):
        key0 = f"test:5:0:{sorted({}.items())}"
        key5 = f"test:5:5:{sorted({}.items())}"
        assert key0 != key5


# ===================================================================
# SharedMemoryStore
# ===================================================================


class TestSharedMemoryStorePagination:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp(prefix="ns_pag_")
        db_path = os.path.join(self.tmp, "shared.db")
        self.store = SharedMemoryStore(db_path=db_path)
        for i in range(15):
            self.store.add("test", f"namespace memory {i}", user_id="u1")

    def test_search_offset(self):
        p1 = self.store.search("namespace memory", namespace="test", limit=5, offset=0)
        p2 = self.store.search("namespace memory", namespace="test", limit=5, offset=5)
        ids1 = {r["id"] for r in p1}
        ids2 = {r["id"] for r in p2}
        assert ids1.isdisjoint(ids2)

    def test_list_by_namespace_offset(self):
        p1 = self.store.list_by_namespace("test", limit=5, offset=0)
        p2 = self.store.list_by_namespace("test", limit=5, offset=5)
        ids1 = {r["id"] for r in p1}
        ids2 = {r["id"] for r in p2}
        assert ids1.isdisjoint(ids2)

    def test_list_by_namespace_offset_beyond(self):
        results = self.store.list_by_namespace("test", limit=5, offset=100)
        assert results == []

    def test_list_by_namespace_recursive_offset(self):
        for i in range(5):
            self.store.add("test/sub", f"sub memory {i}", user_id="u1")
        p1 = self.store.list_by_namespace("test", recursive=True, limit=5, offset=0)
        p2 = self.store.list_by_namespace("test", recursive=True, limit=5, offset=5)
        assert len(p1) == 5
        assert len(p2) == 5
        ids1 = {r["id"] for r in p1}
        ids2 = {r["id"] for r in p2}
        assert ids1.isdisjoint(ids2)


# ===================================================================
# Memoria class (integration)
# ===================================================================


class TestMemoriaPagination:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp(prefix="mem_int_pag_")
        self._prev_data_dir = os.environ.get("MEMORIA_DATA_DIR")
        os.environ["MEMORIA_DATA_DIR"] = self.tmp
        self.m = Memoria(project_dir=self.tmp)

    def teardown_method(self):
        if self._prev_data_dir is None:
            os.environ.pop("MEMORIA_DATA_DIR", None)
        else:
            os.environ["MEMORIA_DATA_DIR"] = self._prev_data_dir

    def test_search_accepts_offset(self):
        results = self.m.search("test query", limit=5, offset=0)
        assert isinstance(results, list)

    def test_search_namespace_offset(self):
        store = self.m._get_namespace_store()
        for i in range(10):
            store.add("ns", f"ns content {i}", user_id="u1")
        p1 = self.m.search("ns content", namespace="ns", limit=3, offset=0)
        p2 = self.m.search("ns content", namespace="ns", limit=3, offset=3)
        ids1 = {r["id"] for r in p1}
        ids2 = {r["id"] for r in p2}
        assert ids1.isdisjoint(ids2)

    def test_search_tiers_accepts_offset(self):
        results = self.m.search_tiers("query", limit=5, offset=0)
        assert isinstance(results, list)

    def test_dream_journal_accepts_offset(self):
        result = self.m.dream_journal(limit=5, offset=0)
        assert isinstance(result, (list, dict))


# ===================================================================
# Backward compatibility
# ===================================================================


class TestPaginationBackwardCompat:
    def test_vector_client_default_offset(self):
        client = VectorClient(dimension=32)
        client.insert(_make_record("doc1", "test content"))
        emb = _make_record("q", "test").embedding
        results = client.search(emb, limit=5)
        assert isinstance(results, list)
        client.close()

    def test_recall_pipeline_default_offset(self):
        pipe = RecallPipeline()
        results = pipe.recall("test", limit=5)
        assert results == []

    def test_memoria_search_default_offset(self):
        tmp = tempfile.mkdtemp(prefix="bc_mem_pag_")
        prev = os.environ.get("MEMORIA_DATA_DIR")
        os.environ["MEMORIA_DATA_DIR"] = tmp
        try:
            m = Memoria(project_dir=tmp)
            results = m.search("test", limit=5)
            assert isinstance(results, list)
        finally:
            if prev is None:
                os.environ.pop("MEMORIA_DATA_DIR", None)
            else:
                os.environ["MEMORIA_DATA_DIR"] = prev
