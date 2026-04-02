"""Tests for the MEMORIA cache layer — backend, memory, redis, factory."""

import json
import os
import threading
import time

import pytest

# ── MemoryCache ──────────────────────────────────────────────────────────

class TestMemoryCache:
    """Tests for the in-memory LRU cache backend."""

    def _make(self, **kwargs):
        from memoria.cache.memory import MemoryCache
        return MemoryCache(**kwargs)

    def test_get_miss(self):
        cache = self._make()
        assert cache.get("nope") is None

    def test_set_get(self):
        cache = self._make()
        cache.set("k1", [1.0, 2.0, 3.0])
        assert cache.get("k1") == [1.0, 2.0, 3.0]

    def test_delete(self):
        cache = self._make()
        cache.set("k1", "value")
        cache.delete("k1")
        assert cache.get("k1") is None

    def test_clear(self):
        cache = self._make()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_lru_eviction(self):
        cache = self._make(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        # Access 'a' to make it most-recently used
        cache.get("a")
        # Insert 'd' — should evict 'b' (least recently used)
        cache.set("d", 4)
        assert cache.get("b") is None
        assert cache.get("a") == 1
        assert cache.get("c") == 3
        assert cache.get("d") == 4

    def test_ttl_expiry(self):
        cache = self._make(default_ttl=1)
        cache.set("k", "val")
        assert cache.get("k") == "val"
        time.sleep(1.1)
        assert cache.get("k") is None

    def test_per_key_ttl(self):
        cache = self._make()
        cache.set("k", "val", ttl=1)
        assert cache.get("k") == "val"
        time.sleep(1.1)
        assert cache.get("k") is None

    def test_invalidate_pattern(self):
        cache = self._make()
        cache.set("embed:abc", [1.0])
        cache.set("embed:def", [2.0])
        cache.set("recall:xyz", [3.0])
        count = cache.invalidate_pattern("embed:*")
        assert count == 2
        assert cache.get("embed:abc") is None
        assert cache.get("recall:xyz") == [3.0]

    def test_stats(self):
        cache = self._make(max_size=100)
        cache.set("k", "v")
        cache.get("k")       # hit
        cache.get("miss")    # miss
        stats = cache.stats()
        assert stats["backend"] == "memory"
        assert stats["size"] == 1
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5

    def test_thread_safety(self):
        cache = self._make(max_size=1000)
        errors = []

        def writer(start):
            try:
                for i in range(100):
                    cache.set(f"k{start + i}", i)
            except Exception as e:
                errors.append(e)

        def reader(start):
            try:
                for i in range(100):
                    cache.get(f"k{start + i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer, args=(0,)),
            threading.Thread(target=writer, args=(100,)),
            threading.Thread(target=reader, args=(0,)),
            threading.Thread(target=reader, args=(100,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors

    def test_set_overwrites(self):
        cache = self._make()
        cache.set("k", "old")
        cache.set("k", "new")
        assert cache.get("k") == "new"

    def test_complex_values(self):
        cache = self._make()
        val = {"nested": [1, 2, {"deep": True}]}
        cache.set("complex", val)
        assert cache.get("complex") == val

    def test_stats_after_clear(self):
        cache = self._make()
        cache.set("k", "v")
        cache.get("k")
        cache.clear()
        stats = cache.stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0


# ── CacheBackend ABC ────────────────────────────────────────────────────

class TestCacheBackendInterface:
    """Verify the ABC cannot be instantiated directly."""

    def test_cannot_instantiate(self):
        from memoria.cache.backend import CacheBackend
        with pytest.raises(TypeError):
            CacheBackend()  # type: ignore[abstract]


# ── Factory ─────────────────────────────────────────────────────────────

class TestFactory:
    """Tests for create_cache factory."""

    def test_default_memory(self):
        from memoria.cache import create_cache
        cache = create_cache()
        stats = cache.stats()
        assert stats["backend"] == "memory"

    def test_explicit_memory(self):
        from memoria.cache import create_cache
        cache = create_cache(backend="memory", max_size=50)
        stats = cache.stats()
        assert stats["backend"] == "memory"
        assert stats["max_size"] == 50

    def test_env_override(self, monkeypatch):
        from memoria.cache import create_cache
        monkeypatch.setenv("MEMORIA_CACHE_MAX_SIZE", "42")
        cache = create_cache()
        stats = cache.stats()
        assert stats["max_size"] == 42

    def test_redis_import_error(self, monkeypatch):
        """When redis package is not available, factory should raise ImportError."""
        from memoria.cache import create_cache
        # If redis isn't installed, this should fail gracefully
        try:
            import redis
            # redis IS installed — try connecting to a non-existent server
            with pytest.raises(ConnectionError):
                create_cache(backend="redis", redis_url="redis://localhost:59999/0")
        except ImportError:
            with pytest.raises(ImportError):
                create_cache(backend="redis")

    def test_ttl_env(self, monkeypatch):
        from memoria.cache import create_cache
        monkeypatch.setenv("MEMORIA_CACHE_TTL", "60")
        cache = create_cache()
        assert cache.stats()["default_ttl"] == 60


# ── RedisCache (conditional) ────────────────────────────────────────────

class TestRedisCache:
    """Tests for RedisCache — skipped if redis not installed or not running."""

    @pytest.fixture(autouse=True)
    def _skip_no_redis(self):
        try:
            import redis
            client = redis.Redis.from_url("redis://localhost:6379/0")
            client.ping()
        except Exception:
            pytest.skip("Redis not available")

    def _make(self, **kwargs):
        from memoria.cache.redis import RedisCache
        defaults = {"url": "redis://localhost:6379/0", "prefix": "test_memoria:"}
        defaults.update(kwargs)
        cache = RedisCache(**defaults)
        cache.clear()
        return cache

    def test_set_get(self):
        cache = self._make()
        cache.set("k1", [1.0, 2.0])
        assert cache.get("k1") == [1.0, 2.0]

    def test_get_miss(self):
        cache = self._make()
        assert cache.get("nonexistent") is None

    def test_delete(self):
        cache = self._make()
        cache.set("k1", "val")
        cache.delete("k1")
        assert cache.get("k1") is None

    def test_ttl_expiry(self):
        cache = self._make(default_ttl=1)
        cache.set("k", "val")
        assert cache.get("k") == "val"
        time.sleep(1.5)
        assert cache.get("k") is None

    def test_invalidate_pattern(self):
        cache = self._make()
        cache.set("embed:a", 1)
        cache.set("embed:b", 2)
        cache.set("recall:c", 3)
        count = cache.invalidate_pattern("embed:*")
        assert count == 2
        assert cache.get("embed:a") is None
        assert cache.get("recall:c") == 3

    def test_clear(self):
        cache = self._make()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") is None

    def test_stats(self):
        cache = self._make()
        cache.set("k", "v")
        cache.get("k")       # hit
        cache.get("miss")    # miss
        stats = cache.stats()
        assert stats["backend"] == "redis"
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_complex_values(self):
        cache = self._make()
        val = {"nested": [1, 2], "deep": {"a": True}}
        cache.set("complex", val)
        assert cache.get("complex") == val

    def test_close(self):
        cache = self._make()
        cache.close()


# ── CachedEmbedder with backend ─────────────────────────────────────────

class TestCachedEmbedderWithBackend:
    """Test the CachedEmbedder class with the new cache backend integration."""

    def _make_embedder(self, cache_backend=None):
        from memoria.vector.embeddings import CachedEmbedder, TFIDFEmbedder
        inner = TFIDFEmbedder(dimension=64)
        return CachedEmbedder(inner, cache_backend=cache_backend)

    def test_legacy_mode(self):
        """Without a backend, uses internal dict (backward compat)."""
        ce = self._make_embedder()
        v1 = ce.embed("hello world")
        v2 = ce.embed("hello world")
        assert v1 == v2
        assert len(v1) == 64

    def test_with_memory_backend(self):
        from memoria.cache.memory import MemoryCache
        cache = MemoryCache(max_size=100)
        ce = self._make_embedder(cache_backend=cache)
        v1 = ce.embed("test cache backend")
        v2 = ce.embed("test cache backend")
        assert v1 == v2
        assert cache.stats()["hits"] == 1

    def test_batch_with_backend(self):
        from memoria.cache.memory import MemoryCache
        cache = MemoryCache(max_size=100)
        ce = self._make_embedder(cache_backend=cache)
        texts = ["alpha", "beta", "gamma"]
        r1 = ce.embed_batch(texts)
        assert len(r1) == 3
        # Second call should hit cache
        r2 = ce.embed_batch(texts)
        assert r1 == r2
        assert cache.stats()["hits"] == 3

    def test_clear_cache_with_backend(self):
        from memoria.cache.memory import MemoryCache
        cache = MemoryCache()
        ce = self._make_embedder(cache_backend=cache)
        ce.embed("something")
        assert cache.stats()["size"] > 0
        ce.clear_cache()
        # After clear, embed:* keys should be gone
        assert cache.stats()["size"] == 0

    def test_cache_stats_legacy(self):
        ce = self._make_embedder()
        ce.embed("x")
        stats = ce.cache_stats()
        assert stats["backend"] == "legacy_dict"
        assert stats["size"] == 1

    def test_cache_stats_with_backend(self):
        from memoria.cache.memory import MemoryCache
        cache = MemoryCache()
        ce = self._make_embedder(cache_backend=cache)
        ce.embed("x")
        stats = ce.cache_stats()
        assert stats["backend"] == "memory"


# ── RecallCache with backend ────────────────────────────────────────────

class TestRecallCacheWithBackend:
    """Test the RecallCache with the new cache backend integration."""

    def _make_ranked_result(self, rid="test1", score=0.9):
        from memoria.recall.ranker import RankedResult
        return RankedResult(
            id=rid,
            content="test content",
            final_score=score,
            sources=["keyword"],
            strategy_scores={"keyword": 0.8},
            metadata={"tier": "core"},
        )

    def test_legacy_mode(self):
        from memoria.recall.pipeline import RecallCache
        rc = RecallCache(ttl_seconds=300)
        results = [self._make_ranked_result()]
        rc.put("q1", results)
        got = rc.get("q1")
        assert got is not None
        assert len(got) == 1
        assert got[0].id == "test1"

    def test_with_memory_backend(self):
        from memoria.cache.memory import MemoryCache
        from memoria.recall.pipeline import RecallCache
        cache = MemoryCache()
        rc = RecallCache(cache_backend=cache)
        results = [self._make_ranked_result()]
        rc.put("q1", results)
        got = rc.get("q1")
        assert got is not None
        assert got[0].id == "test1"
        assert got[0].final_score == 0.9

    def test_invalidate_with_backend(self):
        from memoria.cache.memory import MemoryCache
        from memoria.recall.pipeline import RecallCache
        cache = MemoryCache()
        rc = RecallCache(cache_backend=cache)
        rc.put("q1", [self._make_ranked_result()])
        rc.invalidate("q1")
        assert rc.get("q1") is None

    def test_invalidate_all_with_backend(self):
        from memoria.cache.memory import MemoryCache
        from memoria.recall.pipeline import RecallCache
        cache = MemoryCache()
        rc = RecallCache(cache_backend=cache)
        rc.put("q1", [self._make_ranked_result("a")])
        rc.put("q2", [self._make_ranked_result("b")])
        rc.invalidate()
        assert rc.get("q1") is None
        assert rc.get("q2") is None


# ── Memoria class integration ───────────────────────────────────────────

class TestMemoriaCacheIntegration:
    """Test Memoria.cache_* methods."""

    def _make_memoria(self):
        import tempfile

        from memoria import Memoria
        td = tempfile.mkdtemp()
        return Memoria(project_dir=td)

    def test_cache_stats(self):
        m = self._make_memoria()
        stats = m.cache_stats()
        assert "backend" in stats
        assert stats["backend"] == "memory"

    def test_cache_clear(self):
        m = self._make_memoria()
        result = m.cache_clear()
        assert result["cleared"] == "all"

    def test_cache_clear_pattern(self):
        m = self._make_memoria()
        result = m.cache_clear(pattern="embed:*")
        assert "cleared" in result

    def test_cache_warmup(self):
        m = self._make_memoria()
        result = m.cache_warmup(queries=["test query"])
        assert result["warmed"] == 1

    def test_cache_warmup_empty(self):
        m = self._make_memoria()
        result = m.cache_warmup()
        assert result["warmed"] == 0
