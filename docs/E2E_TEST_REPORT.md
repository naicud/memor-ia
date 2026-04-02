# MEMORIA v2.0.0 — End-to-End Test Report

> Full conversation simulation tests covering all 56 MCP tools, 6 resources,
> and 5 prompts through realistic multi-turn scenarios.

## Test Summary

| Metric | Value |
|--------|-------|
| Total test scenarios | 22 |
| Pass | **22** |
| Fail | 0 |
| Execution time | < 1s |
| Backend | In-memory (FalkorDB fallback) + SQLite + sqlite-vec |
| Python | 3.14.3 |

## Test Scenarios

Each scenario simulates a complete user conversation flow through the MCP
tool layer — the same code path a real client (Claude Desktop, Cursor, VS Code
Copilot) would use. Only the transport is bypassed.

### 1. Developer Onboarding (10-turn)
Stores coding preferences, project architecture, team info. Searches, enriches,
profiles, gets suggestions/insights, and checks stats.

**Tools exercised:** `memoria_add`, `memoria_search`, `memoria_enrich`,
`memoria_profile`, `memoria_suggest`, `memoria_insights`, `memoria_get`,
`memoria_stats`

**Example data flow:**
```
Turn 1 → memoria_add("I prefer Python 3.12+ with strict type hints...")
         → {status: "created", id: "mem-abc123"}

Turn 4 → memoria_search("project architecture backend")
         → [{content: "memor-ia uses FalkorDB...", score: 0.85}]

Turn 6 → memoria_profile(user_id="dev-alice")
         → {user_id: "dev-alice", memory_count: 3, ...}
```

### 2. Episodic Debugging Session (multi-session)
Starts an episode, records observations/actions/decisions, ends with
outcome. Searches across episodes. Validates timeline and search.

**Tools exercised:** `episodic_start`, `episodic_record`, `episodic_end`,
`episodic_timeline`, `episodic_search`

**Example timeline:**
```
Episode: "Debug vector upsert failure"
├── event: observation → "test_vector.py fails on INSERT OR REPLACE"
├── event: action      → "Tried DELETE + INSERT pattern on sqlite-vec"
├── event: decision    → "Virtual tables don't support REPLACE; use DELETE+INSERT"
└── outcome: success   (duration: recorded)
```

### 3. Procedural Tool Learning (8-step)
Records tool invocations (grep, pytest, docker) with success/failure,
asks for suggestions, creates named workflows, lists them.

**Tools exercised:** `procedural_record`, `procedural_suggest`,
`procedural_add_workflow`, `procedural_workflows`,
`get_procedural_patterns` (resource)

**Example workflow:**
```json
{
  "name": "deploy-and-test",
  "steps": [
    {"tool": "docker", "input": "docker compose build"},
    {"tool": "docker", "input": "docker compose up -d"},
    {"tool": "pytest", "input": "pytest tests/test_e2e_backends.py -v"}
  ],
  "tags": ["deploy", "test", "docker"]
}
```

### 4. Tiered Storage Lifecycle
Stores memories in `working`, `reference`, and `archival` tiers with
different importance levels. Searches across tiers and validates retrieval.

**Tools exercised:** `memoria_add_to_tier`, `memoria_search_tiers`

**Tier structure:**
```
Working  (importance ≥ 0.9) → Current sprint context, active bugs
Reference (importance ~0.7) → Architecture patterns, API contracts
Archival  (importance ~0.3) → Historical decisions, old sprint notes
```

### 5. Access Control (ACL)
Grants read/write access by user ID on specific memory IDs. Verifies
access checks return correct permissions.

**Tools exercised:** `memoria_grant_access`, `memoria_check_access`

### 6. Knowledge Graph Entity Pipeline
Stores facts with rich entity content (people, projects, tools). Enriches
new content to extract entities. Validates cross-database search and
insights.

**Tools exercised:** `memoria_add`, `memoria_enrich`, `memoria_search`,
`memoria_insights`, `memoria_stats`

**Example graph data (in-memory fallback):**
```
Entities extracted from enrichment:
  [Person: "Bob"] --works_on--> [Project: "React frontend"]
  [Project: "React frontend"] --uses--> [API: "MEMORIA API"]
  [Person: "Daniel"] --created--> [Project: "memor-ia"]
  [Project: "memor-ia"] --uses--> [Technology: "FalkorDB"]
  [Project: "memor-ia"] --uses--> [Technology: "SQLite"]
```

### 7. Importance Scoring & Self-Edit
Stores memories, scores them by access/connection count, then compresses
low-importance memories with the self-edit tool.

**Tools exercised:** `importance_score`, `self_edit`

**Example:**
```
importance_score(memory_id="mem-xyz", access_count=5, connection_count=3)
→ {score: 0.72, tier: "reference", ...}

self_edit(memory_id="mem-abc", action="compress",
          new_content="Coffee machine in kitchen")
→ {status: "compressed", ...}
```

### 8. User DNA + Dream Consolidation
Collects user interaction data, takes a DNA snapshot (behavioral profile),
runs dream consolidation (memory defragmentation), checks dream journal.

**Tools exercised:** `user_dna_collect`, `user_dna_snapshot`,
`dream_consolidate`, `dream_journal`

### 9. Preference Detection & Teaching
Teaches explicit preferences by category (tool, style, testing). Queries
back by category.

**Valid categories:** `language`, `framework`, `tool`, `style`, `workflow`,
`communication`, `architecture`, `testing`

**Tools exercised:** `preference_teach`, `preference_query`

### 10. Session Snapshot & Resume
Builds state, takes a session snapshot, then resumes from it.

**Tools exercised:** `session_snapshot`, `session_resume`

### 11. Team Collaboration
Shares memory across team namespace, checks team coherence.

**Tools exercised:** `team_share_memory`, `team_coherence_check`

### 12. Prediction & Emotion
Predicts next actions, estimates task difficulty, analyzes emotion from
text, checks developer fatigue.

**Tools exercised:** `predict_next_action`, `estimate_difficulty`,
`emotion_analyze`, `emotion_fatigue_check`

### 13. Product Intelligence (full pipeline)
Registers a product, records usage events, runs behavior fusion model,
churn prediction, workflow detection, habit detection, revenue signal,
and lifecycle tracking.

**Valid product categories:** `billing`, `crm`, `ide`,
`project_management`, `communication`, `analytics`, `storage`, `security`

**Valid revenue signal types:** `upsell_opportunity`,
`cross_sell_opportunity`, `churn_risk`, `expansion_signal`,
`contraction_signal`, `renewal_risk`, `advocacy_signal`

**Tools exercised:** `product_register`, `product_usage_record`,
`fusion_unified_model`, `fusion_churn_predict`, `fusion_detect_workflows`,
`habit_detect`, `biz_revenue_signal`, `biz_lifecycle_update`

### 14. Context Awareness
Registers product context, analyzes situational awareness, infers intent.

**Tools exercised:** `context_situation`, `context_infer_intent`

### 15. Adversarial Protection
Scans content for poisoning, checks consistency against known facts,
verifies integrity.

**Tools exercised:** `adversarial_scan`, `adversarial_check_consistency`,
`adversarial_verify_integrity`

### 16. Cognitive Load Management
Records cognitive load events with topics/complexity, checks for overload,
starts focus sessions.

**Tools exercised:** `cognitive_record`, `cognitive_check_overload`,
`cognitive_focus_session`

### 17-19. Resources & Prompts
Tests all 7 MCP resources return valid JSON and all prompts generate
meaningful output.

**Resources:** `list_memories`, `get_config`, `get_stats`,
`get_episodic_timeline`, `get_procedural_patterns`, `get_budget`,
`get_user_profile`

**Prompts:** `recall_context`, `suggest_next`

### 20. Realistic 15-Turn Conversation
Simulates a complete real-world debugging session:
1. Start episode → 2. Record observations → 3. Add project memories →
4. Enrich content → 5-8. Record debugging steps → 9. End fix →
10. Cognitive check → 11. Get suggestions → 12. Teach preference →
13. Store working memory → 14. End episode → 15. Recall context

### 21-22. Delete & Sync Lifecycle
Tests memory deletion and namespace synchronization.

**Tools exercised:** `memoria_delete`, `memoria_sync`

---

## How to Run

```bash
# Full E2E conversation tests (no external services needed)
python -m pytest tests/test_e2e_conversation.py -v

# With real FalkorDB backend (requires Docker)
docker compose up -d falkordb
MEMORIA_GRAPH_HOST=localhost python -m pytest tests/test_e2e_backends.py -v

# Full test suite
python -m pytest tests/ -q
```

## Architecture Under Test

```
┌─────────────────────────────────────────────────┐
│              MCP Tool Layer (56 tools)           │
│   memoria_* │ episodic_* │ procedural_* │ ...    │
├─────────────┼────────────┼──────────────┼────────┤
│  Memoria    │  Episodic  │  Procedural  │ ...    │
│  (core)     │  Store     │  Store       │ subs   │
├─────────────┴────────────┴──────────────┴────────┤
│            Storage Layer                          │
│  ┌──────────────┐  ┌──────────────┐              │
│  │  Markdown     │  │  SQLite +    │              │
│  │  Files        │  │  sqlite-vec  │              │
│  └──────────────┘  └──────────────┘              │
│  ┌──────────────┐                                │
│  │  FalkorDB    │  (in-memory graph fallback)    │
│  │  Graph       │                                │
│  └──────────────┘                                │
└──────────────────────────────────────────────────┘
```

## Key Findings During Testing

### Bug Fixes Applied Before Tests

1. **sqlite-vec upsert** — Virtual tables don't support `INSERT OR REPLACE`.
   Fixed with `DELETE` + `INSERT` pattern in `vector/client.py`.

2. **Python 3.14 asyncio** — `asyncio.get_event_loop()` removed in 3.14.
   Fixed with `asyncio.run()` and `asyncio.new_event_loop()`.

3. **Dockerfile healthcheck** — Path was `/health` but FastMCP serves on
   `/mcp`. Fixed.

### Enum Validation Discovered

The test suite uncovered that several tools enforce strict enum validation:
- `PreferenceCategory`: language, framework, tool, style, workflow,
  communication, architecture, testing
- `ProductCategory`: billing, crm, ide, project_management, communication,
  analytics, storage, security
- `RevenueSignalType`: upsell_opportunity, cross_sell_opportunity, churn_risk,
  expansion_signal, contraction_signal, renewal_risk, advocacy_signal

### Async Tool Pattern

Product intelligence, context awareness, adversarial protection, and cognitive
load tools are all `async` functions. When calling from sync code, use:

```python
import asyncio

loop = asyncio.new_event_loop()
try:
    result = loop.run_until_complete(async_tool_function(...))
finally:
    loop.close()
```
