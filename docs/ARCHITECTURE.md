# Architecture

Deep dive into MEMORIA's 9-layer architecture, 28 subsystems, and data flow.

---

## Table of Contents

- [Overview](#overview)
- [Layer Diagram](#layer-diagram)
- [Layer 1: Core Services](#layer-1-core-services)
- [Layer 2: Hybrid Recall & Storage](#layer-2-hybrid-recall--storage)
- [Layer 3: Proactive Intelligence Engine](#layer-3-proactive-intelligence-engine)
- [Layer 4: Cognitive Services](#layer-4-cognitive-services)
- [Layer 5: Multi-Agent & Sharing](#layer-5-multi-agent--sharing)
- [Layer 6: Behavioral Prediction](#layer-6-behavioral-prediction)
- [Layer 7: Emotional Intelligence](#layer-7-emotional-intelligence)
- [Layer 8: Cross-Product Intelligence](#layer-8-cross-product-intelligence)
- [Layer 9: Platform Services](#layer-9-platform-services)
- [Data Flow](#data-flow)
- [Module Map](#module-map)
- [Recall Pipeline](#recall-pipeline)

---

## Overview

MEMORIA is organized as 9 stacked layers, each building on the layers below. The bottom layers provide fundamental storage and retrieval; the top layers provide advanced intelligence and cross-product analytics.

**Key design principles:**
- **Zero required dependencies** — every backend has a pure-Python fallback
- **Graceful degradation** — missing optional backends reduce features, never crash
- **Layered independence** — each layer can be used standalone
- **MCP-native** — all functionality exposed via 56 MCP tools

---

## Layer Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 9: Platform Services                                  │
│  GDPR & audit │ webhooks │ summarization │ templates         │
│  streaming │ attachments │ plugins │ dashboard │ federation  │
├─────────────────────────────────────────────────────────────┤
│  Layer 8: Cross-Product Intelligence                        │
│  product tracking │ behavioral fusion │ habit intelligence   │
│  contextual engine │ business intelligence                  │
├─────────────────────────────────────────────────────────────┤
│  Layer 7: Emotional Intelligence                            │
│  emotion analysis │ empathy triggers │ fatigue detection     │
├─────────────────────────────────────────────────────────────┤
│  Layer 6: Behavioral Prediction                             │
│  action prediction │ anomaly detection │ timing │ difficulty│
├─────────────────────────────────────────────────────────────┤
│  Layer 5: Multi-Agent & Sharing                             │
│  broadcasting │ team coherence │ DNA sync │ coordinator     │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: Cognitive Services                                │
│  user DNA │ dream engine │ preferences │ resurrection       │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Proactive Intelligence Engine                     │
│  profiler │ analyzer │ suggestions │ triggers │ episodic    │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Hybrid Recall & Storage                           │
│  keyword + vector + graph → RRF │ procedural │ self-edit    │
│  FalkorDB/InMemory │ SQLite-vec │ Markdown files            │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Core Services                                     │
│  identity │ comms │ context │ consolidation │ ACL           │
└─────────────────────────────────────────────────────────────┘
```

---

## Layer 1: Core Services

The foundation. Identity, communication, and access control.

| Module | Purpose | Key Classes |
|--------|---------|-------------|
| `core/` | Memory file I/O, frontmatter parsing, directory management | `Memoria`, `MemoryType`, `MemoryFrontmatter` |
| `identity/` | Agent identity management via `contextvars` | `AgentIdentity` |
| `comms/` | Inter-agent communication (mailbox, message bus, permissions) | `Mailbox`, `MessageBus` |
| `consolidation/` | Dream consolidation engine (5-gate auto-trigger) | `DreamEngine`, `AutoConsolidator` |
| `acl/` | Access control: roles, policies, grants, enforcement | `ACLEnforcer`, `Policy` |
| `adversarial/` | Memory injection detection, consistency checking, integrity | `ThreatDetector`, `ConsistencyChecker` |

### Core Storage Model

```
Memory File (Markdown)
├── YAML Frontmatter
│   ├── type: user|project|feedback|reference
│   ├── created: ISO 8601 timestamp
│   ├── tags: [list, of, tags]
│   ├── importance: 0.0-1.0
│   └── user_id: string
└── Content Body (Markdown text)
```

Files live in: `~/.memoria/projects/{project_hash}/memory/{type}/`

---

## Layer 2: Hybrid Recall & Storage

Three storage backends fused by Reciprocal Rank Fusion (RRF).

| Module | Purpose | Backend |
|--------|---------|---------|
| `vector/` | Embedding storage + cosine similarity search | SQLite (in-memory or persistent) |
| `graph/` | Entity-relationship knowledge graph | InMemoryGraph or FalkorDB |
| `recall/` | Hybrid recall pipeline (keyword + vector + graph → RRF) | ThreadPoolExecutor merger |
| `extraction/` | Entity and relation extraction from text | Pure Python NLP |
| `tiered/` | 3-tier memory management (working/recall/archival) | On top of core storage |
| `reasoning/` | Graph traversal, explanations, path finding | Dual-backend support |

### Hybrid Recall Pipeline

```
Query
  │
  ├─ Thread 1: Keyword Search ────→ Results + ranks
  ├─ Thread 2: Vector Search  ────→ Results + ranks
  └─ Thread 3: Graph Search   ────→ Results + ranks
  │
  └─ RRF Fusion ─→ Merged & ranked results
```

Each backend returns results independently. RRF combines them:

```
RRF_score(d) = Σ 1 / (k + rank_i(d))
```

Where `k` is a constant (typically 60) and `rank_i(d)` is the rank of document `d` in result set `i`.

---

## Layer 3: Proactive Intelligence Engine

Pattern detection, suggestion generation, and episodic memory.

| Module | Purpose |
|--------|---------|
| `proactive/` | User profiling, pattern analysis, suggestion engine |
| `intelligence/` | Trigger system, proactive recommendations |
| `episodic/` | Time-based episode recording and timeline queries |
| `procedural/` | Tool usage learning and workflow detection |

### Proactive Loop

```
User interaction
  → Record signals (episodic + procedural)
  → Detect patterns (frequency, sequence, timing)
  → Generate suggestions (context-aware)
  → Trigger actions (if confidence > threshold)
```

---

## Layer 4: Cognitive Services

User modeling, memory consolidation, and context resurrection.

| Module | Purpose |
|--------|---------|
| `user_dna/` | Behavioral DNA profiling (expertise, style, habits) |
| `consolidation/` | Dream engine — promote, compress, forget memories |
| `preferences/` | Learn and query user preferences |
| `resurrection/` | Session snapshot and context resume |
| `cognitive/` | Cognitive load tracking and focus sessions |

### Dream Consolidation

Inspired by biological sleep consolidation:

```
1. Score all memories by importance
2. Promote high-value memories (working → recall)
3. Compress medium-value memories (merge similar)
4. Forget low-value memories (archival or delete)
5. Update journal with consolidation report
```

The auto-consolidator triggers when 5 gates are met:
- Memory count exceeds threshold
- Time since last consolidation
- Working tier utilization
- Fragmentation score
- User inactivity period

---

## Layer 5: Multi-Agent & Sharing

Collaborative memory across multiple agents.

| Module | Purpose |
|--------|---------|
| `sharing/` | Memory broadcasting, team coherence checking |
| `sync/` | Cross-agent memory synchronization |

### Team Memory Model

```
Agent A ──share──→ Shared Namespace ←──share── Agent B
                         │
                   Coherence Check
                   (detect conflicts)
```

---

## Layer 6: Behavioral Prediction

Action prediction and anomaly detection.

| Module | Purpose |
|--------|---------|
| `prediction/` | Markov chain action prediction, difficulty estimation |

### Prediction Model

Uses a Markov chain built from observed action sequences:

```
[edit] → [test]    (p=0.6)
[edit] → [commit]  (p=0.25)
[edit] → [search]  (p=0.15)
```

---

## Layer 7: Emotional Intelligence

Sentiment analysis and fatigue detection.

| Module | Purpose |
|--------|---------|
| `emotional/` | Multi-signal emotion analysis, fatigue tracking |

---

## Layer 8: Cross-Product Intelligence

Analytics across multiple products in a user's ecosystem.

| Module | Purpose |
|--------|---------|
| `product_intel/` | Product registration, usage tracking |
| `fusion/` | Unified behavioral model, churn prediction, workflow detection |
| `habits/` | Habit detection from repeated patterns |
| `contextual/` | Situation awareness, intent inference |
| `biz_intel/` | Revenue signals, lifecycle tracking |

---

## Layer 9: Platform Services

Infrastructure services added in v2.1–v3.0 that run alongside Layers 1–8, providing compliance, extensibility, real-time streaming, and federation capabilities.

| Subsystem | Purpose |
|-----------|---------|
| `gdpr/` | Right-to-be-forgotten cascade delete across all stores, audit trail logging, consent management |
| `webhooks/` | HTTP webhook registry for external event notifications (`memory_created`, `memory_deleted`, etc.) |
| `summarization/` | LLM-powered text summarization with key-fact extraction, semantic deduplication with configurable similarity thresholds |
| `templates/` | Structured memory templates with field validation, content templates, category organization |
| `streaming/` | Real-time event channels via SSE/WebSocket, pub/sub pattern, event filtering by type/namespace/user |
| `attachments/` | Multi-modal binary attachment store, MIME-typed file associations per memory |
| `plugins/` | Dynamic plugin registry with activation/deactivation lifecycle, discovery mechanism |
| `dashboard/` | React SPA dashboard (Vite + TypeScript + Tailwind + Recharts), canvas-based knowledge graph, memory CRUD, audit log viewer |
| `federation/` | Peer-to-peer instance federation with PKI trust registry (4 trust levels), CRDT vector clock conflict resolution, selective namespace sync |

### Platform Services Architecture

```
                    ┌───────────────────────────────────┐
                    │      Layer 9: Platform Services    │
                    │                                    │
  ┌──────────┐      │  ┌─────────┐  ┌──────────────┐    │
  │ GDPR &   │◄────►│  │Webhooks │  │Summarization │    │
  │ Audit    │      │  │         │  │& Dedup       │    │
  └──────────┘      │  └─────────┘  └──────────────┘    │
                    │  ┌─────────┐  ┌──────────────┐    │
  ┌──────────┐      │  │Templates│  │  Streaming   │    │
  │Dashboard │◄────►│  │         │  │ (SSE/WS)     │    │
  │ (React)  │      │  └─────────┘  └──────────────┘    │
  └──────────┘      │  ┌─────────┐  ┌──────────────┐    │
                    │  │Attach-  │  │   Plugins    │    │
  ┌──────────┐      │  │ments    │  │  (registry)  │    │
  │Federation│◄────►│  └─────────┘  └──────────────┘    │
  │ (P2P/PKI)│      │                                    │
  └──────────┘      └──────────────┬────────────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
             ┌───────────┐ ┌───────────┐ ┌───────────┐
             │ Layers 1–4│ │ Layers 5–6│ │ Layers 7–8│
             │ Core &    │ │ Multi-Agent│ │ Emotional &│
             │ Storage   │ │ & Predict │ │ Product   │
             └───────────┘ └───────────┘ └───────────┘
```

---

## Data Flow

### Write Path

```
User/Agent
  │
  ├─ memoria.add(content)
  │   ├─ Write Markdown file (core storage)
  │   ├─ Embed + insert vector (vector store)
  │   ├─ Extract entities + insert nodes/edges (graph)
  │   └─ Update tiered storage metadata
  │
  ├─ episodic.record(event)
  │   └─ Append to active episode timeline
  │
  └─ procedural.record(tool_use)
      └─ Update tool usage patterns
```

### Read Path

```
User/Agent
  │
  ├─ memoria.search(query)
  │   ├─ Thread 1: keyword scan of .md files
  │   ├─ Thread 2: vector cosine similarity
  │   ├─ Thread 3: graph entity traversal
  │   └─ RRF fusion → ranked results
  │
  ├─ memoria.suggest(context)
  │   ├─ Profile user patterns
  │   ├─ Match against context
  │   └─ Generate ranked suggestions
  │
  └─ memoria.profile(user_id)
      ├─ Aggregate from all layers
      └─ Build expertise + preference map
```

---

## Module Map

Complete mapping of source modules to layers:

```
src/memoria/
├── __init__.py              # Public API exports
├── core/                    # Layer 1: Core memory I/O
│   └── __init__.py          # Memoria class, MemoryType, file ops
├── identity/                # Layer 1: Agent identity
├── comms/                   # Layer 1: Inter-agent communication
├── acl/                     # Layer 1: Access control
│   ├── enforcement.py
│   ├── grants.py
│   ├── policies.py
│   └── roles.py
├── adversarial/             # Layer 1: Defensive intelligence
│   ├── detector.py
│   ├── hallucination.py
│   ├── tamper.py
│   ├── types.py
│   └── verifier.py
├── consolidation/           # Layer 1+4: Dream engine
│   ├── auto.py
│   ├── dream.py
│   └── engine.py
├── vector/                  # Layer 2: Vector storage
│   ├── client.py            # VectorClient, VectorRecord
│   └── embedding.py         # Embedder, CachedEmbedder
├── graph/                   # Layer 2: Graph storage
│   ├── client.py            # GraphClient (InMemory/FalkorDB)
│   └── knowledge.py         # KnowledgeGraph
├── extraction/              # Layer 2: Entity extraction
│   └── types.py             # Entity, NodeType, Relation
├── recall/                  # Layer 2: Hybrid recall pipeline
├── tiered/                  # Layer 2: 3-tier storage
├── reasoning/               # Layer 2: Graph reasoning
│   ├── traversal.py         # Dual-backend traversal
│   └── explanations.py      # Path explanations
├── proactive/               # Layer 3: Proactive engine
├── intelligence/            # Layer 3: Trigger system
├── episodic/                # Layer 3: Episode memory
├── procedural/              # Layer 3: Tool learning
├── user_dna/                # Layer 4: User DNA profiling
├── preferences/             # Layer 4: Preference engine
├── resurrection/            # Layer 4: Context resurrection
├── cognitive/               # Layer 4: Cognitive load
├── sharing/                 # Layer 5: Team sharing
├── sync/                    # Layer 5: Memory sync
├── prediction/              # Layer 6: Action prediction
├── emotional/               # Layer 7: Emotion analysis
├── product_intel/           # Layer 8: Product tracking
├── fusion/                  # Layer 8: Behavioral fusion
├── habits/                  # Layer 8: Habit detection
├── contextual/              # Layer 8: Situation awareness
├── biz_intel/               # Layer 8: Business intelligence
├── bridge/                  # Integration bridge (optional)
├── orchestration/           # Orchestration layer (optional)
├── namespace/               # Namespace management
├── versioning/              # Memory versioning
└── mcp/                     # MCP server (97 tools)
    └── server.py            # FastMCP 3.0+ server
```

---

## Recall Pipeline

Detailed view of the hybrid search pipeline:

### 1. Query Processing

```python
query = "TypeScript frontend frameworks"
```

### 2. Parallel Search (ThreadPoolExecutor)

**Keyword Search:**
- Scans all `.md` files in memory directory
- Matches query terms against content + tags + frontmatter
- Returns: `[(file_path, keyword_score), ...]`

**Vector Search:**
- Embeds query with TF-IDF hash-trick
- Cosine similarity against all stored embeddings
- Returns: `[(memory_id, cosine_distance), ...]`

**Graph Search:**
- Extracts entities from query ("TypeScript", "frontend", "frameworks")
- Traverses knowledge graph for connected entities
- Returns: `[(entity_id, graph_relevance), ...]`

### 3. RRF Fusion

Each result gets an RRF score based on its rank in each result set:

```
RRF(doc) = Σ_i  1 / (60 + rank_i(doc))
```

Documents appearing in multiple result sets get boosted scores.

### 4. Result Assembly

Top-K results are returned with:
- Original content
- Fused relevance score
- Source metadata
- Which backends contributed to the match
