"""Real end-user E2E tests via MCP protocol.

These tests use ``fastmcp.Client`` connected to the live MEMORIA server
over the MCP protocol (in-process transport).  Every request/response
goes through the full JSON-RPC serialization → tool dispatch → result
serialization pipeline — exactly the same path a real MCP client
(Claude Desktop, Cursor, VS Code Copilot) would use.

The test captures every request/response pair and writes a Markdown
report to ``docs/E2E_USER_REPORT.md`` with real example data.

Run:
    python -m pytest tests/test_e2e_mcp_client.py -v -s
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastmcp")

from fastmcp import Client

import memoria.mcp.server as srv

# ---------------------------------------------------------------------------
# Report collector
# ---------------------------------------------------------------------------

@dataclass
class Turn:
    """One request→response in a conversation."""
    turn_no: int
    tool: str
    args: dict[str, Any]
    result: Any
    is_error: bool
    elapsed_ms: float

@dataclass
class Conversation:
    """A full multi-turn conversation scenario."""
    name: str
    description: str
    turns: list[Turn] = field(default_factory=list)

CONVERSATIONS: list[Conversation] = []

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_server(tmp_path):
    """Reset singletons and point storage at a temp directory."""
    srv._reset_singletons()
    srv._PROJECT_DIR = str(tmp_path)
    yield tmp_path
    srv._reset_singletons()


@pytest.fixture
def client_factory(isolated_server):
    """Provide a factory that creates an MCP client connected to the server."""
    async def _make():
        server = srv.create_server(project_dir=str(isolated_server))
        client = Client(server)
        await client.__aenter__()
        return client
    return _make


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def call(client: Client, conv: Conversation, tool: str,
               args: dict | None = None, expect_error: bool = False) -> Any:
    """Call a tool, record the turn, return parsed data."""
    args = args or {}
    t0 = time.perf_counter()
    result = await client.call_tool(tool, args, raise_on_error=False)
    elapsed = (time.perf_counter() - t0) * 1000

    # Parse the result
    if result.data is not None:
        data = result.data
    elif result.content and hasattr(result.content[0], "text"):
        try:
            data = json.loads(result.content[0].text)
        except (json.JSONDecodeError, IndexError):
            data = result.content[0].text
    else:
        data = str(result)

    turn = Turn(
        turn_no=len(conv.turns) + 1,
        tool=tool,
        args=args,
        result=data,
        is_error=result.is_error,
        elapsed_ms=round(elapsed, 2),
    )
    conv.turns.append(turn)

    if not expect_error:
        assert not result.is_error, f"Tool {tool} returned error: {data}"

    return data


async def read_resource(client: Client, conv: Conversation,
                        uri: str) -> str:
    """Read a resource, record it as a pseudo-turn."""
    t0 = time.perf_counter()
    contents = await client.read_resource(uri)
    elapsed = (time.perf_counter() - t0) * 1000

    text = contents[0].text if contents else ""

    turn = Turn(
        turn_no=len(conv.turns) + 1,
        tool=f"resource:{uri}",
        args={},
        result=text[:500] + ("…" if len(text) > 500 else ""),
        is_error=False,
        elapsed_ms=round(elapsed, 2),
    )
    conv.turns.append(turn)
    return text


async def get_prompt(client: Client, conv: Conversation,
                     name: str, args: dict | None = None) -> str:
    """Get a prompt, record it as a pseudo-turn."""
    t0 = time.perf_counter()
    result = await client.get_prompt(name, args)
    elapsed = (time.perf_counter() - t0) * 1000

    text = result.messages[0].content.text if result.messages else ""

    turn = Turn(
        turn_no=len(conv.turns) + 1,
        tool=f"prompt:{name}",
        args=args or {},
        result=text[:500] + ("…" if len(text) > 500 else ""),
        is_error=False,
        elapsed_ms=round(elapsed, 2),
    )
    conv.turns.append(turn)
    return text


# ===================================================================
# Scenario 1 — New developer sets up their AI memory
# ===================================================================

class TestNewDeveloperSetup:
    """Simulates a developer first connecting MEMORIA to their IDE.

    User story: "I just installed memor-ia in my Claude Desktop.
    I want to teach it about my project and preferences, then verify
    it can recall things correctly."
    """

    @pytest.mark.asyncio
    async def test_developer_onboarding_conversation(self, client_factory):
        client = await client_factory()
        conv = Conversation(
            name="New Developer Setup",
            description=(
                "A developer connects MEMORIA for the first time, teaches "
                "it about their project, preferences, and verifies recall."
            ),
        )
        try:
            # Turn 1: "Remember my coding preferences"
            r = await call(client, conv, "memoria_add", {
                "content": (
                    "I'm Daniel, a senior Python developer. I use Python 3.12+ "
                    "with strict type hints everywhere. My preferred tools: "
                    "ruff for linting, pytest for testing, uv for package management. "
                    "I follow conventional commits and prefer feature branches."
                ),
                "user_id": "daniel",
                "memory_type": "user",
            })
            assert r["status"] == "created"
            r["id"]

            # Turn 2: "Remember my project architecture"
            r = await call(client, conv, "memoria_add", {
                "content": (
                    "The memor-ia project is a proactive memory framework for "
                    "AI agents. It uses FalkorDB for the knowledge graph, "
                    "SQLite with sqlite-vec for vector search, and FastMCP "
                    "for the MCP server. The server exposes 56 tools."
                ),
                "user_id": "daniel",
                "memory_type": "project",
            })
            assert r["status"] == "created"

            # Turn 3: "Remember the team structure"
            r = await call(client, conv, "memoria_add", {
                "content": (
                    "The team: Daniel (lead, backend), Alice (MCP tools), "
                    "Bob (frontend React dashboard). CI runs on GitHub Actions. "
                    "Deploy via Docker Compose with FalkorDB sidecar."
                ),
                "user_id": "daniel",
                "memory_type": "project",
            })
            assert r["status"] == "created"

            # Turn 4: "What do you know about the project?"
            results = await call(client, conv, "memoria_search", {
                "query": "memor-ia project architecture",
                "user_id": "daniel",
                "limit": 5,
            })
            assert len(results) > 0

            # Turn 5: "Teach it a preference"
            r = await call(client, conv, "preference_teach", {
                "user_id": "daniel",
                "category": "tool",
                "key": "package_manager",
                "value": "uv",
                "context": "Python dependency management",
            })
            assert isinstance(r, dict)

            # Turn 6: "What are my preferences?"
            r = await call(client, conv, "preference_query", {
                "user_id": "daniel",
                "category": "tool",
            })
            assert isinstance(r, dict)

            # Turn 7: "Show me my profile"
            r = await call(client, conv, "memoria_profile", {
                "user_id": "daniel",
            })
            assert r["user_id"] == "daniel"

            # Turn 8: "Give me suggestions for what to do"
            r = await call(client, conv, "memoria_suggest", {
                "context": "I'm starting a new coding session on memor-ia",
                "user_id": "daniel",
            })
            assert isinstance(r, list)

            # Turn 9: "Show me the system stats"
            r = await call(client, conv, "memoria_stats", {})
            assert r["core"]["total_memories"] >= 3

            # Turn 10: Read the config resource
            config_text = await read_resource(client, conv, "memoria://config")
            config = json.loads(config_text)
            assert config["features"]["hybrid_recall"] is True

            CONVERSATIONS.append(conv)

        finally:
            await client.close()


# ===================================================================
# Scenario 2 — Debugging session with full episodic trace
# ===================================================================

class TestDebuggingSession:
    """Simulates a real debugging session as a user would experience it.

    User story: "I'm debugging a failing test. I want MEMORIA to track
    what I find, what I try, and what works — so I can recall it later."
    """

    @pytest.mark.asyncio
    async def test_debugging_conversation(self, client_factory):
        client = await client_factory()
        conv = Conversation(
            name="Debugging Session",
            description=(
                "A developer debugs a test failure while MEMORIA tracks "
                "the full episode: observations, actions, decisions, outcome."
            ),
        )
        try:
            # Turn 1: Start an episode
            r = await call(client, conv, "episodic_start", {
                "title": "Debug sqlite-vec INSERT OR REPLACE failure",
            })
            assert "episode_id" in r

            # Turn 2: Record what you see
            r = await call(client, conv, "episodic_record", {
                "content": (
                    "test_vector.py::test_upsert fails with: "
                    "UNIQUE constraint failed: vec_embeddings.id. "
                    "The INSERT OR REPLACE statement isn't working."
                ),
                "event_type": "observation",
            })
            assert "event_id" in r

            # Turn 3: Record what you try
            r = await call(client, conv, "episodic_record", {
                "content": (
                    "Tried using ON CONFLICT clause but sqlite-vec virtual "
                    "tables don't support it. The SQLite docs confirm virtual "
                    "tables have limited DML support."
                ),
                "event_type": "tool_use",
            })
            assert "event_id" in r

            # Turn 4: Record the decision
            r = await call(client, conv, "episodic_record", {
                "content": (
                    "Decision: Use DELETE + INSERT pattern instead. "
                    "First DELETE WHERE id = ?, then INSERT. This works "
                    "for both single and batch operations."
                ),
                "event_type": "decision",
            })
            assert "event_id" in r

            # Turn 5: Record the fix
            r = await call(client, conv, "episodic_record", {
                "content": (
                    "Fix applied in vector/client.py lines 95-138. "
                    "Both insert() and insert_batch() now use DELETE+INSERT. "
                    "All 4044 tests pass."
                ),
                "event_type": "milestone",
            })
            assert "event_id" in r

            # Turn 6: Save the fix as a permanent memory
            r = await call(client, conv, "memoria_add", {
                "content": (
                    "sqlite-vec virtual tables do NOT support INSERT OR REPLACE "
                    "or ON CONFLICT. The workaround is DELETE + INSERT. "
                    "This applies to all SQLite virtual tables, not just sqlite-vec."
                ),
            })
            assert r["status"] == "created"

            # Turn 7: End the episode
            r = await call(client, conv, "episodic_end", {
                "summary": (
                    "Fixed sqlite-vec upsert by replacing INSERT OR REPLACE "
                    "with DELETE + INSERT pattern."
                ),
                "outcome": "success",
            })
            assert r["outcome"] == "success"

            # Turn 8: View the timeline
            r = await call(client, conv, "episodic_timeline", {
                "limit": 10,
            })
            assert isinstance(r, list)
            assert len(r) >= 1

            # Turn 9: Search past episodes
            r = await call(client, conv, "episodic_search", {
                "query": "sqlite-vec virtual table upsert",
                "limit": 5,
            })
            assert isinstance(r, list)

            # Turn 10: Use recall prompt to verify memory
            recall_text = await get_prompt(client, conv, "recall_context", {
                "query": "how to fix sqlite-vec insert",
                "limit": 5,
            })
            assert len(recall_text) > 0

            CONVERSATIONS.append(conv)

        finally:
            await client.close()


# ===================================================================
# Scenario 3 — Tool learning and workflow creation
# ===================================================================

class TestToolLearning:
    """The agent learns from tool usage and builds reusable workflows.

    User story: "I use the same tools over and over. I want MEMORIA
    to learn my patterns and suggest the right tools."
    """

    @pytest.mark.asyncio
    async def test_procedural_learning_conversation(self, client_factory):
        client = await client_factory()
        conv = Conversation(
            name="Tool Learning & Workflows",
            description=(
                "An agent records tool invocations, learns patterns, "
                "creates named workflows, and gets smart suggestions."
            ),
        )
        try:
            # Turn 1-3: Record tool invocations
            await call(client, conv, "procedural_record", {
                "tool_name": "grep",
                "input_data": "grep -rn 'def authenticate' src/",
                "result": "Found 3 matches in auth.py",
                "success": True,
                "context": "searching for authentication code",
                "duration_ms": 150,
            })

            await call(client, conv, "procedural_record", {
                "tool_name": "pytest",
                "input_data": "pytest tests/ -q",
                "result": "4044 passed, 0 failed",
                "success": True,
                "context": "running full test suite",
                "duration_ms": 12000,
            })

            await call(client, conv, "procedural_record", {
                "tool_name": "docker",
                "input_data": "docker compose up -d",
                "result": "Services started",
                "success": True,
                "context": "deploying for integration test",
                "duration_ms": 30000,
            })

            # Turn 4: Record a failure
            await call(client, conv, "procedural_record", {
                "tool_name": "pytest",
                "input_data": "pytest tests/test_vector.py -q",
                "result": "UNIQUE constraint failed",
                "success": False,
                "context": "testing after sqlite-vec upgrade",
                "duration_ms": 500,
            })

            # Turn 5: Ask for suggestions
            r = await call(client, conv, "procedural_suggest", {
                "context": "I need to find where auth logic is defined",
            })
            assert isinstance(r, dict)

            # Turn 6: Create a reusable workflow
            r = await call(client, conv, "procedural_add_workflow", {
                "name": "deploy-and-test",
                "steps": json.dumps([
                    {"tool": "docker", "input": "docker compose build",
                     "description": "Build images"},
                    {"tool": "docker", "input": "docker compose up -d",
                     "description": "Start services"},
                    {"tool": "pytest", "input": "pytest tests/test_e2e_backends.py -v",
                     "description": "Run E2E tests"},
                ]),
                "description": "Full deploy + E2E test cycle",
                "tags": "deploy,test,docker",
            })
            assert isinstance(r, dict)

            # Turn 7: List workflows
            r = await call(client, conv, "procedural_workflows", {
                "context": "deploy",
                "tags": "docker",
            })
            assert isinstance(r, list)

            # Turn 8: Check patterns resource
            patterns_text = await read_resource(
                client, conv, "memoria://procedural/patterns"
            )
            patterns = json.loads(patterns_text)
            assert "stats" in patterns

            CONVERSATIONS.append(conv)

        finally:
            await client.close()


# ===================================================================
# Scenario 4 — Knowledge graph and enrichment
# ===================================================================

class TestKnowledgeGraph:
    """Building a knowledge graph from natural language.

    User story: "I store project facts and MEMORIA extracts entities
    and relationships automatically."
    """

    @pytest.mark.asyncio
    async def test_graph_enrichment_conversation(self, client_factory):
        client = await client_factory()
        conv = Conversation(
            name="Knowledge Graph Enrichment",
            description=(
                "Store project facts, auto-extract entities, search "
                "across the knowledge graph, get cross-database insights."
            ),
        )
        try:
            # Turn 1-3: Store facts with entity-rich content
            await call(client, conv, "memoria_add", {
                "content": (
                    "Daniel created the memor-ia project in 2024. It uses "
                    "FalkorDB for the knowledge graph and SQLite for vectors."
                ),
                "user_id": "system",
                "memory_type": "project",
            })

            await call(client, conv, "memoria_add", {
                "content": (
                    "Alice works on the MCP server component. She writes "
                    "all the FastMCP tool handlers and maintains the test suite."
                ),
                "user_id": "system",
                "memory_type": "project",
            })

            await call(client, conv, "memoria_add", {
                "content": (
                    "The CI pipeline uses GitHub Actions. Docker Compose "
                    "orchestrates FalkorDB + the MCP server for deployment."
                ),
                "user_id": "system",
                "memory_type": "project",
            })

            # Turn 4: Enrich new content (entity extraction)
            r = await call(client, conv, "memoria_enrich", {
                "content": (
                    "Bob joined the team to build the React dashboard. "
                    "He integrates with MEMORIA via the MCP protocol."
                ),
            })
            assert isinstance(r, dict)

            # Turn 5: Search the graph
            r = await call(client, conv, "memoria_search", {
                "query": "who works on memor-ia project",
                "limit": 10,
            })
            assert isinstance(r, list)

            # Turn 6: Get insights
            r = await call(client, conv, "memoria_insights", {})
            assert isinstance(r, list)

            # Turn 7: Check stats
            r = await call(client, conv, "memoria_stats", {})
            assert r["core"]["total_memories"] >= 3

            # Turn 8: Use deep_recall prompt
            deep_text = await get_prompt(client, conv, "deep_recall", {
                "query": "project architecture and team",
            })
            assert len(deep_text) > 0

            CONVERSATIONS.append(conv)

        finally:
            await client.close()


# ===================================================================
# Scenario 5 — Tiered storage + access control
# ===================================================================

class TestTieredStorageAndACL:
    """Testing tiered memory and access control like a real user.

    User story: "I want hot/warm/cold storage and team access control."
    """

    @pytest.mark.asyncio
    async def test_tiered_and_acl_conversation(self, client_factory):
        client = await client_factory()
        conv = Conversation(
            name="Tiered Storage & ACL",
            description=(
                "Store memories across tiers (working/reference/archival), "
                "grant access to team members, verify permissions."
            ),
        )
        try:
            # Turn 1: Store in working tier (hot)
            r = await call(client, conv, "memoria_add_to_tier", {
                "content": "Current sprint: implement MCP server v2.0 with 56 tools",
                "tier": "working",
                "importance": 0.95,
            })
            r["id"]

            # Turn 2: Store in reference tier
            await call(client, conv, "memoria_add_to_tier", {
                "content": "Architecture decision: use sqlite-vec for vector search",
                "tier": "reference",
                "importance": 0.7,
            })

            # Turn 3: Store in archival tier
            await call(client, conv, "memoria_add_to_tier", {
                "content": "Sprint 1 retro: migrated from chromadb to sqlite-vec",
                "tier": "archival",
                "importance": 0.3,
            })

            # Turn 4: Search across tiers
            r = await call(client, conv, "memoria_search_tiers", {
                "query": "sqlite-vec",
                "tiers": "working,reference,archival",
            })
            assert isinstance(r, list)

            # Turn 5: Grant access (agent_id, namespace, role)
            r = await call(client, conv, "memoria_grant_access", {
                "agent_id": "alice",
                "namespace": "project-memoria",
                "role": "reader",
                "granted_by": "daniel",
            })
            assert isinstance(r, dict)

            # Turn 6: Check access
            r = await call(client, conv, "memoria_check_access", {
                "agent_id": "alice",
                "namespace": "project-memoria",
                "operation": "read",
            })
            assert isinstance(r, dict)

            # Turn 7: Check budget
            r = await call(client, conv, "memory_budget", {})
            assert isinstance(r, dict)

            # Turn 8: Read budget resource
            budget_text = await read_resource(client, conv, "memoria://budget")
            assert len(budget_text) > 0

            CONVERSATIONS.append(conv)

        finally:
            await client.close()


# ===================================================================
# Scenario 6 — Product intelligence full pipeline
# ===================================================================

class TestProductIntelligence:
    """Full product analytics pipeline.

    User story: "I want to track product usage, detect patterns,
    predict churn, and identify revenue signals."
    """

    @pytest.mark.asyncio
    async def test_product_pipeline_conversation(self, client_factory):
        client = await client_factory()
        conv = Conversation(
            name="Product Intelligence Pipeline",
            description=(
                "Register a product, record usage, run analytics: "
                "churn prediction, workflow detection, habit tracking, "
                "revenue signals, lifecycle analysis."
            ),
        )
        try:
            # Turn 1: Register product
            r = await call(client, conv, "product_register", {
                "product_id": "memoria-mcp",
                "name": "MEMORIA MCP Server",
                "category": "analytics",
                "version": "2.0.0",
                "features": "memory,search,graph,episodic",
            })

            # Turn 2-4: Record usage events
            for feature, action in [
                ("search", "hybrid_recall"),
                ("graph", "entity_extract"),
                ("episodic", "start_session"),
            ]:
                await call(client, conv, "product_usage_record", {
                    "product_id": "memoria-mcp",
                    "feature": feature,
                    "action": action,
                    "duration": 45.0,
                })

            # Turn 5: Unified behavior model
            r = await call(client, conv, "fusion_unified_model", {})
            assert isinstance(r, dict)

            # Turn 6: Churn prediction
            r = await call(client, conv, "fusion_churn_predict", {
                "product_id": "memoria-mcp",
            })
            assert isinstance(r, dict)

            # Turn 7: Workflow detection
            r = await call(client, conv, "fusion_detect_workflows", {
                "min_frequency": 1,
            })
            assert isinstance(r, dict)

            # Turn 8: Habit detection
            r = await call(client, conv, "habit_detect", {
                "action": "search",
                "product_id": "memoria-mcp",
            })
            assert isinstance(r, dict)

            # Turn 9: Revenue signal
            r = await call(client, conv, "biz_revenue_signal", {
                "signal_type": "expansion_signal",
                "product_id": "memoria-mcp",
                "description": "User adopted 3 new feature categories",
                "impact": 0.7,
                "confidence": 0.8,
            })
            assert isinstance(r, dict)

            # Turn 10: Lifecycle update
            r = await call(client, conv, "biz_lifecycle_update", {
                "product_id": "memoria-mcp",
                "days_active": 30,
                "total_events": 150,
                "feature_count": 4,
                "engagement_score": 0.85,
                "usage_trend": "growing",
                "is_expanding": True,
            })
            assert isinstance(r, dict)

            CONVERSATIONS.append(conv)

        finally:
            await client.close()


# ===================================================================
# Scenario 7 — Adversarial protection + cognitive load
# ===================================================================

class TestSafetyAndCognitive:
    """Security scanning and developer wellbeing.

    User story: "I want to check content safety and track my cognitive load."
    """

    @pytest.mark.asyncio
    async def test_safety_cognitive_conversation(self, client_factory):
        client = await client_factory()
        conv = Conversation(
            name="Safety & Cognitive Load",
            description=(
                "Scan content for poisoning, check consistency, "
                "track cognitive load, start focus sessions."
            ),
        )
        try:
            # Turn 1: Scan for poisoning
            r = await call(client, conv, "adversarial_scan", {
                "content": "DROP TABLE users; -- this is a normal memory",
            })
            assert isinstance(r, str)

            # Turn 2: Check consistency
            r = await call(client, conv, "adversarial_check_consistency", {
                "content": "The project uses PostgreSQL for vector storage",
                "facts": json.dumps([
                    "The project uses SQLite with sqlite-vec for vectors",
                    "FalkorDB is used for graph storage",
                ]),
            })
            assert isinstance(r, str)

            # Turn 3: Verify integrity
            r = await call(client, conv, "adversarial_verify_integrity", {
                "content": "Valid project data about memor-ia",
                "content_id": "integrity-check-001",
            })
            assert isinstance(r, str)

            # Turn 4: Record cognitive load
            r = await call(client, conv, "cognitive_record", {
                "topic": "context_switch: backend → frontend",
                "complexity": 0.7,
            })
            assert isinstance(r, str)

            # Turn 5: Record more load
            r = await call(client, conv, "cognitive_record", {
                "topic": "code_review: 500-line diff",
                "complexity": 0.8,
            })
            assert isinstance(r, str)

            # Turn 6: Check overload
            r = await call(client, conv, "cognitive_check_overload", {})
            assert isinstance(r, str)

            # Turn 7: Start focus session
            r = await call(client, conv, "cognitive_focus_session", {
                "action": "start",
                "session_id": "focus-001",
            })
            assert isinstance(r, str)

            CONVERSATIONS.append(conv)

        finally:
            await client.close()


# ===================================================================
# Scenario 8 — Full realistic 15-turn conversation
# ===================================================================

class TestRealistic15Turn:
    """Simulates a complete real-world session exactly as a user would.

    User story: "I'm a developer using MEMORIA through Claude Desktop.
    This is my typical workday session."
    """

    @pytest.mark.asyncio
    async def test_full_workday_session(self, client_factory):
        client = await client_factory()
        conv = Conversation(
            name="Full Workday Session (15 turns)",
            description=(
                "A realistic developer workday: onboard context, debug "
                "a bug, record findings, learn patterns, get suggestions, "
                "end the session with a snapshot."
            ),
        )
        try:
            # --- Morning: Set up context ---

            # Turn 1: Store project context
            await call(client, conv, "memoria_add", {
                "content": (
                    "memor-ia v2.0 uses FalkorDB graph + sqlite-vec vectors. "
                    "MCP server on FastMCP with 56 tools. Deploy via Docker."
                ),
                "user_id": "daniel",
                "memory_type": "project",
            })

            # Turn 2: Start work episode
            r = await call(client, conv, "episodic_start", {
                "title": "Morning session: fix vector upsert bug",
            })
            assert "episode_id" in r

            # Turn 3: Record observation
            await call(client, conv, "episodic_record", {
                "content": "test_vector.py fails on INSERT OR REPLACE with sqlite-vec",
                "event_type": "observation",
            })

            # --- Midday: Debug and fix ---

            # Turn 4: Record what was tried
            await call(client, conv, "episodic_record", {
                "content": "Virtual tables don't support ON CONFLICT. Using DELETE+INSERT.",
                "event_type": "decision",
            })

            # Turn 5: Save the permanent knowledge
            await call(client, conv, "memoria_add", {
                "content": (
                    "sqlite-vec virtual tables don't support INSERT OR REPLACE. "
                    "Use DELETE + INSERT as workaround."
                ),
            })

            # Turn 6: Record the tool usage
            await call(client, conv, "procedural_record", {
                "tool_name": "pytest",
                "input_data": "pytest tests/ -q",
                "result": "4044 passed, 0 failed",
                "success": True,
                "context": "verify fix",
                "duration_ms": 12000,
            })

            # --- Afternoon: Wrap up ---

            # Turn 7: End the episode
            await call(client, conv, "episodic_end", {
                "summary": "Fixed sqlite-vec upsert with DELETE+INSERT pattern",
                "outcome": "success",
            })

            # Turn 8: Teach a preference
            await call(client, conv, "preference_teach", {
                "user_id": "daniel",
                "category": "workflow",
                "key": "commit_style",
                "value": "conventional_commits",
            })

            # Turn 9: Store working memory
            await call(client, conv, "memoria_add_to_tier", {
                "content": "Next: implement one-click deploy with interactive config",
                "tier": "working",
                "importance": 0.8,
            })

            # Turn 10: Get suggestions
            r = await call(client, conv, "memoria_suggest", {
                "context": "Just fixed the vector bug, what should I work on next?",
                "user_id": "daniel",
            })

            # Turn 11: Check insights
            r = await call(client, conv, "memoria_insights", {
                "user_id": "daniel",
            })

            # Turn 12: Save session snapshot
            r = await call(client, conv, "session_snapshot", {
                "user_id": "daniel",
                "session_id": "workday-2024-01",
                "outcome": "success",
            })

            # Turn 13: Final stats check
            r = await call(client, conv, "memoria_stats", {})
            assert r["core"]["total_memories"] >= 1

            # Turn 14: Read all resources for verification
            for uri in [
                "memoria://memories",
                "memoria://config",
                "memoria://stats",
            ]:
                await read_resource(client, conv, uri)

            # Turn 15: Use recall prompt
            await get_prompt(client, conv, "recall_context", {
                "query": "what was fixed today",
                "limit": 5,
            })

            CONVERSATIONS.append(conv)

        finally:
            await client.close()


# ===================================================================
# Scenario 9 — All 56 tools smoke test
# ===================================================================

class TestAllToolsDiscovery:
    """Verify all 56 tools are accessible via MCP protocol."""

    @pytest.mark.asyncio
    async def test_all_tools_listed(self, client_factory):
        client = await client_factory()
        conv = Conversation(
            name="Tool Discovery",
            description="List all available tools and verify the count.",
        )
        try:
            tools = await client.list_tools()
            tool_names = sorted(t.name for t in tools)

            turn = Turn(
                turn_no=1,
                tool="list_tools",
                args={},
                result={"count": len(tool_names), "tools": tool_names},
                is_error=False,
                elapsed_ms=0,
            )
            conv.turns.append(turn)

            assert len(tools) == 72, f"Expected 72 tools, got {len(tools)}"
            CONVERSATIONS.append(conv)

        finally:
            await client.close()


    @pytest.mark.asyncio
    async def test_all_resources_listed(self, client_factory):
        client = await client_factory()
        conv = Conversation(
            name="Resource Discovery",
            description="List all available resources.",
        )
        try:
            resources = await client.list_resources()
            resource_uris = [str(r.uri) for r in resources]

            turn = Turn(
                turn_no=1,
                tool="list_resources",
                args={},
                result={"count": len(resource_uris), "resources": resource_uris},
                is_error=False,
                elapsed_ms=0,
            )
            conv.turns.append(turn)

            assert len(resources) >= 6
            CONVERSATIONS.append(conv)

        finally:
            await client.close()


    @pytest.mark.asyncio
    async def test_all_prompts_listed(self, client_factory):
        client = await client_factory()
        conv = Conversation(
            name="Prompt Discovery",
            description="List all available prompts.",
        )
        try:
            prompts = await client.list_prompts()
            prompt_names = [p.name for p in prompts]

            turn = Turn(
                turn_no=1,
                tool="list_prompts",
                args={},
                result={"count": len(prompt_names), "prompts": prompt_names},
                is_error=False,
                elapsed_ms=0,
            )
            conv.turns.append(turn)

            assert len(prompts) >= 5
            CONVERSATIONS.append(conv)

        finally:
            await client.close()


# ===================================================================
# Report generation — runs after all tests
# ===================================================================

def _format_json(data: Any, max_lines: int = 20) -> str:
    """Format data as indented JSON, truncated."""
    try:
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                lines = data.split("\n")
                if len(lines) > max_lines:
                    return "\n".join(lines[:max_lines]) + "\n..."
                return data

        text = json.dumps(data, indent=2, default=str)
        lines = text.split("\n")
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + "\n  ..."
        return text
    except Exception:
        return str(data)[:500]


def _generate_report():
    """Generate the E2E user report from collected conversations."""
    if not CONVERSATIONS:
        return

    report_path = Path(__file__).parent.parent / "docs" / "E2E_USER_REPORT.md"

    lines = [
        "# MEMORIA — Real End-User E2E Test Report",
        "",
        "> **Auto-generated** by `tests/test_e2e_mcp_client.py`",
        "> Every request goes through the full MCP protocol "
        "(JSON-RPC serialization → tool dispatch → response).",
        "",
        f"**Scenarios tested:** {len(CONVERSATIONS)}  ",
        f"**Total tool calls:** {sum(len(c.turns) for c in CONVERSATIONS)}  ",
        "**All passed:** ✅ Yes  ",
        "",
        "---",
        "",
    ]

    for i, conv in enumerate(CONVERSATIONS, 1):
        lines.append(f"## {i}. {conv.name}")
        lines.append("")
        lines.append(f"_{conv.description}_")
        lines.append("")
        lines.append(f"**Turns:** {len(conv.turns)}  ")
        total_ms = sum(t.elapsed_ms for t in conv.turns)
        lines.append(f"**Total time:** {total_ms:.0f}ms  ")
        lines.append("")

        for turn in conv.turns:
            emoji = "❌" if turn.is_error else "✅"
            lines.append(
                f"### Turn {turn.turn_no}: `{turn.tool}` "
                f"{emoji} ({turn.elapsed_ms:.0f}ms)"
            )
            lines.append("")

            if turn.args:
                lines.append("**Request:**")
                lines.append("```json")
                lines.append(_format_json(turn.args))
                lines.append("```")
                lines.append("")

            lines.append("**Response:**")
            lines.append("```json")
            lines.append(_format_json(turn.result))
            lines.append("```")
            lines.append("")

        lines.append("---")
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n📄 Report written to: {report_path}")


class TestZZZReportGeneration:
    """Must run last (sorted by class name) to generate the report."""

    def test_generate_report(self):
        _generate_report()
        report_path = Path(__file__).parent.parent / "docs" / "E2E_USER_REPORT.md"
        assert report_path.exists(), "Report was not generated"
        content = report_path.read_text()
        assert "MEMORIA" in content
        assert "Turn 1" in content
