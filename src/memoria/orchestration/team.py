"""Manage teams of agents — leader/worker coordination, idle detection.

Mirrors the TypeScript swarm system:
- Leader spawns workers
- Workers poll mailbox for new tasks
- Leader detects idle workers
- Graceful shutdown: request → wait → kill
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TeamMember:
    """A member of an agent team."""
    agent_id: str
    agent_name: str
    role: str = "worker"      # "leader" | "worker"
    status: str = "active"    # "active" | "idle" | "completed" | "failed" | "killed"
    task_id: Optional[str] = None
    color: Optional[str] = None
    spawned_at: float = field(default_factory=time.time)


@dataclass
class TeamConfig:
    """Configuration for a team."""
    team_name: str
    leader_agent_id: str
    leader_session_id: str
    max_members: int = 10


# ---------------------------------------------------------------------------
# TeamManager
# ---------------------------------------------------------------------------

_TERMINAL_STATUSES = frozenset({"completed", "failed", "killed"})


class TeamManager:
    """Manage a team of coordinated agents.

    All public methods are thread-safe (protected by ``_lock``).
    """

    def __init__(self, config: TeamConfig) -> None:
        self._config = config
        self._members: dict[str, TeamMember] = {}
        self._lock = threading.Lock()
        self._idle_callbacks: list[Callable[[TeamMember], None]] = []
        self._all_idle_event = threading.Event()
        self._shutdown_requested = False

    # -- membership ----------------------------------------------------------

    def add_member(
        self,
        agent_id: str,
        agent_name: str,
        role: str = "worker",
        **kwargs: Any,
    ) -> TeamMember:
        """Add a team member."""
        member = TeamMember(
            agent_id=agent_id,
            agent_name=agent_name,
            role=role,
            **kwargs,
        )
        with self._lock:
            if len(self._members) >= self._config.max_members:
                raise ValueError(
                    f"Team '{self._config.team_name}' is at max capacity "
                    f"({self._config.max_members})"
                )
            self._members[agent_id] = member
            self._all_idle_event.clear()
        logger.info(
            "Added %s '%s' to team '%s'",
            role, agent_name, self._config.team_name,
        )
        return member

    def remove_member(self, agent_id: str) -> Optional[TeamMember]:
        """Remove a team member.  Returns the removed member or *None*."""
        with self._lock:
            member = self._members.pop(agent_id, None)
            if member is not None:
                self._refresh_idle_event()
        return member

    # -- status transitions --------------------------------------------------

    def mark_idle(self, agent_id: str) -> None:
        """Mark agent as idle (waiting for work)."""
        with self._lock:
            member = self._members.get(agent_id)
            if member is None:
                return
            member.status = "idle"
            self._refresh_idle_event()
            idle_cbs = list(self._idle_callbacks)

        # Fire callbacks outside lock
        for cb in idle_cbs:
            try:
                cb(member)
            except Exception:
                logger.exception("Idle callback failed for %s", agent_id)

    def mark_active(self, agent_id: str) -> None:
        """Mark agent as active (executing)."""
        with self._lock:
            member = self._members.get(agent_id)
            if member is None:
                return
            member.status = "active"
            self._all_idle_event.clear()

    def mark_completed(self, agent_id: str) -> None:
        """Mark agent as completed."""
        with self._lock:
            member = self._members.get(agent_id)
            if member is None:
                return
            member.status = "completed"
            self._refresh_idle_event()

    def mark_failed(self, agent_id: str) -> None:
        """Mark agent as failed."""
        with self._lock:
            member = self._members.get(agent_id)
            if member is None:
                return
            member.status = "failed"
            self._refresh_idle_event()

    def mark_killed(self, agent_id: str) -> None:
        """Mark agent as killed."""
        with self._lock:
            member = self._members.get(agent_id)
            if member is None:
                return
            member.status = "killed"
            self._refresh_idle_event()

    # -- queries -------------------------------------------------------------

    def get_idle_members(self) -> list[TeamMember]:
        """Get all idle team members."""
        with self._lock:
            return [m for m in self._members.values() if m.status == "idle"]

    def get_active_members(self) -> list[TeamMember]:
        """Get all active team members."""
        with self._lock:
            return [m for m in self._members.values() if m.status == "active"]

    def get_member(self, agent_id: str) -> Optional[TeamMember]:
        """Get a specific member."""
        with self._lock:
            return self._members.get(agent_id)

    # -- coordination --------------------------------------------------------

    def wait_for_all_idle(self, timeout: Optional[float] = None) -> bool:
        """Wait until all non-terminal members are idle.

        Returns *True* if the condition was met within *timeout*.
        """
        return self._all_idle_event.wait(timeout=timeout)

    def request_shutdown(self) -> None:
        """Request graceful shutdown of all members."""
        with self._lock:
            self._shutdown_requested = True
            for member in self._members.values():
                if member.status not in _TERMINAL_STATUSES:
                    member.status = "killed"
            self._refresh_idle_event()
        logger.info("Shutdown requested for team '%s'", self._config.team_name)

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown_requested

    # -- callbacks -----------------------------------------------------------

    def on_member_idle(self, callback: Callable[[TeamMember], None]) -> Callable[[], None]:
        """Register callback for when a member becomes idle.

        Returns an unregister function.
        """
        with self._lock:
            self._idle_callbacks.append(callback)

        def _unregister() -> None:
            with self._lock:
                try:
                    self._idle_callbacks.remove(callback)
                except ValueError:
                    pass

        return _unregister

    # -- properties ----------------------------------------------------------

    @property
    def team_name(self) -> str:
        return self._config.team_name

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._members)

    @property
    def all_idle(self) -> bool:
        with self._lock:
            return self._all_idle_check()

    # -- internals -----------------------------------------------------------

    def _all_idle_check(self) -> bool:
        """Return True when every non-terminal member is idle.  Caller holds lock."""
        non_terminal = [
            m for m in self._members.values()
            if m.status not in _TERMINAL_STATUSES
        ]
        if not non_terminal:
            return True
        return all(m.status == "idle" for m in non_terminal)

    def _refresh_idle_event(self) -> None:
        """Set or clear ``_all_idle_event``.  Caller holds lock."""
        if self._all_idle_check():
            self._all_idle_event.set()
        else:
            self._all_idle_event.clear()


# ---------------------------------------------------------------------------
# Global team registry
# ---------------------------------------------------------------------------

_teams: dict[str, TeamManager] = {}
_teams_lock = threading.Lock()


def create_team(config: TeamConfig) -> TeamManager:
    """Create and register a new team."""
    manager = TeamManager(config)
    with _teams_lock:
        if config.team_name in _teams:
            raise ValueError(f"Team '{config.team_name}' already exists")
        _teams[config.team_name] = manager
    logger.info("Created team '%s'", config.team_name)
    return manager


def get_team(team_name: str) -> Optional[TeamManager]:
    """Retrieve a team by name."""
    with _teams_lock:
        return _teams.get(team_name)


def list_teams() -> list[str]:
    """List all registered team names."""
    with _teams_lock:
        return list(_teams.keys())


def disband_team(team_name: str) -> None:
    """Disband (remove) a team.  Requests shutdown first."""
    with _teams_lock:
        manager = _teams.pop(team_name, None)
    if manager is not None:
        manager.request_shutdown()
        logger.info("Disbanded team '%s'", team_name)


def _reset_registry() -> None:
    """Clear the global registry (testing only)."""
    with _teams_lock:
        _teams.clear()
