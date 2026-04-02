"""In-process message queue with poll/receive semantics.

Thread-safe mailbox for agent-to-agent communication within a single
process.  Supports blocking receive with timeout, non-blocking poll
with optional filter, and subscriber notification on new messages.

Mirrors the TypeScript ``Mailbox`` class from ``utils/mailbox.ts``.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class MailboxMessage:
    """A message in the mailbox."""

    sender: str  # Agent ID of sender
    content: Any  # Message payload (dict, str, etc.)
    timestamp: float = field(default_factory=time.time)
    message_type: str = "text"  # "text" | "tool_result" | "system" | "progress"
    metadata: dict = field(default_factory=dict)


class Mailbox:
    """In-process message queue with threading-safe poll/receive.

    - Thread-safe via Lock + Condition
    - Supports blocking receive with timeout
    - Supports non-blocking poll with optional filter
    - Subscriber notification on new messages
    """

    def __init__(self, maxlen: int = 10_000) -> None:
        self._queue: deque[MailboxMessage] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._subscribers: list[Callable[[], None]] = []
        self._revision: int = 0

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    def send(self, msg: MailboxMessage) -> None:
        """Add message to queue, notify waiters."""
        with self._condition:
            self._queue.append(msg)
            self._revision += 1
            self._condition.notify_all()
        # Notify subscribers outside lock to avoid deadlock
        for sub in list(self._subscribers):
            try:
                sub()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Receive (blocking & non-blocking)
    # ------------------------------------------------------------------

    def poll(
        self,
        filter_fn: Optional[Callable[[MailboxMessage], bool]] = None,
    ) -> Optional[MailboxMessage]:
        """Non-blocking check.  Returns first matching message or ``None``."""
        with self._lock:
            for i, msg in enumerate(self._queue):
                if filter_fn is None or filter_fn(msg):
                    del self._queue[i]
                    return msg
        return None

    def receive(
        self,
        timeout: Optional[float] = None,
        filter_fn: Optional[Callable[[MailboxMessage], bool]] = None,
    ) -> Optional[MailboxMessage]:
        """Blocking receive.  Waits for matching message up to *timeout*."""
        deadline = time.time() + timeout if timeout is not None else None
        with self._condition:
            while True:
                for i, msg in enumerate(self._queue):
                    if filter_fn is None or filter_fn(msg):
                        del self._queue[i]
                        return msg
                remaining = (deadline - time.time()) if deadline is not None else None
                if remaining is not None and remaining <= 0:
                    return None
                self._condition.wait(timeout=remaining)

    # ------------------------------------------------------------------
    # Peek / drain / clear
    # ------------------------------------------------------------------

    def peek(self) -> Optional[MailboxMessage]:
        """Non-destructive peek at next message."""
        with self._lock:
            return self._queue[0] if self._queue else None

    def drain(self) -> list[MailboxMessage]:
        """Remove and return all messages."""
        with self._lock:
            messages = list(self._queue)
            self._queue.clear()
            return messages

    def clear(self) -> None:
        """Remove all messages without returning them."""
        with self._lock:
            self._queue.clear()

    # ------------------------------------------------------------------
    # Subscriber management
    # ------------------------------------------------------------------

    def subscribe(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Subscribe to new messages.  Returns an unsubscribe function."""
        with self._lock:
            self._subscribers.append(callback)

        def unsubscribe() -> None:
            with self._lock:
                try:
                    self._subscribers.remove(callback)
                except ValueError:
                    pass

        return unsubscribe

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        """Number of messages currently in the mailbox."""
        with self._lock:
            return len(self._queue)

    @property
    def revision(self) -> int:
        """Monotonically-increasing counter bumped on every send."""
        return self._revision


__all__ = [
    "Mailbox",
    "MailboxMessage",
]
