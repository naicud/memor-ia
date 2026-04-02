"""Access-control layer for MEMORIA — roles, grants, policies, enforcement."""

from .enforcement import AccessDenied, Operation, checked_read, checked_write, enforce
from .grants import GrantStore
from .policies import AccessPolicy, PolicyEngine
from .roles import (
    Role,
    RoleAssignment,
    role_can_admin,
    role_can_read,
    role_can_write,
    role_inherits,
)

__all__ = [
    # roles
    "Role",
    "RoleAssignment",
    "role_can_read",
    "role_can_write",
    "role_can_admin",
    "role_inherits",
    # grants
    "GrantStore",
    # policies
    "AccessPolicy",
    "PolicyEngine",
    # enforcement
    "AccessDenied",
    "Operation",
    "enforce",
    "checked_read",
    "checked_write",
]
