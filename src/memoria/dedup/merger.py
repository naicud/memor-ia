"""Memory merger — combine duplicate memories preserving best metadata."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

log = logging.getLogger(__name__)


@dataclass
class MergeResult:
    """Outcome of merging two memory entries."""

    merged_content: str
    merged_metadata: dict = field(default_factory=dict)
    source_ids: list[str] = field(default_factory=list)
    strategy: str = "longer"


class MemoryMerger:
    """Merge near-duplicate memories into one consolidated entry.

    Strategies:
    - ``longer``  — keep the longer / more detailed content (default).
    - ``combine`` — concatenate both (deduped sentences).
    - ``newer``   — keep the more recently created content.
    """

    STRATEGIES = {"longer", "combine", "newer"}

    def __init__(self, strategy: str = "longer") -> None:
        if strategy not in self.STRATEGIES:
            raise ValueError(f"Unknown merge strategy: {strategy!r}. Choose from {self.STRATEGIES}")
        self._strategy = strategy

    @property
    def strategy(self) -> str:
        return self._strategy

    def merge(
        self,
        existing_id: str,
        existing_content: str,
        existing_metadata: dict,
        new_content: str,
        new_metadata: dict | None = None,
    ) -> MergeResult:
        """Merge *new_content* into the *existing* memory.

        Returns a :class:`MergeResult` with the consolidated content and
        metadata ready to be written back.
        """
        new_metadata = new_metadata or {}

        # Pick content
        if self._strategy == "longer":
            merged_content = self._pick_longer(existing_content, new_content)
        elif self._strategy == "combine":
            merged_content = self._combine(existing_content, new_content)
        elif self._strategy == "newer":
            merged_content = new_content
        else:
            merged_content = existing_content

        # Merge metadata — new values override existing, but preserve keys
        merged_meta = {**existing_metadata, **new_metadata}
        merged_meta["merged_at"] = datetime.now(timezone.utc).isoformat()
        merged_meta["merge_strategy"] = self._strategy

        return MergeResult(
            merged_content=merged_content,
            merged_metadata=merged_meta,
            source_ids=[existing_id, "new"],
            strategy=self._strategy,
        )

    @staticmethod
    def _pick_longer(a: str, b: str) -> str:
        return a if len(a) >= len(b) else b

    @staticmethod
    def _combine(a: str, b: str) -> str:
        """Concatenate, deduplicating exact sentence matches."""
        sentences_a = {s.strip() for s in a.split(".") if s.strip()}
        sentences_b = [s.strip() for s in b.split(".") if s.strip()]
        unique_from_b = [s for s in sentences_b if s not in sentences_a]
        if unique_from_b:
            return a.rstrip(".") + ". " + ". ".join(unique_from_b) + "."
        return a
