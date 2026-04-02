# API Reference

Complete Python API reference for the MEMORIA framework.

---

## Table of Contents

- [Installation](#installation)
- [Memoria (Main Class)](#memoria-main-class)
  - [Constructor](#constructor)
  - [Core CRUD](#core-crud)
  - [Intelligence](#intelligence)
  - [Tiered Storage](#tiered-storage)
  - [Access Control](#access-control)
  - [Utilities](#utilities)
- [VectorClient](#vectorclient)
- [GraphClient](#graphclient)
- [Knowledge Graph](#knowledge-graph)
- [Embedding](#embedding)
- [Types](#types)
- [Public Imports](#public-imports)
- [Platform Services API](#platform-services-api)
  - [GDPR & Audit](#gdpr--audit)
  - [Webhooks](#webhooks)
  - [Summarization & Dedup](#summarization--dedup)
  - [Templates](#templates)
  - [Streaming](#streaming)
  - [Attachments](#attachments)
  - [Plugins](#plugins)
  - [Dashboard](#dashboard)
  - [Federation](#federation)

---

## Installation

```python
# Core only
pip install -e .

# With MCP server
pip install -e ".[mcp]"

# With all backends
pip install -e ".[full]"
```

---

## Memoria (Main Class)

```python
from memoria import Memoria
```

The primary entry point for all MEMORIA operations.

### Constructor

```python
Memoria(
    project_dir: str | None = None,
    config: dict | None = None
)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `project_dir` | `str \| None` | Root directory for memory files. Defaults to `MEMORIA_DATA_DIR` or `cwd` |
| `config` | `dict \| None` | Optional configuration overrides |

**Example:**

```python
m = Memoria()
m = Memoria(project_dir="/data/project")
m = Memoria(config={"graph_host": "localhost", "graph_port": 6379})
```

### Core CRUD

#### `add()`

Store a new memory.

```python
add(
    content: str,
    user_id: str | None = None,
    agent_id: str | None = None,
    memory_type: str | None = None,
    namespace: str | None = None
) -> str
```

Returns the memory ID (file path).

```python
mid = m.add("User prefers TypeScript", user_id="daniel", memory_type="user")
# → "user/2024-01-15_preferences.md"
```

#### `search()`

Search memories using hybrid recall (keyword + vector + graph → RRF fusion).

```python
search(
    query: str,
    user_id: str | None = None,
    limit: int = 5,
    namespace: str | None = None
) -> list[dict]
```

Returns a list of matches with scores:

```python
results = m.search("language preferences", user_id="daniel")
# → [{"id": "...", "content": "...", "score": 0.87, "metadata": {...}}]
```

#### `get()`

Retrieve a specific memory by ID.

```python
get(memory_id: str) -> dict | None
```

```python
memory = m.get("user/2024-01-15_preferences.md")
# → {"id": "...", "content": "...", "metadata": {...}, "frontmatter": {...}}
```

#### `delete()`

Delete a memory by ID.

```python
delete(memory_id: str) -> bool
```

```python
m.delete("user/2024-01-15_old_note.md")
# → True
```

### Intelligence

#### `suggest()`

Generate proactive suggestions based on context and patterns.

```python
suggest(
    context: str = "",
    user_id: str | None = None
) -> list[dict]
```

```python
suggestions = m.suggest(context="starting a React project", user_id="daniel")
# → [{"suggestion": "...", "confidence": 0.8, "reason": "..."}]
```

#### `profile()`

Build a user profile from interaction history.

```python
profile(user_id: str | None = None) -> dict
```

```python
profile = m.profile(user_id="daniel")
# → {"expertise": {...}, "preferences": {...}, "patterns": {...}}
```

#### `insights()`

Generate cross-database insights.

```python
insights(user_id: str | None = None) -> list[dict]
```

```python
insights = m.insights(user_id="daniel")
# → [{"insight": "...", "confidence": 0.9, "sources": [...]}]
```

### Tiered Storage

#### `add_to_tier()`

Add a memory to a specific storage tier.

```python
add_to_tier(
    content: str,
    tier: str = "working",
    metadata: dict | None = None,
    importance: float | None = None
) -> str
```

**Tiers:**
- `"working"` — Active, frequently accessed (hot)
- `"recall"` — Important but less frequent (warm)
- `"archival"` — Long-term, rarely accessed (cold)

```python
m.add_to_tier("API key pattern for AWS", tier="recall", importance=0.9)
```

#### `search_tiers()`

Search across memory tiers.

```python
search_tiers(
    query: str,
    tiers: list[str] | None = None,
    limit: int = 10
) -> list[dict]
```

```python
results = m.search_tiers("AWS credentials", tiers=["working", "recall"])
```

### Access Control

#### `grant_access()`

Grant an agent access to a namespace.

```python
grant_access(
    agent_id: str,
    namespace: str,
    role: str = "reader"
) -> str
```

**Roles:** `"reader"`, `"writer"`, `"admin"`

```python
m.grant_access("code-agent", "shared-docs", role="writer")
```

#### `check_access()`

Check if an agent has access to a namespace.

```python
check_access(
    agent_id: str,
    namespace: str,
    operation: str = "read"
) -> bool
```

```python
m.check_access("code-agent", "shared-docs", operation="write")
# → True
```

### Utilities

#### `enrich()`

Enrich content with automatic extraction.

```python
enrich(content: str) -> dict
```

```python
m.enrich("We should use PostgreSQL for the new auth service")
# → {"category": "architecture", "tags": ["database", "auth"], "entities": [...]}
```

#### `sync()`

Sync memories with remote transport.

```python
sync(namespace: str | None = None) -> dict
```

---

## VectorClient

```python
from memoria.vector.client import VectorClient
```

SQLite-backed vector storage with cosine similarity search.

### Constructor

```python
VectorClient(
    db_path: str | None = None,
    dimension: int = 128
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `db_path` | `str \| None` | `None` (in-memory) | SQLite database path |
| `dimension` | `int` | `128` | Embedding vector dimension |

### Methods

#### `insert()`

Insert a vector record.

```python
from memoria.vector.client import VectorRecord

record = VectorRecord(
    id="mem_001",
    embedding=[0.1, 0.2, ...],  # list[float]
    content="User prefers TypeScript",
    metadata={"user_id": "daniel", "type": "preference"}
)
client.insert(record)
```

> **Note:** Use `VectorRecord` dataclass, not positional arguments.

#### `search()`

Search by cosine similarity.

```python
results = client.search(
    query_embedding=[0.1, 0.2, ...],
    limit=5
)
# → [VectorRecord(id="mem_001", ..., distance=0.15)]
```

#### `delete()`

Delete a vector by ID.

```python
client.delete("mem_001")
```

---

## GraphClient

```python
from memoria.graph.client import GraphClient
```

Dual-backend graph client (InMemoryGraph or FalkorDB).

### Constructor

```python
# InMemoryGraph (default)
GraphClient(use_memory=True)

# FalkorDB
GraphClient(host="localhost", port=6379)

# Auto-detect (FalkorDB if installed + available)
GraphClient()
```

### Backend Selection

| Configuration | Backend | Persistence |
|---------------|---------|-------------|
| `GraphClient(use_memory=True)` | InMemoryGraph | Ephemeral |
| `GraphClient(host=..., port=...)` | FalkorDB | Persistent |
| `GraphClient()` + falkordb installed | FalkorDB (auto) | Persistent |
| `GraphClient()` + no falkordb | InMemoryGraph | Ephemeral |

### Methods

#### `add_entity()`

Add a node to the graph.

```python
from memoria.extraction.types import Entity, NodeType

entity = Entity(
    name="python",
    entity_type=NodeType.TECHNOLOGY,
    confidence=0.95,
    source_text="User works with Python"
)
node_id = graph.add_entity(entity)
# InMemoryGraph → UUID string (e.g., "a1b2c3d4-...")
# FalkorDB → integer as string (e.g., "15")
```

> **Important:** `add_entity()` takes an `Entity` object, not keyword arguments. The return type differs by backend.

#### `add_relation()`

Add an edge between two entities.

```python
graph.add_relation(
    source_id=node_id_1,
    target_id=node_id_2,
    relation_type="uses",
    properties={"since": "2020"}
)
```

#### `search_entities()`

Search entities by name or type.

```python
results = graph.search_entities("python")
```

---

## Knowledge Graph

```python
from memoria.graph.knowledge import KnowledgeGraph
```

Higher-level knowledge graph with entity extraction and relationship inference.

### Methods

```python
kg = KnowledgeGraph(graph_client=graph)

# Ingest text — auto-extract entities and relationships
kg.ingest("Daniel uses Python and TypeScript for web development")

# Search entities
entities = kg.search("python")

# Get entity profile
profile = kg.entity_profile("python")

# Get graph statistics
stats = kg.stats()
# → {"nodes": 85, "edges": 120, "by_type": {"technology": 30, "person": 10}}
```

---

## Embedding

```python
from memoria.vector.embedding import Embedder, CachedEmbedder
```

### Embedder

TF-IDF hash-trick embedder — zero ML dependencies.

```python
embedder = Embedder(dimension=384)
vector = embedder.embed("User prefers TypeScript")
# → [0.0, 0.0, 0.42, 0.0, ...] (sparse, L2-normalized)
```

### CachedEmbedder

LRU-cached embedder for repeated queries.

```python
cached = CachedEmbedder(dimension=384, max_size=1000)
vector = cached.embed("User prefers TypeScript")
# First call: ~0.1ms (compute)
# Subsequent: ~0.0002ms (cache hit)
```

> **Note:** The parameter is `max_size`, not `cache_size`.

---

## Types

### Entity

```python
from memoria.extraction.types import Entity, NodeType

entity = Entity(
    name="python",                    # str — entity name (lowercase)
    entity_type=NodeType.TECHNOLOGY,  # NodeType enum
    confidence=0.95,                  # float 0.0-1.0
    source_text="Uses Python daily"   # str — source text
)

entity.name          # → "python"
entity.entity_type   # → NodeType.TECHNOLOGY
entity.entity_type.value  # → "technology" (string)
```

> **Note:** `Entity` is not subscriptable. Use attribute access (`.name`), not dict access (`["name"]`).

### NodeType

```python
from memoria.extraction.types import NodeType

NodeType.PERSON       # "person"
NodeType.TECHNOLOGY   # "technology"
NodeType.CONCEPT      # "concept"
NodeType.PROJECT      # "project"
NodeType.ORGANIZATION # "organization"
```

### VectorRecord

```python
from memoria.vector.client import VectorRecord

record = VectorRecord(
    id="mem_001",          # str
    embedding=[0.1, ...],  # list[float]
    content="...",          # str
    metadata={...},         # dict
    distance=0.15           # float (set by search results)
)
```

### MemoryType

```python
from memoria.core import MemoryType

MemoryType.USER       # "user"
MemoryType.PROJECT    # "project"
MemoryType.FEEDBACK   # "feedback"
MemoryType.REFERENCE  # "reference"
```

### MemoryFrontmatter

```python
from memoria.core import MemoryFrontmatter

fm = MemoryFrontmatter(
    type="user",
    created="2024-01-15T10:30:00",
    tags=["python", "preferences"],
    importance=0.8,
    user_id="daniel"
)
```

---

## Public Imports

Everything importable from the top-level `memoria` package:

```python
from memoria import Memoria

from memoria.core import (
    MemoryType,
    MemoryFrontmatter,
    read_memory_file,
    write_memory_file,
    scan_memory_files,
    ensure_memory_dir_exists,
    get_project_dir,
    ImportanceScorer,
    ImportanceTracker,
    SelfEditingMemory,
)

from memoria.vector.client import VectorClient, VectorRecord
from memoria.vector.embedding import Embedder, CachedEmbedder
from memoria.graph.client import GraphClient
from memoria.graph.knowledge import KnowledgeGraph
from memoria.extraction.types import Entity, NodeType
```

---

## Platform Services API

All platform methods are accessed through the `Memoria` class.

### GDPR & Audit

```python
m = Memoria()

# Right to be forgotten — erases all user data
result = m.gdpr_forget(user_id="user-123")
# → {"status": "completed", "files_deleted": 12, "vectors_deleted": 8, ...}

# Export all user data (DSAR)
export = m.gdpr_export(user_id="user-123")
# → {"memories": [...], "preferences": {...}, "episodic": [...]}

# Query audit trail
logs = m.audit_query(event_type="memory_created", limit=10)
# → [{"event": "memory_created", "timestamp": "...", "actor": "..."}]

# Audit statistics
stats = m.audit_stats()
# → {"total_events": 1234, "by_type": {"memory_created": 500, ...}}
```

### Webhooks

```python
# Register a webhook
result = m.webhook_register(
    url="https://hooks.example.com/memoria",
    events=["memory_created", "memory_deleted"],
    secret="hmac-secret",
    description="Slack notification"
)
# → {"webhook_id": "wh_abc123", "url": "...", "active": true}

# List webhooks
hooks = m.webhook_list(active_only=True)
# → [{"webhook_id": "wh_abc123", "url": "...", "events": [...]}]

# Unregister
m.webhook_unregister(webhook_id="wh_abc123")
```

### Summarization & Dedup

```python
# Summarize text
summary = m.summarize(
    content="Long text to summarize...",
    max_tokens=100
)
# → {"summary": "...", "key_facts": [...], "compression_ratio": 0.7}

# Summarize all memories for a user
result = m.summarize_all(user_id="user-123", limit=50)
# → {"summarized": 12, "results": [...]}

# Scan for duplicates
dupes = m.dedup_scan(threshold=0.85, namespace="default")
# → {"groups": [{"ids": ["a", "b"], "similarity": 0.92}]}

# Merge duplicates
m.dedup_merge(memory_ids=["a", "b"], strategy="best")
```

### Templates

```python
# Create a structured template
m.template_create(
    name="bug-report",
    description="Bug report template",
    fields=[
        {"name": "title", "type": "string", "required": True},
        {"name": "steps", "type": "string", "required": True},
        {"name": "expected", "type": "string", "required": False},
    ],
    content_template="Bug: {title}\nSteps: {steps}\nExpected: {expected}",
    category="engineering"
)

# List templates
templates = m.template_list(category="engineering")
# → [{"name": "bug-report", "fields": 3, "category": "engineering"}]

# Apply a template
result = m.template_apply(
    template_name="bug-report",
    data={"title": "Login fails", "steps": "Click login → 500 error"}
)
# → Creates a structured memory from the template
```

### Streaming

```python
# Subscribe to real-time events
channel = m.stream_subscribe(
    channel_type="sse",
    event_types=["memory_created", "memory_updated"],
    namespaces=["dev"]
)
# → {"channel_id": "abc123", "type": "sse", "filter": {...}}

# Broadcast an event
m.stream_broadcast(
    event_type="memory_created",
    data={"memory_id": "m-123", "content": "..."}
)

# List active channels
channels = m.stream_list_channels()

# Statistics
stats = m.stream_stats()
# → {"total_channels": 3, "sse_channels": 2, "ws_channels": 1}

# Unsubscribe
m.stream_unsubscribe(channel_id="abc123")
```

### Attachments

```python
# Attach a file to a memory
result = m.add_attachment(
    memory_id="memory-abc",
    data=b"\x89PNG...",  # raw bytes
    filename="diagram.png",
    mime_type="image/png",
    description="Architecture diagram"
)
# → {"attachment_id": "att_xyz", "filename": "diagram.png", "size": 1234}

# List attachments
attachments = m.list_attachments(memory_id="memory-abc")

# Get attachment metadata
meta = m.get_attachment(attachment_id="att_xyz")

# Get attachment binary data
data = m.get_attachment_data(attachment_id="att_xyz")
# → b"\x89PNG..."

# Delete
m.delete_attachment(attachment_id="att_xyz")

# Statistics
stats = m.attachment_stats()
# → {"total_attachments": 15, "disk_usage_bytes": 1048576}
```

### Plugins

```python
# Discover available plugins
discovered = m.plugin_discover()

# List registered plugins
plugins = m.plugin_list()
# → [{"name": "my-plugin", "active": false, "version": "1.0.0"}]

# Activate / deactivate
m.plugin_activate(name="my-plugin")
m.plugin_deactivate(name="my-plugin")

# Statistics
stats = m.plugin_stats()
# → {"registered": 3, "active": 1}

# Register a custom plugin
from memoria.plugins import PluginBase
class MyPlugin(PluginBase):
    name = "my-plugin"
    version = "1.0.0"

m.plugin_register(MyPlugin)
```

### Dashboard

```python
# Start the web dashboard
m.dashboard_start(host="127.0.0.1", port=8080)

# Get dashboard URL
url = m.dashboard_url()
# → "http://127.0.0.1:8080"

# Check status
status = m.dashboard_status()
# → {"running": true, "host": "127.0.0.1", "port": 8080}

# Stop
m.dashboard_stop()
```

The dashboard provides:
- 📊 Memory explorer with filtering and search
- 🕸️ D3.js knowledge graph visualization
- 📋 Audit log viewer
- ⚙️ Settings and configuration

### Federation

```python
# Connect to a peer instance
peer = m.federation_connect(
    endpoint="https://team-b.example.com/mcp",
    instance_id="team-b",
    shared_namespaces=["shared", "dev"],
    direction="bidirectional"
)
# → {"instance_id": "team-b", "status": "connected"}

# Configure trust
m.federation_trust_add(
    instance_id="team-b",
    trust_level="elevated"  # untrusted|standard|elevated|full
)

# Synchronize a namespace
result = m.federation_sync(peer_id="team-b", namespace="shared")
# → {"pushed": 5, "pulled": 3, "conflicts_resolved": 1}

# Check federation status
status = m.federation_status()
# → {"protocol": {"total_peers": 2}, "trust": {"valid": 2}, "sync": {...}}

# Disconnect
m.federation_disconnect(peer_id="team-b")
```

Federation features:
- 🔐 PKI trust registry with 4 trust levels
- 🔄 CRDT vector clock conflict resolution (LWW, merge, local-first, remote-first)
- 📡 Selective namespace synchronization (push/pull/bidirectional)
- 🤝 Peer-to-peer message exchange protocol
