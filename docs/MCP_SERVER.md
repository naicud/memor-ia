# MEMORIA MCP Server — v2.0.0

Complete guide to using MEMORIA as a [Model Context Protocol](https://modelcontextprotocol.io/) server.

MEMORIA exposes **97 tools**, **6 resources**, and **5 prompts** via [FastMCP 3.0+](https://github.com/jlowin/fastmcp), supporting **stdio**, **HTTP**, **WebSocket**, and **SSE** transports.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [Transports](#transports)
- [Client Configuration](#client-configuration)
  - [Claude Desktop](#claude-desktop)
  - [Cursor](#cursor)
  - [VS Code + Continue](#vs-code--continue)
  - [Generic MCP Client](#generic-mcp-client)
- [Docker Deployment](#docker-deployment)
- [Environment Variables](#environment-variables)
- [Tools Reference](#tools-reference)
  - [Core CRUD (7)](#core-crud-7-tools)
  - [Tiered Storage & ACL (5)](#tiered-storage--acl-5-tools)
  - [Sync & Stats (2)](#sync--stats-2-tools)
  - [Episodic Memory (5)](#episodic-memory-5-tools)
  - [Procedural Memory (4)](#procedural-memory-4-tools)
  - [Importance & Self-Edit (3)](#importance--self-edit-3-tools)
  - [User DNA (2)](#user-dna-2-tools)
  - [Dream Engine (2)](#dream-engine-2-tools)
  - [Preferences (2)](#preferences-2-tools)
  - [Context Resurrection (2)](#context-resurrection-2-tools)
  - [Team Sharing (2)](#team-sharing-2-tools)
  - [Prediction (2)](#prediction-2-tools)
  - [Emotional Intelligence (2)](#emotional-intelligence-2-tools)
  - [Product Intelligence (2)](#product-intelligence-2-tools)
  - [Behavioral Fusion (3)](#behavioral-fusion-3-tools)
  - [Habit Intelligence (1)](#habit-intelligence-1-tool)
  - [Contextual Intelligence (2)](#contextual-intelligence-2-tools)
  - [Business Intelligence (2)](#business-intelligence-2-tools)
  - [Adversarial Protection (3)](#adversarial-protection-3-tools)
  - [Cognitive Load (3)](#cognitive-load-3-tools)
- [Resources Reference](#resources-reference)
- [Prompts Reference](#prompts-reference)

---

## Quick Start

```bash
# Install with MCP support
pip install -e ".[mcp]"

# Start in stdio mode (for Claude Desktop, Cursor, etc.)
memoria-mcp

# Start in HTTP mode (for web clients, testing)
memoria-mcp --transport http --port 8080
```

---

## Installation

```bash
# Minimal (MCP server only, pure-Python backends)
pip install -e ".[mcp]"

# With FalkorDB graph backend
pip install -e ".[mcp,graph]"

# With SQLite-vec vector backend
pip install -e ".[mcp,vector]"

# Full install (all backends)
pip install -e ".[full]"
```

**Requirements:** Python ≥ 3.11

### With UV (recommended)

```bash
uv pip install -e ".[full]"
```

---

## Transports

MEMORIA supports 4 MCP transports:

| Transport | Use Case | Command |
|-----------|----------|---------|
| **stdio** | Claude Desktop, Cursor, local editors | `memoria-mcp` |
| **HTTP** | Web apps, REST clients, debugging | `memoria-mcp --transport http` |
| **WebSocket** | Real-time bidirectional communication | Via FastMCP config |
| **SSE** | Server-Sent Events, streaming | Via FastMCP config |

### stdio (default)

Standard I/O transport — the MCP client spawns the server as a subprocess. This is the standard for editor integrations.

```bash
memoria-mcp
# or explicitly:
memoria-mcp --transport stdio
```

### HTTP

HTTP transport exposes the MCP server as an HTTP endpoint. Useful for testing with `curl`, web integrations, and remote deployments.

```bash
memoria-mcp --transport http --host 0.0.0.0 --port 8080
```

The server exposes these endpoints:
- `POST /mcp` — MCP JSON-RPC endpoint
- `GET /health` — Health check

---

## Client Configuration

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "memoria": {
      "command": "memoria-mcp",
      "args": [],
      "env": {
        "MEMORIA_DATA_DIR": "/path/to/your/project"
      }
    }
  }
}
```

With UV (recommended for isolated environments):

```json
{
  "mcpServers": {
    "memoria": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/naicud/memor-ia.git", "memoria-mcp"],
      "env": {
        "MEMORIA_DATA_DIR": "/path/to/your/project"
      }
    }
  }
}
```

With FalkorDB graph backend:

```json
{
  "mcpServers": {
    "memoria": {
      "command": "memoria-mcp",
      "args": [],
      "env": {
        "MEMORIA_DATA_DIR": "/path/to/your/project",
        "MEMORIA_GRAPH_HOST": "localhost",
        "MEMORIA_GRAPH_PORT": "6379"
      }
    }
  }
}
```

### Cursor

Add to `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "memoria": {
      "command": "memoria-mcp",
      "args": [],
      "env": {
        "MEMORIA_DATA_DIR": "."
      }
    }
  }
}
```

### VS Code + Continue

Add to `.continue/config.json`:

```json
{
  "mcpServers": [
    {
      "name": "memoria",
      "command": "memoria-mcp",
      "args": [],
      "env": {
        "MEMORIA_DATA_DIR": "${workspaceFolder}"
      }
    }
  ]
}
```

### Generic MCP Client

Any MCP-compatible client can connect via stdio:

```python
import subprocess
import json

proc = subprocess.Popen(
    ["memoria-mcp"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    env={"MEMORIA_DATA_DIR": "/my/project"}
)

# Send MCP JSON-RPC requests via stdin
request = {
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
        "name": "memoria_add",
        "arguments": {
            "content": "User prefers TypeScript",
            "user_id": "daniel"
        }
    },
    "id": 1
}
proc.stdin.write(json.dumps(request).encode() + b"\n")
proc.stdin.flush()
```

Or connect via HTTP:

```bash
# Store a memory
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "memoria_add",
      "arguments": {
        "content": "User prefers TypeScript for frontend",
        "user_id": "daniel"
      }
    },
    "id": 1
  }'

# Search memories
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "memoria_search",
      "arguments": {
        "query": "language preferences",
        "user_id": "daniel"
      }
    },
    "id": 2
  }'
```

---

## Docker Deployment

### Quick Start with Docker Compose

```bash
# Start MEMORIA + FalkorDB
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f memoria-mcp

# Stop
docker compose down
```

This starts:
- **memoria-mcp** on port 8080 (HTTP transport)
- **falkordb** on port 6379 (graph backend)

### Docker Only (no FalkorDB)

```bash
# Build
docker build -t memoria-mcp .

# Run with pure-Python backends
docker run -p 8080:8080 \
  -v memoria-data:/app/data \
  -e MEMORIA_TRANSPORT=http \
  -e MEMORIA_HOST=0.0.0.0 \
  -e MEMORIA_PORT=8080 \
  memoria-mcp
```

### Custom docker-compose.yml

```yaml
services:
  memoria-mcp:
    build: .
    ports:
      - "8080:8080"
    environment:
      - MEMORIA_TRANSPORT=http
      - MEMORIA_HOST=0.0.0.0
      - MEMORIA_PORT=8080
      - MEMORIA_GRAPH_HOST=falkordb
      - MEMORIA_GRAPH_PORT=6379
      - MEMORIA_VECTOR_DB=/app/data/vectors.db
      - MEMORIA_EMBEDDING_DIM=384
      - MEMORIA_DATA_DIR=/app/data
    volumes:
      - memoria-data:/app/data
    depends_on:
      - falkordb

  falkordb:
    image: falkordb/falkordb:latest
    ports:
      - "6379:6379"
    volumes:
      - falkordb-data:/data

volumes:
  memoria-data:
  falkordb-data:
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MEMORIA_TRANSPORT` | MCP transport protocol (`stdio` or `http`) | `stdio` |
| `MEMORIA_HOST` | HTTP server bind address | `127.0.0.1` |
| `MEMORIA_PORT` | HTTP server port | `8080` |
| `MEMORIA_DATA_DIR` | Memory storage directory | Current working directory |
| `MEMORIA_GRAPH_HOST` | FalkorDB host (enables graph backend) | _(not set — uses InMemoryGraph)_ |
| `MEMORIA_GRAPH_PORT` | FalkorDB port | `6379` |
| `MEMORIA_VECTOR_DB` | SQLite vector database path | _(not set — uses in-memory)_ |
| `MEMORIA_EMBEDDING_DIM` | Embedding vector dimension | `384` |

### Backend Selection

MEMORIA automatically selects backends based on configuration:

| Backend | Condition | Fallback |
|---------|-----------|----------|
| **Graph** | `MEMORIA_GRAPH_HOST` is set + `falkordb` installed | InMemoryGraph (pure Python) |
| **Vector** | `MEMORIA_VECTOR_DB` is set | In-memory SQLite |
| **Embeddings** | Always available | TF-IDF hash-trick (no ML deps) |
| **Core Storage** | Always available | Markdown files with YAML frontmatter |

---

## Tools Reference

### Core CRUD (7 tools)

The fundamental memory operations.

#### `memoria_add`

Store a new memory.

```
Parameters:
  content: str          — Memory content text (required)
  user_id: str | None   — Owner user ID
  agent_id: str | None  — Agent that created the memory
  memory_type: str | None — Type: user, feedback, project, reference

Returns: dict
  { "status": "ok", "memory_id": "user/2024-01-15_preferences.md" }
```

**Example:** "User prefers dark mode and TypeScript for all frontend projects"

#### `memoria_search`

Search memories using the hybrid recall pipeline (keyword + vector + graph → RRF fusion).

```
Parameters:
  query: str            — Search query (required)
  user_id: str | None   — Filter by user
  limit: int            — Max results (default: 5)
  offset: int           — Skip first N results for pagination (default: 0)

Returns: list[dict]
  [{ "id": "...", "content": "...", "score": 0.87, "metadata": {...} }]
```

#### `memoria_get`

Retrieve a specific memory by its path/ID.

```
Parameters:
  memory_id: str        — Memory file path (required)

Returns: dict
  { "id": "...", "content": "...", "metadata": {...}, "frontmatter": {...} }
```

#### `memoria_delete`

Delete a memory by its path/ID.

```
Parameters:
  memory_id: str        — Memory file path (required)

Returns: dict
  { "status": "ok", "deleted": "user/2024-01-15_preferences.md" }
```

#### `memoria_suggest`

Generate proactive suggestions based on current context and stored patterns.

```
Parameters:
  context: str          — Current context/situation (default: "")
  user_id: str | None   — User to generate suggestions for

Returns: list[dict]
  [{ "suggestion": "...", "confidence": 0.8, "reason": "..." }]
```

#### `memoria_profile`

Build a user profile from interaction history.

```
Parameters:
  user_id: str | None   — User to profile

Returns: dict
  { "expertise": {...}, "preferences": {...}, "patterns": {...}, "topics": [...] }
```

#### `memoria_insights`

Generate cross-database insights from stored memories.

```
Parameters:
  user_id: str | None   — User to analyze

Returns: list[dict]
  [{ "insight": "...", "confidence": 0.9, "sources": [...] }]
```

---

### Tiered Storage & ACL (5 tools)

Multi-tier memory management and access control.

#### `memoria_add_to_tier`

Add a memory to a specific storage tier.

```
Parameters:
  content: str          — Memory content (required)
  tier: str             — Target tier: "working", "recall", or "archival" (default: "working")
  metadata: str | None  — JSON metadata string
  importance: float | None — Importance score 0.0-1.0

Returns: dict
```

**Tiers:**
- **working** — Active, frequently accessed memories (hot)
- **recall** — Important but less frequently accessed (warm)
- **archival** — Long-term storage, rarely accessed (cold)

#### `memoria_search_tiers`

Search across memory tiers.

```
Parameters:
  query: str            — Search query (required)
  tiers: str | None     — Comma-separated tier names (default: all tiers)
  limit: int            — Max results (default: 10)
  offset: int           — Skip first N results for pagination (default: 0)

Returns: list[dict]
```

#### `memoria_grant_access`

Grant an agent access to a memory namespace.

```
Parameters:
  agent_id: str         — Agent to grant access to (required)
  namespace: str        — Memory namespace (required)
  role: str             — Access role: "reader", "writer", "admin" (default: "reader")
  granted_by: str       — Who granted access (default: "system")

Returns: dict
```

#### `memoria_check_access`

Check if an agent has access to a namespace.

```
Parameters:
  agent_id: str         — Agent to check (required)
  namespace: str        — Namespace to check (required)
  operation: str        — Operation: "read", "write", "admin" (default: "read")

Returns: dict
  { "allowed": true, "role": "writer", "namespace": "shared-project" }
```

#### `memoria_enrich`

Enrich content with automatic category, tags, and entity extraction.

```
Parameters:
  content: str          — Content to enrich (required)

Returns: dict
  { "category": "...", "tags": [...], "entities": [...], "importance": 0.7 }
```

---

### Sync & Stats (2 tools)

#### `memoria_sync`

Sync memories with configured remote transport.

```
Parameters:
  namespace: str | None — Namespace to sync (default: all)

Returns: dict
```

#### `memoria_stats`

Get comprehensive memory statistics.

```
Returns: dict
  {
    "total_memories": 42,
    "by_type": { "user": 15, "project": 20, "feedback": 7 },
    "tiers": { "working": 30, "recall": 10, "archival": 2 },
    "episodes": { "total": 5, "active": 1 },
    "graph": { "nodes": 85, "edges": 120 }
  }
```

---

### Episodic Memory (5 tools)

Record and query time-based episodes (conversations, sessions, events).

#### `episodic_start`

Start a new episode.

```
Parameters:
  title: str            — Episode title (default: "")
  agent_id: str         — Agent starting the episode (default: "")
  session_id: str       — External session ID (default: "")

Returns: dict
  { "episode_id": "ep_2024-01-15_001", "status": "active" }
```

#### `episodic_end`

End the current or specified episode.

```
Parameters:
  episode_id: str       — Episode to end (default: current)
  summary: str          — Episode summary (default: "")
  outcome: str          — Outcome description (default: "")

Returns: dict
```

#### `episodic_record`

Record an event in the active episode.

```
Parameters:
  content: str          — Event content (required)
  event_type: str       — Type: "interaction", "decision", "error", etc. (default: "interaction")
  importance: float     — Importance 0.0-1.0 (default: 0.5)
  agent_id: str         — Agent recording (default: "")
  user_id: str          — User involved (default: "")

Returns: dict
```

#### `episodic_timeline`

Query events across episodes in a time range.

```
Parameters:
  start_time: float | None — Unix timestamp start
  end_time: float | None   — Unix timestamp end
  event_types: str | None  — Comma-separated event types
  min_importance: float    — Minimum importance filter (default: 0.0)
  limit: int               — Max results (default: 50)
  offset: int              — Skip first N results for pagination (default: 0)

Returns: list[dict]
```

#### `episodic_search`

Search episodes by content similarity.

```
Parameters:
  query: str            — Search query (required)
  limit: int            — Max results (default: 5)
  offset: int           — Skip first N results for pagination (default: 0)

Returns: list[dict]
```

---

### Procedural Memory (4 tools)

Learn and recall tool usage patterns and workflows.

#### `procedural_record`

Record a tool use for procedural learning.

```
Parameters:
  tool_name: str        — Tool that was used (required)
  input_data: str       — Tool input (required)
  result: str           — Tool output (required)
  success: bool         — Whether the tool call succeeded (default: true)
  context: str          — Context when tool was used (default: "")
  duration_ms: float    — Execution time in ms (default: 0)

Returns: dict
```

#### `procedural_suggest`

Suggest the best tool/procedure for the current context.

```
Parameters:
  context: str          — Current situation (required)

Returns: dict
  { "tool": "grep", "confidence": 0.85, "reason": "Previously used for similar searches" }
```

#### `procedural_workflows`

Find relevant workflows.

```
Parameters:
  context: str          — Current context (default: "")
  tags: str | None      — Comma-separated tags filter

Returns: list[dict]
```

#### `procedural_add_workflow`

Register a workflow template.

```
Parameters:
  name: str             — Workflow name (required)
  steps: str            — Steps description (required)
  description: str      — Workflow description (default: "")
  trigger_context: str  — When to trigger (default: "")
  tags: str | None      — Comma-separated tags

Returns: dict
```

---

### Importance & Self-Edit (3 tools)

Memory lifecycle management — score, edit, and budget.

#### `importance_score`

Score a memory's importance (0–1) using multi-signal analysis.

```
Parameters:
  memory_id: str        — Memory to score (required)
  access_count: int     — Number of times accessed (default: 0)
  connection_count: int — Number of graph connections (default: 0)

Returns: dict
  { "score": 0.78, "signals": { "recency": 0.9, "frequency": 0.6, "connections": 0.8 } }
```

#### `self_edit`

Edit a memory: keep, discard, compress, promote, or demote.

```
Parameters:
  memory_id: str        — Memory to edit (required)
  action: str           — Action: "keep", "discard", "compress", "promote", "demote" (required)
  reason: str           — Why this action (default: "")
  new_content: str      — New content for compress action (default: "")
  target_tier: str      — Target tier for promote/demote (default: "")

Returns: dict
```

#### `memory_budget`

Check memory budget usage across tiers.

```
Returns: dict
  {
    "working": { "used": 30, "limit": 100, "utilization": 0.3 },
    "recall": { "used": 10, "limit": 500, "utilization": 0.02 },
    "archival": { "used": 2, "limit": null, "utilization": 0.0 }
  }
```

---

### User DNA (2 tools)

Behavioral profiling — build and update user DNA profiles.

#### `user_dna_snapshot`

Get the complete behavioral DNA profile for a user.

```
Parameters:
  user_id: str          — User to profile (required)

Returns: dict
  {
    "expertise": { "python": 0.9, "typescript": 0.7 },
    "work_patterns": { "peak_hours": [9, 14], "session_length": "medium" },
    "preferences": { "editor": "vscode", "language": "python" },
    "cognitive_style": "analytical"
  }
```

#### `user_dna_collect`

Collect behavioral signals from user interaction to update DNA profile.

```
Parameters:
  user_id: str          — User (required)
  message: str          — User message text (default: "")
  code: str             — Code snippet from user (default: "")
  role: str             — Message role (default: "user")

Returns: dict
```

---

### Dream Engine (2 tools)

Memory consolidation — compress, promote, and forget memories (inspired by sleep consolidation).

#### `dream_consolidate`

Run a dream consolidation cycle.

```
Parameters:
  memories: str | None  — JSON array of memory IDs to consolidate (default: auto-select)

Returns: dict
  {
    "promoted": 3,
    "compressed": 5,
    "forgotten": 2,
    "journal_entry": "Consolidated 10 memories: promoted 3 high-value..."
  }
```

#### `dream_journal`

View recent dream consolidation journal entries.

```
Parameters:
  limit: int            — Number of entries (default: 10)
  offset: int           — Skip first N entries for pagination (default: 0)

Returns: dict
```

---

### Preferences (2 tools)

Learn and query user preferences.

#### `preference_query`

Query learned user preferences.

```
Parameters:
  user_id: str          — User (required)
  category: str         — Preference category filter (default: all)
  min_confidence: float — Minimum confidence threshold (default: 0.3)

Returns: dict
  {
    "preferences": [
      { "category": "coding", "key": "language", "value": "python", "confidence": 0.95 },
      { "category": "coding", "key": "style", "value": "functional", "confidence": 0.7 }
    ]
  }
```

#### `preference_teach`

Explicitly teach a user preference with high confidence.

```
Parameters:
  user_id: str          — User (required)
  category: str         — Preference category (required)
  key: str              — Preference key (required)
  value: str            — Preference value (required)
  context: str          — Context for this preference (default: "")

Returns: dict
```

---

### Context Resurrection (2 tools)

Session snapshot and resume for context continuity across sessions.

#### `session_snapshot`

Capture a session snapshot for future context resurrection.

```
Parameters:
  user_id: str              — User (required)
  session_id: str           — Session identifier (required)
  messages: str | None      — JSON array of session messages
  duration_minutes: float   — Session duration (default: 0.0)
  outcome: str              — Session outcome (default: "unknown")

Returns: dict
```

#### `session_resume`

Get context resurrection hints for resuming a session.

```
Parameters:
  user_id: str          — User (required)

Returns: dict
  {
    "last_session": { "id": "...", "summary": "...", "outcome": "..." },
    "active_topics": [...],
    "pending_tasks": [...],
    "suggested_continuation": "..."
  }
```

---

### Team Sharing (2 tools)

Multi-agent memory sharing and coherence.

#### `team_share_memory`

Share a memory across team agents via the broadcast system.

```
Parameters:
  agent_id: str         — Sharing agent (required)
  namespace: str        — Target namespace (required)
  key: str              — Memory key (required)
  value: str            — Memory value (required)
  topics: str           — Comma-separated topics (default: "")

Returns: dict
```

#### `team_coherence_check`

Check memory coherence within a team, detecting conflicts.

```
Parameters:
  team_id: str          — Team identifier (required)

Returns: dict
  {
    "coherent": true,
    "conflicts": [],
    "agents": ["agent-1", "agent-2"],
    "shared_memories": 15
  }
```

---

### Prediction (2 tools)

Action prediction and difficulty estimation using Markov chains and user profiling.

#### `predict_next_action`

Record an action and predict the next user action.

```
Parameters:
  action: str           — Current action (default: "")
  top_k: int            — Number of predictions (default: 3)

Returns: dict
  {
    "predictions": [
      { "action": "run_tests", "probability": 0.6 },
      { "action": "commit", "probability": 0.25 },
      { "action": "refactor", "probability": 0.15 }
    ]
  }
```

#### `estimate_difficulty`

Estimate task difficulty based on user's expertise profile.

```
Parameters:
  description: str      — Task description (required)
  keywords: str         — Comma-separated keywords (default: "")

Returns: dict
  { "difficulty": 0.4, "confidence": 0.8, "factors": [...] }
```

---

### Emotional Intelligence (2 tools)

Sentiment analysis and fatigue detection.

#### `emotion_analyze`

Analyze emotional content of text.

```
Parameters:
  text: str             — Text to analyze (required)
  context: str          — Additional context (default: "")

Returns: dict
  {
    "sentiment": "positive",
    "valence": 0.7,
    "arousal": 0.5,
    "emotions": { "joy": 0.6, "confidence": 0.8 }
  }
```

#### `emotion_fatigue_check`

Check current fatigue level and burnout risk.

```
Returns: dict
  {
    "fatigue_level": 0.3,
    "burnout_risk": "low",
    "recommendation": "Normal workload, no concerns"
  }
```

---

### Product Intelligence (2 tools)

Cross-product tracking and usage analytics.

#### `product_register`

Register a product in the user's ecosystem. _(async)_

```
Parameters:
  product_id: str       — Product identifier (required)
  name: str             — Product name (required)
  category: str         — Product category (required)
  version: str          — Product version (default: "")
  features: str         — Comma-separated features (default: "")

Returns: dict
```

#### `product_usage_record`

Record a product usage event. _(async)_

```
Parameters:
  product_id: str       — Product (required)
  feature: str          — Feature used (required)
  action: str           — Action performed (required)
  duration: float       — Duration in seconds (default: 0.0)
  session_id: str       — Session ID (default: "")

Returns: dict
```

---

### Behavioral Fusion (3 tools)

Unified behavioral model across all products. _(async)_

#### `fusion_unified_model`

Get the unified user model across all products.

```
Returns: dict
  {
    "segments": [...],
    "dominant_patterns": [...],
    "cross_product_workflows": [...]
  }
```

#### `fusion_churn_predict`

Predict churn risk for a specific product.

```
Parameters:
  product_id: str       — Product to evaluate (required)

Returns: dict
  { "risk": 0.15, "factors": [...], "recommendation": "..." }
```

#### `fusion_detect_workflows`

Detect cross-product workflows from usage patterns.

```
Parameters:
  min_frequency: int    — Minimum pattern frequency (default: 3)

Returns: dict
```

---

### Habit Intelligence (1 tool)

#### `habit_detect`

Record an action and detect user habits. _(async)_

```
Parameters:
  action: str           — Action to record (default: "")
  product_id: str       — Product context (default: "")

Returns: dict
  {
    "habits": [
      { "pattern": "morning_code_review", "frequency": 0.8, "time_window": "09:00-10:00" }
    ]
  }
```

---

### Contextual Intelligence (2 tools)

Situation awareness and intent inference. _(async)_

#### `context_situation`

Update situation awareness and get current context.

```
Parameters:
  product_id: str       — Product (required)
  action: str           — Current action (required)

Returns: dict
```

#### `context_infer_intent`

Observe action and infer user intent.

```
Parameters:
  product_id: str       — Product (required)
  action: str           — Observed action (required)

Returns: dict
  { "intent": "debugging", "confidence": 0.85, "context": "..." }
```

---

### Business Intelligence (2 tools)

Revenue signals and product lifecycle tracking. _(async)_

#### `biz_revenue_signal`

Record a revenue-relevant business signal.

```
Parameters:
  signal_type: str      — Signal type (required)
  product_id: str       — Product (required)
  description: str      — Signal description (required)
  impact: float         — Revenue impact 0.0-1.0 (default: 0.5)
  confidence: float     — Signal confidence 0.0-1.0 (default: 0.5)
  evidence: str         — Supporting evidence (default: "")

Returns: dict
```

#### `biz_lifecycle_update`

Update and get lifecycle position for a product. _(async)_

```
Parameters:
  product_id: str       — Product (required)
  days_active: int      — Days since registration (default: 0)
  total_events: int     — Total usage events (default: 0)
  feature_count: int    — Features used (default: 0)
  engagement_score: float — Engagement 0.0-1.0 (default: 0.5)
  usage_trend: str      — "growing", "stable", "declining" (default: "stable")
  is_expanding: bool    — Feature expansion flag (default: false)

Returns: dict
```

---

### Adversarial Protection (3 tools)

Memory injection detection, consistency checking, and integrity verification. _(async)_

#### `adversarial_scan`

Scan content for injection/poisoning threats.

```
Parameters:
  content: str          — Content to scan (required)

Returns: str (JSON)
  { "threats": [], "risk_level": "low", "safe": true }
```

#### `adversarial_check_consistency`

Check content consistency against known facts.

```
Parameters:
  content: str          — Content to check (required)
  facts: str            — JSON array of known facts (default: "[]")

Returns: str (JSON)
  { "consistent": true, "conflicts": [], "confidence": 0.95 }
```

#### `adversarial_verify_integrity`

Hash content and verify its integrity.

```
Parameters:
  content: str          — Content to verify (required)
  content_id: str       — Content identifier (required)

Returns: str (JSON)
  { "valid": true, "hash": "sha256:abc123...", "verified_at": "..." }
```

---

### Cognitive Load (3 tools)

Cognitive load tracking and focus session management. _(async)_

#### `cognitive_record`

Record a cognitive interaction and return current load.

```
Parameters:
  topic: str            — Topic being worked on (required)
  complexity: float     — Topic complexity 0.0-1.0 (default: 0.5)

Returns: str (JSON)
  { "current_load": 0.6, "topics_active": 3, "recommendation": "manageable" }
```

#### `cognitive_check_overload`

Check for cognitive overload.

```
Returns: str (JSON)
  {
    "overloaded": false,
    "load": 0.6,
    "capacity": 1.0,
    "active_topics": ["auth", "database", "testing"]
  }
```

#### `cognitive_focus_session`

Start or check a focus session.

```
Parameters:
  action: str           — "start" or "status" (default: "start")
  session_id: str       — Session identifier (default: auto-generated)

Returns: str (JSON)
  { "session_id": "focus_001", "status": "active", "duration": 0, "topic": "..." }
```

---

### 🗄️ Cache Management (v2.1)

| Tool | Description |
|------|-------------|
| `cache_stats` | Get cache statistics: hits, misses, hit rate, backend type, size |
| `cache_clear` | Clear cache entries (full flush or pattern-based invalidation) |
| `cache_warmup` | Pre-warm the cache with common search queries |

#### `cache_stats`

Get cache statistics.

```
Parameters: (none)

Returns: str (JSON)
  { "backend": "memory", "size": 42, "max_size": 1024,
    "hits": 150, "misses": 23, "hit_rate": 0.8671, "default_ttl": null }
```

#### `cache_clear`

Clear cache entries.

```
Parameters:
  pattern: str        — Glob pattern (default: "" = flush all). Example: "embed:*"

Returns: str (JSON)
  { "cleared": 12, "pattern": "embed:*" }
  or { "cleared": "all" }
```

#### `cache_warmup`

Pre-warm the cache with common queries.

```
Parameters:
  queries: str        — JSON array of search strings (default: "[]")

Returns: str (JSON)
  { "warmed": 3, "queries": ["python", "react", "testing"] }
```

---

### 🛡️ GDPR & Privacy (3 tools)

| Tool | Description |
|------|-------------|
| `gdpr_forget_user` | Delete ALL data for a user across every subsystem (right to erasure) |
| `gdpr_export_data` | Export all user data as portable JSON bundle (right to portability) |
| `gdpr_scan_pii` | Scan text for personally identifiable information (PII) |

#### `gdpr_forget_user`

⚠️ **Irreversible.** Cascade deletes all data for a user across every subsystem: namespace memories, vector embeddings, file-based memories, version history, audit trail, preferences, user DNA, episodic events, recall items, and ACL grants.

```
Parameters:
  user_id: str      — The user ID to delete all data for (required)

Returns: str (JSON)
  {
    "certificate_id": "uuid-...",
    "user_id": "user-42",
    "requested_at": "2024-01-15T10:30:00+00:00",
    "completed_at": "2024-01-15T10:30:01+00:00",
    "items_deleted": { "namespace_memories": 5, "vector_embeddings": 3, "preferences": 2 },
    "total_deleted": 10,
    "subsystems_cleared": ["namespace_store", "vector_store", "preferences"],
    "errors": []
  }
```

#### `gdpr_export_data`

Export all data associated with a user for portability (GDPR Article 20).

```
Parameters:
  user_id: str      — The user ID to export data for (required)

Returns: str (JSON)
  {
    "user_id": "user-42",
    "exported_at": "2024-01-15T10:30:00+00:00",
    "total_items": 8,
    "data": {
      "namespace_memories": [...],
      "vector_memories": [...],
      "preferences": [...],
      "user_dna": [...]
    }
  }
```

#### `gdpr_scan_pii`

Detect PII in arbitrary text. Identifies: email addresses, phone numbers, SSNs, credit card numbers, and IP addresses.

```
Parameters:
  content: str      — Text to scan for PII (required)

Returns: str (JSON)
  {
    "has_pii": true,
    "matches": [
      { "type": "email", "value": "john@example.com", "start": 10, "end": 28 },
      { "type": "phone", "value": "+1-555-0123", "start": 45, "end": 56 }
    ],
    "redacted": "Contact me at [EMAIL_REDACTED] or call [PHONE_REDACTED]"
  }
```

---

### 🔔 Webhooks (3 tools)

| Tool | Description |
|------|-------------|
| `webhook_register` | Register a webhook URL to receive event notifications |
| `webhook_unregister` | Remove a registered webhook by ID |
| `webhook_list` | List all registered webhooks and their status |

#### `webhook_register`

Register a new webhook endpoint. Supports HMAC-SHA256 signature verification
and event filtering.

```
Parameters:
  url: str              — HTTP(S) URL to receive POST notifications (required)
  events: str           — JSON array of event types (default: '["*"]')
  secret: str           — Optional secret for signature verification (default: "")
  description: str      — Human-readable label (default: "")

Events: memory.created, memory.updated, memory.deleted, memory.promoted,
        episode.started, episode.ended, churn.detected, anomaly.detected,
        overload.detected (or "*" for all)

Returns: str (JSON)
  {
    "webhook_id": "wh_abc123def456",
    "url": "https://example.com/hook",
    "events": ["memory.created", "memory.deleted"],
    "active": true,
    "description": "Slack notifier",
    "created_at": "2024-01-15T10:30:00+00:00"
  }
```

#### `webhook_unregister`

Remove a registered webhook.

```
Parameters:
  webhook_id: str       — The webhook ID to remove (required)

Returns: str (JSON)
  { "removed": true, "webhook_id": "wh_abc123def456" }
```

#### `webhook_list`

List all registered webhooks with delivery status.

```
Parameters:
  active_only: bool     — Only show active webhooks (default: false)

Returns: str (JSON array)
  [
    {
      "webhook_id": "wh_abc123def456",
      "url": "https://example.com/hook",
      "events": ["*"],
      "active": true,
      "consecutive_failures": 0,
      "description": "Slack notifier",
      "created_at": "2024-01-15T10:30:00+00:00"
    }
  ]
```

### 🧠 Intelligence — Summarization (2 tools)

| Tool | Description |
|------|-------------|
| `memoria_summarize` | Summarize a text using the configured LLM provider |
| `memoria_summarize_all` | Summarize stored memories for a namespace |

#### `memoria_summarize`

Summarize text content using the configured LLM provider (Ollama, OpenAI, Anthropic, or `none` fallback).

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `content` | string | Yes | The text to summarize |
| `max_tokens` | integer | No | Maximum summary length in tokens (default: 200) |

**Returns:** Object with `summary`, `key_facts`, `compression_ratio`, `original_length`, `summary_length`, `chunks_processed`, `provider`.

**Example:**
```json
{
  "content": "A very long article about machine learning that needs summarizing...",
  "max_tokens": 150
}
```

#### `memoria_summarize_all`

Summarize all memories stored in a given namespace.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `namespace` | string | No | Namespace to summarize (default: "default") |

**Returns:** Object with `summarized` (count), `skipped` (count), and `results` (list of summaries).

**Example:**
```json
{
  "namespace": "project_notes"
}
```

### 🔍 Deduplication (2 tools)

| Tool | Description |
|------|-------------|
| `memoria_find_duplicates` | Find memories similar to given content |
| `memoria_merge_duplicates` | Merge new content into an existing memory |

#### `memoria_find_duplicates`

Find existing memories that are similar to the provided content using embedding-based cosine similarity.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `content` | string | Yes | The text to check for duplicates |
| `limit` | integer | No | Max results (default: 10) |
| `threshold` | float | No | Similarity threshold override (default: 0.92) |
| `user_id` | string | No | Filter by user |

**Returns:** List of duplicate candidates with `memory_id`, `content`, `similarity`, `metadata`.

**Example:**
```json
{
  "content": "The project uses React for the frontend",
  "threshold": 0.85,
  "limit": 5
}
```

#### `memoria_merge_duplicates`

Merge new content into an existing memory using the configured strategy (longer, combine, newer).

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `memory_id` | string | Yes | ID of the existing memory to merge into |
| `new_content` | string | Yes | New content to merge |
| `namespace` | string | No | Namespace (default: "default") |

**Returns:** Object with `status`, `memory_id`, `strategy`, `content_length`, `source_ids`.

**Example:**
```json
{
  "memory_id": "550e8400-e29b-41d4-a716-446655440000",
  "new_content": "The project uses React 18 for the frontend with TypeScript"
}
```

### 📋 Templates (3 tools)

| Tool | Description |
|------|-------------|
| `template_list` | List available memory templates |
| `template_apply` | Apply a template to create a structured memory |
| `template_create` | Create a custom memory template |

#### `template_list`

List all available memory templates, optionally filtered by category.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `category` | string | No | Filter by category (developer, engineering, collaboration, etc.) |

**Returns:** List of template metadata with name, description, category, field count, tags.

**Built-in templates:** `coding_preference`, `project_context`, `bug_report`, `meeting_notes`, `api_endpoint`, `design_decision`, `customer_profile`, `incident_report`, `onboarding_step`, `knowledge_article`.

#### `template_apply`

Apply a template to create a structured memory. Validates fields and renders content from the template.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `template_name` | string | Yes | Name of the template to apply |
| `data` | string (JSON) | Yes | Field data as JSON, e.g. `{"language": "Python"}` |
| `namespace` | string | No | Target namespace (default: "default") |
| `user_id` | string | No | User ID |
| `agent_id` | string | No | Agent ID |

**Example:**
```json
{
  "template_name": "coding_preference",
  "data": "{\"language\": \"Python\", \"framework\": \"FastAPI\", \"style_guide\": \"PEP 8\"}"
}
```

#### `template_create`

Create and register a custom memory template at runtime.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | string | Yes | Template name |
| `description` | string | Yes | What this template is for |
| `fields` | string (JSON) | Yes | Field definitions as JSON array |
| `content_template` | string | Yes | Content template with `{field_name}` placeholders |
| `category` | string | No | Category (default: "custom") |
| `tags` | string (JSON) | No | Tags as JSON array |

**Example:**
```json
{
  "name": "standup_update",
  "description": "Daily standup update",
  "fields": "[{\"name\": \"yesterday\", \"required\": true}, {\"name\": \"today\", \"required\": true}, {\"name\": \"blockers\"}]",
  "content_template": "Yesterday: {yesterday}\nToday: {today}\nBlockers: {blockers}"
}
```

---

## Resources Reference

MCP resources provide read-only data endpoints. Clients can read these at any time for context.

| URI | Description |
|-----|-------------|
| `memoria://memories` | List all stored memories with metadata |
| `memoria://config` | Current MEMORIA configuration (backends, project dir, features) |
| `memoria://profile/{user_id}` | User profile: expertise, topics, patterns |
| `memoria://stats` | Comprehensive statistics across all subsystems |
| `memoria://episodic/timeline` | Recent episodic events (last 20) |
| `memoria://procedural/patterns` | All learned tool patterns and workflows |
| `memoria://budget` | Memory budget usage across tiers |

### Reading Resources

```bash
# Via HTTP
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "resources/read",
    "params": { "uri": "memoria://stats" },
    "id": 1
  }'
```

---

## Prompts Reference

MCP prompts are reusable LLM context templates. Clients invoke these to get pre-formatted context for the LLM.

### `recall_context`

Recall relevant memories and inject them as LLM context.

```
Parameters:
  query: str            — What to recall (required)
  user_id: str | None   — User filter
  limit: int            — Max memories (default: 5)
  offset: int           — Skip first N results for pagination (default: 0)

Use: "Before answering, recall what you know about this topic"
```

### `suggest_next`

Generate proactive suggestions formatted as actionable recommendations.

```
Parameters:
  context: str          — Current situation (default: "")
  user_id: str | None   — User to suggest for

Use: "What should I do next based on my patterns?"
```

### `deep_recall`

Deep search across all memory types: memories + episodic events + procedural patterns.

```
Parameters:
  query: str            — Deep search query (required)
  user_id: str | None   — User filter

Use: "Give me everything you know about this topic across all memory layers"
```

### `consolidation_report`

Generate a full memory health report.

```
Parameters:
  user_id: str | None   — User to report on

Use: "How healthy is my memory system? What needs attention?"
```

### `episodic_recap`

Recap of recent episodes with summaries and outcomes.

```
Parameters:
  limit: int            — Number of episodes (default: 5)
  offset: int           — Skip first N episodes for pagination (default: 0)

Use: "What happened in my last few sessions?"
```

---

## Real-time Streaming Tools

### `stream_subscribe`

Create a streaming subscription for real-time memory events.

```
Parameters:
  channel_type: str     — "sse" or "ws" (default: "sse")
  channel_id: str       — Optional custom channel ID
  event_types: str      — JSON array of event types to filter (default: "[]" = all)
  user_ids: str         — JSON array of user IDs to filter (default: "[]" = all)
  namespaces: str       — JSON array of namespaces to filter (default: "[]" = all)

Returns: Channel info with channel_id, type, filter configuration.

Use: "Subscribe to memory.updated events for user alice"
→ stream_subscribe(channel_type="sse", event_types='["memory.updated"]', user_ids='["alice"]')
```

### `stream_unsubscribe`

Close a streaming channel by ID.

```
Parameters:
  channel_id: str       — ID of the channel to close

Returns: { "status": "closed" | "not_found", "channel_id": "..." }

Use: "Stop listening to channel abc123"
→ stream_unsubscribe(channel_id="abc123")
```

### `stream_list`

List all active streaming channels with their filters and stats.

```
Parameters: (none)

Returns: Array of channel info objects with type, filter, event_count, queue_size.

Use: "What streaming channels are active?"
```

### `stream_broadcast`

Manually broadcast an event to all active streaming channels.

```
Parameters:
  event_type: str       — Event type name (e.g., "custom.notification")
  data: str             — JSON string payload (default: "{}")

Returns: { "status": "broadcast", "event_type": "...", "channels_notified": N }

Use: "Send a test event to all listeners"
→ stream_broadcast(event_type="test.ping", data='{"message": "hello"}')
```

### `stream_stats`

Return streaming manager statistics.

```
Parameters: (none)

Returns: { "sse_channels": N, "ws_channels": N, "total_channels": N,
           "total_events_dispatched": N, "bus_attached": true|false }

Use: "How many streaming channels are active?"
```

---

## Multi-modal Memory Tools

### `add_attachment`

Attach a binary file (image, audio, document) to a memory.

```
Parameters:
  memory_id: str        — ID of the parent memory
  data_base64: str      — Base64-encoded binary content
  filename: str         — Original filename (e.g., "diagram.png")
  mime_type: str        — MIME type (default: "application/octet-stream")
  description: str      — Human-readable description

Returns: Attachment metadata with attachment_id, sha256, size, extracted metadata.

Use: "Attach this screenshot to memory m123"
→ add_attachment(memory_id="m123", data_base64="...", filename="screenshot.png", mime_type="image/png")
```

### `get_attachment`

Get attachment metadata by ID.

```
Parameters:
  attachment_id: str    — ID of the attachment

Returns: Full attachment metadata or error if not found.
```

### `list_attachments`

List attachments, optionally filtered by memory_id.

```
Parameters:
  memory_id: str        — Filter by parent memory (optional)
  limit: int            — Max results (default: 100)
  offset: int           — Skip first N results (default: 0)

Returns: Array of attachment metadata objects.
```

### `delete_attachment`

Delete an attachment by ID.

```
Parameters:
  attachment_id: str    — ID to delete

Returns: { "status": "deleted" | "not_found", "attachment_id": "..." }
```

### `attachment_stats`

Return attachment storage statistics.

```
Parameters: (none)

Returns: { "total_attachments": N, "disk_usage_bytes": N }
```

---

## Plugin System Tools

### `plugin_list`

List all registered plugins with their activation status.

```
Parameters: (none)

Returns: Array of plugin info objects with name, version, active status, tools, backends.
```

### `plugin_discover`

Discover and register plugins from Python entry points (`memoria.plugins` group).

```
Parameters: (none)

Returns: Array of discovered plugins with newly_registered flag.

Use: "Find and load all available plugins"
```

### `plugin_activate`

Activate a registered plugin by name.

```
Parameters:
  name: str             — Plugin name to activate

Returns: { "status": "activated" | "failed", "name": "..." }
```

### `plugin_deactivate`

Deactivate a plugin by name.

```
Parameters:
  name: str             — Plugin name to deactivate

Returns: { "status": "deactivated" | "not_found", "name": "..." }
```

### `plugin_stats`

Return plugin system statistics.

```
Parameters: (none)

Returns: { "registered": N, "active": N, "plugins": [...], "active_plugins": [...] }
```
