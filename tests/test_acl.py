"""Tests for the access-control layer (pkg/memoria/src/memoria/acl)."""

from __future__ import annotations

import pytest

from memoria.acl import (
    AccessDenied,
    AccessPolicy,
    GrantStore,
    Operation,
    PolicyEngine,
    Role,
    RoleAssignment,
    checked_read,
    checked_write,
    enforce,
    role_can_admin,
    role_can_read,
    role_can_write,
    role_inherits,
)

# ═════════════════════════════════════════════════════════════════
# Fixtures
# ═════════════════════════════════════════════════════════════════


@pytest.fixture()
def store() -> GrantStore:
    """Fresh in-memory grant store."""
    return GrantStore()


@pytest.fixture()
def engine(store: GrantStore) -> PolicyEngine:
    """Policy engine backed by an in-memory grant store."""
    return PolicyEngine(grant_store=store)


@pytest.fixture()
def populated(store: GrantStore, engine: PolicyEngine) -> tuple[GrantStore, PolicyEngine]:
    """Store pre-loaded with a realistic grant set.

    Grants::

        alice  → OWNER  on "org/acme"
        bob    → WRITER on "org/acme/team-x"
        carol  → READER on "org/acme"
        *      → READER on "public"
    """
    store.grant("alice", "org/acme", Role.OWNER, "system")
    store.grant("bob", "org/acme/team-x", Role.WRITER, "alice")
    store.grant("carol", "org/acme", Role.READER, "alice")
    store.grant("*", "public", Role.READER, "system")
    return store, engine


# ═════════════════════════════════════════════════════════════════
# TestRoles
# ═════════════════════════════════════════════════════════════════


class TestRoles:
    """Role enum values, ordering, permission predicates, inheritance."""

    # ── enum values ──────────────────────────────────────────────

    def test_role_values(self) -> None:
        assert Role.NONE == 0
        assert Role.READER == 1
        assert Role.WRITER == 2
        assert Role.ADMIN == 3
        assert Role.OWNER == 4

    def test_role_ordering(self) -> None:
        assert Role.NONE < Role.READER < Role.WRITER < Role.ADMIN < Role.OWNER

    def test_role_names(self) -> None:
        assert Role.OWNER.name == "OWNER"
        assert Role["WRITER"] is Role.WRITER

    # ── can_read ─────────────────────────────────────────────────

    def test_can_read_reader(self) -> None:
        assert role_can_read(Role.READER) is True

    def test_can_read_writer(self) -> None:
        assert role_can_read(Role.WRITER) is True

    def test_can_read_admin(self) -> None:
        assert role_can_read(Role.ADMIN) is True

    def test_can_read_owner(self) -> None:
        assert role_can_read(Role.OWNER) is True

    def test_can_read_none(self) -> None:
        assert role_can_read(Role.NONE) is False

    # ── can_write ────────────────────────────────────────────────

    def test_can_write_writer(self) -> None:
        assert role_can_write(Role.WRITER) is True

    def test_can_write_admin(self) -> None:
        assert role_can_write(Role.ADMIN) is True

    def test_can_write_reader(self) -> None:
        assert role_can_write(Role.READER) is False

    def test_can_write_none(self) -> None:
        assert role_can_write(Role.NONE) is False

    # ── can_admin ────────────────────────────────────────────────

    def test_can_admin_admin(self) -> None:
        assert role_can_admin(Role.ADMIN) is True

    def test_can_admin_owner(self) -> None:
        assert role_can_admin(Role.OWNER) is True

    def test_can_admin_writer(self) -> None:
        assert role_can_admin(Role.WRITER) is False

    # ── role_inherits ────────────────────────────────────────────

    def test_inherits_writer(self) -> None:
        assert role_inherits(Role.WRITER) == Role.WRITER

    def test_inherits_owner(self) -> None:
        assert role_inherits(Role.OWNER) == Role.OWNER

    def test_inherits_none(self) -> None:
        assert role_inherits(Role.NONE) == Role.NONE

    # ── RoleAssignment ───────────────────────────────────────────

    def test_role_assignment_is_frozen(self) -> None:
        ra = RoleAssignment("a1", "ns", Role.READER, "sys", "2024-01-01T00:00:00+00:00")
        with pytest.raises(AttributeError):
            ra.role = Role.WRITER  # type: ignore[misc]

    def test_role_assignment_fields(self) -> None:
        ra = RoleAssignment("a1", "org/x", Role.ADMIN, "root", "2024-06-15T12:00:00+00:00")
        assert ra.agent_id == "a1"
        assert ra.namespace == "org/x"
        assert ra.role is Role.ADMIN
        assert ra.granted_by == "root"


# ═════════════════════════════════════════════════════════════════
# TestGrantStore
# ═════════════════════════════════════════════════════════════════


class TestGrantStore:
    """SQLite grant store CRUD operations."""

    def test_grant_returns_id(self, store: GrantStore) -> None:
        gid = store.grant("agent-1", "org/acme", Role.WRITER, "admin")
        assert isinstance(gid, str) and len(gid) > 0

    def test_get_role_after_grant(self, store: GrantStore) -> None:
        store.grant("agent-1", "org/acme", Role.WRITER, "admin")
        assert store.get_role("agent-1", "org/acme") is Role.WRITER

    def test_get_role_missing(self, store: GrantStore) -> None:
        assert store.get_role("ghost", "org/acme") is None

    def test_upsert_updates_role(self, store: GrantStore) -> None:
        store.grant("agent-1", "org/acme", Role.READER, "admin")
        store.grant("agent-1", "org/acme", Role.ADMIN, "admin")
        assert store.get_role("agent-1", "org/acme") is Role.ADMIN

    def test_revoke_existing(self, store: GrantStore) -> None:
        store.grant("agent-1", "org/acme", Role.WRITER, "admin")
        assert store.revoke("agent-1", "org/acme") is True
        assert store.get_role("agent-1", "org/acme") is None

    def test_revoke_missing(self, store: GrantStore) -> None:
        assert store.revoke("ghost", "org/acme") is False

    def test_revoke_all(self, store: GrantStore) -> None:
        store.grant("a1", "org/acme", Role.READER, "sys")
        store.grant("a2", "org/acme", Role.WRITER, "sys")
        store.grant("a3", "org/other", Role.READER, "sys")
        count = store.revoke_all("org/acme")
        assert count == 2
        assert store.get_role("a1", "org/acme") is None
        assert store.get_role("a3", "org/other") is Role.READER

    def test_get_grants_for_agent(self, store: GrantStore) -> None:
        store.grant("a1", "org/acme", Role.WRITER, "sys")
        store.grant("a1", "org/beta", Role.READER, "sys")
        grants = store.get_grants_for_agent("a1")
        assert len(grants) == 2
        assert all(isinstance(g, RoleAssignment) for g in grants)
        namespaces = {g.namespace for g in grants}
        assert namespaces == {"org/acme", "org/beta"}

    def test_get_grants_for_namespace(self, store: GrantStore) -> None:
        store.grant("a1", "org/acme", Role.WRITER, "sys")
        store.grant("a2", "org/acme", Role.READER, "sys")
        grants = store.get_grants_for_namespace("org/acme")
        assert len(grants) == 2
        agents = {g.agent_id for g in grants}
        assert agents == {"a1", "a2"}

    def test_has_any_grant_true(self, store: GrantStore) -> None:
        store.grant("a1", "org/acme", Role.READER, "sys")
        assert store.has_any_grant("a1") is True

    def test_has_any_grant_false(self, store: GrantStore) -> None:
        assert store.has_any_grant("ghost") is False

    def test_grant_timestamps_are_iso(self, store: GrantStore) -> None:
        store.grant("a1", "org/acme", Role.READER, "sys")
        grants = store.get_grants_for_agent("a1")
        assert "T" in grants[0].granted_at  # ISO-8601 contains 'T'


# ═════════════════════════════════════════════════════════════════
# TestPolicyEngine
# ═════════════════════════════════════════════════════════════════


class TestPolicyEngine:
    """Policy evaluation with direct grants, inheritance, and wildcards."""

    # ── direct grants ────────────────────────────────────────────

    def test_direct_read(self, populated: tuple) -> None:
        _, engine = populated
        assert engine.can_read("carol", "org/acme") is True

    def test_direct_write(self, populated: tuple) -> None:
        _, engine = populated
        assert engine.can_write("bob", "org/acme/team-x") is True

    def test_direct_admin(self, populated: tuple) -> None:
        _, engine = populated
        assert engine.can_admin("alice", "org/acme") is True

    def test_no_grant_yields_none(self, engine: PolicyEngine) -> None:
        assert engine.effective_role("nobody", "org/acme") is Role.NONE

    # ── inheritance ──────────────────────────────────────────────

    def test_inherit_owner_to_child(self, populated: tuple) -> None:
        _, engine = populated
        # alice is OWNER on org/acme → inherits to org/acme/team-x
        assert engine.effective_role("alice", "org/acme/team-x") is Role.OWNER

    def test_inherit_reader_to_deep_child(self, populated: tuple) -> None:
        _, engine = populated
        # carol is READER on org/acme → inherits to org/acme/team-x/sub
        assert engine.can_read("carol", "org/acme/team-x/sub") is True
        assert engine.can_write("carol", "org/acme/team-x/sub") is False

    def test_no_upward_inheritance(self, populated: tuple) -> None:
        _, engine = populated
        # bob is WRITER on org/acme/team-x — does NOT inherit up to org/acme
        assert engine.can_write("bob", "org/acme") is False

    def test_direct_overrides_inherited(
        self, store: GrantStore, engine: PolicyEngine
    ) -> None:
        store.grant("agent-1", "org", Role.WRITER, "sys")
        store.grant("agent-1", "org/team", Role.READER, "sys")
        # Direct READER on org/team overrides inherited WRITER from org
        assert engine.effective_role("agent-1", "org/team") is Role.READER

    # ── wildcards ────────────────────────────────────────────────

    def test_wildcard_read(self, populated: tuple) -> None:
        _, engine = populated
        assert engine.can_read("anyone", "public") is True

    def test_wildcard_no_write(self, populated: tuple) -> None:
        _, engine = populated
        assert engine.can_write("anyone", "public") is False

    def test_wildcard_inherits_to_child(self, populated: tuple) -> None:
        _, engine = populated
        assert engine.can_read("stranger", "public/docs") is True

    def test_agent_grant_beats_wildcard(
        self, store: GrantStore, engine: PolicyEngine
    ) -> None:
        store.grant("*", "shared", Role.READER, "sys")
        store.grant("vip", "shared", Role.ADMIN, "sys")
        assert engine.effective_role("vip", "shared") is Role.ADMIN

    # ── effective_role ───────────────────────────────────────────

    def test_effective_role_direct(self, populated: tuple) -> None:
        _, engine = populated
        assert engine.effective_role("bob", "org/acme/team-x") is Role.WRITER

    def test_effective_role_inherited(self, populated: tuple) -> None:
        _, engine = populated
        assert engine.effective_role("alice", "org/acme/team-x/proj") is Role.OWNER

    # ── list_accessible ──────────────────────────────────────────

    def test_list_accessible_all(self, populated: tuple) -> None:
        _, engine = populated
        namespaces = engine.list_accessible("alice")
        assert "org/acme" in namespaces
        # wildcard "public" is included as well
        assert "public" in namespaces

    def test_list_accessible_min_role(self, populated: tuple) -> None:
        _, engine = populated
        namespaces = engine.list_accessible("carol", min_role=Role.WRITER)
        assert "org/acme" not in namespaces  # carol is only READER

    def test_list_accessible_empty(self, engine: PolicyEngine) -> None:
        assert engine.list_accessible("nobody") == []

    # ── default engine (no store) ────────────────────────────────

    def test_default_engine_no_store(self) -> None:
        eng = PolicyEngine()
        assert eng.effective_role("x", "y") is Role.NONE


# ═════════════════════════════════════════════════════════════════
# TestEnforcement
# ═════════════════════════════════════════════════════════════════


class TestEnforcement:
    """Enforcement middleware — enforce(), AccessDenied, context managers."""

    # ── Operation enum ───────────────────────────────────────────

    def test_operation_values(self) -> None:
        assert Operation.READ.value == "read"
        assert Operation.WRITE.value == "write"
        assert Operation.DELETE.value == "delete"
        assert Operation.ADMIN.value == "admin"

    # ── enforce ──────────────────────────────────────────────────

    def test_enforce_allows_read(self, populated: tuple) -> None:
        _, engine = populated
        enforce(engine, "carol", "org/acme", Operation.READ)  # should not raise

    def test_enforce_denies_write(self, populated: tuple) -> None:
        _, engine = populated
        with pytest.raises(AccessDenied) as exc_info:
            enforce(engine, "carol", "org/acme", Operation.WRITE)
        err = exc_info.value
        assert err.agent_id == "carol"
        assert err.namespace == "org/acme"
        assert err.operation is Operation.WRITE

    def test_enforce_admin(self, populated: tuple) -> None:
        _, engine = populated
        enforce(engine, "alice", "org/acme", Operation.ADMIN)  # OWNER can admin

    def test_enforce_delete_requires_write(self, populated: tuple) -> None:
        _, engine = populated
        # bob is WRITER on org/acme/team-x → can delete
        enforce(engine, "bob", "org/acme/team-x", Operation.DELETE)
        # carol is READER → cannot delete
        with pytest.raises(AccessDenied):
            enforce(engine, "carol", "org/acme", Operation.DELETE)

    # ── AccessDenied fields ──────────────────────────────────────

    def test_access_denied_message(self) -> None:
        err = AccessDenied("a1", "ns", Operation.READ)
        assert "a1" in str(err)
        assert "ns" in str(err)
        assert "read" in str(err)

    def test_access_denied_is_exception(self) -> None:
        assert issubclass(AccessDenied, Exception)

    # ── checked_read ─────────────────────────────────────────────

    def test_checked_read_success(self, populated: tuple) -> None:
        _, engine = populated
        with checked_read(engine, "carol", "org/acme"):
            pass  # should not raise

    def test_checked_read_denied(self, engine: PolicyEngine) -> None:
        with pytest.raises(AccessDenied):
            with checked_read(engine, "nobody", "org/acme"):
                pass

    # ── checked_write ────────────────────────────────────────────

    def test_checked_write_success(self, populated: tuple) -> None:
        _, engine = populated
        with checked_write(engine, "bob", "org/acme/team-x"):
            pass  # should not raise

    def test_checked_write_denied(self, populated: tuple) -> None:
        _, engine = populated
        with pytest.raises(AccessDenied):
            with checked_write(engine, "carol", "org/acme"):
                pass


# ═════════════════════════════════════════════════════════════════
# TestAccessPolicy
# ═════════════════════════════════════════════════════════════════


class TestAccessPolicy:
    """AccessPolicy dataclass."""

    def test_default_inherited(self) -> None:
        ap = AccessPolicy(namespace="ns", agent_id="a", role=Role.READER)
        assert ap.inherited is False

    def test_inherited_flag(self) -> None:
        ap = AccessPolicy(namespace="ns", agent_id="a", role=Role.WRITER, inherited=True)
        assert ap.inherited is True

    def test_frozen(self) -> None:
        ap = AccessPolicy(namespace="ns", agent_id="a", role=Role.READER)
        with pytest.raises(AttributeError):
            ap.role = Role.WRITER  # type: ignore[misc]
