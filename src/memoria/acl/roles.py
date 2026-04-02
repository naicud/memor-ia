"""Role definitions and permission helpers for the access-control layer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


# ── Role hierarchy ────────────────────────────────────────────────


class Role(IntEnum):
    """Ordered permission levels (higher value == more power)."""

    NONE = 0
    READER = 1
    WRITER = 2
    ADMIN = 3
    OWNER = 4


# ── Role assignment record ───────────────────────────────────────


@dataclass(frozen=True)
class RoleAssignment:
    """Immutable record of a role granted to an agent on a namespace."""

    agent_id: str
    namespace: str
    role: Role
    granted_by: str
    granted_at: str  # ISO-8601 UTC


# ── Permission predicates ────────────────────────────────────────


def role_can_read(role: Role) -> bool:
    """Return *True* when *role* is READER or above."""
    return role >= Role.READER


def role_can_write(role: Role) -> bool:
    """Return *True* when *role* is WRITER or above."""
    return role >= Role.WRITER


def role_can_admin(role: Role) -> bool:
    """Return *True* when *role* is ADMIN or above."""
    return role >= Role.ADMIN


# ── Inheritance ──────────────────────────────────────────────────


def role_inherits(parent_role: Role) -> Role:
    """Determine the inherited role a child namespace receives.

    A parent namespace role propagates *unchanged* to its descendants.
    For example, WRITER on ``org/acme`` yields WRITER on
    ``org/acme/team-x``.

    Returns :attr:`Role.NONE` when the parent role is NONE.
    """
    return parent_role
