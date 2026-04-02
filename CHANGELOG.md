# Changelog

All notable changes to **memor-ia** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.0] — 2025-07-21

### Added

#### Phase 1 — Core Enhancements
- **Redis Caching Layer** — pluggable cache with in-memory and Redis backends, TTL support, namespace isolation, cache invalidation hooks, LRU eviction
- **Offset-Based Pagination** — paginated search across vector, graph, namespace, and preference stores with configurable `limit`/`offset` and total counts
- **GDPR Cascade Delete** — right-to-erasure compliance with PII scanning (8 patterns), cascade deletion across all stores, audit trail logging, data export

#### Phase 1 — Integration
- **External Webhooks** — webhook registry with CRUD, async HTTP dispatcher (retries + circuit breaker), event bridge for memory lifecycle events, HMAC signature verification

#### Phase 2 — Intelligence
- **LLM-Powered Summarization** — multi-provider engine (Ollama, OpenAI, Anthropic, none/truncation), automatic text chunking, configurable `max_tokens` and `overlap`
- **Semantic Deduplication** — cosine-similarity duplicate detection with 3 modes: `reject` (block), `merge` (auto-combine), `warn` (store + flag), opt-in via env var
- **Memory Templates** — schema-based memory creation with 10 built-in templates (decision, meeting notes, code review, user preference, project status, bug report, learning, conversation summary, action item, feedback), custom template registration

### Changed
- MCP server now exposes **72 tools** (up from 45 in v2.0.0)
- `Memoria.add()` now supports optional deduplication gate (opt-in via `MEMORIA_DEDUP_ENABLED=true`)

### Stats
- **4,464** tests passing (double consecutive clean pass)
- **12** E2E MCP integration tests
- **0** lint errors (ruff)

## [2.0.0] — 2025-06-15

### Added
- Initial public release with FalkorDB graph backend
- SQLite + sqlite-vec vector storage
- FastMCP-based MCP server with 45 tools
- Namespace management, user DNA profiling, preference learning
- Semantic search, relationship mapping, audit trail
- Docker Compose deployment with FalkorDB
- Comprehensive test suite

[2.1.0]: https://github.com/naicud/memor-ia/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/naicud/memor-ia/releases/tag/v2.0.0
