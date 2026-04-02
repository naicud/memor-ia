"""Enforcement middleware — guard clauses and context managers."""

from __future__ import annotations

from contextlib import contextmanager
from enum import Enum
from typing import TYPE_CHECKING, Generator

if TYPE_CHECKING:
    from .policies import PolicyEngine


# ── Operation enum ───────────────────────────────────────────────


class Operation(Enum):
    """Operations that can be enforced."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    ADMIN = "admin"


# ── Exception ────────────────────────────────────────────────────


class AccessDenied(Exception):
    """Raised when an agent lacks permission for an operation."""

    def __init__(
        self,
        agent_id: str,
        namespace: str,
        operation: Operation,
    ) -> None:
        self.agent_id = agent_id
        self.namespace = namespace
        self.operation = operation
        super().__init__(
            f"Agent {agent_id!r} denied {operation.value!r} on {namespace!r}"
        )


# ── Enforcement helpers ─────────────────────────────────────────

_OP_CHECKS = {
    Operation.READ: "can_read",
    Operation.WRITE: "can_write",
    Operation.DELETE: "can_write",  # DELETE requires write permission
    Operation.ADMIN: "can_admin",
}


def enforce(
    policy_engine: PolicyEngine,
    agent_id: str,
    namespace: str,
    operation: Operation,
) -> None:
    """Raise :class:`AccessDenied` if *agent_id* may not perform *operation*.

    Mapping of operations to checks:

    * READ  → ``can_read``
    * WRITE → ``can_write``
    * DELETE → ``can_write``
    * ADMIN → ``can_admin``
    """
    checker_name = _OP_CHECKS[operation]
    allowed: bool = getattr(policy_engine, checker_name)(agent_id, namespace)
    if not allowed:
        raise AccessDenied(agent_id, namespace, operation)


# ── Context managers ─────────────────────────────────────────────


@contextmanager
def checked_read(
    policy_engine: PolicyEngine,
    agent_id: str,
    namespace: str,
) -> Generator[None, None, None]:
    """Context manager that enforces READ before entering the block."""
    enforce(policy_engine, agent_id, namespace, Operation.READ)
    yield


@contextmanager
def checked_write(
    policy_engine: PolicyEngine,
    agent_id: str,
    namespace: str,
) -> Generator[None, None, None]:
    """Context manager that enforces WRITE before entering the block."""
    enforce(policy_engine, agent_id, namespace, Operation.WRITE)
    yield
