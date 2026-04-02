"""MEMORIA MemoryBroadcaster — publish memory events to registered agents."""

from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional

from memoria.sharing.types import (
    BroadcastPolicy,
    SharedMemoryEvent,
)


class MemoryBroadcaster:
    """Broadcasts memory events to registered agents based on a configurable policy."""

    def __init__(self, policy: BroadcastPolicy = BroadcastPolicy.ALL) -> None:
        self._policy = policy
        self._lock = threading.RLock()
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._history: List[Dict[str, Any]] = []
        self._total_broadcasts: int = 0
        self._total_events: int = 0
        self._events_per_agent: Dict[str, int] = defaultdict(int)
        self._max_history: int = 10_000

    @property
    def policy(self) -> BroadcastPolicy:
        with self._lock:
            return self._policy

    @property
    def total_broadcasts(self) -> int:
        with self._lock:
            return self._total_broadcasts

    @property
    def total_events(self) -> int:
        with self._lock:
            return self._total_events

    def set_policy(self, policy: BroadcastPolicy) -> None:
        with self._lock:
            self._policy = policy

    def register_agent(
        self,
        agent_id: str,
        namespaces: Optional[List[str]] = None,
        topics: Optional[List[str]] = None,
    ) -> None:
        with self._lock:
            self._agents[agent_id] = {
                "agent_id": agent_id,
                "namespaces": list(namespaces or []),
                "topics": list(topics or []),
                "registered_at": time.time(),
            }

    def unregister_agent(self, agent_id: str) -> None:
        with self._lock:
            self._agents.pop(agent_id, None)
            self._events_per_agent.pop(agent_id, None)

    def broadcast(self, event: SharedMemoryEvent) -> Dict[str, Any]:
        with self._lock:
            self._total_events += 1
            recipients: List[str] = []

            for agent_id, config in self._agents.items():
                if agent_id == event.source_agent_id:
                    continue
                if self._should_broadcast(event, agent_id, config):
                    recipients.append(agent_id)
                    self._events_per_agent[agent_id] += 1

            self._total_broadcasts += 1

            record = {
                "broadcast_id": str(uuid.uuid4()),
                "event": self._event_to_dict(event),
                "recipients": recipients,
                "policy": self._policy.value,
                "timestamp": time.time(),
            }
            self._history.append(record)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

            return {
                "broadcast_id": record["broadcast_id"],
                "recipients": recipients,
                "recipient_count": len(recipients),
                "policy": self._policy.value,
            }

    def get_broadcast_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        with self._lock:
            return list(self._history[-limit:])

    def get_registered_agents(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {aid: dict(cfg) for aid, cfg in self._agents.items()}

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_broadcasts": self._total_broadcasts,
                "total_events": self._total_events,
                "registered_agents": len(self._agents),
                "events_per_agent": dict(self._events_per_agent),
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _should_broadcast(
        self,
        event: SharedMemoryEvent,
        agent_id: str,
        agent_config: Dict[str, Any],
    ) -> bool:
        if self._policy == BroadcastPolicy.NONE:
            return False

        if self._policy == BroadcastPolicy.ALL:
            return True

        if self._policy == BroadcastPolicy.NAMESPACE:
            agent_ns = agent_config.get("namespaces", [])
            if not agent_ns:
                return False
            return event.target_namespace in agent_ns

        if self._policy == BroadcastPolicy.TOPIC:
            agent_topics = agent_config.get("topics", [])
            if not agent_topics or not event.topics:
                return False
            return bool(set(event.topics) & set(agent_topics))

        return False

    @staticmethod
    def _event_to_dict(event: SharedMemoryEvent) -> Dict[str, Any]:
        return event.to_dict()
