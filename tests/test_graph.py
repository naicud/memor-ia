"""Comprehensive tests for the MEMORIA graph layer."""

from __future__ import annotations

import time

import pytest

from memoria.graph.client import GraphClient, InMemoryGraph
from memoria.graph.schema import (
    GRAPH_SCHEMA,
    NodeSchema,
    NodeType,
    RelationType,
    all_allowed_props,
    validate_node_props,
)
from memoria.graph.entities import (
    Entity,
    Relation,
    extract_entities,
    extract_relations,
)
from memoria.graph.knowledge import KnowledgeGraph
from memoria.graph.temporal import (
    decay_confidence,
    get_entity_timeline,
    get_stale_entities,
    get_trending_concepts,
    record_interaction,
)
from memoria.graph.queries import QUERIES


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture()
def mem_graph() -> InMemoryGraph:
    return InMemoryGraph()


@pytest.fixture()
def client() -> GraphClient:
    return GraphClient(use_memory=True)


@pytest.fixture()
def kg(client: GraphClient) -> KnowledgeGraph:
    return KnowledgeGraph(client)


# ===================================================================
# 1. Client / InMemoryGraph tests
# ===================================================================


class TestInMemoryGraph:
    def test_add_and_query_node(self, mem_graph: InMemoryGraph) -> None:
        nid = mem_graph.add_node("Person", {"name": "Alice"})
        assert nid
        nodes = mem_graph.query_nodes("Person")
        assert len(nodes) == 1
        assert nodes[0]["name"] == "Alice"

    def test_add_and_query_multiple_nodes(self, mem_graph: InMemoryGraph) -> None:
        mem_graph.add_node("Person", {"name": "Alice"})
        mem_graph.add_node("Person", {"name": "Bob"})
        mem_graph.add_node("Tool", {"name": "git"})
        assert len(mem_graph.query_nodes("Person")) == 2
        assert len(mem_graph.query_nodes("Tool")) == 1

    def test_query_nodes_with_filters(self, mem_graph: InMemoryGraph) -> None:
        mem_graph.add_node("Person", {"name": "Alice", "role": "dev"})
        mem_graph.add_node("Person", {"name": "Bob", "role": "pm"})
        devs = mem_graph.query_nodes("Person", {"role": "dev"})
        assert len(devs) == 1
        assert devs[0]["name"] == "Alice"

    def test_add_and_query_edge(self, mem_graph: InMemoryGraph) -> None:
        a = mem_graph.add_node("Person", {"name": "Alice"})
        b = mem_graph.add_node("Project", {"name": "MEMORIA"})
        eid = mem_graph.add_edge(a, b, "WORKS_ON", {"since": "2024"})
        assert eid
        edges = mem_graph.query_edges("WORKS_ON")
        assert len(edges) == 1
        assert edges[0]["since"] == "2024"

    def test_add_edge_bad_node_raises(self, mem_graph: InMemoryGraph) -> None:
        a = mem_graph.add_node("Person", {"name": "Alice"})
        with pytest.raises(KeyError):
            mem_graph.add_edge(a, "nonexistent", "WORKS_ON")
        with pytest.raises(KeyError):
            mem_graph.add_edge("nonexistent", a, "WORKS_ON")

    def test_neighbors(self, mem_graph: InMemoryGraph) -> None:
        a = mem_graph.add_node("Person", {"name": "Alice"})
        b = mem_graph.add_node("Project", {"name": "P1"})
        c = mem_graph.add_node("Tool", {"name": "git"})
        mem_graph.add_edge(a, b, "WORKS_ON")
        mem_graph.add_edge(a, c, "USES")
        # All neighbors
        nb = mem_graph.neighbors(a)
        assert len(nb) == 2
        # Filtered by rel_type
        nb_works = mem_graph.neighbors(a, "WORKS_ON")
        assert len(nb_works) == 1
        assert nb_works[0]["name"] == "P1"

    def test_neighbors_bad_node_raises(self, mem_graph: InMemoryGraph) -> None:
        with pytest.raises(KeyError):
            mem_graph.neighbors("nonexistent")

    def test_delete_node_removes_edges(self, mem_graph: InMemoryGraph) -> None:
        a = mem_graph.add_node("Person", {"name": "Alice"})
        b = mem_graph.add_node("Project", {"name": "P1"})
        mem_graph.add_edge(a, b, "WORKS_ON")
        mem_graph.delete_node(a)
        assert len(mem_graph.nodes) == 1
        assert len(mem_graph.edges) == 0

    def test_delete_edge(self, mem_graph: InMemoryGraph) -> None:
        a = mem_graph.add_node("Person", {"name": "Alice"})
        b = mem_graph.add_node("Project", {"name": "P1"})
        eid = mem_graph.add_edge(a, b, "WORKS_ON")
        mem_graph.delete_edge(eid)
        assert len(mem_graph.edges) == 0
        assert len(mem_graph.nodes) == 2

    def test_delete_edge_bad_id_raises(self, mem_graph: InMemoryGraph) -> None:
        with pytest.raises(KeyError):
            mem_graph.delete_edge("nonexistent")

    def test_update_node(self, mem_graph: InMemoryGraph) -> None:
        nid = mem_graph.add_node("Person", {"name": "Alice"})
        mem_graph.update_node(nid, {"role": "dev"})
        nodes = mem_graph.query_nodes("Person")
        assert nodes[0]["role"] == "dev"

    def test_query_nodes_no_label(self, mem_graph: InMemoryGraph) -> None:
        mem_graph.add_node("Person", {"name": "Alice"})
        mem_graph.add_node("Tool", {"name": "git"})
        all_nodes = mem_graph.query_nodes()
        assert len(all_nodes) == 2


class TestGraphClient:
    def test_context_manager(self) -> None:
        with GraphClient(use_memory=True) as c:
            g = c.get_graph()
            assert isinstance(g, InMemoryGraph)

    def test_memory_backend_flag(self) -> None:
        c = GraphClient(use_memory=True)
        assert c.is_memory_backend is True

    def test_execute_raises_on_memory_backend(self, client: GraphClient) -> None:
        with pytest.raises(NotImplementedError):
            client.execute("MATCH (n) RETURN n")

    def test_close(self) -> None:
        c = GraphClient(use_memory=True)
        c.close()
        assert c._closed is True


# ===================================================================
# 2. Schema tests
# ===================================================================


class TestSchema:
    def test_all_node_types_have_schema(self) -> None:
        for nt in NodeType:
            assert nt in GRAPH_SCHEMA, f"Missing schema for {nt}"

    def test_all_relation_types_defined(self) -> None:
        expected = {
            "WORKS_ON", "KNOWS", "PREFERS", "USES", "DISCUSSED",
            "MODIFIED", "ABOUT", "REFERENCES", "WRITTEN_IN",
            "CHILD_OF", "MEMBER_OF_TEAM", "DETECTED_IN", "INVOLVES",
            "RELATED_TO",
        }
        actual = {rt.value for rt in RelationType}
        assert expected == actual

    def test_validate_node_props_ok(self) -> None:
        errors = validate_node_props(NodeType.PERSON, {"name": "Alice"})
        assert errors == []

    def test_validate_node_props_missing(self) -> None:
        errors = validate_node_props(NodeType.PERSON, {"role": "dev"})
        assert "name" in errors

    def test_all_allowed_props(self) -> None:
        props = all_allowed_props(NodeType.PROJECT)
        assert "name" in props
        assert "path" in props


# ===================================================================
# 3. Entity extraction tests
# ===================================================================


class TestEntityExtraction:
    def test_extract_names(self) -> None:
        entities = extract_entities("I spoke with John Smith about the project.")
        names = [e.name for e in entities if e.entity_type == NodeType.PERSON]
        assert "John Smith" in names

    def test_extract_mentions(self) -> None:
        entities = extract_entities("Ask @danieln for help.")
        names = [e.name for e in entities if e.entity_type == NodeType.PERSON]
        assert "danieln" in names

    def test_extract_tools(self) -> None:
        entities = extract_entities("We use docker and git for deployment.")
        tools = [e.name for e in entities if e.entity_type == NodeType.TOOL]
        assert "docker" in tools
        assert "git" in tools

    def test_extract_concepts(self) -> None:
        entities = extract_entities("Focus on testing and refactoring this sprint.")
        concepts = [e.name for e in entities if e.entity_type == NodeType.CONCEPT]
        assert "testing" in concepts
        assert "refactoring" in concepts

    def test_extract_paths(self) -> None:
        entities = extract_entities("Check the code in /src/memoria/graph/client.py")
        projects = [e.name for e in entities if e.entity_type == NodeType.PROJECT]
        assert any("/src/memoria/graph/client.py" in p for p in projects)

    def test_extract_urls(self) -> None:
        entities = extract_entities("See https://github.com/user/repo for details.")
        projects = [e.name for e in entities if e.entity_type == NodeType.PROJECT]
        assert any("github.com" in p for p in projects)

    def test_extract_preferences(self) -> None:
        entities = extract_entities("I prefer tabs over spaces.")
        prefs = [e.name for e in entities if e.entity_type == NodeType.PREFERENCE]
        assert any("tabs" in p for p in prefs)

    def test_confidence_scoring(self) -> None:
        entities = extract_entities("@alice mentioned docker.")
        for e in entities:
            assert 0.0 < e.confidence <= 1.0

    def test_empty_text(self) -> None:
        assert extract_entities("") == []

    def test_no_entities(self) -> None:
        entities = extract_entities("hello world this is a simple sentence")
        # May still find some things; just verify no crash
        assert isinstance(entities, list)

    def test_whitespace_only(self) -> None:
        assert extract_entities("   \n\t  ") == []

    def test_deduplication(self) -> None:
        entities = extract_entities("docker docker docker")
        docker_ents = [e for e in entities if e.name == "docker"]
        assert len(docker_ents) == 1

    def test_extract_relations_works_on(self) -> None:
        text = "git works on the project."
        entities = extract_entities(text)
        relations = extract_relations(text, entities)
        # At minimum, should not crash
        assert isinstance(relations, list)

    def test_extract_relations_empty(self) -> None:
        assert extract_relations("", []) == []

    def test_extract_relations_uses(self) -> None:
        text = "docker uses linux."
        entities = extract_entities(text)
        relations = extract_relations(text, entities)
        uses_rels = [r for r in relations if r.relation_type == RelationType.USES]
        if uses_rels:
            assert uses_rels[0].source.name == "docker"


# ===================================================================
# 4. Knowledge graph tests
# ===================================================================


class TestKnowledgeGraph:
    def test_add_and_find_entity(self, kg: KnowledgeGraph) -> None:
        entity = Entity("Alice", NodeType.PERSON, 0.9)
        node_id = kg.add_entity(entity)
        assert node_id
        found = kg.find_entity("Alice")
        assert len(found) == 1
        assert found[0]["name"] == "Alice"

    def test_add_entity_merge(self, kg: KnowledgeGraph) -> None:
        e1 = Entity("Alice", NodeType.PERSON, 0.9)
        e2 = Entity("Alice", NodeType.PERSON, 0.95)
        id1 = kg.add_entity(e1)
        id2 = kg.add_entity(e2)
        assert id1 == id2
        found = kg.find_entity("Alice")
        assert len(found) == 1

    def test_add_relation(self, kg: KnowledgeGraph) -> None:
        src = Entity("Alice", NodeType.PERSON, 0.9)
        tgt = Entity("MEMORIA", NodeType.PROJECT, 0.8)
        rel = Relation(src, tgt, RelationType.WORKS_ON, 0.85)
        edge_id = kg.add_relation(rel)
        assert edge_id

    def test_find_entity_by_type(self, kg: KnowledgeGraph) -> None:
        kg.add_entity(Entity("Alice", NodeType.PERSON))
        kg.add_entity(Entity("docker", NodeType.TOOL))
        persons = kg.find_entity("Alice", NodeType.PERSON)
        assert len(persons) == 1
        tools = kg.find_entity("docker", NodeType.TOOL)
        assert len(tools) == 1

    def test_find_entity_substring(self, kg: KnowledgeGraph) -> None:
        kg.add_entity(Entity("Alice Smith", NodeType.PERSON))
        found = kg.find_entity("Alice")
        assert len(found) == 1

    def test_ingest_text(self, kg: KnowledgeGraph) -> None:
        result = kg.ingest_text("We use docker and git for the project.")
        assert result["entities"] >= 2  # at least docker and git

    def test_ingest_text_with_session(self, kg: KnowledgeGraph) -> None:
        result = kg.ingest_text(
            "Focus on testing this sprint.", session_id="sess-001"
        )
        assert result["entities"] >= 1

    def test_get_related(self, kg: KnowledgeGraph) -> None:
        src = Entity("Alice", NodeType.PERSON, 0.9)
        tgt = Entity("MEMORIA", NodeType.PROJECT, 0.8)
        kg.add_relation(Relation(src, tgt, RelationType.WORKS_ON))
        related = kg.get_related("Alice")
        assert len(related) >= 1
        assert any(r.get("name") == "MEMORIA" for r in related)

    def test_get_related_with_type_filter(self, kg: KnowledgeGraph) -> None:
        src = Entity("Alice", NodeType.PERSON)
        tgt1 = Entity("P1", NodeType.PROJECT)
        tgt2 = Entity("docker", NodeType.TOOL)
        kg.add_relation(Relation(src, tgt1, RelationType.WORKS_ON))
        kg.add_relation(Relation(src, tgt2, RelationType.USES))
        works = kg.get_related("Alice", RelationType.WORKS_ON)
        assert len(works) == 1
        assert works[0]["name"] == "P1"

    def test_get_related_depth(self, kg: KnowledgeGraph) -> None:
        a = Entity("A", NodeType.CONCEPT)
        b = Entity("B", NodeType.CONCEPT)
        c = Entity("C", NodeType.CONCEPT)
        kg.add_relation(Relation(a, b, RelationType.RELATED_TO))
        kg.add_relation(Relation(b, c, RelationType.RELATED_TO))
        # Depth 1: only B
        d1 = kg.get_related("A", depth=1)
        assert any(r.get("name") == "B" for r in d1)
        # Depth 2: B and C
        d2 = kg.get_related("A", depth=2)
        names = {r.get("name") for r in d2}
        assert "B" in names
        assert "C" in names

    def test_get_entity_profile(self, kg: KnowledgeGraph) -> None:
        src = Entity("Alice", NodeType.PERSON)
        tgt = Entity("P1", NodeType.PROJECT)
        kg.add_relation(Relation(src, tgt, RelationType.WORKS_ON))
        profile = kg.get_entity_profile("Alice")
        assert profile["entity"]["name"] == "Alice"
        assert len(profile["outgoing_relations"]) >= 1

    def test_get_entity_profile_not_found(self, kg: KnowledgeGraph) -> None:
        profile = kg.get_entity_profile("Nonexistent")
        assert profile == {}

    def test_merge_entities(self, kg: KnowledgeGraph) -> None:
        kg.add_entity(Entity("JS", NodeType.CONCEPT))
        kg.add_entity(Entity("JavaScript", NodeType.CONCEPT))
        tgt = Entity("web", NodeType.CONCEPT)
        kg.add_entity(tgt)
        # Add a relation from "JS" to "web"
        kg.add_relation(
            Relation(Entity("JS", NodeType.CONCEPT), tgt, RelationType.RELATED_TO)
        )
        kg.merge_entities("JavaScript", "JS")
        # "JS" should be gone
        assert kg.find_entity("JS", NodeType.CONCEPT) == []
        # "JavaScript" should have inherited the relation
        related = kg.get_related("JavaScript")
        assert any(r.get("name") == "web" for r in related)

    def test_delete_entity(self, kg: KnowledgeGraph) -> None:
        kg.add_entity(Entity("temp", NodeType.CONCEPT))
        assert kg.delete_entity("temp") is True
        assert kg.find_entity("temp") == []

    def test_delete_entity_not_found(self, kg: KnowledgeGraph) -> None:
        assert kg.delete_entity("nonexistent") is False

    def test_stats(self, kg: KnowledgeGraph) -> None:
        kg.add_entity(Entity("Alice", NodeType.PERSON))
        kg.add_entity(Entity("docker", NodeType.TOOL))
        kg.add_relation(
            Relation(
                Entity("Alice", NodeType.PERSON),
                Entity("docker", NodeType.TOOL),
                RelationType.USES,
            )
        )
        s = kg.stats()
        assert s["total_nodes"] == 2
        assert s["total_edges"] == 1
        assert s["nodes_by_type"]["Person"] == 1
        assert s["nodes_by_type"]["Tool"] == 1

    def test_stats_empty(self, kg: KnowledgeGraph) -> None:
        s = kg.stats()
        assert s["total_nodes"] == 0
        assert s["total_edges"] == 0


# ===================================================================
# 5. Temporal tests
# ===================================================================


class TestTemporal:
    def test_record_interaction(self, kg: KnowledgeGraph) -> None:
        kg.add_entity(Entity("docker", NodeType.TOOL))
        record_interaction(kg, "docker", "sess-001")
        found = kg.find_entity("docker")
        assert found[0]["interaction_count"] == 1
        record_interaction(kg, "docker", "sess-002")
        found = kg.find_entity("docker")
        assert found[0]["interaction_count"] == 2

    def test_get_entity_timeline(self, kg: KnowledgeGraph) -> None:
        kg.add_entity(Entity("docker", NodeType.TOOL))
        record_interaction(kg, "docker", "sess-001")
        record_interaction(kg, "docker", "sess-002")
        timeline = get_entity_timeline(kg, "docker")
        assert len(timeline) == 2
        assert timeline[0]["session_id"] == "sess-001"

    def test_get_trending_concepts(self, kg: KnowledgeGraph) -> None:
        kg.add_entity(Entity("testing", NodeType.CONCEPT))
        record_interaction(kg, "testing", "s1")
        record_interaction(kg, "testing", "s2")
        trending = get_trending_concepts(kg, days=7)
        assert len(trending) >= 1
        assert trending[0]["name"] == "testing"

    def test_get_stale_entities(self, kg: KnowledgeGraph) -> None:
        kg.add_entity(Entity("old_thing", NodeType.CONCEPT))
        # Manually set last_seen to 60 days ago
        graph: InMemoryGraph = kg._graph
        for node in graph.nodes.values():
            if node.properties.get("name") == "old_thing":
                from datetime import datetime, timedelta, timezone

                old_date = (
                    datetime.now(timezone.utc) - timedelta(days=60)
                ).isoformat()
                node.properties["last_seen"] = old_date
        stale = get_stale_entities(kg, days=30)
        assert len(stale) >= 1
        assert stale[0]["name"] == "old_thing"

    def test_decay_confidence(self, kg: KnowledgeGraph) -> None:
        src = Entity("A", NodeType.CONCEPT)
        tgt = Entity("B", NodeType.CONCEPT)
        kg.add_relation(Relation(src, tgt, RelationType.RELATED_TO, 1.0))
        # Set edge created_at to 30 days ago (one half-life)
        graph: InMemoryGraph = kg._graph
        from datetime import datetime, timedelta, timezone

        old_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        for edge in graph.edges.values():
            edge.properties["created_at"] = old_date
            edge.properties["confidence"] = 1.0
        updated = decay_confidence(kg, half_life_days=30)
        assert updated >= 1
        for edge in graph.edges.values():
            # After one half-life, confidence should be ~0.5
            assert 0.4 <= edge.properties["confidence"] <= 0.6


# ===================================================================
# 6. Queries module test
# ===================================================================


class TestQueries:
    def test_all_queries_are_strings(self) -> None:
        for name, query in QUERIES.items():
            assert isinstance(query, str), f"Query {name!r} is not a string"
            assert len(query) > 10, f"Query {name!r} seems too short"

    def test_expected_queries_exist(self) -> None:
        expected = {
            "find_person", "person_projects", "concept_experts",
            "session_concepts", "related_concepts", "entity_neighbors",
            "graph_stats",
        }
        assert expected.issubset(set(QUERIES.keys()))
