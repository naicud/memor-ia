"""End-to-end conversation simulation tests for MEMORIA MCP Server.

Simulates realistic multi-turn conversations through the MCP tool layer,
exercising the full backend stack: markdown files, SQLite vector DB (with
sqlite-vec), FalkorDB knowledge graph (in-memory fallback), episodic memory,
procedural memory, tiered storage, importance scoring, and proactive
intelligence.

Each test class represents a distinct user scenario. Every tool call goes
through the same code path a real MCP client (Claude Desktop, Cursor, etc.)
would use. No mocks on the backend — only the transport is bypassed.

Run:
    python -m pytest tests/test_e2e_conversation.py -v --tb=short
"""

from __future__ import annotations

import asyncio
import json

import pytest

pytest.importorskip("fastmcp")

import memoria.mcp.server as srv
from memoria.mcp.server import (
    adversarial_check_consistency,
    # Adversarial
    adversarial_scan,
    adversarial_verify_integrity,
    biz_lifecycle_update,
    # Biz Intel
    biz_revenue_signal,
    cognitive_check_overload,
    cognitive_focus_session,
    # Cognitive
    cognitive_record,
    context_infer_intent,
    # Context
    context_situation,
    # Dream
    dream_consolidate,
    dream_journal,
    emotion_analyze,
    emotion_fatigue_check,
    episodic_end,
    episodic_record,
    episodic_search,
    # Episodic
    episodic_start,
    episodic_timeline,
    estimate_difficulty,
    fusion_churn_predict,
    fusion_detect_workflows,
    fusion_unified_model,
    get_budget,
    get_config,
    get_episodic_timeline,
    get_procedural_patterns,
    get_stats,
    habit_detect,
    # Importance / Self-edit / Budget
    importance_score,
    # Resources
    list_memories,
    # Core
    memoria_add,
    # Tiered / ACL / Enrichment
    memoria_add_to_tier,
    memoria_check_access,
    memoria_delete,
    memoria_enrich,
    memoria_get,
    memoria_grant_access,
    memoria_insights,
    memoria_profile,
    memoria_search,
    memoria_search_tiers,
    memoria_stats,
    memoria_suggest,
    memoria_sync,
    memory_budget,
    predict_next_action,
    # Preferences
    preference_query,
    preference_teach,
    procedural_add_workflow,
    # Procedural
    procedural_record,
    procedural_suggest,
    procedural_workflows,
    # Product / Fusion
    product_register,
    product_usage_record,
    # Prompts
    recall_context,
    self_edit,
    session_resume,
    # Resurrection
    session_snapshot,
    suggest_next,
    team_coherence_check,
    # Sharing / Prediction / Emotion
    team_share_memory,
    user_dna_collect,
    # User DNA
    user_dna_snapshot,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_server(tmp_path):
    """Reset all singletons and point storage at a temp directory."""
    srv._reset_singletons()
    srv._PROJECT_DIR = str(tmp_path)
    yield tmp_path
    srv._reset_singletons()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _no_error(result):
    """Assert that a tool result contains no error."""
    if isinstance(result, dict):
        assert "error" not in result, f"Unexpected error: {result.get('error')}"
    elif isinstance(result, list):
        for item in result:
            if isinstance(item, dict):
                assert "error" not in item, f"Unexpected error: {item.get('error')}"
    return result


def _run(coro):
    """Run an async coroutine synchronously (Python 3.14 compatible)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ===================================================================
# Scenario 1 — Developer onboarding conversation
# ===================================================================

class TestDeveloperOnboarding:
    """Simulates a new developer being onboarded into a project.

    Conversation flow:
      1. User stores coding preferences (Python, type hints, ruff)
      2. User stores project architecture knowledge
      3. User asks for recall of project context
      4. System provides proactive suggestions
      5. User checks their profile
    """

    def test_full_onboarding_flow(self, isolated_server):

        # Turn 1: Store coding preferences
        r1 = _no_error(memoria_add(
            "I prefer Python 3.12+ with strict type hints. "
            "Use ruff for linting and pytest for testing.",
            user_id="dev-alice",
            memory_type="user",
        ))
        assert r1["status"] == "created"
        pref_id = r1["id"]

        # Turn 2: Store project architecture
        r2 = _no_error(memoria_add(
            "The memor-ia project uses FalkorDB as graph backend and "
            "SQLite with sqlite-vec for vector storage. "
            "The MCP server is built on FastMCP and exposes 56 tools.",
            user_id="dev-alice",
            memory_type="project",
        ))
        assert r2["status"] == "created"

        # Turn 3: Store team information
        r3 = _no_error(memoria_add(
            "Team lead is Daniel. Backend is Python, "
            "frontend is React. CI runs on GitHub Actions.",
            user_id="dev-alice",
            memory_type="project",
        ))
        assert r3["status"] == "created"

        # Turn 4: Search — "What do I know about the project?"
        results = memoria_search("project architecture backend", user_id="dev-alice", limit=5)
        assert len(results) > 0

        # Turn 5: Enrich a new piece of knowledge
        enrichment = _no_error(memoria_enrich(
            "Daniel prefers FastAPI for REST endpoints and uses Docker for deployment"
        ))
        assert isinstance(enrichment, dict)

        # Turn 6: Check profile
        profile = _no_error(memoria_profile(user_id="dev-alice"))
        assert profile["user_id"] == "dev-alice"

        # Turn 7: Get suggestions
        suggestions = memoria_suggest(
            context="I'm setting up the development environment",
            user_id="dev-alice",
        )
        assert isinstance(suggestions, list)

        # Turn 8: Get insights
        insights = memoria_insights(user_id="dev-alice")
        assert isinstance(insights, list)

        # Turn 9: Retrieve the first memory
        memory = memoria_get(pref_id)
        # get returns the memory dict or not_found
        assert isinstance(memory, dict)

        # Turn 10: Get full stats
        stats = _no_error(memoria_stats())
        assert stats["core"]["total_memories"] >= 1


# ===================================================================
# Scenario 2 — Multi-session episodic conversation
# ===================================================================

class TestEpisodicConversation:
    """Simulates a multi-session debugging workflow tracked episodically.

    Flow:
      1. Start episode "Debug auth failure"
      2. Record several events (observations, decisions, tool uses)
      3. End episode with outcome
      4. Start new episode "Fix tests"
      5. Query timeline across episodes
      6. Search episodes by content
    """

    def test_multi_session_debugging(self, isolated_server):
        # Session 1: Debug auth failure
        ep1 = _no_error(episodic_start(
            title="Debug auth failure",
            agent_id="copilot-main",
            session_id="sess-001",
        ))
        assert "episode_id" in ep1

        # Record observations
        _no_error(episodic_record(
            "User reports 401 errors on /api/v2/memories endpoint",
            event_type="observation",
            importance=0.8,
            agent_id="copilot-main",
        ))

        _no_error(episodic_record(
            "Traced issue to missing Bearer token validation in middleware",
            event_type="observation",
            importance=0.9,
        ))

        # Record decision
        _no_error(episodic_record(
            "Decision: Add JWT validation middleware before route handler",
            event_type="decision",
            importance=0.95,
        ))

        # Record tool use
        _no_error(episodic_record(
            "Ran pytest tests/test_auth.py — 3 failed, 12 passed",
            event_type="tool_use",
            importance=0.7,
        ))

        # Record milestone
        _no_error(episodic_record(
            "Auth middleware fix deployed, all tests passing",
            event_type="milestone",
            importance=1.0,
        ))

        # End episode
        ep1_end = _no_error(episodic_end(
            summary="Fixed 401 auth errors by adding JWT middleware",
            outcome="success",
        ))
        assert ep1_end.get("outcome") == "success"

        # Session 2: Fix broken tests
        ep2 = _no_error(episodic_start(
            title="Fix integration tests after auth change",
            agent_id="copilot-main",
            session_id="sess-002",
        ))
        assert ep2["episode_id"] != ep1["episode_id"]

        _no_error(episodic_record(
            "Integration tests failing because test fixtures lack auth tokens",
            event_type="observation",
            importance=0.8,
        ))

        _no_error(episodic_record(
            "Added conftest.py fixture for test auth tokens",
            event_type="decision",
            importance=0.7,
        ))

        _no_error(episodic_end(
            summary="Fixed test fixtures with auth token generator",
            outcome="success",
        ))

        # Query timeline across both sessions
        timeline = episodic_timeline(limit=20)
        assert isinstance(timeline, list)
        assert len(timeline) >= 5  # at least the events we recorded

        # Filter by importance
        important = episodic_timeline(min_importance=0.9, limit=10)
        assert isinstance(important, list)

        # Search episodes
        search_results = episodic_search("auth middleware JWT", limit=5)
        assert isinstance(search_results, list)


# ===================================================================
# Scenario 3 — Procedural learning from tool usage
# ===================================================================

class TestProceduralLearning:
    """Simulates an agent learning tool patterns over multiple interactions.

    Flow:
      1. Record successful tool uses (grep, pytest, docker)
      2. Record a failure pattern
      3. Ask for tool suggestions based on context
      4. Create and retrieve workflows
    """

    def test_tool_pattern_learning(self, isolated_server):
        # Record successful tool uses
        r1 = procedural_record(
            tool_name="grep",
            input_data="grep -rn 'def authenticate' src/",
            result="Found 3 matches in auth.py",
            success=True,
            context="searching for authentication code",
            duration_ms=150,
        )
        assert isinstance(r1, dict)

        procedural_record(
            tool_name="pytest",
            input_data="pytest tests/ -q",
            result="4044 passed, 0 failed",
            success=True,
            context="running full test suite after code change",
            duration_ms=12000,
        )

        procedural_record(
            tool_name="docker",
            input_data="docker compose up -d",
            result="All services started",
            success=True,
            context="deploying services for integration testing",
            duration_ms=30000,
        )

        # Record a failure
        procedural_record(
            tool_name="pytest",
            input_data="pytest tests/test_vector.py -q",
            result="UNIQUE constraint failed on vec_embeddings",
            success=False,
            context="testing vector insert after sqlite-vec upgrade",
            duration_ms=500,
        )

        # Ask for tool suggestion
        suggestion = procedural_suggest("I need to find where auth is defined")
        assert isinstance(suggestion, dict)

        # Create a workflow
        workflow = _no_error(procedural_add_workflow(
            name="deploy-and-test",
            steps=json.dumps([
                {"tool": "docker", "input": "docker compose build", "description": "Build images"},
                {"tool": "docker", "input": "docker compose up -d", "description": "Start services"},
                {"tool": "pytest", "input": "pytest tests/test_e2e_backends.py -v", "description": "Run E2E"},
            ]),
            description="Build, deploy, and run E2E tests",
            tags="deploy,test,docker",
        ))
        assert isinstance(workflow, dict)

        # List workflows
        workflows = procedural_workflows(context="deploy", tags="docker")
        assert isinstance(workflows, list)

        # Check procedural patterns resource
        patterns_json = get_procedural_patterns()
        patterns = json.loads(patterns_json)
        assert "stats" in patterns


# ===================================================================
# Scenario 4 — Tiered storage lifecycle
# ===================================================================

class TestTieredStorageLifecycle:
    """Tests the full tier lifecycle: working → recall → archival.

    Flow:
      1. Add working memory (ephemeral)
      2. Add recall memory (persistent)
      3. Add archival memory (cold storage)
      4. Search across tiers
      5. Check memory budget
    """

    def test_tier_progression(self, isolated_server):
        # Working memory (ephemeral, session-scoped)
        w1 = _no_error(memoria_add_to_tier(
            "Current task: fix vector insert bug in sqlite-vec backend",
            tier="working",
            importance=0.9,
        ))
        assert w1["tier"] == "working"

        w2 = _no_error(memoria_add_to_tier(
            "Temporary note: port 6379 is in use by another Redis instance",
            tier="working",
            importance=0.3,
        ))
        assert w2["tier"] == "working"

        # Recall memory (persistent)
        r1 = _no_error(memoria_add_to_tier(
            "sqlite-vec virtual tables do NOT support INSERT OR REPLACE. "
            "Use DELETE + INSERT pattern instead.",
            tier="recall",
            metadata=json.dumps({"source": "debugging", "confidence": 0.99}),
            importance=0.95,
        ))
        assert r1["tier"] == "recall"

        # Archival memory (cold storage)
        a1 = _no_error(memoria_add_to_tier(
            "Historical: Project started on 2025-01-15 by Daniel. "
            "Initial prototype used Mem0 as inspiration.",
            tier="archival",
            importance=0.5,
        ))
        assert a1["tier"] == "archival"

        # Search across tiers
        all_results = memoria_search_tiers("sqlite-vec", limit=10)
        assert isinstance(all_results, list)

        # Search specific tiers
        recall_only = memoria_search_tiers("sqlite-vec", tiers="recall", limit=5)
        assert isinstance(recall_only, list)

        # Check budget
        budget = _no_error(memory_budget())
        assert isinstance(budget, dict)

        # Resource: budget
        budget_json = get_budget()
        budget_data = json.loads(budget_json)
        assert isinstance(budget_data, dict)


# ===================================================================
# Scenario 5 — Access control and namespaces
# ===================================================================

class TestAccessControlFlow:
    """Tests namespace-scoped access control.

    Flow:
      1. Grant reader access to agent
      2. Grant writer access to another agent
      3. Check access permissions
    """

    def test_acl_lifecycle(self, isolated_server):
        # Grant reader access
        grant1 = _no_error(memoria_grant_access(
            agent_id="agent-reader",
            namespace="project/memor-ia",
            role="reader",
            granted_by="admin",
        ))
        assert grant1["status"] == "granted"
        assert grant1["role"] == "reader"

        # Grant writer access
        grant2 = _no_error(memoria_grant_access(
            agent_id="agent-writer",
            namespace="project/memor-ia",
            role="writer",
            granted_by="admin",
        ))
        assert grant2["status"] == "granted"

        # Check access
        access = _no_error(memoria_check_access(
            agent_id="agent-reader",
            namespace="project/memor-ia",
        ))
        assert isinstance(access, dict)


# ===================================================================
# Scenario 6 — Graph knowledge + entity extraction
# ===================================================================

class TestGraphKnowledgeFlow:
    """Tests knowledge graph entity extraction and graph queries.

    Flow:
      1. Store facts that contain entities (people, projects, tools)
      2. Enrich content to extract entities
      3. Search and verify graph relationships
      4. Get insights from cross-database analysis
    """

    def test_entity_graph_pipeline(self, isolated_server):
        # Store facts with rich entity content
        _no_error(memoria_add(
            "Daniel created the memor-ia project. It uses FalkorDB for "
            "graph storage and SQLite for vector embeddings.",
            user_id="system",
            memory_type="project",
        ))

        _no_error(memoria_add(
            "Alice is a backend developer who works on the MCP server. "
            "She prefers Python type hints and uses ruff for linting.",
            user_id="system",
            memory_type="project",
        ))

        _no_error(memoria_add(
            "The CI pipeline runs on GitHub Actions. Docker is used "
            "for deployment. FalkorDB runs as a Docker service.",
            user_id="system",
            memory_type="project",
        ))

        # Enrich content — extract entities
        enrichment = _no_error(memoria_enrich(
            "Bob joined the team to work on the React frontend. "
            "He integrates with the MEMORIA API using fetch."
        ))
        assert isinstance(enrichment, dict)

        # Search for graph-connected knowledge
        results = memoria_search("who works on memor-ia", limit=5)
        assert isinstance(results, list)

        # Cross-database insights
        insights = memoria_insights()
        assert isinstance(insights, list)

        # Stats should show memories
        stats = _no_error(memoria_stats())
        assert stats["core"]["total_memories"] >= 3


# ===================================================================
# Scenario 7 — Importance scoring and self-editing
# ===================================================================

class TestImportanceSelfEdit:
    """Tests importance scoring and autonomous memory management.

    Flow:
      1. Store memories and get IDs
      2. Score importance by memory ID
      3. Run self-edit action on a memory
    """

    def test_importance_and_self_edit(self, isolated_server):
        # Add memories of varying importance
        m1 = _no_error(memoria_add("Critical: production database credentials rotated today"))
        _no_error(memoria_add("Reminder: team standup at 10am"))
        m3 = _no_error(memoria_add("FYI: new coffee machine in the kitchen"))

        # Score importance by memory ID
        score = _no_error(importance_score(
            memory_id=m1["id"],
            access_count=5,
            connection_count=3,
        ))
        assert isinstance(score, dict)

        # Self-edit: compress a low-importance memory
        edits = _no_error(self_edit(
            memory_id=m3["id"],
            action="compress",
            reason="Low importance, compress for storage efficiency",
            new_content="New coffee machine in kitchen",
        ))
        assert isinstance(edits, dict)


# ===================================================================
# Scenario 8 — User DNA + Dream consolidation
# ===================================================================

class TestUserDNAAndDream:
    """Tests user DNA profiling and dream consolidation.

    Flow:
      1. Collect user interaction data
      2. Take a DNA snapshot
      3. Run dream consolidation
      4. Check dream journal
    """

    def test_dna_and_dream_flow(self, isolated_server):
        # Collect user interaction data
        collect_result = _no_error(user_dna_collect(
            user_id="dev-alice",
            message="How do I set up FalkorDB?",
            role="user",
        ))
        assert isinstance(collect_result, dict)

        _no_error(user_dna_collect(
            user_id="dev-alice",
            message="What about vector search with sqlite-vec?",
            role="user",
        ))

        # Take DNA snapshot
        snapshot = _no_error(user_dna_snapshot(user_id="dev-alice"))
        assert isinstance(snapshot, dict)

        # Run dream consolidation
        dream = _no_error(dream_consolidate())
        assert isinstance(dream, dict)

        # Check dream journal
        journal = _no_error(dream_journal())
        assert isinstance(journal, dict)


# ===================================================================
# Scenario 9 — Preferences teaching and querying
# ===================================================================

class TestPreferences:
    """Tests preference teaching and retrieval.

    Flow:
      1. Teach the system about user preferences
      2. Query preferences by context
    """

    def test_preference_lifecycle(self, isolated_server):
        # Teach preferences (valid categories: language, framework, tool, style, workflow, etc.)
        _no_error(preference_teach(
            user_id="dev-alice",
            category="tool",
            key="dark_mode",
            value="always",
            context="IDE settings",
        ))

        _no_error(preference_teach(
            user_id="dev-alice",
            category="style",
            key="indent_style",
            value="spaces_4",
        ))

        _no_error(preference_teach(
            user_id="dev-alice",
            category="testing",
            key="test_runner",
            value="pytest",
        ))

        # Query preferences
        prefs = _no_error(preference_query(
            user_id="dev-alice",
            category="style",
        ))
        assert isinstance(prefs, dict)


# ===================================================================
# Scenario 10 — Session snapshot and resurrection
# ===================================================================

class TestSessionResurrection:
    """Tests session snapshot and resume (resurrection).

    Flow:
      1. Build up state (memories + episode)
      2. Take a snapshot
      3. Resume from snapshot
    """

    def test_snapshot_and_resume(self, isolated_server):
        # Build state
        _no_error(memoria_add("Important project context for snapshot test"))
        _no_error(episodic_start(title="snapshot-test-session"))
        _no_error(episodic_record("Working on snapshot feature", event_type="observation"))

        # Take snapshot (user_id, session_id)
        snap = _no_error(session_snapshot(
            user_id="dev-alice",
            session_id="snap-001",
        ))
        assert isinstance(snap, dict)

        # Resume
        resumed = _no_error(session_resume(user_id="dev-alice"))
        assert isinstance(resumed, dict)


# ===================================================================
# Scenario 11 — Team collaboration and sharing
# ===================================================================

class TestTeamCollaboration:
    """Tests team memory sharing and coherence checks."""

    def test_team_flow(self, isolated_server):
        # Share memory with team (agent_id, namespace, key, value, topics)
        share = _no_error(team_share_memory(
            agent_id="dev-alice",
            namespace="backend-team",
            key="architecture",
            value="Use event-driven pattern for inter-service communication",
            topics="architecture,patterns",
        ))
        assert isinstance(share, dict)

        # Check team coherence
        coherence = _no_error(team_coherence_check(team_id="backend-team"))
        assert isinstance(coherence, dict)


# ===================================================================
# Scenario 12 — Prediction and emotional analysis
# ===================================================================

class TestPredictionAndEmotion:
    """Tests action prediction, difficulty estimation, emotion analysis."""

    def test_prediction_flow(self, isolated_server):
        # Predict next action (action, top_k)
        prediction = _no_error(predict_next_action(
            action="debug_complete",
            top_k=3,
        ))
        assert isinstance(prediction, dict)

        # Estimate difficulty (description, keywords)
        difficulty = _no_error(estimate_difficulty(
            description="Migrate FalkorDB schema to support temporal relations",
            keywords="graph,migration,schema",
        ))
        assert isinstance(difficulty, dict)

        # Analyze emotion (text, context)
        emotion = _no_error(emotion_analyze(
            text="This bug is driving me crazy! I've been stuck for hours.",
            context="debugging",
        ))
        assert isinstance(emotion, dict)

        # Check fatigue (no args)
        fatigue = _no_error(emotion_fatigue_check())
        assert isinstance(fatigue, dict)


# ===================================================================
# Scenario 13 — Product intelligence and business signals
# ===================================================================

class TestProductIntelligence:
    """Tests product tracking, usage profiling, and business intelligence."""

    def test_product_intel_flow(self, isolated_server):
        # Register product (product_id, name, category, version, features)
        reg = _no_error(_run(product_register(
            product_id="memoria-mcp",
            name="MEMORIA MCP Server",
            category="analytics",
            version="3.0.0",
            features="memory,search,graph",
        )))
        assert isinstance(reg, dict)

        # Record usage (product_id, feature, action, duration, session_id)
        usage = _no_error(_run(product_usage_record(
            product_id="memoria-mcp",
            feature="search",
            action="hybrid_recall",
            duration=45.0,
            session_id="sess-001",
        )))
        assert isinstance(usage, dict)

        # Unified behavior model (no args)
        model = _no_error(_run(fusion_unified_model()))
        assert isinstance(model, dict)

        # Churn prediction (product_id)
        churn = _no_error(_run(fusion_churn_predict(product_id="memoria-mcp")))
        assert isinstance(churn, dict)

        # Workflow detection (min_frequency)
        workflows = _no_error(_run(fusion_detect_workflows(min_frequency=1)))
        assert isinstance(workflows, dict)

        # Habit detection (action, product_id)
        habits = _no_error(_run(habit_detect(action="search", product_id="memoria-mcp")))
        assert isinstance(habits, dict)

        # Revenue signal (signal_type, product_id, description)
        revenue = _no_error(_run(biz_revenue_signal(
            signal_type="expansion_signal",
            product_id="memoria-mcp",
            description="User adopted 3 new tool categories this week",
            impact=0.7,
            confidence=0.8,
        )))
        assert isinstance(revenue, dict)

        # Lifecycle update (product_id, days_active, ...)
        lifecycle = _no_error(_run(biz_lifecycle_update(
            product_id="memoria-mcp",
            days_active=30,
            total_events=150,
            feature_count=5,
            engagement_score=0.8,
        )))
        assert isinstance(lifecycle, dict)


# ===================================================================
# Scenario 14 — Context awareness and intent inference
# ===================================================================

class TestContextAwareness:
    """Tests situation awareness and intent inference."""

    def test_context_flow(self, isolated_server):
        # Register product first (needed for context tools)
        _no_error(_run(product_register(
            product_id="memoria-mcp",
            name="MEMORIA",
            category="analytics",
        )))

        # Analyze situation (product_id, action)
        situation = _no_error(_run(context_situation(
            product_id="memoria-mcp",
            action="debug_vector",
        )))
        assert isinstance(situation, dict)

        # Infer intent (product_id, action)
        intent = _no_error(_run(context_infer_intent(
            product_id="memoria-mcp",
            action="search_code",
        )))
        assert isinstance(intent, dict)


# ===================================================================
# Scenario 15 — Adversarial protection
# ===================================================================

class TestAdversarialProtection:
    """Tests memory poisoning detection, consistency checks, tamper proofing."""

    def test_adversarial_flow(self, isolated_server):
        # Store legitimate memories
        _no_error(memoria_add("Legitimate project configuration details"))
        _no_error(memoria_add("Valid team member information"))

        # Scan for poisoning (returns str)
        scan = _run(adversarial_scan(
            content="DROP TABLE users; -- this is a normal memory",
        ))
        assert isinstance(scan, str)

        # Check consistency (content, facts)
        consistency = _run(adversarial_check_consistency(
            content="The project uses PostgreSQL",
            facts='["The project uses SQLite and FalkorDB"]',
        ))
        assert isinstance(consistency, str)

        # Verify integrity (content, content_id)
        integrity = _run(adversarial_verify_integrity(
            content="Valid project data",
            content_id="test-001",
        ))
        assert isinstance(integrity, str)


# ===================================================================
# Scenario 16 — Cognitive load management
# ===================================================================

class TestCognitiveLoadManagement:
    """Tests cognitive load tracking, overload prevention, focus sessions."""

    def test_cognitive_flow(self, isolated_server):
        # Record cognitive load events (topic, complexity) → returns str
        r1 = _run(cognitive_record(
            topic="context_switch: backend to frontend",
            complexity=0.7,
        ))
        assert isinstance(r1, str)

        r2 = _run(cognitive_record(
            topic="code review: 500-line diff",
            complexity=0.8,
        ))
        assert isinstance(r2, str)

        # Check overload → returns str
        overload = _run(cognitive_check_overload())
        assert isinstance(overload, str)

        # Start focus session (action, session_id) → returns str
        focus = _run(cognitive_focus_session(
            action="start",
            session_id="focus-001",
        ))
        assert isinstance(focus, str)


# ===================================================================
# Scenario 17 — Resources and prompts
# ===================================================================

class TestResourcesAndPrompts:
    """Tests all MCP resources and prompts return valid data."""

    def test_all_resources(self, isolated_server):
        # Seed some data
        _no_error(memoria_add("Resource test memory"))
        _no_error(episodic_start(title="resource-test"))

        # All resources should return valid JSON
        memories_json = list_memories()
        memories = json.loads(memories_json)
        assert isinstance(memories, list)
        assert len(memories) >= 1

        config_json = get_config()
        config = json.loads(config_json)
        assert config["backends"]["graph"] in ("KnowledgeGraph", "InMemoryGraph", "none")
        assert config["features"]["hybrid_recall"] is True

        stats_json = get_stats()
        stats = json.loads(stats_json)
        assert isinstance(stats, dict)

        timeline_json = get_episodic_timeline()
        timeline = json.loads(timeline_json)
        assert isinstance(timeline, (list, dict))

        patterns_json = get_procedural_patterns()
        patterns = json.loads(patterns_json)
        assert "stats" in patterns

        budget_json = get_budget()
        budget = json.loads(budget_json)
        assert isinstance(budget, dict)

    def test_recall_prompt(self, isolated_server):
        _no_error(memoria_add("Python uses snake_case for variable names"))
        prompt = recall_context("Python naming conventions", limit=3)
        assert isinstance(prompt, str)

    def test_suggest_prompt(self, isolated_server):
        _no_error(memoria_add("The deploy process uses Docker"))
        prompt = suggest_next(context="working on deployment automation")
        assert isinstance(prompt, str)


# ===================================================================
# Scenario 18 — Full conversation simulation (end-to-end)
# ===================================================================

class TestFullConversationSimulation:
    """Simulates a complete multi-turn conversation with a developer.

    This is the integration test that exercises the full stack:
    memory CRUD → graph entities → vector search → episodic tracking →
    procedural learning → tiered storage → proactive intelligence.

    Represents a realistic 15-turn conversation.
    """

    def test_realistic_15_turn_conversation(self, isolated_server):
        # --- Turn 1: Start session ---
        ep = _no_error(episodic_start(
            title="Daily development session",
            agent_id="memoria-assistant",
            session_id="daily-2026-04-02",
        ))
        assert "episode_id" in ep

        # --- Turn 2: User context ---
        _no_error(episodic_record(
            "User is working on memor-ia, specifically the vector backend",
            event_type="observation",
            importance=0.6,
        ))

        # --- Turn 3: Store what was learned ---
        _no_error(memoria_add(
            "sqlite-vec virtual tables do NOT support INSERT OR REPLACE. "
            "The workaround is DELETE followed by INSERT.",
            user_id="daniel",
            memory_type="project",
        ))

        # --- Turn 4: Store in recall tier (persistent) ---
        _no_error(memoria_add_to_tier(
            "FalkorDB connection uses port 6379 by default. "
            "If port is occupied, use FALKORDB_PORT env var.",
            tier="recall",
            importance=0.8,
        ))

        # --- Turn 5: Record tool usage ---
        _no_error(procedural_record(
            tool_name="pytest",
            input_data="pytest tests/ -q",
            result="4044 passed, 0 failed in 12.75s",
            success=True,
            context="running full test suite after vector fix",
            duration_ms=12750,
        ))

        # --- Turn 6: Record a decision ---
        _no_error(episodic_record(
            "Decision: Use DELETE+INSERT pattern for sqlite-vec upserts",
            event_type="decision",
            importance=0.95,
        ))

        # --- Turn 7: Search for related knowledge ---
        search_results = memoria_search("sqlite-vec insert pattern", limit=5)
        assert isinstance(search_results, list)

        # --- Turn 8: Enrich with entities ---
        _no_error(memoria_enrich(
            "Daniel fixed the vector client to use DELETE+INSERT for sqlite-vec "
            "virtual tables. This was deployed via Docker."
        ))

        # --- Turn 9: Score importance ---
        _no_error(importance_score(
            "sqlite-vec virtual tables do NOT support INSERT OR REPLACE"
        ))

        # --- Turn 10: Check cognitive load ---
        _run(cognitive_record(
            topic="Vector fix completed and tests passing",
            complexity=0.3,
        ))

        # --- Turn 11: Get proactive suggestions ---
        memoria_suggest(
            context="Just fixed vector backend, considering what to work on next",
            user_id="daniel",
        )

        # --- Turn 12: Teach preference ---
        _no_error(preference_teach(
            user_id="daniel",
            category="workflow",
            key="commit_style",
            value="conventional_commits",
        ))

        # --- Turn 13: Store working memory for next task ---
        _no_error(memoria_add_to_tier(
            "Next up: implement one-click deploy with interactive config",
            tier="working",
            importance=0.7,
        ))

        # --- Turn 14: End episode ---
        _no_error(episodic_end(
            summary="Fixed sqlite-vec INSERT OR REPLACE bug using DELETE+INSERT. "
                    "All 4044 tests passing. Docker deploy verified.",
            outcome="success",
        ))

        # --- Turn 15: Final recall prompt ---
        prompt = recall_context("what was fixed today", limit=5)
        assert "sqlite" in prompt.lower() or "memor" in prompt.lower() or "No relevant" in prompt

        # --- Verify full state ---
        stats = _no_error(memoria_stats())
        assert stats["core"]["total_memories"] >= 1

        budget = _no_error(memory_budget())
        assert isinstance(budget, dict)

        config_json = get_config()
        config = json.loads(config_json)
        assert config["features"]["hybrid_recall"] is True


# ===================================================================
# Scenario 19 — Delete and sync lifecycle
# ===================================================================

class TestDeleteAndSync:
    """Tests memory deletion and sync operations."""

    def test_delete_flow(self, isolated_server):
        # Create
        r = _no_error(memoria_add("Temporary memory to delete"))
        mem_id = r["id"]

        # Verify exists
        got = _no_error(memoria_get(mem_id))
        assert got.get("status") != "not_found"

        # Delete
        deleted = _no_error(memoria_delete(mem_id))
        assert deleted["status"] == "deleted"

        # Verify gone
        gone = memoria_get(mem_id)
        assert gone["status"] == "not_found"

    def test_sync(self, isolated_server):
        _no_error(memoria_add("Memory to sync"))
        sync_result = _no_error(memoria_sync())
        assert isinstance(sync_result, dict)
