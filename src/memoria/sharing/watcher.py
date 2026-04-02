"""MEMORIA MemoryWatcher — subscription-based memory event notification system."""

from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional

from memoria.sharing.types import (
    MemorySubscription,
    SharedMemoryEvent,
    SubscriptionFilter,
)


class MemoryWatcher:
    """Manages subscriptions to memory events and dispatches notifications."""

    _MAX_NOTIFICATIONS_PER_SUBSCRIBER = 1_000

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscriptions: Dict[str, MemorySubscription] = {}
        self._notifications: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._total_notifications: int = 0
        self._notifications_per_subscriber: Dict[str, int] = defaultdict(int)

    @property
    def total_notifications(self) -> int:
        with self._lock:
            return self._total_notifications

    def subscribe(self, subscription: MemorySubscription) -> str:
        with self._lock:
            sub_id = subscription.callback_id or str(uuid.uuid4())
            subscription.callback_id = sub_id
            self._subscriptions[sub_id] = subscription
            return sub_id

    def unsubscribe(self, subscription_id: str) -> bool:
        with self._lock:
            if subscription_id in self._subscriptions:
                del self._subscriptions[subscription_id]
                return True
            return False

    def notify(self, event: SharedMemoryEvent) -> int:
        with self._lock:
            notified = 0
            for sub_id, sub in self._subscriptions.items():
                if not sub.active:
                    continue
                if self._matches_filter(sub, event):
                    notification = {
                        "notification_id": str(uuid.uuid4()),
                        "subscription_id": sub_id,
                        "event": event.to_dict(),
                        "timestamp": time.time(),
                    }
                    notif_list = self._notifications[sub.subscriber_id]
                    notif_list.append(notification)
                    if len(notif_list) > self._MAX_NOTIFICATIONS_PER_SUBSCRIBER:
                        self._notifications[sub.subscriber_id] = notif_list[-self._MAX_NOTIFICATIONS_PER_SUBSCRIBER:]
                    self._total_notifications += 1
                    self._notifications_per_subscriber[sub.subscriber_id] += 1
                    notified += 1
            return notified

    def get_notifications(
        self, subscriber_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        if limit <= 0:
            return []
        with self._lock:
            pending = self._notifications.get(subscriber_id, [])
            return list(pending[-limit:])

    def clear_notifications(self, subscriber_id: str) -> int:
        with self._lock:
            count = len(self._notifications.get(subscriber_id, []))
            self._notifications.pop(subscriber_id, None)
            self._notifications_per_subscriber.pop(subscriber_id, None)
            return count

    def get_active_subscriptions(
        self, subscriber_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        with self._lock:
            results: List[Dict[str, Any]] = []
            for sub_id, sub in self._subscriptions.items():
                if not sub.active:
                    continue
                if subscriber_id and sub.subscriber_id != subscriber_id:
                    continue
                results.append(sub.to_dict())
            return results

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_subscriptions": len(self._subscriptions),
                "active_subscriptions": sum(
                    1 for s in self._subscriptions.values() if s.active
                ),
                "total_notifications": self._total_notifications,
                "notifications_per_subscriber": dict(
                    self._notifications_per_subscriber
                ),
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _matches_filter(
        subscription: MemorySubscription, event: SharedMemoryEvent
    ) -> bool:
        ft = subscription.filter_type

        if ft == SubscriptionFilter.ALL:
            return True

        if ft == SubscriptionFilter.BY_NAMESPACE:
            return event.target_namespace == subscription.filter_value

        if ft == SubscriptionFilter.BY_TOPIC:
            return subscription.filter_value in event.topics

        if ft == SubscriptionFilter.BY_AGENT:
            return event.source_agent_id == subscription.filter_value

        return False
