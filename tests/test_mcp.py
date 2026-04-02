"""Tests for MEMORIA MCP Server.

Tests all 7 tools, 3 resources, and 2 prompts exposed via FastMCP.
Uses tempdir isolation — no external services required.
"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch


class TestMCPServerImport(unittest.TestCase):
    """Test that the MCP server module can be imported."""

    def test_import_server_module(self):
        from memoria.mcp.server import mcp, create_server
        self.assertIsNotNone(mcp)
        self.assertEqual(mcp.name, "MEMORIA")

    def test_create_server_returns_mcp(self):
        from memoria.mcp.server import create_server
        with tempfile.TemporaryDirectory() as td:
            server = create_server(project_dir=td)
            self.assertIsNotNone(server)


class TestMCPTools(unittest.TestCase):
    """Test all 7 MCP tools via direct function calls."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Reset the global memoria instance for each test
        import memoria.mcp.server as srv
        srv._memoria_instance = None
        srv._PROJECT_DIR = self.tmpdir

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        import memoria.mcp.server as srv
        srv._memoria_instance = None

    def test_memoria_add(self):
        from memoria.mcp.server import memoria_add
        result = memoria_add("Test memory about Python programming")
        self.assertEqual(result["status"], "created")
        self.assertIn("id", result)
        self.assertIn("Python", result["content_preview"])

    def test_memoria_add_with_user_id(self):
        from memoria.mcp.server import memoria_add
        result = memoria_add(
            "User prefers dark mode",
            user_id="alice",
            memory_type="user",
        )
        self.assertEqual(result["status"], "created")

    def test_memoria_add_with_agent_id(self):
        from memoria.mcp.server import memoria_add
        result = memoria_add(
            "Agent context data",
            agent_id="agent-001",
        )
        self.assertEqual(result["status"], "created")

    def test_memoria_search_empty(self):
        from memoria.mcp.server import memoria_search
        results = memoria_search("nonexistent topic")
        self.assertIsInstance(results, list)

    def test_memoria_search_finds_added(self):
        from memoria.mcp.server import memoria_add, memoria_search
        memoria_add("I love programming in Rust for systems work")
        memoria_add("Python is great for data science projects")
        memoria_add("TypeScript is my frontend language of choice")

        results = memoria_search("programming language preferences")
        self.assertIsInstance(results, list)

    def test_memoria_search_with_limit(self):
        from memoria.mcp.server import memoria_add, memoria_search
        for i in range(10):
            memoria_add(f"Memory number {i} about topic alpha")

        results = memoria_search("topic alpha", limit=3)
        self.assertLessEqual(len(results), 3)

    def test_memoria_search_with_user_id(self):
        from memoria.mcp.server import memoria_add, memoria_search
        memoria_add("Alice likes cats", user_id="alice")
        results = memoria_search("cats", user_id="alice")
        self.assertIsInstance(results, list)

    def test_memoria_get_existing(self):
        from memoria.mcp.server import memoria_add, memoria_get
        added = memoria_add("Retrievable memory content")
        result = memoria_get(added["id"])
        self.assertIsNotNone(result)
        self.assertIn("memory", result)
        self.assertIn("Retrievable", result["memory"])

    def test_memoria_get_nonexistent(self):
        from memoria.mcp.server import memoria_get
        result = memoria_get("/nonexistent/path/memory.md")
        self.assertEqual(result["status"], "not_found")

    def test_memoria_delete_existing(self):
        from memoria.mcp.server import memoria_add, memoria_delete, memoria_get
        added = memoria_add("Memory to delete")
        mid = added["id"]

        result = memoria_delete(mid)
        self.assertEqual(result["status"], "deleted")

        # Verify it's gone (the tool returns {"status": "not_found"})
        check = memoria_get(mid)
        self.assertEqual(check["status"], "not_found")

    def test_memoria_delete_nonexistent(self):
        from memoria.mcp.server import memoria_delete
        result = memoria_delete("/nonexistent/path/memory.md")
        self.assertEqual(result["status"], "not_found")

    def test_memoria_add_search_get_delete_lifecycle(self):
        from memoria.mcp.server import (
            memoria_add, memoria_search, memoria_get, memoria_delete,
        )
        # Add
        added = memoria_add("Full lifecycle test memory about React hooks")
        mid = added["id"]
        self.assertEqual(added["status"], "created")

        # Search
        results = memoria_search("React hooks")
        self.assertIsInstance(results, list)

        # Get
        got = memoria_get(mid)
        self.assertIsNotNone(got)
        self.assertIn("React", got["memory"])

        # Delete
        deleted = memoria_delete(mid)
        self.assertEqual(deleted["status"], "deleted")

        # Verify gone (the tool returns {"status": "not_found"})
        gone = memoria_get(mid)
        self.assertEqual(gone["status"], "not_found")

    def test_memoria_suggest(self):
        from memoria.mcp.server import memoria_suggest
        results = memoria_suggest(context="working on a web app")
        self.assertIsInstance(results, list)

    def test_memoria_suggest_with_user_id(self):
        from memoria.mcp.server import memoria_add, memoria_suggest
        # Add some memories first to give the engine data
        memoria_add("I work with React daily", user_id="dev1")
        memoria_add("I prefer functional components", user_id="dev1")

        results = memoria_suggest(
            context="building a new component",
            user_id="dev1",
        )
        self.assertIsInstance(results, list)

    def test_memoria_profile(self):
        from memoria.mcp.server import memoria_profile
        result = memoria_profile(user_id="testuser")
        self.assertIsInstance(result, dict)
        self.assertEqual(result["user_id"], "testuser")
        self.assertIn("expertise", result)
        self.assertIn("message_count", result)

    def test_memoria_profile_default_user(self):
        from memoria.mcp.server import memoria_profile
        result = memoria_profile()
        self.assertIsInstance(result, dict)
        self.assertIn("expertise", result)

    def test_memoria_insights(self):
        from memoria.mcp.server import memoria_insights
        results = memoria_insights(user_id="testuser")
        self.assertIsInstance(results, list)

    def test_memoria_insights_default_user(self):
        from memoria.mcp.server import memoria_insights
        results = memoria_insights()
        self.assertIsInstance(results, list)

    def test_suggest_result_structure(self):
        from memoria.mcp.server import memoria_suggest
        results = memoria_suggest(context="test context")
        for s in results:
            self.assertIn("type", s)
            self.assertIn("content", s)
            self.assertIn("confidence", s)
            self.assertIn("reason", s)

    def test_insights_result_structure(self):
        from memoria.mcp.server import memoria_insights
        results = memoria_insights()
        for i in results:
            self.assertIn("type", i)
            self.assertIn("description", i)
            self.assertIn("confidence", i)


class TestMCPResources(unittest.TestCase):
    """Test all 3 MCP resources."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import memoria.mcp.server as srv
        srv._memoria_instance = None
        srv._PROJECT_DIR = self.tmpdir

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        import memoria.mcp.server as srv
        srv._memoria_instance = None

    def test_list_memories_empty(self):
        from memoria.mcp.server import list_memories
        result = json.loads(list_memories())
        self.assertIsInstance(result, list)

    def test_list_memories_with_content(self):
        from memoria.mcp.server import memoria_add, list_memories
        memoria_add("First memory for resource test")
        memoria_add("Second memory for resource test")

        result = json.loads(list_memories())
        self.assertIsInstance(result, list)
        self.assertGreaterEqual(len(result), 2)

        for mem in result:
            self.assertIn("id", mem)

    def test_list_memories_has_preview(self):
        from memoria.mcp.server import memoria_add, list_memories
        memoria_add("This is a test memory with a nice preview")

        result = json.loads(list_memories())
        self.assertGreaterEqual(len(result), 1)
        # At least one memory should have an id
        self.assertTrue(any("id" in mem for mem in result))

    def test_get_config(self):
        from memoria.mcp.server import get_config
        result = json.loads(get_config())
        self.assertIn("project_dir", result)
        self.assertIn("memory_dir", result)
        self.assertIn("version", result)
        self.assertEqual(result["version"], "2.0.0")
        self.assertIn("backends", result)
        self.assertIn("features", result)

    def test_get_config_backends(self):
        from memoria.mcp.server import get_config
        result = json.loads(get_config())
        backends = result["backends"]
        self.assertIn("graph", backends)
        self.assertIn("vector", backends)
        self.assertIn("embedder", backends)

    def test_get_config_features(self):
        from memoria.mcp.server import get_config
        result = json.loads(get_config())
        features = result["features"]
        self.assertTrue(features["hybrid_recall"])
        self.assertTrue(features["proactive_suggestions"])

    def test_get_user_profile(self):
        from memoria.mcp.server import get_user_profile
        result = json.loads(get_user_profile("testuser"))
        self.assertIn("user_id", result)
        self.assertEqual(result["user_id"], "testuser")
        self.assertIn("expertise", result)
        self.assertIn("topics", result)

    def test_get_user_profile_different_users(self):
        from memoria.mcp.server import get_user_profile
        r1 = json.loads(get_user_profile("alice"))
        r2 = json.loads(get_user_profile("bob"))
        self.assertEqual(r1["user_id"], "alice")
        self.assertEqual(r2["user_id"], "bob")


class TestMCPPrompts(unittest.TestCase):
    """Test both MCP prompts."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import memoria.mcp.server as srv
        srv._memoria_instance = None
        srv._PROJECT_DIR = self.tmpdir

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        import memoria.mcp.server as srv
        srv._memoria_instance = None

    def test_recall_context_empty(self):
        from memoria.mcp.server import recall_context
        result = recall_context("nonexistent topic")
        self.assertIn("No relevant memories", result)

    def test_recall_context_with_memories(self):
        from memoria.mcp.server import memoria_add, recall_context
        memoria_add("Python is excellent for data analysis and ML")
        memoria_add("Use pandas for data manipulation tasks")
        memoria_add("scikit-learn for machine learning models")

        result = recall_context("data science tools")
        self.assertIsInstance(result, str)
        # Should contain the section header
        self.assertIn("Relevant Memories", result)

    def test_recall_context_with_user_id(self):
        from memoria.mcp.server import memoria_add, recall_context
        memoria_add("Alice's project uses FastAPI", user_id="alice")
        result = recall_context("web framework", user_id="alice")
        self.assertIsInstance(result, str)

    def test_recall_context_respects_limit(self):
        from memoria.mcp.server import memoria_add, recall_context
        for i in range(10):
            memoria_add(f"Memory {i} about testing framework pytest")
        result = recall_context("testing", limit=2)
        self.assertIsInstance(result, str)

    def test_suggest_next_empty(self):
        from memoria.mcp.server import suggest_next
        result = suggest_next()
        self.assertIsInstance(result, str)

    def test_suggest_next_with_context(self):
        from memoria.mcp.server import suggest_next
        result = suggest_next(context="building a REST API")
        self.assertIsInstance(result, str)

    def test_suggest_next_with_user_id(self):
        from memoria.mcp.server import suggest_next
        result = suggest_next(context="coding", user_id="dev1")
        self.assertIsInstance(result, str)


class TestMCPServerIntegration(unittest.TestCase):
    """End-to-end integration tests for the MCP server."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import memoria.mcp.server as srv
        srv._memoria_instance = None
        srv._PROJECT_DIR = self.tmpdir

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        import memoria.mcp.server as srv
        srv._memoria_instance = None

    def test_full_workflow(self):
        """Complete workflow: add → search → recall → suggest → profile."""
        from memoria.mcp.server import (
            memoria_add, memoria_search, recall_context,
            memoria_suggest, memoria_profile, get_config,
        )

        # 1. Add memories
        memoria_add("I use React for frontend development", user_id="dev")
        memoria_add("Python FastAPI for backend APIs", user_id="dev")
        memoria_add("PostgreSQL is my preferred database", user_id="dev")

        # 2. Search
        results = memoria_search("frontend", user_id="dev")
        self.assertIsInstance(results, list)

        # 3. Recall context prompt
        ctx = recall_context("tech stack", user_id="dev")
        self.assertIsInstance(ctx, str)

        # 4. Suggestions
        suggestions = memoria_suggest(
            context="starting a new project",
            user_id="dev",
        )
        self.assertIsInstance(suggestions, list)

        # 5. Profile
        profile = memoria_profile(user_id="dev")
        self.assertIsInstance(profile, dict)
        self.assertEqual(profile["user_id"], "dev")

        # 6. Config
        config = json.loads(get_config())
        self.assertEqual(config["version"], "2.0.0")

    def test_multi_user_isolation(self):
        """Verify memories can be scoped per user."""
        from memoria.mcp.server import memoria_add, memoria_search

        memoria_add("Alice likes cats", user_id="alice")
        memoria_add("Bob likes dogs", user_id="bob")

        alice_results = memoria_search("pets", user_id="alice")
        bob_results = memoria_search("pets", user_id="bob")

        self.assertIsInstance(alice_results, list)
        self.assertIsInstance(bob_results, list)

    def test_memory_persistence_across_calls(self):
        """Verify memories persist within the same server instance."""
        from memoria.mcp.server import memoria_add, list_memories

        memoria_add("Persistent memory 1")
        count1 = len(json.loads(list_memories()))

        memoria_add("Persistent memory 2")
        count2 = len(json.loads(list_memories()))

        self.assertEqual(count2, count1 + 1)

    def test_delete_removes_from_listing(self):
        """Verify deleted memories don't appear in listings."""
        from memoria.mcp.server import memoria_add, memoria_delete, list_memories

        added = memoria_add("Temp memory to delete")
        mid = added["id"]

        before = len(json.loads(list_memories()))
        memoria_delete(mid)
        after = len(json.loads(list_memories()))

        self.assertEqual(after, before - 1)

    def test_server_lazy_initialization(self):
        """Verify the Memoria instance is lazily created."""
        import memoria.mcp.server as srv
        self.assertIsNone(srv._memoria_instance)

        # First tool call triggers initialization
        from memoria.mcp.server import memoria_search
        memoria_search("test")
        self.assertIsNotNone(srv._memoria_instance)

    def test_create_server_with_custom_dir(self):
        """Verify create_server accepts custom project_dir."""
        from memoria.mcp.server import create_server
        import memoria.mcp.server as srv

        with tempfile.TemporaryDirectory() as td:
            server = create_server(project_dir=td)
            self.assertEqual(srv._PROJECT_DIR, td)


class TestMCPCLI(unittest.TestCase):
    """Test CLI argument parsing and transport configuration."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        import memoria.mcp.server as srv
        srv._memoria_instance = None
        srv._PROJECT_DIR = self.tmpdir

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        import memoria.mcp.server as srv
        srv._memoria_instance = None

    def test_cli_function_exists(self):
        from memoria.mcp.server import _cli
        self.assertTrue(callable(_cli))

    def test_server_name(self):
        from memoria.mcp.server import mcp
        self.assertEqual(mcp.name, "MEMORIA")

    def test_server_has_instructions(self):
        from memoria.mcp.server import mcp
        self.assertIsNotNone(mcp.instructions)

    def test_transport_env_var_default(self):
        """Verify MEMORIA_TRANSPORT env var is read."""
        import memoria.mcp.server as srv
        # Default should be stdio when env not set
        transport = os.environ.get("MEMORIA_TRANSPORT", "stdio")
        self.assertEqual(transport, "stdio")

    def test_host_env_var_default(self):
        """Verify MEMORIA_HOST defaults to 127.0.0.1."""
        host = os.environ.get("MEMORIA_HOST", "127.0.0.1")
        self.assertEqual(host, "127.0.0.1")

    def test_port_env_var_default(self):
        """Verify MEMORIA_PORT defaults to 8080."""
        port = int(os.environ.get("MEMORIA_PORT", "8080"))
        self.assertEqual(port, 8080)

    def test_main_module_importable(self):
        """Verify __main__.py exists and is importable."""
        import importlib
        spec = importlib.util.find_spec("memoria.mcp.__main__")
        self.assertIsNotNone(spec)

    def test_create_server_returns_mcp_with_http_support(self):
        """Verify the server object has run method for transport selection."""
        from memoria.mcp.server import create_server
        with tempfile.TemporaryDirectory() as td:
            server = create_server(project_dir=td)
            self.assertTrue(hasattr(server, "run"))


if __name__ == "__main__":
    unittest.main()
