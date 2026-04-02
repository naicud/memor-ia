"""Multi-hop graph traversal and path finding."""

from __future__ import annotations

import heapq
from collections import deque
from dataclasses import dataclass
from typing import Any, Optional

from memoria.graph.client import GraphClient, InMemoryGraph
from memoria.graph.knowledge import KnowledgeGraph

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

CONFIDENCE_DECAY = 0.9


@dataclass
class PathResult:
    """A single path between two entities in the knowledge graph."""

    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    hops: int
    confidence: float
    total_weight: float


# ---------------------------------------------------------------------------
# GraphTraverser
# ---------------------------------------------------------------------------


class GraphTraverser:
    """Multi-hop path finding over a :class:`KnowledgeGraph`.

    Supports both InMemoryGraph (direct dict access) and FalkorDB (Cypher queries).
    """

    def __init__(self, knowledge_graph: KnowledgeGraph) -> None:
        self._kg = knowledge_graph
        self._client: GraphClient = knowledge_graph._client
        self._is_memory = isinstance(knowledge_graph._graph, InMemoryGraph)
        if self._is_memory:
            self._graph: InMemoryGraph = knowledge_graph._graph  # type: ignore[assignment]

    # -- helpers ------------------------------------------------------------

    def _node_dict(self, node_id: str) -> Optional[dict[str, Any]]:
        """Return a node as a dict or *None* if missing."""
        if self._is_memory:
            node = self._graph.nodes.get(node_id)
            if node is None:
                return None
            return {"id": node.node_id, "label": node.label, **node.properties}
        # FalkorDB: query by internal integer ID
        try:
            result = self._client.execute(
                "MATCH (n) WHERE ID(n) = $nid RETURN n, labels(n)[0] AS lbl",
                {"nid": int(node_id)},
            )
            if result.result_set:
                row = result.result_set[0]
                n = row[0]
                label = row[1] if len(row) > 1 else ""
                props = dict(n.properties) if hasattr(n, "properties") else {}
                return {"id": node_id, "label": label, **props}
        except Exception:
            pass
        return None

    def _edges_for_node(self, node_id: str) -> list[dict[str, Any]]:
        """Return all edges connected to *node_id* (both directions)."""
        if self._is_memory:
            results: list[dict[str, Any]] = []
            for edge in self._graph.edges.values():
                if edge.src_id == node_id or edge.dst_id == node_id:
                    results.append(
                        {
                            "id": edge.edge_id,
                            "src_id": edge.src_id,
                            "dst_id": edge.dst_id,
                            "rel_type": edge.rel_type,
                            **edge.properties,
                        }
                    )
            return results
        # FalkorDB: get edges via Cypher (both outgoing and incoming)
        edges: list[dict[str, Any]] = []
        try:
            nid_int = int(node_id)
            result = self._client.execute(
                "MATCH (a)-[r]-(b) WHERE ID(a) = $nid "
                "RETURN ID(a), type(r), ID(b), r",
                {"nid": nid_int},
            )
            for row in result.result_set:
                src_id = str(row[0])
                rel_type = row[1]
                dst_id = str(row[2])
                r = row[3]
                props = dict(r.properties) if hasattr(r, "properties") else {}
                edges.append({
                    "id": f"{src_id}-{rel_type}-{dst_id}",
                    "src_id": src_id,
                    "dst_id": dst_id,
                    "rel_type": rel_type,
                    **props,
                })
        except Exception:
            pass
        return edges

    # -- public API ---------------------------------------------------------

    def neighbors(
        self, entity_id: str, relation_type: str | None = None
    ) -> list[dict[str, Any]]:
        """Return direct 1-hop neighbours, optionally filtered by relation type."""
        if self._is_memory:
            return self._graph.neighbors(entity_id, relation_type)
        # FalkorDB: query neighbours via Cypher
        try:
            nid_int = int(entity_id)
            if relation_type:
                result = self._client.execute(
                    f"MATCH (a)-[:{relation_type}]-(b) WHERE ID(a) = $nid "
                    "RETURN ID(b) AS id, labels(b)[0] AS lbl, b",
                    {"nid": nid_int},
                )
            else:
                result = self._client.execute(
                    "MATCH (a)-[]-(b) WHERE ID(a) = $nid "
                    "RETURN ID(b) AS id, labels(b)[0] AS lbl, b",
                    {"nid": nid_int},
                )
            nbrs: list[dict[str, Any]] = []
            for row in result.result_set:
                nid = str(row[0])
                label = row[1] if len(row) > 1 else ""
                n = row[2] if len(row) > 2 else None
                props = dict(n.properties) if n and hasattr(n, "properties") else {}
                nbrs.append({"id": nid, "label": label, **props})
            return nbrs
        except Exception:
            return []

    def find_paths(
        self, source_id: str, target_id: str, max_depth: int = 3,
        max_paths: int = 100,
    ) -> list[PathResult]:
        """Find all paths from *source_id* to *target_id* up to *max_depth*.

        Returns paths sorted by confidence (descending).
        """
        if self._node_dict(source_id) is None or self._node_dict(target_id) is None:
            return []

        all_paths: list[PathResult] = []
        # DFS with visited tracking per branch
        stack: list[tuple[str, list[str], list[dict[str, Any]]]] = [
            (source_id, [source_id], [])
        ]

        while stack:
            current, path_ids, path_edges = stack.pop()

            if current == target_id and len(path_ids) > 1:
                nodes = [self._node_dict(nid) for nid in path_ids]
                pr = PathResult(
                    nodes=nodes,  # type: ignore[arg-type]
                    edges=list(path_edges),
                    hops=len(path_edges),
                    confidence=0.0,
                    total_weight=0.0,
                )
                pr.confidence = self.path_confidence(pr)
                pr.total_weight = sum(
                    e.get("confidence", 1.0) for e in path_edges
                )
                all_paths.append(pr)
                if len(all_paths) >= max_paths:
                    break
                continue

            if len(path_ids) - 1 >= max_depth:
                continue

            for edge in self._edges_for_node(current):
                neighbor_id = (
                    edge["dst_id"] if edge["src_id"] == current else edge["src_id"]
                )
                if neighbor_id in path_ids:
                    continue  # cycle avoidance
                stack.append(
                    (neighbor_id, path_ids + [neighbor_id], path_edges + [edge])
                )

        all_paths.sort(key=lambda p: p.confidence, reverse=True)
        return all_paths

    def shortest_path(
        self, source_id: str, target_id: str
    ) -> Optional[PathResult]:
        """BFS shortest path between two entities."""
        if self._node_dict(source_id) is None or self._node_dict(target_id) is None:
            return None
        if source_id == target_id:
            node = self._node_dict(source_id)
            return PathResult(
                nodes=[node],  # type: ignore[list-item]
                edges=[],
                hops=0,
                confidence=1.0,
                total_weight=0.0,
            )

        visited: set[str] = {source_id}
        queue: deque[tuple[str, list[str], list[dict[str, Any]]]] = deque()
        queue.append((source_id, [source_id], []))

        while queue:
            current, path_ids, path_edges = queue.popleft()

            for edge in self._edges_for_node(current):
                neighbor_id = (
                    edge["dst_id"] if edge["src_id"] == current else edge["src_id"]
                )
                if neighbor_id in visited:
                    continue
                visited.add(neighbor_id)

                new_path_ids = path_ids + [neighbor_id]
                new_path_edges = path_edges + [edge]

                if neighbor_id == target_id:
                    nodes = [self._node_dict(nid) for nid in new_path_ids]
                    pr = PathResult(
                        nodes=nodes,  # type: ignore[arg-type]
                        edges=new_path_edges,
                        hops=len(new_path_edges),
                        confidence=0.0,
                        total_weight=sum(
                            e.get("confidence", 1.0) for e in new_path_edges
                        ),
                    )
                    pr.confidence = self.path_confidence(pr)
                    return pr

                queue.append((neighbor_id, new_path_ids, new_path_edges))

        return None

    def find_lowest_cost_path(
        self, source_id: str, target_id: str
    ) -> Optional[PathResult]:
        """Find minimum-cost path using Dijkstra's algorithm.

        Edge cost = 1.0 / confidence (lower confidence = higher cost).
        """
        if self._node_dict(source_id) is None or self._node_dict(target_id) is None:
            return None
        if source_id == target_id:
            node = self._node_dict(source_id)
            return PathResult(nodes=[node], edges=[], hops=0, confidence=1.0, total_weight=0.0)

        costs: dict[str, float] = {source_id: 0.0}
        parents: dict[str, tuple[str, dict[str, Any]]] = {}
        pq: list[tuple[float, int, str]] = [(0.0, 0, source_id)]
        visited: set[str] = set()
        counter = 0  # tie-breaker for heap

        while pq:
            cost, _, current = heapq.heappop(pq)
            if current in visited:
                continue
            visited.add(current)

            if current == target_id:
                # Reconstruct path
                path_ids: list[str] = []
                path_edges: list[dict[str, Any]] = []
                node = target_id
                while node in parents:
                    parent, edge = parents[node]
                    path_ids.append(node)
                    path_edges.append(edge)
                    node = parent
                path_ids.append(source_id)
                path_ids.reverse()
                path_edges.reverse()

                nodes = [self._node_dict(nid) for nid in path_ids]
                pr = PathResult(
                    nodes=nodes,
                    edges=path_edges,
                    hops=len(path_edges),
                    confidence=0.0,
                    total_weight=sum(e.get("confidence", 1.0) for e in path_edges),
                )
                pr.confidence = self.path_confidence(pr)
                return pr

            for edge in self._edges_for_node(current):
                neighbor = edge["dst_id"] if edge["src_id"] == current else edge["src_id"]
                if neighbor in visited:
                    continue
                edge_cost = 1.0 / max(edge.get("confidence", 1.0), 0.01)
                new_cost = cost + edge_cost

                if neighbor not in costs or new_cost < costs[neighbor]:
                    costs[neighbor] = new_cost
                    parents[neighbor] = (current, edge)
                    counter += 1
                    heapq.heappush(pq, (new_cost, counter, neighbor))

        return None

    def bidirectional_shortest_path(
        self, source_id: str, target_id: str
    ) -> Optional[PathResult]:
        """BFS from both ends, meeting in middle for faster search."""
        if self._node_dict(source_id) is None or self._node_dict(target_id) is None:
            return None
        if source_id == target_id:
            node = self._node_dict(source_id)
            return PathResult(nodes=[node], edges=[], hops=0, confidence=1.0, total_weight=0.0)

        # Forward BFS state
        fwd_visited: dict[str, tuple[list[str], list[dict[str, Any]]]] = {
            source_id: ([source_id], [])
        }
        fwd_queue: deque[str] = deque([source_id])

        # Backward BFS state
        bwd_visited: dict[str, tuple[list[str], list[dict[str, Any]]]] = {
            target_id: ([target_id], [])
        }
        bwd_queue: deque[str] = deque([target_id])

        def _expand(queue, visited, other_visited, reverse=False):
            if not queue:
                return None
            current = queue.popleft()
            cur_path, cur_edges = visited[current]

            for edge in self._edges_for_node(current):
                neighbor = edge["dst_id"] if edge["src_id"] == current else edge["src_id"]
                if neighbor in visited:
                    continue

                new_path = cur_path + [neighbor]
                new_edges = cur_edges + [edge]
                visited[neighbor] = (new_path, new_edges)

                if neighbor in other_visited:
                    # Found meeting point
                    other_path, other_edges = other_visited[neighbor]
                    if reverse:
                        full_ids = list(reversed(new_path)) + other_path[1:]
                        full_edges = list(reversed(new_edges)) + other_edges
                    else:
                        full_ids = new_path + list(reversed(other_path))[1:]
                        full_edges = new_edges + list(reversed(other_edges))
                    return (full_ids, full_edges)

                queue.append(neighbor)
            return None

        while fwd_queue or bwd_queue:
            result = _expand(fwd_queue, fwd_visited, bwd_visited, reverse=False)
            if result:
                path_ids, path_edges = result
                nodes = [self._node_dict(nid) for nid in path_ids]
                pr = PathResult(
                    nodes=nodes, edges=path_edges, hops=len(path_edges),
                    confidence=0.0,
                    total_weight=sum(e.get("confidence", 1.0) for e in path_edges),
                )
                pr.confidence = self.path_confidence(pr)
                return pr

            result = _expand(bwd_queue, bwd_visited, fwd_visited, reverse=True)
            if result:
                path_ids, path_edges = result
                nodes = [self._node_dict(nid) for nid in path_ids]
                pr = PathResult(
                    nodes=nodes, edges=path_edges, hops=len(path_edges),
                    confidence=0.0,
                    total_weight=sum(e.get("confidence", 1.0) for e in path_edges),
                )
                pr.confidence = self.path_confidence(pr)
                return pr

        return None

    def find_connections(
        self, entity_id: str, max_depth: int = 2
    ) -> list[dict[str, Any]]:
        """Find all entities reachable within *max_depth* hops.

        Returns list of ``{entity, depth, path}`` dicts.
        """
        if self._node_dict(entity_id) is None:
            return []

        visited: set[str] = {entity_id}
        results: list[dict[str, Any]] = []
        # BFS with depth tracking
        queue: deque[tuple[str, int, list[str]]] = deque()
        queue.append((entity_id, 0, [entity_id]))

        while queue:
            current, depth, path = queue.popleft()

            if depth > 0:
                entity = self._node_dict(current)
                results.append(
                    {"entity": entity, "depth": depth, "path": list(path)}
                )

            if depth >= max_depth:
                continue

            for edge in self._edges_for_node(current):
                neighbor_id = (
                    edge["dst_id"] if edge["src_id"] == current else edge["src_id"]
                )
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append(
                        (neighbor_id, depth + 1, path + [neighbor_id])
                    )

        return results

    def path_confidence(
        self, path: PathResult, decay: float | None = None
    ) -> float:
        """Compute path confidence with configurable depth decay."""
        if not path.edges:
            return 1.0

        decay_rate = decay if decay is not None else CONFIDENCE_DECAY
        confidence = 1.0
        for i, edge in enumerate(path.edges):
            edge_conf = edge.get("confidence", 1.0)
            confidence *= edge_conf * (decay_rate ** (i + 1))
        return round(confidence, 6)
