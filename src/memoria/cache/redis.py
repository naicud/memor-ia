"""Redis cache backend for multi-pod / shared-cache deployments."""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

from memoria.cache.backend import CacheBackend

logger = logging.getLogger(__name__)

try:
    import redis as _redis_lib

    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False
    _redis_lib = None  # type: ignore[assignment]


class RedisCache(CacheBackend):
    """Redis-backed cache with JSON serialization.

    Requires: ``pip install redis`` or ``pip install memoria[cache]``

    Parameters
    ----------
    url : str
        Redis connection URL (e.g. ``redis://localhost:6379/0``).
    prefix : str
        Key prefix for namespacing (default ``memoria:``).
    default_ttl : int | None
        Default TTL in seconds.  ``None`` means no expiry.
    max_connections : int
        Connection-pool size (default 10).
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        prefix: str = "memoria:",
        default_ttl: int | None = 3600,
        max_connections: int = 10,
    ):
        if not HAS_REDIS:
            raise ImportError(
                "redis package not installed. "
                "Install with: pip install redis  (or pip install memoria[cache])"
            )
        self._prefix = prefix
        self._default_ttl = default_ttl
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

        pool = _redis_lib.ConnectionPool.from_url(url, max_connections=max_connections)
        self._client: _redis_lib.Redis = _redis_lib.Redis(connection_pool=pool)
        # Verify connectivity on creation
        try:
            self._client.ping()
            logger.info("Redis cache connected: %s (prefix=%s)", url, prefix)
        except _redis_lib.ConnectionError as exc:
            raise ConnectionError(
                f"Cannot connect to Redis at {url}: {exc}"
            ) from exc

    # -- helpers -----------------------------------------------------------

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    @staticmethod
    def _serialize(value: Any) -> str:
        return json.dumps(value)

    @staticmethod
    def _deserialize(raw: bytes | str | None) -> Any:
        if raw is None:
            return None
        return json.loads(raw)

    # -- public API --------------------------------------------------------

    def get(self, key: str) -> Any | None:
        raw = self._client.get(self._key(key))
        if raw is None:
            with self._lock:
                self._misses += 1
            return None
        with self._lock:
            self._hits += 1
        return self._deserialize(raw)

    def set(self, key: str, value: Any, *, ttl: int | None = None) -> None:
        effective_ttl = ttl if ttl is not None else self._default_ttl
        serialized = self._serialize(value)
        if effective_ttl is not None:
            self._client.setex(self._key(key), effective_ttl, serialized)
        else:
            self._client.set(self._key(key), serialized)

    def delete(self, key: str) -> None:
        self._client.delete(self._key(key))

    def invalidate_pattern(self, pattern: str) -> int:
        full_pattern = self._key(pattern)
        count = 0
        cursor = 0
        while True:
            cursor, keys = self._client.scan(cursor=cursor, match=full_pattern, count=100)
            if keys:
                count += self._client.delete(*keys)
            if cursor == 0:
                break
        return count

    def clear(self) -> None:
        count = self.invalidate_pattern("*")
        with self._lock:
            self._hits = 0
            self._misses = 0
        logger.info("Redis cache cleared: %d keys deleted", count)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            base = {
                "backend": "redis",
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total else 0.0,
                "prefix": self._prefix,
                "default_ttl": self._default_ttl,
            }

        # Attempt to add server info
        try:
            info = self._client.info("keyspace")
            db_info = info.get("db0", {})
            base["keys"] = db_info.get("keys", 0) if isinstance(db_info, dict) else 0
        except Exception:
            base["keys"] = -1

        return base

    def close(self) -> None:
        """Close the Redis connection pool."""
        self._client.close()
