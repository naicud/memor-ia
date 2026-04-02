# Configuration Guide

Complete guide to configuring MEMORIA backends, storage, and behavior.

---

## Table of Contents

- [Environment Variables](#environment-variables)
- [Storage Backends](#storage-backends)
  - [Core Storage (Markdown)](#core-storage-markdown)
  - [Vector Backend](#vector-backend)
  - [Graph Backend](#graph-backend)
  - [Embedding Engine](#embedding-engine)
- [Backend Architecture](#backend-architecture)
- [FalkorDB Setup](#falkordb-setup)
- [SQLite-vec Setup](#sqlite-vec-setup)
- [Python API Configuration](#python-api-configuration)
- [MCP Server Configuration](#mcp-server-configuration)
- [Makefile Targets](#makefile-targets)

---

## Environment Variables

All MEMORIA behavior can be configured via environment variables:

### MCP Server

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `MEMORIA_TRANSPORT` | Transport protocol | `stdio` | `http` |
| `MEMORIA_HOST` | HTTP bind address | `127.0.0.1` | `0.0.0.0` |
| `MEMORIA_PORT` | HTTP port | `8080` | `3000` |
| `MEMORIA_DATA_DIR` | Memory storage root | `cwd` | `/data/memoria` |

### Graph Backend

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `MEMORIA_GRAPH_HOST` | FalkorDB host | _(not set)_ | `localhost` |
| `MEMORIA_GRAPH_PORT` | FalkorDB port | `6379` | `6380` |

When `MEMORIA_GRAPH_HOST` is not set, MEMORIA uses InMemoryGraph (pure Python, no dependencies).

### Vector Backend

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `MEMORIA_VECTOR_DB` | SQLite database path | _(in-memory)_ | `/data/vectors.db` |
| `MEMORIA_EMBEDDING_DIM` | Embedding dimension | `384` | `128` |

### Cache Backend (v2.1)

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `MEMORIA_CACHE_BACKEND` | Cache type | `memory` | `redis` |
| `MEMORIA_REDIS_URL` | Redis connection string | `redis://localhost:6379/0` | `redis://cache:6379/1` |
| `MEMORIA_CACHE_PREFIX` | Key prefix for namespacing | `memoria:` | `myapp:memoria:` |
| `MEMORIA_CACHE_MAX_SIZE` | Max entries (in-memory only) | `1024` | `4096` |
| `MEMORIA_CACHE_TTL` | Default TTL in seconds | _(none for memory, 3600 for redis)_ | `600` |

### Platform Services (v2.1–v3.0)

#### Webhooks

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMORIA_WEBHOOK_TIMEOUT` | `10` | HTTP request timeout for webhook delivery (seconds) |
| `MEMORIA_WEBHOOK_RETRY` | `3` | Number of retries for failed deliveries |

#### Streaming

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMORIA_STREAM_MAX_CHANNELS` | `100` | Maximum concurrent channels |
| `MEMORIA_STREAM_BUFFER_SIZE` | `1000` | Event buffer size per channel |

#### Dashboard

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMORIA_DASHBOARD_HOST` | `127.0.0.1` | Dashboard bind address |
| `MEMORIA_DASHBOARD_PORT` | `8080` | Dashboard port |
| `MEMORIA_DASHBOARD_ENABLED` | `false` | Enable dashboard at startup |

#### Federation

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMORIA_FEDERATION_ENDPOINT` | _(not set)_ | This instance's advertised endpoint URL |
| `MEMORIA_FEDERATION_INSTANCE_ID` | _(not set)_ | Unique instance identifier for federation |
| `MEMORIA_FEDERATION_DEFAULT_TRUST` | `standard` | Default trust level for new peers |
| `MEMORIA_FEDERATION_SYNC_INTERVAL` | `300` | Auto-sync interval in seconds |

#### Attachments

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMORIA_ATTACHMENT_MAX_SIZE` | `10485760` | Maximum attachment size in bytes (10 MB) |
| `MEMORIA_ATTACHMENT_STORE_PATH` | `.memoria/attachments` | Path for attachment file storage |

#### Plugins

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMORIA_PLUGIN_DIR` | `.memoria/plugins` | Directory to scan for plugins |
| `MEMORIA_PLUGIN_AUTOLOAD` | `false` | Auto-load discovered plugins |

### Shell Configuration

```bash
# Minimal (pure Python backends)
export MEMORIA_DATA_DIR=/path/to/project

# With FalkorDB
export MEMORIA_GRAPH_HOST=localhost
export MEMORIA_GRAPH_PORT=6379

# With persistent vector DB
export MEMORIA_VECTOR_DB=/data/vectors.db
export MEMORIA_EMBEDDING_DIM=384

# With Redis cache (multi-pod deployments)
export MEMORIA_CACHE_BACKEND=redis
export MEMORIA_REDIS_URL=redis://cache:6379/0
export MEMORIA_CACHE_TTL=3600

# HTTP transport
export MEMORIA_TRANSPORT=http
export MEMORIA_HOST=0.0.0.0
export MEMORIA_PORT=8080
```

---

## Storage Backends

MEMORIA uses a layered storage architecture. Every backend has a **zero-dependency pure-Python fallback**.

### Core Storage (Markdown)

**Always active.** No configuration needed.

Memories are stored as Markdown files with YAML frontmatter:

```
~/.memoria/projects/{project_hash}/memory/
├── user/
│   ├── 2024-01-15_preferences.md
│   └── 2024-01-16_workflow.md
├── project/
│   └── 2024-01-15_architecture.md
├── feedback/
│   └── 2024-01-15_review.md
└── reference/
    └── 2024-01-15_api_docs.md
```

Each file looks like:

```markdown
---
type: user
created: 2024-01-15T10:30:00
tags: [preferences, typescript, frontend]
importance: 0.8
user_id: daniel
---
User prefers TypeScript for all frontend projects.
Uses React with Next.js for new projects.
Prefers functional components over class components.
```

**Memory types:**
- `user` — User preferences, habits, personal info
- `project` — Project-specific knowledge, architecture decisions
- `feedback` — User feedback, corrections, ratings
- `reference` — Reference material, documentation, API notes

### Vector Backend

Two modes:

#### In-Memory SQLite (default)

No configuration needed. Vector embeddings are stored in SQLite with two tables:

- `vec_metadata` — id, content, metadata (JSON), user_id, memory_type, created_at
- `vec_embeddings` — id, embedding (JSON array of floats)

Search uses pure-Python cosine similarity. Data is ephemeral (lost on restart) unless `MEMORIA_VECTOR_DB` is set.

#### Persistent SQLite

Set `MEMORIA_VECTOR_DB` to persist vectors to disk:

```bash
export MEMORIA_VECTOR_DB=/data/vectors.db
```

The schema is identical. Data survives restarts.

#### SQLite-vec Extension

For hardware-accelerated vector search, install the `sqlite-vec` extension:

```bash
pip install sqlite-vec
```

This replaces pure-Python cosine search with native SIMD-optimized similarity.

### Graph Backend

Two modes:

#### InMemoryGraph (default)

Pure Python, zero dependencies. Uses Python dicts with UUID keys:

- Nodes: `_Node(id=UUID, label=str, properties=dict)`
- Edges: `_Edge(source=UUID, target=UUID, label=str, properties=dict)`

Data is ephemeral (lost on restart).

#### FalkorDB

Production-grade graph database (Redis-compatible protocol, Cypher queries):

```bash
# Install client
pip install falkordb

# Start FalkorDB
docker run -p 6379:6379 falkordb/falkordb:latest

# Configure
export MEMORIA_GRAPH_HOST=localhost
export MEMORIA_GRAPH_PORT=6379
```

FalkorDB uses integer node IDs (not UUIDs) and Cypher queries:

```cypher
CREATE (n:entity {name: 'Python', entity_type: 'technology'})
MATCH (a)-[r]->(b) WHERE ID(a) = 15 RETURN b
```

### Embedding Engine

MEMORIA uses a **TF-IDF hash-trick** embedding model — zero ML dependencies:

- Projects text into a fixed-dimension vector via murmurhash of word tokens
- Sparse: ~6-7 nonzero values out of `MEMORIA_EMBEDDING_DIM` dimensions
- L2-normalized to 1.0
- Consistent 5x discrimination ratio (similar vs dissimilar content)
- CachedEmbedder: 0.0002ms/call for cache hits

Configure the dimension:

```bash
# Higher dimension = more precision, more memory
export MEMORIA_EMBEDDING_DIM=384   # default
export MEMORIA_EMBEDDING_DIM=128   # lighter
export MEMORIA_EMBEDDING_DIM=64    # minimal
```

---

## Backend Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    MCP Server (97 tools)                 │
├─────────────────────────────────────────────────────────┤
│                  Memoria Core API                       │
├─────────────┬───────────────┬───────────────────────────┤
│  Core Store │  Vector Store  │       Graph Store         │
│  (Markdown) │  (SQLite)      │  (InMemory / FalkorDB)   │
├─────────────┼───────────────┼───────────────────────────┤
│  ~/.memoria/ │  SQLite DB     │  Dict / Redis:6379       │
│  /memory/   │  (in-mem or    │                           │
│  *.md files │   persistent)  │                           │
└─────────────┴───────────────┴───────────────────────────┘
```

The **Hybrid Recall Pipeline** merges results from all three backends using Reciprocal Rank Fusion (RRF):

1. **Keyword search** — File-based scanning with text matching
2. **Vector search** — Cosine similarity on TF-IDF embeddings
3. **Graph search** — Entity and relationship traversal

Results are fused with RRF scoring and returned ranked by relevance.

---

## FalkorDB Setup

### With Docker (recommended)

```bash
# Start FalkorDB
docker run -d --name falkordb -p 6379:6379 falkordb/falkordb:latest

# Verify
docker exec -it falkordb redis-cli PING
# → PONG
```

### With Docker Compose

```bash
# In the memor-ia directory
docker compose up falkordb -d

# Verify
docker compose exec falkordb redis-cli PING
```

### Install Python Client

```bash
pip install falkordb
# or
pip install -e ".[graph]"
```

### Verify Connection

```python
from falkordb import FalkorDB

db = FalkorDB(host="localhost", port=6379)
graph = db.select_graph("test")
graph.query("RETURN 1")
print("FalkorDB connected!")
```

### Configure MEMORIA

```bash
export MEMORIA_GRAPH_HOST=localhost
export MEMORIA_GRAPH_PORT=6379
```

Or in Python:

```python
from memoria import Memoria
from memoria.graph.client import GraphClient

graph = GraphClient(host="localhost", port=6379)
m = Memoria(graph_client=graph)
```

---

## SQLite-vec Setup

```bash
# Install
pip install sqlite-vec
# or
pip install -e ".[vector]"
```

### Verify

```python
import sqlite3
import sqlite_vec

db = sqlite3.connect(":memory:")
db.enable_load_extension(True)
sqlite_vec.load(db)
print("sqlite-vec loaded!")
```

> **Note:** Some Python builds don't support `enable_load_extension`. In that case, MEMORIA falls back to pure-Python cosine similarity automatically.

---

## Python API Configuration

```python
from memoria import Memoria

# Minimal — all defaults (pure Python backends)
m = Memoria()

# With project directory
m = Memoria(project_dir="/path/to/project")

# With custom config dict
m = Memoria(config={
    "project_dir": "/data/project",
    "graph_host": "localhost",
    "graph_port": 6379,
    "vector_db": "/data/vectors.db",
    "embedding_dim": 384,
})
```

### Backend-Specific Initialization

```python
from memoria.graph.client import GraphClient
from memoria.vector.client import VectorClient

# FalkorDB graph
graph = GraphClient(host="localhost", port=6379)

# InMemory graph (default)
graph = GraphClient(use_memory=True)

# Persistent vector store
vector = VectorClient(db_path="/data/vectors.db", dimension=384)

# In-memory vector store (default)
vector = VectorClient(dimension=128)
```

---

## MCP Server Configuration

### CLI Options

```bash
memoria-mcp [OPTIONS]

Options:
  --transport [stdio|http]   Transport protocol (default: stdio)
  --host TEXT                HTTP bind address (default: 127.0.0.1)
  --port INT                 HTTP port (default: 8080)
  --project-dir PATH         Memory storage directory (default: cwd)
```

### Precedence

Environment variables override CLI defaults:

1. CLI arguments (highest priority)
2. Environment variables
3. Built-in defaults (lowest priority)

---

## Makefile Targets

Run `make help` for the full list. Key targets:

### Setup

```bash
make venv          # Create virtual environment with UV
make install       # Install core + MCP deps
make install-dev   # Install with dev + test deps
make install-full  # Install everything (graph, vector, MCP, dev, test)
```

### Testing

```bash
make test          # Run test suite (quiet)
make test-verbose  # Run with verbose output
make test-e2e      # Run E2E backend tests (local only)
make test-e2e-full # Run E2E with FalkorDB (requires docker compose up falkordb)
make test-cov      # Run with coverage report
```

### Development

```bash
make lint          # Run ruff linter
make lint-fix      # Auto-fix linting issues
make typecheck     # Run mypy
make check         # Run all quality checks (lint + typecheck + test)
```

### Server

```bash
make serve         # Start MCP server (stdio)
make serve-http    # Start MCP server (HTTP, port 8080)
```

### Docker

```bash
make docker-build  # Build Docker image
make docker-run    # Run MCP in Docker
make docker-up     # Start with docker-compose (MEMORIA + FalkorDB)
make docker-down   # Stop docker-compose
```

### Package

```bash
make build         # Build distribution package
make clean         # Clean build artifacts and caches
```
