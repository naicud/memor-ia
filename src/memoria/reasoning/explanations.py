"""Explainability layer — generate human-readable reasons for graph results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from memoria.graph.knowledge import KnowledgeGraph

from .traversal import GraphTraverser, PathResult

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Explanation:
    """Structured explanation for a graph result."""

    query: str
    result_id: str
    reason: str
    evidence: list[dict[str, Any]]
    confidence: float
    graph_paths: list[PathResult]


# ---------------------------------------------------------------------------
# ExplanationBuilder
# ---------------------------------------------------------------------------


class ExplanationBuilder:
    """Build human-readable explanations of graph relationships."""

    def __init__(
        self,
        knowledge_graph: KnowledgeGraph,
        traverser: GraphTraverser | None = None,
    ) -> None:
        self._kg = knowledge_graph
        self._traverser = traverser or GraphTraverser(knowledge_graph)

    # -- public API ---------------------------------------------------------

    def explain_connection(
        self, entity1_id: str, entity2_id: str
    ) -> Explanation:
        """Explain WHY two entities are connected.

        Finds all paths between them and builds a natural-language
        explanation with supporting evidence.
        """
        paths = self._traverser.find_paths(entity1_id, entity2_id)

        evidence: list[dict[str, Any]] = []
        reasons: list[str] = []

        for path in paths:
            for edge in path.edges:
                evidence.append(edge)
            reasons.append(_path_reason(path))

        if not reasons:
            reason = "No connection found between the two entities."
            confidence = 0.0
        else:
            reason = " | ".join(reasons)
            confidence = max(p.confidence for p in paths)

        node1 = self._traverser._node_dict(entity1_id)
        node2 = self._traverser._node_dict(entity2_id)
        name1 = node1.get("name", entity1_id) if node1 else entity1_id
        name2 = node2.get("name", entity2_id) if node2 else entity2_id

        return Explanation(
            query=f"connection({name1}, {name2})",
            result_id=entity2_id,
            reason=reason,
            evidence=evidence,
            confidence=confidence,
            graph_paths=paths,
        )

    def explain_relevance(
        self, query: str, entity_id: str
    ) -> Explanation:
        """Explain why *entity_id* is relevant to *query*.

        Searches for query terms in entity properties and related entities.
        """
        node = self._traverser._node_dict(entity_id)
        if node is None:
            return Explanation(
                query=query,
                result_id=entity_id,
                reason="Entity not found.",
                evidence=[],
                confidence=0.0,
                graph_paths=[],
            )

        terms = query.lower().split()
        evidence: list[dict[str, Any]] = []
        reasons: list[str] = []
        score = 0.0

        # Direct property matches
        for key, value in node.items():
            if key in ("id", "label"):
                continue
            val_str = str(value).lower()
            for term in terms:
                if term in val_str:
                    evidence.append({"type": "property_match", "key": key, "value": value})
                    reasons.append(f"Property '{key}' contains '{term}'")
                    score += 0.3

        # Check related entities for matches
        connections = self._traverser.find_connections(entity_id, max_depth=2)
        for conn in connections:
            related = conn["entity"]
            if related is None:
                continue
            related_name = str(related.get("name", "")).lower()
            for term in terms:
                if term in related_name:
                    evidence.append(
                        {
                            "type": "related_match",
                            "entity": related,
                            "depth": conn["depth"],
                        }
                    )
                    reasons.append(
                        f"Related entity '{related.get('name')}' matches '{term}'"
                    )
                    score += 0.2 / conn["depth"]

        confidence = min(score, 1.0)
        reason = "; ".join(reasons) if reasons else "No direct relevance found."

        return Explanation(
            query=query,
            result_id=entity_id,
            reason=reason,
            evidence=evidence,
            confidence=confidence,
            graph_paths=[],
        )

    def explain_suggestion(
        self, entity_id: str, suggested_entities: list[str]
    ) -> list[Explanation]:
        """Explain why each entity in *suggested_entities* is suggested."""
        explanations: list[Explanation] = []
        for suggested_id in suggested_entities:
            expl = self.explain_connection(entity_id, suggested_id)
            explanations.append(expl)
        return explanations

    def format_explanation(self, explanation: Explanation) -> str:
        """Format an :class:`Explanation` as multi-line human-readable text."""
        lines: list[str] = [
            f"Query: {explanation.query}",
            f"Result: {explanation.result_id}",
            f"Confidence: {explanation.confidence:.2f}",
            f"Reason: {explanation.reason}",
        ]

        if explanation.evidence:
            lines.append("Evidence:")
            for i, ev in enumerate(explanation.evidence, 1):
                ev_type = ev.get("type", ev.get("rel_type", "edge"))
                lines.append(f"  {i}. [{ev_type}] {_evidence_summary(ev)}")

        if explanation.graph_paths:
            lines.append("Paths:")
            for i, path in enumerate(explanation.graph_paths, 1):
                names = [
                    n.get("name", n.get("id", "?")) for n in path.nodes
                ]
                lines.append(
                    f"  {i}. {' -> '.join(names)} "
                    f"(hops={path.hops}, conf={path.confidence:.2f})"
                )

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _path_reason(path: PathResult) -> str:
    """Build a one-line reason string from a path."""
    parts: list[str] = []
    for i, edge in enumerate(path.edges):
        src_name = path.nodes[i].get("name", "?")
        rel = edge.get("rel_type", "related_to")
        parts.append(f"{src_name} {rel}")
    last_name = path.nodes[-1].get("name", "?")
    parts.append(last_name)
    return " -> ".join(parts)


def _evidence_summary(evidence: dict[str, Any]) -> str:
    """One-line summary of an evidence dict."""
    ev_type = evidence.get("type", "")
    if ev_type == "property_match":
        return f"{evidence['key']}={evidence['value']}"
    if ev_type == "related_match":
        entity = evidence.get("entity", {})
        return f"related to {entity.get('name', '?')} (depth {evidence.get('depth', '?')})"
    # Edge evidence
    rel = evidence.get("rel_type", "?")
    return f"{evidence.get('src_id', '?')} -{rel}-> {evidence.get('dst_id', '?')}"
