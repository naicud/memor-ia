"""Standard payload schemas for webhook events."""
from __future__ import annotations

from enum import Enum


class WebhookEvent(str, Enum):
    """Webhook event types (superset of internal EventType)."""

    MEMORY_CREATED = "memory.created"
    MEMORY_UPDATED = "memory.updated"
    MEMORY_DELETED = "memory.deleted"
    MEMORY_PROMOTED = "memory.promoted"
    EPISODE_STARTED = "episode.started"
    EPISODE_ENDED = "episode.ended"
    CHURN_DETECTED = "churn.detected"
    ANOMALY_DETECTED = "anomaly.detected"
    OVERLOAD_DETECTED = "overload.detected"


# Map internal EventType values → WebhookEvent where they overlap
_INTERNAL_TO_WEBHOOK: dict[str, str] = {
    "memory.updated": WebhookEvent.MEMORY_UPDATED.value,
    "memory.recalled": WebhookEvent.MEMORY_UPDATED.value,
    "task.completed": WebhookEvent.MEMORY_UPDATED.value,
}


def map_internal_event(internal_event_type: str) -> str | None:
    """Map an internal EventType value to a WebhookEvent value.

    Returns *None* if no mapping exists (event is not webhook-worthy).
    """
    return _INTERNAL_TO_WEBHOOK.get(internal_event_type)


def build_payload(
    event_type: str,
    webhook_id: str,
    data: dict | None = None,
    *,
    source: str = "memoria",
) -> dict:
    """Build a standard webhook payload envelope.

    Returns a dict ready for JSON serialization and HTTP delivery.
    """
    from datetime import datetime, timezone

    return {
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "webhook_id": webhook_id,
        "source": source,
        "data": data or {},
    }
