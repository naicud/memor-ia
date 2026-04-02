"""Namespace resolution and ancestor traversal utilities."""

from __future__ import annotations

from typing import Optional

from .hierarchy import MemoryNamespace

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_namespace(
    current: MemoryNamespace,
    relative_path: str,
) -> MemoryNamespace:
    """Resolve a relative path against *current*.

    Supported syntax:

    - ``"sub-agent"`` or ``"./sub-agent"`` — append to current path
    - ``".."`` — go up one level
    - ``"../sibling"`` — go up, then into sibling
    - ``"../../other"`` — go up two levels, then into other
    - Absolute paths (no leading dots) with ``/`` are treated as absolute
    """
    stripped = relative_path.strip("/")
    if not stripped:
        return current

    segments = stripped.split("/")

    # Handle "./" prefix — treat as relative child
    if segments[0] == ".":
        segments = segments[1:]
        if not segments:
            return current
        child_path = "/".join(filter(None, [current.path] + segments))
        return MemoryNamespace.from_path(child_path)

    # Handle ".." — walk up
    if segments[0] == "..":
        ns = current
        idx = 0
        while idx < len(segments) and segments[idx] == "..":
            parent = ns.parent()
            if parent is None:
                # Already at global, stay there
                break
            ns = parent
            idx += 1
        # Skip any remaining ".." that go beyond global
        while idx < len(segments) and segments[idx] == "..":
            idx += 1
        remaining = segments[idx:]
        if remaining:
            child_path = "/".join(filter(None, [ns.path] + remaining))
            return MemoryNamespace.from_path(child_path)
        return ns

    # No relative prefix — treat as child of current
    child_path = "/".join(filter(None, [current.path] + segments))
    return MemoryNamespace.from_path(child_path)


def walk_ancestors(ns: MemoryNamespace) -> list[MemoryNamespace]:
    """Return all ancestor namespaces from *ns* (inclusive) up to global.

    The list starts with *ns* itself and ends with the global namespace.
    """
    result: list[MemoryNamespace] = [ns]
    current = ns.parent()
    while current is not None:
        result.append(current)
        current = current.parent()
    return result


def find_shared_ancestor(
    ns1: MemoryNamespace,
    ns2: MemoryNamespace,
) -> Optional[MemoryNamespace]:
    """Find the lowest common ancestor of two namespaces.

    Returns ``None`` only when no common ancestor exists (which cannot
    happen — global is always a common ancestor).
    """
    ancestors1 = {a.path for a in walk_ancestors(ns1)}
    for ancestor in walk_ancestors(ns2):
        if ancestor.path in ancestors1:
            return ancestor
    return None


def scope_intersection(
    ns1: MemoryNamespace,
    ns2: MemoryNamespace,
) -> Optional[MemoryNamespace]:
    """Return the shared scope between two namespaces.

    If one contains the other, returns the more specific (deeper) one.
    Otherwise returns their lowest common ancestor.
    """
    if ns1.contains(ns2):
        return ns2
    if ns2.contains(ns1):
        return ns1
    return find_shared_ancestor(ns1, ns2)
