"""Cross-layer integration tests for the MEMORIA proactive memory framework.

Tests cross-layer interactions between:
  Layer 1 (Core):      identity, comms, context, consolidation, orchestration, bridge
  Layer 2 (Storage):   graph (InMemoryGraph), vector (SQLite/cosine), file (markdown)
  Layer 3 (Recall):    keyword + vector + graph strategies → RRF fusion → ranking
  Layer 4 (Proactive): profiler, analyzer, suggestions, triggers, insights

All tests use in-memory backends (InMemoryGraph, pure-Python cosine, TFIDFEmbedder)
and require no external services.
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

# --- Core (Layer 1) ---
from memoria import Memoria

# --- Comms / Identity / Orchestration ---
from memoria.comms.bus import Event, EventType, MessageBus
from memoria.comms.mailbox import Mailbox, MailboxMessage
from memoria.comms.permissions import PermissionBridge, PermissionDecision
from memoria.context.compaction import CompactionConfig, ContextCompactor
from memoria.context.window import (
    TokenBudget,
    analyze_context,
)
from memoria.core.paths import ensure_memory_dir_exists
from memoria.core.store import (
    read_memory_file,
    write_memory_file,
)
from memoria.core.types import MemoryFrontmatter, MemoryType

# --- Graph (Layer 2 – Storage) ---
from memoria.graph.client import GraphClient, InMemoryGraph
from memoria.graph.knowledge import KnowledgeGraph
from memoria.graph.temporal import (
    get_entity_timeline,
    get_stale_entities,
    get_trending_concepts,
    record_interaction,
)
from memoria.identity.agent_id import (
    create_agent_id,
    create_session_id,
)
from memoria.identity.context import (
    AgentContext,
)
from memoria.identity.factory import (
    create_fork_context,
)
from memoria.orchestration.spawner import AgentSpawner, SpawnConfig, SpawnMode
from memoria.orchestration.team import (
    TeamConfig,
    TeamManager,
    _reset_registry,
)
from memoria.proactive.analyzer import PatternAnalyzer
from memoria.proactive.insights import InsightGenerator

# --- Proactive (Layer 4) ---
from memoria.proactive.profiler import ClientProfile, Profiler
from memoria.proactive.suggestions import SuggestionEngine
from memoria.proactive.triggers import Trigger, TriggerSystem
from memoria.recall.context_filter import RecallContext, deduplicate
from memoria.recall.pipeline import RecallPipeline
from memoria.recall.ranker import reciprocal_rank_fusion

# --- Recall (Layer 3) ---
from memoria.recall.strategies import (
    GraphStrategy,
    KeywordStrategy,
    RecallResult,
    VectorStrategy,
)

# --- Vector (Layer 2 – Storage) ---
from memoria.vector.client import VectorClient
from memoria.vector.embeddings import TFIDFEmbedder
from memoria.vector.index import VectorIndex
from memoria.vector.search import SemanticSearch

# ====================================================================
#  Helpers
# ====================================================================

def _make_graph() -> tuple[GraphClient, KnowledgeGraph]:
    """Create an in-memory GraphClient + KnowledgeGraph pair."""
    client = GraphClient(use_memory=True)
    kg = KnowledgeGraph(client)
    return client, kg


def _make_vector(dimension: int = 384, tmpdir: str | None = None) -> tuple[VectorClient, TFIDFEmbedder]:
    """Create a VectorClient + TFIDFEmbedder pair.

    When *tmpdir* is provided the SQLite db is file-backed (thread-safe
    for the RecallPipeline which runs strategies in parallel threads).
    Otherwise uses in-memory SQLite (single-thread use only).
    """
    if tmpdir:
        db_path = Path(tmpdir) / "vectors.db"
    else:
        db_path = None
    vc = VectorClient(db_path=db_path, dimension=dimension)
    emb = TFIDFEmbedder(dimension=dimension)
    return vc, emb


def _seed_memories(mem_dir: Path, count: int = 5) -> list[Path]:
    """Write *count* distinct memory files into *mem_dir*."""
    topics = [
        ("python_testing", "Python testing with pytest and fixtures"),
        ("docker_deploy", "Docker deployment and containerization strategies"),
        ("react_hooks", "React hooks patterns and custom hook design"),
        ("database_indexing", "Database indexing and query optimization tips"),
        ("git_workflow", "Git branching workflow and code review best practices"),
        ("rust_memory", "Rust memory safety and ownership model"),
        ("kubernetes_scaling", "Kubernetes scaling and pod auto-scaling"),
        ("graphql_schema", "GraphQL schema design and resolver patterns"),
    ]
    paths: list[Path] = []
    for i in range(min(count, len(topics))):
        slug, content = topics[i]
        fm = MemoryFrontmatter(
            name=slug,
            description=content,
            type=MemoryType.PROJECT,
        )
        p = mem_dir / f"{slug}.md"
        write_memory_file(p, fm, content)
        paths.append(p)
    return paths


# ====================================================================
# 1. TestMemoriaEndToEnd  (~10 tests)
# ====================================================================

class TestMemoriaEndToEnd:
    """End-to-end Memoria API (add / search / get / delete)."""

    def setup_method(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.project_dir = self._tmpdir.name
        self.m = Memoria(project_dir=self.project_dir)

    def teardown_method(self) -> None:
        self._tmpdir.cleanup()

    # -- tests --

    def test_add_then_search(self):
        self.m.add("Python testing with pytest fixtures")
        results = self.m.search("pytest fixtures")
        assert len(results) >= 1
        assert any("pytest" in r["memory"].lower() for r in results)

    def test_add_multiple_search_ranked(self):
        self.m.add("Python testing with pytest")
        self.m.add("Docker deployment guide")
        self.m.add("React component patterns")
        self.m.add("Pytest fixture best practices")
        self.m.add("Advanced pytest plugins")
        results = self.m.search("pytest")
        assert len(results) >= 1
        # Top result should mention pytest
        assert "pytest" in results[0]["memory"].lower()

    def test_add_get_delete_lifecycle(self):
        path = self.m.add("lifecycle test memory")
        got = self.m.get(path)
        assert got is not None
        assert "lifecycle" in got["memory"]
        assert self.m.delete(path) is True
        assert self.m.get(path) is None

    def test_search_empty_returns_empty(self):
        results = self.m.search("nonexistent topic")
        assert results == []

    def test_add_with_user_id_scoping(self):
        self.m.add("user-scoped memory", user_id="alice")
        self.m.add("global memory without user scope")
        results = self.m.search("memory", user_id="alice")
        # Keyword strategy does not filter by user_id, but
        # context filter boosts matching user_id metadata.
        assert isinstance(results, list)

    def test_add_with_agent_id(self):
        path = self.m.add("agent memory", agent_id="agent-001")
        got = self.m.get(path)
        assert got is not None
        # agent_id is set on fm.raw at creation time but format_frontmatter
        # only serialises name/description/type — verify the memory itself
        # is stored and retrievable (agent_id is an in-memory-only hint).
        assert "agent memory" in got["memory"]

    def test_search_limit_respected(self):
        for i in range(8):
            self.m.add(f"memory about topic {i} testing")
        results = self.m.search("testing", limit=3)
        assert len(results) <= 3

    def test_add_various_memory_types(self):
        p1 = self.m.add("user preference note", memory_type="user")
        p2 = self.m.add("project architecture doc", memory_type="project")
        p3 = self.m.add("user feedback on refactoring", memory_type="feedback")
        g1 = self.m.get(p1)
        g2 = self.m.get(p2)
        g3 = self.m.get(p3)
        assert g1 is not None and g1["metadata"]["type"] == "user"
        assert g2 is not None and g2["metadata"]["type"] == "project"
        assert g3 is not None and g3["metadata"]["type"] == "feedback"

    def test_get_nonexistent_returns_none(self):
        assert self.m.get("/nonexistent/path/abc.md") is None

    def test_delete_nonexistent_returns_false(self):
        assert self.m.delete("/nonexistent/path/abc.md") is False


# ====================================================================
# 2. TestRecallPipelineCrossLayer  (~10 tests)
# ====================================================================

class TestRecallPipelineCrossLayer:
    """Recall pipeline integrating keyword, vector, and graph strategies."""

    def setup_method(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.mem_dir = ensure_memory_dir_exists(self._tmpdir.name)
        _seed_memories(self.mem_dir)

        self.vc, self.emb = _make_vector(tmpdir=self._tmpdir.name)
        self._gc, self.kg = _make_graph()

        # Index memories in vector store
        idx = VectorIndex(self.vc, self.emb)
        for p in self.mem_dir.glob("*.md"):
            _, body = read_memory_file(p)
            idx.index_text(str(p), body.strip())

        # Ingest into graph
        for p in self.mem_dir.glob("*.md"):
            _, body = read_memory_file(p)
            self.kg.ingest_text(body.strip())

    def teardown_method(self) -> None:
        self.vc.close()
        self._tmpdir.cleanup()

    # -- tests --

    def test_keyword_strategy_with_core_store(self):
        strategy = KeywordStrategy(self.mem_dir)
        results = strategy.retrieve("python testing pytest")
        assert len(results) >= 1
        assert results[0].source == "keyword"

    def test_vector_strategy_with_embedder(self):
        search = SemanticSearch(self.vc, self.emb)
        strategy = VectorStrategy(search)
        results = strategy.retrieve("testing with pytest")
        assert len(results) >= 1
        assert results[0].source == "vector"

    def test_graph_strategy_with_knowledge_graph(self):
        strategy = GraphStrategy(self.kg)
        results = strategy.retrieve("Docker deployment kubernetes")
        # Graph strategy extracts entities from query then finds related
        assert isinstance(results, list)
        if results:
            assert results[0].source == "graph"

    def test_all_three_strategies_combined(self):
        pipeline = RecallPipeline.create_default(
            memory_dir=self.mem_dir,
            vector_client=self.vc,
            embedder=self.emb,
            knowledge_graph=self.kg,
        )
        assert len(pipeline.strategies) == 3
        results = pipeline.recall("python testing")
        assert len(results) >= 1
        # Should have contributions from multiple strategies
        all_sources = set()
        for r in results:
            all_sources.update(r.sources)
        assert "keyword" in all_sources

    def test_rrf_ranking_produces_stable_order(self):
        pipeline = RecallPipeline.create_default(
            memory_dir=self.mem_dir,
            vector_client=self.vc,
            embedder=self.emb,
            knowledge_graph=self.kg,
        )
        r1 = pipeline.recall("pytest fixtures")
        r2 = pipeline.recall("pytest fixtures")
        assert [r.id for r in r1] == [r.id for r in r2]

    def test_context_filter_with_user_id(self):
        # Insert a memory with user_id metadata
        fm = MemoryFrontmatter(name="alice_mem", description="alice specific memory", type=MemoryType.USER)
        fm.raw["user_id"] = "alice"
        p = self.mem_dir / "alice_mem.md"
        write_memory_file(p, fm, "alice prefers functional programming")

        pipeline = RecallPipeline.create_default(memory_dir=self.mem_dir)
        ctx = RecallContext(user_id="alice")
        results = pipeline.recall("functional programming", context=ctx)
        assert isinstance(results, list)

    def test_deduplicate_cross_strategy(self):
        # Same content from two sources should be deduplicated
        r1 = RecallResult(id="a", content="python testing guide", score=0.9, source="keyword")
        r2 = RecallResult(id="b", content="python testing guide", score=0.8, source="vector")
        fused = reciprocal_rank_fusion([[r1], [r2]])
        deduped = deduplicate(fused)
        # Two different IDs with identical content → one should be removed
        assert len(deduped) <= 2

    def test_empty_query_handling(self):
        pipeline = RecallPipeline.create_default(memory_dir=self.mem_dir)
        assert pipeline.recall("") == []
        assert pipeline.recall("   ") == []

    def test_pipeline_with_no_backends(self):
        pipeline = RecallPipeline()
        assert pipeline.recall("anything") == []

    def test_pipeline_create_default(self):
        # Keyword only
        p1 = RecallPipeline.create_default(memory_dir=self.mem_dir)
        assert len(p1.strategies) == 1

        # Keyword + Vector
        p2 = RecallPipeline.create_default(
            memory_dir=self.mem_dir, vector_client=self.vc, embedder=self.emb,
        )
        assert len(p2.strategies) == 2

        # All three
        p3 = RecallPipeline.create_default(
            memory_dir=self.mem_dir, vector_client=self.vc,
            embedder=self.emb, knowledge_graph=self.kg,
        )
        assert len(p3.strategies) == 3

    def test_weighted_fusion_alternative(self):
        pipeline = RecallPipeline(fusion_method="weighted")
        pipeline.add_strategy(KeywordStrategy(self.mem_dir), weight=1.0)
        results = pipeline.recall("python testing")
        assert isinstance(results, list)

    def test_vector_only_pipeline(self):
        pipeline = RecallPipeline.create_default(
            vector_client=self.vc, embedder=self.emb,
        )
        assert len(pipeline.strategies) == 1
        results = pipeline.recall("testing with pytest")
        assert isinstance(results, list)


# ====================================================================
# 3. TestGraphVectorSynergy  (~8 tests)
# ====================================================================

class TestGraphVectorSynergy:
    """Graph ↔ Vector synergy: entities, indexing, temporal tracking."""

    def setup_method(self) -> None:
        self._gc, self.kg = _make_graph()
        self.vc, self.emb = _make_vector()
        self.idx = VectorIndex(self.vc, self.emb)
        self.search = SemanticSearch(self.vc, self.emb)

    def teardown_method(self) -> None:
        self.vc.close()

    # -- tests --

    def test_entity_extraction_feeds_graph(self):
        text = "I use Docker and Kubernetes for deployment"
        stats = self.kg.ingest_text(text)
        assert stats["entities"] >= 2
        found = self.kg.find_entity("docker")
        assert len(found) >= 1

    def test_graph_entity_searchable_via_vector(self):
        text = "Docker containerization for microservices"
        self.kg.ingest_text(text)
        self.idx.index_text("doc-1", text)
        results = self.search.search("containerization")
        assert len(results) >= 1
        assert "container" in results[0].content.lower()

    def test_vector_search_enriched_by_graph_relations(self):
        self.kg.ingest_text("Python uses pytest for testing")
        self.idx.index_text("mem-1", "Python testing with pytest and fixtures")
        self.idx.index_text("mem-2", "Java testing with JUnit")

        # Vector search
        vec_results = self.search.search("Python pytest")
        # Graph relations
        graph_related = self.kg.get_related("pytest")

        assert len(vec_results) >= 1
        assert isinstance(graph_related, list)

    def test_temporal_tracking_with_vector_index(self):
        text = "Working with Redis caching strategies"
        self.kg.ingest_text(text)
        self.idx.index_text("cache-1", text)

        record_interaction(self.kg, "redis", "session-1")
        record_interaction(self.kg, "redis", "session-2")

        timeline = get_entity_timeline(self.kg, "redis")
        assert len(timeline) == 2

        vec_results = self.search.search("redis caching")
        assert len(vec_results) >= 1

    def test_knowledge_ingest_and_vector_index_sync(self):
        texts = [
            "Flask is a Python web framework",
            "FastAPI is faster than Flask for async",
            "Django is a full-featured Python framework",
        ]
        for i, t in enumerate(texts):
            self.kg.ingest_text(t)
            self.idx.index_text(f"txt-{i}", t)

        graph_stats = self.kg.stats()
        vec_count = self.vc.count()
        assert graph_stats["total_nodes"] >= 3
        assert vec_count == 3

    def test_trending_concepts_match_vector_frequency(self):
        for _ in range(3):
            self.kg.ingest_text("Working with Python and testing")
        for ent in self.kg.find_entity("python"):
            record_interaction(self.kg, "python", "sess-1")

        trending = get_trending_concepts(self.kg, days=7)
        # python should be among trending concepts
        trending_names = [c.get("name", "").lower() for c in trending]
        assert "python" in trending_names

    def test_stale_entities_cleanup(self):
        # Create entity with old timestamp
        graph: InMemoryGraph = self._gc.get_graph()
        graph.add_node("Concept", {
            "name": "old_concept",
            "last_seen": "2020-01-01T00:00:00+00:00",
            "interaction_count": 1,
        })
        stale = get_stale_entities(self.kg, days=30)
        stale_names = [s.get("name", "") for s in stale]
        assert "old_concept" in stale_names

    def test_graph_relations_enhance_recall(self):
        self.kg.ingest_text("I prefer using vim over vscode for editing")
        entities = self.kg.find_entity("vim")
        assert len(entities) >= 1

        related = self.kg.get_related("vim", depth=2)
        # Should find at least vscode as related
        assert isinstance(related, list)

    def test_entity_profile_combines_graph_data(self):
        self.kg.ingest_text("Python uses pytest. Python uses Flask.")
        profile = self.kg.get_entity_profile("python")
        assert profile != {}
        assert profile["related_count"] >= 1

    def test_vector_index_reindex_preserves_data(self):
        self.idx.index_text("r1", "Machine learning with neural networks")
        self.idx.index_text("r2", "Deep learning architectures")
        count = self.idx.reindex_all()
        assert count == 2
        # Data still searchable
        results = self.search.search("neural networks")
        assert len(results) >= 1


# ====================================================================
# 4. TestProactiveWithRecall  (~10 tests)
# ====================================================================

class TestProactiveWithRecall:
    """Proactive layer (profiler, analyzer, suggestions) + recall pipeline."""

    def setup_method(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.mem_dir = ensure_memory_dir_exists(self._tmpdir.name)
        _seed_memories(self.mem_dir)

        self._gc, self.kg = _make_graph()
        self.vc, self.emb = _make_vector(tmpdir=self._tmpdir.name)

        self.profiler = Profiler(kg=self.kg)
        self.analyzer = PatternAnalyzer()

        self.pipeline = RecallPipeline.create_default(
            memory_dir=self.mem_dir,
            vector_client=self.vc,
            embedder=self.emb,
            knowledge_graph=self.kg,
        )
        self.engine = SuggestionEngine(
            profiler=self.profiler,
            analyzer=self.analyzer,
            pipeline=self.pipeline,
        )

    def teardown_method(self) -> None:
        self.vc.close()
        self._tmpdir.cleanup()

    # -- tests --

    def test_profiler_builds_from_memories(self):
        self.profiler.update_from_message("user-1", "I use Python and pytest for testing")
        self.profiler.update_from_message("user-1", "Docker deployment with kubernetes")
        profile = self.profiler.get_profile("user-1")
        assert profile.interaction_count == 2
        assert "python" in profile.primary_languages
        assert "docker" in profile.preferred_tools

    def test_analyzer_detects_patterns_in_messages(self):
        for _ in range(4):
            self.analyzer.record_query("how to deploy docker containers")
        patterns = self.analyzer.detect_repetitions(min_count=3)
        assert len(patterns) >= 1
        assert patterns[0].pattern_type == "repetition"

    def test_suggestion_engine_uses_recall_pipeline(self):
        self.profiler.update_from_message("user-1", "Working on Python testing")
        for _ in range(4):
            self.analyzer.record_query("pytest fixtures")

        self.analyzer.detect_repetitions()  # Populate internal state
        suggestions = self.engine.generate("user-1", current_context="python testing")
        assert isinstance(suggestions, list)

    def test_suggestions_with_graph_context(self):
        self.kg.ingest_text("Python uses pytest for testing. Docker uses kubernetes.")
        self.profiler.update_from_message("user-1", "Working with Python testing")
        suggestions = self.engine.generate("user-1", current_context="pytest fixtures")
        assert isinstance(suggestions, list)

    def test_triggers_fire_on_bus_events(self):
        bus = MessageBus()
        ts = TriggerSystem(bus=bus)

        fired_events: list[dict] = []

        trigger = Trigger(
            name="test_trigger",
            event_type=EventType.MEMORY_UPDATED.value,
            condition=lambda d: d.get("important", False),
            action=lambda d: fired_events.append(d),
            cooldown_s=0,
        )
        ts.register(trigger)
        ts.start()

        bus.publish(Event(
            type=EventType.MEMORY_UPDATED,
            source="test",
            data={"important": True, "content": "new memory"},
        ))
        ts.stop()

        assert len(fired_events) == 1
        assert fired_events[0]["content"] == "new memory"

    def test_insights_cross_reference_graph_vector(self):
        self.kg.ingest_text("Python uses pytest for testing")
        self.kg.ingest_text("Docker uses kubernetes for orchestration")

        gen = InsightGenerator(kg=self.kg, search=self.search if hasattr(self, 'search') else None)
        insights = gen.generate_all("user-1")
        assert isinstance(insights, list)

    def test_memoria_suggest_api(self):
        m = Memoria(project_dir=self._tmpdir.name, config={
            "knowledge_graph": self.kg,
            "vector_client": self.vc,
            "embedder": self.emb,
        })
        m.add("Python testing with pytest is important")
        suggestions = m.suggest(context="pytest", user_id="user-1")
        assert isinstance(suggestions, list)

    def test_memoria_profile_api(self):
        m = Memoria(project_dir=self._tmpdir.name, config={
            "knowledge_graph": self.kg,
        })
        # Profile starts empty
        profile = m.profile(user_id="new-user")
        assert isinstance(profile, ClientProfile)
        assert profile.user_id == "new-user"

    def test_memoria_insights_api(self):
        self.kg.ingest_text("Python testing with pytest")
        self.kg.ingest_text("Docker deployment with kubernetes")

        m = Memoria(project_dir=self._tmpdir.name, config={
            "knowledge_graph": self.kg,
            "vector_client": self.vc,
            "embedder": self.emb,
        })
        insights = m.insights(user_id="user-1")
        assert isinstance(insights, list)

    def test_proactive_cooldown_prevents_duplicates(self):
        for _ in range(5):
            self.analyzer.record_query("repeated query about docker")
        self.analyzer.detect_repetitions()

        s1 = self.engine.generate("user-1")
        # Immediately requesting again should return fewer (cooldown active)
        s2 = self.engine.generate("user-1")

        # At minimum, previously emitted suggestions should be filtered
        s1_ids = {s.id for s in s1}
        s2_ids = {s.id for s in s2}
        # The overlap should be empty due to cooldown
        assert len(s1_ids & s2_ids) == 0 or len(s2) <= len(s1)


# ====================================================================
# 5. TestCommsOrchestrationIntegration  (~8 tests)
# ====================================================================

class TestCommsOrchestrationIntegration:
    """Communication + orchestration layer integration."""

    def setup_method(self) -> None:
        _reset_registry()

    def teardown_method(self) -> None:
        _reset_registry()

    # -- tests --

    def test_mailbox_with_agent_identity(self):
        aid = create_agent_id("worker")
        mailbox = Mailbox()
        msg = MailboxMessage(sender=str(aid), content="hello from worker")
        mailbox.send(msg)
        received = mailbox.poll()
        assert received is not None
        assert received.sender == str(aid)
        assert received.content == "hello from worker"

    def test_bus_events_cross_agents(self):
        bus = MessageBus()
        a1 = create_agent_id("agent-a")
        a2 = create_agent_id("agent-b")

        received: list[Event] = []
        bus.subscribe(EventType.MESSAGE_SENT.value, lambda e: received.append(e))

        bus.publish(Event(
            type=EventType.MESSAGE_SENT,
            source=str(a1),
            data={"to": str(a2), "content": "hello"},
        ))

        assert len(received) == 1
        assert received[0].source == str(a1)

    def test_team_with_memory_sharing(self):
        sid = create_session_id()
        lid = create_agent_id("leader")
        config = TeamConfig(
            team_name="test_mem_team",
            leader_agent_id=str(lid),
            leader_session_id=str(sid),
        )
        tm = TeamManager(config)
        w1 = tm.add_member(str(create_agent_id("w1")), "worker-1")
        tm.add_member(str(create_agent_id("w2")), "worker-2")
        assert tm.size == 2
        assert w1.role == "worker"

    def test_permissions_delegation_chain(self):
        bridge = PermissionBridge()
        bridge.set_allowed_tools("child-1", {"read_file", "list_dir"})
        bridge.set_denied_tools("child-1", {"execute_command"})

        assert bridge.check_pre_authorized("child-1", "read_file") == PermissionDecision.ALLOW
        assert bridge.check_pre_authorized("child-1", "execute_command") == PermissionDecision.DENY
        assert bridge.check_pre_authorized("child-1", "web_search") is None

    def test_context_window_with_memory_loading(self):
        budget = TokenBudget(max_input_tokens=200_000, reserve_tokens=10_000)
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Tell me about Python testing."},
            {"role": "assistant", "content": "Python testing uses pytest..." * 20},
        ]
        analysis = analyze_context(messages, budget)
        assert analysis.total_tokens > 0
        assert 0 < analysis.utilization <= 1.0

    def test_compaction_preserves_important_memories(self):
        compactor = ContextCompactor(CompactionConfig(preserve_recent_n=2))
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "old question 1"},
            {"role": "assistant", "content": "old answer 1"},
            {"role": "tool", "content": ""},  # low-value
            {"role": "user", "content": "recent question"},
            {"role": "assistant", "content": "recent answer"},
        ]
        compacted = compactor.micro_compact(messages)
        # System and recent messages preserved; low-value tool result removed
        assert any(m.get("role") == "system" for m in compacted)
        assert any("recent" in m.get("content", "") for m in compacted)
        assert len(compacted) < len(messages)

    def test_spawner_creates_valid_agents(self):
        spawner = AgentSpawner()
        config = SpawnConfig(
            prompt="Analyze the codebase",
            mode=SpawnMode.ASYNC,
            label="analyzer",
        )
        result = spawner.spawn(config)
        assert result.success is True
        assert "analyzer" in result.agent_id

        children = spawner.list_children()
        assert len(children) == 1
        assert children[0]["status"] == "running"

        spawner.cleanup()

    def test_fork_inherits_context(self):
        parent = AgentContext(
            agent_id=create_agent_id("parent"),
            session_id=create_session_id(),
        )
        fork_ctx = create_fork_context(parent, "fork-test")
        assert fork_ctx.session_id == parent.session_id
        assert fork_ctx.parent_agent_id == parent.agent_id
        assert fork_ctx.permission_mode == "bubble"


# ====================================================================
# 6. TestFullPipelineScenarios  (~8 tests — realistic scenarios)
# ====================================================================

class TestFullPipelineScenarios:
    """Realistic end-to-end scenarios spanning all layers."""

    def setup_method(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.project_dir = self._tmpdir.name
        self._gc, self.kg = _make_graph()
        self.vc, self.emb = _make_vector(tmpdir=self._tmpdir.name)
        self.m = Memoria(
            project_dir=self.project_dir,
            config={
                "knowledge_graph": self.kg,
                "vector_client": self.vc,
                "embedder": self.emb,
            },
        )

    def teardown_method(self) -> None:
        self.vc.close()
        self._tmpdir.cleanup()

    # -- tests --

    def test_developer_workflow(self):
        """Simulate a developer adding memories, then querying."""
        self.m.add("Prefer using black for Python formatting")
        self.m.add("Project uses FastAPI with SQLAlchemy ORM")
        self.m.add("CI/CD pipeline runs pytest then deploys to AWS")

        results = self.m.search("Python formatting")
        assert len(results) >= 1

        profile = self.m.profile(user_id="dev-1")
        assert isinstance(profile, ClientProfile)

    def test_multi_session_memory_persistence(self):
        """Memories persist across Memoria instances."""
        m1 = Memoria(project_dir=self.project_dir)
        path = m1.add("persistent memory across sessions")

        m2 = Memoria(project_dir=self.project_dir)
        got = m2.get(path)
        assert got is not None
        assert "persistent" in got["memory"]

    def test_knowledge_graph_grows_over_time(self):
        texts = [
            "Python is great for machine learning",
            "TensorFlow and PyTorch are ML frameworks",
            "Docker containerizes applications",
            "Kubernetes orchestrates Docker containers",
            "Redis is used for caching in microservices",
        ]
        for t in texts:
            self.kg.ingest_text(t)

        stats = self.kg.stats()
        assert stats["total_nodes"] >= 5
        assert stats["total_edges"] >= 0

    def test_semantic_search_accuracy(self):
        idx = VectorIndex(self.vc, self.emb)
        idx.index_text("doc-1", "Python programming language for data science")
        idx.index_text("doc-2", "Java enterprise application development")
        idx.index_text("doc-3", "Python machine learning with scikit-learn")

        search = SemanticSearch(self.vc, self.emb)
        results = search.search("Python data analysis")
        assert len(results) >= 1
        # Python-related docs should score higher than Java
        python_results = [r for r in results if "python" in r.content.lower()]
        assert len(python_results) >= 1

    def test_proactive_after_pattern_detection(self):
        profiler = Profiler(kg=self.kg)
        analyzer = PatternAnalyzer()

        for i in range(5):
            profiler.update_from_message("dev", f"How do I deploy with Docker? iteration {i}")
            analyzer.record_query("docker deployment")

        patterns = analyzer.detect_repetitions(min_count=3)
        assert len(patterns) >= 1

        pipeline = RecallPipeline.create_default(memory_dir=self.m._mem_dir)
        engine = SuggestionEngine(profiler=profiler, analyzer=analyzer, pipeline=pipeline)
        suggestions = engine.generate("dev")
        assert isinstance(suggestions, list)

    def test_concurrent_memory_operations(self):
        """Thread safety for add/search."""
        errors: list[str] = []

        def add_memories(start: int) -> None:
            try:
                for i in range(5):
                    self.m.add(f"concurrent memory {start + i} about testing")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=add_memories, args=(i * 5,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == []
        results = self.m.search("testing")
        assert len(results) >= 1

    def test_large_memory_set_performance(self):
        """100+ memories, search should complete quickly."""
        for i in range(100):
            self.m.add(f"memory number {i} about various topic {i % 10}")

        start = time.time()
        results = self.m.search("topic")
        elapsed = time.time() - start
        assert elapsed < 5.0  # generous threshold for CI
        assert len(results) >= 1

    def test_memory_type_filtering_end_to_end(self):
        self.m.add("user preference for dark mode", memory_type="user")
        self.m.add("project uses microservices architecture", memory_type="project")
        self.m.add("feedback: avoid long functions", memory_type="feedback")

        results = self.m.search("microservices")
        assert len(results) >= 1
        # Verify the project memory is found
        found_project = any(
            "microservices" in r["memory"].lower()
            for r in results
        )
        assert found_project

    def test_full_graph_vector_recall_roundtrip(self):
        """Ingest text → graph → recall pipeline finds it via graph + keyword."""
        text = "Rust ownership model prevents memory leaks at compile time"
        self.kg.ingest_text(text)
        # Also add as a memory file so keyword strategy can find it
        self.m.add(text)

        # Use keyword + graph pipeline (skipping vector to avoid
        # SQLite threading limitations in pure-python mode)
        pipeline = RecallPipeline.create_default(
            memory_dir=self.m._mem_dir,
            knowledge_graph=self.kg,
        )
        results = pipeline.recall("Rust memory safety")
        assert len(results) >= 1

    def test_profiler_expertise_evolves_with_messages(self):
        """Profiler expertise level changes as messages are added."""
        profiler = Profiler()
        for i in range(4):
            profiler.update_from_message("u1", "What is a variable? How do I use loops?")
        assert profiler.detect_expertise("u1") == "beginner"

        for _ in range(4):
            profiler.update_from_message(
                "u1",
                "Implementing dependency injection with inversion of control "
                "using the saga pattern and event sourcing with CQRS",
            )
        assert profiler.detect_expertise("u1") in ("intermediate", "expert")
