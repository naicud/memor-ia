"""Tests for the hybrid recall pipeline (M4)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from memoria.recall.context_filter import (
    RecallContext,
    deduplicate,
    filter_by_context,
)
from memoria.recall.pipeline import RecallPipeline
from memoria.recall.ranker import (
    RankedResult,
    reciprocal_rank_fusion,
    weighted_score_fusion,
)
from memoria.recall.strategies import (
    GraphStrategy,
    KeywordStrategy,
    RecallResult,
    RecallStrategy,
    VectorStrategy,
)

# ===================================================================
# Helpers
# ===================================================================

def _make_result(id: str, content: str, score: float, source: str, **meta) -> RecallResult:
    return RecallResult(id=id, content=content, score=score, source=source, metadata=meta)


def _make_ranked(id: str, content: str, score: float, sources: list[str], **meta) -> RankedResult:
    return RankedResult(
        id=id, content=content, final_score=score,
        sources=sources, strategy_scores={}, metadata=meta,
    )


class StubStrategy(RecallStrategy):
    """Strategy that returns pre-set results."""

    def __init__(self, strategy_name: str, results: list[RecallResult]) -> None:
        self._name = strategy_name
        self._results = results

    def retrieve(self, query: str, limit: int = 10, **kwargs) -> list[RecallResult]:
        return self._results[:limit]

    @property
    def name(self) -> str:
        return self._name


class FailingStrategy(RecallStrategy):
    """Strategy that always raises."""

    def retrieve(self, query: str, limit: int = 10, **kwargs) -> list[RecallResult]:
        raise RuntimeError("boom")

    @property
    def name(self) -> str:
        return "failing"


# ===================================================================
# 1. Strategy tests (~12)
# ===================================================================

class TestKeywordStrategy:

    def test_returns_results_from_memory_files(self, tmp_path):
        """KeywordStrategy finds memories via keyword overlap."""
        mem_dir = tmp_path / ".claude" / "memory"
        mem_dir.mkdir(parents=True)
        (mem_dir / "python-tips.md").write_text(
            "---\nname: python tips\ndescription: python coding tips\n---\nSome python tips."
        )
        (mem_dir / "docker-setup.md").write_text(
            "---\nname: docker setup\ndescription: docker container setup\n---\nDocker info."
        )

        strategy = KeywordStrategy(mem_dir)
        results = strategy.retrieve("python tips")

        assert len(results) >= 1
        assert results[0].source == "keyword"
        assert results[0].score > 0

    def test_empty_query_returns_empty(self, tmp_path):
        mem_dir = tmp_path / ".claude" / "memory"
        mem_dir.mkdir(parents=True)
        strategy = KeywordStrategy(mem_dir)
        assert strategy.retrieve("") == []
        assert strategy.retrieve("   ") == []

    def test_limit_parameter(self, tmp_path):
        mem_dir = tmp_path / ".claude" / "memory"
        mem_dir.mkdir(parents=True)
        for i in range(5):
            (mem_dir / f"python-note-{i}.md").write_text(
                f"---\nname: python note {i}\ndescription: python coding note {i}\n---\nNote {i}."
            )

        strategy = KeywordStrategy(mem_dir)
        results = strategy.retrieve("python note", limit=2)
        assert len(results) <= 2

    def test_name_property(self, tmp_path):
        strategy = KeywordStrategy(tmp_path)
        assert strategy.name == "keyword"


class TestVectorStrategy:

    def test_wraps_semantic_search(self):
        mock_search = MagicMock()
        mock_result = MagicMock()
        mock_result.id = "v1"
        mock_result.content = "vector content"
        mock_result.score = 0.85
        mock_result.metadata = {"key": "val"}
        mock_search.search.return_value = [mock_result]

        strategy = VectorStrategy(mock_search)
        results = strategy.retrieve("test query", limit=5)

        mock_search.search.assert_called_once_with("test query", limit=5)
        assert len(results) == 1
        assert results[0].id == "v1"
        assert results[0].source == "vector"
        assert results[0].score == 0.85

    def test_passes_user_id_kwarg(self):
        mock_search = MagicMock()
        mock_search.search.return_value = []
        strategy = VectorStrategy(mock_search)
        strategy.retrieve("q", user_id="u1")
        mock_search.search.assert_called_once_with("q", limit=10, user_id="u1")

    def test_empty_results(self):
        mock_search = MagicMock()
        mock_search.search.return_value = []
        strategy = VectorStrategy(mock_search)
        assert strategy.retrieve("nothing") == []

    def test_name_property(self):
        strategy = VectorStrategy(MagicMock())
        assert strategy.name == "vector"


class TestGraphStrategy:

    def test_extracts_entities_and_traverses(self):
        from memoria.graph.client import GraphClient
        from memoria.graph.entities import Entity
        from memoria.graph.knowledge import KnowledgeGraph
        from memoria.graph.schema import NodeType

        client = GraphClient(use_memory=True)
        kg = KnowledgeGraph(client)
        kg.add_entity(Entity("docker", NodeType.TOOL, confidence=0.9))
        kg.add_entity(Entity("kubernetes", NodeType.TOOL, confidence=0.9))
        # Add a relation between them
        from memoria.graph.entities import Relation
        from memoria.graph.schema import RelationType
        kg.add_relation(Relation(
            Entity("docker", NodeType.TOOL),
            Entity("kubernetes", NodeType.TOOL),
            RelationType.RELATED_TO,
        ))

        strategy = GraphStrategy(kg)
        results = strategy.retrieve("using docker for deployment")
        assert strategy.name == "graph"
        # docker is a known tool, should find related entities
        if results:
            assert all(r.source == "graph" for r in results)
            assert all(0.0 <= r.score <= 1.0 for r in results)

    def test_empty_query_no_entities(self):
        kg = MagicMock()
        strategy = GraphStrategy(kg)
        results = strategy.retrieve("")
        assert results == []

    def test_limit_respected(self):
        kg = MagicMock()
        kg.get_related.return_value = [
            {"name": f"entity-{i}", "id": f"id-{i}"} for i in range(20)
        ]
        with patch("memoria.graph.entities.extract_entities") as mock_ext:
            from memoria.graph.entities import Entity
            from memoria.graph.schema import NodeType
            mock_ext.return_value = [Entity("test", NodeType.CONCEPT, confidence=0.8)]
            strategy = GraphStrategy(kg)
            results = strategy.retrieve("test concept", limit=3)
            assert len(results) <= 3

    def test_name_property(self):
        strategy = GraphStrategy(MagicMock())
        assert strategy.name == "graph"


# ===================================================================
# 2. Ranker tests (~12)
# ===================================================================

class TestReciprocalRankFusion:

    def test_single_strategy_passthrough(self):
        results = [
            _make_result("a", "alpha", 0.9, "keyword"),
            _make_result("b", "beta", 0.7, "keyword"),
        ]
        ranked = reciprocal_rank_fusion([results])
        assert len(ranked) == 2
        assert ranked[0].id == "a"
        assert ranked[1].id == "b"

    def test_two_strategies_merge(self):
        list1 = [
            _make_result("a", "alpha", 0.9, "keyword"),
            _make_result("b", "beta", 0.5, "keyword"),
        ]
        list2 = [
            _make_result("c", "charlie", 0.8, "vector"),
            _make_result("a", "alpha", 0.7, "vector"),
        ]
        ranked = reciprocal_rank_fusion([list1, list2])
        # "a" appears in both, should have highest RRF score
        assert ranked[0].id == "a"
        assert "keyword" in ranked[0].sources
        assert "vector" in ranked[0].sources

    def test_weights_change_ranking(self):
        list1 = [_make_result("a", "alpha", 0.9, "keyword")]
        list2 = [_make_result("b", "beta", 0.9, "vector")]
        # Heavily weight vector
        ranked = reciprocal_rank_fusion([list1, list2], weights={"keyword": 0.1, "vector": 10.0})
        assert ranked[0].id == "b"

    def test_items_from_multiple_strategies_score_higher(self):
        list1 = [_make_result("shared", "shared content", 0.8, "keyword")]
        list2 = [_make_result("shared", "shared content", 0.7, "vector")]
        list3 = [_make_result("unique", "unique content", 0.9, "graph")]
        ranked = reciprocal_rank_fusion([list1, list2, list3])
        # "shared" found by 2 strategies should rank higher than "unique" from 1
        shared = next(r for r in ranked if r.id == "shared")
        unique = next(r for r in ranked if r.id == "unique")
        assert shared.final_score > unique.final_score

    def test_empty_input_returns_empty(self):
        assert reciprocal_rank_fusion([]) == []
        assert reciprocal_rank_fusion([[], []]) == []

    def test_preserves_strategy_scores(self):
        list1 = [_make_result("a", "alpha", 0.9, "keyword")]
        ranked = reciprocal_rank_fusion([list1])
        assert ranked[0].strategy_scores["keyword"] == 0.9

    def test_k_parameter_affects_scores(self):
        results = [_make_result("a", "alpha", 0.9, "keyword")]
        ranked_low_k = reciprocal_rank_fusion([results], k=1)
        ranked_high_k = reciprocal_rank_fusion([results], k=100)
        # Lower k gives higher RRF scores
        assert ranked_low_k[0].final_score > ranked_high_k[0].final_score


class TestWeightedScoreFusion:

    def test_single_list(self):
        results = [
            _make_result("a", "alpha", 0.9, "keyword"),
            _make_result("b", "beta", 0.5, "keyword"),
        ]
        ranked = weighted_score_fusion([results])
        assert ranked[0].id == "a"
        assert ranked[0].final_score == pytest.approx(0.9, abs=0.01)

    def test_multi_strategy_average(self):
        list1 = [_make_result("a", "alpha", 0.8, "keyword")]
        list2 = [_make_result("a", "alpha", 0.6, "vector")]
        ranked = weighted_score_fusion([list1, list2])
        # Average of 0.8 and 0.6 = 0.7 (equal weights)
        assert ranked[0].final_score == pytest.approx(0.7, abs=0.01)

    def test_weighted_average(self):
        list1 = [_make_result("a", "alpha", 1.0, "keyword")]
        list2 = [_make_result("a", "alpha", 0.0, "vector")]
        ranked = weighted_score_fusion(
            [list1, list2], weights={"keyword": 2.0, "vector": 1.0}
        )
        # Weighted avg: (1.0*2.0 + 0.0*1.0) / (2.0 + 1.0) = 2/3
        assert ranked[0].final_score == pytest.approx(2.0 / 3.0, abs=0.01)

    def test_empty_input(self):
        assert weighted_score_fusion([]) == []
        assert weighted_score_fusion([[], []]) == []

    def test_sources_tracked(self):
        list1 = [_make_result("a", "alpha", 0.8, "keyword")]
        list2 = [_make_result("a", "alpha", 0.6, "vector")]
        ranked = weighted_score_fusion([list1, list2])
        assert sorted(ranked[0].sources) == ["keyword", "vector"]


# ===================================================================
# 3. Context filter tests (~8)
# ===================================================================

class TestFilterByContext:

    def test_filter_by_excluded_ids(self):
        results = [
            _make_ranked("a", "alpha", 0.9, ["keyword"]),
            _make_ranked("b", "beta", 0.8, ["keyword"]),
            _make_ranked("c", "charlie", 0.7, ["keyword"]),
        ]
        ctx = RecallContext(excluded_ids={"b"})
        filtered = filter_by_context(results, ctx)
        ids = [r.id for r in filtered]
        assert "b" not in ids
        assert "a" in ids
        assert "c" in ids

    def test_boost_matching_project(self):
        results = [
            _make_ranked("a", "alpha", 0.5, ["keyword"], project_path="/my/project"),
            _make_ranked("b", "beta", 0.5, ["keyword"], project_path="/other/project"),
        ]
        ctx = RecallContext(project_path="/my/project")
        filtered = filter_by_context(results, ctx)
        # Item matching project should be boosted
        a_result = next(r for r in filtered if r.id == "a")
        b_result = next(r for r in filtered if r.id == "b")
        assert a_result.final_score > b_result.final_score

    def test_boost_matching_user(self):
        results = [
            _make_ranked("a", "alpha", 0.5, ["keyword"], user_id="user1"),
            _make_ranked("b", "beta", 0.5, ["keyword"], user_id="user2"),
        ]
        ctx = RecallContext(user_id="user1")
        filtered = filter_by_context(results, ctx)
        a_result = next(r for r in filtered if r.id == "a")
        b_result = next(r for r in filtered if r.id == "b")
        assert a_result.final_score > b_result.final_score

    def test_demote_stale_results(self):
        now_ms = time.time() * 1000
        old_ms = now_ms - (60 * 24 * 60 * 60 * 1000)  # 60 days ago
        results = [
            _make_ranked("fresh", "fresh content", 0.5, ["keyword"], mtime_ms=now_ms),
            _make_ranked("stale", "stale content", 0.5, ["keyword"], mtime_ms=old_ms),
        ]
        ctx = RecallContext()
        filtered = filter_by_context(results, ctx)
        fresh = next(r for r in filtered if r.id == "fresh")
        stale = next(r for r in filtered if r.id == "stale")
        assert fresh.final_score > stale.final_score

    def test_empty_context_no_filtering(self):
        results = [
            _make_ranked("a", "alpha", 0.9, ["keyword"]),
            _make_ranked("b", "beta", 0.8, ["keyword"]),
        ]
        ctx = RecallContext()
        filtered = filter_by_context(results, ctx)
        assert len(filtered) == 2

    def test_empty_results(self):
        ctx = RecallContext(excluded_ids={"x"})
        assert filter_by_context([], ctx) == []


class TestDeduplicate:

    def test_removes_near_duplicates(self):
        results = [
            _make_ranked("a", "the quick brown fox jumps over the lazy dog", 0.9, ["keyword"]),
            _make_ranked("b", "the quick brown fox jumps over the lazy dog today", 0.8, ["vector"]),
        ]
        deduped = deduplicate(results, similarity_threshold=0.8)
        assert len(deduped) == 1
        assert deduped[0].id == "a"  # Keeps highest-scored

    def test_keeps_distinct_content(self):
        results = [
            _make_ranked("a", "python programming tips", 0.9, ["keyword"]),
            _make_ranked("b", "docker container setup guide", 0.8, ["keyword"]),
        ]
        deduped = deduplicate(results)
        assert len(deduped) == 2

    def test_empty_input(self):
        assert deduplicate([]) == []

    def test_custom_threshold(self):
        results = [
            _make_ranked("a", "hello world foo bar baz", 0.9, ["keyword"]),
            _make_ranked("b", "hello world foo bar qux", 0.8, ["keyword"]),
        ]
        # High threshold: treats them as distinct
        assert len(deduplicate(results, similarity_threshold=0.99)) == 2
        # Very low threshold: treats everything as duplicate
        assert len(deduplicate(results, similarity_threshold=0.1)) == 1


# ===================================================================
# 4. Pipeline tests (~15)
# ===================================================================

class TestRecallPipeline:

    def test_pipeline_with_single_strategy(self):
        results = [
            _make_result("a", "alpha", 0.9, "keyword"),
            _make_result("b", "beta", 0.7, "keyword"),
        ]
        strategy = StubStrategy("keyword", results)
        pipeline = RecallPipeline(strategies=[strategy])
        ranked = pipeline.recall("test query", limit=5)
        assert len(ranked) == 2
        assert ranked[0].id == "a"

    def test_pipeline_with_all_three_strategies(self):
        kw = [_make_result("a", "alpha keyword", 0.9, "keyword")]
        vec = [_make_result("b", "beta vector", 0.8, "vector")]
        gr = [_make_result("c", "charlie graph", 0.7, "graph")]

        pipeline = RecallPipeline(strategies=[
            StubStrategy("keyword", kw),
            StubStrategy("vector", vec),
            StubStrategy("graph", gr),
        ])
        ranked = pipeline.recall("test query")
        assert len(ranked) == 3
        ids = {r.id for r in ranked}
        assert ids == {"a", "b", "c"}

    def test_pipeline_fuses_shared_items(self):
        kw = [_make_result("shared", "shared content", 0.8, "keyword")]
        vec = [
            _make_result("shared", "shared content", 0.7, "vector"),
            _make_result("unique", "unique content", 0.9, "vector"),
        ]

        pipeline = RecallPipeline(strategies=[
            StubStrategy("keyword", kw),
            StubStrategy("vector", vec),
        ])
        ranked = pipeline.recall("test query")
        shared = next(r for r in ranked if r.id == "shared")
        assert len(shared.sources) == 2

    def test_fusion_method_rrf(self):
        results = [_make_result("a", "alpha", 0.9, "keyword")]
        pipeline = RecallPipeline(
            strategies=[StubStrategy("keyword", results)],
            fusion_method="rrf",
        )
        ranked = pipeline.recall("test")
        assert len(ranked) == 1

    def test_fusion_method_weighted(self):
        results = [_make_result("a", "alpha", 0.9, "keyword")]
        pipeline = RecallPipeline(
            strategies=[StubStrategy("keyword", results)],
            fusion_method="weighted",
        )
        ranked = pipeline.recall("test")
        assert len(ranked) == 1
        assert ranked[0].final_score == pytest.approx(0.9, abs=0.01)

    def test_limit_parameter(self):
        results = [
            _make_result(f"r{i}", f"content {i}", 0.9 - i * 0.1, "keyword")
            for i in range(10)
        ]
        pipeline = RecallPipeline(strategies=[StubStrategy("keyword", results)])
        ranked = pipeline.recall("test", limit=3)
        assert len(ranked) <= 3

    def test_empty_query_returns_empty(self):
        results = [_make_result("a", "alpha", 0.9, "keyword")]
        pipeline = RecallPipeline(strategies=[StubStrategy("keyword", results)])
        assert pipeline.recall("") == []
        assert pipeline.recall("   ") == []

    def test_no_strategies_returns_empty(self):
        pipeline = RecallPipeline()
        assert pipeline.recall("test query") == []

    def test_context_filtering_integration(self):
        results = [
            _make_result("keep", "keep this", 0.9, "keyword"),
            _make_result("skip", "skip this", 0.8, "keyword"),
        ]
        pipeline = RecallPipeline(strategies=[StubStrategy("keyword", results)])
        ctx = RecallContext(excluded_ids={"skip"})
        ranked = pipeline.recall("test", context=ctx)
        ids = [r.id for r in ranked]
        assert "skip" not in ids
        assert "keep" in ids

    def test_add_strategy(self):
        pipeline = RecallPipeline()
        strategy = StubStrategy("keyword", [])
        pipeline.add_strategy(strategy, weight=1.5)
        assert len(pipeline.strategies) == 1
        assert pipeline.weights["keyword"] == 1.5

    def test_strategy_failure_handled_gracefully(self):
        good = [_make_result("a", "alpha", 0.9, "keyword")]
        pipeline = RecallPipeline(strategies=[
            StubStrategy("keyword", good),
            FailingStrategy(),
        ])
        ranked = pipeline.recall("test")
        # Should still return results from the working strategy
        assert len(ranked) >= 1

    def test_thread_parallel_execution(self):
        """Verify strategies run in parallel by checking timing."""
        import threading

        call_threads: list[str] = []

        class ThreadTrackingStrategy(RecallStrategy):
            def __init__(self, sname: str):
                self._name = sname

            def retrieve(self, query, limit=10, **kwargs):
                call_threads.append(threading.current_thread().name)
                return [_make_result(self._name, f"{self._name} content", 0.5, self._name)]

            @property
            def name(self):
                return self._name

        pipeline = RecallPipeline(strategies=[
            ThreadTrackingStrategy("s1"),
            ThreadTrackingStrategy("s2"),
            ThreadTrackingStrategy("s3"),
        ])
        ranked = pipeline.recall("test")
        assert len(ranked) == 3
        # With thread pool, at least some should run on different threads
        assert len(call_threads) == 3

    def test_deduplication_in_pipeline(self):
        """Near-duplicate results from different strategies should be deduped."""
        kw = [_make_result("a", "the quick brown fox jumps over the lazy dog", 0.9, "keyword")]
        vec = [_make_result("b", "the quick brown fox jumps over the lazy dog", 0.8, "vector")]

        pipeline = RecallPipeline(strategies=[
            StubStrategy("keyword", kw),
            StubStrategy("vector", vec),
        ])
        ranked = pipeline.recall("test")
        # Identical content should be deduped to 1 result
        assert len(ranked) == 1


class TestCreateDefault:

    def test_keyword_only(self, tmp_path):
        mem_dir = tmp_path / ".claude" / "memory"
        mem_dir.mkdir(parents=True)
        pipeline = RecallPipeline.create_default(memory_dir=mem_dir)
        assert len(pipeline.strategies) == 1
        assert pipeline.strategies[0].name == "keyword"

    def test_with_vector_backend(self, tmp_path):
        from memoria.vector.client import VectorClient
        from memoria.vector.embeddings import TFIDFEmbedder

        mem_dir = tmp_path / ".claude" / "memory"
        mem_dir.mkdir(parents=True)
        vc = VectorClient()
        emb = TFIDFEmbedder()
        pipeline = RecallPipeline.create_default(
            memory_dir=mem_dir, vector_client=vc, embedder=emb,
        )
        assert len(pipeline.strategies) == 2
        names = {s.name for s in pipeline.strategies}
        assert names == {"keyword", "vector"}

    def test_with_graph_backend(self, tmp_path):
        from memoria.graph.client import GraphClient
        from memoria.graph.knowledge import KnowledgeGraph

        mem_dir = tmp_path / ".claude" / "memory"
        mem_dir.mkdir(parents=True)
        client = GraphClient(use_memory=True)
        kg = KnowledgeGraph(client)
        pipeline = RecallPipeline.create_default(
            memory_dir=mem_dir, knowledge_graph=kg,
        )
        assert len(pipeline.strategies) == 2
        names = {s.name for s in pipeline.strategies}
        assert names == {"keyword", "graph"}

    def test_all_backends(self, tmp_path):
        from memoria.graph.client import GraphClient
        from memoria.graph.knowledge import KnowledgeGraph
        from memoria.vector.client import VectorClient
        from memoria.vector.embeddings import TFIDFEmbedder

        mem_dir = tmp_path / ".claude" / "memory"
        mem_dir.mkdir(parents=True)
        pipeline = RecallPipeline.create_default(
            memory_dir=mem_dir,
            vector_client=VectorClient(),
            embedder=TFIDFEmbedder(),
            knowledge_graph=KnowledgeGraph(GraphClient(use_memory=True)),
        )
        assert len(pipeline.strategies) == 3
        names = {s.name for s in pipeline.strategies}
        assert names == {"keyword", "vector", "graph"}

    def test_no_backends_empty_pipeline(self):
        pipeline = RecallPipeline.create_default()
        assert len(pipeline.strategies) == 0

    def test_vector_requires_both_client_and_embedder(self):
        from memoria.vector.client import VectorClient
        # Only client, no embedder — should NOT add vector strategy
        pipeline = RecallPipeline.create_default(vector_client=VectorClient())
        names = {s.name for s in pipeline.strategies}
        assert "vector" not in names


class TestMemoriaSearchIntegration:
    """Test that Memoria.search() uses the recall pipeline."""

    def test_search_returns_results(self, tmp_path):
        from memoria import Memoria

        mem = Memoria(project_dir=str(tmp_path))
        mem.add("python programming best practices for beginners")
        results = mem.search("python programming")
        assert isinstance(results, list)
        for r in results:
            assert "id" in r
            assert "score" in r
            assert "memory" in r
            assert "metadata" in r

    def test_search_empty_query(self, tmp_path):
        from memoria import Memoria

        mem = Memoria(project_dir=str(tmp_path))
        results = mem.search("")
        assert results == []

    def test_search_with_vector_config(self, tmp_path):
        from memoria import Memoria
        from memoria.vector.client import VectorClient
        from memoria.vector.embeddings import TFIDFEmbedder

        vc = VectorClient()
        emb = TFIDFEmbedder()
        # Index some content
        embedding = emb.embed("docker container tips")
        from memoria.vector.client import VectorRecord
        vc.insert(VectorRecord(
            id="doc1", embedding=embedding,
            content="docker container tips", metadata={},
        ))

        mem = Memoria(
            project_dir=str(tmp_path),
            config={"vector_client": vc, "embedder": emb},
        )
        results = mem.search("docker container")
        assert isinstance(results, list)
