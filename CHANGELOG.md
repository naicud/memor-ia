# Changelog

All notable changes to **memor-ia** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] — 2025-07-21

### Added

#### Real-time Streaming (Phase 3.1)
- **SSE channels** with async queue, keepalive heartbeats, and overflow protection
- **WebSocket channels** with bidirectional messaging and dynamic filter updates
- **Stream filters** — filter events by type, namespace, or custom predicate
- **StreamManager** — central registry with event bus bridge and fan-out dispatch
- 5 new MCP tools: `subscribe_stream`, `unsubscribe_stream`, `list_streams`, `stream_stats`, `stream_replay`
- 70 new tests

#### Multi-modal Memory (Phase 3.2)
- **Binary attachment storage** with content-addressable SHA-256 integrity checks
- **Metadata extraction** — graceful degradation when PIL/mutagen unavailable
- **AttachmentStore** with `blobs/` + `meta/` directory layout and JSON sidecars
- 5 new MCP tools: `add_attachment`, `get_attachment`, `list_attachments`, `delete_attachment`, `attachment_stats`
- 47 new tests

#### Plugin System (Phase 3.3)
- **MemoriaPlugin ABC** with lifecycle hooks (activate/deactivate) and extension points
- **PluginRegistry** — thread-safe registry with event dispatch
- **Entry-point discovery** via `importlib.metadata` for pip-installable plugins
- 5 new MCP tools: `list_plugins`, `activate_plugin`, `deactivate_plugin`, `plugin_info`, `plugin_events`
- 45 new tests

### Fixed
- Multimodal integration tests made resilient to shared state (relative counts)

### Stats
- Total MCP tools: **87** (was 72)
- Total tests: **4,626 passing** (was 4,464)

---

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
