"""Stream manager — central registry for all active channels.

Bridges the synchronous ``MessageBus`` to async SSE/WebSocket channels
by subscribing to ``"*"`` (all events) and fan-out dispatching to each
registered channel.
"""

from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Any, Callable

from memoria.streaming.filters import EventFilter
from memoria.streaming.sse import SSEChannel
from memoria.streaming.websocket import WSChannel


class StreamManager:
    """Manages all active streaming channels and bridges the event bus.

    Thread-safe.  The manager subscribes to the event bus with ``"*"``
    (wildcard) and fans out every event to all registered channels,
    letting each channel's own ``EventFilter`` decide acceptance.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sse_channels: dict[str, SSEChannel] = {}
        self._ws_channels: dict[str, WSChannel] = {}
        self._unsubscribe_fn: Callable[[], None] | None = None
        self._total_events_dispatched = 0

    # ------------------------------------------------------------------
    # Bus bridge
    # ------------------------------------------------------------------

    def attach_to_bus(self, bus: Any) -> None:
        """Subscribe to all events on the given ``MessageBus``."""
        if self._unsubscribe_fn is not None:
            return  # already attached
        self._unsubscribe_fn = bus.subscribe("*", self._on_bus_event)

    def detach_from_bus(self) -> None:
        """Unsubscribe from the event bus."""
        if self._unsubscribe_fn is not None:
            self._unsubscribe_fn()
            self._unsubscribe_fn = None

    def _on_bus_event(self, event: Any) -> None:
        """Callback invoked by the MessageBus for every event."""
        event_type = (
            event.type.value if isinstance(event.type, Enum) else str(event.type)
        )
        event_data = dict(event.data) if hasattr(event, "data") else {}
        event_data.setdefault("source", getattr(event, "source", "unknown"))
        event_data.setdefault("timestamp", getattr(event, "timestamp", time.time()))

        self._dispatch(event_type, event_data)

    def _dispatch(self, event_type: str, event_data: dict[str, Any]) -> None:
        """Fan-out an event to all registered channels."""
        with self._lock:
            sse_channels = list(self._sse_channels.values())
            ws_channels = list(self._ws_channels.values())

        closed_sse: list[str] = []
        closed_ws: list[str] = []

        for ch in sse_channels:
            if ch.closed:
                closed_sse.append(ch.channel_id)
            else:
                ch.push(event_type, event_data)

        for ch in ws_channels:
            if ch.closed:
                closed_ws.append(ch.channel_id)
            else:
                ch.push(event_type, event_data)

        self._total_events_dispatched += 1

        # Cleanup closed channels
        if closed_sse or closed_ws:
            with self._lock:
                for cid in closed_sse:
                    self._sse_channels.pop(cid, None)
                for cid in closed_ws:
                    self._ws_channels.pop(cid, None)

    # ------------------------------------------------------------------
    # Direct dispatch (for use outside bus, e.g., from MCP tools)
    # ------------------------------------------------------------------

    def broadcast(self, event_type: str, event_data: dict[str, Any]) -> int:
        """Broadcast an event to all channels.  Returns the number of channels notified."""
        with self._lock:
            channels = list(self._sse_channels.values()) + list(self._ws_channels.values())

        count = 0
        for ch in channels:
            if not ch.closed:
                ch.push(event_type, event_data)
                count += 1
        return count

    # ------------------------------------------------------------------
    # SSE channel management
    # ------------------------------------------------------------------

    def create_sse_channel(
        self,
        channel_id: str | None = None,
        event_filter: EventFilter | None = None,
        max_queue: int = 256,
    ) -> SSEChannel:
        """Create and register a new SSE channel."""
        ch = SSEChannel(
            channel_id=channel_id,
            event_filter=event_filter,
            max_queue=max_queue,
        )
        with self._lock:
            self._sse_channels[ch.channel_id] = ch
        return ch

    def get_sse_channel(self, channel_id: str) -> SSEChannel | None:
        with self._lock:
            return self._sse_channels.get(channel_id)

    def close_sse_channel(self, channel_id: str) -> bool:
        with self._lock:
            ch = self._sse_channels.pop(channel_id, None)
        if ch is not None:
            ch.close()
            return True
        return False

    # ------------------------------------------------------------------
    # WebSocket channel management
    # ------------------------------------------------------------------

    def create_ws_channel(
        self,
        channel_id: str | None = None,
        event_filter: EventFilter | None = None,
        max_queue: int = 256,
    ) -> WSChannel:
        """Create and register a new WebSocket channel."""
        ch = WSChannel(
            channel_id=channel_id,
            event_filter=event_filter,
            max_queue=max_queue,
        )
        with self._lock:
            self._ws_channels[ch.channel_id] = ch
        return ch

    def get_ws_channel(self, channel_id: str) -> WSChannel | None:
        with self._lock:
            return self._ws_channels.get(channel_id)

    def close_ws_channel(self, channel_id: str) -> bool:
        with self._lock:
            ch = self._ws_channels.pop(channel_id, None)
        if ch is not None:
            ch.close()
            return True
        return False

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def close_channel(self, channel_id: str) -> bool:
        """Close a channel by ID (SSE or WS)."""
        return self.close_sse_channel(channel_id) or self.close_ws_channel(channel_id)

    def close_all(self) -> int:
        """Close all channels.  Returns the number closed."""
        with self._lock:
            all_channels = list(self._sse_channels.values()) + list(
                self._ws_channels.values()
            )
            self._sse_channels.clear()
            self._ws_channels.clear()

        for ch in all_channels:
            ch.close()
        return len(all_channels)

    def list_channels(self) -> list[dict[str, Any]]:
        """Return info dicts for all active channels."""
        with self._lock:
            channels = list(self._sse_channels.values()) + list(
                self._ws_channels.values()
            )
        return [ch.info() for ch in channels if not ch.closed]

    def stats(self) -> dict[str, Any]:
        """Return manager-level statistics."""
        with self._lock:
            sse_count = len(self._sse_channels)
            ws_count = len(self._ws_channels)
        return {
            "sse_channels": sse_count,
            "ws_channels": ws_count,
            "total_channels": sse_count + ws_count,
            "total_events_dispatched": self._total_events_dispatched,
            "bus_attached": self._unsubscribe_fn is not None,
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_manager = StreamManager()


def get_stream_manager() -> StreamManager:
    """Return the module-level singleton ``StreamManager``."""
    return _manager
