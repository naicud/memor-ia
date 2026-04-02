"""MEMORIA graph layer — knowledge graph backed by FalkorDB or in-memory store."""

from .client import HAS_FALKORDB, GraphClient, InMemoryGraph
from .entities import Entity, Relation, extract_entities, extract_relations
from .knowledge import KnowledgeGraph
from .queries import QUERIES
from .schema import GRAPH_SCHEMA, NodeSchema, NodeType, RelationType, ensure_schema
from .temporal import (
    decay_confidence,
    get_entity_timeline,
    get_stale_entities,
    get_trending_concepts,
    record_interaction,
)

__all__ = [
    # client
    "GraphClient",
    "InMemoryGraph",
    "HAS_FALKORDB",
    # schema
    "NodeType",
    "RelationType",
    "NodeSchema",
    "GRAPH_SCHEMA",
    "ensure_schema",
    # entities
    "Entity",
    "Relation",
    "extract_entities",
    "extract_relations",
    # knowledge
    "KnowledgeGraph",
    # temporal
    "record_interaction",
    "get_entity_timeline",
    "get_trending_concepts",
    "get_stale_entities",
    "decay_confidence",
    # queries
    "QUERIES",
]
