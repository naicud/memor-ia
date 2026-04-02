"""Bridge between the internal event bus and the webhook dispatcher."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Callable

from memoria.comms import Event, get_message_bus
from memoria.webhooks.payloads import map_internal_event

if TYPE_CHECKING:
    from memoria.webhooks.dispatcher import WebhookDispatcher

log = logging.getLogger(__name__)


class WebhookBridge:
    """Subscribes to the internal event bus and dispatches webhooks.

    The bridge translates internal ``EventType`` values into webhook
    event names and fires the dispatcher for all matching webhooks.
    """

    def __init__(self, dispatcher: "WebhookDispatcher") -> None:
        self._dispatcher = dispatcher
        self._unsub: Callable[[], None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> None:
        """Start listening on the event bus (wildcard subscription)."""
        bus = get_message_bus()
        self._unsub = bus.subscribe("*", self._on_event)
        log.info("WebhookBridge started — listening for all events")

    def stop(self) -> None:
        """Stop listening."""
        if self._unsub:
            self._unsub()
            self._unsub = None
        log.info("WebhookBridge stopped")

    def _on_event(self, event: Event) -> None:
        """Callback for every bus event — fire webhooks if mapped."""
        webhook_event = map_internal_event(event.type.value if hasattr(event.type, "value") else str(event.type))
        if webhook_event is None:
            # Also allow direct webhook event names on the bus
            event_str = event.type.value if hasattr(event.type, "value") else str(event.type)
            if event_str.startswith("memory.") or event_str.startswith("episode.") or \
               event_str.endswith(".detected"):
                webhook_event = event_str
            else:
                return

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._dispatcher.dispatch_event(webhook_event, event.data)
            )
        except RuntimeError:
            # No running loop — run synchronously in a new loop
            try:
                loop = asyncio.new_event_loop()
                loop.run_until_complete(
                    self._dispatcher.dispatch_event(webhook_event, event.data)
                )
                loop.close()
            except Exception as exc:
                log.warning("WebhookBridge dispatch error: %s", exc)
