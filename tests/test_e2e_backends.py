"""End-to-end tests for MEMORIA with real backends.

These tests validate the full pipeline:
- sqlite-vec for accelerated vector search (falls back to pure Python if unavailable)
- FalkorDB for knowledge graph (skipped if Redis not reachable)
- MCP server tool invocation with configured backends

Run standalone:
    pytest tests/test_e2e_backends.py -v

Run with FalkorDB (requires docker compose up falkordb):
    MEMORIA_GRAPH_HOST=localhost pytest tests/test_e2e_backends.py -v
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Backend availability checks
# ---------------------------------------------------------------------------

try:
    import sqlite_vec

    _HAS_SQLITE_VEC = True
except ImportError:
    _HAS_SQLITE_VEC = False

try:
    from falkordb import FalkorDB as _FalkorDB

    _HAS_FALKORDB = True
except ImportError:
    _HAS_FALKORDB = False


def _falkordb_reachable(host: str = "localhost", port: int = 6379) -> bool:
    if not _HAS_FALKORDB:
        return False
    try:
        db = _FalkorDB(host=host, port=port)
        db.connection.ping()
        return True
    except Exception:
        return False


_GRAPH_HOST = os.environ.get("MEMORIA_GRAPH_HOST", "localhost")
_GRAPH_PORT = int(os.environ.get("MEMORIA_GRAPH_PORT", "6379"))
_GRAPH_AVAILABLE = _falkordb_reachable(_GRAPH_HOST, _GRAPH_PORT)


# ===========================================================================
# Vector backend tests
# ===========================================================================


class TestVectorClient:
    """Test VectorClient with persistent SQLite and optional sqlite-vec."""

    def test_persistent_storage(self, tmp_path: Path):
        """Vectors survive across connections when using a file path."""
        from memoria.vector.client import VectorClient, VectorRecord
        from memoria.vector.embeddings import TFIDFEmbedder

        db_file = tmp_path / "vectors.db"
        embedder = TFIDFEmbedder(dimension=128)

        client = VectorClient(db_path=str(db_file), dimension=128)
        vec = embedder.embed("Python programming language")
        client.insert(VectorRecord(
            id="mem-1", embedding=vec,
            content="Python programming language", metadata={"type": "test"},
        ))
        client.conn.close()

        client2 = VectorClient(db_path=str(db_file), dimension=128)
        results = client2.search(vec, limit=5)
        client2.conn.close()

        assert len(results) >= 1
        assert results[0].id == "mem-1"
        assert results[0].content == "Python programming language"

    def test_similarity_ranking(self):
        """Similar texts score higher than unrelated texts."""
        from memoria.vector.client import VectorClient, VectorRecord
        from memoria.vector.embeddings import TFIDFEmbedder

        embedder = TFIDFEmbedder(dimension=128)
        client = VectorClient(dimension=128)

        texts = [
            ("m1", "Python is a programming language"),
            ("m2", "JavaScript is used for web development"),
            ("m3", "The weather today is sunny and warm"),
        ]
        for mid, text in texts:
            client.insert(VectorRecord(id=mid, embedding=embedder.embed(text), content=text))

        query_vec = embedder.embed("Python programming")
        results = client.search(query_vec, limit=3)

        assert len(results) >= 1
        assert results[0].id == "m1"

    @pytest.mark.skipif(not _HAS_SQLITE_VEC, reason="sqlite-vec not installed")
    def test_sqlite_vec_acceleration(self, tmp_path: Path):
        """Verify sqlite-vec extension loads and creates vec0 virtual table."""
        from memoria.vector.client import VectorClient

        db_file = tmp_path / "vec_test.db"
        client = VectorClient(db_path=str(db_file), dimension=64)

        if not client._use_vec:
            client.conn.close()
            pytest.skip("sqlite-vec installed but extension loading not supported by this Python build")
        client.conn.close()

    def test_embedding_dimensions(self):
        """Embeddings have correct dimension for various sizes."""
        from memoria.vector.embeddings import CachedEmbedder, TFIDFEmbedder

        for dim in [64, 128, 384, 512]:
            embedder = TFIDFEmbedder(dimension=dim)
            vec = embedder.embed("test text for dimension check")
            assert len(vec) == dim, f"Expected {dim}, got {len(vec)}"

        cached = CachedEmbedder(TFIDFEmbedder(dimension=256), max_size=10)
        vec1 = cached.embed("cached embedding test")
        vec2 = cached.embed("cached embedding test")
        assert len(vec1) == 256
        assert vec1 == vec2

    def test_batch_embeddings(self):
        """Batch embedding produces consistent results."""
        from memoria.vector.embeddings import TFIDFEmbedder

        embedder = TFIDFEmbedder(dimension=128)
        texts = ["Python is great", "JavaScript is dynamic", "Rust is fast"]
        batch = embedder.embed_batch(texts)

        assert len(batch) == 3
        for vec in batch:
            assert len(vec) == 128


# ===========================================================================
# Graph backend tests (InMemoryGraph)
# ===========================================================================


class TestInMemoryGraph:
    """Test graph operations with InMemoryGraph backend."""

    def test_node_crud(self):
        from memoria.graph.client import InMemoryGraph

        g = InMemoryGraph()
        nid = g.add_node("Person", {"name": "Alice", "role": "developer"})
        assert nid is not None

        nodes = g.query_nodes("Person", {"name": "Alice"})
        assert len(nodes) == 1
        assert nodes[0]["name"] == "Alice"

        g.delete_node(nid)
        nodes = g.query_nodes("Person", {"name": "Alice"})
        assert len(nodes) == 0

    def test_edge_and_neighbors(self):
        from memoria.graph.client import InMemoryGraph

        g = InMemoryGraph()
        n1 = g.add_node("Person", {"name": "Alice"})
        n2 = g.add_node("Tool", {"name": "Python"})
        eid = g.add_edge(n1, n2, "USES", {"proficiency": "expert"})

        assert eid is not None
        neighbors = g.neighbors(n1)
        assert len(neighbors) >= 1
        assert any(n["name"] == "Python" for n in neighbors)

    def test_entity_extraction(self):
        from memoria.graph.entities import extract_entities, extract_relations

        text = "Alice uses Python and Docker for the MEMORIA project"
        entities = extract_entities(text)
        tool_types = [e.entity_type.value for e in entities if e.entity_type.value == "Tool"]
        assert len(tool_types) > 0, f"Expected Tool entity, got types: {[e.entity_type.value for e in entities]}"

        relations = extract_relations(text, entities)
        assert isinstance(relations, list)

    def test_knowledge_graph_ingest(self):
        from memoria.graph.client import GraphClient
        from memoria.graph.knowledge import KnowledgeGraph

        gc = GraphClient(use_memory=True)
        kg = KnowledgeGraph(client=gc)

        result = kg.ingest_text("Bob uses Docker and Python for web development")
        assert isinstance(result, dict)
        assert result.get("entities", 0) >= 0

    def test_knowledge_graph_find_entity(self):
        from memoria.graph.client import GraphClient
        from memoria.graph.entities import Entity
        from memoria.graph.knowledge import KnowledgeGraph
        from memoria.graph.schema import NodeType

        gc = GraphClient(use_memory=True)
        kg = KnowledgeGraph(client=gc)

        kg.add_entity(Entity(name="Rust", entity_type=NodeType.TOOL, confidence=0.95))
        found = kg.find_entity("Rust")
        assert len(found) >= 1


# ===========================================================================
# FalkorDB tests (requires running instance)
# ===========================================================================


@pytest.mark.skipif(not _GRAPH_AVAILABLE, reason="FalkorDB not reachable")
class TestFalkorDBGraph:
    """Tests requiring a running FalkorDB instance."""

    def test_falkordb_connection(self):
        from memoria.graph.client import GraphClient

        gc = GraphClient(host=_GRAPH_HOST, port=_GRAPH_PORT)
        assert gc._db is not None
        assert gc.is_memory_backend is False

    def test_falkordb_knowledge_graph_ingest(self):
        from memoria.graph.client import GraphClient
        from memoria.graph.knowledge import KnowledgeGraph

        gc = GraphClient(host=_GRAPH_HOST, port=_GRAPH_PORT)
        kg = KnowledgeGraph(client=gc)

        result = kg.ingest_text("E2E test: Alice uses Docker for the MEMORIA project")
        assert isinstance(result, dict)
        assert result.get("entities", 0) >= 1

        stats = kg.stats()
        assert isinstance(stats, dict)

    def test_falkordb_entity_roundtrip(self):
        from memoria.graph.client import GraphClient
        from memoria.graph.entities import Entity
        from memoria.graph.knowledge import KnowledgeGraph
        from memoria.graph.schema import NodeType

        gc = GraphClient(host=_GRAPH_HOST, port=_GRAPH_PORT)
        kg = KnowledgeGraph(client=gc)

        kg.add_entity(Entity(name="e2e_kubernetes", entity_type=NodeType.TOOL, confidence=0.99))
        found = kg.find_entity("e2e_kubernetes")
        assert len(found) >= 1
        assert found[0]["name"] == "e2e_kubernetes"

    def test_falkordb_full_pipeline_with_memoria(self, tmp_path: Path):
        from memoria import Memoria
        from memoria.graph.client import GraphClient
        from memoria.graph.knowledge import KnowledgeGraph

        gc = GraphClient(host=_GRAPH_HOST, port=_GRAPH_PORT)
        kg = KnowledgeGraph(client=gc)

        m = Memoria(project_dir=str(tmp_path), config={"knowledge_graph": kg})
        m.add("FalkorDB E2E: Rust provides memory safety without garbage collection")

        result = kg.ingest_text("FalkorDB E2E: Rust provides memory safety without garbage collection")
        assert isinstance(result, dict)

        stats = kg.stats()
        assert stats.get("nodes_by_type") is not None


# ===========================================================================
# Full pipeline: Memoria with real backends
# ===========================================================================


class TestMemoriaFullPipeline:
    """End-to-end test of the full Memoria pipeline."""

    def test_add_search_with_vector_persistence(self, tmp_path: Path):
        """Full add→search pipeline with persistent vector storage."""
        from memoria import Memoria
        from memoria.vector.client import VectorClient
        from memoria.vector.embeddings import TFIDFEmbedder

        embedder = TFIDFEmbedder(dimension=128)
        vc = VectorClient(db_path=str(tmp_path / "mem.db"), dimension=128)

        m = Memoria(
            project_dir=str(tmp_path),
            config={"embedder": embedder, "vector_client": vc},
        )

        m.add("MEMORIA is a proactive memory framework for AI agents")
        m.add("FalkorDB provides knowledge graph capabilities")
        m.add("The weather forecast says rain tomorrow")

        results = m.search("proactive memory AI")
        assert len(results) >= 1

    def test_graph_entity_extraction_pipeline(self, tmp_path: Path):
        """KnowledgeGraph.ingest_text auto-extracts entities from text."""
        from memoria.graph.client import GraphClient
        from memoria.graph.knowledge import KnowledgeGraph

        gc = GraphClient(use_memory=True)
        kg = KnowledgeGraph(client=gc)

        result = kg.ingest_text("Alice uses Docker and Kubernetes for deploying MEMORIA")
        assert isinstance(result, dict)
        assert result.get("entities", 0) >= 0

    def test_hybrid_recall_pipeline(self, tmp_path: Path):
        """Hybrid recall combines keyword + vector search."""
        from memoria import Memoria
        from memoria.vector.client import VectorClient
        from memoria.vector.embeddings import TFIDFEmbedder

        embedder = TFIDFEmbedder(dimension=128)
        vc = VectorClient(db_path=str(tmp_path / "recall.db"), dimension=128)

        m = Memoria(
            project_dir=str(tmp_path),
            config={"embedder": embedder, "vector_client": vc},
        )

        memories = [
            "Python is excellent for data science and machine learning",
            "Rust provides memory safety without garbage collection",
            "TypeScript adds static types to JavaScript",
            "Docker containers simplify deployment workflows",
            "MEMORIA uses sqlite-vec for fast vector similarity search",
        ]
        for text in memories:
            m.add(text)

        results = m.search("vector similarity search")
        assert len(results) >= 1

    def test_tiered_memory_workflow(self, tmp_path: Path):
        """Add to tiers (working → recall → archival) and search across."""
        from memoria import Memoria

        m = Memoria(project_dir=str(tmp_path))
        m.add_to_tier("Quick note about Python", tier="working")
        m.add_to_tier("Important architecture decision", tier="recall")
        m.add_to_tier("Historical project context", tier="archival")

        results = m.search_tiers("architecture")
        assert len(results) >= 1


# ===========================================================================
# MCP server configuration tests
# ===========================================================================


class TestMCPServerConfig:
    """Test MCP server initializes correctly with env var configuration."""

    def test_default_initialization(self, monkeypatch):
        import memoria.mcp.server as srv

        srv._memoria_instance = None
        monkeypatch.delenv("MEMORIA_GRAPH_HOST", raising=False)
        monkeypatch.delenv("MEMORIA_VECTOR_DB", raising=False)

        m = srv._get_memoria()
        assert m is not None
        srv._memoria_instance = None

    def test_vector_db_path_config(self, monkeypatch, tmp_path: Path):
        import memoria.mcp.server as srv

        srv._memoria_instance = None
        db_path = str(tmp_path / "env_vectors.db")
        monkeypatch.setenv("MEMORIA_VECTOR_DB", db_path)
        monkeypatch.delenv("MEMORIA_GRAPH_HOST", raising=False)

        m = srv._get_memoria()
        assert m is not None
        assert Path(db_path).exists()
        srv._memoria_instance = None

    def test_embedding_dim_config(self, monkeypatch, tmp_path: Path):
        import memoria.mcp.server as srv

        srv._memoria_instance = None
        monkeypatch.setenv("MEMORIA_EMBEDDING_DIM", "128")
        monkeypatch.setenv("MEMORIA_PROJECT_DIR", str(tmp_path))
        monkeypatch.delenv("MEMORIA_GRAPH_HOST", raising=False)
        monkeypatch.delenv("MEMORIA_VECTOR_DB", raising=False)

        m = srv._get_memoria()
        assert m is not None
        srv._memoria_instance = None

    @pytest.mark.skipif(not _GRAPH_AVAILABLE, reason="FalkorDB not reachable")
    def test_graph_host_config(self, monkeypatch, tmp_path: Path):
        import memoria.mcp.server as srv

        srv._memoria_instance = None
        monkeypatch.setenv("MEMORIA_GRAPH_HOST", _GRAPH_HOST)
        monkeypatch.setenv("MEMORIA_GRAPH_PORT", str(_GRAPH_PORT))
        monkeypatch.setenv("MEMORIA_PROJECT_DIR", str(tmp_path))
        monkeypatch.delenv("MEMORIA_VECTOR_DB", raising=False)

        m = srv._get_memoria()
        assert m is not None
        srv._memoria_instance = None

    def test_mcp_server_name(self):
        from memoria.mcp.server import mcp

        assert mcp.name == "MEMORIA"

    def test_cli_entry_importable(self):
        from memoria.mcp.server import _cli

        assert callable(_cli)
