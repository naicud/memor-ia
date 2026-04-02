"""Content and metadata diffing between memory versions."""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Any

from .history import VersionEntry

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class DiffEntry:
    """A single field-level difference between two versions."""

    field: str
    old_value: Any
    new_value: Any


# ---------------------------------------------------------------------------
# MemoryDiff
# ---------------------------------------------------------------------------


class MemoryDiff:
    """Utility class for computing diffs between :class:`VersionEntry` objects."""

    @staticmethod
    def compute(old: VersionEntry, new: VersionEntry) -> list[DiffEntry]:
        """Compute field-level diffs between two version entries.

        Compares content, metadata keys (added / removed / changed), and
        the ``changed_by`` field.
        """
        diffs: list[DiffEntry] = []

        # Content
        if old.content != new.content:
            diffs.append(DiffEntry(field="content", old_value=old.content, new_value=new.content))

        # Metadata
        old_meta = old.metadata or {}
        new_meta = new.metadata or {}
        all_keys = sorted(set(old_meta) | set(new_meta))
        for key in all_keys:
            old_val = old_meta.get(key)
            new_val = new_meta.get(key)
            if old_val != new_val:
                if key not in old_meta:
                    diffs.append(DiffEntry(field=f"metadata.{key}", old_value=None, new_value=new_val))
                elif key not in new_meta:
                    diffs.append(DiffEntry(field=f"metadata.{key}", old_value=old_val, new_value=None))
                else:
                    diffs.append(DiffEntry(field=f"metadata.{key}", old_value=old_val, new_value=new_val))

        # changed_by
        if old.changed_by != new.changed_by:
            diffs.append(DiffEntry(field="changed_by", old_value=old.changed_by, new_value=new.changed_by))

        return diffs

    @staticmethod
    def content_diff(old_content: str, new_content: str) -> list[str]:
        """Return a unified-diff between *old_content* and *new_content*."""
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        return list(difflib.unified_diff(old_lines, new_lines, fromfile="old", tofile="new"))

    @staticmethod
    def summarize(diffs: list[DiffEntry]) -> str:
        """Human-readable one-line summary of a diff list."""
        if not diffs:
            return "No changes"

        parts: list[str] = []
        content_changed = any(d.field == "content" for d in diffs)
        meta_changes = [d for d in diffs if d.field.startswith("metadata.")]
        author_changed = any(d.field == "changed_by" for d in diffs)

        if content_changed:
            parts.append("Content changed")
        if meta_changes:
            n = len(meta_changes)
            parts.append(f"{n} metadata field{'s' if n != 1 else ''} updated")
        if author_changed:
            parts.append("Author changed")

        return ", ".join(parts)

    @staticmethod
    def has_content_change(diffs: list[DiffEntry]) -> bool:
        """Return ``True`` if any diff entry refers to content."""
        return any(d.field == "content" for d in diffs)

    @staticmethod
    def has_metadata_change(diffs: list[DiffEntry]) -> bool:
        """Return ``True`` if any diff entry refers to a metadata field."""
        return any(d.field.startswith("metadata.") for d in diffs)
