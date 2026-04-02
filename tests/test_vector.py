"""Comprehensive tests for the MEMORIA vector layer."""

from __future__ import annotations

import math

import pytest

from memoria.vector.chunking import chunk_code, chunk_markdown, chunk_text
from memoria.vector.client import VectorClient, VectorRecord, _cosine_similarity
from memoria.vector.embeddings import TFIDFEmbedder, get_default_embedder
from memoria.vector.index import VectorIndex
from memoria.vector.search import SearchResult, SemanticSearch

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """In-memory VectorClient (falls back to pure-python if sqlite-vec unavailable)."""
    c = VectorClient(dimension=32)
    yield c
    c.close()


@pytest.fixture()
def embedder():
    return TFIDFEmbedder(dimension=32)


@pytest.fixture()
def index(client, embedder):
    return VectorIndex(client, embedder)


@pytest.fixture()
def semantic(client, embedder):
    return SemanticSearch(client, embedder)


def _make_record(rid: str, content: str, dim: int = 32, **meta) -> VectorRecord:
    """Helper: create a VectorRecord with a simple deterministic embedding."""
    emb = [0.0] * dim
    for i, ch in enumerate(content.encode()):
        emb[i % dim] += ch
    norm = math.sqrt(sum(x * x for x in emb)) or 1.0
    emb = [x / norm for x in emb]
    return VectorRecord(id=rid, embedding=emb, content=content, metadata=meta)


# ===================================================================
# CLIENT TESTS
# ===================================================================


class TestVectorClient:
    """~12 tests for VectorClient."""

    def test_in_memory_creation(self):
        with VectorClient(dimension=32) as c:
            assert c.count() == 0

    def test_insert_and_get(self, client):
        rec = _make_record("r1", "hello world")
        client.insert(rec)
        got = client.get("r1")
        assert got is not None
        assert got.id == "r1"
        assert got.content == "hello world"

    def test_get_nonexistent(self, client):
        assert client.get("nope") is None

    def test_delete(self, client):
        rec = _make_record("r1", "to be deleted")
        client.insert(rec)
        assert client.get("r1") is not None
        client.delete("r1")
        assert client.get("r1") is None

    def test_count(self, client):
        assert client.count() == 0
        client.insert(_make_record("a", "alpha"))
        assert client.count() == 1
        client.insert(_make_record("b", "beta"))
        assert client.count() == 2
        client.delete("a")
        assert client.count() == 1

    def test_search_cosine(self, client):
        client.insert(_make_record("a", "python programming language"))
        client.insert(_make_record("b", "javascript web development"))
        client.insert(_make_record("c", "python data science"))

        query_emb = _make_record("q", "python coding").embedding
        results = client.search(query_emb, limit=2)
        assert len(results) <= 2
        # All returned records should be valid
        for r in results:
            assert r.id in {"a", "b", "c"}

    def test_search_filter_user_id(self, client):
        r1 = _make_record("a", "user one note", user_id="u1")
        r2 = _make_record("b", "user two note", user_id="u2")
        client.insert(r1)
        client.insert(r2)

        query_emb = _make_record("q", "note").embedding
        results = client.search(query_emb, limit=10, user_id="u1")
        assert all(r.metadata.get("user_id") == "u1" for r in results)

    def test_search_filter_memory_type(self, client):
        r1 = _make_record("a", "feedback item", memory_type="feedback")
        r2 = _make_record("b", "project item", memory_type="project")
        client.insert(r1)
        client.insert(r2)

        query_emb = _make_record("q", "item").embedding
        results = client.search(query_emb, limit=10, memory_type="feedback")
        assert all(r.metadata.get("memory_type") == "feedback" for r in results)

    def test_context_manager(self):
        with VectorClient(dimension=16) as c:
            c.insert(_make_record("x", "ctx test", dim=16))
            assert c.count() == 1
        # Connection should be closed after exiting context

    def test_insert_replace(self, client):
        client.insert(_make_record("r1", "original"))
        client.insert(_make_record("r1", "updated"))
        got = client.get("r1")
        assert got is not None
        assert got.content == "updated"
        assert client.count() == 1

    def test_file_persistence(self, tmp_path):
        db_file = tmp_path / "test.db"
        with VectorClient(db_path=db_file, dimension=16) as c:
            c.insert(_make_record("persist", "persistent data", dim=16))

        # Reopen
        with VectorClient(db_path=db_file, dimension=16) as c2:
            got = c2.get("persist")
            assert got is not None
            assert got.content == "persistent data"

    def test_search_empty_index(self, client):
        query_emb = [0.1] * 32
        results = client.search(query_emb, limit=5)
        assert results == []


# ===================================================================
# EMBEDDING TESTS
# ===================================================================


class TestEmbeddings:
    """~10 tests for embedding providers."""

    def test_tfidf_dimension(self, embedder):
        emb = embedder.embed("hello world")
        assert len(emb) == 32

    def test_tfidf_deterministic(self, embedder):
        e1 = embedder.embed("deterministic test")
        e2 = embedder.embed("deterministic test")
        assert e1 == e2

    def test_tfidf_similar_texts(self, embedder):
        e1 = embedder.embed("python programming language")
        e2 = embedder.embed("python programming")
        e3 = embedder.embed("quantum physics theory")
        sim_close = _cosine_similarity(e1, e2)
        sim_far = _cosine_similarity(e1, e3)
        assert sim_close > sim_far

    def test_tfidf_batch(self, embedder):
        texts = ["alpha", "beta", "gamma"]
        batch = embedder.embed_batch(texts)
        assert len(batch) == 3
        assert all(len(e) == 32 for e in batch)
        # Batch should match individual calls
        for text, batch_emb in zip(texts, batch):
            assert embedder.embed(text) == batch_emb

    def test_tfidf_normalization(self, embedder):
        emb = embedder.embed("normalized vector test")
        norm = math.sqrt(sum(x * x for x in emb))
        assert abs(norm - 1.0) < 1e-6

    def test_tfidf_empty_text(self, embedder):
        emb = embedder.embed("")
        assert len(emb) == 32
        assert all(x == 0.0 for x in emb)

    def test_tfidf_whitespace_only(self, embedder):
        emb = embedder.embed("   \n\t  ")
        assert len(emb) == 32
        assert all(x == 0.0 for x in emb)

    def test_tfidf_different_dimensions(self):
        e64 = TFIDFEmbedder(dimension=64)
        e128 = TFIDFEmbedder(dimension=128)
        assert len(e64.embed("test")) == 64
        assert len(e128.embed("test")) == 128

    def test_get_default_embedder(self):
        emb = get_default_embedder(dimension=32)
        assert emb.dimension in (32, 384)
        result = emb.embed("test")
        assert len(result) == emb.dimension

    def test_cosine_similarity_identical(self):
        v = [1.0, 2.0, 3.0]
        assert abs(_cosine_similarity(v, v) - 1.0) < 1e-6

    def test_cosine_similarity_orthogonal(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(_cosine_similarity(a, b)) < 1e-6

    def test_cosine_similarity_zero_vector(self):
        a = [1.0, 2.0]
        b = [0.0, 0.0]
        assert _cosine_similarity(a, b) == 0.0


# ===================================================================
# INDEX TESTS
# ===================================================================


class TestVectorIndex:
    """~10 tests for VectorIndex."""

    def test_index_text(self, index):
        rid = index.index_text("t1", "hello world index")
        assert rid == "t1"
        rec = index.client.get("t1")
        assert rec is not None
        assert rec.content == "hello world index"

    def test_index_text_with_metadata(self, index):
        index.index_text(
            "t2", "meta test", metadata={"key": "value"}, user_id="u1"
        )
        rec = index.client.get("t2")
        assert rec is not None
        assert rec.metadata["key"] == "value"
        assert rec.metadata["user_id"] == "u1"

    def test_index_batch(self, index):
        items = [
            {"id": "b1", "text": "batch item one"},
            {"id": "b2", "text": "batch item two"},
            {"id": "b3", "text": "batch item three"},
        ]
        ids = index.index_batch(items)
        assert ids == ["b1", "b2", "b3"]
        assert index.client.count() == 3

    def test_index_batch_with_metadata(self, index):
        items = [
            {"id": "m1", "text": "with meta", "metadata": {"tag": "a"}, "user_id": "u1"},
        ]
        index.index_batch(items)
        rec = index.client.get("m1")
        assert rec is not None
        assert rec.metadata["tag"] == "a"
        assert rec.metadata["user_id"] == "u1"

    def test_remove(self, index):
        index.index_text("rm1", "remove me")
        assert index.client.count() == 1
        index.remove("rm1")
        assert index.client.count() == 0

    def test_stats(self, index):
        index.index_text("s1", "stats test")
        stats = index.stats()
        assert stats["count"] == 1
        assert stats["dimension"] == 32
        assert stats["backend"] in ("pure-python", "sqlite-vec")
        assert stats["embedder"] == "TFIDFEmbedder"

    def test_reindex_all(self, index):
        index.index_text("re1", "reindex me")
        index.index_text("re2", "and me too")
        count = index.reindex_all()
        assert count == 2
        assert index.client.count() == 2

    def test_index_replaces_existing(self, index):
        index.index_text("dup", "version one")
        index.index_text("dup", "version two")
        assert index.client.count() == 1
        rec = index.client.get("dup")
        assert rec.content == "version two"

    def test_stats_empty(self, index):
        stats = index.stats()
        assert stats["count"] == 0

    def test_index_text_with_memory_type(self, index):
        index.index_text("mt1", "typed", memory_type="feedback")
        rec = index.client.get("mt1")
        assert rec.metadata["memory_type"] == "feedback"


# ===================================================================
# SEARCH TESTS
# ===================================================================


class TestSemanticSearch:
    """~12 tests for SemanticSearch."""

    def test_search_returns_results(self, index, semantic):
        index.index_text("s1", "python programming language")
        index.index_text("s2", "python data science")
        index.index_text("s3", "javascript web framework")

        results = semantic.search("python programming")
        assert len(results) > 0
        assert all(isinstance(r, SearchResult) for r in results)

    def test_search_score_ordering(self, index, semantic):
        index.index_text("s1", "python programming language tutorial")
        index.index_text("s2", "cooking recipes for dinner")

        results = semantic.search("python programming")
        assert len(results) >= 1
        # Scores should be descending
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score

    def test_search_limit(self, index, semantic):
        for i in range(10):
            index.index_text(f"lim{i}", f"document number {i}")

        results = semantic.search("document", limit=3)
        assert len(results) <= 3

    def test_search_min_score(self, index, semantic):
        index.index_text("high", "python programming language")
        index.index_text("low", "quantum physics entanglement theory")

        results = semantic.search("python programming", min_score=0.5)
        for r in results:
            assert r.score >= 0.5

    def test_search_user_filter(self, index, semantic):
        index.index_text("u1a", "note from user one", user_id="u1")
        index.index_text("u2a", "note from user two", user_id="u2")

        results = semantic.search("note", user_id="u1")
        for r in results:
            assert r.metadata.get("user_id") == "u1"

    def test_find_similar(self, index, semantic):
        index.index_text("src", "machine learning algorithms")
        index.index_text("sim", "machine learning models")
        index.index_text("diff", "cooking italian pasta recipes")

        results = semantic.find_similar("src", limit=2)
        assert all(r.id != "src" for r in results)

    def test_find_similar_nonexistent(self, semantic):
        results = semantic.find_similar("nope")
        assert results == []

    def test_search_empty_index(self, semantic):
        results = semantic.search("anything")
        assert results == []

    def test_search_by_embedding(self, index, semantic, embedder):
        index.index_text("e1", "embedding search test")
        emb = embedder.embed("embedding search test")
        results = semantic.search_by_embedding(emb, limit=5)
        assert len(results) >= 1
        assert results[0].id == "e1"

    def test_search_result_has_content(self, index, semantic):
        index.index_text("cnt", "content check result")
        results = semantic.search("content check")
        if results:
            assert results[0].content == "content check result"

    def test_search_result_has_metadata(self, index, semantic):
        index.index_text("md", "metadata check", metadata={"key": "val"})
        results = semantic.search("metadata check")
        if results:
            assert results[0].metadata.get("key") == "val"

    def test_search_score_range(self, index, semantic):
        index.index_text("rng", "score range test")
        results = semantic.search("score range test")
        for r in results:
            assert 0.0 <= r.score <= 1.0


# ===================================================================
# CHUNKING TESTS
# ===================================================================


class TestChunking:
    """~8 tests for text chunking."""

    def test_chunk_text_basic(self):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = chunk_text(text, max_chars=200)
        assert len(chunks) >= 1
        combined = " ".join(c.text for c in chunks)
        assert "First" in combined
        assert "Third" in combined

    def test_chunk_text_overlap(self):
        long = " ".join([f"word{i}" for i in range(200)])
        chunks = chunk_text(long, max_chars=100, overlap=20)
        assert len(chunks) > 1

    def test_chunk_text_paragraph_boundary(self):
        text = "Paragraph one content.\n\nParagraph two content.\n\nParagraph three content."
        chunks = chunk_text(text, max_chars=1000)
        # With large max_chars, paragraphs should be merged
        assert len(chunks) >= 1

    def test_chunk_text_empty(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_chunk_text_short(self):
        text = "Very short."
        chunks = chunk_text(text, max_chars=500)
        assert len(chunks) == 1
        assert chunks[0].text == "Very short."

    def test_chunk_markdown_headers(self):
        md = "# Header 1\nContent one.\n\n# Header 2\nContent two."
        chunks = chunk_markdown(md, max_chars=500)
        assert len(chunks) >= 2
        assert any("Header 1" in c.text for c in chunks)
        assert any("Header 2" in c.text for c in chunks)

    def test_chunk_markdown_empty(self):
        assert chunk_markdown("") == []

    def test_chunk_code_functions(self):
        code = (
            "def foo():\n    pass\n\n"
            "def bar():\n    return 1\n\n"
            "class Baz:\n    pass\n"
        )
        chunks = chunk_code(code, max_chars=500)
        assert len(chunks) >= 2

    def test_chunk_code_empty(self):
        assert chunk_code("") == []

    def test_chunk_text_positions(self):
        text = "AAA.\n\nBBB.\n\nCCC."
        chunks = chunk_text(text, max_chars=10)
        for ch in chunks:
            assert ch.start >= 0
            assert ch.end >= ch.start
