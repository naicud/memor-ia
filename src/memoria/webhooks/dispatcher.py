"""Async HTTP dispatcher with retry and circuit breaker."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from memoria.webhooks.registry import Webhook, WebhookRegistry

log = logging.getLogger(__name__)


class WebhookDispatcher:
    """Deliver webhook payloads over HTTP with exponential backoff retry.

    Circuit breaker: after 10 consecutive failures for a webhook, the
    registry marks it as inactive automatically.
    """

    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 5, 30]  # seconds
    TIMEOUT = 10  # seconds

    def __init__(self, registry: "WebhookRegistry") -> None:
        self._registry = registry

    async def dispatch(self, webhook: "Webhook", payload: dict) -> bool:
        """Send *payload* to *webhook.url*.

        Returns True on success, False after all retries exhausted.
        """
        headers = {
            "Content-Type": "application/json",
            "X-Memoria-Event": payload.get("event_type", "unknown"),
            "User-Agent": "Memoria-Webhook/2.1",
        }
        if webhook.secret:
            headers["X-Memoria-Signature"] = self._sign(payload, webhook.secret)

        body = json.dumps(payload)

        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        webhook.url,
                        content=body,
                        headers=headers,
                        timeout=self.TIMEOUT,
                    )
                    if response.status_code < 400:
                        self._registry.record_success(webhook.webhook_id)
                        log.debug(
                            "webhook %s delivered (status=%d)",
                            webhook.webhook_id,
                            response.status_code,
                        )
                        return True
                    log.warning(
                        "webhook %s HTTP %d on attempt %d",
                        webhook.webhook_id,
                        response.status_code,
                        attempt + 1,
                    )
            except Exception as exc:
                log.warning(
                    "webhook %s attempt %d error: %s",
                    webhook.webhook_id,
                    attempt + 1,
                    exc,
                )

            if attempt < self.MAX_RETRIES - 1:
                await asyncio.sleep(self.RETRY_DELAYS[attempt])

        # All retries exhausted
        self._registry.record_failure(webhook.webhook_id)
        log.error(
            "webhook %s delivery failed after %d retries",
            webhook.webhook_id,
            self.MAX_RETRIES,
        )
        return False

    async def dispatch_event(self, event_type: str, data: dict) -> dict:
        """Dispatch an event to all matching webhooks.

        Returns a summary dict with delivery results.
        """
        from memoria.webhooks.payloads import build_payload

        webhooks = self._registry.for_event(event_type)
        if not webhooks:
            return {"dispatched": 0, "succeeded": 0, "failed": 0}

        results = {"dispatched": len(webhooks), "succeeded": 0, "failed": 0}
        tasks = []
        for wh in webhooks:
            payload = build_payload(event_type, wh.webhook_id, data)
            tasks.append(self.dispatch(wh, payload))

        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        for outcome in outcomes:
            if outcome is True:
                results["succeeded"] += 1
            else:
                results["failed"] += 1

        return results

    @staticmethod
    def _sign(payload: dict, secret: str) -> str:
        """Compute HMAC-SHA256 signature for the payload."""
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        sig = hmac.new(
            secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"sha256={sig}"

    def verify_signature(self, payload: dict, secret: str, signature: str) -> bool:
        """Verify a webhook signature."""
        expected = self._sign(payload, secret)
        return hmac.compare_digest(expected, signature)
