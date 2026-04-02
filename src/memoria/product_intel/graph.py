"""Grafo delle relazioni tra prodotti nell'ecosistema."""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Tuple

from .types import ProductRelationship


class ProductGraph:
    """Builds a graph of cross-product relationships and workflows.

    Records product-to-product transitions and explicit relationships,
    then exposes queries for workflow chains and complementary products.
    """

    def __init__(self, max_relationships: int = 500) -> None:
        self._lock = threading.RLock()
        self._relationships: List[ProductRelationship] = []
        self._temporal_sequences: Dict[str, List[str]] = {}  # "A->B" -> [session_ids]
        self._max_relationships = max(1, max_relationships)
        self._total_transitions: int = 0

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_transition(
        self,
        from_product: str,
        to_product: str,
        timestamp: float,  # noqa: ARG002 – kept for future use
        session_id: str = "",
    ) -> None:
        """Record a user transition from *from_product* to *to_product*."""
        if not from_product or not to_product:
            return
        if from_product == to_product:
            return

        with self._lock:
            self._total_transitions += 1
            key = f"{from_product}->{to_product}"
            sessions = self._temporal_sequences.setdefault(key, [])
            sessions.append(session_id)
            # Cap stored sessions
            if len(sessions) > 10_000:
                self._temporal_sequences[key] = sessions[-10_000:]

            # Upsert temporal_sequence relationship
            evidence = len(self._temporal_sequences[key])
            total = self._total_transitions if self._total_transitions else 1
            strength = min(1.0, evidence / total)

            rel = self._find_relationship(
                from_product, to_product, "temporal_sequence"
            )
            if rel is None:
                rel = ProductRelationship(
                    source_product=from_product,
                    target_product=to_product,
                    relationship_type="temporal_sequence",
                    strength=strength,
                    evidence_count=evidence,
                )
                self._add_relationship_internal(rel)
            else:
                rel.evidence_count = evidence
                rel.strength = strength

    def add_relationship(
        self,
        source: str,
        target: str,
        rel_type: str,
        strength: float = 0.0,
        common_features: Optional[List[str]] = None,
    ) -> ProductRelationship:
        """Add or update an explicit relationship between two products."""
        with self._lock:
            existing = self._find_relationship(source, target, rel_type)
            if existing is not None:
                existing.strength = max(0.0, min(1.0, strength))
                if common_features is not None:
                    existing.common_features = list(common_features)
                existing.evidence_count += 1
                return existing

            rel = ProductRelationship(
                source_product=source,
                target_product=target,
                relationship_type=rel_type,
                strength=max(0.0, min(1.0, strength)),
                evidence_count=1,
                common_features=list(common_features) if common_features else [],
            )
            self._add_relationship_internal(rel)
            return rel

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_relationships(
        self, product_id: Optional[str] = None
    ) -> List[ProductRelationship]:
        """Get all relationships, optionally filtered by *product_id*."""
        with self._lock:
            if product_id is None:
                return list(self._relationships)
            return [
                r
                for r in self._relationships
                if r.source_product == product_id
                or r.target_product == product_id
            ]

    def get_workflow_chains(
        self, min_strength: float = 0.3
    ) -> List[List[str]]:
        """Find common product usage chains with strength > *min_strength*.

        Returns chains of 2+ products sorted by total strength descending.
        """
        with self._lock:
            # Collect strong temporal edges
            edges: Dict[str, List[Tuple[str, float]]] = {}
            for r in self._relationships:
                if (
                    r.relationship_type == "temporal_sequence"
                    and r.strength >= min_strength
                ):
                    edges.setdefault(r.source_product, []).append(
                        (r.target_product, r.strength)
                    )

            # Build chains via DFS (max depth 10 to avoid cycles)
            chains: List[Tuple[List[str], float]] = []
            for start in edges:
                self._dfs_chains(start, [start], 0.0, edges, chains, set())

            chains.sort(key=lambda x: x[1], reverse=True)
            return [c for c, _ in chains]

    def get_complementary_products(
        self, product_id: str
    ) -> List[Tuple[str, float]]:
        """Find products commonly used alongside *product_id*."""
        with self._lock:
            scores: Dict[str, float] = {}
            for r in self._relationships:
                if r.source_product == product_id:
                    other = r.target_product
                elif r.target_product == product_id:
                    other = r.source_product
                else:
                    continue
                scores[other] = scores.get(other, 0.0) + r.strength

            return sorted(scores.items(), key=lambda x: x[1], reverse=True)

    def get_graph_summary(self) -> Dict[str, Any]:
        """Summary: nodes, edges, strongest relationships, isolated products."""
        with self._lock:
            nodes: set[str] = set()
            for r in self._relationships:
                nodes.add(r.source_product)
                nodes.add(r.target_product)

            strongest = sorted(
                self._relationships, key=lambda r: r.strength, reverse=True
            )[:5]

            return {
                "total_nodes": len(nodes),
                "total_edges": len(self._relationships),
                "strongest_relationships": [r.to_dict() for r in strongest],
            }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _find_relationship(
        self, source: str, target: str, rel_type: str
    ) -> Optional[ProductRelationship]:
        for r in self._relationships:
            if (
                r.source_product == source
                and r.target_product == target
                and r.relationship_type == rel_type
            ):
                return r
        return None

    def _add_relationship_internal(self, rel: ProductRelationship) -> None:
        if len(self._relationships) >= self._max_relationships:
            # Evict weakest relationship
            weakest = min(self._relationships, key=lambda r: r.strength)
            self._relationships.remove(weakest)
        self._relationships.append(rel)

    @staticmethod
    def _dfs_chains(
        node: str,
        path: List[str],
        total_strength: float,
        edges: Dict[str, List[Tuple[str, float]]],
        results: List[Tuple[List[str], float]],
        visited: set,
    ) -> None:
        """DFS to enumerate chains up to depth 10."""
        if len(path) > 10:
            return
        if len(path) >= 2:
            results.append((list(path), total_strength))
        visited.add(node)
        for neighbour, strength in edges.get(node, []):
            if neighbour not in visited:
                path.append(neighbour)
                ProductGraph._dfs_chains(
                    neighbour,
                    path,
                    total_strength + strength,
                    edges,
                    results,
                    visited,
                )
                path.pop()
        visited.discard(node)
