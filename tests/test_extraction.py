"""Comprehensive tests for the memoria.extraction module."""

from __future__ import annotations

import json

import pytest

from memoria.graph.entities import Entity, Relation
from memoria.graph.schema import NodeType, RelationType

from memoria.extraction.providers import (
    ExtractionProvider,
    RegexExtractor,
    LLMExtractor,
    HybridExtractor,
)
from memoria.extraction.dedup import MemoryDeduplicator, jaccard_similarity
from memoria.extraction.conflicts import (
    ConflictType,
    Conflict,
    ResolutionStrategy,
    ConflictDetector,
)
from memoria.extraction.enricher import MemoryCategory, MemoryEnricher


# ===================================================================
# TestRegexExtractor
# ===================================================================


class TestRegexExtractor:
    """Verify the regex-based extraction wrapper."""

    def test_extract_entities_person(self):
        ext = RegexExtractor()
        entities = ext.extract_entities("John Smith works on the project")
        names = [e.name for e in entities]
        assert "John Smith" in names

    def test_extract_entities_tool(self):
        ext = RegexExtractor()
        entities = ext.extract_entities("We use docker and pytest for CI")
        names = [e.name.lower() for e in entities]
        assert "docker" in names
        assert "pytest" in names

    def test_extract_entities_concept(self):
        ext = RegexExtractor()
        entities = ext.extract_entities("We practice TDD with python")
        names = [e.name.lower() for e in entities]
        assert "tdd" in names
        assert "python" in names

    def test_extract_entities_empty_text(self):
        ext = RegexExtractor()
        assert ext.extract_entities("") == []
        assert ext.extract_entities("   ") == []

    def test_extract_entities_path(self):
        ext = RegexExtractor()
        entities = ext.extract_entities("Check the file at src/memoria/graph/entities.py")
        types = [e.entity_type for e in entities]
        assert NodeType.PROJECT in types

    def test_extract_entities_preference(self):
        ext = RegexExtractor()
        entities = ext.extract_entities("I prefer vim over emacs")
        types = [e.entity_type for e in entities]
        assert NodeType.PREFERENCE in types or NodeType.TOOL in types

    def test_extract_relations_basic(self):
        ext = RegexExtractor()
        text = "Alice uses docker"
        entities = ext.extract_entities(text)
        # Ensure we have both entities for the relation check
        relations = ext.extract_relations(text, entities)
        # Relations depend on both entities being found; just verify no crash
        assert isinstance(relations, list)

    def test_extract_relations_empty(self):
        ext = RegexExtractor()
        assert ext.extract_relations("", []) == []

    def test_implements_provider_interface(self):
        ext = RegexExtractor()
        assert isinstance(ext, ExtractionProvider)


# ===================================================================
# TestLLMExtractor
# ===================================================================


class TestLLMExtractor:
    """Test LLM-powered extraction with mock llm_fn."""

    def _mock_llm_entities(self, prompt: str) -> str:
        """Return a valid JSON entity response."""
        return json.dumps([
            {"name": "Alice", "entity_type": "Person", "confidence": 0.95},
            {"name": "Python", "entity_type": "Concept", "confidence": 0.9},
        ])

    def _mock_llm_relations(self, prompt: str) -> str:
        """Return valid JSON relations when prompted."""
        if "relationships" in prompt.lower() or "relationship" in prompt.lower():
            return json.dumps([
                {
                    "source": "Alice",
                    "target": "Python",
                    "relation_type": "USES",
                    "confidence": 0.85,
                }
            ])
        return self._mock_llm_entities(prompt)

    def test_extract_entities_with_llm(self):
        ext = LLMExtractor(llm_fn=self._mock_llm_entities)
        entities = ext.extract_entities("Alice uses Python daily")
        names = [e.name for e in entities]
        assert "Alice" in names
        assert "Python" in names

    def test_entity_types_mapped_correctly(self):
        ext = LLMExtractor(llm_fn=self._mock_llm_entities)
        entities = ext.extract_entities("test")
        type_map = {e.name: e.entity_type for e in entities}
        assert type_map["Alice"] == NodeType.PERSON
        assert type_map["Python"] == NodeType.CONCEPT

    def test_confidence_values(self):
        ext = LLMExtractor(llm_fn=self._mock_llm_entities)
        entities = ext.extract_entities("test")
        for e in entities:
            assert 0.0 <= e.confidence <= 1.0

    def test_fallback_when_no_llm(self):
        ext = LLMExtractor(llm_fn=None)
        entities = ext.extract_entities("We use docker for deployment")
        # Should fall back to regex — docker should be found
        names = [e.name.lower() for e in entities]
        assert "docker" in names

    def test_fallback_on_invalid_json(self):
        def bad_llm(prompt: str) -> str:
            return "This is not JSON at all"

        ext = LLMExtractor(llm_fn=bad_llm)
        entities = ext.extract_entities("We use docker for deployment")
        # Should fall back to regex
        names = [e.name.lower() for e in entities]
        assert "docker" in names

    def test_fallback_on_exception(self):
        def exploding_llm(prompt: str) -> str:
            raise RuntimeError("LLM timeout")

        ext = LLMExtractor(llm_fn=exploding_llm)
        entities = ext.extract_entities("We use docker")
        names = [e.name.lower() for e in entities]
        assert "docker" in names

    def test_extract_relations_with_llm(self):
        ext = LLMExtractor(llm_fn=self._mock_llm_relations)
        entities = [
            Entity("Alice", NodeType.PERSON, 0.95),
            Entity("Python", NodeType.CONCEPT, 0.9),
        ]
        relations = ext.extract_relations("Alice uses Python", entities)
        assert len(relations) >= 1
        assert relations[0].relation_type == RelationType.USES

    def test_relations_fallback_no_llm(self):
        ext = LLMExtractor(llm_fn=None)
        entities = ext.extract_entities("Alice uses docker")
        relations = ext.extract_relations("Alice uses docker", entities)
        assert isinstance(relations, list)

    def test_markdown_fence_stripping(self):
        def fenced_llm(prompt: str) -> str:
            return '```json\n[{"name": "Bob", "entity_type": "Person", "confidence": 0.8}]\n```'

        ext = LLMExtractor(llm_fn=fenced_llm)
        entities = ext.extract_entities("Bob said hello")
        assert any(e.name == "Bob" for e in entities)

    def test_unknown_entity_type_defaults_to_concept(self):
        def llm_with_unknown_type(prompt: str) -> str:
            return json.dumps([
                {"name": "Widget", "entity_type": "Unknown", "confidence": 0.7}
            ])

        ext = LLMExtractor(llm_fn=llm_with_unknown_type)
        entities = ext.extract_entities("test")
        assert entities[0].entity_type == NodeType.CONCEPT

    def test_model_name_stored(self):
        ext = LLMExtractor(llm_fn=None, model_name="gpt-4")
        assert ext._model_name == "gpt-4"


# ===================================================================
# TestHybridExtractor
# ===================================================================


class TestHybridExtractor:
    """Test hybrid regex+LLM extraction with merge logic."""

    def _mock_llm(self, prompt: str) -> str:
        return json.dumps([
            {"name": "FastAPI", "entity_type": "Tool", "confidence": 0.95},
            {"name": "docker", "entity_type": "Tool", "confidence": 0.99},
        ])

    def test_regex_only_when_no_llm(self):
        ext = HybridExtractor(llm_fn=None)
        entities = ext.extract_entities("We use docker")
        names = [e.name.lower() for e in entities]
        assert "docker" in names

    def test_merge_regex_and_llm(self):
        ext = HybridExtractor(llm_fn=self._mock_llm)
        entities = ext.extract_entities("We use docker and FastAPI")
        names = [e.name.lower() for e in entities]
        assert "docker" in names
        assert "fastapi" in names

    def test_dedup_keeps_higher_confidence(self):
        ext = HybridExtractor(llm_fn=self._mock_llm)
        entities = ext.extract_entities("We use docker")
        docker_entities = [e for e in entities if e.name.lower() == "docker"]
        assert len(docker_entities) == 1
        # LLM returned 0.99, regex returns 0.9 — should keep 0.99
        assert docker_entities[0].confidence == 0.99

    def test_relations_merge(self):
        ext = HybridExtractor(llm_fn=None)
        text = "Alice uses docker"
        entities = ext.extract_entities(text)
        relations = ext.extract_relations(text, entities)
        assert isinstance(relations, list)

    def test_implements_provider_interface(self):
        ext = HybridExtractor()
        assert isinstance(ext, ExtractionProvider)


# ===================================================================
# TestMemoryDeduplicator
# ===================================================================


class TestMemoryDeduplicator:
    """Test memory deduplication."""

    def test_identical_texts_are_duplicates(self):
        dedup = MemoryDeduplicator()
        assert dedup.is_duplicate("hello world", "hello world") is True

    def test_different_texts_not_duplicates(self):
        dedup = MemoryDeduplicator()
        assert dedup.is_duplicate("hello world", "completely different text") is False

    def test_similar_texts_threshold(self):
        dedup = MemoryDeduplicator(similarity_threshold=0.5)
        # Shares many words
        assert dedup.is_duplicate(
            "the user prefers dark mode for coding",
            "the user prefers dark mode for editing",
        ) is True

    def test_jaccard_similarity_identical(self):
        assert jaccard_similarity("a b c", "a b c") == 1.0

    def test_jaccard_similarity_disjoint(self):
        assert jaccard_similarity("a b c", "d e f") == 0.0

    def test_jaccard_similarity_empty(self):
        assert jaccard_similarity("", "") == 1.0
        assert jaccard_similarity("hello", "") == 0.0

    def test_find_duplicates(self):
        dedup = MemoryDeduplicator(similarity_threshold=0.8)
        memories = [
            {"id": "m1", "content": "user prefers dark mode in the editor"},
            {"id": "m2", "content": "user prefers dark mode in the editor always"},
            {"id": "m3", "content": "the weather is sunny today"},
        ]
        dups = dedup.find_duplicates(memories)
        # m1 and m2 should be duplicates, m3 is unrelated
        dup_pairs = [(d[0], d[1]) for d in dups]
        assert ("m1", "m2") in dup_pairs
        assert all("m3" not in pair for pair in dup_pairs)

    def test_merge_memories_keeps_longer_content(self):
        dedup = MemoryDeduplicator()
        m1 = {"id": "m1", "content": "short"}
        m2 = {"id": "m2", "content": "this is a much longer content piece"}
        merged = dedup.merge_memories(m1, m2)
        assert merged["content"] == "this is a much longer content piece"

    def test_merge_memories_combines_metadata(self):
        dedup = MemoryDeduplicator()
        m1 = {"id": "m1", "content": "hello", "metadata": {"tag": "work"}}
        m2 = {"id": "m2", "content": "hello world", "metadata": {"source": "chat"}}
        merged = dedup.merge_memories(m1, m2)
        assert merged["metadata"]["source"] == "chat"
        assert merged["metadata"]["tag"] == "work"

    def test_merge_keeps_earlier_timestamp(self):
        dedup = MemoryDeduplicator()
        m1 = {"id": "m1", "content": "hi", "created_at": "2024-01-01"}
        m2 = {"id": "m2", "content": "hi there friend", "created_at": "2024-06-01"}
        merged = dedup.merge_memories(m1, m2)
        assert merged["created_at"] == "2024-01-01"

    def test_deduplicate_removes_duplicates(self):
        dedup = MemoryDeduplicator(similarity_threshold=0.8)
        memories = [
            {"id": "m1", "content": "user likes dark mode in the editor"},
            {"id": "m2", "content": "user likes dark mode in the editor settings"},
            {"id": "m3", "content": "the weather is sunny"},
        ]
        result = dedup.deduplicate(memories)
        assert len(result) == 2

    def test_deduplicate_empty_list(self):
        dedup = MemoryDeduplicator()
        assert dedup.deduplicate([]) == []

    def test_deduplicate_no_duplicates(self):
        dedup = MemoryDeduplicator()
        memories = [
            {"id": "m1", "content": "alpha bravo charlie"},
            {"id": "m2", "content": "delta echo foxtrot"},
        ]
        result = dedup.deduplicate(memories)
        assert len(result) == 2


# ===================================================================
# TestConflictDetector
# ===================================================================


class TestConflictDetector:
    """Test conflict detection and resolution."""

    def test_detect_contradiction(self):
        detector = ConflictDetector()
        memories = [
            {"id": "m1", "content": "Alice likes python"},
            {"id": "m2", "content": "Alice hates python"},
        ]
        conflicts = detector.detect_conflicts(memories)
        contradictions = [c for c in conflicts if c.conflict_type == ConflictType.CONTRADICTION]
        assert len(contradictions) >= 1
        assert contradictions[0].confidence > 0

    def test_detect_contradiction_prefers_vs_avoids(self):
        detector = ConflictDetector()
        memories = [
            {"id": "m1", "content": "Bob prefers tabs"},
            {"id": "m2", "content": "Bob avoids tabs"},
        ]
        conflicts = detector.detect_conflicts(memories)
        contradictions = [c for c in conflicts if c.conflict_type == ConflictType.CONTRADICTION]
        assert len(contradictions) >= 1

    def test_no_contradiction_same_polarity(self):
        detector = ConflictDetector()
        memories = [
            {"id": "m1", "content": "Alice likes python"},
            {"id": "m2", "content": "Alice loves python"},
        ]
        conflicts = detector.detect_conflicts(memories)
        contradictions = [c for c in conflicts if c.conflict_type == ConflictType.CONTRADICTION]
        assert len(contradictions) == 0

    def test_detect_redundant(self):
        detector = ConflictDetector()
        memories = [
            {"id": "m1", "content": "user prefers dark mode in the editor for coding"},
            {"id": "m2", "content": "user prefers dark mode in the editor for coding work"},
        ]
        conflicts = detector.detect_conflicts(memories)
        redundant = [c for c in conflicts if c.conflict_type == ConflictType.REDUNDANT]
        assert len(redundant) >= 1

    def test_detect_outdated(self):
        detector = ConflictDetector()
        memories = [
            {"id": "m1", "content": "the project uses react version 17",
             "created_at": "2023-01-01"},
            {"id": "m2", "content": "the project uses react version 18",
             "created_at": "2024-01-01"},
        ]
        conflicts = detector.detect_conflicts(memories)
        outdated = [c for c in conflicts if c.conflict_type == ConflictType.OUTDATED]
        assert len(outdated) >= 1

    def test_no_outdated_without_timestamps(self):
        detector = ConflictDetector()
        memories = [
            {"id": "m1", "content": "the project uses react version 17"},
            {"id": "m2", "content": "the project uses react version 18"},
        ]
        conflicts = detector.detect_conflicts(memories)
        outdated = [c for c in conflicts if c.conflict_type == ConflictType.OUTDATED]
        assert len(outdated) == 0

    def test_no_conflicts_unrelated(self):
        detector = ConflictDetector()
        memories = [
            {"id": "m1", "content": "Alice works on frontend development"},
            {"id": "m2", "content": "The weather is nice today in Barcelona"},
        ]
        conflicts = detector.detect_conflicts(memories)
        assert len(conflicts) == 0

    def test_resolve_latest_wins(self):
        detector = ConflictDetector()
        conflict = Conflict("m1", "m2", ConflictType.OUTDATED, 0.8, "test")
        memories = {
            "m1": {"id": "m1", "content": "old", "created_at": "2023-01-01"},
            "m2": {"id": "m2", "content": "new", "created_at": "2024-01-01"},
        }
        winner = detector.resolve(conflict, ResolutionStrategy.LATEST_WINS, memories)
        assert winner["content"] == "new"

    def test_resolve_confidence_weighted(self):
        detector = ConflictDetector()
        conflict = Conflict("m1", "m2", ConflictType.CONTRADICTION, 0.8, "test")
        memories = {
            "m1": {"id": "m1", "content": "a", "metadata": {"confidence": 0.9}},
            "m2": {"id": "m2", "content": "b", "metadata": {"confidence": 0.3}},
        }
        winner = detector.resolve(
            conflict, ResolutionStrategy.CONFIDENCE_WEIGHTED, memories
        )
        assert winner["content"] == "a"

    def test_resolve_merge(self):
        detector = ConflictDetector()
        conflict = Conflict("m1", "m2", ConflictType.REDUNDANT, 0.95, "test")
        memories = {
            "m1": {"id": "m1", "content": "short"},
            "m2": {"id": "m2", "content": "a longer piece of content"},
        }
        winner = detector.resolve(conflict, ResolutionStrategy.MERGE, memories)
        assert winner["content"] == "a longer piece of content"

    def test_resolve_manual(self):
        detector = ConflictDetector()
        conflict = Conflict("m1", "m2", ConflictType.CONTRADICTION, 0.8, "test")
        memories = {
            "m1": {"id": "m1", "content": "alpha"},
            "m2": {"id": "m2", "content": "beta"},
        }
        result = detector.resolve(conflict, ResolutionStrategy.MANUAL, memories)
        assert result["metadata"]["needs_review"] is True
        assert result["metadata"]["conflict_with"] == "m2"

    def test_conflict_type_enum_values(self):
        assert ConflictType.CONTRADICTION.value == "contradiction"
        assert ConflictType.OUTDATED.value == "outdated"
        assert ConflictType.REDUNDANT.value == "redundant"

    def test_resolution_strategy_enum_values(self):
        assert ResolutionStrategy.LATEST_WINS.value == "latest_wins"
        assert ResolutionStrategy.CONFIDENCE_WEIGHTED.value == "confidence_weighted"
        assert ResolutionStrategy.MANUAL.value == "manual"
        assert ResolutionStrategy.MERGE.value == "merge"


# ===================================================================
# TestMemoryEnricher
# ===================================================================


class TestMemoryEnricher:
    """Test memory enrichment."""

    def test_categorize_preference(self):
        enricher = MemoryEnricher()
        assert enricher.categorize("I prefer dark mode") == MemoryCategory.PREFERENCE

    def test_categorize_event(self):
        enricher = MemoryEnricher()
        assert enricher.categorize("Had a meeting yesterday") == MemoryCategory.EVENT

    def test_categorize_relationship(self):
        enricher = MemoryEnricher()
        assert enricher.categorize("Alice works with Bob on the team") == MemoryCategory.RELATIONSHIP

    def test_categorize_skill(self):
        enricher = MemoryEnricher()
        assert enricher.categorize("She is expert in machine learning") == MemoryCategory.SKILL

    def test_categorize_opinion(self):
        enricher = MemoryEnricher()
        assert enricher.categorize("I think this approach is better") == MemoryCategory.OPINION

    def test_categorize_fact_default(self):
        enricher = MemoryEnricher()
        assert enricher.categorize("The sky is blue") == MemoryCategory.FACT

    def test_extract_tags(self):
        enricher = MemoryEnricher()
        tags = enricher.extract_tags("We use docker and pytest for the project")
        assert "docker" in tags
        assert "pytest" in tags

    def test_extract_tags_empty(self):
        enricher = MemoryEnricher()
        tags = enricher.extract_tags("")
        assert tags == []

    def test_extract_tags_no_duplicates(self):
        enricher = MemoryEnricher()
        tags = enricher.extract_tags("docker docker docker")
        assert tags.count("docker") == 1

    def test_enrich_adds_category(self):
        enricher = MemoryEnricher()
        memory = {"id": "m1", "content": "I prefer vim for editing"}
        enriched = enricher.enrich(memory)
        assert enriched["metadata"]["category"] == MemoryCategory.PREFERENCE.value

    def test_enrich_adds_tags(self):
        enricher = MemoryEnricher()
        memory = {"id": "m1", "content": "We use docker and pytest"}
        enriched = enricher.enrich(memory)
        assert "docker" in enriched["metadata"]["tags"]

    def test_enrich_adds_entities(self):
        enricher = MemoryEnricher()
        memory = {"id": "m1", "content": "John Smith uses docker"}
        enriched = enricher.enrich(memory)
        assert len(enriched["metadata"]["entities"]) > 0

    def test_enrich_adds_entity_types(self):
        enricher = MemoryEnricher()
        memory = {"id": "m1", "content": "John Smith uses docker"}
        enriched = enricher.enrich(memory)
        entity_types = enriched["metadata"]["entity_types"]
        assert isinstance(entity_types, dict)
        assert len(entity_types) > 0

    def test_enrich_preserves_existing_metadata(self):
        enricher = MemoryEnricher()
        memory = {"id": "m1", "content": "hello", "metadata": {"source": "chat"}}
        enriched = enricher.enrich(memory)
        assert enriched["metadata"]["source"] == "chat"

    def test_enrich_does_not_mutate_original(self):
        enricher = MemoryEnricher()
        memory = {"id": "m1", "content": "I prefer dark mode"}
        enricher.enrich(memory)
        assert "metadata" not in memory or "category" not in memory.get("metadata", {})

    def test_enrich_with_custom_extractor(self):
        """Verify that a custom ExtractionProvider can be injected."""

        class StubExtractor(ExtractionProvider):
            def extract_entities(self, text):
                return [Entity("Stub", NodeType.CONCEPT, 1.0, text)]

            def extract_relations(self, text, entities):
                return []

        enricher = MemoryEnricher(extractor=StubExtractor())
        enriched = enricher.enrich({"id": "m1", "content": "anything"})
        assert "Stub" in enriched["metadata"]["entities"]

    def test_memory_category_enum_values(self):
        assert MemoryCategory.FACT.value == "fact"
        assert MemoryCategory.PREFERENCE.value == "preference"
        assert MemoryCategory.EVENT.value == "event"
        assert MemoryCategory.RELATIONSHIP.value == "relationship"
        assert MemoryCategory.SKILL.value == "skill"
        assert MemoryCategory.OPINION.value == "opinion"
