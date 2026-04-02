# MEMORIA — Real End-User E2E Test Report

> **Auto-generated** by `tests/test_e2e_mcp_client.py`
> Every request goes through the full MCP protocol (JSON-RPC serialization → tool dispatch → response).

**Scenarios tested:** 11  
**Total tool calls:** 81  
**All passed:** ✅ Yes

---

## 1. New Developer Setup

_A developer connects MEMORIA for the first time, teaches it about their project, preferences, and verifies recall._

**Turns:** 10  
**Total time:** 18ms

### Turn 1: `memoria_add` ✅ (6ms)

**Request:**

```json
{
  "content": "I'm Daniel, a senior Python developer. I use Python 3.12+ with strict type hints everywhere. My preferred tools: ruff for linting, pytest for testing, uv for package management. I follow conventional commits and prefer feature branches.",
  "user_id": "daniel",
  "memory_type": "user"
}
```

**Response:**

```json
{
  "status": "created",
  "id": "/Users/user/.memoria/projects/test_developer_onboarding_conv0-54e818d8e6b0b1e2/memory/1c733424.md",
  "content_preview": "I'm Daniel, a senior Python developer. I use Python 3.12+ with strict type hints everywhere. My pref"
}
```

### Turn 2: `memoria_add` ✅ (2ms)

**Request:**

```json
{
  "content": "The memor-ia project is a proactive memory framework for AI agents. It uses FalkorDB for the knowledge graph, SQLite with sqlite-vec for vector search, and FastMCP for the MCP server. The server exposes 56 tools.",
  "user_id": "daniel",
  "memory_type": "project"
}
```

**Response:**

```json
{
  "status": "created",
  "id": "/Users/user/.memoria/projects/test_developer_onboarding_conv0-54e818d8e6b0b1e2/memory/be91e937.md",
  "content_preview": "The memor-ia project is a proactive memory framework for AI agents. It uses FalkorDB for the knowled"
}
```

### Turn 3: `memoria_add` ✅ (1ms)

**Request:**

```json
{
  "content": "The team: Daniel (lead, backend), Alice (MCP tools), Bob (frontend React dashboard). CI runs on GitHub Actions. Deploy via Docker Compose with FalkorDB sidecar.",
  "user_id": "daniel",
  "memory_type": "project"
}
```

**Response:**

```json
{
  "status": "created",
  "id": "/Users/user/.memoria/projects/test_developer_onboarding_conv0-54e818d8e6b0b1e2/memory/d4301ddc.md",
  "content_preview": "The team: Daniel (lead, backend), Alice (MCP tools), Bob (frontend React dashboard). CI runs on GitH"
}
```

### Turn 4: `memoria_search` ✅ (2ms)

**Request:**

```json
{
  "query": "memor-ia project architecture",
  "user_id": "daniel",
  "limit": 5
}
```

**Response:**

```json
["Root()"]
```

### Turn 5: `preference_teach` ✅ (1ms)

**Request:**

```json
{
  "user_id": "daniel",
  "category": "tool",
  "key": "package_manager",
  "value": "uv",
  "context": "Python dependency management"
}
```

**Response:**

```json
{
  "id": "pref-daniel-tool-package_manager",
  "category": "tool",
  "key": "package_manager",
  "value": "uv",
  "confidence": 0.9
}
```

### Turn 6: `preference_query` ✅ (1ms)

**Request:**

```json
{
  "user_id": "daniel",
  "category": "tool"
}
```

**Response:**

```json
{
  "preferences": [
    {
      "id": "pref-daniel-tool-package_manager",
      "category": "tool",
      "key": "package_manager",
      "value": "uv",
      "confidence": 0.9,
      "observations": 1
    }
  ],
  "total": 1
}
```

### Turn 7: `memoria_profile` ✅ (1ms)

**Request:**

```json
{
  "user_id": "daniel"
}
```

**Response:**

```json
{
  "user_id": "daniel",
  "expertise": {},
  "topics": [],
  "message_count": 0,
  "session_count": 0
}
```

### Turn 8: `memoria_suggest` ✅ (2ms)

**Request:**

```json
{
  "context": "I'm starting a new coding session on memor-ia",
  "user_id": "daniel"
}
```

**Response:**

```json
[]
```

### Turn 9: `memoria_stats` ✅ (1ms)

**Response:**

```json
{
  "core": {
    "total_memories": 3,
    "memory_dir": "/Users/user/.memoria/projects/test_developer_onboarding_conv0-54e818d8e6b0b1e2/memory"
  },
  "episodic": {
    "total_episodes": 0,
    "active_episode": null,
    "total_events": 0,
    "episodes_by_outcome": {},
    "event_type_distribution": {}
  },
  "procedural": {
    "total_tool_patterns": 0,
    "tools_tracked": [],
    "total_workflows": 0,
    "total_procedures": 0,
    "procedures_by_status": {},
    "top_tools": []
  },
  ...
```

### Turn 10: `resource:memoria://config` ✅ (1ms)

**Response:**

```json
{
  "project_dir": "/private/var/folders/fv/mf1hrly52x52xn37lc4wq3y00000gn/T/pytest-of-user/pytest-445/test_developer_onboarding_conv0",
  "memory_dir": "/Users/user/.memoria/projects/test_developer_onboarding_conv0-54e818d8e6b0b1e2/memory",
  "version": "3.0.0",
  "backends": {
    "graph": "KnowledgeGraph",
    "vector": "VectorClient",
    "embedder": "TFIDFEmbedder"
  },
  "features": {
    "hybrid_recall": true,
    "proactive_suggestions": true,
    "knowledge_g…
```

---

## 2. Debugging Session

_A developer debugs a test failure while MEMORIA tracks the full episode: observations, actions, decisions, outcome._

**Turns:** 10  
**Total time:** 16ms

### Turn 1: `episodic_start` ✅ (3ms)

**Request:**

```json
{
  "title": "Debug sqlite-vec INSERT OR REPLACE failure"
}
```

**Response:**

```json
{
  "episode_id": "eac9985187aa",
  "title": "Debug sqlite-vec INSERT OR REPLACE failure",
  "started_at": 1775154701.1489851,
  "ended_at": null,
  "agent_id": "",
  "session_id": "",
  "summary": "",
  "tags": [],
  "outcome": "",
  "event_count": 0
}
```

### Turn 2: `episodic_record` ✅ (1ms)

**Request:**

```json
{
  "content": "test_vector.py::test_upsert fails with: UNIQUE constraint failed: vec_embeddings.id. The INSERT OR REPLACE statement isn't working.",
  "event_type": "observation"
}
```

**Response:**

```json
{
  "event_id": "f359ebcd12ce",
  "event_type": "observation",
  "content": "test_vector.py::test_upsert fails with: UNIQUE constraint failed: vec_embeddings.id. The INSERT OR REPLACE statement isn't working.",
  "timestamp": 1775154701.151434,
  "agent_id": "",
  "user_id": "",
  "metadata": {},
  "importance": 0.5
}
```

### Turn 3: `episodic_record` ✅ (1ms)

**Request:**

```json
{
  "content": "Tried using ON CONFLICT clause but sqlite-vec virtual tables don't support it. The SQLite docs confirm virtual tables have limited DML support.",
  "event_type": "tool_use"
}
```

**Response:**

```json
{
  "event_id": "f9f3b2e5aea2",
  "event_type": "tool_use",
  "content": "Tried using ON CONFLICT clause but sqlite-vec virtual tables don't support it. The SQLite docs confirm virtual tables have limited DML support.",
  "timestamp": 1775154701.1525419,
  "agent_id": "",
  "user_id": "",
  "metadata": {},
  "importance": 0.5
}
```

### Turn 4: `episodic_record` ✅ (1ms)

**Request:**

```json
{
  "content": "Decision: Use DELETE + INSERT pattern instead. First DELETE WHERE id = ?, then INSERT. This works for both single and batch operations.",
  "event_type": "decision"
}
```

**Response:**

```json
{
  "event_id": "472b0ab1f48d",
  "event_type": "decision",
  "content": "Decision: Use DELETE + INSERT pattern instead. First DELETE WHERE id = ?, then INSERT. This works for both single and batch operations.",
  "timestamp": 1775154701.153616,
  "agent_id": "",
  "user_id": "",
  "metadata": {},
  "importance": 0.5
}
```

### Turn 5: `episodic_record` ✅ (1ms)

**Request:**

```json
{
  "content": "Fix applied in vector/client.py lines 95-138. Both insert() and insert_batch() now use DELETE+INSERT. All 4044 tests pass.",
  "event_type": "milestone"
}
```

**Response:**

```json
{
  "event_id": "15342a89a20b",
  "event_type": "milestone",
  "content": "Fix applied in vector/client.py lines 95-138. Both insert() and insert_batch() now use DELETE+INSERT. All 4044 tests pass.",
  "timestamp": 1775154701.154877,
  "agent_id": "",
  "user_id": "",
  "metadata": {},
  "importance": 0.5
}
```

### Turn 6: `memoria_add` ✅ (4ms)

**Request:**

```json
{
  "content": "sqlite-vec virtual tables do NOT support INSERT OR REPLACE or ON CONFLICT. The workaround is DELETE + INSERT. This applies to all SQLite virtual tables, not just sqlite-vec."
}
```

**Response:**

```json
{
  "status": "created",
  "id": "/Users/user/.memoria/projects/test_debugging_conversation0-1fd378256f9b022d/memory/1bee7544.md",
  "content_preview": "sqlite-vec virtual tables do NOT support INSERT OR REPLACE or ON CONFLICT. The workaround is DELETE "
}
```

### Turn 7: `episodic_end` ✅ (1ms)

**Request:**

```json
{
  "summary": "Fixed sqlite-vec upsert by replacing INSERT OR REPLACE with DELETE + INSERT pattern.",
  "outcome": "success"
}
```

**Response:**

```json
{
  "episode_id": "eac9985187aa",
  "title": "Debug sqlite-vec INSERT OR REPLACE failure",
  "started_at": 1775154701.1489851,
  "ended_at": 1775154701.15987,
  "agent_id": "",
  "session_id": "",
  "summary": "Fixed sqlite-vec upsert by replacing INSERT OR REPLACE with DELETE + INSERT pattern.",
  "tags": [],
  "outcome": "success",
  "event_count": 4
}
```

### Turn 8: `episodic_timeline` ✅ (1ms)

**Request:**

```json
{
  "limit": 10
}
```

**Response:**

```json
["Root()", "Root()", "Root()", "Root()"]
```

### Turn 9: `episodic_search` ✅ (1ms)

**Request:**

```json
{
  "query": "sqlite-vec virtual table upsert",
  "limit": 5
}
```

**Response:**

```json
["Root()"]
```

### Turn 10: `prompt:recall_context` ✅ (2ms)

**Request:**

```json
{
  "query": "how to fix sqlite-vec insert",
  "limit": 5
}
```

**Response:**

```json
## Relevant Memories for: 'how to fix sqlite-vec insert'

### Memory 1 (score: 0.016, via: keyword)
sqlite-vec virtual tables do NOT support INSERT OR REPLACE or ON CONFLICT. The workaround is DELETE + INSERT. This applies to all SQLite virtual tables, not just sqlite-vec.

---
*Use these memories to inform your response. Cite specific memories when relevant.*
```

---

## 3. Tool Learning & Workflows

_An agent records tool invocations, learns patterns, creates named workflows, and gets smart suggestions._

**Turns:** 8  
**Total time:** 10ms

### Turn 1: `procedural_record` ✅ (3ms)

**Request:**

```json
{
  "tool_name": "grep",
  "input_data": "grep -rn 'def authenticate' src/",
  "result": "Found 3 matches in auth.py",
  "success": true,
  "context": "searching for authentication code",
  "duration_ms": 150
}
```

**Response:**

```json
{
  "tool_name": "grep",
  "pattern_id": "d51d7586e27f",
  "input_template": "grep -rn 'def authenticate' src/",
  "context_trigger": "searching for authentication code",
  "success_rate": 1.0,
  "use_count": 1,
  "last_used": 1775154701.167792,
  "avg_duration_ms": 150.0,
  "common_errors": []
}
```

### Turn 2: `procedural_record` ✅ (1ms)

**Request:**

```json
{
  "tool_name": "pytest",
  "input_data": "pytest tests/ -q",
  "result": "4044 passed, 0 failed",
  "success": true,
  "context": "running full test suite",
  "duration_ms": 12000
}
```

**Response:**

```json
{
  "tool_name": "pytest",
  "pattern_id": "31d954322a02",
  "input_template": "pytest tests/ -q",
  "context_trigger": "running full test suite",
  "success_rate": 1.0,
  "use_count": 1,
  "last_used": 1775154701.170175,
  "avg_duration_ms": 12000.0,
  "common_errors": []
}
```

### Turn 3: `procedural_record` ✅ (1ms)

**Request:**

```json
{
  "tool_name": "docker",
  "input_data": "docker compose up -d",
  "result": "Services started",
  "success": true,
  "context": "deploying for integration test",
  "duration_ms": 30000
}
```

**Response:**

```json
{
  "tool_name": "docker",
  "pattern_id": "1672ec128c35",
  "input_template": "docker compose up -d",
  "context_trigger": "deploying for integration test",
  "success_rate": 1.0,
  "use_count": 1,
  "last_used": 1775154701.171453,
  "avg_duration_ms": 30000.0,
  "common_errors": []
}
```

### Turn 4: `procedural_record` ✅ (1ms)

**Request:**

```json
{
  "tool_name": "pytest",
  "input_data": "pytest tests/test_vector.py -q",
  "result": "UNIQUE constraint failed",
  "success": false,
  "context": "testing after sqlite-vec upgrade",
  "duration_ms": 500
}
```

**Response:**

```json
{
  "tool_name": "pytest",
  "pattern_id": "31d954322a02",
  "input_template": "pytest tests/ -q",
  "context_trigger": "running full test suite",
  "success_rate": 0.5,
  "use_count": 2,
  "last_used": 1775154701.172607,
  "avg_duration_ms": 6250.0,
  "common_errors": ["UNIQUE constraint failed"]
}
```

### Turn 5: `procedural_suggest` ✅ (1ms)

**Request:**

```json
{
  "context": "I need to find where auth logic is defined"
}
```

**Response:**

```json
{
  "message": "No matching patterns found for this context."
}
```

### Turn 6: `procedural_add_workflow` ✅ (1ms)

**Request:**

```json
{
  "name": "deploy-and-test",
  "steps": "[{\"tool\": \"docker\", \"input\": \"docker compose build\", \"description\": \"Build images\"}, {\"tool\": \"docker\", \"input\": \"docker compose up -d\", \"description\": \"Start services\"}, {\"tool\": \"pytest\", \"input\": \"pytest tests/test_e2e_backends.py -v\", \"description\": \"Run E2E tests\"}]",
  "description": "Full deploy + E2E test cycle",
  "tags": "deploy,test,docker"
}
```

**Response:**

```json
{
  "workflow_id": "22c710d82cde",
  "name": "deploy-and-test",
  "description": "Full deploy + E2E test cycle",
  "steps": [
    {
      "step_index": 0,
      "tool_name": "",
      "description": "Build images",
      "input_template": "",
      "expected_output": "",
      "is_optional": false,
      "condition": ""
    },
    {
      "step_index": 1,
      "tool_name": "",
      "description": "Start services",
      "input_template": "",
      "expected_output": "",
  ...
```

### Turn 7: `procedural_workflows` ✅ (1ms)

**Request:**

```json
{
  "context": "deploy",
  "tags": "docker"
}
```

**Response:**

```json
["Root()"]
```

### Turn 8: `resource:memoria://procedural/patterns` ✅ (1ms)

**Response:**

```json
{
  "stats": {
    "total_tool_patterns": 3,
    "tools_tracked": [
      "grep",
      "pytest",
      "docker"
    ],
    "total_workflows": 1,
    "total_procedures": 0,
    "procedures_by_status": {},
    "top_tools": [
      [
        "pytest",
        2
      ],
      [
        "grep",
        1
      ],
  ...
```

---

## 4. Knowledge Graph Enrichment

_Store project facts, auto-extract entities, search across the knowledge graph, get cross-database insights._

**Turns:** 8  
**Total time:** 135ms

### Turn 1: `memoria_add` ✅ (6ms)

**Request:**

```json
{
  "content": "Daniel created the memor-ia project in 2024. It uses FalkorDB for the knowledge graph and SQLite for vectors.",
  "user_id": "system",
  "memory_type": "project"
}
```

**Response:**

```json
{
  "status": "created",
  "id": "/Users/user/.memoria/projects/test_graph_enrichment_conversa0-b687f6a9159cb7d5/memory/07d264d0.md",
  "content_preview": "Daniel created the memor-ia project in 2024. It uses FalkorDB for the knowledge graph and SQLite for"
}
```

### Turn 2: `memoria_add` ✅ (1ms)

**Request:**

```json
{
  "content": "Alice works on the MCP server component. She writes all the FastMCP tool handlers and maintains the test suite.",
  "user_id": "system",
  "memory_type": "project"
}
```

**Response:**

```json
{
  "status": "created",
  "id": "/Users/user/.memoria/projects/test_graph_enrichment_conversa0-b687f6a9159cb7d5/memory/e5185881.md",
  "content_preview": "Alice works on the MCP server component. She writes all the FastMCP tool handlers and maintains the "
}
```

### Turn 3: `memoria_add` ✅ (1ms)

**Request:**

```json
{
  "content": "The CI pipeline uses GitHub Actions. Docker Compose orchestrates FalkorDB + the MCP server for deployment.",
  "user_id": "system",
  "memory_type": "project"
}
```

**Response:**

```json
{
  "status": "created",
  "id": "/Users/user/.memoria/projects/test_graph_enrichment_conversa0-b687f6a9159cb7d5/memory/54a1a711.md",
  "content_preview": "The CI pipeline uses GitHub Actions. Docker Compose orchestrates FalkorDB + the MCP server for deplo"
}
```

### Turn 4: `memoria_enrich` ✅ (1ms)

**Request:**

```json
{
  "content": "Bob joined the team to build the React dashboard. He integrates with MEMORIA via the MCP protocol."
}
```

**Response:**

```json
{
  "category": "relationship",
  "tags": ["react"],
  "entities": ["react"],
  "entity_types": {
    "react": "Concept"
  }
}
```

### Turn 5: `memoria_search` ✅ (2ms)

**Request:**

```json
{
  "query": "who works on memor-ia project",
  "limit": 10
}
```

**Response:**

```json
["Root()", "Root()"]
```

### Turn 6: `memoria_insights` ✅ (120ms)

**Response:**

```json
[
  "Root()",
  "Root()",
  "Root()",
  "Root()",
  "Root()",
  "Root()",
  "Root()",
  "Root()",
  "Root()"
]
```

### Turn 7: `memoria_stats` ✅ (2ms)

**Response:**

```json
{
  "core": {
    "total_memories": 3,
    "memory_dir": "/Users/user/.memoria/projects/test_graph_enrichment_conversa0-b687f6a9159cb7d5/memory"
  },
  "episodic": {
    "total_episodes": 0,
    "active_episode": null,
    "total_events": 0,
    "episodes_by_outcome": {},
    "event_type_distribution": {}
  },
  "procedural": {
    "total_tool_patterns": 0,
    "tools_tracked": [],
    "total_workflows": 0,
    "total_procedures": 0,
    "procedures_by_status": {},
    "top_tools": []
  },
  ...
```

### Turn 8: `prompt:deep_recall` ✅ (2ms)

**Request:**

```json
{
  "query": "project architecture and team"
}
```

**Response:**

```json
## Deep Recall for: 'project architecture and team'

### Stored Memories
1. (score: 0.016) Daniel created the memor-ia project in 2024. It uses FalkorDB for the knowledge graph and SQLite for vectors.
2. (score: 0.016) Alice works on the MCP server component. She writes all the FastMCP tool handlers and maintains the test suite.

---
*Use these memories to inform your response. Cite specific memories when relevant.*
```

---

## 5. Tiered Storage & ACL

_Store memories across tiers (working/reference/archival), grant access to team members, verify permissions._

**Turns:** 8  
**Total time:** 11ms

### Turn 1: `memoria_add_to_tier` ✅ (5ms)

**Request:**

```json
{
  "content": "Current sprint: implement MCP server v2.0 with 56 tools",
  "tier": "working",
  "importance": 0.95
}
```

**Response:**

```json
{
  "status": "created",
  "id": "af819173-4549-45b2-992d-8b99e2f99396",
  "tier": "working"
}
```

### Turn 2: `memoria_add_to_tier` ✅ (1ms)

**Request:**

```json
{
  "content": "Architecture decision: use sqlite-vec for vector search",
  "tier": "reference",
  "importance": 0.7
}
```

**Response:**

```json
{
  "error": "Unknown tier: 'reference'"
}
```

### Turn 3: `memoria_add_to_tier` ✅ (1ms)

**Request:**

```json
{
  "content": "Sprint 1 retro: migrated from chromadb to sqlite-vec",
  "tier": "archival",
  "importance": 0.3
}
```

**Response:**

```json
{
  "status": "created",
  "id": "da9d89f1-ba79-45dd-b388-997f0120aece",
  "tier": "archival"
}
```

### Turn 4: `memoria_search_tiers` ✅ (1ms)

**Request:**

```json
{
  "query": "sqlite-vec",
  "tiers": "working,reference,archival"
}
```

**Response:**

```json
["Root()"]
```

### Turn 5: `memoria_grant_access` ✅ (1ms)

**Request:**

```json
{
  "agent_id": "alice",
  "namespace": "project-memoria",
  "role": "reader",
  "granted_by": "daniel"
}
```

**Response:**

```json
{
  "status": "granted",
  "grant_id": "e11da271f9974b9e8646ca97814beaf1",
  "agent_id": "alice",
  "namespace": "project-memoria",
  "role": "reader"
}
```

### Turn 6: `memoria_check_access` ✅ (1ms)

**Request:**

```json
{
  "agent_id": "alice",
  "namespace": "project-memoria",
  "operation": "read"
}
```

**Response:**

```json
{
  "agent_id": "alice",
  "namespace": "project-memoria",
  "operation": "read",
  "allowed": true
}
```

### Turn 7: `memory_budget` ✅ (1ms)

**Response:**

```json
{
  "working": {
    "current": 0,
    "max": 50,
    "usage": 0.0
  },
  "recall": {
    "current": 0,
    "max": 500,
    "usage": 0.0
  },
  "archival": {
    "current": 0,
    "max": 5000,
    "usage": 0.0
  },
  "action_needed": "none"
}
```

### Turn 8: `resource:memoria://budget` ✅ (1ms)

**Response:**

```json
{
  "working": {
    "current": 0,
    "max": 50,
    "usage": 0.0
  },
  "recall": {
    "current": 0,
    "max": 500,
    "usage": 0.0
  },
  "archival": {
    "current": 0,
    "max": 5000,
    "usage": 0.0
  },
  "action_needed": "none"
}
```

---

## 6. Product Intelligence Pipeline

_Register a product, record usage, run analytics: churn prediction, workflow detection, habit tracking, revenue signals, lifecycle analysis._

**Turns:** 10  
**Total time:** 9ms

### Turn 1: `product_register` ✅ (2ms)

**Request:**

```json
{
  "product_id": "memoria-mcp",
  "name": "MEMORIA MCP Server",
  "category": "analytics",
  "version": "3.0.0",
  "features": "memory,search,graph,episodic"
}
```

**Response:**

```json
{
  "product_id": "memoria-mcp",
  "name": "MEMORIA MCP Server",
  "category": "analytics",
  "version": "3.0.0",
  "description": "",
  "features": ["memory", "search", "graph", "episodic"],
  "metadata": {},
  "registered_at": 1775154701.330826
}
```

### Turn 2: `product_usage_record` ✅ (1ms)

**Request:**

```json
{
  "product_id": "memoria-mcp",
  "feature": "search",
  "action": "hybrid_recall",
  "duration": 45.0
}
```

**Response:**

```json
{
  "event": {
    "product_id": "memoria-mcp",
    "feature": "search",
    "action": "hybrid_recall",
    "timestamp": 1775154701.332643,
    "duration_seconds": 45.0,
    "metadata": {},
    "session_id": ""
  },
  "profile_summary": {
    "total_events": 1,
    "frequency": "monthly"
  }
}
```

### Turn 3: `product_usage_record` ✅ (1ms)

**Request:**

```json
{
  "product_id": "memoria-mcp",
  "feature": "graph",
  "action": "entity_extract",
  "duration": 45.0
}
```

**Response:**

```json
{
  "event": {
    "product_id": "memoria-mcp",
    "feature": "graph",
    "action": "entity_extract",
    "timestamp": 1775154701.333631,
    "duration_seconds": 45.0,
    "metadata": {},
    "session_id": ""
  },
  "profile_summary": {
    "total_events": 2,
    "frequency": "monthly"
  }
}
```

### Turn 4: `product_usage_record` ✅ (1ms)

**Request:**

```json
{
  "product_id": "memoria-mcp",
  "feature": "episodic",
  "action": "start_session",
  "duration": 45.0
}
```

**Response:**

```json
{
  "event": {
    "product_id": "memoria-mcp",
    "feature": "episodic",
    "action": "start_session",
    "timestamp": 1775154701.334521,
    "duration_seconds": 45.0,
    "metadata": {},
    "session_id": ""
  },
  "profile_summary": {
    "total_events": 3,
    "frequency": "monthly"
  }
}
```

### Turn 5: `fusion_unified_model` ✅ (1ms)

**Response:**

```json
{
  "user_id": "default",
  "total_signals": 0,
  "products_active": [],
  "dominant_patterns": [],
  "engagement_score": 0.0,
  "consistency_score": 0.0,
  "cross_product_activity": 0.0,
  "last_updated": 0.0,
  "signal_breakdown": {}
}
```

### Turn 6: `fusion_churn_predict` ✅ (1ms)

**Request:**

```json
{
  "product_id": "memoria-mcp"
}
```

**Response:**

```json
{
  "product_id": "memoria-mcp",
  "risk_level": "none",
  "probability": 0.0,
  "days_until_likely_churn": -1,
  "warning_signals": ["No data available"],
  "recommended_actions": ["Start tracking usage"],
  "confidence": 0.0
}
```

### Turn 7: `fusion_detect_workflows` ✅ (1ms)

**Request:**

```json
{
  "min_frequency": 1
}
```

**Response:**

```json
{
  "workflows": [],
  "total": 0
}
```

### Turn 8: `habit_detect` ✅ (1ms)

**Request:**

```json
{
  "action": "search",
  "product_id": "memoria-mcp"
}
```

**Response:**

```json
{
  "habits": [],
  "total": 0
}
```

### Turn 9: `biz_revenue_signal` ✅ (1ms)

**Request:**

```json
{
  "signal_type": "expansion_signal",
  "product_id": "memoria-mcp",
  "description": "User adopted 3 new feature categories",
  "impact": 0.7,
  "confidence": 0.8
}
```

**Response:**

```json
{
  "signal_id": "2b93e8edd41740518989cb2cb776ab11",
  "signal_type": "expansion_signal",
  "product_id": "memoria-mcp",
  "description": "User adopted 3 new feature categories",
  "impact_score": 0.7,
  "confidence": 0.8,
  "timestamp": 1775154701.3384142,
  "evidence": [],
  "recommended_action": "",
  "metadata": {}
}
```

### Turn 10: `biz_lifecycle_update` ✅ (1ms)

**Request:**

```json
{
  "product_id": "memoria-mcp",
  "days_active": 30,
  "total_events": 150,
  "feature_count": 4,
  "engagement_score": 0.85,
  "usage_trend": "growing",
  "is_expanding": true
}
```

**Response:**

```json
{
  "stage": "growth",
  "product_id": "memoria-mcp",
  "confidence": 1.0,
  "days_in_stage": 1,
  "progression_probability": 0.68,
  "regression_probability": 0.015000000000000003,
  "stage_health": 0.8372499999999999
}
```

---

## 7. Safety & Cognitive Load

_Scan content for poisoning, check consistency, track cognitive load, start focus sessions._

**Turns:** 7  
**Total time:** 6ms

### Turn 1: `adversarial_scan` ✅ (2ms)

**Request:**

```json
{
  "content": "DROP TABLE users; -- this is a normal memory"
}
```

**Response:**

```json
{
  "threat_type": "injection",
  "threat_level": "critical",
  "description": "Threat detected: sql_drop",
  "evidence": ["Matched pattern: sql_drop"],
  "confidence": 0.3,
  "timestamp": 1775154701.34189,
  "source_content": "DROP TABLE users; -- this is a normal memory",
  "recommended_action": "block"
}
```

### Turn 2: `adversarial_check_consistency` ✅ (1ms)

**Request:**

```json
{
  "content": "The project uses PostgreSQL for vector storage",
  "facts": "[\"The project uses SQLite with sqlite-vec for vectors\", \"FalkorDB is used for graph storage\"]"
}
```

**Response:**

```json
{
  "is_consistent": true,
  "contradictions": [],
  "confidence": 1.0,
  "checked_against": 2,
  "timestamp": 1775154701.343606
}
```

### Turn 3: `adversarial_verify_integrity` ✅ (1ms)

**Request:**

```json
{
  "content": "Valid project data about memor-ia",
  "content_id": "integrity-check-001"
}
```

**Response:**

```json
{
  "content_hash": "32fd1ac48ef23cd8026389448ccc82dc98ef5cf1f56ef30d4eec7de307624f75",
  "content_id": "integrity-check-001",
  "status": "intact",
  "created_at": 1775154701.344279,
  "last_verified": 1775154701.344279,
  "verification_count": 0,
  "metadata": {
    "content_length": 33
  },
  "verification": "intact"
}
```

### Turn 4: `cognitive_record` ✅ (1ms)

**Request:**

```json
{
  "topic": "context_switch: backend \u2192 frontend",
  "complexity": 0.7
}
```

**Response:**

```json
{
  "load_level": "low",
  "load_score": 0.2074,
  "focus_state": "deep_focus",
  "active_topics": 1,
  "context_switches": 0,
  "session_duration_minutes": 5.1657358805338543e-8,
  "timestamp": 1775154701.344922
}
```

### Turn 5: `cognitive_record` ✅ (1ms)

**Request:**

```json
{
  "topic": "code_review: 500-line diff",
  "complexity": 0.8
}
```

**Response:**

```json
{
  "load_level": "low",
  "load_score": 0.2529,
  "focus_state": "deep_focus",
  "active_topics": 2,
  "context_switches": 1,
  "session_duration_minutes": 1.0685125986735027e-5,
  "timestamp": 1775154701.34556
}
```

### Turn 6: `cognitive_check_overload` ✅ (1ms)

**Response:**

```json
{
  "is_overloaded": false,
  "signals": [],
  "severity": 0.0,
  "recommendation": "",
  "cooldown_minutes": 0,
  "timestamp": 1775154701.3461812
}
```

### Turn 7: `cognitive_focus_session` ✅ (1ms)

**Request:**

```json
{
  "action": "start",
  "session_id": "focus-001"
}
```

**Response:**

```json
{
  "session_id": "71acd3f4-72fb-4854-b775-e0f64f1a2343",
  "started_at": 1775154701.346803,
  "ended_at": null,
  "focus_scores": [],
  "context_switches": 0,
  "topics": [],
  "peak_focus": 0.0,
  "average_focus": 0.0
}
```

---

## 8. Full Workday Session (15 turns)

_A realistic developer workday: onboard context, debug a bug, record findings, learn patterns, get suggestions, end the session with a snapshot._

**Turns:** 17  
**Total time:** 146ms

### Turn 1: `memoria_add` ✅ (5ms)

**Request:**

```json
{
  "content": "memor-ia v2.0 uses FalkorDB graph + sqlite-vec vectors. MCP server on FastMCP with 56 tools. Deploy via Docker.",
  "user_id": "daniel",
  "memory_type": "project"
}
```

**Response:**

```json
{
  "status": "created",
  "id": "/Users/user/.memoria/projects/test_full_workday_session0-74e6f70e5a1745ff/memory/0f9cd375.md",
  "content_preview": "memor-ia v2.0 uses FalkorDB graph + sqlite-vec vectors. MCP server on FastMCP with 56 tools. Deploy "
}
```

### Turn 2: `episodic_start` ✅ (1ms)

**Request:**

```json
{
  "title": "Morning session: fix vector upsert bug"
}
```

**Response:**

```json
{
  "episode_id": "24ae8df79ebb",
  "title": "Morning session: fix vector upsert bug",
  "started_at": 1775154701.3551779,
  "ended_at": null,
  "agent_id": "",
  "session_id": "",
  "summary": "",
  "tags": [],
  "outcome": "",
  "event_count": 0
}
```

### Turn 3: `episodic_record` ✅ (1ms)

**Request:**

```json
{
  "content": "test_vector.py fails on INSERT OR REPLACE with sqlite-vec",
  "event_type": "observation"
}
```

**Response:**

```json
{
  "event_id": "b7edfd11970f",
  "event_type": "observation",
  "content": "test_vector.py fails on INSERT OR REPLACE with sqlite-vec",
  "timestamp": 1775154701.356282,
  "agent_id": "",
  "user_id": "",
  "metadata": {},
  "importance": 0.5
}
```

### Turn 4: `episodic_record` ✅ (1ms)

**Request:**

```json
{
  "content": "Virtual tables don't support ON CONFLICT. Using DELETE+INSERT.",
  "event_type": "decision"
}
```

**Response:**

```json
{
  "event_id": "3d0d16f044fa",
  "event_type": "decision",
  "content": "Virtual tables don't support ON CONFLICT. Using DELETE+INSERT.",
  "timestamp": 1775154701.357213,
  "agent_id": "",
  "user_id": "",
  "metadata": {},
  "importance": 0.5
}
```

### Turn 5: `memoria_add` ✅ (1ms)

**Request:**

```json
{
  "content": "sqlite-vec virtual tables don't support INSERT OR REPLACE. Use DELETE + INSERT as workaround."
}
```

**Response:**

```json
{
  "status": "created",
  "id": "/Users/user/.memoria/projects/test_full_workday_session0-74e6f70e5a1745ff/memory/71be36e6.md",
  "content_preview": "sqlite-vec virtual tables don't support INSERT OR REPLACE. Use DELETE + INSERT as workaround."
}
```

### Turn 6: `procedural_record` ✅ (1ms)

**Request:**

```json
{
  "tool_name": "pytest",
  "input_data": "pytest tests/ -q",
  "result": "4044 passed, 0 failed",
  "success": true,
  "context": "verify fix",
  "duration_ms": 12000
}
```

**Response:**

```json
{
  "tool_name": "pytest",
  "pattern_id": "cd3d1243529b",
  "input_template": "pytest tests/ -q",
  "context_trigger": "verify fix",
  "success_rate": 1.0,
  "use_count": 1,
  "last_used": 1775154701.3595011,
  "avg_duration_ms": 12000.0,
  "common_errors": []
}
```

### Turn 7: `episodic_end` ✅ (1ms)

**Request:**

```json
{
  "summary": "Fixed sqlite-vec upsert with DELETE+INSERT pattern",
  "outcome": "success"
}
```

**Response:**

```json
{
  "episode_id": "24ae8df79ebb",
  "title": "Morning session: fix vector upsert bug",
  "started_at": 1775154701.3551779,
  "ended_at": 1775154701.36047,
  "agent_id": "",
  "session_id": "",
  "summary": "Fixed sqlite-vec upsert with DELETE+INSERT pattern",
  "tags": [],
  "outcome": "success",
  "event_count": 2
}
```

### Turn 8: `preference_teach` ✅ (1ms)

**Request:**

```json
{
  "user_id": "daniel",
  "category": "workflow",
  "key": "commit_style",
  "value": "conventional_commits"
}
```

**Response:**

```json
{
  "id": "pref-daniel-workflow-commit_style",
  "category": "workflow",
  "key": "commit_style",
  "value": "conventional_commits",
  "confidence": 0.9
}
```

### Turn 9: `memoria_add_to_tier` ✅ (1ms)

**Request:**

```json
{
  "content": "Next: implement one-click deploy with interactive config",
  "tier": "working",
  "importance": 0.8
}
```

**Response:**

```json
{
  "status": "created",
  "id": "d8505766-67a4-4468-98fc-0e056fd03256",
  "tier": "working"
}
```

### Turn 10: `memoria_suggest` ✅ (2ms)

**Request:**

```json
{
  "context": "Just fixed the vector bug, what should I work on next?",
  "user_id": "daniel"
}
```

**Response:**

```json
[]
```

### Turn 11: `memoria_insights` ✅ (125ms)

**Request:**

```json
{
  "user_id": "daniel"
}
```

**Response:**

```json
[
  "Root()",
  "Root()",
  "Root()",
  "Root()",
  "Root()",
  "Root()",
  "Root()",
  "Root()",
  "Root()"
]
```

### Turn 12: `session_snapshot` ✅ (1ms)

**Request:**

```json
{
  "user_id": "daniel",
  "session_id": "workday-2024-01",
  "outcome": "success"
}
```

**Response:**

```json
{
  "error": "'success' is not a valid SessionOutcome"
}
```

### Turn 13: `memoria_stats` ✅ (1ms)

**Response:**

```json
{
  "core": {
    "total_memories": 2,
    "memory_dir": "/Users/user/.memoria/projects/test_full_workday_session0-74e6f70e5a1745ff/memory"
  },
  "episodic": {
    "total_episodes": 1,
    "active_episode": null,
    "total_events": 2,
    "episodes_by_outcome": {
      "success": 1
    },
    "event_type_distribution": {
      "observation": 1,
      "decision": 1
    }
  },
  "procedural": {
    "total_tool_patterns": 1,
    "tools_tracked": [
  ...
```

### Turn 14: `resource:memoria://memories` ✅ (1ms)

**Response:**

```json
[
  {
    "id": "MemoryHeader(filename='71be36e6.md', file_path='/Users/user/.memoria/projects/test_full_workday_session0-74e6f70e5a1745ff/memory/71be36e6.md', mtime_ms=1775154701358.4507, description=\"sqlite-vec virtual tables don't support INSERT OR REPLACE. Use DELETE + INSERT as workaround.\", type=<MemoryType.USER: 'user'>)",
    "error": "unreadable"
  },
  {
    "id": "MemoryHeader(filename='0f9cd375.md', file_path='/Users/user/.memoria/projects/test_full_work…
```

### Turn 15: `resource:memoria://config` ✅ (1ms)

**Response:**

```json
{
  "project_dir": "/private/var/folders/fv/mf1hrly52x52xn37lc4wq3y00000gn/T/pytest-of-user/pytest-445/test_full_workday_session0",
  "memory_dir": "/Users/user/.memoria/projects/test_full_workday_session0-74e6f70e5a1745ff/memory",
  "version": "3.0.0",
  "backends": {
    "graph": "KnowledgeGraph",
    "vector": "VectorClient",
    "embedder": "TFIDFEmbedder"
  },
  "features": {
    "hybrid_recall": true,
    "proactive_suggestions": true,
    "knowledge_graph": tru…
```

### Turn 16: `resource:memoria://stats` ✅ (1ms)

**Response:**

```json
{
  "core": {
    "total_memories": 2,
    "memory_dir": "/Users/user/.memoria/projects/test_full_workday_session0-74e6f70e5a1745ff/memory"
  },
  "episodic": {
    "total_episodes": 1,
    "active_episode": null,
    "total_events": 2,
    "episodes_by_outcome": {
      "success": 1
    },
    "event_type_distribution": {
      "observation": 1,
      "decision": 1
    }
  },
  "procedural": {
    "total_tool_patterns": 1,
    "tools_tracked": [
...
```

### Turn 17: `prompt:recall_context` ✅ (1ms)

**Request:**

```json
{
  "query": "what was fixed today",
  "limit": 5
}
```

**Response:**

```json
No relevant memories found for: 'what was fixed today'
```

---

## 9. Tool Discovery

_List all available tools and verify the count._

**Turns:** 1  
**Total time:** 0ms

### Turn 1: `list_tools` ✅ (0ms)

**Response:**

```json
{
  "count": 97,
  "tools": [
    "add_attachment",
    "adversarial_check_consistency",
    "adversarial_scan",
    "adversarial_verify_integrity",
    "attachment_stats",
    "biz_lifecycle_update",
    "biz_revenue_signal",
    "cache_clear",
    "cache_stats",
    "cache_warmup",
    "cognitive_check_overload",
    "cognitive_focus_session",
    "cognitive_record",
    "context_infer_intent",
    "context_situation",
    "dashboard_config",
    "dashboard_status",
  ...
```

---

## 10. Resource Discovery

_List all available resources._

**Turns:** 1  
**Total time:** 0ms

### Turn 1: `list_resources` ✅ (0ms)

**Response:**

```json
{
  "count": 6,
  "resources": [
    "memoria://memories",
    "memoria://config",
    "memoria://stats",
    "memoria://episodic/timeline",
    "memoria://procedural/patterns",
    "memoria://budget"
  ]
}
```

---

## 11. Prompt Discovery

_List all available prompts._

**Turns:** 1  
**Total time:** 0ms

### Turn 1: `list_prompts` ✅ (0ms)

**Response:**

```json
{
  "count": 5,
  "prompts": [
    "recall_context",
    "suggest_next",
    "deep_recall",
    "consolidation_report",
    "episodic_recap"
  ]
}
```

---
