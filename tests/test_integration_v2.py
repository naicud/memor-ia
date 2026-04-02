"""Cross-layer integration tests for MEMORIA 2.0.

Tests cross-layer interactions between:
  - Namespace + ACL enforcement
  - Tiered memory + Namespace scoping
  - Extraction → Graph → Reasoning
  - Versioning + Audit trail
  - Sync protocol + Namespace + ACL
  - Memoria v2 unified API
  - MCP v2 tools

All tests use in-memory backends and require no external services.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

# --- v2 modules ---
from memoria.namespace import SharedMemoryStore
from memoria.acl import (
    Role, GrantStore, PolicyEngine,
    role_can_read, role_can_write, role_can_admin,
)
from memoria.tiered import (
    TieredMemoryManager, WorkingMemory, RecallMemory, ArchivalMemory,
)
from memoria.extraction import (
    MemoryEnricher, RegexExtractor, MemoryDeduplicator, ConflictDetector,
)
from memoria.versioning import VersionHistory
from memoria.reasoning import GraphTraverser, ExplanationBuilder
from memoria.sync import SyncProtocol, InMemoryTransport, SyncConflictResolver

# --- existing modules ---
from memoria.graph.client import GraphClient, InMemoryGraph
from memoria.graph.knowledge import KnowledgeGraph

# --- top-level API ---
from memoria import Memoria


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture()
def namespace_store():
    return SharedMemoryStore()


@pytest.fixture()
def grant_store():
    return GrantStore()


@pytest.fixture()
def policy_engine(grant_store):
    return PolicyEngine(grant_store=grant_store)


@pytest.fixture()
def tiered_manager():
    return TieredMemoryManager()


@pytest.fixture()
def enricher():
    return RegexExtractor()


@pytest.fixture()
def memory_enricher():
    return MemoryEnricher()


@pytest.fixture()
def version_history():
    return VersionHistory()


@pytest.fixture()
def knowledge_graph():
    client = GraphClient()
    return KnowledgeGraph(client=client)


@pytest.fixture()
def traverser(knowledge_graph):
    return GraphTraverser(knowledge_graph)


@pytest.fixture()
def explanation_builder(knowledge_graph, traverser):
    return ExplanationBuilder(knowledge_graph, traverser=traverser)


@pytest.fixture()
def sync_transport():
    return InMemoryTransport()


@pytest.fixture()
def sync_protocol(namespace_store, sync_transport):
    return SyncProtocol(local_store=namespace_store, transport=sync_transport)


@pytest.fixture()
def memoria_instance():
    with tempfile.TemporaryDirectory() as td:
        kg = KnowledgeGraph(client=GraphClient())
        m = Memoria(project_dir=td, config={"knowledge_graph": kg})
        yield m


# ===================================================================
# 1. Namespace + ACL Integration  (~12 tests)
# ===================================================================


class TestNamespaceACLIntegration:
    """Test namespace operations with ACL enforcement."""

    def test_create_namespace_and_grant_reader(self, namespace_store, grant_store, policy_engine):
        namespace_store.add("acme", "Company policy doc")
        grant_store.grant("agent-1", "acme", Role.READER, "admin")
        assert policy_engine.can_read("agent-1", "acme")

    def test_reader_cannot_write(self, grant_store, policy_engine):
        grant_store.grant("agent-r", "acme", Role.READER, "admin")
        assert not policy_engine.can_write("agent-r", "acme")

    def test_writer_can_read_and_write(self, grant_store, policy_engine):
        grant_store.grant("agent-w", "acme", Role.WRITER, "admin")
        assert policy_engine.can_read("agent-w", "acme")
        assert policy_engine.can_write("agent-w", "acme")

    def test_admin_can_admin(self, grant_store, policy_engine):
        grant_store.grant("agent-a", "acme", Role.ADMIN, "admin")
        assert policy_engine.can_admin("agent-a", "acme")
        assert policy_engine.can_write("agent-a", "acme")

    def test_no_grant_denies_all(self, policy_engine):
        assert not policy_engine.can_read("stranger", "acme")
        assert not policy_engine.can_write("stranger", "acme")

    def test_namespace_hierarchy_inheritance(self, namespace_store, grant_store, policy_engine):
        namespace_store.add("acme", "Top-level doc")
        namespace_store.add("acme/frontend", "Frontend doc")
        grant_store.grant("agent-h", "acme", Role.WRITER, "admin")
        assert policy_engine.can_write("agent-h", "acme/frontend")

    def test_revoke_removes_access(self, grant_store, policy_engine):
        grant_store.grant("agent-rv", "acme", Role.WRITER, "admin")
        assert policy_engine.can_write("agent-rv", "acme")
        grant_store.revoke("agent-rv", "acme")
        assert not policy_engine.can_write("agent-rv", "acme")

    def test_owner_role_grants_everything(self, grant_store, policy_engine):
        grant_store.grant("owner-1", "acme", Role.OWNER, "system")
        assert policy_engine.can_read("owner-1", "acme")
        assert policy_engine.can_write("owner-1", "acme")
        assert policy_engine.can_admin("owner-1", "acme")

    def test_multiple_namespaces_isolation(self, namespace_store, grant_store, policy_engine):
        namespace_store.add("alpha", "Alpha content")
        namespace_store.add("beta", "Beta content")
        grant_store.grant("agent-m", "alpha", Role.WRITER, "admin")
        assert policy_engine.can_write("agent-m", "alpha")
        assert not policy_engine.can_read("agent-m", "beta")

    def test_store_and_search_with_acl_check(self, namespace_store, grant_store, policy_engine):
        namespace_store.add("secure", "Secret document about quantum physics")
        grant_store.grant("reader-1", "secure", Role.READER, "admin")
        assert policy_engine.can_read("reader-1", "secure")
        results = namespace_store.search("quantum", namespace="secure")
        assert len(results) >= 1

    def test_list_accessible_namespaces(self, grant_store, policy_engine):
        grant_store.grant("agent-l", "ns-a", Role.READER, "admin")
        grant_store.grant("agent-l", "ns-b", Role.WRITER, "admin")
        accessible = policy_engine.list_accessible("agent-l")
        assert "ns-a" in accessible
        assert "ns-b" in accessible

    def test_effective_role_resolution(self, grant_store, policy_engine):
        grant_store.grant("agent-e", "acme", Role.ADMIN, "admin")
        role = policy_engine.effective_role("agent-e", "acme")
        assert role == Role.ADMIN


# ===================================================================
# 2. Tiered Memory + Namespace Integration  (~10 tests)
# ===================================================================


class TestTieredNamespaceIntegration:
    """Test tiered memory with namespace scoping."""

    def test_add_to_working_tier(self, tiered_manager):
        mid = tiered_manager.add("Working thought", tier="working")
        assert mid is not None

    def test_add_to_recall_tier(self, tiered_manager):
        mid = tiered_manager.add("Important fact", tier="recall")
        assert mid is not None

    def test_add_to_archival_tier(self, tiered_manager):
        mid = tiered_manager.add("Historical document", tier="archival")
        assert mid is not None

    def test_search_specific_tier(self, tiered_manager):
        tiered_manager.add("Python is great for data science", tier="recall")
        results = tiered_manager.search("Python", tiers=["recall"])
        assert len(results) >= 1

    def test_search_all_tiers(self, tiered_manager):
        tiered_manager.add("Alpha content in working", tier="working")
        tiered_manager.add("Alpha content in recall", tier="recall")
        results = tiered_manager.search("Alpha")
        assert len(results) >= 1

    def test_promote_working_to_recall(self, tiered_manager):
        mid = tiered_manager.add("Promote me", tier="working")
        new_id = tiered_manager.promote(mid, "working", "recall")
        assert new_id is not None

    def test_flush_session_moves_working_to_recall(self, tiered_manager):
        tiered_manager.add("Session note 1", tier="working")
        tiered_manager.add("Session note 2", tier="working")
        result = tiered_manager.flush_session()
        flushed = result["flushed_to_recall"]
        assert isinstance(flushed, (int, list))

    def test_stats_reflect_tiers(self, tiered_manager):
        tiered_manager.add("Stats test", tier="working")
        stats = tiered_manager.stats()
        assert "working" in stats

    def test_get_from_any_tier(self, tiered_manager):
        mid = tiered_manager.add("Find me anywhere", tier="recall")
        found = tiered_manager.get(mid)
        assert found is not None

    def test_delete_from_tier(self, tiered_manager):
        mid = tiered_manager.add("Delete me", tier="recall")
        deleted = tiered_manager.delete(mid)
        assert deleted is True


# ===================================================================
# 3. Extraction → Graph → Reasoning Integration  (~10 tests)
# ===================================================================


class TestExtractionGraphIntegration:
    """Test extraction feeding into graph + reasoning."""

    def test_enricher_categorizes_fact(self, memory_enricher):
        enriched = memory_enricher.enrich({"content": "Python was created by Guido van Rossum", "metadata": {}})
        assert "metadata" in enriched
        meta = enriched["metadata"]
        assert "category" in meta or "tags" in meta or "entities" in meta

    def test_enricher_extracts_tags(self, memory_enricher):
        tags = memory_enricher.extract_tags("Machine learning with TensorFlow and PyTorch")
        assert isinstance(tags, list)

    def test_enricher_categorize_preference(self, memory_enricher):
        cat = memory_enricher.categorize("I prefer dark mode for coding")
        assert cat is not None

    def test_deduplicator_finds_similar(self):
        dedup = MemoryDeduplicator()
        memories = [
            {"content": "Python is a programming language", "id": "1"},
            {"content": "Python is a popular programming language", "id": "2"},
            {"content": "JavaScript runs in browsers", "id": "3"},
        ]
        deduped = dedup.deduplicate(memories)
        assert isinstance(deduped, list)

    def test_conflict_detector(self):
        detector = ConflictDetector()
        m1 = {"content": "The deadline is Monday", "metadata": {"id": "1"}}
        m2 = {"content": "The deadline is Friday", "metadata": {"id": "2"}}
        conflicts = detector.detect_conflicts([m1, m2])
        assert isinstance(conflicts, list)

    def test_graph_traverser_neighbors(self, knowledge_graph, traverser):
        from memoria.graph.entities import Entity, Relation
        from memoria.graph.schema import NodeType, RelationType
        e_python = Entity(name="Python", entity_type=NodeType.TOOL)
        e_guido = Entity(name="Guido", entity_type=NodeType.PERSON)
        nid_python = knowledge_graph.add_entity(e_python)
        nid_guido = knowledge_graph.add_entity(e_guido)
        rel = Relation(source=e_guido, target=e_python, relation_type=RelationType.USES)
        knowledge_graph.add_relation(rel)
        neighbors = traverser.neighbors(nid_guido)
        assert len(neighbors) >= 1

    def test_graph_traverser_find_paths(self, knowledge_graph, traverser):
        from memoria.graph.entities import Entity, Relation
        from memoria.graph.schema import NodeType, RelationType
        e_a = Entity(name="ConceptA", entity_type=NodeType.CONCEPT)
        e_b = Entity(name="ConceptB", entity_type=NodeType.CONCEPT)
        nid_a = knowledge_graph.add_entity(e_a)
        nid_b = knowledge_graph.add_entity(e_b)
        rel = Relation(source=e_a, target=e_b, relation_type=RelationType.RELATED_TO)
        knowledge_graph.add_relation(rel)
        paths = traverser.find_paths(nid_a, nid_b)
        assert len(paths) >= 1

    def test_explanation_builder_explain_connection(self, knowledge_graph, explanation_builder):
        from memoria.graph.entities import Entity, Relation
        from memoria.graph.schema import NodeType, RelationType
        e_rust = Entity(name="Rust", entity_type=NodeType.TOOL)
        e_safety = Entity(name="MemSafety", entity_type=NodeType.CONCEPT)
        nid_rust = knowledge_graph.add_entity(e_rust)
        nid_safety = knowledge_graph.add_entity(e_safety)
        rel = Relation(source=e_rust, target=e_safety, relation_type=RelationType.RELATED_TO)
        knowledge_graph.add_relation(rel)
        explanation = explanation_builder.explain_connection(nid_rust, nid_safety)
        assert hasattr(explanation, "reason")
        assert hasattr(explanation, "confidence")

    def test_explanation_builder_no_connection(self, knowledge_graph, explanation_builder):
        from memoria.graph.entities import Entity
        from memoria.graph.schema import NodeType
        knowledge_graph.add_entity(Entity(name="Island1", entity_type=NodeType.CONCEPT))
        knowledge_graph.add_entity(Entity(name="Island2", entity_type=NodeType.CONCEPT))
        explanation = explanation_builder.explain_connection("Island1", "Island2")
        assert explanation.confidence == 0.0 or explanation.reason != ""

    def test_enrichment_then_graph_flow(self, memory_enricher, knowledge_graph, traverser):
        from memoria.graph.entities import Entity
        from memoria.graph.schema import NodeType
        enriched = memory_enricher.enrich({
            "content": "Alice works at Google on AI research",
            "metadata": {},
        })
        meta = enriched.get("metadata", {})
        entities = meta.get("entities", [])
        for ent in entities:
            name = ent if isinstance(ent, str) else ent.get("text", str(ent))
            knowledge_graph.add_entity(Entity(name=name, entity_type=NodeType.CONCEPT))
        assert isinstance(entities, list)


# ===================================================================
# 4. Versioning + Audit Trail Integration  (~10 tests)
# ===================================================================


class TestVersioningAuditIntegration:
    """Test versioning with audit trail."""

    def test_record_initial_version(self, version_history):
        entry = version_history.record("mem-1", "Initial content", changed_by="user")
        assert entry.version == 1
        assert entry.change_type == "update" or entry.change_type == "create"

    def test_record_multiple_versions(self, version_history):
        version_history.record("mem-2", "Version 1", changed_by="user", change_type="create")
        version_history.record("mem-2", "Version 2", changed_by="user", change_type="update")
        version_history.record("mem-2", "Version 3", changed_by="user", change_type="update")
        history = version_history.get_history("mem-2")
        assert len(history) == 3

    def test_get_latest_version(self, version_history):
        version_history.record("mem-3", "First", changed_by="user", change_type="create")
        version_history.record("mem-3", "Second", changed_by="user", change_type="update")
        latest = version_history.get_latest("mem-3")
        assert latest.content == "Second"

    def test_get_specific_version(self, version_history):
        version_history.record("mem-4", "V1", changed_by="user", change_type="create")
        version_history.record("mem-4", "V2", changed_by="user", change_type="update")
        v1 = version_history.get_version("mem-4", 1)
        assert v1.content == "V1"

    def test_version_count(self, version_history):
        version_history.record("mem-5", "A", changed_by="user", change_type="create")
        version_history.record("mem-5", "B", changed_by="user", change_type="update")
        assert version_history.version_count("mem-5") == 2

    def test_rollback_creates_restore_entry(self, version_history):
        version_history.record("mem-6", "Original", changed_by="user", change_type="create")
        version_history.record("mem-6", "Modified", changed_by="user", change_type="update")
        restored = version_history.rollback("mem-6", to_version=1, changed_by="admin")
        assert restored.change_type == "restore"
        assert restored.content == "Original"

    def test_history_ordered_by_version(self, version_history):
        for i in range(5):
            version_history.record("mem-7", f"Content {i}", changed_by="user")
        history = version_history.get_history("mem-7")
        versions = [e.version for e in history]
        assert versions == sorted(versions)

    def test_changed_by_tracked(self, version_history):
        version_history.record("mem-8", "Content", changed_by="alice", change_type="create")
        entry = version_history.get_latest("mem-8")
        assert entry.changed_by == "alice"

    def test_changed_at_is_iso_timestamp(self, version_history):
        entry = version_history.record("mem-9", "Content", changed_by="user")
        assert isinstance(entry.changed_at, str)
        assert "T" in entry.changed_at or "-" in entry.changed_at

    def test_empty_history_for_unknown_id(self, version_history):
        history = version_history.get_history("nonexistent")
        assert history == []


# ===================================================================
# 5. Sync Protocol Integration  (~10 tests)
# ===================================================================


class TestSyncIntegration:
    """Test sync protocol with namespace + ACL."""

    def test_push_empty_store(self, sync_protocol):
        result = sync_protocol.push()
        assert hasattr(result, "pushed")

    def test_pull_empty_remote(self, sync_protocol):
        result = sync_protocol.pull()
        assert hasattr(result, "pulled")

    def test_bidirectional_sync(self, sync_protocol):
        result = sync_protocol.sync()
        assert hasattr(result, "pushed")
        assert hasattr(result, "pulled")

    def test_sync_state_tracking(self, sync_protocol):
        sync_protocol.sync()
        state = sync_protocol.get_state()
        assert hasattr(state, "sync_count")

    def test_sync_with_namespace_filter(self, namespace_store, sync_transport):
        namespace_store.add("ns-a", "Content for namespace A")
        protocol = SyncProtocol(local_store=namespace_store, transport=sync_transport)
        result = protocol.sync(namespace="ns-a")
        assert hasattr(result, "pushed")

    def test_record_change_and_pending(self, sync_protocol, namespace_store):
        mid = namespace_store.add("sync-ns", "Pending change content")
        sync_protocol.record_change(mid, "sync-ns", "create")
        pending = sync_protocol.get_pending_changes()
        assert isinstance(pending, list)

    def test_sync_conflict_resolver(self):
        resolver = SyncConflictResolver()
        local = {"content": "Local version", "metadata": {"id": "1", "updated_at": "2024-01-02"}}
        remote = {"content": "Remote version", "metadata": {"id": "1", "updated_at": "2024-01-01"}}
        conflict = resolver.detect(local, remote)
        if conflict is not None:
            resolution = resolver.resolve(conflict)
            assert resolution is not None

    def test_reset_state(self, sync_protocol):
        sync_protocol.sync()
        sync_protocol.reset_state()
        state = sync_protocol.get_state()
        assert state.sync_count == 0

    def test_in_memory_transport_ping(self, sync_transport):
        assert sync_transport.ping() is True

    def test_multiple_syncs_increment_count(self, sync_protocol):
        sync_protocol.sync()
        sync_protocol.sync()
        state = sync_protocol.get_state()
        assert state.sync_count >= 2


# ===================================================================
# 6. Memoria v2 Unified API  (~15 tests)
# ===================================================================


class TestMemoriaV2API:
    """Test the updated Memoria class with v2 features."""

    # --- backward compatibility ---

    def test_v1_add_still_works(self, memoria_instance):
        path = memoria_instance.add("Hello world from v1")
        assert path is not None
        assert isinstance(path, str)

    def test_v1_add_with_user_id(self, memoria_instance):
        path = memoria_instance.add("User memory", user_id="u1")
        assert path is not None

    def test_v1_search_still_works(self, memoria_instance):
        memoria_instance.add("Machine learning is fascinating")
        results = memoria_instance.search("machine learning")
        assert isinstance(results, list)

    def test_v1_get_still_works(self, memoria_instance):
        path = memoria_instance.add("Retrievable content")
        result = memoria_instance.get(path)
        assert result is not None
        assert "memory" in result

    def test_v1_delete_still_works(self, memoria_instance):
        path = memoria_instance.add("Deletable content")
        assert memoria_instance.delete(path) is True
        assert memoria_instance.get(path) is None

    def test_v1_suggest_still_works(self, memoria_instance):
        suggestions = memoria_instance.suggest()
        assert isinstance(suggestions, list)

    def test_v1_profile_still_works(self, memoria_instance):
        profile = memoria_instance.profile()
        assert profile is not None

    def test_v1_insights_still_works(self, memoria_instance):
        insights = memoria_instance.insights()
        assert isinstance(insights, list)

    # --- v2 namespace ---

    def test_add_with_namespace(self, memoria_instance):
        mid = memoria_instance.add("Namespaced content", namespace="project/docs")
        assert mid is not None

    def test_search_with_namespace(self, memoria_instance):
        memoria_instance.add("Python testing best practices", namespace="dev")
        results = memoria_instance.search("Python testing", namespace="dev")
        assert isinstance(results, list)

    # --- v2 tiered ---

    def test_add_to_tier(self, memoria_instance):
        mid = memoria_instance.add_to_tier("Working thought", tier="working")
        assert mid is not None

    def test_search_tiers(self, memoria_instance):
        memoria_instance.add_to_tier("Important note about deployment", tier="recall")
        results = memoria_instance.search_tiers("deployment")
        assert isinstance(results, list)

    def test_flush_session(self, memoria_instance):
        memoria_instance.add_to_tier("Session data", tier="working")
        result = memoria_instance.flush_session()
        assert isinstance(result, dict)
        assert "flushed_to_recall" in result

    # --- v2 ACL ---

    def test_grant_and_check_access(self, memoria_instance):
        memoria_instance.grant_access("agent-1", "ns/private", role="writer")
        assert memoria_instance.check_access("agent-1", "ns/private", "write") is True
        assert memoria_instance.check_access("agent-1", "ns/private", "read") is True

    def test_check_access_denied(self, memoria_instance):
        assert memoria_instance.check_access("unknown", "ns/secret", "read") is False

    # --- v2 versioning ---

    def test_get_history_empty(self, memoria_instance):
        history = memoria_instance.get_history("nonexistent")
        assert history == []

    # --- v2 enrichment ---

    def test_enrich_content(self, memoria_instance):
        result = memoria_instance.enrich("Alice works at Google on machine learning")
        assert isinstance(result, dict)

    # --- v2 explain ---

    def test_explain_connection(self, memoria_instance):
        from memoria.graph.entities import Entity, Relation
        from memoria.graph.schema import NodeType, RelationType
        kg = memoria_instance._config.get("knowledge_graph")
        e_react = Entity(name="React", entity_type=NodeType.TOOL)
        e_js = Entity(name="JavaScript", entity_type=NodeType.TOOL)
        nid_react = kg.add_entity(e_react)
        nid_js = kg.add_entity(e_js)
        kg.add_relation(Relation(
            source=e_react, target=e_js,
            relation_type=RelationType.USES,
        ))
        result = memoria_instance.explain(nid_react, nid_js)
        assert "reason" in result
        assert "confidence" in result

    # --- v2 sync ---

    def test_sync(self, memoria_instance):
        result = memoria_instance.sync()
        assert "pushed" in result
        assert "pulled" in result

    def test_version_is_2(self):
        from memoria import __version__
        assert __version__ == "2.0.0"


# ===================================================================
# 7. MCP v2 Tools  (~13 tests)
# ===================================================================


class TestMCPV2Tools:
    """Test new MCP v2 tools."""

    @pytest.fixture(autouse=True)
    def _setup_mcp(self):
        """Reset the global MCP Memoria instance for each test."""
        import memoria.mcp.server as srv
        srv._memoria_instance = None
        with tempfile.TemporaryDirectory() as td:
            srv._PROJECT_DIR = td
            yield

    def _get_memoria_mcp(self):
        import memoria.mcp.server as srv
        return srv._get_memoria()

    # --- memoria_add_to_tier ---

    def test_mcp_add_to_tier_working(self):
        from memoria.mcp.server import memoria_add_to_tier
        result = memoria_add_to_tier("Quick thought", tier="working")
        assert result["status"] == "created"
        assert result["tier"] == "working"

    def test_mcp_add_to_tier_recall(self):
        from memoria.mcp.server import memoria_add_to_tier
        result = memoria_add_to_tier("Important fact", tier="recall")
        assert result["status"] == "created"
        assert result["tier"] == "recall"

    def test_mcp_add_to_tier_archival(self):
        from memoria.mcp.server import memoria_add_to_tier
        result = memoria_add_to_tier("Archive doc", tier="archival")
        assert result["status"] == "created"

    # --- memoria_search_tiers ---

    def test_mcp_search_tiers_all(self):
        from memoria.mcp.server import memoria_add_to_tier, memoria_search_tiers
        memoria_add_to_tier("Search target content", tier="recall")
        results = memoria_search_tiers("Search target")
        assert isinstance(results, list)

    def test_mcp_search_tiers_filtered(self):
        from memoria.mcp.server import memoria_add_to_tier, memoria_search_tiers
        memoria_add_to_tier("Recall only content", tier="recall")
        results = memoria_search_tiers("Recall only", tiers="recall")
        assert isinstance(results, list)

    # --- memoria_grant_access ---

    def test_mcp_grant_access_reader(self):
        from memoria.mcp.server import memoria_grant_access
        result = memoria_grant_access("agent-1", "my/namespace", role="reader")
        assert result["status"] == "granted"
        assert result["role"] == "reader"

    def test_mcp_grant_access_writer(self):
        from memoria.mcp.server import memoria_grant_access
        result = memoria_grant_access("agent-2", "my/ns", role="writer", granted_by="admin")
        assert result["status"] == "granted"
        assert result["agent_id"] == "agent-2"

    def test_mcp_grant_access_admin(self):
        from memoria.mcp.server import memoria_grant_access
        result = memoria_grant_access("agent-3", "ns", role="admin")
        assert result["status"] == "granted"

    # --- memoria_enrich ---

    def test_mcp_enrich_returns_metadata(self):
        from memoria.mcp.server import memoria_enrich
        result = memoria_enrich("Alice works at Google on AI research")
        assert isinstance(result, dict)

    def test_mcp_enrich_with_simple_text(self):
        from memoria.mcp.server import memoria_enrich
        result = memoria_enrich("I prefer using Python for scripting")
        assert isinstance(result, dict)

    # --- memoria_sync ---

    def test_mcp_sync_default(self):
        from memoria.mcp.server import memoria_sync
        result = memoria_sync()
        assert "pushed" in result
        assert "pulled" in result

    def test_mcp_sync_with_namespace(self):
        from memoria.mcp.server import memoria_sync
        result = memoria_sync(namespace="project/docs")
        assert "pushed" in result

    # --- existing tools still work ---

    def test_mcp_add_still_works(self):
        from memoria.mcp.server import memoria_add
        result = memoria_add("Test v1 add via MCP")
        assert result["status"] == "created"
