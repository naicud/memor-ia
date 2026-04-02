"""Tests for semantic deduplication: detector, merger, and integration."""
from __future__ import annotations

import json

import pytest

from memoria.dedup.detector import DuplicateDetector, DuplicateMatch
from memoria.dedup.merger import MemoryMerger, MergeResult

# ===================================================================
# Helper: mock embedder + vector client
# ===================================================================

class _FakeEmbedder:
    """Deterministic embedder for testing — hash-based unit vector."""

    @property
    def dimension(self):
        return 8

    def embed(self, text: str) -> list[float]:
        import hashlib
        h = hashlib.md5(text.encode()).hexdigest()[:16]
        raw = [int(h[i:i+2], 16) / 255.0 for i in range(0, 16, 2)]
        norm = sum(x * x for x in raw) ** 0.5 or 1.0
        return [x / norm for x in raw]

    def embed_batch(self, texts):
        return [self.embed(t) for t in texts]


class _FakeVectorRecord:
    def __init__(self, id, content, embedding, metadata=None, distance=0.0):
        self.id = id
        self.content = content
        self.embedding = embedding
        self.metadata = metadata or {}
        self.distance = distance


class _FakeVectorClient:
    """In-memory vector client for testing."""

    def __init__(self):
        self._records: list[_FakeVectorRecord] = []

    def add_record(self, id, content, embedding, metadata=None):
        self._records.append(_FakeVectorRecord(id, content, embedding, metadata))

    def search(self, query_embedding, limit=5, offset=0, user_id=None, memory_type=None):
        results = []
        for rec in self._records:
            if user_id and rec.metadata.get("user_id") != user_id:
                continue
            dot = sum(a * b for a, b in zip(query_embedding, rec.embedding))
            na = sum(x * x for x in query_embedding) ** 0.5
            nb = sum(x * x for x in rec.embedding) ** 0.5
            sim = dot / (na * nb) if na and nb else 0.0
            distance = 1.0 - sim
            results.append(_FakeVectorRecord(
                id=rec.id,
                content=rec.content,
                embedding=rec.embedding,
                metadata=rec.metadata,
                distance=max(0.0, distance),
            ))
        results.sort(key=lambda r: r.distance)
        return results[offset:offset + limit]


# ===================================================================
# DuplicateDetector
# ===================================================================

class TestDuplicateDetector:
    def setup_method(self):
        self.embedder = _FakeEmbedder()
        self.vc = _FakeVectorClient()
        self.detector = DuplicateDetector(self.embedder, self.vc, threshold=0.90)

    def test_no_records_no_duplicates(self):
        matches = self.detector.find_duplicates("hello world")
        assert matches == []

    def test_exact_duplicate_detected(self):
        text = "This is a test memory about Python programming"
        emb = self.embedder.embed(text)
        self.vc.add_record("mem-1", text, emb)

        matches = self.detector.find_duplicates(text)
        assert len(matches) == 1
        assert matches[0].memory_id == "mem-1"
        assert matches[0].similarity >= 0.99  # exact match

    def test_dissimilar_not_detected(self):
        emb = self.embedder.embed("completely unrelated topic about cooking")
        self.vc.add_record("mem-1", "cooking recipe for pasta", emb)

        matches = self.detector.find_duplicates("Python programming tutorial")
        assert len(matches) == 0

    def test_threshold_configurable(self):
        text = "test content"
        emb = self.embedder.embed(text)
        self.vc.add_record("mem-1", text, emb)

        # With very high threshold, exact match still passes
        self.detector.threshold = 1.0  # max threshold
        matches = self.detector.find_duplicates(text)
        assert len(matches) >= 1  # exact match has similarity ~1.0

        # Reset to permissive
        self.detector.threshold = 0.5
        matches = self.detector.find_duplicates(text)
        assert len(matches) >= 1

    def test_threshold_validation(self):
        with pytest.raises(ValueError):
            self.detector.threshold = -0.1
        with pytest.raises(ValueError):
            self.detector.threshold = 1.5

    def test_is_duplicate_returns_match(self):
        text = "exact duplicate content"
        emb = self.embedder.embed(text)
        self.vc.add_record("mem-1", text, emb)

        match = self.detector.is_duplicate(text)
        assert match is not None
        assert match.memory_id == "mem-1"

    def test_is_duplicate_returns_none(self):
        match = self.detector.is_duplicate("no records at all")
        assert match is None

    def test_empty_content(self):
        matches = self.detector.find_duplicates("")
        assert matches == []

    def test_whitespace_only(self):
        matches = self.detector.find_duplicates("   ")
        assert matches == []

    def test_user_id_filter(self):
        text = "shared memory content"
        emb = self.embedder.embed(text)
        self.vc.add_record("mem-1", text, emb, {"user_id": "alice"})

        matches = self.detector.find_duplicates(text, user_id="bob")
        assert len(matches) == 0

        matches = self.detector.find_duplicates(text, user_id="alice")
        assert len(matches) >= 1

    def test_limit_respected(self):
        for i in range(5):
            text = f"memory content {i}"
            emb = self.embedder.embed(text)
            self.vc.add_record(f"mem-{i}", text, emb)

        # Search for exact duplicate of first one, limit to 2
        matches = self.detector.find_duplicates("memory content 0", limit=2)
        assert len(matches) <= 2

    def test_results_sorted_by_similarity(self):
        text = "important information about the project"
        emb = self.embedder.embed(text)
        self.vc.add_record("mem-1", text, emb)

        # Add a slightly different one (won't match as well with fake embedder)
        text2 = "important information about the project and more details"
        emb2 = self.embedder.embed(text2)
        self.vc.add_record("mem-2", text2, emb2)

        self.detector.threshold = 0.0  # accept everything
        matches = self.detector.find_duplicates(text, limit=10)
        if len(matches) >= 2:
            assert matches[0].similarity >= matches[1].similarity


# ===================================================================
# MemoryMerger
# ===================================================================

class TestMemoryMerger:
    def test_longer_strategy(self):
        merger = MemoryMerger(strategy="longer")
        result = merger.merge("id-1", "short", {}, "this is much longer content")
        assert result.merged_content == "this is much longer content"
        assert result.strategy == "longer"

    def test_longer_keeps_existing_when_longer(self):
        merger = MemoryMerger(strategy="longer")
        result = merger.merge("id-1", "this is the existing longer content", {}, "short")
        assert result.merged_content == "this is the existing longer content"

    def test_newer_strategy(self):
        merger = MemoryMerger(strategy="newer")
        result = merger.merge("id-1", "old content", {}, "brand new content")
        assert result.merged_content == "brand new content"

    def test_combine_strategy(self):
        merger = MemoryMerger(strategy="combine")
        result = merger.merge(
            "id-1",
            "First fact. Second fact",
            {},
            "Second fact. Third fact",
        )
        assert "First fact" in result.merged_content
        assert "Third fact" in result.merged_content

    def test_combine_deduplicates_sentences(self):
        merger = MemoryMerger(strategy="combine")
        result = merger.merge("id-1", "A. B", {}, "A. B. C")
        # C is the only unique sentence from new
        assert "C" in result.merged_content

    def test_metadata_merged(self):
        merger = MemoryMerger()
        result = merger.merge(
            "id-1", "content", {"key1": "val1"}, "new", {"key2": "val2"}
        )
        assert result.merged_metadata["key1"] == "val1"
        assert result.merged_metadata["key2"] == "val2"
        assert "merged_at" in result.merged_metadata
        assert "merge_strategy" in result.merged_metadata

    def test_new_metadata_overrides_existing(self):
        merger = MemoryMerger()
        result = merger.merge("id-1", "c", {"k": "old"}, "c", {"k": "new"})
        assert result.merged_metadata["k"] == "new"

    def test_source_ids(self):
        merger = MemoryMerger()
        result = merger.merge("existing-id", "a", {}, "b")
        assert "existing-id" in result.source_ids

    def test_unknown_strategy_raises(self):
        with pytest.raises(ValueError, match="Unknown merge strategy"):
            MemoryMerger(strategy="invalid")

    def test_none_new_metadata(self):
        merger = MemoryMerger()
        result = merger.merge("id-1", "content", {"k": "v"}, "new", None)
        assert result.merged_metadata["k"] == "v"


# ===================================================================
# MergeResult
# ===================================================================

class TestMergeResult:
    def test_defaults(self):
        r = MergeResult(merged_content="hello")
        assert r.merged_metadata == {}
        assert r.source_ids == []
        assert r.strategy == "longer"


# ===================================================================
# Integration via Memoria class
# ===================================================================

class TestMemoriaDeduplication:
    def test_find_duplicates_empty(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        result = m.find_duplicates("test content")
        assert isinstance(result, list)

    def test_dedup_detector_lazy_init(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        d1 = m._get_dedup_detector()
        d2 = m._get_dedup_detector()
        assert d1 is d2

    def test_dedup_merger_lazy_init(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        m1 = m._get_dedup_merger()
        m2 = m._get_dedup_merger()
        assert m1 is m2

    def test_dedup_disabled_by_default(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        assert not m._dedup_enabled

    def test_dedup_enabled_via_config(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path), config={"dedup_enabled": "true"})
        assert m._dedup_enabled

    def test_dedup_mode_default_warn(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        assert m._dedup_mode == "warn"

    def test_dedup_mode_from_config(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path), config={"dedup_mode": "reject"})
        assert m._dedup_mode == "reject"

    def test_find_duplicates_with_threshold(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        result = m.find_duplicates("test", threshold=0.5)
        assert isinstance(result, list)

    def test_merge_duplicates_not_found(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        result = m.merge_duplicates("nonexistent-id", "new content")
        assert "error" in result

    def test_merge_duplicates_success(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        # First add a memory to the namespace store
        mid = m.add("original content to merge", namespace="test")
        result = m.merge_duplicates(mid, "updated content with more detail", namespace="test")
        assert result["status"] == "merged"
        assert result["memory_id"] == mid

    def test_add_without_dedup_returns_id(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        result = m.add("test memory", namespace="default")
        assert isinstance(result, str)  # UUID string

    def test_add_with_dedup_reject_mode(self, tmp_path):
        """When dedup is on in reject mode and a duplicate is found, add() returns status dict."""
        from unittest.mock import MagicMock, patch

        from memoria import Memoria

        m = Memoria(
            project_dir=str(tmp_path),
            config={"dedup_enabled": "true", "dedup_mode": "reject"},
        )
        fake_match = DuplicateMatch(
            memory_id="existing-123",
            content="existing content",
            similarity=0.95,
            metadata={},
        )
        with patch.object(
            type(m._get_dedup_detector()), "is_duplicate", return_value=fake_match
        ):
            result = m.add("duplicate content", namespace="test")
        assert isinstance(result, dict)
        assert result["status"] == "duplicate"
        assert result["existing_id"] == "existing-123"

    def test_add_with_dedup_warn_mode(self, tmp_path):
        """When dedup is on in warn mode, add() stores but returns warning."""
        from unittest.mock import patch

        from memoria import Memoria

        m = Memoria(
            project_dir=str(tmp_path),
            config={"dedup_enabled": "true", "dedup_mode": "warn"},
        )
        fake_match = DuplicateMatch(
            memory_id="existing-123",
            content="existing content",
            similarity=0.95,
            metadata={},
        )
        with patch.object(
            type(m._get_dedup_detector()), "is_duplicate", return_value=fake_match
        ):
            result = m.add("similar content", namespace="test")
        assert isinstance(result, dict)
        assert result["status"] == "created"
        assert result["warning"] == "similar_memory_exists"
        assert "id" in result

    def test_add_with_dedup_no_match(self, tmp_path):
        """When dedup is enabled but no duplicate found, normal add."""
        from unittest.mock import patch

        from memoria import Memoria

        m = Memoria(
            project_dir=str(tmp_path),
            config={"dedup_enabled": "true", "dedup_mode": "warn"},
        )
        with patch.object(
            type(m._get_dedup_detector()), "is_duplicate", return_value=None
        ):
            result = m.add("unique content", namespace="test")
        assert isinstance(result, str)  # UUID string, no warning
