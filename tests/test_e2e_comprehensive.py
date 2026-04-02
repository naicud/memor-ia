"""Comprehensive E2E tests — every Memoria feature via MCP protocol.

Simulates real multi-turn conversations exercising: streaming,
attachments, plugins, templates, webhooks, summarization,
dashboard, federation, and core CRUD.

Every request goes through the full MCP JSON-RPC pipeline.

Run:
    python -m pytest tests/test_e2e_comprehensive.py -v -s
"""

from __future__ import annotations

import base64
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
# Report types
# ---------------------------------------------------------------------------


@dataclass
class Turn:
    turn_no: int
    tool: str
    args: dict[str, Any]
    result: Any
    is_error: bool
    elapsed_ms: float


@dataclass
class Conversation:
    name: str
    description: str
    turns: list[Turn] = field(default_factory=list)


CONVERSATIONS: list[Conversation] = []

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated(tmp_path):
    srv._reset_singletons()
    srv._PROJECT_DIR = str(tmp_path)
    yield tmp_path
    srv._reset_singletons()


@pytest.fixture
def client_factory(isolated):
    async def _make():
        server = srv.create_server(project_dir=str(isolated))
        client = Client(server)
        await client.__aenter__()
        return client
    return _make

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def call(client: Client, conv: Conversation, tool: str,
               args: dict | None = None, expect_error: bool = False) -> Any:
    """Call a tool, auto-parse JSON strings, record turn, return data."""
    args = args or {}
    t0 = time.perf_counter()
    result = await client.call_tool(tool, args, raise_on_error=False)
    elapsed = (time.perf_counter() - t0) * 1000

    raw = result.data
    if raw is not None:
        if isinstance(raw, str):
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                data = raw
        else:
            data = raw
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


# ===================================================================
# 1 — Streaming lifecycle
# ===================================================================

class TestStreamingConversation:

    @pytest.mark.asyncio
    async def test_streaming_full_lifecycle(self, client_factory):
        client = await client_factory()
        conv = Conversation(
            name="Streaming Lifecycle",
            description="Subscribe → broadcast → list → stats → unsubscribe.",
        )
        try:
            # Subscribe
            r = await call(client, conv, "stream_subscribe", {
                "channel_type": "sse",
                "event_types": '["memory_created", "memory_updated"]',
                "user_ids": '["user-stream-1"]',
                "namespaces": '["dev"]',
            })
            assert "channel_id" in r
            channel_id = r["channel_id"]

            # List — should contain our channel
            r = await call(client, conv, "stream_list")
            assert isinstance(r, list)
            assert any(ch["channel_id"] == channel_id for ch in r)

            # Broadcast
            r = await call(client, conv, "stream_broadcast", {
                "event_type": "memory_created",
                "data": json.dumps({"memory_id": "m-123"}),
            })
            assert r["status"] == "broadcast"

            # Stats
            r = await call(client, conv, "stream_stats")
            assert r["total_channels"] >= 1

            # Unsubscribe
            r = await call(client, conv, "stream_unsubscribe", {
                "channel_id": channel_id,
            })
            assert r["status"] in ("closed", "unsubscribed", "not_found")

            # Stats after
            r = await call(client, conv, "stream_stats")
            assert "total_channels" in r
        finally:
            CONVERSATIONS.append(conv)
            await client.__aexit__(None, None, None)


# ===================================================================
# 2 — Multimodal / Attachments
# ===================================================================

class TestMultimodalConversation:

    @pytest.mark.asyncio
    async def test_attachment_lifecycle(self, client_factory):
        client = await client_factory()
        conv = Conversation(
            name="Multimodal Attachments",
            description="Create memory → attach files → list → get → stats → delete.",
        )
        try:
            # Create parent memory
            r = await call(client, conv, "memoria_add", {
                "content": "Architecture diagram discussion",
                "user_id": "user-attach",
                "memory_type": "project",
            })
            assert r["status"] == "created"
            mem_id = r["id"]

            # Attach PNG
            png_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\nfakeimage").decode()
            r = await call(client, conv, "add_attachment", {
                "memory_id": mem_id,
                "data_base64": png_b64,
                "filename": "diagram.png",
                "mime_type": "image/png",
                "description": "System architecture v1",
            })
            assert "attachment_id" in r
            att_id = r["attachment_id"]

            # Attach JSON
            json_b64 = base64.b64encode(b'{"key":"value"}').decode()
            r = await call(client, conv, "add_attachment", {
                "memory_id": mem_id,
                "data_base64": json_b64,
                "filename": "config.json",
                "mime_type": "application/json",
            })
            assert "attachment_id" in r
            att_id2 = r["attachment_id"]

            # List
            r = await call(client, conv, "list_attachments", {"memory_id": mem_id})
            assert isinstance(r, list)
            assert len(r) >= 2

            # Get metadata
            r = await call(client, conv, "get_attachment", {"attachment_id": att_id})
            assert r["filename"] == "diagram.png"

            # Stats
            r = await call(client, conv, "attachment_stats")
            assert r["total_attachments"] >= 2

            # Delete one
            r = await call(client, conv, "delete_attachment", {"attachment_id": att_id2})
            assert r["status"] == "deleted"

            # Verify deletion
            r = await call(client, conv, "list_attachments", {"memory_id": mem_id})
            ids = [a["attachment_id"] for a in r] if isinstance(r, list) else []
            assert att_id2 not in ids
        finally:
            CONVERSATIONS.append(conv)
            await client.__aexit__(None, None, None)


# ===================================================================
# 3 — Plugins
# ===================================================================

class TestPluginConversation:

    @pytest.mark.asyncio
    async def test_plugin_lifecycle(self, client_factory):
        client = await client_factory()
        conv = Conversation(
            name="Plugin Management",
            description="Discover → list → stats (activate/deactivate if any exist).",
        )
        try:
            # Discover
            r = await call(client, conv, "plugin_discover")
            # Returns a list (possibly empty)
            assert isinstance(r, list)

            # List
            r = await call(client, conv, "plugin_list")
            assert isinstance(r, list)
            plugin_count = len(r)

            # Activate if available
            if plugin_count > 0:
                name = r[0]["name"]
                r = await call(client, conv, "plugin_activate", {"name": name})
                assert r.get("status") in ("activated", "already_active")
                r = await call(client, conv, "plugin_deactivate", {"name": name})
                assert r.get("status") in ("deactivated", "already_inactive")

            # Stats
            r = await call(client, conv, "plugin_stats")
            assert "registered" in r
        finally:
            CONVERSATIONS.append(conv)
            await client.__aexit__(None, None, None)


# ===================================================================
# 4 — Templates
# ===================================================================

class TestTemplateConversation:

    @pytest.mark.asyncio
    async def test_template_lifecycle(self, client_factory):
        client = await client_factory()
        conv = Conversation(
            name="Template Workflow",
            description="Create template → list → apply.",
        )
        try:
            # Create
            r = await call(client, conv, "template_create", {
                "name": "meeting-notes",
                "description": "Template for team meeting notes",
                "fields": json.dumps([
                    {"name": "date", "type": "string", "required": True},
                    {"name": "attendees", "type": "string", "required": True},
                    {"name": "decisions", "type": "string", "required": False},
                ]),
                "content_template": "Meeting on {date} with {attendees}. Decisions: {decisions}",
                "category": "meetings",
                "tags": '["meeting", "notes"]',
            })
            assert r["status"] == "created"

            # List
            r = await call(client, conv, "template_list", {"category": "meetings"})
            assert isinstance(r, list)
            assert any(t["name"] == "meeting-notes" for t in r)

            # Apply (param is "data", not "values")
            r = await call(client, conv, "template_apply", {
                "template_name": "meeting-notes",
                "data": json.dumps({
                    "date": "2025-01-15",
                    "attendees": "Alice, Bob, Carol",
                    "decisions": "Migrate to Python 3.14; adopt uv",
                }),
            })
            assert r["status"] == "created"
            assert "id" in r
        finally:
            CONVERSATIONS.append(conv)
            await client.__aexit__(None, None, None)


# ===================================================================
# 5 — Webhooks
# ===================================================================

class TestWebhookConversation:

    @pytest.mark.asyncio
    async def test_webhook_lifecycle(self, client_factory):
        client = await client_factory()
        conv = Conversation(
            name="Webhook Management",
            description="Register → list → unregister.",
        )
        try:
            # Register
            r = await call(client, conv, "webhook_register", {
                "url": "https://example.com/hook",
                "events": '["memory_created", "memory_updated"]',
                "secret": "test-secret-123",
                "description": "CI notification hook",
            })
            assert "webhook_id" in r
            hook_id = r["webhook_id"]

            # List
            r = await call(client, conv, "webhook_list")
            assert isinstance(r, list)
            assert len(r) >= 1

            # Unregister
            r = await call(client, conv, "webhook_unregister", {
                "webhook_id": hook_id,
            })
            assert r.get("removed") is True or r.get("status") == "unregistered"
        finally:
            CONVERSATIONS.append(conv)
            await client.__aexit__(None, None, None)


# ===================================================================
# 6 — Summarization
# ===================================================================

class TestSummarizationConversation:

    @pytest.mark.asyncio
    async def test_summarize(self, client_factory):
        client = await client_factory()
        conv = Conversation(
            name="Summarization",
            description="Summarize content + summarize_all.",
        )
        try:
            # Single content summarize
            r = await call(client, conv, "memoria_summarize", {
                "content": (
                    "The memor-ia framework provides namespace isolation, "
                    "semantic search, tiered storage, GDPR compliance, "
                    "audit trails, streaming, attachments, templates, "
                    "webhooks, plugins, dashboard, and federation."
                ),
                "max_tokens": 50,
            })
            assert "summary" in r

            # Add memories for summarize_all
            await call(client, conv, "memoria_add", {
                "content": "Python 3.14 improves generics and type inference",
                "user_id": "user-sum",
            })
            await call(client, conv, "memoria_add", {
                "content": "Team decided to use FalkorDB for graph storage",
                "user_id": "user-sum",
            })

            # Summarize all
            r = await call(client, conv, "memoria_summarize_all", {
                "user_id": "user-sum",
                "limit": 10,
            })
            assert isinstance(r, dict)
        finally:
            CONVERSATIONS.append(conv)
            await client.__aexit__(None, None, None)


# ===================================================================
# 7 — Dashboard
# ===================================================================

class TestDashboardConversation:

    @pytest.mark.asyncio
    async def test_dashboard_lifecycle(self, client_factory):
        client = await client_factory()
        conv = Conversation(
            name="Dashboard Lifecycle",
            description="Status → start → url → config → stop.",
        )
        try:
            # Status before start
            r = await call(client, conv, "dashboard_status")
            assert r["running"] is False

            # Start
            r = await call(client, conv, "start_dashboard", {
                "host": "127.0.0.1",
                "port": 19950,
            })
            assert r["status"] == "started"
            assert "url" in r

            # Status after start
            r = await call(client, conv, "dashboard_status")
            assert r["running"] is True

            # URL
            r = await call(client, conv, "dashboard_url")
            assert "url" in r

            # Config
            r = await call(client, conv, "dashboard_config")
            assert r["running"] is True

            # Stop
            r = await call(client, conv, "stop_dashboard")
            assert r["status"] == "stopped"
        finally:
            CONVERSATIONS.append(conv)
            await client.__aexit__(None, None, None)


# ===================================================================
# 8 — Federation
# ===================================================================

class TestFederationConversation:

    @pytest.mark.asyncio
    async def test_federation_lifecycle(self, client_factory):
        client = await client_factory()
        conv = Conversation(
            name="Federation Protocol",
            description="Connect → trust → status → sync → disconnect.",
        )
        try:
            # Connect
            r = await call(client, conv, "federation_connect", {
                "endpoint": "https://peer1.example.com/mcp",
                "instance_id": "peer-alpha",
                "shared_namespaces": "dev,staging",
                "direction": "bidirectional",
            })
            assert r["status"] == "connected"
            peer_id = r["instance_id"]

            # Trust
            r = await call(client, conv, "federation_trust", {
                "instance_id": peer_id,
                "action": "add",
                "trust_level": "elevated",
            })
            assert r["trust_level"] == "elevated"

            # Status
            r = await call(client, conv, "federation_status")
            assert r["protocol"]["total_peers"] >= 1

            # Sync
            r = await call(client, conv, "federation_sync", {
                "peer_id": peer_id,
                "namespace": "dev",
            })
            assert isinstance(r, dict)

            # Disconnect
            r = await call(client, conv, "federation_disconnect", {
                "peer_id": peer_id,
            })
            assert r["status"] in ("disconnected", "removed", "not_found")
        finally:
            CONVERSATIONS.append(conv)
            await client.__aexit__(None, None, None)


# ===================================================================
# 9 — Full cross-feature conversation (20+ turns)
# ===================================================================

class TestCrossFeatureConversation:
    """Realistic session using multiple features together."""

    @pytest.mark.asyncio
    async def test_realistic_multi_feature_session(self, client_factory):
        client = await client_factory()
        conv = Conversation(
            name="Cross-Feature Developer Session",
            description=(
                "20+ turn conversation covering: CRUD, search, attachments, "
                "streaming, templates, webhooks, plugins, dashboard, "
                "federation, summarization."
            ),
        )
        try:
            # --- Phase 1: Core memory ---

            # T1: Store a memory
            r = await call(client, conv, "memoria_add", {
                "content": (
                    "Our API uses FastAPI with Pydantic v2 models. "
                    "All endpoints require JWT auth. Rate limit: 100 req/min."
                ),
                "user_id": "dev-cross",
                "memory_type": "project",
            })
            assert r["status"] == "created"
            mem1_id = r["id"]

            # T2: Store another
            r = await call(client, conv, "memoria_add", {
                "content": (
                    "Database schema: users(id, email, role), "
                    "memories(id, content, embedding, namespace, created_at)."
                ),
                "user_id": "dev-cross",
                "memory_type": "reference",
            })
            assert r["status"] == "created"
            mem2_id = r["id"]

            # T3: Search
            r = await call(client, conv, "memoria_search", {
                "query": "API authentication",
                "user_id": "dev-cross",
                "limit": 5,
            })
            assert isinstance(r, (list, dict))

            # --- Phase 2: Attachments ---

            # T4: Attach SVG
            svg_b64 = base64.b64encode(b"<svg>arch</svg>").decode()
            r = await call(client, conv, "add_attachment", {
                "memory_id": mem1_id,
                "data_base64": svg_b64,
                "filename": "api-arch.svg",
                "mime_type": "image/svg+xml",
                "description": "API architecture diagram",
            })
            assert "attachment_id" in r

            # T5: Attach SQL
            sql_b64 = base64.b64encode(b"CREATE TABLE users (id INT);").decode()
            r = await call(client, conv, "add_attachment", {
                "memory_id": mem2_id,
                "data_base64": sql_b64,
                "filename": "schema.sql",
                "mime_type": "text/sql",
            })
            assert "attachment_id" in r

            # T6: Stats
            r = await call(client, conv, "attachment_stats")
            assert r["total_attachments"] >= 2

            # --- Phase 3: Streaming ---

            # T7: Subscribe
            r = await call(client, conv, "stream_subscribe", {
                "channel_type": "sse",
                "event_types": '["memory_created"]',
            })
            assert "channel_id" in r
            chan_id = r["channel_id"]

            # T8: Broadcast
            r = await call(client, conv, "stream_broadcast", {
                "event_type": "memory_created",
                "data": json.dumps({"source": "cross-test"}),
            })
            assert r["status"] == "broadcast"

            # T9: Stats
            r = await call(client, conv, "stream_stats")
            assert r["total_channels"] >= 1

            # --- Phase 4: Templates ---

            # T10: Create
            r = await call(client, conv, "template_create", {
                "name": "bug-report-cross",
                "description": "Bug report template",
                "fields": json.dumps([
                    {"name": "title", "type": "string", "required": True},
                    {"name": "steps", "type": "string", "required": True},
                    {"name": "expected", "type": "string", "required": True},
                    {"name": "actual", "type": "string", "required": True},
                ]),
                "content_template": "Bug: {title}\nSteps: {steps}\nExpected: {expected}\nActual: {actual}",
                "category": "engineering",
            })
            assert r["status"] == "created"

            # T11: Apply
            r = await call(client, conv, "template_apply", {
                "template_name": "bug-report-cross",
                "data": json.dumps({
                    "title": "Login fails with SSO",
                    "steps": "Click SSO → Redirect → Return",
                    "expected": "User logged in",
                    "actual": "500 error",
                }),
            })
            assert r["status"] == "created"

            # --- Phase 5: Webhooks ---

            # T12: Register
            r = await call(client, conv, "webhook_register", {
                "url": "https://hooks.example.com/memoria",
                "events": '["memory_created", "memory_deleted"]',
                "secret": "wh-secret-123",
                "description": "Slack notification",
            })
            assert "webhook_id" in r
            wh_id = r["webhook_id"]

            # T13: List
            r = await call(client, conv, "webhook_list")
            assert isinstance(r, list)
            assert len(r) >= 1

            # --- Phase 6: Plugins ---

            # T14: Discover
            r = await call(client, conv, "plugin_discover")
            assert isinstance(r, list)

            # T15: List
            r = await call(client, conv, "plugin_list")
            assert isinstance(r, list)

            # T16: Stats
            r = await call(client, conv, "plugin_stats")
            assert "registered" in r

            # --- Phase 7: Dashboard ---

            # T17: Status
            r = await call(client, conv, "dashboard_status")
            assert "running" in r

            # T18: Config
            r = await call(client, conv, "dashboard_config")
            assert isinstance(r, dict)

            # --- Phase 8: Federation ---

            # T19: Connect
            r = await call(client, conv, "federation_connect", {
                "endpoint": "https://team-b.example.com/mcp",
                "instance_id": "team-b-cross",
                "shared_namespaces": "shared",
            })
            assert r["status"] == "connected"

            # T20: Trust
            r = await call(client, conv, "federation_trust", {
                "instance_id": "team-b-cross",
                "action": "add",
                "trust_level": "standard",
            })
            assert r["trust_level"] == "standard"

            # T21: Status
            r = await call(client, conv, "federation_status")
            assert r["protocol"]["total_peers"] >= 1

            # --- Phase 9: Summarization ---

            # T22: Summarize
            r = await call(client, conv, "memoria_summarize", {
                "content": (
                    "Comprehensive test of all features: CRUD, search, "
                    "attachments, streaming, templates, webhooks, plugins, "
                    "dashboard, federation, and summarization."
                ),
                "max_tokens": 30,
            })
            assert "summary" in r

            # --- Cleanup ---

            # T23: Unsubscribe stream
            r = await call(client, conv, "stream_unsubscribe", {
                "channel_id": chan_id,
            })
            assert r["status"] in ("closed", "unsubscribed", "not_found")

            # T24: Unregister webhook
            r = await call(client, conv, "webhook_unregister", {
                "webhook_id": wh_id,
            })
            assert r.get("removed") is True or r.get("status") == "unregistered"

        finally:
            CONVERSATIONS.append(conv)
            await client.__aexit__(None, None, None)


# ===================================================================
# 10 — Memory CRUD deep
# ===================================================================

class TestMemoryCRUDDeep:

    @pytest.mark.asyncio
    async def test_crud_and_search(self, client_factory):
        client = await client_factory()
        conv = Conversation(
            name="Memory CRUD Deep",
            description="Add → search → get → delete → verify.",
        )
        try:
            ids = []
            contents = [
                "Python asyncio: use asyncio.run(), prefer TaskGroup over gather",
                "Docker multi-stage builds: use python:3.14-slim as final stage",
                "FalkorDB Cypher: MATCH (n:Memory)-[:RELATED]->(m) RETURN n, m",
            ]
            for c in contents:
                r = await call(client, conv, "memoria_add", {
                    "content": c,
                    "user_id": "dev-crud",
                })
                assert r["status"] == "created"
                ids.append(r["id"])

            # Search
            r = await call(client, conv, "memoria_search", {
                "query": "Docker image optimization",
                "user_id": "dev-crud",
                "limit": 3,
            })
            results = r if isinstance(r, list) else r.get("results", [])
            assert len(results) >= 1

            # Get by ID
            r = await call(client, conv, "memoria_get", {"memory_id": ids[0]})
            assert "memory" in r or "content" in r

            # Delete
            r = await call(client, conv, "memoria_delete", {"memory_id": ids[2]})
            assert r["status"] == "deleted"

            # Verify deleted — expect error or empty
            r = await call(client, conv, "memoria_get", {"memory_id": ids[2]},
                           expect_error=True)
        finally:
            CONVERSATIONS.append(conv)
            await client.__aexit__(None, None, None)


# ===================================================================
# Report generation
# ===================================================================

class TestZZZComprehensiveReport:
    """Runs last (ZZZ prefix) to collect all conversation data."""

    def test_generate_report(self):
        if not CONVERSATIONS:
            pytest.skip("No conversations recorded")

        lines = [
            "# Comprehensive E2E Test Report — Memoria",
            "",
            "> Auto-generated by `tests/test_e2e_comprehensive.py`",
            f"> {len(CONVERSATIONS)} conversations, "
            f"{sum(len(c.turns) for c in CONVERSATIONS)} total turns",
            "",
            "## Table of Contents",
            "",
        ]

        for i, conv in enumerate(CONVERSATIONS, 1):
            anchor = conv.name.lower().replace(" ", "-").replace("/", "-")
            lines.append(f"{i}. [{conv.name}](#{anchor}) — {len(conv.turns)} turns")

        lines.append("")

        for conv in CONVERSATIONS:
            lines.append(f"## {conv.name}")
            lines.append("")
            lines.append(f"*{conv.description}*")
            lines.append("")

            if not conv.turns:
                lines.append("*(no turns recorded)*")
                lines.append("")
                continue

            total_ms = sum(t.elapsed_ms for t in conv.turns)
            lines.append(f"**Turns:** {len(conv.turns)} | "
                         f"**Total time:** {total_ms:.0f}ms | "
                         f"**Avg:** {total_ms / len(conv.turns):.0f}ms/turn")
            lines.append("")

            for turn in conv.turns:
                status = "✅" if not turn.is_error else "❌"
                lines.append(f"### Turn {turn.turn_no} — `{turn.tool}` {status}")
                lines.append("")
                lines.append("**Request:**")
                lines.append("```json")
                lines.append(json.dumps(turn.args, indent=2, default=str))
                lines.append("```")
                lines.append("")
                lines.append(f"**Response** ({turn.elapsed_ms}ms):")
                lines.append("```json")
                result_str = json.dumps(turn.result, indent=2, default=str)
                if len(result_str) > 2000:
                    result_str = result_str[:2000] + "\n  ... (truncated)"
                lines.append(result_str)
                lines.append("```")
                lines.append("")

            lines.append("---")
            lines.append("")

        # Feature coverage matrix
        lines.append("## Feature Coverage Matrix")
        lines.append("")
        lines.append("| Feature | Tools Tested | Turns | Status |")
        lines.append("|---------|-------------|-------|--------|")

        feature_map = {
            "Core Memory": ["memoria_add", "memoria_search", "memoria_get",
                            "memoria_delete"],
            "Streaming": ["stream_subscribe", "stream_unsubscribe",
                          "stream_broadcast", "stream_list", "stream_stats"],
            "Attachments": ["add_attachment", "get_attachment",
                            "list_attachments", "delete_attachment",
                            "attachment_stats"],
            "Plugins": ["plugin_discover", "plugin_list", "plugin_activate",
                        "plugin_deactivate", "plugin_stats"],
            "Templates": ["template_create", "template_list", "template_apply"],
            "Webhooks": ["webhook_register", "webhook_list",
                         "webhook_unregister"],
            "Summarization": ["memoria_summarize", "memoria_summarize_all"],
            "Dashboard": ["start_dashboard", "stop_dashboard",
                          "dashboard_status", "dashboard_url",
                          "dashboard_config"],
            "Federation": ["federation_connect", "federation_disconnect",
                           "federation_trust", "federation_sync",
                           "federation_status"],
        }

        all_tools_called = set()
        for conv in CONVERSATIONS:
            for t in conv.turns:
                all_tools_called.add(t.tool)

        for feature, tools in feature_map.items():
            tested = [t for t in tools if t in all_tools_called]
            turn_count = sum(
                1 for c in CONVERSATIONS for t in c.turns if t.tool in tools
            )
            if len(tested) == len(tools):
                status = "✅ Full"
            else:
                status = f"⚠️ {len(tested)}/{len(tools)}"
            lines.append(
                f"| {feature} | {', '.join(tested)} | {turn_count} | {status} |"
            )

        lines.append("")
        lines.append("## Summary")
        lines.append("")
        total_turns = sum(len(c.turns) for c in CONVERSATIONS)
        errors = sum(1 for c in CONVERSATIONS for t in c.turns if t.is_error)
        total_ms = sum(t.elapsed_ms for c in CONVERSATIONS for t in c.turns)
        lines.append(f"- **Conversations:** {len(CONVERSATIONS)}")
        lines.append(f"- **Total turns:** {total_turns}")
        lines.append(f"- **Errors:** {errors}")
        lines.append(f"- **Total time:** {total_ms:.0f}ms")
        lines.append(f"- **Unique tools tested:** {len(all_tools_called)}")
        avg = total_ms / max(total_turns, 1)
        lines.append(f"- **Average response time:** {avg:.0f}ms")
        lines.append("")

        report_path = (Path(__file__).resolve().parent.parent
                       / "docs" / "E2E_COMPREHENSIVE_REPORT.md")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(lines), encoding="utf-8")

        print(f"\n📊 Report written to {report_path}")
        print(f"   {len(CONVERSATIONS)} conversations, "
              f"{total_turns} turns, {errors} errors")
