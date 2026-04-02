"""Temporal knowledge tracking — interaction history, trending, decay."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from .client import InMemoryGraph
from .knowledge import KnowledgeGraph

# ---------------------------------------------------------------------------
# Interaction recording
# ---------------------------------------------------------------------------


def record_interaction(
    kg: KnowledgeGraph, entity_name: str, session_id: str
) -> None:
    """Update last_seen and increment interaction_count for *entity_name*."""
    if not kg.is_memory_backend:
        kg._client.execute(
            "MATCH (n {name: $name}) "
            "SET n.last_seen = $now, "
            "n.interaction_count = COALESCE(n.interaction_count, 0) + 1",
            {"name": entity_name, "now": _now_iso()},
        )
        return

    graph: InMemoryGraph = kg._graph
    for node in graph.nodes.values():
        if node.properties.get("name", "").lower() == entity_name.lower():
            count = node.properties.get("interaction_count", 0)
            node.properties["interaction_count"] = count + 1
            node.properties["last_seen"] = _now_iso()
            # Append to timeline
            timeline: list[dict[str, str]] = node.properties.get("_timeline", [])
            timeline.append({"session_id": session_id, "timestamp": _now_iso()})
            node.properties["_timeline"] = timeline
            # Rotate timeline to prevent unbounded growth
            if len(timeline) > 1000:
                node.properties["_timeline"] = timeline[-1000:]
            break


# ---------------------------------------------------------------------------
# Timeline queries
# ---------------------------------------------------------------------------


def get_entity_timeline(
    kg: KnowledgeGraph, entity_name: str
) -> list[dict[str, str]]:
    """Get chronological history of entity interactions."""
    if not kg.is_memory_backend:
        result = kg._client.execute(
            "MATCH (n {name: $name}) RETURN n._timeline",
            {"name": entity_name},
        )
        if result.result_set:
            return result.result_set[0][0] or []
        return []

    graph: InMemoryGraph = kg._graph
    for node in graph.nodes.values():
        if node.properties.get("name", "").lower() == entity_name.lower():
            return list(node.properties.get("_timeline", []))
    return []


# ---------------------------------------------------------------------------
# Trending / stale
# ---------------------------------------------------------------------------


def get_trending_concepts(
    kg: KnowledgeGraph, days: int = 7
) -> list[dict[str, Any]]:
    """Get concepts most discussed in recent sessions."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    if not kg.is_memory_backend:
        result = kg._client.execute(
            "MATCH (n:Concept) WHERE n.last_seen >= $cutoff "
            "RETURN n ORDER BY n.interaction_count DESC LIMIT 20",
            {"cutoff": cutoff},
        )
        return [dict(r[0].properties) for r in result.result_set]

    graph: InMemoryGraph = kg._graph
    concepts: list[dict[str, Any]] = []
    for node in graph.nodes.values():
        if node.label != "Concept":
            continue
        last_seen = node.properties.get("last_seen", "")
        if last_seen >= cutoff:
            concepts.append(
                {"id": node.node_id, "label": node.label, **node.properties}
            )
    concepts.sort(key=lambda c: c.get("interaction_count", 0), reverse=True)
    return concepts[:20]


def get_trending_nodes(
    kg: KnowledgeGraph,
    days: int = 7,
    label_filter: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Get trending nodes with optional label filtering (generalized)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    if not kg.is_memory_backend:
        label_clause = f":{label_filter}" if label_filter else ""
        result = kg._client.execute(
            f"MATCH (n{label_clause}) WHERE n.last_seen >= $cutoff "
            f"RETURN n ORDER BY n.interaction_count DESC LIMIT {limit}",
            {"cutoff": cutoff},
        )
        return [dict(r[0].properties) for r in result.result_set]

    graph: InMemoryGraph = kg._graph
    nodes: list[dict[str, Any]] = []
    for node in graph.nodes.values():
        if label_filter and node.label != label_filter:
            continue
        last_seen = node.properties.get("last_seen", "")
        if last_seen >= cutoff:
            nodes.append(
                {"id": node.node_id, "label": node.label, **node.properties}
            )
    nodes.sort(key=lambda n: n.get("interaction_count", 0), reverse=True)
    return nodes[:limit]


def get_stale_entities(
    kg: KnowledgeGraph, days: int = 30
) -> list[dict[str, Any]]:
    """Get entities not interacted with for *days*."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    if not kg.is_memory_backend:
        result = kg._client.execute(
            "MATCH (n) WHERE n.last_seen < $cutoff RETURN n",
            {"cutoff": cutoff},
        )
        return [dict(r[0].properties) for r in result.result_set]

    graph: InMemoryGraph = kg._graph
    stale: list[dict[str, Any]] = []
    for node in graph.nodes.values():
        last_seen = node.properties.get("last_seen", "")
        if last_seen and last_seen < cutoff:
            stale.append(
                {"id": node.node_id, "label": node.label, **node.properties}
            )
    return stale


def archive_stale_entities(
    kg: KnowledgeGraph, days: int = 30, archive_tag: str = "archived"
) -> int:
    """Archive stale entities by tagging them. Returns count archived."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    archived = 0

    if not kg.is_memory_backend:
        raise NotImplementedError(
            "archive_stale_entities currently only supports in-memory backend"
        )

    graph: InMemoryGraph = kg._graph
    for node in graph.nodes.values():
        last_seen = node.properties.get("last_seen", "")
        if last_seen and last_seen < cutoff:
            node.properties["status"] = archive_tag
            node.properties["archived_at"] = _now_iso()
            archived += 1

    return archived


# ---------------------------------------------------------------------------
# Confidence decay
# ---------------------------------------------------------------------------


def decay_confidence(
    kg: KnowledgeGraph, half_life_days: int = 30
) -> int:
    """Apply time-based confidence decay to relationships.

    Returns the number of edges updated.
    """
    now = datetime.now(timezone.utc)
    updated = 0

    if not kg.is_memory_backend:
        raise NotImplementedError(
            "decay_confidence currently only supports in-memory backend"
        )

    graph: InMemoryGraph = kg._graph
    for edge in graph.edges.values():
        created_str = edge.properties.get("created_at", "")
        if not created_str:
            continue
        try:
            created = datetime.fromisoformat(created_str)
        except (ValueError, TypeError):
            continue

        age_days = (now - created).total_seconds() / 86400.0
        if age_days <= 0:
            continue

        original = edge.properties.get("confidence", 1.0)
        if half_life_days <= 0:
            decay_factor = 0.0
        else:
            decay_factor = math.pow(0.5, age_days / half_life_days)
        edge.properties["confidence"] = max(0.0, min(1.0, round(original * decay_factor, 4)))
        updated += 1

    return updated


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
