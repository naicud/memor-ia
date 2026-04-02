"""Entity extraction providers — regex, LLM, and hybrid strategies."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Callable, Optional

from memoria.graph.entities import (
    Entity,
    Relation,
    extract_entities as regex_extract_entities,
    extract_relations as regex_extract_relations,
)
from memoria.graph.schema import NodeType, RelationType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template for LLM-based extraction
# ---------------------------------------------------------------------------

_ENTITY_PROMPT = """\
Extract all entities from the following text. Return a JSON array of objects.
Each object must have:
- "name": entity name (string)
- "entity_type": one of {entity_types}
- "confidence": float between 0 and 1

Text:
\"\"\"
{text}
\"\"\"

Return ONLY valid JSON. No markdown, no explanation."""

_RELATION_PROMPT = """\
Given these entities: {entities}

Extract relationships from the following text. Return a JSON array of objects.
Each object must have:
- "source": entity name (string)
- "target": entity name (string)
- "relation_type": one of {relation_types}
- "confidence": float between 0 and 1

Text:
\"\"\"
{text}
\"\"\"

Return ONLY valid JSON. No markdown, no explanation."""

# ---------------------------------------------------------------------------
# Valid enum values for parsing
# ---------------------------------------------------------------------------

_VALID_NODE_TYPES: dict[str, NodeType] = {nt.value.lower(): nt for nt in NodeType}
_VALID_RELATION_TYPES: dict[str, RelationType] = {
    rt.value.lower(): rt for rt in RelationType
}


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class ExtractionProvider(ABC):
    """Abstract base for entity extraction providers."""

    @abstractmethod
    def extract_entities(self, text: str) -> list[Entity]:
        """Extract entities from text."""
        ...

    @abstractmethod
    def extract_relations(self, text: str, entities: list[Entity]) -> list[Relation]:
        """Extract relations between entities."""
        ...


# ---------------------------------------------------------------------------
# Regex-based extractor (wraps existing functions)
# ---------------------------------------------------------------------------


class RegexExtractor(ExtractionProvider):
    """Wraps existing regex-based extraction from memoria.graph.entities."""

    def extract_entities(self, text: str) -> list[Entity]:
        return regex_extract_entities(text)

    def extract_relations(self, text: str, entities: list[Entity]) -> list[Relation]:
        return regex_extract_relations(text, entities)


# ---------------------------------------------------------------------------
# LLM-powered extractor
# ---------------------------------------------------------------------------


class LLMExtractor(ExtractionProvider):
    """LLM-powered extraction using pluggable providers.

    Supports any callable that takes a prompt and returns text.
    Default: no LLM (falls back to regex).
    """

    def __init__(
        self,
        llm_fn: Optional[Callable[[str], str]] = None,
        model_name: Optional[str] = None,
    ):
        self._llm_fn = llm_fn
        self._model_name = model_name
        self._fallback = RegexExtractor()

    def extract_entities(self, text: str) -> list[Entity]:
        if not self._llm_fn:
            return self._fallback.extract_entities(text)

        entity_types = ", ".join(nt.value for nt in NodeType)
        prompt = _ENTITY_PROMPT.format(text=text, entity_types=entity_types)

        try:
            raw = self._llm_fn(prompt)
            parsed = _parse_json_array(raw)
            return _json_to_entities(parsed, text)
        except Exception:
            logger.debug("LLM entity extraction failed, falling back to regex")
            return self._fallback.extract_entities(text)

    def extract_relations(
        self, text: str, entities: list[Entity]
    ) -> list[Relation]:
        if not self._llm_fn:
            return self._fallback.extract_relations(text, entities)

        entity_names = [e.name for e in entities]
        relation_types = ", ".join(rt.value for rt in RelationType)
        prompt = _RELATION_PROMPT.format(
            text=text,
            entities=json.dumps(entity_names),
            relation_types=relation_types,
        )

        try:
            raw = self._llm_fn(prompt)
            parsed = _parse_json_array(raw)
            return _json_to_relations(parsed, entities)
        except Exception:
            logger.debug("LLM relation extraction failed, falling back to regex")
            return self._fallback.extract_relations(text, entities)


# ---------------------------------------------------------------------------
# Hybrid extractor
# ---------------------------------------------------------------------------


class HybridExtractor(ExtractionProvider):
    """Combines regex and LLM extraction.

    Uses regex first for high-confidence patterns, then LLM for complex cases.
    Merges and deduplicates results.
    """

    def __init__(self, llm_fn: Optional[Callable[[str], str]] = None):
        self._regex = RegexExtractor()
        self._llm = LLMExtractor(llm_fn) if llm_fn else None

    def extract_entities(self, text: str) -> list[Entity]:
        regex_entities = self._regex.extract_entities(text)
        if not self._llm:
            return regex_entities

        llm_entities = self._llm.extract_entities(text)
        return _merge_entities(regex_entities, llm_entities)

    def extract_relations(
        self, text: str, entities: list[Entity]
    ) -> list[Relation]:
        regex_relations = self._regex.extract_relations(text, entities)
        if not self._llm:
            return regex_relations

        llm_relations = self._llm.extract_relations(text, entities)
        return _merge_relations(regex_relations, llm_relations)


# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------


def _parse_json_array(raw: str) -> list[dict]:
    """Parse a JSON array from an LLM response, tolerating markdown fences."""
    text = raw.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove first and last lines (the fences)
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines)
    return json.loads(text)


def _json_to_entities(items: list[dict], source_text: str) -> list[Entity]:
    """Convert parsed JSON dicts into Entity objects."""
    entities: list[Entity] = []
    for item in items:
        name = item.get("name", "").strip()
        if not name:
            continue
        raw_type = str(item.get("entity_type", "")).lower()
        node_type = _VALID_NODE_TYPES.get(raw_type, NodeType.CONCEPT)
        confidence = float(item.get("confidence", 0.7))
        confidence = max(0.0, min(1.0, confidence))
        entities.append(
            Entity(
                name=name,
                entity_type=node_type,
                confidence=confidence,
                source_text=source_text,
            )
        )
    return entities


def _json_to_relations(
    items: list[dict], entities: list[Entity]
) -> list[Relation]:
    """Convert parsed JSON dicts into Relation objects."""
    entity_map: dict[str, Entity] = {e.name.lower(): e for e in entities}
    relations: list[Relation] = []
    for item in items:
        src_name = str(item.get("source", "")).strip().lower()
        tgt_name = str(item.get("target", "")).strip().lower()
        src = entity_map.get(src_name)
        tgt = entity_map.get(tgt_name)
        if not src or not tgt:
            continue
        raw_type = str(item.get("relation_type", "")).lower()
        rel_type = _VALID_RELATION_TYPES.get(raw_type, RelationType.RELATED_TO)
        confidence = float(item.get("confidence", 0.7))
        confidence = max(0.0, min(1.0, confidence))
        relations.append(
            Relation(source=src, target=tgt, relation_type=rel_type, confidence=confidence)
        )
    return relations


# ---------------------------------------------------------------------------
# Merge / dedup helpers
# ---------------------------------------------------------------------------


def _merge_entities(
    primary: list[Entity], secondary: list[Entity]
) -> list[Entity]:
    """Merge two entity lists, deduplicating by name (keep higher confidence)."""
    by_name: dict[str, Entity] = {}
    for entity in primary:
        key = entity.name.lower()
        by_name[key] = entity
    for entity in secondary:
        key = entity.name.lower()
        existing = by_name.get(key)
        if existing is None or entity.confidence > existing.confidence:
            by_name[key] = entity
    return list(by_name.values())


def _merge_relations(
    primary: list[Relation], secondary: list[Relation]
) -> list[Relation]:
    """Merge two relation lists, deduplicating by (source, target, type)."""
    seen: dict[tuple[str, str, str], Relation] = {}
    for rel in primary:
        key = (rel.source.name.lower(), rel.target.name.lower(), rel.relation_type.value)
        seen[key] = rel
    for rel in secondary:
        key = (rel.source.name.lower(), rel.target.name.lower(), rel.relation_type.value)
        existing = seen.get(key)
        if existing is None or rel.confidence > existing.confidence:
            seen[key] = rel
    return list(seen.values())
