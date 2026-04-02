"""Real-time streaming module for MEMORIA.

Provides Server-Sent Events (SSE) and WebSocket endpoints for live
memory-change notifications.  Bridges the internal ``MessageBus`` to
async streaming channels with client-side event filtering.
"""

from memoria.streaming.filters import EventFilter
from memoria.streaming.manager import StreamManager, get_stream_manager
from memoria.streaming.sse import SSEChannel
from memoria.streaming.websocket import WSChannel

__all__ = [
    "EventFilter",
    "SSEChannel",
    "StreamManager",
    "WSChannel",
    "get_stream_manager",
]
