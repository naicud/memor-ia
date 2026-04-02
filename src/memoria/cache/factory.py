"""Cache backend factory — reads config / env vars and returns the right backend."""

from __future__ import annotations

import os
from typing import Any

from memoria.cache.backend import CacheBackend
from memoria.cache.memory import MemoryCache


def create_cache(
    backend: str | None = None,
    *,
    redis_url: str | None = None,
    prefix: str | None = None,
    max_size: int | None = None,
    default_ttl: int | None = None,
    max_connections: int | None = None,
) -> CacheBackend:
    """Create a cache backend from explicit args or environment variables.

    Environment variables (lower priority than explicit args):
        ``MEMORIA_CACHE_BACKEND``  — ``memory`` (default) or ``redis``
        ``MEMORIA_REDIS_URL``      — Redis connection string
        ``MEMORIA_CACHE_PREFIX``   — Key prefix (default ``memoria:``)
        ``MEMORIA_CACHE_MAX_SIZE`` — Max entries for in-memory (default 1024)
        ``MEMORIA_CACHE_TTL``      — Default TTL in seconds

    Returns
    -------
    CacheBackend
        A ready-to-use cache instance.
    """
    chosen = backend or os.getenv("MEMORIA_CACHE_BACKEND", "memory")

    if chosen == "redis":
        from memoria.cache.redis import RedisCache

        return RedisCache(
            url=redis_url or os.getenv("MEMORIA_REDIS_URL", "redis://localhost:6379/0"),
            prefix=prefix or os.getenv("MEMORIA_CACHE_PREFIX", "memoria:"),
            default_ttl=_int_or(default_ttl, os.getenv("MEMORIA_CACHE_TTL"), 3600),
            max_connections=_int_or(max_connections, None, 10),
        )

    # Default: in-memory
    return MemoryCache(
        max_size=_int_or(max_size, os.getenv("MEMORIA_CACHE_MAX_SIZE"), 1024),
        default_ttl=_int_or(default_ttl, os.getenv("MEMORIA_CACHE_TTL"), None),
    )


def _int_or(explicit: Any, env: str | None, fallback: Any) -> Any:
    """Resolve an integer config value: explicit > env > fallback."""
    if explicit is not None:
        return int(explicit)
    if env is not None:
        try:
            return int(env)
        except (ValueError, TypeError):
            pass
    return fallback
