"""Memory enrichment — categorization, tagging, and entity linking."""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from .providers import ExtractionProvider, RegexExtractor


# ---------------------------------------------------------------------------
# Memory categories
# ---------------------------------------------------------------------------


class MemoryCategory(str, Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    EVENT = "event"
    RELATIONSHIP = "relationship"
    SKILL = "skill"
    OPINION = "opinion"


# ---------------------------------------------------------------------------
# Category keyword patterns
# ---------------------------------------------------------------------------

_CATEGORY_PATTERNS: list[tuple[MemoryCategory, re.Pattern[str]]] = [
    (
        MemoryCategory.PREFERENCE,
        re.compile(r"\b(?:prefer|like|love|use|choose)\b", re.I),
    ),
    (
        MemoryCategory.EVENT,
        re.compile(
            r"\b(?:yesterday|today|tomorrow|meeting|completed|started|finished|"
            r"\d{4}-\d{2}-\d{2})\b",
            re.I,
        ),
    ),
    (
        MemoryCategory.RELATIONSHIP,
        re.compile(
            r"\b(?:works\s+with|reports\s+to|team|collaborated|managed\s+by)\b",
            re.I,
        ),
    ),
    (
        MemoryCategory.SKILL,
        re.compile(
            r"\b(?:knows|expert\s+in|experienced\s+with|learned|proficient)\b",
            re.I,
        ),
    ),
    (
        MemoryCategory.OPINION,
        re.compile(r"\b(?:think|believe|feel|opinion)\b", re.I),
    ),
]


# ---------------------------------------------------------------------------
# MemoryEnricher
# ---------------------------------------------------------------------------


class MemoryEnricher:
    """Enrich memories with category, tags, and entity metadata."""

    def __init__(self, extractor: Optional[ExtractionProvider] = None):
        self._extractor = extractor or RegexExtractor()

    def categorize(self, content: str) -> MemoryCategory:
        """Auto-categorize a memory based on keyword patterns."""
        for category, pattern in _CATEGORY_PATTERNS:
            if pattern.search(content):
                return category
        return MemoryCategory.FACT

    def extract_tags(self, content: str) -> list[str]:
        """Extract relevant tags from content using entity extraction."""
        entities = self._extractor.extract_entities(content)
        tags: list[str] = []
        seen: set[str] = set()
        for entity in entities:
            tag = entity.name.lower()
            if tag not in seen:
                seen.add(tag)
                tags.append(tag)
        return tags

    def enrich(self, memory: dict) -> dict:
        """Add category, tags, entities, and entity types to memory metadata.

        Returns a copy of the memory dict with enriched metadata.
        """
        content = memory.get("content", "")
        entities = self._extractor.extract_entities(content)

        category = self.categorize(content)
        tags = self.extract_tags(content)
        entity_names = [e.name for e in entities]
        entity_types = {e.name: e.entity_type.value for e in entities}

        enriched = dict(memory)
        metadata = dict(enriched.get("metadata") or {})
        metadata["category"] = category.value
        metadata["tags"] = tags
        metadata["entities"] = entity_names
        metadata["entity_types"] = entity_types
        enriched["metadata"] = metadata

        return enriched

    def enrich_batch(self, memories: list[dict]) -> list[dict]:
        """Enrich multiple memories in batch. More efficient than calling enrich() in a loop."""
        return [self.enrich(m) for m in memories]
