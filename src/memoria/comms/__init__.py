"""MEMORIA comms — mailbox, message bus, and permission bridge."""

from memoria.comms.bus import (
    Event,
    EventType,
    MessageBus,
    get_message_bus,
    publish,
    subscribe,
)
from memoria.comms.mailbox import Mailbox, MailboxMessage
from memoria.comms.permissions import (
    PermissionBridge,
    PermissionDecision,
    PermissionRequest,
    get_permission_bridge,
)

__all__ = [
    # mailbox
    "Mailbox",
    "MailboxMessage",
    # bus
    "Event",
    "EventType",
    "MessageBus",
    "get_message_bus",
    "publish",
    "subscribe",
    # permissions
    "PermissionBridge",
    "PermissionDecision",
    "PermissionRequest",
    "get_permission_bridge",
]
