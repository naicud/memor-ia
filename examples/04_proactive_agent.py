#!/usr/bin/env python3
"""MEMORIA — Example 4: Proactive Agent

Shows profiling, pattern analysis, suggestions, and triggers.
"""

import tempfile
import time
import logging

# Silenziamo i log del recall pipeline (SQLite thread warnings in-memory)
logging.getLogger("memoria.recall.pipeline").setLevel(logging.CRITICAL)

from memoria import Memoria
from memoria.graph import GraphClient, KnowledgeGraph
from memoria.vector import VectorClient, TFIDFEmbedder
from memoria.proactive import (
    Profiler,
    PatternAnalyzer,
    SuggestionEngine,
    TriggerSystem,
    Trigger,
)
from memoria.comms import MessageBus, Event, EventType


# ── Formattazione output ──────────────────────────────────────────────────

def header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def section(title: str) -> None:
    print(f"\n--- {title} {'-' * (55 - len(title))}")


def main() -> None:
    header("MEMORIA — Proactive Agent")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Configuriamo tutti i backend
        embedder = TFIDFEmbedder(dimension=384)
        vec_client = VectorClient(db_path=None, dimension=384)
        graph_client = GraphClient(use_memory=True)
        kg = KnowledgeGraph(graph_client)

        # Inizializziamo Memoria con tutti i layer
        m = Memoria(
            project_dir=tmpdir,
            config={
                "vector_client": vec_client,
                "embedder": embedder,
                "knowledge_graph": kg,
            },
        )
        print("  Memoria initialized with all backends")

        # ── 1. Simuliamo una sessione utente ──────────────────────────
        section("1. Simulating user session")

        # Messaggi che un developer potrebbe inviare
        user_messages = [
            "How do I create a REST API with FastAPI?",
            "I need to add JWT authentication to my Python API",
            "Show me how to use SQLAlchemy with async support",
            "What's the best way to handle database migrations with Alembic?",
            "How do I write unit tests for FastAPI endpoints?",
            "I prefer pytest over unittest for testing",
            "Can you help me set up Docker for my FastAPI application?",
            "How do I configure CORS in FastAPI?",
            "I always use Black and Ruff for Python formatting",
            "Show me how to implement WebSocket connections in FastAPI",
            "What's the difference between sync and async in Python?",
            "How do I deploy my FastAPI app to Kubernetes?",
            "I need to add rate limiting to my API endpoints",
            "How do I use Pydantic models for request validation?",
            "Can you explain dependency injection in FastAPI?",
        ]

        # Il profiler analizza ogni messaggio
        profiler = m._get_profiler()
        for msg in user_messages:
            profiler.update_from_message("dev_marco", msg, role="user")
            print(f"  > {msg[:55]}...")

        print(f"\n  Processed {len(user_messages)} messages")

        # Salviamo anche come memorie
        for msg in user_messages[:5]:
            m.add(msg, user_id="dev_marco")

        # ── 2. Profilo utente ─────────────────────────────────────────
        section("2. User profile")

        profile = profiler.get_profile("dev_marco")
        print(f"  User ID:        {profile.user_id}")
        print(f"  Expertise:      {profile.expertise_level}")
        print(f"  Languages:      {', '.join(profile.primary_languages) or 'N/A'}")
        print(f"  Frameworks:     {', '.join(profile.primary_frameworks) or 'N/A'}")
        print(f"  Tools:          {', '.join(profile.preferred_tools) or 'N/A'}")
        print(f"  Interactions:   {profile.interaction_count}")
        if profile.topics_of_interest:
            print(f"  Topics:         {', '.join(profile.topics_of_interest[:5])}")
        if profile.preferences:
            print(f"  Preferences:    {profile.preferences}")

        # Livello di expertise
        expertise = profiler.detect_expertise("dev_marco")
        print(f"  Detected level: {expertise}")

        # ── 3. Analisi dei pattern ────────────────────────────────────
        section("3. Pattern analysis")

        analyzer = m._get_analyzer()

        # Registriamo le query per trovare ripetizioni
        for msg in user_messages:
            analyzer.record_query(msg)

        # Aggiungiamo query ripetute per far scattare la detection
        for _ in range(3):
            analyzer.record_query("How do I create a REST API with FastAPI?")
            analyzer.record_query("FastAPI authentication")

        # Registriamo anche azioni con contesto
        actions = [
            ("edit_file", "main.py"),
            ("run_tests", "pytest"),
            ("edit_file", "models.py"),
            ("run_tests", "pytest"),
            ("edit_file", "routes.py"),
            ("run_tests", "pytest"),
            ("docker_build", ""),
            ("deploy", "staging"),
        ]
        for action, ctx in actions:
            analyzer.record_action(action, context=ctx)

        # Cerchiamo pattern
        all_patterns = analyzer.detect_all()
        print(f"  Detected {len(all_patterns)} patterns:")
        for p in all_patterns:
            print(f"\n    Pattern: {p.name}")
            print(f"    Type:    {p.pattern_type}")
            print(f"    Desc:    {p.description[:60]}")
            print(f"    Freq:    {p.frequency}")
            print(f"    Conf:    {p.confidence:.2f}")
            if p.examples:
                print(f"    Examples: {p.examples[:2]}")

        # Cerchiamo le ripetizioni esplicitamente
        repetitions = analyzer.detect_repetitions(min_count=2)
        if repetitions:
            print(f"\n  Repetitions found: {len(repetitions)}")
            for r in repetitions[:3]:
                print(f"    - {r.description[:60]}... (x{r.frequency})")

        # Cerchiamo le sequenze
        sequences = analyzer.detect_sequences(min_length=2)
        if sequences:
            print(f"\n  Sequences found: {len(sequences)}")
            for s in sequences[:3]:
                print(f"    - {s.description[:60]}...")

        # ── 4. Suggerimenti proattivi ─────────────────────────────────
        section("4. Proactive suggestions")

        suggestions = m.suggest(
            context="working on FastAPI authentication",
            user_id="dev_marco",
        )
        if suggestions:
            for s in suggestions:
                print(f"\n    [{s.suggestion_type}] {s.title}")
                print(f"    {s.description[:70]}")
                print(f"    Priority: {s.priority:.2f} | Source: {s.source}")
                if s.action:
                    print(f"    Action: {s.action}")
        else:
            print("  No suggestions generated (profiler needs more data)")

        # ── 5. Trigger system con MessageBus ──────────────────────────
        section("5. Trigger system + MessageBus")

        bus = MessageBus()
        trigger_system = TriggerSystem(bus)

        # Teniamo traccia dei trigger attivati
        fired_triggers = []

        # Trigger personalizzato: si attiva quando si ricevono messaggi ripetuti
        def repetition_condition(data: dict) -> bool:
            return data.get("repetitions", 0) >= 3

        def repetition_action(data: dict) -> None:
            msg = f"  [TRIGGER FIRED] Repetition detected: \"{data.get('query', '?')}\" " \
                  f"repeated {data.get('repetitions', 0)} times"
            fired_triggers.append(msg)
            print(msg)

        trigger_system.register(Trigger(
            name="high_repetition",
            event_type=EventType.MESSAGE_RECEIVED.value,
            condition=repetition_condition,
            action=repetition_action,
            cooldown_s=0,  # Nessun cooldown per la demo
        ))

        # Trigger per aggiornamento memoria
        def memory_condition(data: dict) -> bool:
            return data.get("action") == "added"

        def memory_action(data: dict) -> None:
            msg = f"  [TRIGGER FIRED] New memory stored: {data.get('content', '?')[:40]}..."
            fired_triggers.append(msg)
            print(msg)

        trigger_system.register(Trigger(
            name="memory_alert",
            event_type=EventType.MEMORY_UPDATED.value,
            condition=memory_condition,
            action=memory_action,
            cooldown_s=0,
        ))

        # Avviamo il sistema (si iscrive al bus)
        trigger_system.start()

        print(f"  Registered triggers: {len(trigger_system.get_active_triggers())}")
        for t in trigger_system.get_active_triggers():
            print(f"    - {t.name} (event: {t.event_type})")

        # Pubblichiamo eventi che dovrebbero attivare i trigger
        print("\n  Publishing events...")

        bus.publish(Event(
            type=EventType.MESSAGE_RECEIVED,
            source="agent-1",
            data={"query": "FastAPI auth", "repetitions": 5},
        ))

        bus.publish(Event(
            type=EventType.MEMORY_UPDATED,
            source="agent-1",
            data={"action": "added", "content": "User prefers FastAPI for API development"},
        ))

        bus.publish(Event(
            type=EventType.MESSAGE_RECEIVED,
            source="agent-1",
            data={"query": "Docker setup", "repetitions": 1},
        ))

        # Fermiamo il trigger system
        trigger_system.stop()

        print(f"\n  Total triggers fired: {len(fired_triggers)}")
        fire_history = trigger_system.get_fire_history()
        if fire_history:
            print(f"  Fire history: {fire_history}")

        # ── 6. Insights ───────────────────────────────────────────────
        section("6. Generating insights")

        # Ingeriamo dati nel grafo per dare materiale all'insight generator
        kg.ingest_text("Marco uses FastAPI and SQLAlchemy for the payment API")
        kg.ingest_text("Marco is learning Docker and Kubernetes for deployment")
        kg.ingest_text("The team uses PostgreSQL and Redis for data storage")

        insights = m.insights(user_id="dev_marco")
        if insights:
            for ins in insights:
                print(f"\n    [{ins.insight_type}] {ins.title}")
                print(f"    {ins.description[:70]}")
                print(f"    Confidence: {ins.confidence:.2f}")
        else:
            print("  No insights generated yet (need more data diversity)")

        # ── Riepilogo ─────────────────────────────────────────────────
        section("Summary")

        print(f"  Messages processed:  {len(user_messages)}")
        print(f"  Patterns detected:   {len(all_patterns)}")
        print(f"  Suggestions:         {len(suggestions)}")
        print(f"  Triggers fired:      {len(fired_triggers)}")
        print(f"  Insights generated:  {len(insights)}")

        vec_client.close()

    print(f"\n{'=' * 60}")
    print("  Proactive agent demo complete!")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
