#!/usr/bin/env python3
"""MEMORIA — Example 5: Full Pipeline

Complete demo showing all MEMORIA layers working together:
core → graph → vector → recall → proactive.
"""

import tempfile
import logging

# Silenziamo i log del recall pipeline (SQLite thread warnings in-memory)
logging.getLogger("memoria.recall.pipeline").setLevel(logging.CRITICAL)

from memoria import Memoria
from memoria.graph import GraphClient, KnowledgeGraph
from memoria.vector import VectorClient, TFIDFEmbedder, VectorIndex, SemanticSearch
from memoria.proactive import Profiler, PatternAnalyzer
from memoria.recall import RecallPipeline


# ── Formattazione output ──────────────────────────────────────────────────

def header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def section(title: str) -> None:
    print(f"\n--- {title} {'-' * (55 - len(title))}")


def subsection(title: str) -> None:
    print(f"\n  >> {title}")


def main() -> None:
    header("MEMORIA — Full Pipeline Demo")

    with tempfile.TemporaryDirectory() as tmpdir:
        # ── Setup completo di tutti i backend ─────────────────────────
        section("Setup: Initializing all backends")

        embedder = TFIDFEmbedder(dimension=384)
        vec_client = VectorClient(db_path=None, dimension=384)
        vec_index = VectorIndex(vec_client, embedder)
        vec_search = SemanticSearch(vec_client, embedder)

        graph_client = GraphClient(use_memory=True)
        kg = KnowledgeGraph(graph_client)

        m = Memoria(
            project_dir=tmpdir,
            config={
                "vector_client": vec_client,
                "embedder": embedder,
                "knowledge_graph": kg,
            },
        )

        profiler = m._get_profiler()
        analyzer = m._get_analyzer()

        print("  All layers configured:")
        print("    Core:      file-based memory store")
        print("    Graph:     InMemoryGraph (knowledge graph)")
        print("    Vector:    TFIDFEmbedder + in-memory VectorClient")
        print("    Recall:    hybrid pipeline (keyword + vector + graph)")
        print("    Proactive: profiler + pattern analyzer + suggestions")

        user_id = "dev_sara"

        # ==============================================================
        # Sessione 1: React patterns
        # ==============================================================
        section("Session 1: React patterns & frontend development")

        session1_messages = [
            "I'm working on a React dashboard with TypeScript",
            "Need to implement state management with Redux Toolkit",
            "The frontend uses React Query for server state and caching",
            "I prefer functional components with hooks over class components",
            "We use Tailwind CSS for styling the UI components",
        ]

        session1_memories = []
        for msg in session1_messages:
            # Aggiorniamo il profilo con ogni messaggio
            profiler.update_from_message(user_id, msg, role="user")
            analyzer.record_query(msg)

            # Salviamo come memoria
            mem_id = m.add(msg, user_id=user_id)
            session1_memories.append(mem_id)

            # Indicizziamo nel vettore
            vec_index.index_text(mem_id, msg, metadata={"session": "1"})

            # Ingeriamo nel grafo
            kg.ingest_text(msg)

            print(f"  > {msg}")

        subsection("After Session 1")
        graph_stats = kg.stats()
        print(f"  Memories: {len(session1_memories)}")
        print(f"  Graph nodes: {graph_stats['total_nodes']}, "
              f"edges: {graph_stats['total_edges']}")

        profile = profiler.get_profile(user_id)
        print(f"  Profile — languages: {profile.primary_languages}")
        print(f"  Profile — frameworks: {profile.primary_frameworks}")
        print(f"  Profile — expertise: {profile.expertise_level}")

        # ==============================================================
        # Sessione 2: Python API development
        # ==============================================================
        section("Session 2: Python API development")

        session2_messages = [
            "Now I'm building a REST API with FastAPI and Python",
            "The API connects to PostgreSQL using SQLAlchemy ORM",
            "I need to implement JWT authentication for the API endpoints",
            "Using Pydantic for request and response validation",
            "The API serves data to the React frontend I built earlier",
        ]

        session2_memories = []
        for msg in session2_messages:
            profiler.update_from_message(user_id, msg, role="user")
            analyzer.record_query(msg)
            mem_id = m.add(msg, user_id=user_id)
            session2_memories.append(mem_id)
            vec_index.index_text(mem_id, msg, metadata={"session": "2"})
            kg.ingest_text(msg)
            print(f"  > {msg}")

        subsection("After Session 2")
        graph_stats = kg.stats()
        total_memories = len(session1_memories) + len(session2_memories)
        print(f"  Memories: {total_memories}")
        print(f"  Graph nodes: {graph_stats['total_nodes']}, "
              f"edges: {graph_stats['total_edges']}")

        profile = profiler.get_profile(user_id)
        print(f"  Profile — languages: {profile.primary_languages}")
        print(f"  Profile — frameworks: {profile.primary_frameworks}")

        # ==============================================================
        # Sessione 3: Code review & DevOps
        # ==============================================================
        section("Session 3: Code review & DevOps")

        session3_messages = [
            "I'm reviewing pull requests for the authentication module",
            "The team uses Docker Compose for local development setup",
            "We deploy to Kubernetes with Helm charts and GitHub Actions",
            "Need to set up monitoring with Prometheus and Grafana",
            "Code review checklist: tests, types, error handling, security",
        ]

        session3_memories = []
        for msg in session3_messages:
            profiler.update_from_message(user_id, msg, role="user")
            analyzer.record_query(msg)
            mem_id = m.add(msg, user_id=user_id)
            session3_memories.append(mem_id)
            vec_index.index_text(mem_id, msg, metadata={"session": "3"})
            kg.ingest_text(msg)
            print(f"  > {msg}")

        subsection("After Session 3")
        graph_stats = kg.stats()
        total_memories = (len(session1_memories) + len(session2_memories) +
                          len(session3_memories))
        print(f"  Memories: {total_memories}")
        print(f"  Graph nodes: {graph_stats['total_nodes']}, "
              f"edges: {graph_stats['total_edges']}")

        profile = profiler.get_profile(user_id)
        print(f"  Profile — languages: {profile.primary_languages}")
        print(f"  Profile — frameworks: {profile.primary_frameworks}")
        print(f"  Profile — tools: {profile.preferred_tools}")
        print(f"  Profile — expertise: {profile.expertise_level}")

        # ==============================================================
        # Hybrid Recall: stessa query, risultati da tutte le fonti
        # ==============================================================
        section("Hybrid Recall: multi-source retrieval")

        test_queries = [
            "web framework and API development",
            "deployment and infrastructure tools",
            "frontend state management",
        ]

        for query in test_queries:
            print(f"\n  Query: \"{query}\"")

            # Ricerca con il pipeline ibrido di Memoria
            results = m.search(query, user_id=user_id, limit=5)
            if results:
                for i, r in enumerate(results, 1):
                    score = r["score"]
                    content = r["memory"][:55]
                    sources = r["metadata"].get("sources", [])
                    print(f"    {i}. [{score:.3f}] {content}...")
                    if sources:
                        print(f"       Sources: {', '.join(sources)}")
            else:
                print("    (no results from hybrid recall)")

            # Confrontiamo con la ricerca semantica pura
            sem_results = vec_search.search(query, limit=3)
            if sem_results:
                print(f"    Vector-only top result: [{sem_results[0].score:.3f}] "
                      f"{sem_results[0].content[:50]}...")

        # ==============================================================
        # Knowledge Graph: relazioni tra tecnologie
        # ==============================================================
        section("Knowledge Graph: technology relationships")

        # Esploriamo le connessioni nel grafo
        explore_entities = ["Python", "React", "FastAPI", "Docker"]
        for entity_name in explore_entities:
            found = kg.find_entity(entity_name)
            if found:
                related = kg.get_related(entity_name, depth=1)
                rel_names = []
                for r in related[:4]:
                    name = r.get("name", r.get("properties", {}).get("name", "?"))
                    rel_names.append(name)
                connections = ", ".join(rel_names) if rel_names else "none"
                print(f"  {entity_name} -> [{connections}]")
            else:
                print(f"  {entity_name}: not found in graph")

        # ==============================================================
        # Proactive: suggerimenti e pattern
        # ==============================================================
        section("Proactive Intelligence")

        subsection("Detected patterns")
        patterns = analyzer.detect_all()
        if patterns:
            for p in patterns[:5]:
                print(f"  [{p.pattern_type}] {p.description[:60]}... "
                      f"(conf: {p.confidence:.2f})")
        else:
            print("  No patterns detected yet")

        subsection("Proactive suggestions")
        suggestions = m.suggest(
            context="planning the next sprint for fullstack development",
            user_id=user_id,
        )
        if suggestions:
            for s in suggestions:
                print(f"  [{s.suggestion_type}] {s.title}")
                print(f"    {s.description[:65]}...")
        else:
            print("  No suggestions available (need more interaction data)")

        subsection("Insights")
        insights = m.insights(user_id=user_id)
        if insights:
            for ins in insights:
                print(f"  [{ins.insight_type}] {ins.title}")
                print(f"    {ins.description[:65]}...")
        else:
            print("  No cross-reference insights yet")

        # ==============================================================
        # Riepilogo finale
        # ==============================================================
        section("Final Summary")

        final_graph = kg.stats()
        final_profile = profiler.get_profile(user_id)

        print(f"  Total memories stored:    {total_memories}")
        print(f"  Knowledge graph nodes:    {final_graph['total_nodes']}")
        print(f"  Knowledge graph edges:    {final_graph['total_edges']}")
        print(f"  Vector index records:     {vec_client.count()}")
        print(f"  Patterns detected:        {len(patterns)}")
        print(f"  Suggestions generated:    {len(suggestions)}")
        print(f"  Insights found:           {len(insights)}")
        print()
        print(f"  Developer profile:")
        print(f"    Languages:   {', '.join(final_profile.primary_languages)}")
        print(f"    Frameworks:  {', '.join(final_profile.primary_frameworks)}")
        print(f"    Tools:       {', '.join(final_profile.preferred_tools)}")
        print(f"    Expertise:   {final_profile.expertise_level}")
        print(f"    Interactions: {final_profile.interaction_count}")

        if "nodes_by_type" in final_graph:
            print(f"\n  Graph breakdown:")
            for ntype, count in sorted(final_graph["nodes_by_type"].items()):
                print(f"    {ntype}: {count}")

        vec_client.close()

    print(f"\n{'=' * 60}")
    print("  Full pipeline demo complete!")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
