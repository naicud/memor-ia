"""Tests for the webhook system: registry, dispatcher, payloads, bridge."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from memoria.webhooks.bridge import WebhookBridge
from memoria.webhooks.dispatcher import WebhookDispatcher
from memoria.webhooks.payloads import WebhookEvent, build_payload, map_internal_event
from memoria.webhooks.registry import Webhook, WebhookRegistry

# ===================================================================
# Webhook dataclass
# ===================================================================

class TestWebhook:
    def test_defaults(self):
        wh = Webhook(webhook_id="wh_test", url="https://example.com/hook")
        assert wh.active is True
        assert wh.events == ["*"]
        assert wh.secret == ""
        assert wh.consecutive_failures == 0

    def test_matches_wildcard(self):
        wh = Webhook(webhook_id="wh1", url="http://x", events=["*"])
        assert wh.matches_event("memory.created") is True
        assert wh.matches_event("anything") is True

    def test_matches_specific(self):
        wh = Webhook(webhook_id="wh1", url="http://x", events=["memory.created", "memory.deleted"])
        assert wh.matches_event("memory.created") is True
        assert wh.matches_event("memory.deleted") is True
        assert wh.matches_event("memory.updated") is False

    def test_inactive_never_matches(self):
        wh = Webhook(webhook_id="wh1", url="http://x", events=["*"], active=False)
        assert wh.matches_event("memory.created") is False


# ===================================================================
# WebhookEvent enum
# ===================================================================

class TestWebhookEvent:
    def test_event_values(self):
        assert WebhookEvent.MEMORY_CREATED.value == "memory.created"
        assert WebhookEvent.MEMORY_UPDATED.value == "memory.updated"
        assert WebhookEvent.MEMORY_DELETED.value == "memory.deleted"
        assert WebhookEvent.MEMORY_PROMOTED.value == "memory.promoted"
        assert WebhookEvent.EPISODE_STARTED.value == "episode.started"
        assert WebhookEvent.EPISODE_ENDED.value == "episode.ended"
        assert WebhookEvent.CHURN_DETECTED.value == "churn.detected"
        assert WebhookEvent.ANOMALY_DETECTED.value == "anomaly.detected"
        assert WebhookEvent.OVERLOAD_DETECTED.value == "overload.detected"

    def test_event_count(self):
        assert len(WebhookEvent) == 9


# ===================================================================
# WebhookRegistry
# ===================================================================

class TestWebhookRegistry:
    def setup_method(self):
        self.registry = WebhookRegistry()  # in-memory

    def test_register_returns_webhook(self):
        wh = self.registry.register("https://example.com/hook")
        assert wh.webhook_id.startswith("wh_")
        assert wh.url == "https://example.com/hook"
        assert wh.events == ["*"]
        assert wh.active is True

    def test_register_with_options(self):
        wh = self.registry.register(
            "https://example.com/hook",
            events=["memory.created"],
            secret="s3cr3t",
            description="test hook",
        )
        assert wh.events == ["memory.created"]
        assert wh.secret == "s3cr3t"
        assert wh.description == "test hook"
        assert wh.created_at != ""

    def test_list_empty(self):
        assert self.registry.list_all() == []

    def test_list_returns_all(self):
        self.registry.register("http://a")
        self.registry.register("http://b")
        assert len(self.registry.list_all()) == 2

    def test_get_by_id(self):
        wh = self.registry.register("http://example.com")
        fetched = self.registry.get(wh.webhook_id)
        assert fetched is not None
        assert fetched.url == "http://example.com"

    def test_get_nonexistent(self):
        assert self.registry.get("wh_nonexistent") is None

    def test_unregister(self):
        wh = self.registry.register("http://example.com")
        assert self.registry.unregister(wh.webhook_id) is True
        assert self.registry.get(wh.webhook_id) is None

    def test_unregister_nonexistent(self):
        assert self.registry.unregister("wh_nonexistent") is False

    def test_for_event_wildcard(self):
        self.registry.register("http://a", events=["*"])
        self.registry.register("http://b", events=["memory.created"])
        result = self.registry.for_event("memory.created")
        assert len(result) == 2

    def test_for_event_specific(self):
        self.registry.register("http://a", events=["memory.created"])
        self.registry.register("http://b", events=["memory.deleted"])
        result = self.registry.for_event("memory.created")
        assert len(result) == 1
        assert result[0].url == "http://a"

    def test_for_event_excludes_inactive(self):
        wh = self.registry.register("http://a", events=["*"])
        self.registry.update_active(wh.webhook_id, False)
        assert len(self.registry.for_event("memory.created")) == 0

    def test_record_failure_increments(self):
        wh = self.registry.register("http://a")
        self.registry.record_failure(wh.webhook_id)
        updated = self.registry.get(wh.webhook_id)
        assert updated.consecutive_failures == 1
        assert updated.active is True

    def test_circuit_breaker_at_10_failures(self):
        wh = self.registry.register("http://a")
        for _ in range(10):
            self.registry.record_failure(wh.webhook_id)
        updated = self.registry.get(wh.webhook_id)
        assert updated.consecutive_failures == 10
        assert updated.active is False

    def test_record_success_resets_failures(self):
        wh = self.registry.register("http://a")
        for _ in range(5):
            self.registry.record_failure(wh.webhook_id)
        self.registry.record_success(wh.webhook_id)
        updated = self.registry.get(wh.webhook_id)
        assert updated.consecutive_failures == 0

    def test_update_active(self):
        wh = self.registry.register("http://a")
        self.registry.update_active(wh.webhook_id, False)
        assert self.registry.get(wh.webhook_id).active is False
        self.registry.update_active(wh.webhook_id, True)
        assert self.registry.get(wh.webhook_id).active is True

    def test_list_active_only(self):
        wh1 = self.registry.register("http://a")
        wh2 = self.registry.register("http://b")
        self.registry.update_active(wh1.webhook_id, False)
        active = self.registry.list_all(active_only=True)
        assert len(active) == 1
        assert active[0].webhook_id == wh2.webhook_id

    def test_persistence_on_disk(self, tmp_path):
        db = tmp_path / "webhooks.db"
        reg1 = WebhookRegistry(db_path=db)
        wh = reg1.register("http://persisted")
        # New registry instance should see the webhook
        reg2 = WebhookRegistry(db_path=db)
        assert reg2.get(wh.webhook_id) is not None


# ===================================================================
# Payloads
# ===================================================================

class TestPayloads:
    def test_build_payload_structure(self):
        p = build_payload("memory.created", "wh_123", {"memory_id": "m1"})
        assert p["event_type"] == "memory.created"
        assert p["webhook_id"] == "wh_123"
        assert p["data"]["memory_id"] == "m1"
        assert "timestamp" in p
        assert p["source"] == "memoria"

    def test_build_payload_custom_source(self):
        p = build_payload("test", "wh_x", source="custom-agent")
        assert p["source"] == "custom-agent"

    def test_build_payload_empty_data(self):
        p = build_payload("test", "wh_x")
        assert p["data"] == {}

    def test_map_internal_event_known(self):
        assert map_internal_event("memory.updated") is not None

    def test_map_internal_event_unknown(self):
        assert map_internal_event("agent.spawned") is None


# ===================================================================
# WebhookDispatcher
# ===================================================================

class TestWebhookDispatcher:
    def setup_method(self):
        self.registry = WebhookRegistry()
        self.dispatcher = WebhookDispatcher(self.registry)

    @pytest.mark.asyncio
    async def test_dispatch_success(self):
        wh = self.registry.register("http://test.local/hook", secret="key")
        payload = build_payload("memory.created", wh.webhook_id, {"id": "m1"})

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("memoria.webhooks.dispatcher.httpx") as mock_httpx:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            result = await self.dispatcher.dispatch(wh, payload)
            assert result is True
            mock_client.post.assert_called_once()

        # Failures should be reset
        updated = self.registry.get(wh.webhook_id)
        assert updated.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_dispatch_failure_records(self):
        wh = self.registry.register("http://test.local/hook")
        payload = build_payload("memory.created", wh.webhook_id)

        with patch("memoria.webhooks.dispatcher.httpx") as mock_httpx:
            mock_client = AsyncMock()
            mock_client.post.side_effect = Exception("Connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            # Override sleep to not actually wait
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await self.dispatcher.dispatch(wh, payload)

            assert result is False

        updated = self.registry.get(wh.webhook_id)
        assert updated.consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_dispatch_http_error_retries(self):
        wh = self.registry.register("http://test.local/hook")
        payload = build_payload("memory.created", wh.webhook_id)

        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 500
        mock_response_ok = MagicMock()
        mock_response_ok.status_code = 200

        with patch("memoria.webhooks.dispatcher.httpx") as mock_httpx:
            mock_client = AsyncMock()
            mock_client.post.side_effect = [mock_response_fail, mock_response_ok]
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await self.dispatcher.dispatch(wh, payload)

            assert result is True
            assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_dispatch_event_to_matching_webhooks(self):
        self.registry.register("http://a", events=["memory.created"])
        self.registry.register("http://b", events=["memory.deleted"])

        with patch("memoria.webhooks.dispatcher.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_httpx.AsyncClient.return_value = mock_client

            result = await self.dispatcher.dispatch_event(
                "memory.created", {"id": "m1"}
            )
            assert result["dispatched"] == 1
            assert result["succeeded"] == 1
            assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_dispatch_event_no_webhooks(self):
        result = await self.dispatcher.dispatch_event("memory.created", {})
        assert result["dispatched"] == 0

    def test_sign_deterministic(self):
        payload = {"event_type": "test", "data": {}}
        sig1 = self.dispatcher._sign(payload, "secret")
        sig2 = self.dispatcher._sign(payload, "secret")
        assert sig1 == sig2
        assert sig1.startswith("sha256=")

    def test_verify_signature(self):
        payload = {"event_type": "test", "data": {"x": 1}}
        sig = self.dispatcher._sign(payload, "mykey")
        assert self.dispatcher.verify_signature(payload, "mykey", sig) is True
        assert self.dispatcher.verify_signature(payload, "wrong", sig) is False

    def test_sign_different_secrets(self):
        payload = {"event_type": "test"}
        sig1 = self.dispatcher._sign(payload, "key1")
        sig2 = self.dispatcher._sign(payload, "key2")
        assert sig1 != sig2


# ===================================================================
# WebhookBridge
# ===================================================================

class TestWebhookBridge:
    def test_start_subscribes(self):
        dispatcher = MagicMock()
        bridge = WebhookBridge(dispatcher)
        with patch("memoria.webhooks.bridge.get_message_bus") as mock_bus_fn:
            mock_bus = MagicMock()
            mock_bus.subscribe.return_value = lambda: None
            mock_bus_fn.return_value = mock_bus
            bridge.start()
            mock_bus.subscribe.assert_called_once_with("*", bridge._on_event)

    def test_stop_unsubscribes(self):
        dispatcher = MagicMock()
        bridge = WebhookBridge(dispatcher)
        unsub = MagicMock()
        bridge._unsub = unsub
        bridge.stop()
        unsub.assert_called_once()
        assert bridge._unsub is None

    def test_on_event_dispatches_memory_event(self):
        registry = WebhookRegistry()
        dispatcher = WebhookDispatcher(registry)
        bridge = WebhookBridge(dispatcher)

        from memoria.comms.bus import Event, EventType
        event = Event(
            type=EventType.MEMORY_UPDATED,
            source="test",
            data={"memory_id": "m1"},
        )

        with patch.object(dispatcher, "dispatch_event", new_callable=AsyncMock):
            # Run with event loop
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(self._trigger_bridge(bridge, event))
            finally:
                loop.close()

    async def _trigger_bridge(self, bridge, event):
        """Helper to trigger bridge in an async context."""
        bridge._on_event(event)


# ===================================================================
# Integration via Memoria class
# ===================================================================

class TestMemoriaWebhookIntegration:
    def test_register_webhook(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        result = m.webhook_register("http://example.com/hook")
        assert "webhook_id" in result
        assert result["url"] == "http://example.com/hook"
        assert result["active"] is True

    def test_register_with_events(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        result = m.webhook_register(
            "http://example.com/hook",
            events=["memory.created", "memory.deleted"],
            secret="test-secret",
            description="Test hook",
        )
        assert result["events"] == ["memory.created", "memory.deleted"]
        assert result["description"] == "Test hook"

    def test_list_webhooks_empty(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        assert m.webhook_list() == []

    def test_list_webhooks(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        m.webhook_register("http://a")
        m.webhook_register("http://b")
        webhooks = m.webhook_list()
        assert len(webhooks) == 2

    def test_unregister_webhook(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        wh = m.webhook_register("http://example.com")
        result = m.webhook_unregister(wh["webhook_id"])
        assert result["removed"] is True
        assert m.webhook_list() == []

    def test_unregister_nonexistent(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        result = m.webhook_unregister("wh_nonexistent")
        assert result["removed"] is False

    def test_lazy_init(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        reg1 = m._get_webhook_registry()
        reg2 = m._get_webhook_registry()
        assert reg1 is reg2  # same instance

    def test_bridge_starts_on_register(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        m.webhook_register("http://example.com")
        # Bridge should have been started
        assert hasattr(m, "_webhook_bridge")


# ===================================================================
# Edge cases
# ===================================================================

class TestWebhookEdgeCases:
    def test_payload_serializable(self):
        p = build_payload("test", "wh_x", {"key": "value"})
        serialized = json.dumps(p)
        assert "test" in serialized

    def test_webhook_id_format(self):
        registry = WebhookRegistry()
        wh = registry.register("http://x")
        assert wh.webhook_id.startswith("wh_")
        assert len(wh.webhook_id) == 15  # "wh_" + 12 hex chars

    def test_circuit_breaker_reactivate(self):
        registry = WebhookRegistry()
        wh = registry.register("http://x")
        # Trip the circuit breaker
        for _ in range(10):
            registry.record_failure(wh.webhook_id)
        assert registry.get(wh.webhook_id).active is False
        # Manually reactivate
        registry.update_active(wh.webhook_id, True)
        updated = registry.get(wh.webhook_id)
        assert updated.active is True
        assert updated.consecutive_failures == 0  # reset on reactivation

    def test_empty_events_defaults_to_wildcard(self):
        registry = WebhookRegistry()
        wh = registry.register("http://x", events=None)
        assert wh.events == ["*"]
