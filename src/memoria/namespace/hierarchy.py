"""Hierarchical namespace model for multi-tenant memory scoping."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .store import SharedMemoryStore

# ---------------------------------------------------------------------------
# Namespace levels
# ---------------------------------------------------------------------------

_VALID_PART_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


class NamespaceLevel(IntEnum):
    """Hierarchical scope level (lower = broader)."""

    GLOBAL = 0
    ORG = 1
    TEAM = 2
    AGENT = 3
    SESSION = 4


# ---------------------------------------------------------------------------
# Level names for path ↔ level mapping
# ---------------------------------------------------------------------------

_LEVEL_NAMES = ["global", "org", "team", "agent", "session"]

# ---------------------------------------------------------------------------
# MemoryNamespace
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MemoryNamespace:
    """Immutable hierarchical namespace reference.

    Paths look like ``"global/acme-corp/frontend-team/agent-001/sess-abc"``.
    Each component maps to a :class:`NamespaceLevel`.
    """

    level: NamespaceLevel
    path: str
    parts: list = field(default_factory=list)

    # -- navigation --------------------------------------------------------

    def parent(self) -> Optional[MemoryNamespace]:
        """Walk up one level, or ``None`` if already at GLOBAL."""
        if self.level == NamespaceLevel.GLOBAL:
            return None
        parent_parts = self.parts[:-1]
        return MemoryNamespace.from_path("/".join(parent_parts)) if parent_parts else _GLOBAL_NS

    def children(self, store: SharedMemoryStore) -> list[MemoryNamespace]:
        """List sub-namespaces that exist in *store*."""
        prefix = f"{self.path}/" if self.path else ""
        result: list[MemoryNamespace] = []
        for ns_path in store.namespaces():
            if ns_path.startswith(prefix) and ns_path != self.path:
                # Only direct children (one additional level)
                remainder = ns_path[len(prefix):]
                if "/" not in remainder:
                    result.append(MemoryNamespace.from_path(ns_path))
        return result

    def contains(self, other: MemoryNamespace) -> bool:
        """Return ``True`` if *other* is a descendant of (or equal to) this namespace."""
        if self.path == other.path:
            return True
        if not self.path:
            # Global contains everything
            return True
        return other.path.startswith(self.path + "/")

    def ancestors(self) -> list[MemoryNamespace]:
        """All parent namespaces from immediate parent up to global."""
        result: list[MemoryNamespace] = []
        current = self.parent()
        while current is not None:
            result.append(current)
            current = current.parent()
        return result

    # -- constructors ------------------------------------------------------

    @classmethod
    def from_path(cls, path: str) -> MemoryNamespace:
        """Parse a slash-separated namespace path.

        Examples::

            MemoryNamespace.from_path("global")
            MemoryNamespace.from_path("acme-corp/frontend/agent-1")
        """
        normalized = path.strip("/").lower()
        if not normalized or normalized == "global":
            return _GLOBAL_NS

        parts_raw = normalized.split("/")
        # Strip leading "global" if present
        if parts_raw and parts_raw[0] == "global":
            parts_raw = parts_raw[1:]
        if not parts_raw:
            return _GLOBAL_NS

        for part in parts_raw:
            if not _VALID_PART_RE.match(part):
                raise ValueError(
                    f"Invalid namespace part {part!r}: "
                    "only alphanumeric, hyphens, and underscores allowed"
                )

        depth = min(len(parts_raw), len(NamespaceLevel) - 1)
        level = NamespaceLevel(depth)
        full_path = "/".join(parts_raw)
        return cls(level=level, path=full_path, parts=list(parts_raw))

    @classmethod
    def from_parts(
        cls,
        *,
        org: str | None = None,
        team: str | None = None,
        agent: str | None = None,
        session: str | None = None,
    ) -> MemoryNamespace:
        """Build a namespace from named components.

        Components must be supplied in order; you cannot set *agent* without
        *org* and *team*.
        """
        components: list[str] = []
        for value in (org, team, agent, session):
            if value is None:
                break
            components.append(value)
        if not components:
            return _GLOBAL_NS
        return cls.from_path("/".join(components))

    # -- dunder ------------------------------------------------------------

    def __str__(self) -> str:
        return self.path or "global"

    def __hash__(self) -> int:
        return hash(self.path)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MemoryNamespace):
            return NotImplemented
        return self.path == other.path


# Singleton global namespace
_GLOBAL_NS = MemoryNamespace(level=NamespaceLevel.GLOBAL, path="", parts=[])
