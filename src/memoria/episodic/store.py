"""Episodic memory storage — chronological event log with timeline queries."""

from __future__ import annotations

import threading
import time
import uuid
from collections import Counter
from typing import Optional

from .types import Episode, EpisodicEvent, EventType


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


class EpisodicMemory:
    """Chronological event log with timeline query capabilities.

    Supports:
    - Recording events into episodes (sessions)
    - Temporal range queries (what happened between T1 and T2)
    - Semantic search over episodes
    - Episode summarisation
    - Active episode management (start/end/current)
    - Event importance filtering
    """

    def __init__(
        self,
        max_episodes: int = 1000,
        max_events_per_episode: int = 500,
    ) -> None:
        self._lock = threading.RLock()
        self._episodes: dict[str, Episode] = {}
        self._active_episode: Optional[str] = None
        self._max_episodes = max_episodes
        self._max_events = max_events_per_episode
        self._event_counter = 0

    # ── Episode lifecycle ─────────────────────────────────────────

    def start_episode(
        self,
        agent_id: str = "",
        session_id: str = "",
        title: str = "",
    ) -> Episode:
        """Start a new episode.  Auto-closes any currently active episode."""
        with self._lock:
            if self._active_episode is not None:
                self.end_episode()

            episode = Episode(
                episode_id=_new_id(),
                title=title,
                agent_id=agent_id,
                session_id=session_id,
            )
            self._episodes[episode.episode_id] = episode
            self._active_episode = episode.episode_id
            self._rotate_episodes()
            return episode

    def end_episode(
        self,
        episode_id: str = "",
        summary: str = "",
        outcome: str = "",
    ) -> Optional[Episode]:
        """End an episode.  If *episode_id* is omitted, ends the active one."""
        with self._lock:
            eid = episode_id or self._active_episode
            if eid is None or eid not in self._episodes:
                return None

            ep = self._episodes[eid]
            ep.ended_at = time.time()
            if summary:
                ep.summary = summary
            if outcome:
                ep.outcome = outcome

            if eid == self._active_episode:
                self._active_episode = None
            return ep

    def get_active_episode(self) -> Optional[Episode]:
        """Return the currently active episode, or *None*."""
        if self._active_episode is None:
            return None
        return self._episodes.get(self._active_episode)

    # ── Event recording ───────────────────────────────────────────

    def record_event(
        self,
        content: str,
        event_type: EventType = EventType.INTERACTION,
        agent_id: str = "",
        user_id: str = "",
        importance: float = 0.5,
        metadata: Optional[dict] = None,
        episode_id: str = "",
    ) -> EpisodicEvent:
        """Record an event into the active or specified episode.

        If no episode exists and none is specified, a new one is started
        automatically.
        """
        with self._lock:
            eid = episode_id or self._active_episode
            if eid is None or eid not in self._episodes:
                ep = self.start_episode(agent_id=agent_id)
                eid = ep.episode_id

            ep = self._episodes[eid]

            if len(ep.events) >= self._max_events:
                event = EpisodicEvent(
                    event_id=_new_id(),
                    event_type=event_type,
                    content=content,
                    agent_id=agent_id,
                    user_id=user_id,
                    importance=importance,
                    metadata={**(metadata or {}), "_dropped": True,
                              "_reason": "max_events_per_episode reached"},
                )
                return event

            event = EpisodicEvent(
                event_id=_new_id(),
                event_type=event_type,
                content=content,
                agent_id=agent_id,
                user_id=user_id,
                importance=importance,
                metadata=dict(metadata) if metadata else {},
            )
            ep.events.append(event)
            self._event_counter += 1
            return event

    def record_interaction(
        self, content: str, role: str = "user", **kwargs
    ) -> EpisodicEvent:
        """Shorthand for recording an interaction event."""
        meta = kwargs.pop("metadata", {})
        meta["role"] = role
        return self.record_event(
            content=content,
            event_type=EventType.INTERACTION,
            metadata=meta,
            **kwargs,
        )

    def record_tool_use(
        self,
        tool_name: str,
        input_data: str,
        result: str,
        **kwargs,
    ) -> EpisodicEvent:
        """Shorthand for recording a tool-use event."""
        meta = kwargs.pop("metadata", {})
        meta.update({"tool": tool_name, "input": input_data, "result": result})
        return self.record_event(
            content=f"Used {tool_name}: {input_data} → {result}",
            event_type=EventType.TOOL_USE,
            metadata=meta,
            **kwargs,
        )

    def record_decision(
        self, decision: str, reasoning: str = "", **kwargs
    ) -> EpisodicEvent:
        """Shorthand for recording a decision event."""
        meta = kwargs.pop("metadata", {})
        if reasoning:
            meta["reasoning"] = reasoning
        return self.record_event(
            content=decision,
            event_type=EventType.DECISION,
            metadata=meta,
            **kwargs,
        )

    # ── Timeline queries ──────────────────────────────────────────

    def query_timeline(
        self,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        event_types: Optional[list[EventType]] = None,
        agent_id: str = "",
        min_importance: float = 0.0,
        limit: int = 50,
    ) -> list[EpisodicEvent]:
        """Query events across all episodes within a time range."""
        with self._lock:
            events: list[EpisodicEvent] = []
            for ep in list(self._episodes.values()):
                for ev in ep.events:
                    if start_time is not None and ev.timestamp < start_time:
                        continue
                    if end_time is not None and ev.timestamp > end_time:
                        continue
                    if event_types and ev.event_type not in event_types:
                        continue
                    if agent_id and ev.agent_id != agent_id:
                        continue
                    if ev.importance < min_importance:
                        continue
                    events.append(ev)

            events.sort(key=lambda e: e.timestamp)
            return events[:limit]

    def get_recent_events(
        self,
        n: int = 10,
        event_types: Optional[list[EventType]] = None,
    ) -> list[EpisodicEvent]:
        """Return the *n* most recent events, optionally filtered by type."""
        with self._lock:
            events: list[EpisodicEvent] = []
            for ep in list(self._episodes.values()):
                for ev in ep.events:
                    if event_types and ev.event_type not in event_types:
                        continue
                    events.append(ev)

            events.sort(key=lambda e: e.timestamp, reverse=True)
            return events[:n]

    def search_episodes(self, query: str, limit: int = 5) -> list[Episode]:
        """Simple word-overlap search over episode summaries and event content."""
        query_words = set(query.lower().split())
        if not query_words:
            return []

        with self._lock:
            scored: list[tuple[float, Episode]] = []
            for ep in list(self._episodes.values()):
                score = 0.0
                corpus = f"{ep.title} {ep.summary}".lower()
                score += len(query_words & set(corpus.split())) * 2.0
                for ev in ep.events:
                    overlap = len(query_words & set(ev.content.lower().split()))
                    score += overlap
                if score > 0:
                    scored.append((score, ep))

            scored.sort(key=lambda t: t[0], reverse=True)
            return [ep for _, ep in scored[:limit]]

    # ── Episode queries ───────────────────────────────────────────

    def get_episode(self, episode_id: str) -> Optional[Episode]:
        """Return an episode by ID, or *None*."""
        with self._lock:
            return self._episodes.get(episode_id)

    def list_episodes(
        self,
        agent_id: str = "",
        limit: int = 20,
        include_active: bool = True,
    ) -> list[Episode]:
        """List episodes, most recent first."""
        with self._lock:
            eps = list(self._episodes.values())
            if agent_id:
                eps = [e for e in eps if e.agent_id == agent_id]
            if not include_active:
                eps = [e for e in eps if not e.is_active()]
            eps.sort(key=lambda e: e.started_at, reverse=True)
            return eps[:limit]

    def get_episode_summary(self, episode_id: str) -> str:
        """Generate a text summary of an episode."""
        with self._lock:
            ep = self._episodes.get(episode_id)
            if ep is None:
                return ""
            if ep.summary:
                return ep.summary

            parts: list[str] = []
            if ep.title:
                parts.append(f"Episode: {ep.title}")
            parts.append(f"Events: {ep.event_count}")
            parts.append(f"Duration: {ep.duration_s:.1f}s")
            if ep.outcome:
                parts.append(f"Outcome: {ep.outcome}")

            type_counts = Counter(ev.event_type.value for ev in ep.events)
            if type_counts:
                dist = ", ".join(f"{k}={v}" for k, v in type_counts.most_common())
                parts.append(f"Types: {dist}")

            return " | ".join(parts)

    # ── Statistics ────────────────────────────────────────────────

    def stats(self) -> dict:
        """Return episodic memory statistics."""
        with self._lock:
            outcomes: dict[str, int] = Counter()
            type_dist: dict[str, int] = Counter()

            for ep in list(self._episodes.values()):
                key = ep.outcome or "unknown"
                outcomes[key] += 1
                for ev in ep.events:
                    type_dist[ev.event_type.value] += 1

            return {
                "total_episodes": len(self._episodes),
                "active_episode": self._active_episode,
                "total_events": self._event_counter,
                "episodes_by_outcome": dict(outcomes),
                "event_type_distribution": dict(type_dist),
            }

    # ── Maintenance ───────────────────────────────────────────────

    def _rotate_episodes(self) -> None:
        """Remove oldest completed episodes when over max capacity."""
        if len(self._episodes) <= self._max_episodes:
            return

        completed = [
            ep
            for ep in list(self._episodes.values())
            if not ep.is_active()
        ]
        completed.sort(key=lambda e: e.started_at)

        to_remove = len(self._episodes) - self._max_episodes
        for ep in completed[:to_remove]:
            del self._episodes[ep.episode_id]

    def compact_episode(self, episode_id: str) -> Optional[Episode]:
        """Compact an episode by removing low-importance events and
        generating a summary from them."""
        with self._lock:
            ep = self._episodes.get(episode_id)
            if ep is None:
                return None

            kept: list[EpisodicEvent] = []
            removed_contents: list[str] = []

            for ev in ep.events:
                if ev.importance > 0.7:
                    kept.append(ev)
                else:
                    removed_contents.append(ev.content)

            if removed_contents:
                compacted_summary = "Compacted events: " + "; ".join(removed_contents)
                if ep.summary:
                    ep.summary += " | " + compacted_summary
                else:
                    ep.summary = compacted_summary

            removed_count = len(ep.events) - len(kept)
            self._event_counter = max(0, self._event_counter - removed_count)
            ep.events = kept
            return ep
