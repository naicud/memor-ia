"""Time-aware reasoning over the knowledge graph."""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from memoria.graph.client import InMemoryGraph
from memoria.graph.knowledge import KnowledgeGraph

# ---------------------------------------------------------------------------
# TemporalReasoner
# ---------------------------------------------------------------------------


class TemporalReasoner:
    """Time-aware queries and temporal pattern detection."""

    def __init__(self, knowledge_graph: KnowledgeGraph) -> None:
        self._kg = knowledge_graph
        self._graph: InMemoryGraph = knowledge_graph._graph  # type: ignore[assignment]

    # -- public API ---------------------------------------------------------

    def entities_active_in_range(
        self, start: str, end: str
    ) -> list[dict[str, Any]]:
        """Find entities with activity between *start* and *end* (ISO strings).

        Checks ``created_at``, ``last_seen``, and ``updated_at`` properties.
        """
        results: list[dict[str, Any]] = []
        for node in self._graph.nodes.values():
            props = node.properties
            timestamps = [
                props.get("created_at", ""),
                props.get("last_seen", ""),
                props.get("updated_at", ""),
            ]
            for ts in timestamps:
                if ts and start <= ts <= end:
                    results.append(
                        {"id": node.node_id, "label": node.label, **props}
                    )
                    break
        return results

    def relationship_timeline(
        self, entity_id: str
    ) -> list[dict[str, Any]]:
        """Chronological list of all relations for *entity_id*.

        Returns ``[{relation, connected_entity, timestamp, type}]`` sorted
        by timestamp.
        """
        timeline: list[dict[str, Any]] = []
        for edge in self._graph.edges.values():
            if edge.src_id != entity_id and edge.dst_id != entity_id:
                continue
            connected_id = (
                edge.dst_id if edge.src_id == entity_id else edge.src_id
            )
            connected = self._graph.nodes.get(connected_id)
            if connected is None:
                continue

            connected_dict = {
                "id": connected.node_id,
                "label": connected.label,
                **connected.properties,
            }
            ts = edge.properties.get("created_at", "")
            timeline.append(
                {
                    "relation": {
                        "id": edge.edge_id,
                        "src_id": edge.src_id,
                        "dst_id": edge.dst_id,
                        "rel_type": edge.rel_type,
                        **edge.properties,
                    },
                    "connected_entity": connected_dict,
                    "timestamp": ts,
                    "type": edge.rel_type,
                }
            )

        timeline.sort(key=lambda x: x["timestamp"])
        return timeline

    def recent_connections(
        self, entity_id: str, days: int = 7
    ) -> list[dict[str, Any]]:
        """Connections made in the last *days* days."""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).isoformat()

        results: list[dict[str, Any]] = []
        for edge in self._graph.edges.values():
            if edge.src_id != entity_id and edge.dst_id != entity_id:
                continue
            ts = edge.properties.get("created_at", "")
            if ts and ts >= cutoff:
                connected_id = (
                    edge.dst_id if edge.src_id == entity_id else edge.src_id
                )
                connected = self._graph.nodes.get(connected_id)
                if connected is None:
                    continue
                results.append(
                    {
                        "id": connected.node_id,
                        "label": connected.label,
                        "rel_type": edge.rel_type,
                        "timestamp": ts,
                        **connected.properties,
                    }
                )
        return results

    def detect_patterns(
        self, entity_id: str
    ) -> list[dict[str, Any]]:
        """Detect temporal patterns for *entity_id*.

        Pattern types:
        - ``recurring``: same entity connected multiple times
        - ``burst``: many connections in a short period
        - ``decay``: connections becoming less frequent
        """
        timeline = self.relationship_timeline(entity_id)
        if not timeline:
            return []

        patterns: list[dict[str, Any]] = []

        # --- recurring: same entity connected multiple times ---------------
        entity_counts: Counter[str] = Counter()
        entity_names: dict[str, str] = {}
        for entry in timeline:
            cid = entry["connected_entity"]["id"]
            entity_counts[cid] += 1
            entity_names[cid] = entry["connected_entity"].get("name", cid)

        for cid, count in entity_counts.items():
            if count >= 2:
                patterns.append(
                    {
                        "pattern_type": "recurring",
                        "description": (
                            f"Entity '{entity_names[cid]}' connected "
                            f"{count} times"
                        ),
                        "frequency": count,
                        "entities": [cid],
                    }
                )

        # --- burst: many connections in a short period (24h window) --------
        timestamps = _parse_timestamps(timeline)
        if len(timestamps) >= 3:
            window = timedelta(hours=24)
            for i in range(len(timestamps)):
                burst_entities: list[str] = []
                for j in range(i, len(timestamps)):
                    if timestamps[j] - timestamps[i] <= window:
                        burst_entities.append(
                            timeline[j]["connected_entity"]["id"]
                        )
                    else:
                        break
                if len(burst_entities) >= 3:
                    patterns.append(
                        {
                            "pattern_type": "burst",
                            "description": (
                                f"{len(burst_entities)} connections within "
                                f"24 hours"
                            ),
                            "frequency": len(burst_entities),
                            "entities": burst_entities,
                        }
                    )
                    break  # report first burst only

        # --- burst: multi-day (7-day window) ---
        if len(timestamps) >= 5:
            week_window = timedelta(days=7)
            for i in range(len(timestamps)):
                week_entities: list[str] = []
                for j in range(i, len(timestamps)):
                    if timestamps[j] - timestamps[i] <= week_window:
                        week_entities.append(
                            timeline[j]["connected_entity"]["id"]
                        )
                    else:
                        break
                if len(week_entities) >= 5:
                    patterns.append(
                        {
                            "pattern_type": "burst",
                            "description": (
                                f"{len(week_entities)} connections within "
                                f"7 days (weekly burst)"
                            ),
                            "frequency": len(week_entities),
                            "entities": week_entities,
                        }
                    )
                    break

        # --- decay: connections becoming less frequent ---------------------
        if len(timestamps) >= 3:
            gaps = [
                (timestamps[i + 1] - timestamps[i]).total_seconds()
                for i in range(len(timestamps) - 1)
            ]
            increasing = all(
                gaps[i] <= gaps[i + 1] for i in range(len(gaps) - 1)
            )
            if increasing and gaps[-1] > gaps[0]:
                patterns.append(
                    {
                        "pattern_type": "decay",
                        "description": "Connections becoming less frequent over time",
                        "frequency": len(gaps),
                        "entities": [
                            entry["connected_entity"]["id"] for entry in timeline
                        ],
                    }
                )

        return patterns

    def decay_score(
        self, entity_id: str, reference_time: str | None = None,
        half_life_days: float = 30.0,
    ) -> float:
        """Compute time-based relevance decay with configurable half-life.

        Returns a value in ``(0, 1]``.
        """
        node = self._graph.nodes.get(entity_id)
        if node is None:
            return 0.0

        ref = (
            datetime.fromisoformat(reference_time)
            if reference_time
            else datetime.now(timezone.utc)
        )

        last_seen = node.properties.get(
            "last_seen", node.properties.get("created_at", "")
        )
        if not last_seen:
            return 0.0

        try:
            last_dt = datetime.fromisoformat(last_seen)
        except (ValueError, TypeError):
            return 0.0

        age_days = (ref - last_dt).total_seconds() / 86400.0
        if age_days <= 0:
            return 1.0

        if half_life_days <= 0:
            return 0.0

        return round(math.pow(0.5, age_days / half_life_days), 6)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_timestamps(
    timeline: list[dict[str, Any]],
) -> list[datetime]:
    """Extract and parse timestamps from a timeline, skipping invalid ones."""
    parsed: list[datetime] = []
    for entry in timeline:
        ts = entry.get("timestamp", "")
        if not ts:
            continue
        try:
            parsed.append(datetime.fromisoformat(ts))
        except (ValueError, TypeError):
            continue
    return parsed
