"""MEMORIA MemoryCoordinator — orchestrate multi-agent memory sharing."""

from __future__ import annotations

import threading
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional

from memoria.sharing.broadcaster import MemoryBroadcaster
from memoria.sharing.types import (
    CoherenceReport,
    ConflictStrategy,
    SharedMemoryEvent,
    TeamMemoryView,
)
from memoria.sharing.watcher import MemoryWatcher


class MemoryCoordinator:
    """High-level coordinator for multi-agent memory sharing, coherence, and conflict resolution."""

    def __init__(
        self,
        broadcaster: Optional[MemoryBroadcaster] = None,
        watcher: Optional[MemoryWatcher] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._broadcaster = broadcaster or MemoryBroadcaster()
        self._watcher = watcher or MemoryWatcher()
        self._teams: Dict[str, List[str]] = {}
        self._memory_store: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._timeline: List[Dict[str, Any]] = []
        self._max_memories_per_agent: int = 50_000
        self._max_timeline: int = 100_000

    @property
    def broadcaster(self) -> MemoryBroadcaster:
        return self._broadcaster

    @property
    def watcher(self) -> MemoryWatcher:
        return self._watcher

    def register_team(self, team_id: str, agent_ids: List[str]) -> None:
        with self._lock:
            self._teams[team_id] = list(agent_ids)
            for agent_id in agent_ids:
                self._broadcaster.register_agent(agent_id)

    def get_team_status(self, team_id: str) -> Dict[str, Any]:
        with self._lock:
            agents = self._teams.get(team_id, [])
            total = sum(
                len(self._memory_store.get(aid, []))
                for aid in agents
            )
            return {
                "team_id": team_id,
                "agent_count": len(agents),
                "agents": list(agents),
                "total_memories": total,
                "broadcaster_stats": self._broadcaster.get_stats(),
                "watcher_stats": self._watcher.get_stats(),
            }

    def share_memory(
        self,
        agent_id: str,
        namespace: str,
        key: str,
        value: Any,
        topics: Optional[List[str]] = None,
        confidence: float = 1.0,
    ) -> Dict[str, Any]:
        with self._lock:
            event = SharedMemoryEvent(
                event_id=str(uuid.uuid4()),
                source_agent_id=agent_id,
                target_namespace=namespace,
                memory_key=key,
                memory_value=value,
                topics=topics or [],
                provenance={"confidence": confidence},
            )

            # Store the memory
            mem_record = {
                "key": key,
                "value": value,
                "namespace": namespace,
                "agent_id": agent_id,
                "confidence": confidence,
                "timestamp": event.timestamp,
                "topics": event.topics,
                "event_id": event.event_id,
            }
            self._memory_store[agent_id].append(mem_record)
            if len(self._memory_store[agent_id]) > self._max_memories_per_agent:
                self._memory_store[agent_id] = self._memory_store[agent_id][-self._max_memories_per_agent:]

            # Record on timeline
            self._timeline.append(mem_record)
            if len(self._timeline) > self._max_timeline:
                self._timeline = self._timeline[-self._max_timeline:]

            # Broadcast and notify
            broadcast_result = self._broadcaster.broadcast(event)
            notify_count = self._watcher.notify(event)

            return {
                "event_id": event.event_id,
                "stored": True,
                "broadcast": broadcast_result,
                "notifications_sent": notify_count,
            }

    def query_team_memories(
        self,
        team_id: str,
        topic: Optional[str] = None,
        namespace: Optional[str] = None,
    ) -> TeamMemoryView:
        with self._lock:
            agents = self._teams.get(team_id, [])
            agent_memories: Dict[str, List[Dict[str, Any]]] = {}
            shared: List[Dict[str, Any]] = []
            total = 0

            for agent_id in agents:
                memories = self._memory_store.get(agent_id, [])
                filtered: List[Dict[str, Any]] = []
                for m in memories:
                    if namespace and m.get("namespace") != namespace:
                        continue
                    if topic and topic not in m.get("topics", []):
                        continue
                    filtered.append(m)
                agent_memories[agent_id] = filtered
                total += len(filtered)

                # Memories visible to multiple agents are "shared"
                for m in filtered:
                    shared.append(m)

            return TeamMemoryView(
                team_id=team_id,
                agent_memories=agent_memories,
                shared_memories=shared,
                total_memories=total,
            )

    def check_coherence(self, team_id: str) -> CoherenceReport:
        with self._lock:
            agents = self._teams.get(team_id, [])
            all_memories: List[Dict[str, Any]] = []
            for agent_id in agents:
                for m in self._memory_store.get(agent_id, []):
                    all_memories.append(m)

            conflicts = self._detect_conflicts(all_memories)

            return CoherenceReport(
                team_id=team_id,
                total_checked=len(all_memories),
                conflicts_found=len(conflicts),
                resolved=0,
                unresolved=len(conflicts),
                details=conflicts,
            )

    def resolve_conflict(
        self,
        conflict: Dict[str, Any],
        strategy: ConflictStrategy = ConflictStrategy.LATEST_WINS,
    ) -> Dict[str, Any]:
        with self._lock:
            if strategy == ConflictStrategy.LATEST_WINS:
                return self._resolve_latest_wins(conflict)
            elif strategy == ConflictStrategy.HIGHEST_CONFIDENCE:
                return self._resolve_highest_confidence(conflict)
            elif strategy == ConflictStrategy.MERGE:
                return self._resolve_merge(conflict)
            else:
                return {
                    "strategy": strategy.value,
                    "resolved": False,
                    "conflict": conflict,
                    "reason": "manual resolution required",
                }

    def get_memory_timeline(
        self, team_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        with self._lock:
            agents = set(self._teams.get(team_id, []))
            team_events = [
                e for e in self._timeline if e.get("agent_id") in agents
            ]
            sorted_events = sorted(team_events, key=lambda e: e.get("timestamp", 0))
            return sorted_events[-limit:]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_conflicts(memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        by_key: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for m in memories:
            composite = f"{m.get('namespace', '')}::{m.get('key', '')}"
            by_key[composite].append(m)

        conflicts: List[Dict[str, Any]] = []
        for composite_key, entries in by_key.items():
            if len(entries) < 2:
                continue
            values = set()
            for e in entries:
                v = e.get("value")
                values.add(str(v))
            if len(values) > 1:
                conflicts.append({
                    "key": composite_key,
                    "entries": entries,
                    "value_count": len(values),
                })
        return conflicts

    @staticmethod
    def _resolve_latest_wins(conflict: Dict[str, Any]) -> Dict[str, Any]:
        entries = conflict.get("entries", [])
        if not entries:
            return {"strategy": "latest_wins", "resolved": False}
        winner = max(entries, key=lambda e: e.get("timestamp", 0))
        return {
            "strategy": "latest_wins",
            "resolved": True,
            "winner": winner,
            "key": conflict.get("key", ""),
        }

    @staticmethod
    def _resolve_highest_confidence(conflict: Dict[str, Any]) -> Dict[str, Any]:
        entries = conflict.get("entries", [])
        if not entries:
            return {"strategy": "highest_confidence", "resolved": False}
        winner = max(entries, key=lambda e: e.get("confidence", 0))
        return {
            "strategy": "highest_confidence",
            "resolved": True,
            "winner": winner,
            "key": conflict.get("key", ""),
        }

    @staticmethod
    def _resolve_merge(conflict: Dict[str, Any]) -> Dict[str, Any]:
        entries = conflict.get("entries", [])
        if not entries:
            return {"strategy": "merge", "resolved": False}
        # Merge: combine all values into a list, pick latest timestamp
        merged_value = [e.get("value") for e in entries]
        latest_ts = max(e.get("timestamp", 0) for e in entries)
        return {
            "strategy": "merge",
            "resolved": True,
            "merged_value": merged_value,
            "key": conflict.get("key", ""),
            "timestamp": latest_ts,
        }
