"""Comprehensive tests for the MEMORIA namespace module."""

from __future__ import annotations

import pytest

from memoria.namespace.hierarchy import MemoryNamespace, NamespaceLevel
from memoria.namespace.store import SharedMemoryStore
from memoria.namespace.resolver import (
    find_shared_ancestor,
    resolve_namespace,
    scope_intersection,
    walk_ancestors,
)
from memoria.namespace.scopes import (
    ScopeFilter,
    normalize_path,
    validate_namespace_path,
    validate_part,
)


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture()
def store() -> SharedMemoryStore:
    return SharedMemoryStore()


@pytest.fixture()
def populated_store(store: SharedMemoryStore) -> SharedMemoryStore:
    """Store pre-loaded with memories in various namespaces."""
    store.add("acme", "Global policy doc", metadata={"kind": "policy"})
    store.add("acme", "Acme onboarding guide", user_id="u1")
    store.add("acme/frontend", "React style guide", agent_id="a1")
    store.add("acme/frontend", "CSS conventions", user_id="u1")
    store.add("acme/backend", "API design doc")
    store.add("acme/frontend/agent-1", "Agent-1 session note", user_id="u2", agent_id="a1")
    store.add("acme/frontend/agent-1/sess-abc", "Session transcript")
    return store


# ===================================================================
# 1. NamespaceLevel
# ===================================================================


class TestNamespaceLevel:
    def test_enum_values(self) -> None:
        assert NamespaceLevel.GLOBAL == 0
        assert NamespaceLevel.ORG == 1
        assert NamespaceLevel.TEAM == 2
        assert NamespaceLevel.AGENT == 3
        assert NamespaceLevel.SESSION == 4

    def test_ordering(self) -> None:
        assert NamespaceLevel.GLOBAL < NamespaceLevel.ORG
        assert NamespaceLevel.ORG < NamespaceLevel.TEAM
        assert NamespaceLevel.TEAM < NamespaceLevel.AGENT
        assert NamespaceLevel.AGENT < NamespaceLevel.SESSION

    def test_all_levels_count(self) -> None:
        assert len(NamespaceLevel) == 5

    def test_level_is_int(self) -> None:
        assert isinstance(NamespaceLevel.GLOBAL, int)


# ===================================================================
# 2. MemoryNamespace
# ===================================================================


class TestMemoryNamespace:
    # -- from_path ---------------------------------------------------------

    def test_from_path_global_empty(self) -> None:
        ns = MemoryNamespace.from_path("")
        assert ns.level == NamespaceLevel.GLOBAL
        assert ns.path == ""
        assert ns.parts == []

    def test_from_path_global_keyword(self) -> None:
        ns = MemoryNamespace.from_path("global")
        assert ns.level == NamespaceLevel.GLOBAL
        assert ns.path == ""

    def test_from_path_org(self) -> None:
        ns = MemoryNamespace.from_path("acme-corp")
        assert ns.level == NamespaceLevel.ORG
        assert ns.path == "acme-corp"
        assert ns.parts == ["acme-corp"]

    def test_from_path_team(self) -> None:
        ns = MemoryNamespace.from_path("acme/frontend")
        assert ns.level == NamespaceLevel.TEAM
        assert ns.path == "acme/frontend"
        assert ns.parts == ["acme", "frontend"]

    def test_from_path_agent(self) -> None:
        ns = MemoryNamespace.from_path("acme/frontend/agent-1")
        assert ns.level == NamespaceLevel.AGENT
        assert ns.path == "acme/frontend/agent-1"
        assert ns.parts == ["acme", "frontend", "agent-1"]

    def test_from_path_session(self) -> None:
        ns = MemoryNamespace.from_path("acme/frontend/agent-1/sess-xyz")
        assert ns.level == NamespaceLevel.SESSION
        assert ns.parts == ["acme", "frontend", "agent-1", "sess-xyz"]

    def test_from_path_strips_slashes(self) -> None:
        ns = MemoryNamespace.from_path("/acme/frontend/")
        assert ns.path == "acme/frontend"

    def test_from_path_lowercases(self) -> None:
        ns = MemoryNamespace.from_path("ACME/FrontEnd")
        assert ns.path == "acme/frontend"

    def test_from_path_strips_global_prefix(self) -> None:
        ns = MemoryNamespace.from_path("global/acme/frontend")
        assert ns.path == "acme/frontend"
        assert ns.level == NamespaceLevel.TEAM

    def test_from_path_invalid_chars(self) -> None:
        with pytest.raises(ValueError, match="Invalid namespace part"):
            MemoryNamespace.from_path("acme/front end")

    def test_from_path_invalid_special_chars(self) -> None:
        with pytest.raises(ValueError, match="Invalid namespace part"):
            MemoryNamespace.from_path("acme/@team")

    # -- from_parts --------------------------------------------------------

    def test_from_parts_global(self) -> None:
        ns = MemoryNamespace.from_parts()
        assert ns.level == NamespaceLevel.GLOBAL

    def test_from_parts_org_only(self) -> None:
        ns = MemoryNamespace.from_parts(org="acme")
        assert ns.level == NamespaceLevel.ORG
        assert ns.path == "acme"

    def test_from_parts_org_team(self) -> None:
        ns = MemoryNamespace.from_parts(org="acme", team="frontend")
        assert ns.level == NamespaceLevel.TEAM
        assert ns.path == "acme/frontend"

    def test_from_parts_full(self) -> None:
        ns = MemoryNamespace.from_parts(org="acme", team="fe", agent="a1", session="s1")
        assert ns.level == NamespaceLevel.SESSION
        assert ns.parts == ["acme", "fe", "a1", "s1"]

    def test_from_parts_stops_at_none(self) -> None:
        ns = MemoryNamespace.from_parts(org="acme", team=None, agent="a1")
        assert ns.level == NamespaceLevel.ORG
        assert ns.parts == ["acme"]

    # -- parent / ancestors ------------------------------------------------

    def test_parent_of_global_is_none(self) -> None:
        ns = MemoryNamespace.from_path("")
        assert ns.parent() is None

    def test_parent_of_org_is_global(self) -> None:
        ns = MemoryNamespace.from_path("acme")
        parent = ns.parent()
        assert parent is not None
        assert parent.level == NamespaceLevel.GLOBAL

    def test_parent_of_team(self) -> None:
        ns = MemoryNamespace.from_path("acme/frontend")
        parent = ns.parent()
        assert parent is not None
        assert parent.path == "acme"

    def test_ancestors_of_session(self) -> None:
        ns = MemoryNamespace.from_path("acme/fe/agent-1/sess-1")
        ancs = ns.ancestors()
        paths = [a.path for a in ancs]
        assert paths == ["acme/fe/agent-1", "acme/fe", "acme", ""]

    def test_ancestors_of_global(self) -> None:
        ns = MemoryNamespace.from_path("global")
        assert ns.ancestors() == []

    # -- contains ----------------------------------------------------------

    def test_global_contains_everything(self) -> None:
        g = MemoryNamespace.from_path("")
        child = MemoryNamespace.from_path("acme/fe/a1")
        assert g.contains(child)

    def test_org_contains_team(self) -> None:
        org = MemoryNamespace.from_path("acme")
        team = MemoryNamespace.from_path("acme/frontend")
        assert org.contains(team)

    def test_team_does_not_contain_sibling(self) -> None:
        t1 = MemoryNamespace.from_path("acme/frontend")
        t2 = MemoryNamespace.from_path("acme/backend")
        assert not t1.contains(t2)

    def test_contains_self(self) -> None:
        ns = MemoryNamespace.from_path("acme/frontend")
        assert ns.contains(ns)

    # -- children ----------------------------------------------------------

    def test_children(self, populated_store: SharedMemoryStore) -> None:
        org = MemoryNamespace.from_path("acme")
        kids = org.children(populated_store)
        kid_paths = sorted(k.path for k in kids)
        assert "acme/frontend" in kid_paths
        assert "acme/backend" in kid_paths

    # -- str / equality ----------------------------------------------------

    def test_str_global(self) -> None:
        assert str(MemoryNamespace.from_path("")) == "global"

    def test_str_org(self) -> None:
        assert str(MemoryNamespace.from_path("acme")) == "acme"

    def test_equality(self) -> None:
        a = MemoryNamespace.from_path("acme/frontend")
        b = MemoryNamespace.from_path("ACME/Frontend")
        assert a == b

    def test_hash_equal(self) -> None:
        a = MemoryNamespace.from_path("acme/frontend")
        b = MemoryNamespace.from_path("acme/frontend")
        assert hash(a) == hash(b)


# ===================================================================
# 3. SharedMemoryStore
# ===================================================================


class TestSharedMemoryStore:
    def test_add_returns_uuid(self, store: SharedMemoryStore) -> None:
        mid = store.add("org", "hello world")
        assert isinstance(mid, str)
        assert len(mid) == 36  # UUID format

    def test_get_existing(self, store: SharedMemoryStore) -> None:
        mid = store.add("org", "test content", metadata={"key": "val"})
        mem = store.get(mid)
        assert mem is not None
        assert mem["content"] == "test content"
        assert mem["namespace"] == "org"
        assert mem["metadata"] == {"key": "val"}

    def test_get_missing(self, store: SharedMemoryStore) -> None:
        assert store.get("nonexistent-id") is None

    def test_delete_existing(self, store: SharedMemoryStore) -> None:
        mid = store.add("org", "to delete")
        assert store.delete(mid) is True
        assert store.get(mid) is None

    def test_delete_missing(self, store: SharedMemoryStore) -> None:
        assert store.delete("no-such-id") is False

    def test_add_with_user_and_agent(self, store: SharedMemoryStore) -> None:
        mid = store.add("ns", "content", user_id="u1", agent_id="a1")
        mem = store.get(mid)
        assert mem is not None
        assert mem["user_id"] == "u1"
        assert mem["agent_id"] == "a1"

    def test_timestamps_are_iso(self, store: SharedMemoryStore) -> None:
        mid = store.add("ns", "content")
        mem = store.get(mid)
        assert mem is not None
        assert "T" in mem["created_at"]
        assert "T" in mem["updated_at"]

    # -- search ------------------------------------------------------------

    def test_search_basic(self, populated_store: SharedMemoryStore) -> None:
        results = populated_store.search("style")
        assert len(results) >= 1
        assert any("style" in r["content"].lower() for r in results)

    def test_search_with_namespace(self, populated_store: SharedMemoryStore) -> None:
        results = populated_store.search("guide", namespace="acme", include_ancestors=False)
        assert len(results) >= 1
        assert all(r["namespace"] == "acme" for r in results)

    def test_search_with_ancestors(self, populated_store: SharedMemoryStore) -> None:
        results = populated_store.search("guide", namespace="acme/frontend", include_ancestors=True)
        assert len(results) >= 1
        # Should include results from "acme" ancestor
        namespaces = {r["namespace"] for r in results}
        assert "acme" in namespaces

    def test_search_with_user_id(self, populated_store: SharedMemoryStore) -> None:
        results = populated_store.search("guide", user_id="u1")
        assert len(results) >= 1
        assert all(r["user_id"] == "u1" for r in results)

    def test_search_limit(self, populated_store: SharedMemoryStore) -> None:
        results = populated_store.search("a", limit=2)
        assert len(results) <= 2

    def test_search_no_results(self, store: SharedMemoryStore) -> None:
        results = store.search("nonexistent-query-xyz")
        assert results == []

    # -- list_by_namespace -------------------------------------------------

    def test_list_by_namespace_exact(self, populated_store: SharedMemoryStore) -> None:
        results = populated_store.list_by_namespace("acme/frontend")
        assert len(results) == 2
        assert all(r["namespace"] == "acme/frontend" for r in results)

    def test_list_by_namespace_recursive(self, populated_store: SharedMemoryStore) -> None:
        results = populated_store.list_by_namespace("acme/frontend", recursive=True)
        assert len(results) >= 3  # frontend + agent-1 + session
        namespaces = {r["namespace"] for r in results}
        assert "acme/frontend" in namespaces
        assert "acme/frontend/agent-1" in namespaces

    # -- count -------------------------------------------------------------

    def test_count_all(self, populated_store: SharedMemoryStore) -> None:
        assert populated_store.count() == 7

    def test_count_namespace(self, populated_store: SharedMemoryStore) -> None:
        assert populated_store.count("acme/frontend") >= 2

    def test_count_empty_store(self, store: SharedMemoryStore) -> None:
        assert store.count() == 0

    # -- namespaces --------------------------------------------------------

    def test_namespaces(self, populated_store: SharedMemoryStore) -> None:
        ns_list = populated_store.namespaces()
        assert "acme" in ns_list
        assert "acme/frontend" in ns_list
        assert "acme/backend" in ns_list

    def test_namespaces_empty(self, store: SharedMemoryStore) -> None:
        assert store.namespaces() == []

    # -- move --------------------------------------------------------------

    def test_move_success(self, store: SharedMemoryStore) -> None:
        mid = store.add("old-ns", "moveable")
        assert store.move(mid, "new-ns") is True
        mem = store.get(mid)
        assert mem is not None
        assert mem["namespace"] == "new-ns"

    def test_move_nonexistent(self, store: SharedMemoryStore) -> None:
        assert store.move("no-such-id", "ns") is False

    # -- metadata parsing --------------------------------------------------

    def test_metadata_none_returns_empty_dict(self, store: SharedMemoryStore) -> None:
        mid = store.add("ns", "content")
        mem = store.get(mid)
        assert mem is not None
        assert mem["metadata"] == {}

    def test_metadata_round_trip(self, store: SharedMemoryStore) -> None:
        meta = {"tags": ["python", "ai"], "priority": 5}
        mid = store.add("ns", "content", metadata=meta)
        mem = store.get(mid)
        assert mem is not None
        assert mem["metadata"] == meta


# ===================================================================
# 4. Namespace Resolver
# ===================================================================


class TestNamespaceResolver:
    # -- resolve_namespace -------------------------------------------------

    def test_resolve_child(self) -> None:
        current = MemoryNamespace.from_path("acme/frontend")
        result = resolve_namespace(current, "agent-1")
        assert result.path == "acme/frontend/agent-1"

    def test_resolve_dot_child(self) -> None:
        current = MemoryNamespace.from_path("acme/frontend")
        result = resolve_namespace(current, "./agent-1")
        assert result.path == "acme/frontend/agent-1"

    def test_resolve_parent(self) -> None:
        current = MemoryNamespace.from_path("acme/frontend/agent-1")
        result = resolve_namespace(current, "..")
        assert result.path == "acme/frontend"

    def test_resolve_parent_sibling(self) -> None:
        current = MemoryNamespace.from_path("acme/frontend/agent-1")
        result = resolve_namespace(current, "../agent-2")
        assert result.path == "acme/frontend/agent-2"

    def test_resolve_double_parent(self) -> None:
        current = MemoryNamespace.from_path("acme/frontend/agent-1")
        result = resolve_namespace(current, "../..")
        assert result.path == "acme"

    def test_resolve_parent_beyond_global(self) -> None:
        current = MemoryNamespace.from_path("acme")
        result = resolve_namespace(current, "../..")
        assert result.level == NamespaceLevel.GLOBAL

    def test_resolve_empty(self) -> None:
        current = MemoryNamespace.from_path("acme/frontend")
        result = resolve_namespace(current, "")
        assert result.path == "acme/frontend"

    def test_resolve_dot_only(self) -> None:
        current = MemoryNamespace.from_path("acme/frontend")
        result = resolve_namespace(current, "./")
        assert result.path == "acme/frontend"

    # -- walk_ancestors ----------------------------------------------------

    def test_walk_ancestors_includes_self(self) -> None:
        ns = MemoryNamespace.from_path("acme/fe/a1")
        chain = walk_ancestors(ns)
        assert chain[0] == ns
        assert chain[-1].level == NamespaceLevel.GLOBAL

    def test_walk_ancestors_length(self) -> None:
        ns = MemoryNamespace.from_path("acme/fe/a1")
        chain = walk_ancestors(ns)
        assert len(chain) == 4  # self + fe + acme + global

    def test_walk_ancestors_global(self) -> None:
        ns = MemoryNamespace.from_path("global")
        chain = walk_ancestors(ns)
        assert len(chain) == 1
        assert chain[0].level == NamespaceLevel.GLOBAL

    # -- find_shared_ancestor ----------------------------------------------

    def test_shared_ancestor_siblings(self) -> None:
        a = MemoryNamespace.from_path("acme/frontend/a1")
        b = MemoryNamespace.from_path("acme/frontend/a2")
        shared = find_shared_ancestor(a, b)
        assert shared is not None
        assert shared.path == "acme/frontend"

    def test_shared_ancestor_different_orgs(self) -> None:
        a = MemoryNamespace.from_path("acme/frontend")
        b = MemoryNamespace.from_path("bigcorp/backend")
        shared = find_shared_ancestor(a, b)
        assert shared is not None
        assert shared.level == NamespaceLevel.GLOBAL

    def test_shared_ancestor_parent_child(self) -> None:
        a = MemoryNamespace.from_path("acme")
        b = MemoryNamespace.from_path("acme/frontend")
        shared = find_shared_ancestor(a, b)
        assert shared is not None
        assert shared.path == "acme"

    # -- scope_intersection ------------------------------------------------

    def test_scope_intersection_parent_child(self) -> None:
        parent = MemoryNamespace.from_path("acme")
        child = MemoryNamespace.from_path("acme/frontend")
        result = scope_intersection(parent, child)
        assert result is not None
        assert result.path == "acme/frontend"

    def test_scope_intersection_siblings(self) -> None:
        a = MemoryNamespace.from_path("acme/frontend")
        b = MemoryNamespace.from_path("acme/backend")
        result = scope_intersection(a, b)
        assert result is not None
        assert result.path == "acme"

    def test_scope_intersection_same(self) -> None:
        ns = MemoryNamespace.from_path("acme/frontend")
        result = scope_intersection(ns, ns)
        assert result is not None
        assert result.path == "acme/frontend"


# ===================================================================
# 5. Scope Validation
# ===================================================================


class TestScopeValidation:
    # -- validate_part -----------------------------------------------------

    def test_valid_part_alpha(self) -> None:
        assert validate_part("frontend") is True

    def test_valid_part_with_hyphen(self) -> None:
        assert validate_part("my-team") is True

    def test_valid_part_with_underscore(self) -> None:
        assert validate_part("my_team") is True

    def test_valid_part_with_numbers(self) -> None:
        assert validate_part("agent001") is True

    def test_invalid_part_space(self) -> None:
        assert validate_part("my team") is False

    def test_invalid_part_special(self) -> None:
        assert validate_part("@team") is False

    def test_invalid_part_empty(self) -> None:
        assert validate_part("") is False

    # -- validate_namespace_path -------------------------------------------

    def test_valid_path_empty(self) -> None:
        assert validate_namespace_path("") is True

    def test_valid_path_global(self) -> None:
        assert validate_namespace_path("global") is True

    def test_valid_path_org(self) -> None:
        assert validate_namespace_path("acme-corp") is True

    def test_valid_path_full(self) -> None:
        assert validate_namespace_path("acme/frontend/agent-1/sess-abc") is True

    def test_invalid_path_spaces(self) -> None:
        assert validate_namespace_path("acme/my team") is False

    # -- normalize_path ----------------------------------------------------

    def test_normalize_strips_slashes(self) -> None:
        assert normalize_path("/acme/frontend/") == "acme/frontend"

    def test_normalize_lowercases(self) -> None:
        assert normalize_path("ACME/FrontEnd") == "acme/frontend"

    def test_normalize_global(self) -> None:
        assert normalize_path("global") == ""

    def test_normalize_empty(self) -> None:
        assert normalize_path("") == ""

    def test_normalize_strips_global_prefix(self) -> None:
        assert normalize_path("global/acme/frontend") == "acme/frontend"

    # -- ScopeFilter -------------------------------------------------------

    def test_filter_exact_match(self) -> None:
        sf = ScopeFilter(namespaces=["acme/frontend"])
        assert sf.matches("acme/frontend") is True

    def test_filter_no_match(self) -> None:
        sf = ScopeFilter(namespaces=["acme/frontend"], include_ancestors=False)
        assert sf.matches("acme/backend") is False

    def test_filter_ancestor_match(self) -> None:
        sf = ScopeFilter(namespaces=["acme/frontend"], include_ancestors=True)
        assert sf.matches("acme") is True

    def test_filter_descendant_match(self) -> None:
        sf = ScopeFilter(
            namespaces=["acme/frontend"],
            include_ancestors=False,
            include_descendants=True,
        )
        assert sf.matches("acme/frontend/agent-1") is True

    def test_filter_descendant_no_match_without_flag(self) -> None:
        sf = ScopeFilter(
            namespaces=["acme/frontend"],
            include_ancestors=False,
            include_descendants=False,
        )
        assert sf.matches("acme/frontend/agent-1") is False

    def test_filter_global_ancestor(self) -> None:
        sf = ScopeFilter(namespaces=["acme/frontend"], include_ancestors=True)
        assert sf.matches("") is True

    def test_filter_empty_namespaces(self) -> None:
        sf = ScopeFilter(namespaces=[])
        assert sf.matches("acme") is False
