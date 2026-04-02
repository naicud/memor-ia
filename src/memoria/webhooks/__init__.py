"""External webhook system for MEMORIA.

Allows registering HTTP webhook endpoints that receive notifications
when memory events occur (create, update, delete, promote, etc.).
"""

from memoria.webhooks.bridge import WebhookBridge
from memoria.webhooks.dispatcher import WebhookDispatcher
from memoria.webhooks.payloads import WebhookEvent, build_payload
from memoria.webhooks.registry import Webhook, WebhookRegistry

__all__ = [
    "Webhook",
    "WebhookBridge",
    "WebhookDispatcher",
    "WebhookEvent",
    "WebhookRegistry",
    "build_payload",
]
