"""MEMORIA graph layer — knowledge graph backed by FalkorDB or in-memory store."""

from .client import GraphClient, InMemoryGraph, HAS_FALKORDB
from .schema import NodeType, RelationType, NodeSchema, GRAPH_SCHEMA, ensure_schema
from .entities import Entity, Relation, extract_entities, extract_relations
from .knowledge import KnowledgeGraph
from .temporal import (
    record_interaction,
    get_entity_timeline,
    get_trending_concepts,
    get_stale_entities,
    decay_confidence,
)
from .queries import QUERIES

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
