"""Scope validation and filtering utilities for namespace paths."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_VALID_PART_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def validate_part(part: str) -> bool:
    """Return ``True`` if *part* is a valid single namespace component."""
    return bool(part and _VALID_PART_RE.match(part))


def validate_namespace_path(path: str) -> bool:
    """Return ``True`` if *path* is a valid namespace path.

    An empty path (representing global) is valid.
    """
    normalized = path.strip("/").lower()
    if not normalized or normalized == "global":
        return True
    parts = normalized.split("/")
    # Strip leading "global"
    if parts[0] == "global":
        parts = parts[1:]
    return all(validate_part(p) for p in parts) if parts else True


def normalize_path(path: str) -> str:
    """Normalize a namespace path: strip slashes, lowercase, deduplicate.

    Returns an empty string for the global namespace.
    """
    stripped = path.strip("/").lower()
    if not stripped or stripped == "global":
        return ""
    parts = stripped.split("/")
    if parts and parts[0] == "global":
        parts = parts[1:]
    # Filter out empty segments from double slashes
    parts = [p for p in parts if p]
    return "/".join(parts)


# ---------------------------------------------------------------------------
# ScopeFilter
# ---------------------------------------------------------------------------


@dataclass
class ScopeFilter:
    """Filter that checks whether a namespace matches a whitelist of scopes."""

    namespaces: list[str] = field(default_factory=list)
    include_ancestors: bool = True
    include_descendants: bool = False

    def matches(self, namespace: str) -> bool:
        """Return ``True`` if *namespace* is allowed by this filter."""
        normalized = normalize_path(namespace)

        for allowed in self.namespaces:
            allowed_norm = normalize_path(allowed)

            # Exact match
            if normalized == allowed_norm:
                return True

            # Check if namespace is an ancestor of allowed
            if self.include_ancestors and allowed_norm:
                if allowed_norm.startswith(normalized + "/") or normalized == "":
                    return True

            # Check if namespace is a descendant of allowed
            if self.include_descendants and normalized:
                if normalized.startswith(allowed_norm + "/") or allowed_norm == "":
                    return True

        return False
