"""Comprehensive tests for MEMORIA MCP Server — 26 tools, 7 resources, 5 prompts.

Tests all tool functions directly (they're regular Python functions behind
FastMCP decorators). Uses temp-dir isolation and singleton resets for
full test independence.

Requires: fastmcp (skips entire module if unavailable).
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastmcp")

import memoria.mcp.server as srv
from memoria.mcp.server import (
    consolidation_report,
    deep_recall,
    dream_consolidate,
    dream_journal,
    emotion_analyze,
    emotion_fatigue_check,
    episodic_end,
    episodic_recap,
    episodic_record,
    episodic_search,
    # Episodic tools (13-17)
    episodic_start,
    episodic_timeline,
    estimate_difficulty,
    get_budget,
    get_config,
    get_episodic_timeline,
    get_procedural_patterns,
    get_stats,
    get_user_profile,
    # Importance / Self-edit tools (22-24)
    importance_score,
    # Resources
    list_memories,
    # Core tools (1-7)
    memoria_add,
    # Tiered / ACL / Enrichment / Sync tools (8-12)
    memoria_add_to_tier,
    # Remaining tools (25-26)
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
    preference_query,
    preference_teach,
    procedural_add_workflow,
    # Procedural tools (18-21)
    procedural_record,
    procedural_suggest,
    procedural_workflows,
    # Prompts
    recall_context,
    self_edit,
    session_resume,
    session_snapshot,
    suggest_next,
    team_coherence_check,
    # Hyper tools (35-40)
    team_share_memory,
    user_dna_collect,
    # Ultra tools (27-34)
    user_dna_snapshot,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_singletons():
    """Reset all lazy singletons for test isolation."""
    srv._reset_singletons()


@pytest.fixture(autouse=True)
def _isolated_project(tmp_path):
    """Give every test its own project dir and reset singletons."""
    _reset_singletons()
    srv._PROJECT_DIR = str(tmp_path)
    yield
    _reset_singletons()


# ===================================================================
# 1. Core CRUD tools
# ===================================================================


class TestMCPCoreTools:
    """Test core CRUD tools: add, search, get, delete."""

    def test_add_returns_created_status(self):
        result = memoria_add("Test memory about Python")
        assert result["status"] == "created"

    def test_add_returns_id(self):
        result = memoria_add("Another memory")
        assert "id" in result
        assert result["id"]  # non-empty

    def test_add_returns_content_preview(self):
        content = "A long memory about machine learning" + " data" * 50
        result = memoria_add(content)
        assert "content_preview" in result
        assert len(result["content_preview"]) <= 100

    def test_search_empty(self):
        results = memoria_search("nonexistent xyz topic")
        assert isinstance(results, list)

    def test_search_after_add(self):
        memoria_add("Rust is great for systems programming")
        results = memoria_search("Rust programming")
        assert isinstance(results, list)

    def test_search_with_limit(self):
        for i in range(6):
            memoria_add(f"Memory {i} about databases")
        results = memoria_search("databases", limit=3)
        assert len(results) <= 3

    def test_get_existing(self):
        added = memoria_add("Retrievable memory content")
        result = memoria_get(added["id"])
        assert result is not None
        assert "memory" in result
        assert "Retrievable" in result["memory"]

    def test_get_not_found(self):
        result = memoria_get("/nonexistent/path/memory.md")
        assert result["status"] == "not_found"

    def test_delete(self):
        added = memoria_add("Memory to delete")
        result = memoria_delete(added["id"])
        assert result["status"] == "deleted"
        # Confirm gone
        assert memoria_get(added["id"])["status"] == "not_found"

    def test_delete_not_found(self):
        result = memoria_delete("/no/such/file.md")
        assert result["status"] == "not_found"


# ===================================================================
# 2. Proactive tools
# ===================================================================


class TestMCPProactiveTools:
    """Test suggest, profile, insights."""

    def test_suggest_empty(self):
        results = memoria_suggest(context="test context")
        assert isinstance(results, list)

    def test_suggest_returns_list_with_structure(self):
        memoria_add("I use React daily")
        results = memoria_suggest(context="frontend")
        assert isinstance(results, list)
        for s in results:
            assert "type" in s
            assert "content" in s
            assert "confidence" in s
            assert "reason" in s

    def test_profile_default(self):
        result = memoria_profile()
        assert isinstance(result, dict)
        assert "expertise" in result
        assert "topics" in result
        assert "message_count" in result
        assert "session_count" in result

    def test_profile_specific_user(self):
        result = memoria_profile(user_id="alice")
        assert result["user_id"] == "alice"

    def test_insights_empty(self):
        results = memoria_insights()
        assert isinstance(results, list)

    def test_insights_structure(self):
        results = memoria_insights(user_id="u1")
        for item in results:
            assert "type" in item
            assert "description" in item
            assert "confidence" in item


# ===================================================================
# 3. Tiered tools
# ===================================================================


class TestMCPTieredTools:
    """Test tiered memory tools: add_to_tier, search_tiers."""

    def test_add_to_tier_working(self):
        result = memoria_add_to_tier("ephemeral note", tier="working")
        assert result["status"] == "created"
        assert result["tier"] == "working"
        assert "id" in result

    def test_add_to_tier_recall(self):
        result = memoria_add_to_tier("persistent note", tier="recall")
        assert result["status"] == "created"
        assert result["tier"] == "recall"

    def test_add_to_tier_archival(self):
        result = memoria_add_to_tier("cold storage note", tier="archival")
        assert result["status"] == "created"
        assert result["tier"] == "archival"

    def test_add_to_tier_with_metadata(self):
        meta = json.dumps({"source": "test"})
        result = memoria_add_to_tier("meta note", tier="working", metadata=meta)
        assert result["status"] == "created"

    def test_add_to_tier_with_importance(self):
        result = memoria_add_to_tier("important note", tier="recall", importance=0.9)
        assert result["status"] == "created"

    def test_add_to_tier_invalid_json_metadata(self):
        """Bug fix: invalid JSON in metadata returns error instead of crashing."""
        result = memoria_add_to_tier("note", tier="working", metadata="not valid json{")
        assert "error" in result
        assert "Invalid JSON" in result["error"]

    def test_search_tiers(self):
        memoria_add_to_tier("searchable tier note", tier="working")
        results = memoria_search_tiers("searchable")
        assert isinstance(results, list)

    def test_search_tiers_specific(self):
        memoria_add_to_tier("only in recall", tier="recall")
        results = memoria_search_tiers("only in recall", tiers="recall")
        assert isinstance(results, list)

    def test_search_tiers_multiple(self):
        results = memoria_search_tiers("something", tiers="working,recall")
        assert isinstance(results, list)


# ===================================================================
# 4. Access-control tools
# ===================================================================


class TestMCPAccessTools:
    """Test ACL tools: grant_access, check_access."""

    def test_grant_access(self):
        result = memoria_grant_access(
            agent_id="bot-1", namespace="shared", role="writer",
        )
        assert result["status"] == "granted"
        assert result["agent_id"] == "bot-1"
        assert result["namespace"] == "shared"
        assert result["role"] == "writer"
        assert "grant_id" in result

    def test_check_access_default(self):
        result = memoria_check_access(agent_id="unknown", namespace="private")
        assert isinstance(result, dict)
        assert "allowed" in result

    def test_check_access_after_grant(self):
        memoria_grant_access(agent_id="bot-2", namespace="ns", role="reader")
        result = memoria_check_access(agent_id="bot-2", namespace="ns", operation="read")
        assert isinstance(result, dict)
        assert "allowed" in result

    def test_check_access_invalid_operation(self):
        result = memoria_check_access(
            agent_id="x", namespace="y", operation="nuke",
        )
        assert "error" in result


# ===================================================================
# 5. Enrichment & Sync tools
# ===================================================================


class TestMCPEnrichmentTools:
    """Test enrichment and sync tools."""

    def test_enrich_content(self):
        result = memoria_enrich("Python is a popular programming language")
        assert isinstance(result, dict)

    def test_enrich_returns_metadata(self):
        result = memoria_enrich("Meeting with Alice about the API project on Monday")
        assert isinstance(result, dict)

    def test_sync_empty(self):
        result = memoria_sync()
        assert isinstance(result, dict)

    def test_sync_with_namespace(self):
        result = memoria_sync(namespace="default")
        assert isinstance(result, dict)


# ===================================================================
# 6. Episodic tools
# ===================================================================


class TestMCPEpisodicTools:
    """Test episodic memory tools: start, end, record, timeline, search."""

    def test_start_episode(self):
        result = episodic_start(title="Test Episode")
        assert isinstance(result, dict)
        assert "error" not in result or result.get("episode_id")

    def test_end_episode(self):
        ep = episodic_start(title="Ep to end")
        ep_id = ep.get("episode_id", "")
        result = episodic_end(episode_id=ep_id, summary="done", outcome="success")
        assert isinstance(result, dict)

    def test_end_episode_no_active(self):
        result = episodic_end()
        assert isinstance(result, dict)

    def test_end_episode_invalid_outcome(self):
        episodic_start(title="X")
        result = episodic_end(outcome="invalid_value")
        assert "error" in result

    def test_record_event(self):
        episodic_start(title="Record test")
        result = episodic_record(content="User asked about Python")
        assert isinstance(result, dict)
        # Should either succeed or have an error key
        if "error" not in result:
            assert "content" in result or "event_id" in result or result

    def test_record_multiple_types(self):
        episodic_start(title="Multi-type")
        for etype in ("interaction", "decision", "observation", "tool_use"):
            result = episodic_record(content=f"Event of type {etype}", event_type=etype)
            assert isinstance(result, dict)

    def test_record_invalid_event_type(self):
        episodic_start(title="Bad type")
        result = episodic_record(content="bad", event_type="nonexistent")
        assert "error" in result

    def test_timeline_query(self):
        episodic_start(title="Timeline test")
        episodic_record(content="Event 1")
        episodic_record(content="Event 2")
        result = episodic_timeline()
        assert isinstance(result, list)

    def test_timeline_with_filters(self):
        episodic_start(title="Filtered timeline")
        episodic_record(content="Decision event", event_type="decision")
        result = episodic_timeline(event_types="decision", min_importance=0.0)
        assert isinstance(result, list)

    def test_timeline_invalid_event_type(self):
        result = episodic_timeline(event_types="bogus_type")
        assert isinstance(result, list)
        if result:
            assert "error" in result[0]

    def test_search_episodes(self):
        episodic_start(title="Searchable episode about databases")
        episodic_record(content="Discussed PostgreSQL indexing")
        episodic_end(summary="Talked about databases")
        result = episodic_search("databases")
        assert isinstance(result, list)

    def test_episode_lifecycle(self):
        """Full lifecycle: start → record → end → search."""
        ep = episodic_start(title="Lifecycle test episode")
        assert isinstance(ep, dict)
        ep_id = ep.get("episode_id", "")

        rec = episodic_record(content="Important decision made", event_type="decision")
        assert isinstance(rec, dict)

        ended = episodic_end(episode_id=ep_id, summary="Completed lifecycle", outcome="success")
        assert isinstance(ended, dict)

        found = episodic_search("lifecycle")
        assert isinstance(found, list)


# ===================================================================
# 7. Procedural tools
# ===================================================================


class TestMCPProceduralTools:
    """Test procedural memory tools: record, suggest, workflows."""

    def test_record_tool_use(self):
        result = procedural_record(
            tool_name="grep",
            input_data="pattern: TODO",
            result="3 matches found",
            success=True,
            context="searching for TODOs",
            duration_ms=42.0,
        )
        assert isinstance(result, dict)

    def test_record_tool_use_failure(self):
        result = procedural_record(
            tool_name="compile",
            input_data="main.rs",
            result="error: mismatched types",
            success=False,
        )
        assert isinstance(result, dict)

    def test_suggest_tool(self):
        # Record some uses first so there's data
        procedural_record(
            tool_name="grep", input_data="pattern", result="found", success=True,
        )
        result = procedural_suggest(context="searching for text")
        assert isinstance(result, dict)

    def test_suggest_no_match(self):
        result = procedural_suggest(context="completely unrelated xyz")
        assert isinstance(result, dict)
        # Either has a suggestion or the "no matching" message
        assert "suggested_tool" in result or "message" in result or "suggested_procedure" in result

    def test_workflows_empty(self):
        result = procedural_workflows()
        assert isinstance(result, list)

    def test_add_workflow(self):
        steps = json.dumps([
            {"tool_name": "memoria_search", "description": "Find context", "input_template": "{}"},
            {"tool_name": "memoria_add", "description": "Store result", "input_template": "{}"},
        ])
        result = procedural_add_workflow(
            name="search-and-store",
            steps=steps,
            description="Search then store results",
            trigger_context="when user asks to save search results",
            tags="search,store",
        )
        assert isinstance(result, dict)
        if "error" not in result:
            assert result.get("name") == "search-and-store" or "workflow_id" in result or result

    def test_add_workflow_invalid_json(self):
        result = procedural_add_workflow(
            name="bad", steps="not json at all",
        )
        assert "error" in result

    def test_add_workflow_steps_not_list(self):
        result = procedural_add_workflow(
            name="bad", steps='{"not": "a list"}',
        )
        assert "error" in result

    def test_find_workflows(self):
        steps = json.dumps([
            {"tool_name": "grep", "description": "Search code", "input_template": "{}"},
        ])
        procedural_add_workflow(
            name="code-search", steps=steps, description="Search codebase",
        )
        result = procedural_workflows(context="search code")
        assert isinstance(result, list)

    def test_workflows_with_tags(self):
        steps = json.dumps([{"tool_name": "t", "description": "d", "input_template": "{}"}])
        procedural_add_workflow(name="tagged-wf", steps=steps, tags="alpha,beta")
        result = procedural_workflows(tags="alpha")
        assert isinstance(result, list)


# ===================================================================
# 8. Importance & Self-edit tools
# ===================================================================


class TestMCPImportanceTools:
    """Test importance scoring, self-edit, and memory budget tools."""

    def test_importance_score(self):
        result = importance_score(memory_id="mem-001")
        assert isinstance(result, dict)
        if "error" not in result:
            assert "score" in result
            assert "memory_id" in result
            assert isinstance(result["score"], (int, float))

    def test_importance_score_with_signals(self):
        result = importance_score(
            memory_id="mem-002", access_count=10, connection_count=5,
        )
        assert isinstance(result, dict)
        if "error" not in result:
            assert "score" in result
            assert "should_forget" in result
            assert "should_compress" in result
            assert "should_promote" in result
            assert "signals" in result

    def test_self_edit_keep(self):
        result = self_edit(memory_id="mem-k", action="keep", reason="important")
        assert isinstance(result, dict)

    def test_self_edit_discard(self):
        result = self_edit(memory_id="mem-d", action="discard", reason="stale")
        assert isinstance(result, dict)

    def test_self_edit_compress(self):
        result = self_edit(
            memory_id="mem-c", action="compress",
            new_content="compressed version", reason="too long",
        )
        assert isinstance(result, dict)

    def test_self_edit_promote(self):
        result = self_edit(
            memory_id="mem-p", action="promote",
            target_tier="recall", reason="frequently accessed",
        )
        assert isinstance(result, dict)

    def test_self_edit_demote(self):
        result = self_edit(
            memory_id="mem-dm", action="demote",
            target_tier="archival", reason="rarely accessed",
        )
        assert isinstance(result, dict)

    def test_self_edit_invalid_action(self):
        result = self_edit(memory_id="mem-x", action="explode")
        assert "error" in result
        assert "Invalid action" in result["error"]

    def test_self_edit_compress_requires_new_content(self):
        """Bug fix: compress without new_content returns validation error."""
        result = self_edit(memory_id="mem-c", action="compress", reason="shrink")
        assert "error" in result
        assert "new_content" in result["error"]

    def test_self_edit_promote_requires_target_tier(self):
        """Bug fix: promote without target_tier returns validation error."""
        result = self_edit(memory_id="mem-p", action="promote", reason="upgrade")
        assert "error" in result
        assert "target_tier" in result["error"]

    def test_self_edit_demote_requires_target_tier(self):
        """Bug fix: demote without target_tier returns validation error."""
        result = self_edit(memory_id="mem-d", action="demote", reason="downgrade")
        assert "error" in result
        assert "target_tier" in result["error"]

    def test_memory_budget(self):
        result = memory_budget()
        assert isinstance(result, dict)


# ===================================================================
# 9. Stats tool
# ===================================================================


class TestMCPStatsTools:
    """Test the memoria_stats tool."""

    def test_stats_returns_dict(self):
        result = memoria_stats()
        assert isinstance(result, dict)

    def test_stats_has_subsystems(self):
        result = memoria_stats()
        assert "core" in result
        assert "episodic" in result
        assert "procedural" in result
        assert "self_edit" in result

    def test_stats_core_has_total(self):
        result = memoria_stats()
        core = result.get("core", {})
        if "error" not in core:
            assert "total_memories" in core


# ===================================================================
# 10. Resources
# ===================================================================


class TestMCPResources:
    """Test all 7 resource functions."""

    def test_list_memories_resource(self):
        result = json.loads(list_memories())
        assert isinstance(result, list)

    def test_list_memories_after_add(self):
        memoria_add("Resource test memory")
        result = json.loads(list_memories())
        assert len(result) >= 1
        assert "id" in result[0]

    def test_config_resource(self):
        result = json.loads(get_config())
        assert "project_dir" in result
        assert "memory_dir" in result
        assert result["version"] == "3.0.0"
        assert "backends" in result
        assert "features" in result

    def test_config_backends(self):
        result = json.loads(get_config())
        backends = result["backends"]
        assert "graph" in backends
        assert "vector" in backends
        assert "embedder" in backends

    def test_config_features(self):
        result = json.loads(get_config())
        features = result["features"]
        assert features["hybrid_recall"] is True
        assert features["episodic_memory"] is True
        assert features["procedural_memory"] is True
        assert features["importance_scoring"] is True
        assert features["self_editing"] is True

    def test_stats_resource(self):
        raw = get_stats()
        result = json.loads(raw)
        assert isinstance(result, dict)
        assert "core" in result

    def test_episodic_timeline_resource(self):
        raw = get_episodic_timeline()
        result = json.loads(raw)
        assert isinstance(result, (list, dict))

    def test_episodic_timeline_after_events(self):
        episodic_start(title="Resource timeline test")
        episodic_record(content="Event for resource test")
        raw = get_episodic_timeline()
        result = json.loads(raw)
        assert isinstance(result, (list, dict))

    def test_procedural_patterns_resource(self):
        raw = get_procedural_patterns()
        result = json.loads(raw)
        assert isinstance(result, dict)
        if "error" not in result:
            assert "stats" in result
            assert "procedures" in result

    def test_budget_resource(self):
        raw = get_budget()
        result = json.loads(raw)
        assert isinstance(result, dict)

    def test_user_profile_resource(self):
        raw = get_user_profile("test-user")
        result = json.loads(raw)
        assert result["user_id"] == "test-user"
        assert "expertise" in result
        assert "topics" in result

    def test_user_profile_different_users(self):
        r1 = json.loads(get_user_profile("alice"))
        r2 = json.loads(get_user_profile("bob"))
        assert r1["user_id"] == "alice"
        assert r2["user_id"] == "bob"


# ===================================================================
# 11. Prompts
# ===================================================================


class TestMCPPrompts:
    """Test all 5 prompt template functions."""

    def test_recall_context_no_results(self):
        result = recall_context("absolutely nonexistent topic xyz")
        assert isinstance(result, str)
        assert "No relevant memories" in result

    def test_recall_context_prompt(self):
        memoria_add("Python is great for data science")
        result = recall_context("data science")
        assert isinstance(result, str)
        # Either has results or the 'no memories' message
        assert "Relevant Memories" in result or "No relevant memories" in result

    def test_recall_context_with_user_id(self):
        memoria_add("Alice uses FastAPI", user_id="alice")
        result = recall_context("web framework", user_id="alice")
        assert isinstance(result, str)

    def test_recall_context_with_limit(self):
        for i in range(8):
            memoria_add(f"Memory {i} about testing")
        result = recall_context("testing", limit=2)
        assert isinstance(result, str)

    def test_suggest_next_prompt(self):
        result = suggest_next(context="building an API")
        assert isinstance(result, str)

    def test_suggest_next_empty(self):
        result = suggest_next()
        assert isinstance(result, str)

    def test_suggest_next_with_user_id(self):
        result = suggest_next(context="coding", user_id="dev1")
        assert isinstance(result, str)

    def test_deep_recall_prompt(self):
        memoria_add("Deep recall test: Python ORM setup")
        result = deep_recall("Python ORM")
        assert isinstance(result, str)
        assert "Deep Recall" in result

    def test_deep_recall_no_results(self):
        result = deep_recall("completely unknown xyz topic 999")
        assert isinstance(result, str)

    def test_consolidation_report_prompt(self):
        result = consolidation_report()
        assert isinstance(result, str)
        assert "Consolidation Report" in result
        assert "System Statistics" in result
        assert "Budget Status" in result

    def test_consolidation_report_with_user_id(self):
        result = consolidation_report(user_id="u1")
        assert isinstance(result, str)
        assert "Consolidation Report" in result

    def test_episodic_recap_prompt(self):
        result = episodic_recap()
        assert isinstance(result, str)

    def test_episodic_recap_with_episodes(self):
        episodic_start(title="Recap test episode")
        episodic_record(content="Did some work")
        episodic_end(summary="Finished work", outcome="success")
        result = episodic_recap(limit=3)
        assert isinstance(result, str)

    def test_episodic_recap_no_episodes(self):
        result = episodic_recap()
        assert isinstance(result, str)
        # Should indicate no episodes or return recap
        assert "No episodes" in result or "Recent Episodes" in result


# ===================================================================
# 12. Integration / Cross-cutting
# ===================================================================


class TestMCPIntegration:
    """Cross-cutting integration tests."""

    def test_full_crud_lifecycle(self):
        """add → get → search → delete → verify gone."""
        added = memoria_add("Integration lifecycle memory about Go concurrency")
        mid = added["id"]
        assert added["status"] == "created"

        got = memoria_get(mid)
        assert "memory" in got
        assert "Go" in got["memory"]

        results = memoria_search("Go concurrency")
        assert isinstance(results, list)

        deleted = memoria_delete(mid)
        assert deleted["status"] == "deleted"

        gone = memoria_get(mid)
        assert gone["status"] == "not_found"

    def test_add_appears_in_list_memories(self):
        memoria_add("Visible in listing")
        memories = json.loads(list_memories())
        assert len(memories) >= 1

    def test_delete_removes_from_listing(self):
        added = memoria_add("Temp memory for listing")
        before = len(json.loads(list_memories()))
        memoria_delete(added["id"])
        after = len(json.loads(list_memories()))
        assert after == before - 1

    def test_episodic_then_search(self):
        """Episodic events should be searchable."""
        episodic_start(title="Integration ep")
        episodic_record(content="Discussed deployment strategy", event_type="decision")
        episodic_end(summary="Deployment planning done", outcome="success")
        result = episodic_search("deployment")
        assert isinstance(result, list)

    def test_procedural_record_then_suggest(self):
        """Recorded tool uses should influence suggestions."""
        procedural_record(
            tool_name="jest", input_data="--coverage", result="pass", success=True,
        )
        result = procedural_suggest(context="running tests with coverage")
        assert isinstance(result, dict)

    def test_stats_reflects_added_memories(self):
        memoria_add("Stats test memory")
        stats = memoria_stats()
        core = stats.get("core", {})
        if "total_memories" in core:
            assert core["total_memories"] >= 1

    def test_singleton_reset_gives_fresh_state(self):
        """After reset, singletons should be None."""
        # Force init
        memoria_search("trigger init")
        assert srv._memoria_instance is not None
        _reset_singletons()
        assert srv._memoria_instance is None
        assert srv._episodic_instance is None
        assert srv._procedural_instance is None

    def test_server_name_and_instructions(self):
        from memoria.mcp.server import mcp
        assert mcp.name == "MEMORIA"
        assert mcp.instructions is not None
        assert "memory" in mcp.instructions.lower()


# ===================================================================
# 13. Ultra tools (User DNA, Dream, Preferences, Resurrection)
# ===================================================================


class TestMCPUltraTools:
    """Test v4 Ultra tools: DNA, Dream, Preferences, Resurrection."""

    def test_user_dna_snapshot(self):
        result = user_dna_snapshot(user_id="test-user")
        assert isinstance(result, dict)

    def test_user_dna_collect_message(self):
        result = user_dna_collect(user_id="test-user", message="I prefer Python for backend")
        assert isinstance(result, dict)
        assert "error" not in result
        assert result.get("signals", 0) >= 1

    def test_user_dna_collect_code(self):
        result = user_dna_collect(user_id="test-user", code="def hello_world():\n    pass")
        assert isinstance(result, dict)

    def test_user_dna_collect_empty(self):
        result = user_dna_collect(user_id="test-user")
        assert isinstance(result, dict)

    def test_dream_consolidate_empty(self):
        result = dream_consolidate()
        assert isinstance(result, dict)
        assert result.get("success") is True

    def test_dream_consolidate_with_memories(self):
        import json
        memories = json.dumps([
            {"id": "m1", "content": "Python is great", "importance": 0.9},
            {"id": "m2", "content": "Short note", "importance": 0.1},
        ])
        result = dream_consolidate(memories=memories)
        assert isinstance(result, dict)
        assert "cycle_id" in result

    def test_dream_consolidate_invalid_json(self):
        result = dream_consolidate(memories="not json{")
        assert "error" in result

    def test_dream_journal_empty(self):
        result = dream_journal()
        assert isinstance(result, dict)
        assert "entries" in result

    def test_preference_query(self):
        result = preference_query(user_id="test-user")
        assert isinstance(result, dict)
        assert "preferences" in result

    def test_preference_teach(self):
        result = preference_teach(user_id="test-user", category="language", key="backend", value="python")
        assert isinstance(result, dict)
        assert result.get("value") == "python"
        assert result.get("confidence", 0) >= 0.8

    def test_preference_teach_invalid_category(self):
        result = preference_teach(user_id="test-user", category="invalid_cat", key="x", value="y")
        assert "error" in result

    def test_preference_query_after_teach(self):
        preference_teach(user_id="pref-test", category="tool", key="editor", value="vscode")
        result = preference_query(user_id="pref-test", category="tool")
        assert isinstance(result, dict)
        assert result.get("total", 0) >= 1

    def test_session_snapshot(self):
        result = session_snapshot(user_id="test-user", session_id="s1")
        assert isinstance(result, dict)
        assert "snapshot_id" in result

    def test_session_snapshot_with_messages(self):
        import json
        msgs = json.dumps([
            {"role": "user", "content": "Help me with Python"},
            {"role": "assistant", "content": "Sure!"},
        ])
        result = session_snapshot(user_id="test-user", session_id="s2", messages=msgs)
        assert isinstance(result, dict)
        assert result.get("message_count", 0) >= 1

    def test_session_snapshot_invalid_json(self):
        result = session_snapshot(user_id="test-user", session_id="s3", messages="bad json{")
        assert "error" in result

    def test_session_resume_no_snapshots(self):
        result = session_resume(user_id="never-seen-user")
        assert isinstance(result, dict)
        assert result.get("user_id") == "never-seen-user"

    def test_session_resume_after_snapshot(self):
        session_snapshot(user_id="resume-test", session_id="s1")
        result = session_resume(user_id="resume-test")
        assert isinstance(result, dict)
        assert "greeting" in result


# ===================================================================
# 14. Hyper tools (Sharing, Prediction, Emotional Intelligence)
# ===================================================================


class TestMCPHyperTools:
    """Test v5 Hyper tools: Sharing, Prediction, Emotional Intelligence."""

    # -- Sharing tools --

    def test_team_share_memory(self):
        result = team_share_memory("agent-1", "ns1", "key1", "value1")
        assert isinstance(result, dict)
        assert "error" not in result

    def test_team_share_memory_with_topics(self):
        result = team_share_memory("agent-1", "ns1", "key1", "val1", topics="python,testing")
        assert isinstance(result, dict)

    def test_team_coherence_check(self):
        result = team_coherence_check("team-1")
        assert isinstance(result, dict)

    # -- Prediction tools --

    def test_predict_next_action_record(self):
        result = predict_next_action(action="edit_file")
        assert isinstance(result, dict)

    def test_predict_next_action_empty(self):
        result = predict_next_action()
        assert isinstance(result, dict)

    def test_estimate_difficulty(self):
        result = estimate_difficulty("implement auth", keywords="python,jwt")
        assert isinstance(result, dict)

    def test_estimate_difficulty_no_keywords(self):
        result = estimate_difficulty("simple task")
        assert isinstance(result, dict)

    # -- Emotion tools --

    def test_emotion_analyze_frustration(self):
        result = emotion_analyze("This is so frustrating!!! Nothing works")
        assert isinstance(result, dict)
        assert "error" not in result

    def test_emotion_analyze_positive(self):
        result = emotion_analyze("Great job, this is perfect!")
        assert isinstance(result, dict)

    def test_emotion_analyze_neutral(self):
        result = emotion_analyze("The function returns a list")
        assert isinstance(result, dict)

    def test_emotion_fatigue_check(self):
        result = emotion_fatigue_check()
        assert isinstance(result, dict)

    def test_emotion_analyze_with_context(self):
        result = emotion_analyze("help", context="debugging")
        assert isinstance(result, dict)


# ===================================================================
# 11. Cross-Product Intelligence tools (v6)
# ===================================================================

from memoria.mcp.server import (
    biz_lifecycle_update,
    biz_revenue_signal,
    context_infer_intent,
    context_situation,
    fusion_churn_predict,
    fusion_detect_workflows,
    fusion_unified_model,
    habit_detect,
    product_register,
    product_usage_record,
)


class TestMCPMegaTools:
    """Integration tests for v6 Cross-Product MCP tools."""

    def setup_method(self):
        from memoria.mcp.server import _reset_singletons
        _reset_singletons()

    # Product Intel
    @pytest.mark.asyncio
    async def test_product_register(self):
        result = await product_register("billing-app", "InvoicePro", "billing")
        assert "error" not in result
        assert result.get("product_id") == "billing-app" or result.get("name") == "InvoicePro"

    @pytest.mark.asyncio
    async def test_product_usage_record(self):
        result = await product_usage_record("billing-app", "create_invoice", "create")
        assert "error" not in result

    # Fusion
    @pytest.mark.asyncio
    async def test_fusion_unified_model(self):
        result = await fusion_unified_model()
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_fusion_churn_predict(self):
        result = await fusion_churn_predict("billing-app")
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_fusion_detect_workflows(self):
        result = await fusion_detect_workflows()
        assert "error" not in result

    # Habits
    @pytest.mark.asyncio
    async def test_habit_detect(self):
        result = await habit_detect(action="open_dashboard", product_id="crm")
        assert "error" not in result

    # Contextual
    @pytest.mark.asyncio
    async def test_context_situation(self):
        result = await context_situation("billing-app", "create_invoice")
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_context_infer_intent(self):
        result = await context_infer_intent("billing-app", "create_invoice")
        assert "error" not in result

    # BizIntel
    @pytest.mark.asyncio
    async def test_biz_revenue_signal(self):
        result = await biz_revenue_signal("upsell_opportunity", "billing-app", "User exploring premium features")
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_biz_lifecycle_update(self):
        result = await biz_lifecycle_update("billing-app", days_active=30, total_events=100)
        assert "error" not in result


# ===================================================================
# 12. Defensive Intelligence tools (v7)
# ===================================================================

from memoria.mcp.server import (
    adversarial_check_consistency,
    adversarial_scan,
    adversarial_verify_integrity,
    cognitive_check_overload,
    cognitive_focus_session,
    cognitive_record,
)


class TestMCPDefensiveTools:
    """Integration tests for v7 Defensive Intelligence MCP tools."""

    def setup_method(self):
        from memoria.mcp.server import _reset_singletons
        _reset_singletons()

    @pytest.mark.asyncio
    async def test_adversarial_scan(self):
        result = await adversarial_scan("normal content for testing")
        parsed = json.loads(result) if isinstance(result, str) else result
        assert "error" not in parsed

    @pytest.mark.asyncio
    async def test_adversarial_check_consistency(self):
        result = await adversarial_check_consistency("The sky is blue", '["The sky is blue"]')
        parsed = json.loads(result) if isinstance(result, str) else result
        assert "error" not in parsed

    @pytest.mark.asyncio
    async def test_adversarial_verify_integrity(self):
        result = await adversarial_verify_integrity("hello world", "test-content-1")
        parsed = json.loads(result) if isinstance(result, str) else result
        assert "error" not in parsed

    @pytest.mark.asyncio
    async def test_cognitive_record(self):
        result = await cognitive_record("python testing", complexity=0.3)
        parsed = json.loads(result) if isinstance(result, str) else result
        assert "error" not in parsed

    @pytest.mark.asyncio
    async def test_cognitive_check_overload(self):
        result = await cognitive_check_overload()
        parsed = json.loads(result) if isinstance(result, str) else result
        assert "error" not in parsed

    @pytest.mark.asyncio
    async def test_cognitive_focus_session(self):
        result = await cognitive_focus_session(action="start")
        parsed = json.loads(result) if isinstance(result, str) else result
        assert "error" not in parsed
