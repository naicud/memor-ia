"""Abstract cache backend interface for MEMORIA."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CacheBackend(ABC):
    """Abstract cache backend.

    All MEMORIA caches — embedding, recall, query — route through
    this interface so the underlying store (in-memory dict vs. Redis)
    can be swapped transparently.
    """

    @abstractmethod
    def get(self, key: str) -> Any | None:
        """Return the cached value for *key*, or ``None`` on miss."""

    @abstractmethod
    def set(self, key: str, value: Any, *, ttl: int | None = None) -> None:
        """Store *value* under *key* with an optional TTL in seconds."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove a single key."""

    @abstractmethod
    def invalidate_pattern(self, pattern: str) -> int:
        """Delete all keys matching *pattern* (glob-style). Return count."""

    @abstractmethod
    def clear(self) -> None:
        """Flush every entry."""

    @abstractmethod
    def stats(self) -> dict[str, Any]:
        """Return cache statistics (hits, misses, size, backend type)."""
