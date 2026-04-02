"""Relationship chain resolution and inference."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from memoria.graph.knowledge import KnowledgeGraph

from .traversal import GraphTraverser, PathResult

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class ChainType(str, Enum):
    DIRECT = "direct"
    MULTI_HOP = "multi_hop"
    CAUSAL = "causal"
    TEMPORAL = "temporal"
    INFERRED = "inferred"


@dataclass
class ChainLink:
    """A single link in a reasoning chain."""

    entity: dict[str, Any]
    relation: dict[str, Any]
    confidence: float


@dataclass
class ReasoningChain:
    """An ordered chain of links forming an inference path."""

    links: list[ChainLink]
    conclusion: str
    overall_confidence: float
    chain_type: ChainType = ChainType.MULTI_HOP
    alternatives_count: int = 0


# ---------------------------------------------------------------------------
# ChainBuilder
# ---------------------------------------------------------------------------


class ChainBuilder:
    """Build and validate reasoning chains over a knowledge graph."""

    def __init__(
        self,
        knowledge_graph: KnowledgeGraph,
        traverser: GraphTraverser | None = None,
    ) -> None:
        self._kg = knowledge_graph
        self._traverser = traverser or GraphTraverser(knowledge_graph)

    # -- public API ---------------------------------------------------------

    def build_chain(
        self, source_id: str, target_id: str
    ) -> Optional[ReasoningChain]:
        """Build an explanation chain from *source_id* to *target_id*.

        Uses the shortest path and converts each step into a
        :class:`ChainLink`.
        """
        path = self._traverser.shortest_path(source_id, target_id)
        if path is None or not path.edges:
            return None
        return self._path_to_chain(path)

    def build_alternative_chains(
        self, source_id: str, target_id: str, k: int = 3
    ) -> list[ReasoningChain]:
        """Build top-k alternative explanation chains."""
        all_paths = self._traverser.find_paths(source_id, target_id, max_depth=4)
        chains: list[ReasoningChain] = []
        for path in all_paths[:k]:
            chain = self._path_to_chain(path)
            chain.chain_type = self._infer_chain_type(path)
            chain.alternatives_count = len(all_paths)
            chains.append(chain)
        return chains

    @staticmethod
    def confidence_geometric_mean(chain: ReasoningChain) -> float:
        """Compute confidence using geometric mean (less aggressive than product)."""
        if not chain.links:
            return 1.0
        confidences = [link.confidence for link in chain.links]
        if not confidences:
            return 1.0
        import math
        product = math.prod(confidences)
        geo_mean = product ** (1.0 / len(confidences))
        depth_factor = 0.95 ** len(chain.links)
        return round(geo_mean * depth_factor, 6)

    def infer_relations(
        self, entity_id: str, max_depth: int = 2, max_chains: int = 50
    ) -> list[ReasoningChain]:
        """Find implicit relationships through multi-hop chains.

        For each entity reachable in 2+ hops, build a chain explaining the
        connection.
        """
        connections = self._traverser.find_connections(entity_id, max_depth)
        chains: list[ReasoningChain] = []
        for conn in connections:
            depth = conn["depth"]
            if depth < 2:
                continue
            target = conn["entity"]
            if target is None:
                continue
            chain = self.build_chain(entity_id, target["id"])
            if chain is not None:
                chains.append(chain)
                if len(chains) >= max_chains:
                    break
        return chains

    def validate_chain(self, chain: ReasoningChain) -> bool:
        """Check all entities and relations in the chain still exist."""
        graph = self._traverser._graph
        for link in chain.links:
            entity_id = link.entity.get("id", "")
            if entity_id not in graph.nodes:
                return False
            rel_id = link.relation.get("id", "")
            if rel_id and rel_id not in graph.edges:
                return False
        return True

    def chain_to_text(self, chain: ReasoningChain) -> str:
        """Return a human-readable explanation of the reasoning chain."""
        if not chain.links:
            return chain.conclusion

        # Confidence qualifier
        if chain.overall_confidence > 0.8:
            qualifier = "strongly"
        elif chain.overall_confidence > 0.5:
            qualifier = "moderately"
        else:
            qualifier = "weakly"

        parts: list[str] = []
        for link in chain.links:
            entity_name = link.entity.get("name", link.entity.get("id", "?"))
            rel_type = link.relation.get("rel_type", "related_to")
            if link.confidence < 0.7:
                parts.append(f"{entity_name} {rel_type} (conf: {link.confidence:.0%})")
            else:
                parts.append(f"{entity_name} {rel_type}")

        # Append the final target entity name
        last_link = chain.links[-1]
        last_edge = last_link.relation
        last_src = last_edge.get("src_id", "")
        last_dst = last_edge.get("dst_id", "")
        target_id = last_dst if last_src == last_link.entity.get("id") else last_src
        target_node = self._traverser._node_dict(target_id)
        target_name = (
            target_node.get("name", target_id) if target_node else target_id
        )

        text = " -> ".join(parts) + f" -> {target_name}"
        text += f"\nType: {chain.chain_type.value}"
        text += f"\nConclusion ({qualifier}, {chain.overall_confidence:.0%}): {chain.conclusion}"
        return text

    # -- internals ----------------------------------------------------------

    def _infer_chain_type(self, path: PathResult) -> ChainType:
        """Determine chain type from path structure."""
        if not path.edges:
            return ChainType.DIRECT
        if len(path.edges) == 1:
            return ChainType.DIRECT

        # Check for temporal relations
        temporal_rels = {"DISCUSSED", "MODIFIED", "DETECTED_IN"}
        if any(e.get("rel_type", "") in temporal_rels for e in path.edges):
            return ChainType.TEMPORAL

        # Check for causal-like relations
        causal_rels = {"USES", "WORKS_ON", "WRITTEN_IN"}
        if all(e.get("rel_type", "") in causal_rels for e in path.edges):
            return ChainType.CAUSAL

        if path.hops >= 2:
            return ChainType.INFERRED

        return ChainType.MULTI_HOP

    def _path_to_chain(self, path: PathResult) -> ReasoningChain:
        """Convert a :class:`PathResult` into a :class:`ReasoningChain`."""
        links: list[ChainLink] = []
        for i, edge in enumerate(path.edges):
            node = path.nodes[i]
            links.append(
                ChainLink(
                    entity=node,
                    relation=edge,
                    confidence=edge.get("confidence", 1.0),
                )
            )

        conclusion = self._build_conclusion(path)
        return ReasoningChain(
            links=links,
            conclusion=conclusion,
            overall_confidence=path.confidence,
        )

    def _build_conclusion(self, path: PathResult) -> str:
        """Generate a natural-language conclusion for a path."""
        if len(path.nodes) < 2:
            return ""

        segments: list[str] = []
        for i, edge in enumerate(path.edges):
            src_name = path.nodes[i].get("name", "?")
            dst_name = path.nodes[i + 1].get("name", "?")
            rel = edge.get("rel_type", "related_to")
            segments.append(f"{src_name} {rel} {dst_name}")

        first_name = path.nodes[0].get("name", "?")
        last_name = path.nodes[-1].get("name", "?")
        chain_text = ", ".join(segments)
        return f"{chain_text}, therefore {first_name} is connected to {last_name}"
