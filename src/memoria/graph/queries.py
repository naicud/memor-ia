"""Pre-built Cypher query templates for common graph operations."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Query library
# ---------------------------------------------------------------------------

QUERIES: dict[str, str] = {
    # --- Person ---
    "find_person": (
        "MATCH (p:Person) WHERE p.name CONTAINS $name RETURN p"
    ),
    "person_projects": (
        "MATCH (p:Person)-[:WORKS_ON]->(proj:Project) "
        "WHERE p.name = $name RETURN proj"
    ),
    "person_tools": (
        "MATCH (p:Person)-[:USES]->(t:Tool) "
        "WHERE p.name = $name RETURN t"
    ),
    "person_preferences": (
        "MATCH (p:Person)-[:PREFERS]->(pref:Preference) "
        "WHERE p.name = $name RETURN pref"
    ),
    # --- Concept ---
    "concept_experts": (
        "MATCH (p:Person)-[k:KNOWS]->(c:Concept) "
        "WHERE c.name = $concept RETURN p, k.level"
    ),
    "related_concepts": (
        "MATCH (c1:Concept)-[r:RELATED_TO]->(c2:Concept) "
        "WHERE c1.name = $concept RETURN c2, r.weight"
    ),
    # --- Session ---
    "session_concepts": (
        "MATCH (s:Session)-[:DISCUSSED]->(c:Concept) "
        "WHERE s.id = $session_id RETURN c"
    ),
    "session_entities": (
        "MATCH (s:Session)-[:INVOLVES]->(n) "
        "WHERE s.id = $session_id RETURN n"
    ),
    # --- General ---
    "entity_neighbors": (
        "MATCH (n {name: $name})-[r]-(m) RETURN type(r), m"
    ),
    "find_by_name": (
        "MATCH (n) WHERE n.name CONTAINS $name RETURN n, labels(n)"
    ),
    # --- Stats ---
    "graph_stats": (
        "MATCH (n) RETURN labels(n)[0] AS type, count(n) AS count"
    ),
    "edge_stats": (
        "MATCH ()-[r]->() RETURN type(r) AS rel_type, count(r) AS count"
    ),
    # --- Temporal ---
    "recently_seen": (
        "MATCH (n) WHERE n.last_seen IS NOT NULL "
        "RETURN n ORDER BY n.last_seen DESC LIMIT $limit"
    ),
    "frequently_discussed": (
        "MATCH (n) WHERE n.interaction_count IS NOT NULL "
        "RETURN n ORDER BY n.interaction_count DESC LIMIT $limit"
    ),
}
