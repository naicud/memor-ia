#!/usr/bin/env python3
"""MEMORIA — Example 2: Knowledge Graph

Shows entity extraction, graph building, and relationship queries.
"""

from memoria.graph import (
    GraphClient,
    KnowledgeGraph,
    extract_entities,
    extract_relations,
    NodeType,
    record_interaction,
    get_trending_concepts,
)


# ── Formattazione output ──────────────────────────────────────────────────

def header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def section(title: str) -> None:
    print(f"\n--- {title} {'-' * (55 - len(title))}")


def main() -> None:
    header("MEMORIA — Knowledge Graph")

    # Creiamo il client in-memory (nessuna dipendenza esterna)
    client = GraphClient(use_memory=True)
    kg = KnowledgeGraph(client)

    print(f"  Backend: InMemoryGraph (no external dependencies)")
    print(f"  Initial stats: {kg.stats()}")

    # ── 1. Estrazione entità da testo ────────────────────────────────
    section("1. Entity extraction from text")

    # Paragrafi sul lavoro di un developer
    paragraphs = [
        (
            "Marco uses Python and FastAPI to build the payment service. "
            "He collaborates with Elena on the authentication module. "
            "The team deploys everything on Kubernetes using Docker containers."
        ),
        (
            "Elena specializes in React and TypeScript for the frontend. "
            "She built the dashboard using Next.js and Tailwind CSS. "
            "The frontend communicates with Marco's FastAPI backend via REST APIs."
        ),
        (
            "The team recently adopted PostgreSQL instead of MongoDB for the main database. "
            "Marco is integrating Redis for caching to improve API response times. "
            "They use GitHub Actions for CI/CD pipelines."
        ),
        (
            "Elena is learning Rust for performance-critical components. "
            "Marco prefers Docker Compose for local development. "
            "The whole team follows trunk-based development with feature flags."
        ),
    ]

    # Mostriamo prima l'estrazione grezza
    sample = paragraphs[0]
    entities = extract_entities(sample)
    print(f"\n  Sample text: \"{sample[:60]}...\"")
    print(f"  Extracted {len(entities)} entities:")
    for e in entities:
        print(f"    - {e.name} ({e.entity_type.value}, confidence: {e.confidence:.1f})")

    # ── 2. Costruzione del grafo ──────────────────────────────────────
    section("2. Building the knowledge graph")

    # Ingeriamo tutti i paragrafi nel grafo
    for i, text in enumerate(paragraphs, 1):
        result = kg.ingest_text(text)
        print(f"  Paragraph {i}: +{result['entities']} entities, "
              f"+{result['relations']} relations")

    stats = kg.stats()
    print(f"\n  Graph stats after ingestion:")
    print(f"    Total nodes: {stats['total_nodes']}")
    print(f"    Total edges: {stats['total_edges']}")

    # Mostriamo i nodi per tipo
    if "nodes_by_type" in stats:
        print(f"    Nodes by type:")
        for ntype, count in sorted(stats["nodes_by_type"].items()):
            print(f"      {ntype}: {count}")

    # ── 3. Cercare entità ─────────────────────────────────────────────
    section("3. Finding entities")

    # Cerchiamo entità specifiche
    search_terms = ["Python", "FastAPI", "Marco", "React"]
    for term in search_terms:
        found = kg.find_entity(term)
        if found:
            for e in found:
                label = e.get("label", "?")
                name = e.get("name", e.get("properties", {}).get("name", "?"))
                print(f"  Found: {name} (type: {label})")
        else:
            print(f"  \"{term}\": not found in graph")

    # ── 4. Esplorare relazioni ────────────────────────────────────────
    section("4. Exploring relationships")

    # Chi/cosa è collegato a un'entità?
    entities_to_explore = ["Python", "FastAPI", "Docker"]
    for entity_name in entities_to_explore:
        related = kg.get_related(entity_name, depth=1)
        if related:
            print(f"\n  \"{entity_name}\" is connected to:")
            for r in related[:5]:
                name = r.get("name", r.get("properties", {}).get("name", "?"))
                label = r.get("label", "?")
                print(f"    -> {name} ({label})")
        else:
            print(f"\n  \"{entity_name}\": no connections found")

    # ── 5. Profilo completo di un'entità ──────────────────────────────
    section("5. Entity profile")

    # Profilo completo di FastAPI
    profile = kg.get_entity_profile("FastAPI")
    if profile:
        print(f"  Entity: {profile.get('name', 'FastAPI')}")
        print(f"  Type: {profile.get('label', 'N/A')}")
        related_count = profile.get("related_count", 0)
        print(f"  Related entities: {related_count}")
        relations = profile.get("relations", [])
        for rel in relations[:5]:
            print(f"    - {rel}")
    else:
        print("  FastAPI profile not available")

    # ── 6. Tracking temporale ─────────────────────────────────────────
    section("6. Temporal tracking & trending concepts")

    # Registriamo interazioni simulate con alcune entità
    interaction_data = [
        ("Python", "sess_a"),
        ("Python", "sess_b"),
        ("Python", "sess_c"),
        ("FastAPI", "sess_a"),
        ("FastAPI", "sess_b"),
        ("React", "sess_c"),
        ("Docker", "sess_a"),
    ]

    for entity_name, sess_id in interaction_data:
        try:
            record_interaction(kg, entity_name, sess_id)
        except Exception:
            pass  # L'entità potrebbe non esistere nel grafo

    # Concetti di tendenza
    trending = get_trending_concepts(kg, days=30)
    if trending:
        print("  Trending concepts (last 30 days):")
        for t in trending[:5]:
            name = t.get("name", "?")
            count = t.get("interaction_count", t.get("count", 0))
            print(f"    {name}: {count} interactions")
    else:
        print("  No trending data available yet")

    # ── 7. Statistiche finali ─────────────────────────────────────────
    section("7. Final graph statistics")

    final_stats = kg.stats()
    print(f"  Nodes: {final_stats['total_nodes']}")
    print(f"  Edges: {final_stats['total_edges']}")

    print(f"\n{'=' * 60}")
    print("  Knowledge graph demo complete!")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
