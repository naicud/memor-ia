"""Graph schema definitions — node types, relation types, and constraints."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .client import GraphClient

# ---------------------------------------------------------------------------
# Node types
# ---------------------------------------------------------------------------


class NodeType(str, Enum):
    PERSON = "Person"
    PROJECT = "Project"
    CONCEPT = "Concept"
    PREFERENCE = "Preference"
    SESSION = "Session"
    MEMORY = "Memory"
    AGENT = "Agent"
    TOOL = "Tool"
    PATTERN = "Pattern"
    # Extended types
    ORGANIZATION = "Organization"
    LOCATION = "Location"
    DATE = "Date"
    EMAIL = "Email"


# ---------------------------------------------------------------------------
# Relation types
# ---------------------------------------------------------------------------


class RelationType(str, Enum):
    WORKS_ON = "WORKS_ON"
    KNOWS = "KNOWS"
    PREFERS = "PREFERS"
    USES = "USES"
    DISCUSSED = "DISCUSSED"
    MODIFIED = "MODIFIED"
    ABOUT = "ABOUT"
    REFERENCES = "REFERENCES"
    WRITTEN_IN = "WRITTEN_IN"
    CHILD_OF = "CHILD_OF"
    MEMBER_OF_TEAM = "MEMBER_OF_TEAM"
    DETECTED_IN = "DETECTED_IN"
    INVOLVES = "INVOLVES"
    RELATED_TO = "RELATED_TO"


# ---------------------------------------------------------------------------
# Node schema definitions
# ---------------------------------------------------------------------------


@dataclass
class NodeSchema:
    node_type: NodeType
    required_props: list[str] = field(default_factory=list)
    optional_props: list[str] = field(default_factory=list)


GRAPH_SCHEMA: dict[NodeType, NodeSchema] = {
    NodeType.PERSON: NodeSchema(
        node_type=NodeType.PERSON,
        required_props=["name"],
        optional_props=["role", "email", "team", "last_seen"],
    ),
    NodeType.PROJECT: NodeSchema(
        node_type=NodeType.PROJECT,
        required_props=["name"],
        optional_props=["path", "url", "language", "description", "last_modified"],
    ),
    NodeType.CONCEPT: NodeSchema(
        node_type=NodeType.CONCEPT,
        required_props=["name"],
        optional_props=["category", "description", "confidence", "last_seen"],
    ),
    NodeType.PREFERENCE: NodeSchema(
        node_type=NodeType.PREFERENCE,
        required_props=["name"],
        optional_props=["value", "context", "confidence"],
    ),
    NodeType.SESSION: NodeSchema(
        node_type=NodeType.SESSION,
        required_props=["id"],
        optional_props=["started_at", "ended_at", "agent_id", "summary"],
    ),
    NodeType.MEMORY: NodeSchema(
        node_type=NodeType.MEMORY,
        required_props=["id"],
        optional_props=["content", "memory_type", "created_at", "source"],
    ),
    NodeType.AGENT: NodeSchema(
        node_type=NodeType.AGENT,
        required_props=["name"],
        optional_props=["agent_id", "role", "capabilities"],
    ),
    NodeType.TOOL: NodeSchema(
        node_type=NodeType.TOOL,
        required_props=["name"],
        optional_props=["category", "version", "description"],
    ),
    NodeType.PATTERN: NodeSchema(
        node_type=NodeType.PATTERN,
        required_props=["name"],
        optional_props=["description", "frequency", "confidence", "last_seen"],
    ),
    NodeType.ORGANIZATION: NodeSchema(
        node_type=NodeType.ORGANIZATION,
        required_props=["name"],
        optional_props=["industry", "url", "description", "last_seen"],
    ),
    NodeType.LOCATION: NodeSchema(
        node_type=NodeType.LOCATION,
        required_props=["name"],
        optional_props=["country", "region", "coordinates"],
    ),
    NodeType.DATE: NodeSchema(
        node_type=NodeType.DATE,
        required_props=["name"],
        optional_props=["iso_date", "context"],
    ),
    NodeType.EMAIL: NodeSchema(
        node_type=NodeType.EMAIL,
        required_props=["name"],
        optional_props=["domain", "owner"],
    ),
}


# ---------------------------------------------------------------------------
# Schema validation helpers
# ---------------------------------------------------------------------------


def validate_node_props(
    node_type: NodeType, properties: dict[str, object]
) -> list[str]:
    """Return list of missing required properties (empty if valid)."""
    schema = GRAPH_SCHEMA.get(node_type)
    if schema is None:
        return [f"Unknown node type: {node_type}"]
    return [p for p in schema.required_props if p not in properties]


def all_allowed_props(node_type: NodeType) -> list[str]:
    """Return all allowed property names for a node type."""
    schema = GRAPH_SCHEMA.get(node_type)
    if schema is None:
        return []
    return schema.required_props + schema.optional_props


# ---------------------------------------------------------------------------
# Schema enforcement (FalkorDB indexes / constraints)
# ---------------------------------------------------------------------------

_INDEX_QUERIES: list[str] = [
    f"CREATE INDEX IF NOT EXISTS FOR (n:{nt.value}) ON (n.name)"
    for nt in NodeType
    if "name" in GRAPH_SCHEMA[nt].required_props
] + [
    f"CREATE INDEX IF NOT EXISTS FOR (n:{NodeType.SESSION.value}) ON (n.id)",
    f"CREATE INDEX IF NOT EXISTS FOR (n:{NodeType.MEMORY.value}) ON (n.id)",
]


def ensure_schema(client: GraphClient) -> None:
    """Create indexes and constraints for all node types.

    Only runs against the FalkorDB backend; silently skips for in-memory.
    """
    if client.is_memory_backend:
        return
    for query in _INDEX_QUERIES:
        client.execute(query)
