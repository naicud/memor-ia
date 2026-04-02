"""Server-Sent Events (SSE) channel.

Each ``SSEChannel`` represents a single client connection receiving a stream
of events formatted as SSE (``text/event-stream``).
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator
from uuid import uuid4

from memoria.streaming.filters import EventFilter


@dataclass
class SSEEvent:
    """A single SSE frame ready for serialization."""

    event_type: str
    data: dict[str, Any]
    event_id: str = field(default_factory=lambda: uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)

    def serialize(self) -> str:
        """Serialize to the SSE wire format."""
        lines = [
            f"id: {self.event_id}",
            f"event: {self.event_type}",
            f"data: {json.dumps(self.data)}",
            "",  # trailing blank line terminates the event
            "",
        ]
        return "\n".join(lines)


class SSEChannel:
    """A single SSE subscription backed by an async queue.

    Call :meth:`push` to enqueue events from the bus bridge;
    iterate with ``async for`` to consume them.

    Parameters
    ----------
    channel_id : str | None
        Unique channel ID.  Auto-generated if not provided.
    event_filter : EventFilter | None
        Optional filter applied *before* enqueuing.
    max_queue : int
        Maximum queue depth.  Oldest events are dropped on overflow.
    """

    def __init__(
        self,
        channel_id: str | None = None,
        event_filter: EventFilter | None = None,
        max_queue: int = 256,
    ) -> None:
        self.channel_id = channel_id or uuid4().hex[:16]
        self.event_filter = event_filter or EventFilter()
        self._queue: asyncio.Queue[SSEEvent | None] = asyncio.Queue(maxsize=max_queue)
        self._closed = False
        self._created_at = time.time()
        self._event_count = 0

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
        """Signal the channel to stop iterating."""
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
        """Push an event if it passes the filter.

        Returns ``True`` if the event was enqueued (or skipped due to filter).
        Returns ``False`` if the channel is closed.
        """
        if self._closed:
            return False

        if not self.event_filter.matches(event_type, data):
            return True  # filtered out — not an error

        sse = SSEEvent(event_type=event_type, data=data)
        try:
            self._queue.put_nowait(sse)
            self._event_count += 1
        except asyncio.QueueFull:
            # Drop oldest to make room (back-pressure strategy)
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self._queue.put_nowait(sse)
                self._event_count += 1
            except asyncio.QueueFull:
                pass

        return True

    # ------------------------------------------------------------------
    # Consume (async iterator)
    # ------------------------------------------------------------------

    async def __aiter__(self) -> AsyncIterator[str]:
        """Yield SSE-formatted strings until the channel is closed and queue is drained."""
        while True:
            if self._closed and self._queue.empty():
                break
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                if self._closed:
                    break
                # Send keepalive comment to prevent proxy/client timeouts
                yield ": keepalive\n\n"
                continue

            if event is None:
                break
            yield event.serialize()

    def info(self) -> dict[str, Any]:
        """Return channel metadata."""
        return {
            "channel_id": self.channel_id,
            "type": "sse",
            "closed": self._closed,
            "event_count": self._event_count,
            "queue_size": self.queue_size,
            "created_at": self._created_at,
            "filter": {
                "event_types": list(self.event_filter.event_types),
                "user_ids": list(self.event_filter.user_ids),
                "namespaces": list(self.event_filter.namespaces),
            },
        }
