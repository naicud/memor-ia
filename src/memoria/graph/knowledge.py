"""High-level knowledge graph CRUD operations."""

from __future__ import annotations

import time
from typing import Any, Optional

from .client import GraphClient, InMemoryGraph
from .entities import Entity, Relation, extract_entities, extract_relations
from .schema import NodeType, RelationType, validate_node_props

# ---------------------------------------------------------------------------
# KnowledgeGraph
# ---------------------------------------------------------------------------


class KnowledgeGraph:
    """High-level knowledge graph operations backed by a GraphClient."""

    def __init__(self, client: GraphClient) -> None:
        self._client = client
        self._graph: InMemoryGraph | Any = client.get_graph()

    @property
    def is_memory_backend(self) -> bool:
        return self._client.is_memory_backend

    # -- entity CRUD --------------------------------------------------------

    def add_entity(self, entity: Entity) -> str:
        """Add or merge an entity node.  Returns the node_id."""
        if self.is_memory_backend:
            return self._add_entity_memory(entity)
        return self._add_entity_cypher(entity)

    def _add_entity_memory(self, entity: Entity) -> str:
        graph: InMemoryGraph = self._graph
        existing = graph.query_nodes(
            entity.entity_type.value, {"name": entity.name}
        )
        if existing:
            node_id = existing[0]["id"]
            graph.update_node(
                node_id,
                {
                    "confidence": entity.confidence,
                    "last_seen": _now_iso(),
                },
            )
            return node_id
        return graph.add_node(
            entity.entity_type.value,
            {
                "name": entity.name,
                "confidence": entity.confidence,
                "created_at": _now_iso(),
                "last_seen": _now_iso(),
                "interaction_count": 0,
            },
        )

    def _add_entity_cypher(self, entity: Entity) -> str:
        label = entity.entity_type.value
        result = self._client.execute(
            f"MERGE (n:{label} {{name: $name}}) "
            f"ON CREATE SET n.confidence = $conf, n.created_at = $now, "
            f"n.last_seen = $now, n.interaction_count = 0 "
            f"ON MATCH SET n.confidence = $conf, n.last_seen = $now "
            f"RETURN id(n)",
            {
                "name": entity.name,
                "conf": entity.confidence,
                "now": _now_iso(),
            },
        )
        return str(result.result_set[0][0]) if result.result_set else ""

    # -- relation CRUD ------------------------------------------------------

    def add_relation(self, relation: Relation) -> str:
        """Add a relationship edge.  Returns the edge_id."""
        src_id = self.add_entity(relation.source)
        tgt_id = self.add_entity(relation.target)

        if self.is_memory_backend:
            graph: InMemoryGraph = self._graph
            # Avoid duplicate edges
            existing = graph.query_edges(
                relation.relation_type.value,
                {"src_name": relation.source.name, "tgt_name": relation.target.name},
            )
            if existing:
                return existing[0]["id"]
            return graph.add_edge(
                src_id,
                tgt_id,
                relation.relation_type.value,
                {
                    "confidence": relation.confidence,
                    "created_at": _now_iso(),
                    "src_name": relation.source.name,
                    "tgt_name": relation.target.name,
                },
            )

        rel = relation.relation_type.value
        result = self._client.execute(
            f"MATCH (a {{name: $src}}), (b {{name: $tgt}}) "
            f"MERGE (a)-[r:{rel}]->(b) "
            f"ON CREATE SET r.confidence = $conf, r.created_at = $now "
            f"RETURN id(r)",
            {
                "src": relation.source.name,
                "tgt": relation.target.name,
                "conf": relation.confidence,
                "now": _now_iso(),
            },
        )
        return str(result.result_set[0][0]) if result.result_set else ""

    # -- text ingestion -----------------------------------------------------

    def ingest_text(
        self,
        text: str,
        session_id: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, int]:
        """Extract entities & relations from *text* and add to graph.

        Returns a dict with counts: ``{"entities": N, "relations": M}``.
        """
        entities = extract_entities(text)
        relations = extract_relations(text, entities)

        for entity in entities:
            self.add_entity(entity)
        for relation in relations:
            self.add_relation(relation)

        # Link to session if provided
        if session_id and self.is_memory_backend:
            graph: InMemoryGraph = self._graph
            sess_nodes = graph.query_nodes(NodeType.SESSION.value, {"id": session_id})
            if not sess_nodes:
                sid = graph.add_node(
                    NodeType.SESSION.value,
                    {"id": session_id, "started_at": _now_iso()},
                )
            else:
                sid = sess_nodes[0]["id"]

            for entity in entities:
                enodes = graph.query_nodes(
                    entity.entity_type.value, {"name": entity.name}
                )
                if enodes:
                    graph.add_edge(
                        sid,
                        enodes[0]["id"],
                        RelationType.INVOLVES.value,
                        {"created_at": _now_iso()},
                    )

        return {"entities": len(entities), "relations": len(relations)}

    # -- query helpers ------------------------------------------------------

    def find_entity(
        self, name: str, entity_type: NodeType | None = None
    ) -> list[dict[str, Any]]:
        """Find entities by name (substring match)."""
        if self.is_memory_backend:
            graph: InMemoryGraph = self._graph
            results: list[dict[str, Any]] = []
            label = entity_type.value if entity_type else None
            for node in graph.query_nodes(label):
                node_name = node.get("name", "")
                if name.lower() in node_name.lower():
                    results.append(node)
            return results

        query = "MATCH (n) WHERE n.name CONTAINS $name"
        if entity_type:
            query = f"MATCH (n:{entity_type.value}) WHERE n.name CONTAINS $name"
        query += " RETURN n"
        result = self._client.execute(query, {"name": name})
        return [dict(r[0].properties) for r in result.result_set]

    def get_related(
        self,
        entity_name: str,
        rel_type: RelationType | None = None,
        depth: int = 1,
    ) -> list[dict[str, Any]]:
        """Get entities related to *entity_name*."""
        if self.is_memory_backend:
            return self._get_related_memory(entity_name, rel_type, depth)

        rel_filter = f":{rel_type.value}" if rel_type else ""
        result = self._client.execute(
            f"MATCH (n {{name: $name}})-[r{rel_filter}*1..{depth}]-(m) "
            f"RETURN DISTINCT m",
            {"name": entity_name},
        )
        return [dict(r[0].properties) for r in result.result_set]

    def _get_related_memory(
        self,
        entity_name: str,
        rel_type: RelationType | None = None,
        depth: int = 1,
    ) -> list[dict[str, Any]]:
        graph: InMemoryGraph = self._graph
        # Find starting node
        start_nodes = [
            n for n in graph.query_nodes()
            if n.get("name", "").lower() == entity_name.lower()
        ]
        if not start_nodes:
            return []

        visited: set[str] = set()
        results: list[dict[str, Any]] = []
        frontier = [start_nodes[0]["id"]]

        for _ in range(depth):
            next_frontier: list[str] = []
            for nid in frontier:
                visited.add(nid)
                neighbors = graph.neighbors(
                    nid, rel_type.value if rel_type else None
                )
                for nb in neighbors:
                    if nb["id"] not in visited:
                        results.append(nb)
                        next_frontier.append(nb["id"])
            frontier = next_frontier

        return results

    def get_entity_profile(self, name: str) -> dict[str, Any]:
        """Get complete profile of an entity (all relations and types)."""
        entities = self.find_entity(name)
        if not entities:
            return {}

        entity = entities[0]
        related = self.get_related(name)

        if self.is_memory_backend:
            graph: InMemoryGraph = self._graph
            edges_out: list[dict[str, Any]] = []
            edges_in: list[dict[str, Any]] = []
            for edge in graph.edges.values():
                if edge.src_id == entity["id"]:
                    dst = graph.nodes.get(edge.dst_id)
                    if dst:
                        edges_out.append(
                            {
                                "rel_type": edge.rel_type,
                                "target": dst.properties.get("name", dst.node_id),
                                "target_label": dst.label,
                            }
                        )
                elif edge.dst_id == entity["id"]:
                    src = graph.nodes.get(edge.src_id)
                    if src:
                        edges_in.append(
                            {
                                "rel_type": edge.rel_type,
                                "source": src.properties.get("name", src.node_id),
                                "source_label": src.label,
                            }
                        )
        else:
            edges_out = []
            edges_in = []

        return {
            "entity": entity,
            "outgoing_relations": edges_out,
            "incoming_relations": edges_in,
            "related_count": len(related),
        }

    def merge_entities(self, name1: str, name2: str) -> None:
        """Merge two entities that refer to the same thing.

        Keeps *name1* and transfers all edges from *name2* to *name1*,
        then deletes *name2*.
        """
        if not self.is_memory_backend:
            raise NotImplementedError("merge_entities only supports in-memory backend")

        graph: InMemoryGraph = self._graph
        nodes1 = [
            n for n in graph.query_nodes()
            if n.get("name", "").lower() == name1.lower()
        ]
        nodes2 = [
            n for n in graph.query_nodes()
            if n.get("name", "").lower() == name2.lower()
        ]
        if not nodes1 or not nodes2:
            return

        keep_id = nodes1[0]["id"]
        remove_id = nodes2[0]["id"]

        # Re-point edges from remove_id → keep_id
        for edge in list(graph.edges.values()):
            if edge.src_id == remove_id:
                edge.src_id = keep_id
            if edge.dst_id == remove_id:
                edge.dst_id = keep_id

        # Delete the duplicate node (but not its now-reassigned edges)
        del graph.nodes[remove_id]

    def delete_entity(self, name: str) -> bool:
        """Delete entity and all its relations.  Returns True if found."""
        if self.is_memory_backend:
            graph: InMemoryGraph = self._graph
            targets = [
                n
                for n in graph.query_nodes()
                if n.get("name", "").lower() == name.lower()
            ]
            if not targets:
                return False
            graph.delete_node(targets[0]["id"])
            return True

        result = self._client.execute(
            "MATCH (n {name: $name}) DETACH DELETE n RETURN count(n)",
            {"name": name},
        )
        return bool(result.result_set and result.result_set[0][0] > 0)

    # -- statistics ---------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """Return graph statistics (node/edge counts by type)."""
        if self.is_memory_backend:
            graph: InMemoryGraph = self._graph
            node_counts: dict[str, int] = {}
            for node in graph.nodes.values():
                node_counts[node.label] = node_counts.get(node.label, 0) + 1
            edge_counts: dict[str, int] = {}
            for edge in graph.edges.values():
                edge_counts[edge.rel_type] = edge_counts.get(edge.rel_type, 0) + 1
            return {
                "total_nodes": len(graph.nodes),
                "total_edges": len(graph.edges),
                "nodes_by_type": node_counts,
                "edges_by_type": edge_counts,
            }

        node_result = self._client.execute(
            "MATCH (n) RETURN labels(n)[0] AS type, count(n) AS count"
        )
        edge_result = self._client.execute(
            "MATCH ()-[r]->() RETURN type(r) AS rel_type, count(r) AS count"
        )
        return {
            "nodes_by_type": {r[0]: r[1] for r in node_result.result_set},
            "edges_by_type": {r[0]: r[1] for r in edge_result.result_set},
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return current UTC time as ISO string."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
