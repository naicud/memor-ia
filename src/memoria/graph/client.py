"""FalkorDB connection manager with in-memory fallback."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Optional FalkorDB import
# ---------------------------------------------------------------------------

try:
    from falkordb import FalkorDB as _FalkorDB

    HAS_FALKORDB = True
except ImportError:
    HAS_FALKORDB = False

# ---------------------------------------------------------------------------
# In-memory mock graph (used when FalkorDB is not installed)
# ---------------------------------------------------------------------------


@dataclass
class _Node:
    node_id: str
    label: str
    properties: dict[str, Any]


@dataclass
class _Edge:
    edge_id: str
    src_id: str
    dst_id: str
    rel_type: str
    properties: dict[str, Any]


class InMemoryGraph:
    """Lightweight dict-backed graph for testing and development."""

    def __init__(self) -> None:
        self.nodes: dict[str, _Node] = {}
        self.edges: dict[str, _Edge] = {}

    def add_node(self, label: str, properties: dict[str, Any] | None = None) -> str:
        node_id = str(uuid.uuid4())
        self.nodes[node_id] = _Node(
            node_id=node_id, label=label, properties=dict(properties or {})
        )
        return node_id

    def add_edge(
        self,
        src_id: str,
        dst_id: str,
        rel_type: str,
        properties: dict[str, Any] | None = None,
    ) -> str:
        if src_id not in self.nodes:
            raise KeyError(f"Source node {src_id!r} not found")
        if dst_id not in self.nodes:
            raise KeyError(f"Destination node {dst_id!r} not found")
        edge_id = str(uuid.uuid4())
        self.edges[edge_id] = _Edge(
            edge_id=edge_id,
            src_id=src_id,
            dst_id=dst_id,
            rel_type=rel_type,
            properties=dict(properties or {}),
        )
        return edge_id

    def query_nodes(
        self, label: str | None = None, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for node in self.nodes.values():
            if label and node.label != label:
                continue
            if filters and not _match_filters(node.properties, filters):
                continue
            results.append(
                {"id": node.node_id, "label": node.label, **node.properties}
            )
        return results

    def query_edges(
        self, rel_type: str | None = None, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for edge in self.edges.values():
            if rel_type and edge.rel_type != rel_type:
                continue
            if filters and not _match_filters(edge.properties, filters):
                continue
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

    def neighbors(
        self, node_id: str, rel_type: str | None = None
    ) -> list[dict[str, Any]]:
        if node_id not in self.nodes:
            raise KeyError(f"Node {node_id!r} not found")
        result: list[dict[str, Any]] = []
        for edge in self.edges.values():
            other_id: str | None = None
            if edge.src_id == node_id:
                other_id = edge.dst_id
            elif edge.dst_id == node_id:
                other_id = edge.src_id
            if other_id is None:
                continue
            if rel_type and edge.rel_type != rel_type:
                continue
            other = self.nodes[other_id]
            result.append(
                {"id": other.node_id, "label": other.label, **other.properties}
            )
        return result

    def update_node(self, node_id: str, properties: dict[str, Any]) -> None:
        if node_id not in self.nodes:
            raise KeyError(f"Node {node_id!r} not found")
        self.nodes[node_id].properties.update(properties)

    def delete_node(self, node_id: str) -> None:
        if node_id not in self.nodes:
            raise KeyError(f"Node {node_id!r} not found")
        del self.nodes[node_id]
        # Remove connected edges
        to_remove = [
            eid
            for eid, e in self.edges.items()
            if e.src_id == node_id or e.dst_id == node_id
        ]
        for eid in to_remove:
            del self.edges[eid]

    def delete_edge(self, edge_id: str) -> None:
        if edge_id not in self.edges:
            raise KeyError(f"Edge {edge_id!r} not found")
        del self.edges[edge_id]


def _match_filters(props: dict[str, Any], filters: dict[str, Any]) -> bool:
    """Check if all filter key-value pairs exist in *props*."""
    return all(props.get(k) == v for k, v in filters.items())


# ---------------------------------------------------------------------------
# GraphClient
# ---------------------------------------------------------------------------


class GraphClient:
    """Manages FalkorDB connection (embedded or remote) with in-memory fallback."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        host: str | None = None,
        port: int | None = None,
        use_memory: bool = False,
    ) -> None:
        self._db: Any = None
        self._graph: InMemoryGraph | None = None
        self._closed = False

        if use_memory or (not HAS_FALKORDB and host is None):
            self._graph = InMemoryGraph()
            return

        if not HAS_FALKORDB:
            raise ImportError(
                "FalkorDB is not installed. Install it with: "
                "pip install 'memoria[graph]'  or  pip install falkordb"
            )

        _default_port = int(os.environ.get("MEMORIA_GRAPH_PORT", "6379"))
        if host:
            self._db = _FalkorDB(host=host, port=port or _default_port)
        else:
            self._db = _FalkorDB(host="localhost", port=port or _default_port)

    # -- public API ---------------------------------------------------------

    def get_graph(self, name: str = "memoria") -> InMemoryGraph | Any:
        """Get or create a named graph."""
        if self._graph is not None:
            return self._graph
        return self._db.select_graph(name)

    def execute(self, query: str, params: dict[str, Any] | None = None) -> Any:
        """Execute a Cypher query (only for FalkorDB backend)."""
        if self._graph is not None:
            raise NotImplementedError(
                "Cypher queries are not supported on the in-memory backend. "
                "Use the InMemoryGraph API directly."
            )
        graph = self.get_graph()
        return graph.query(query, params=params)

    def close(self) -> None:
        """Close connection."""
        self._closed = True
        self._db = None
        self._graph = None

    @property
    def is_memory_backend(self) -> bool:
        return self._graph is not None

    # -- context manager ----------------------------------------------------

    def __enter__(self) -> GraphClient:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
