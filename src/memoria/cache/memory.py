"""In-memory LRU cache backend (default, zero-dependency)."""

from __future__ import annotations

import fnmatch
import threading
import time
from collections import OrderedDict
from typing import Any

from memoria.cache.backend import CacheBackend


class MemoryCache(CacheBackend):
    """Thread-safe in-memory LRU cache with optional TTL.

    Uses :class:`OrderedDict` for true LRU eviction — the most-recently
    accessed entry is always at the end, so eviction pops from the front.
    """

    def __init__(self, max_size: int = 1024, default_ttl: int | None = None):
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = threading.Lock()
        # value: (timestamp, ttl | None, payload)
        self._store: OrderedDict[str, tuple[float, int | None, Any]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    # -- public API --------------------------------------------------------

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            ts, ttl, value = entry
            if ttl is not None and (time.time() - ts) > ttl:
                del self._store[key]
                self._misses += 1
                return None
            # Move to end (most-recently used)
            self._store.move_to_end(key)
            self._hits += 1
            return value

    def set(self, key: str, value: Any, *, ttl: int | None = None) -> None:
        effective_ttl = ttl if ttl is not None else self._default_ttl
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (time.time(), effective_ttl, value)
            while len(self._store) > self._max_size:
                self._store.popitem(last=False)  # evict LRU

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def invalidate_pattern(self, pattern: str) -> int:
        with self._lock:
            to_delete = [k for k in self._store if fnmatch.fnmatch(k, pattern)]
            for k in to_delete:
                del self._store[k]
            return len(to_delete)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "backend": "memory",
                "size": len(self._store),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total else 0.0,
                "default_ttl": self._default_ttl,
            }
