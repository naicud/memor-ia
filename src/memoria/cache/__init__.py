"""MEMORIA — Pluggable cache layer with in-memory and Redis backends."""

from __future__ import annotations

from memoria.cache.backend import CacheBackend
from memoria.cache.factory import create_cache
from memoria.cache.memory import MemoryCache

__all__ = [
    "CacheBackend",
    "MemoryCache",
    "create_cache",
]
