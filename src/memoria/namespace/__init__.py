"""MEMORIA namespace — hierarchical namespace management and shared store."""

from __future__ import annotations

from .hierarchy import MemoryNamespace, NamespaceLevel
from .store import SharedMemoryStore
from .resolver import (
    find_shared_ancestor,
    resolve_namespace,
    scope_intersection,
    walk_ancestors,
)
from .scopes import ScopeFilter, normalize_path, validate_namespace_path, validate_part

__all__ = [
    # hierarchy
    "MemoryNamespace",
    "NamespaceLevel",
    # store
    "SharedMemoryStore",
    # resolver
    "find_shared_ancestor",
    "resolve_namespace",
    "scope_intersection",
    "walk_ancestors",
    # scopes
    "ScopeFilter",
    "normalize_path",
    "validate_namespace_path",
    "validate_part",
]
