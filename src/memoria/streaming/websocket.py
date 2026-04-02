"""WebSocket channel for bidirectional streaming.

Each ``WSChannel`` wraps a conceptual WebSocket connection, receiving events
via :meth:`push` and allowing clients to send control messages (subscribe,
unsubscribe, update filters) via :meth:`handle_client_message`.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator
from uuid import uuid4

from memoria.streaming.filters import EventFilter


class WSChannel:
    """A WebSocket subscription backed by an async queue.

    Parameters
    ----------
    channel_id : str | None
        Unique channel ID.
    event_filter : EventFilter | None
        Filter applied before enqueuing.
    max_queue : int
        Max buffered messages.
    """

    def __init__(
        self,
        channel_id: str | None = None,
        event_filter: EventFilter | None = None,
        max_queue: int = 256,
    ) -> None:
        self.channel_id = channel_id or uuid4().hex[:16]
        self.event_filter = event_filter or EventFilter()
        self._queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(
            maxsize=max_queue
        )
        self._closed = False
        self._created_at = time.time()
        self._event_count = 0
        self._messages_received = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def event_count(self) -> int:
        return self._event_count

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    def close(self) -> None:
        """Close the channel."""
        if not self._closed:
            self._closed = True
            try:
                self._queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

    # ------------------------------------------------------------------
    # Push (producer side)
    # ------------------------------------------------------------------

    def push(self, event_type: str, data: dict[str, Any]) -> bool:
        """Push event if it passes the filter.  Returns False if closed."""
        if self._closed:
            return False

        if not self.event_filter.matches(event_type, data):
            return True

        msg = {
            "type": "event",
            "event_type": event_type,
            "data": data,
            "timestamp": time.time(),
            "id": uuid4().hex[:12],
        }
        try:
            self._queue.put_nowait(msg)
            self._event_count += 1
        except asyncio.QueueFull:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self._queue.put_nowait(msg)
                self._event_count += 1
            except asyncio.QueueFull:
                pass

        return True

    # ------------------------------------------------------------------
    # Client message handling (bidirectional)
    # ------------------------------------------------------------------

    def handle_client_message(self, raw: str) -> dict[str, Any]:
        """Process a message from the client (JSON string).

        Supported actions:
        - ``{"action": "update_filter", "event_types": [...], ...}``
        - ``{"action": "ping"}``

        Returns a response dict.
        """
        self._messages_received += 1
        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {"status": "error", "message": "Invalid JSON"}

        action = msg.get("action", "")

        if action == "update_filter":
            self.event_filter = EventFilter.from_params(
                event_types=msg.get("event_types"),
                user_ids=msg.get("user_ids"),
                namespaces=msg.get("namespaces"),
            )
            return {"status": "ok", "action": "filter_updated", "filter": self._filter_info()}

        if action == "ping":
            return {"status": "ok", "action": "pong", "timestamp": time.time()}

        return {"status": "error", "message": f"Unknown action: {action}"}

    # ------------------------------------------------------------------
    # Consume (async iterator — yields JSON-serializable dicts)
    # ------------------------------------------------------------------

    async def __aiter__(self) -> AsyncIterator[str]:
        """Yield JSON-encoded messages until closed and queue is drained."""
        while True:
            if self._closed and self._queue.empty():
                break
            try:
                msg = await asyncio.wait_for(self._queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                if self._closed:
                    break
                yield json.dumps({"type": "ping", "timestamp": time.time()})
                continue

            if msg is None:
                break
            yield json.dumps(msg)

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def _filter_info(self) -> dict[str, Any]:
        return {
            "event_types": list(self.event_filter.event_types),
            "user_ids": list(self.event_filter.user_ids),
            "namespaces": list(self.event_filter.namespaces),
        }

    def info(self) -> dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "type": "websocket",
            "closed": self._closed,
            "event_count": self._event_count,
            "messages_received": self._messages_received,
            "queue_size": self.queue_size,
            "created_at": self._created_at,
            "filter": self._filter_info(),
        }
