"""Tests for memoria.reasoning — multi-hop graph reasoning."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from memoria.graph.client import GraphClient
from memoria.graph.entities import Entity, Relation
from memoria.graph.knowledge import KnowledgeGraph
from memoria.graph.schema import NodeType, RelationType
from memoria.reasoning.chains import ChainBuilder, ChainLink, ReasoningChain
from memoria.reasoning.explanations import Explanation, ExplanationBuilder
from memoria.reasoning.temporal import TemporalReasoner
from memoria.reasoning.traversal import GraphTraverser, PathResult


# ---------------------------------------------------------------------------
# Shared test-graph builder
# ---------------------------------------------------------------------------


def _build_test_graph() -> tuple[KnowledgeGraph, dict[str, str]]:
    """Build a small test knowledge graph and return (kg, ids).

    Graph topology::

        Alice --WORKS_ON--> Project-X --USES--> Python
        Bob   --KNOWS----> Python
        Alice --KNOWS----> Bob
        Project-X --RELATED_TO--> AI
    """
    gc = GraphClient(use_memory=True)
    kg = KnowledgeGraph(gc)

    alice_id = kg.add_entity(Entity("Alice", NodeType.PERSON, 0.9))
    bob_id = kg.add_entity(Entity("Bob", NodeType.PERSON, 0.85))
    projx_id = kg.add_entity(Entity("Project-X", NodeType.PROJECT, 0.95))
    python_id = kg.add_entity(Entity("Python", NodeType.CONCEPT, 0.9))
    ai_id = kg.add_entity(Entity("AI", NodeType.CONCEPT, 0.8))

    kg.add_relation(
        Relation(
            Entity("Alice", NodeType.PERSON),
            Entity("Project-X", NodeType.PROJECT),
            RelationType.WORKS_ON,
            0.9,
        )
    )
    kg.add_relation(
        Relation(
            Entity("Project-X", NodeType.PROJECT),
            Entity("Python", NodeType.CONCEPT),
            RelationType.USES,
            0.85,
        )
    )
    kg.add_relation(
        Relation(
            Entity("Bob", NodeType.PERSON),
            Entity("Python", NodeType.CONCEPT),
            RelationType.KNOWS,
            0.8,
        )
    )
    kg.add_relation(
        Relation(
            Entity("Alice", NodeType.PERSON),
            Entity("Bob", NodeType.PERSON),
            RelationType.KNOWS,
            0.75,
        )
    )
    kg.add_relation(
        Relation(
            Entity("Project-X", NodeType.PROJECT),
            Entity("AI", NodeType.CONCEPT),
            RelationType.RELATED_TO,
            0.7,
        )
    )

    ids = {
        "alice": alice_id,
        "bob": bob_id,
        "projx": projx_id,
        "python": python_id,
        "ai": ai_id,
    }
    return kg, ids


# ===========================================================================
# TestGraphTraverser
# ===========================================================================


class TestGraphTraverser:
    """Tests for :class:`GraphTraverser`."""

    def setup_method(self) -> None:
        self.kg, self.ids = _build_test_graph()
        self.traverser = GraphTraverser(self.kg)

    # -- neighbors ----------------------------------------------------------

    def test_neighbors_returns_direct_connections(self) -> None:
        nbrs = self.traverser.neighbors(self.ids["alice"])
        names = {n["name"] for n in nbrs}
        assert "Project-X" in names
        assert "Bob" in names

    def test_neighbors_filtered_by_relation(self) -> None:
        nbrs = self.traverser.neighbors(
            self.ids["alice"], relation_type=RelationType.WORKS_ON.value
        )
        names = {n["name"] for n in nbrs}
        assert names == {"Project-X"}

    def test_neighbors_empty_for_isolated_node(self) -> None:
        gc = GraphClient(use_memory=True)
        kg = KnowledgeGraph(gc)
        nid = kg.add_entity(Entity("Loner", NodeType.PERSON))
        t = GraphTraverser(kg)
        assert t.neighbors(nid) == []

    # -- find_paths ---------------------------------------------------------

    def test_find_paths_direct(self) -> None:
        paths = self.traverser.find_paths(self.ids["alice"], self.ids["bob"])
        assert len(paths) >= 1
        direct = [p for p in paths if p.hops == 1]
        assert len(direct) >= 1

    def test_find_paths_multi_hop(self) -> None:
        # Alice -> Project-X -> Python; Bob -> Python
        paths = self.traverser.find_paths(
            self.ids["alice"], self.ids["python"], max_depth=3
        )
        assert len(paths) >= 1
        hops = {p.hops for p in paths}
        assert 2 in hops  # Alice -> ProjectX -> Python

    def test_find_paths_respects_max_depth(self) -> None:
        paths = self.traverser.find_paths(
            self.ids["alice"], self.ids["python"], max_depth=1
        )
        # No direct edge Alice->Python, so no paths at depth 1
        assert len(paths) == 0

    def test_find_paths_no_connection(self) -> None:
        gc = GraphClient(use_memory=True)
        kg = KnowledgeGraph(gc)
        a = kg.add_entity(Entity("X", NodeType.PERSON))
        b = kg.add_entity(Entity("Y", NodeType.PERSON))
        t = GraphTraverser(kg)
        assert t.find_paths(a, b) == []

    def test_find_paths_sorted_by_confidence(self) -> None:
        paths = self.traverser.find_paths(
            self.ids["alice"], self.ids["python"], max_depth=4
        )
        if len(paths) >= 2:
            confs = [p.confidence for p in paths]
            assert confs == sorted(confs, reverse=True)

    def test_find_paths_invalid_source(self) -> None:
        assert self.traverser.find_paths("no-such-id", self.ids["bob"]) == []

    # -- shortest_path ------------------------------------------------------

    def test_shortest_path_direct(self) -> None:
        path = self.traverser.shortest_path(self.ids["alice"], self.ids["bob"])
        assert path is not None
        assert path.hops == 1

    def test_shortest_path_multi_hop(self) -> None:
        path = self.traverser.shortest_path(
            self.ids["alice"], self.ids["python"]
        )
        assert path is not None
        assert path.hops == 2  # Alice -> ProjectX -> Python

    def test_shortest_path_same_node(self) -> None:
        path = self.traverser.shortest_path(
            self.ids["alice"], self.ids["alice"]
        )
        assert path is not None
        assert path.hops == 0
        assert path.confidence == 1.0

    def test_shortest_path_no_connection(self) -> None:
        gc = GraphClient(use_memory=True)
        kg = KnowledgeGraph(gc)
        a = kg.add_entity(Entity("X", NodeType.PERSON))
        b = kg.add_entity(Entity("Y", NodeType.PERSON))
        t = GraphTraverser(kg)
        assert t.shortest_path(a, b) is None

    # -- find_connections ---------------------------------------------------

    def test_find_connections_depth_1(self) -> None:
        conns = self.traverser.find_connections(self.ids["alice"], max_depth=1)
        entities = {c["entity"]["name"] for c in conns}
        assert "Project-X" in entities
        assert "Bob" in entities

    def test_find_connections_depth_2(self) -> None:
        conns = self.traverser.find_connections(self.ids["alice"], max_depth=2)
        entities = {c["entity"]["name"] for c in conns}
        assert "Python" in entities
        assert "AI" in entities

    def test_find_connections_includes_depth(self) -> None:
        conns = self.traverser.find_connections(self.ids["alice"], max_depth=2)
        depth_map = {c["entity"]["name"]: c["depth"] for c in conns}
        assert depth_map.get("Project-X") == 1
        assert depth_map.get("Bob") == 1

    def test_find_connections_invalid_entity(self) -> None:
        assert self.traverser.find_connections("no-such-id") == []

    # -- path_confidence ----------------------------------------------------

    def test_path_confidence_empty_path(self) -> None:
        pr = PathResult(nodes=[], edges=[], hops=0, confidence=0, total_weight=0)
        assert self.traverser.path_confidence(pr) == 1.0

    def test_path_confidence_decays(self) -> None:
        path = self.traverser.shortest_path(
            self.ids["alice"], self.ids["python"]
        )
        assert path is not None
        assert path.confidence < 1.0
        assert path.confidence > 0.0

    # -- cycle handling -----------------------------------------------------

    def test_no_infinite_loop_on_cycle(self) -> None:
        gc = GraphClient(use_memory=True)
        kg = KnowledgeGraph(gc)
        a = kg.add_entity(Entity("A", NodeType.CONCEPT))
        b = kg.add_entity(Entity("B", NodeType.CONCEPT))
        c = kg.add_entity(Entity("C", NodeType.CONCEPT))
        kg.add_relation(Relation(Entity("A", NodeType.CONCEPT), Entity("B", NodeType.CONCEPT), RelationType.RELATED_TO))
        kg.add_relation(Relation(Entity("B", NodeType.CONCEPT), Entity("C", NodeType.CONCEPT), RelationType.RELATED_TO))
        kg.add_relation(Relation(Entity("C", NodeType.CONCEPT), Entity("A", NodeType.CONCEPT), RelationType.RELATED_TO))
        t = GraphTraverser(kg)
        paths = t.find_paths(a, c, max_depth=5)
        # Should finish without hanging
        assert len(paths) >= 1


# ===========================================================================
# TestChainBuilder
# ===========================================================================


class TestChainBuilder:
    """Tests for :class:`ChainBuilder`."""

    def setup_method(self) -> None:
        self.kg, self.ids = _build_test_graph()
        self.builder = ChainBuilder(self.kg)

    # -- build_chain --------------------------------------------------------

    def test_build_chain_direct(self) -> None:
        chain = self.builder.build_chain(self.ids["alice"], self.ids["bob"])
        assert chain is not None
        assert len(chain.links) >= 1
        assert chain.overall_confidence > 0

    def test_build_chain_multi_hop(self) -> None:
        chain = self.builder.build_chain(
            self.ids["alice"], self.ids["python"]
        )
        assert chain is not None
        assert len(chain.links) >= 2

    def test_build_chain_conclusion_text(self) -> None:
        chain = self.builder.build_chain(self.ids["alice"], self.ids["bob"])
        assert chain is not None
        assert "Alice" in chain.conclusion
        assert "Bob" in chain.conclusion
        assert "connected" in chain.conclusion.lower()

    def test_build_chain_no_path(self) -> None:
        gc = GraphClient(use_memory=True)
        kg = KnowledgeGraph(gc)
        a = kg.add_entity(Entity("X", NodeType.PERSON))
        b = kg.add_entity(Entity("Y", NodeType.PERSON))
        builder = ChainBuilder(kg)
        assert builder.build_chain(a, b) is None

    # -- infer_relations ----------------------------------------------------

    def test_infer_relations_finds_implicit(self) -> None:
        chains = self.builder.infer_relations(self.ids["alice"], max_depth=2)
        # Should find multi-hop chains (depth >= 2)
        assert len(chains) >= 1
        for chain in chains:
            assert len(chain.links) >= 2

    def test_infer_relations_empty_for_isolated(self) -> None:
        gc = GraphClient(use_memory=True)
        kg = KnowledgeGraph(gc)
        nid = kg.add_entity(Entity("Loner", NodeType.PERSON))
        builder = ChainBuilder(kg)
        assert builder.infer_relations(nid) == []

    # -- validate_chain -----------------------------------------------------

    def test_validate_chain_valid(self) -> None:
        chain = self.builder.build_chain(self.ids["alice"], self.ids["bob"])
        assert chain is not None
        assert self.builder.validate_chain(chain)

    def test_validate_chain_after_deletion(self) -> None:
        chain = self.builder.build_chain(self.ids["alice"], self.ids["bob"])
        assert chain is not None
        # Remove Bob from the graph
        graph = self.kg._graph
        graph.delete_node(self.ids["bob"])
        assert not self.builder.validate_chain(chain)

    # -- chain_to_text ------------------------------------------------------

    def test_chain_to_text_readable(self) -> None:
        chain = self.builder.build_chain(self.ids["alice"], self.ids["bob"])
        assert chain is not None
        text = self.builder.chain_to_text(chain)
        assert "Alice" in text
        assert "Conclusion" in text

    def test_chain_to_text_empty_chain(self) -> None:
        chain = ReasoningChain(links=[], conclusion="No links", overall_confidence=0)
        text = self.builder.chain_to_text(chain)
        assert text == "No links"


# ===========================================================================
# TestTemporalReasoner
# ===========================================================================


class TestTemporalReasoner:
    """Tests for :class:`TemporalReasoner`."""

    def _build_temporal_graph(self) -> tuple[KnowledgeGraph, dict[str, str]]:
        gc = GraphClient(use_memory=True)
        kg = KnowledgeGraph(gc)
        now = datetime.now(timezone.utc)

        a_id = kg.add_entity(Entity("Alice", NodeType.PERSON))
        b_id = kg.add_entity(Entity("Bob", NodeType.PERSON))
        p_id = kg.add_entity(Entity("ProjectT", NodeType.PROJECT))

        # Set timestamps on nodes
        graph = kg._graph
        graph.nodes[a_id].properties["last_seen"] = now.isoformat()
        graph.nodes[a_id].properties["created_at"] = (
            now - timedelta(days=10)
        ).isoformat()
        graph.nodes[b_id].properties["last_seen"] = (
            now - timedelta(days=60)
        ).isoformat()
        graph.nodes[b_id].properties["created_at"] = (
            now - timedelta(days=90)
        ).isoformat()
        graph.nodes[p_id].properties["last_seen"] = now.isoformat()

        # Relation with timestamp
        kg.add_relation(
            Relation(
                Entity("Alice", NodeType.PERSON),
                Entity("ProjectT", NodeType.PROJECT),
                RelationType.WORKS_ON,
                0.9,
            )
        )

        return kg, {"alice": a_id, "bob": b_id, "project": p_id}

    def setup_method(self) -> None:
        self.kg, self.ids = self._build_temporal_graph()
        self.reasoner = TemporalReasoner(self.kg)

    # -- entities_active_in_range -------------------------------------------

    def test_active_in_range_finds_recent(self) -> None:
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=15)).isoformat()
        end = now.isoformat()
        results = self.reasoner.entities_active_in_range(start, end)
        names = {r.get("name") for r in results}
        assert "Alice" in names

    def test_active_in_range_excludes_old(self) -> None:
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=5)).isoformat()
        end = now.isoformat()
        results = self.reasoner.entities_active_in_range(start, end)
        names = {r.get("name") for r in results}
        assert "Bob" not in names

    def test_active_in_range_empty(self) -> None:
        results = self.reasoner.entities_active_in_range(
            "1990-01-01T00:00:00+00:00", "1990-01-02T00:00:00+00:00"
        )
        assert results == []

    # -- relationship_timeline ----------------------------------------------

    def test_relationship_timeline_sorted(self) -> None:
        timeline = self.reasoner.relationship_timeline(self.ids["alice"])
        assert len(timeline) >= 1
        timestamps = [e["timestamp"] for e in timeline if e["timestamp"]]
        assert timestamps == sorted(timestamps)

    def test_relationship_timeline_contents(self) -> None:
        timeline = self.reasoner.relationship_timeline(self.ids["alice"])
        assert all("connected_entity" in e for e in timeline)
        assert all("type" in e for e in timeline)

    # -- recent_connections -------------------------------------------------

    def test_recent_connections_finds_recent(self) -> None:
        conns = self.reasoner.recent_connections(self.ids["alice"], days=7)
        # The relation was just created, so created_at is recent
        assert len(conns) >= 1

    def test_recent_connections_respects_days(self) -> None:
        # Create a graph with an old connection
        gc = GraphClient(use_memory=True)
        kg = KnowledgeGraph(gc)
        a = kg.add_entity(Entity("Old", NodeType.PERSON))
        b = kg.add_entity(Entity("Friend", NodeType.PERSON))
        graph = kg._graph
        old_ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        graph.add_edge(a, b, RelationType.KNOWS.value, {"created_at": old_ts})
        reasoner = TemporalReasoner(kg)
        conns = reasoner.recent_connections(a, days=7)
        assert len(conns) == 0

    # -- detect_patterns ----------------------------------------------------

    def test_detect_patterns_recurring(self) -> None:
        gc = GraphClient(use_memory=True)
        kg = KnowledgeGraph(gc)
        a = kg.add_entity(Entity("Dev", NodeType.PERSON))
        b = kg.add_entity(Entity("Repo", NodeType.PROJECT))
        graph = kg._graph
        now = datetime.now(timezone.utc)
        # Add two edges to same target
        graph.add_edge(
            a, b, RelationType.WORKS_ON.value,
            {"created_at": (now - timedelta(days=5)).isoformat()},
        )
        graph.add_edge(
            a, b, RelationType.WORKS_ON.value,
            {"created_at": now.isoformat()},
        )
        reasoner = TemporalReasoner(kg)
        patterns = reasoner.detect_patterns(a)
        types = {p["pattern_type"] for p in patterns}
        assert "recurring" in types

    def test_detect_patterns_burst(self) -> None:
        gc = GraphClient(use_memory=True)
        kg = KnowledgeGraph(gc)
        a = kg.add_entity(Entity("BurstDev", NodeType.PERSON))
        graph = kg._graph
        now = datetime.now(timezone.utc)
        # Add 4 connections in 1 hour
        for i in range(4):
            target = kg.add_entity(
                Entity(f"Task-{i}", NodeType.CONCEPT)
            )
            graph.add_edge(
                a, target, RelationType.RELATED_TO.value,
                {"created_at": (now - timedelta(hours=i)).isoformat()},
            )
        reasoner = TemporalReasoner(kg)
        patterns = reasoner.detect_patterns(a)
        types = {p["pattern_type"] for p in patterns}
        assert "burst" in types

    def test_detect_patterns_decay(self) -> None:
        gc = GraphClient(use_memory=True)
        kg = KnowledgeGraph(gc)
        a = kg.add_entity(Entity("DecayDev", NodeType.PERSON))
        graph = kg._graph
        now = datetime.now(timezone.utc)
        # Connections with increasing gaps: 10→7 (3d gap), 7→1 (6d gap)
        for offset in [10, 7, 1]:
            target = kg.add_entity(Entity(f"T-{offset}", NodeType.CONCEPT))
            ts = (now - timedelta(days=offset)).isoformat()
            graph.add_edge(
                a, target, RelationType.RELATED_TO.value,
                {"created_at": ts},
            )
        reasoner = TemporalReasoner(kg)
        patterns = reasoner.detect_patterns(a)
        types = {p["pattern_type"] for p in patterns}
        assert "decay" in types

    def test_detect_patterns_empty(self) -> None:
        gc = GraphClient(use_memory=True)
        kg = KnowledgeGraph(gc)
        a = kg.add_entity(Entity("Lonely", NodeType.PERSON))
        reasoner = TemporalReasoner(kg)
        assert reasoner.detect_patterns(a) == []

    # -- decay_score --------------------------------------------------------

    def test_decay_score_recent_is_high(self) -> None:
        score = self.reasoner.decay_score(self.ids["alice"])
        assert score > 0.7

    def test_decay_score_old_is_low(self) -> None:
        score = self.reasoner.decay_score(self.ids["bob"])
        assert score < 0.5

    def test_decay_score_missing_entity(self) -> None:
        assert self.reasoner.decay_score("nonexistent") == 0.0

    def test_decay_score_with_reference_time(self) -> None:
        future = (
            datetime.now(timezone.utc) + timedelta(days=60)
        ).isoformat()
        score = self.reasoner.decay_score(self.ids["alice"], reference_time=future)
        assert score < 0.5


# ===========================================================================
# TestExplanationBuilder
# ===========================================================================


class TestExplanationBuilder:
    """Tests for :class:`ExplanationBuilder`."""

    def setup_method(self) -> None:
        self.kg, self.ids = _build_test_graph()
        self.builder = ExplanationBuilder(self.kg)

    # -- explain_connection -------------------------------------------------

    def test_explain_connection_found(self) -> None:
        expl = self.builder.explain_connection(
            self.ids["alice"], self.ids["bob"]
        )
        assert isinstance(expl, Explanation)
        assert expl.confidence > 0
        assert len(expl.graph_paths) >= 1

    def test_explain_connection_no_link(self) -> None:
        gc = GraphClient(use_memory=True)
        kg = KnowledgeGraph(gc)
        a = kg.add_entity(Entity("X", NodeType.PERSON))
        b = kg.add_entity(Entity("Y", NodeType.PERSON))
        builder = ExplanationBuilder(kg)
        expl = builder.explain_connection(a, b)
        assert expl.confidence == 0.0
        assert "No connection" in expl.reason

    def test_explain_connection_evidence(self) -> None:
        expl = self.builder.explain_connection(
            self.ids["alice"], self.ids["bob"]
        )
        assert len(expl.evidence) >= 1

    # -- explain_relevance --------------------------------------------------

    def test_explain_relevance_direct_match(self) -> None:
        expl = self.builder.explain_relevance("Alice", self.ids["alice"])
        assert expl.confidence > 0
        assert len(expl.evidence) >= 1

    def test_explain_relevance_no_match(self) -> None:
        expl = self.builder.explain_relevance(
            "zzz_nonexistent_zzz", self.ids["alice"]
        )
        assert expl.confidence == 0.0

    def test_explain_relevance_missing_entity(self) -> None:
        expl = self.builder.explain_relevance("test", "nonexistent-id")
        assert "not found" in expl.reason.lower()

    # -- explain_suggestion -------------------------------------------------

    def test_explain_suggestion_returns_list(self) -> None:
        explanations = self.builder.explain_suggestion(
            self.ids["alice"], [self.ids["bob"], self.ids["projx"]]
        )
        assert len(explanations) == 2
        assert all(isinstance(e, Explanation) for e in explanations)

    # -- format_explanation -------------------------------------------------

    def test_format_explanation_basic(self) -> None:
        expl = self.builder.explain_connection(
            self.ids["alice"], self.ids["bob"]
        )
        text = self.builder.format_explanation(expl)
        assert "Query:" in text
        assert "Confidence:" in text
        assert "Reason:" in text

    def test_format_explanation_with_paths(self) -> None:
        expl = self.builder.explain_connection(
            self.ids["alice"], self.ids["bob"]
        )
        text = self.builder.format_explanation(expl)
        assert "Paths:" in text
