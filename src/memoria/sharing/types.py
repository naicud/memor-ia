"""MEMORIA sharing types — data structures for multi-agent memory sharing."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import time


class BroadcastPolicy(Enum):
    """Policy controlling how memory events are broadcast to team members."""
    ALL = "all"
    NAMESPACE = "namespace"
    TOPIC = "topic"
    NONE = "none"


class ConflictStrategy(Enum):
    """Strategy for resolving conflicting memories across agents."""
    LATEST_WINS = "latest_wins"
    HIGHEST_CONFIDENCE = "highest_confidence"
    MANUAL = "manual"
    MERGE = "merge"


class SubscriptionFilter(Enum):
    """Filter type for memory event subscriptions."""
    BY_NAMESPACE = "by_namespace"
    BY_TOPIC = "by_topic"
    BY_AGENT = "by_agent"
    ALL = "all"


@dataclass
class SharedMemoryEvent:
    """A memory event broadcast across agents."""
    event_id: str
    source_agent_id: str
    target_namespace: str
    memory_key: str
    memory_value: Any
    timestamp: float = field(default_factory=time.time)
    topics: List[str] = field(default_factory=list)
    ttl: Optional[float] = None
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "source_agent_id": self.source_agent_id,
            "target_namespace": self.target_namespace,
            "memory_key": self.memory_key,
            "memory_value": self.memory_value,
            "timestamp": self.timestamp,
            "topics": list(self.topics),
            "ttl": self.ttl,
            "provenance": dict(self.provenance),
        }

    def is_expired(self) -> bool:
        if self.ttl is None:
            return False
        return (time.time() - self.timestamp) > self.ttl


@dataclass
class MemorySubscription:
    """A subscription to memory events with filtering."""
    subscriber_id: str
    filter_type: SubscriptionFilter
    filter_value: str = ""
    callback_id: str = ""
    created_at: float = field(default_factory=time.time)
    active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subscriber_id": self.subscriber_id,
            "filter_type": self.filter_type.value,
            "filter_value": self.filter_value,
            "callback_id": self.callback_id,
            "created_at": self.created_at,
            "active": self.active,
        }


@dataclass
class TeamMemoryView:
    """Aggregated view of a team's memories."""
    team_id: str
    agent_memories: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    shared_memories: List[Dict[str, Any]] = field(default_factory=list)
    total_memories: int = 0
    last_sync: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "team_id": self.team_id,
            "agent_memories": dict(self.agent_memories),
            "shared_memories": list(self.shared_memories),
            "total_memories": self.total_memories,
            "last_sync": self.last_sync,
        }


@dataclass
class TeamDNAProfile:
    """Aggregated DNA profile for a team of agents."""
    team_id: str
    member_count: int = 0
    aggregated_expertise: Dict[str, float] = field(default_factory=dict)
    common_preferences: Dict[str, Any] = field(default_factory=dict)
    diversity_score: float = 0.0
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "team_id": self.team_id,
            "member_count": self.member_count,
            "aggregated_expertise": dict(self.aggregated_expertise),
            "common_preferences": dict(self.common_preferences),
            "diversity_score": self.diversity_score,
            "last_updated": self.last_updated,
        }


@dataclass
class CoherenceReport:
    """Report on memory coherence across a team."""
    team_id: str
    total_checked: int = 0
    conflicts_found: int = 0
    resolved: int = 0
    unresolved: int = 0
    details: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "team_id": self.team_id,
            "total_checked": self.total_checked,
            "conflicts_found": self.conflicts_found,
            "resolved": self.resolved,
            "unresolved": self.unresolved,
            "details": list(self.details),
            "timestamp": self.timestamp,
        }
