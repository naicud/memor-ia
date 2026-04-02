"""Policy engine — resolves effective roles with namespace inheritance."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .grants import GrantStore
from .roles import Role, role_can_admin, role_can_read, role_can_write, role_inherits


# ── Data ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AccessPolicy:
    """Snapshot of an evaluated policy for a single agent+namespace pair."""

    namespace: str
    agent_id: str
    role: Role
    inherited: bool = False


# ── Helpers ──────────────────────────────────────────────────────


def _ancestor_paths(namespace: str) -> list[str]:
    """Return all ancestor namespace paths from root to *namespace* (exclusive).

    Example::

        >>> _ancestor_paths("org/acme/team-x")
        ['org', 'org/acme']
    """
    parts = [p for p in namespace.split("/") if p]
    ancestors: list[str] = []
    for i in range(1, len(parts)):
        ancestors.append("/".join(parts[:i]))
    return ancestors


# ── PolicyEngine ─────────────────────────────────────────────────


class PolicyEngine:
    """Evaluate permissions against a :class:`GrantStore`.

    Inheritance logic
    -----------------
    * If *agent_id* has a direct grant on *namespace*, that role wins.
    * Otherwise, the engine walks **up** the namespace hierarchy: if the
      agent has WRITER on ``org/acme``, they inherit WRITER on
      ``org/acme/team-x`` (via :func:`role_inherits`).
    * A wildcard grant (``agent_id="*"``) applies to every agent and is
      checked at every level.  An explicit per-agent grant always beats
      a wildcard at the **same** level.
    """

    def __init__(self, grant_store: GrantStore | None = None) -> None:
        self._store = grant_store or GrantStore()

    # ── public API ───────────────────────────────────────────────

    def can_read(self, agent_id: str, namespace: str) -> bool:
        """Return *True* if *agent_id* may read from *namespace*."""
        return role_can_read(self.effective_role(agent_id, namespace))

    def can_write(self, agent_id: str, namespace: str) -> bool:
        """Return *True* if *agent_id* may write to *namespace*."""
        return role_can_write(self.effective_role(agent_id, namespace))

    def can_admin(self, agent_id: str, namespace: str) -> bool:
        """Return *True* if *agent_id* may administer *namespace*."""
        return role_can_admin(self.effective_role(agent_id, namespace))

    def effective_role(self, agent_id: str, namespace: str) -> Role:
        """Resolve the effective role considering hierarchy and wildcards.

        Resolution order (first match wins):

        1. Direct grant on *namespace* for *agent_id*.
        2. Direct wildcard grant (``"*"``) on *namespace*.
        3. Walk ancestors from nearest to root, repeating steps 1–2.
        4. Check root (``""``) grants.
        5. Fall back to :attr:`Role.NONE`.
        """
        # Check target namespace first, then ancestors (nearest → root).
        paths_to_check = [namespace] + list(reversed(_ancestor_paths(namespace)))
        # Also check the root namespace ("").
        if namespace != "":
            paths_to_check.append("")

        for ns in paths_to_check:
            is_inherited = ns != namespace
            # Agent-specific grant takes priority.
            role = self._store.get_role(agent_id, ns)
            if role is not None:
                return role_inherits(role) if is_inherited else role
            # Wildcard fallback.
            wildcard = self._store.get_role("*", ns)
            if wildcard is not None:
                return role_inherits(wildcard) if is_inherited else wildcard

        return Role.NONE

    def list_accessible(
        self,
        agent_id: str,
        min_role: Role = Role.READER,
    ) -> list[str]:
        """Return namespaces where *agent_id* has at least *min_role*.

        Only directly-granted namespaces are returned (inherited children
        are not enumerated because they are unbounded).
        """
        grants = self._store.get_grants_for_agent(agent_id)
        wildcards = self._store.get_grants_for_agent("*")
        seen: set[str] = set()
        result: list[str] = []
        for g in grants + wildcards:
            if g.namespace not in seen and g.role >= min_role:
                seen.add(g.namespace)
                result.append(g.namespace)
        return sorted(result)
