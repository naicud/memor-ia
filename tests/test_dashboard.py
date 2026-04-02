"""Tests for the Memoria Web Dashboard module."""

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from memoria.dashboard.api import DashboardAPI
from memoria.dashboard.server import DashboardServer, _DashboardHandler

# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture
def mock_memoria():
    """Create a mock Memoria instance for API testing."""
    m = MagicMock()
    m.list_memories.return_value = [
        {"id": "m1", "content": "Hello world"},
        {"id": "m2", "content": "Test memory"},
    ]
    m.get.return_value = {"id": "m1", "content": "Hello world"}
    m.search.return_value = [{"content": "result1", "score": 0.95}]
    m.add.return_value = {"id": "m3"}
    m.delete.return_value = True
    m.list_namespaces.return_value = ["general", "work", "personal"]
    m.attachment_stats.return_value = {"total_attachments": 5, "disk_usage_bytes": 1024}
    m.list_plugins.return_value = [{"name": "test-plugin", "active": True}]
    m.stream_stats.return_value = {"active_channels": 2}
    m._get_audit_trail.return_value = MagicMock(
        get_entries=MagicMock(return_value=[
            {"action": "add", "timestamp": "2025-01-01T00:00:00Z", "details": "Added memory"}
        ])
    )
    return m


@pytest.fixture
def api(mock_memoria):
    return DashboardAPI(mock_memoria)


# ── DashboardAPI Tests ────────────────────────────────────

class TestDashboardAPI:
    """Tests for the REST API routing layer."""

    def test_health(self, api):
        status, data = api.route("GET", "/api/v1/health")
        assert status == 200
        assert data["status"] == "ok"
        assert "uptime_seconds" in data

    def test_list_memories(self, api):
        status, data = api.route("GET", "/api/v1/memories")
        assert status == 200
        assert "memories" in data
        assert data["total"] == 2

    def test_list_memories_with_namespace(self, api):
        status, data = api.route("GET", "/api/v1/memories",
                                  query={"namespace": "work"})
        assert status == 200

    def test_get_memory(self, api):
        status, data = api.route("GET", "/api/v1/memories/m1")
        assert status == 200
        assert data["id"] == "m1"

    def test_get_memory_not_found(self, api, mock_memoria):
        mock_memoria.get.return_value = None
        status, data = api.route("GET", "/api/v1/memories/missing")
        assert status == 404

    def test_add_memory(self, api):
        status, data = api.route("POST", "/api/v1/memories",
                                  body={"namespace": "general", "content": "New memory"})
        assert status == 201
        assert data["created"] is True

    def test_add_memory_no_body(self, api):
        status, data = api.route("POST", "/api/v1/memories")
        assert status == 400

    def test_add_memory_no_content(self, api):
        status, data = api.route("POST", "/api/v1/memories",
                                  body={"namespace": "general"})
        assert status == 400

    def test_delete_memory(self, api):
        status, data = api.route("DELETE", "/api/v1/memories/m1")
        assert status == 200
        assert data["deleted"] is True

    def test_search(self, api):
        status, data = api.route("GET", "/api/v1/search",
                                  query={"q": "hello"})
        assert status == 200
        assert len(data["results"]) == 1

    def test_search_no_query(self, api):
        status, data = api.route("GET", "/api/v1/search")
        assert status == 400

    def test_list_namespaces(self, api):
        status, data = api.route("GET", "/api/v1/namespaces")
        assert status == 200
        assert len(data["namespaces"]) == 3

    def test_stats(self, api):
        status, data = api.route("GET", "/api/v1/stats")
        assert status == 200
        assert "namespace_count" in data
        assert "total_memories" in data

    def test_graph_data(self, api):
        status, data = api.route("GET", "/api/v1/graph")
        assert status == 200
        assert "nodes" in data
        assert "edges" in data

    def test_audit_log(self, api):
        status, data = api.route("GET", "/api/v1/audit")
        assert status == 200
        assert "entries" in data

    def test_list_plugins_api(self, api):
        status, data = api.route("GET", "/api/v1/plugins")
        assert status == 200
        assert len(data["plugins"]) == 1

    def test_list_streams_api(self, api):
        status, data = api.route("GET", "/api/v1/streams")
        assert status == 200

    def test_404(self, api):
        status, data = api.route("GET", "/api/v1/nonexistent")
        assert status == 404

    def test_method_not_allowed(self, api):
        status, data = api.route("PUT", "/api/v1/health")
        assert status == 404

    def test_error_handling(self, api, mock_memoria):
        mock_memoria.list_memories.side_effect = Exception("DB error")
        status, data = api.route("GET", "/api/v1/memories")
        assert status == 200  # graceful degradation
        assert data["memories"] == []


# ── DashboardServer Tests ─────────────────────────────────

class TestDashboardServer:
    """Tests for the HTTP server lifecycle."""

    def test_init(self, mock_memoria):
        server = DashboardServer(mock_memoria, port=19876)
        assert not server.is_running
        assert server.url == "http://127.0.0.1:19876"

    def test_start_stop(self, mock_memoria):
        server = DashboardServer(mock_memoria, port=19877)
        result = server.start()
        assert result["status"] == "started"
        assert server.is_running
        time.sleep(0.2)

        status = server.status()
        assert status["running"] is True
        assert "uptime_seconds" in status

        result = server.stop()
        assert result["status"] == "stopped"
        assert not server.is_running

    def test_double_start(self, mock_memoria):
        server = DashboardServer(mock_memoria, port=19878)
        server.start()
        try:
            result = server.start()
            assert result["status"] == "already_running"
        finally:
            server.stop()

    def test_stop_when_not_running(self, mock_memoria):
        server = DashboardServer(mock_memoria, port=19879)
        result = server.stop()
        assert result["status"] == "not_running"

    def test_status_not_running(self, mock_memoria):
        server = DashboardServer(mock_memoria, port=19880)
        status = server.status()
        assert status["running"] is False

    def test_http_health_endpoint(self, mock_memoria):
        server = DashboardServer(mock_memoria, port=19881)
        server.start()
        try:
            time.sleep(0.3)
            req = urllib.request.Request("http://127.0.0.1:19881/api/v1/health")
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read())
                assert data["status"] == "ok"
        finally:
            server.stop()

    def test_http_static_index(self, mock_memoria):
        server = DashboardServer(mock_memoria, port=19882)
        server.start()
        try:
            time.sleep(0.3)
            req = urllib.request.Request("http://127.0.0.1:19882/")
            with urllib.request.urlopen(req, timeout=2) as resp:
                html = resp.read().decode()
                assert "Memoria" in html
        finally:
            server.stop()

    def test_http_cors_headers(self, mock_memoria):
        server = DashboardServer(mock_memoria, port=19883)
        server.start()
        try:
            time.sleep(0.3)
            req = urllib.request.Request("http://127.0.0.1:19883/api/v1/health")
            with urllib.request.urlopen(req, timeout=2) as resp:
                cors = resp.headers.get("Access-Control-Allow-Origin")
                assert cors == "*"
        finally:
            server.stop()

    def test_http_post_memory(self, mock_memoria):
        server = DashboardServer(mock_memoria, port=19884)
        server.start()
        try:
            time.sleep(0.3)
            payload = json.dumps({"namespace": "test", "content": "hello"}).encode()
            req = urllib.request.Request(
                "http://127.0.0.1:19884/api/v1/memories",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read())
                assert data["created"] is True
        finally:
            server.stop()

    def test_http_404_static(self, mock_memoria):
        server = DashboardServer(mock_memoria, port=19885)
        server.start()
        try:
            time.sleep(0.3)
            # Non-API routes should fall back to index.html (SPA routing)
            req = urllib.request.Request("http://127.0.0.1:19885/some/page")
            with urllib.request.urlopen(req, timeout=2) as resp:
                html = resp.read().decode()
                assert "Memoria" in html  # falls back to index.html
        finally:
            server.stop()


# ── Memoria Integration Tests ─────────────────────────────

class TestMemoriaDashboard:
    """Tests for Memoria dashboard accessor methods."""

    def _make_memoria(self, tmp_path):
        from memoria import Memoria
        return Memoria(project_dir=str(tmp_path))

    def test_dashboard_config(self, tmp_path):
        m = self._make_memoria(tmp_path)
        config = m.dashboard_config()
        assert config["running"] is False
        assert "port" in config

    def test_dashboard_status_not_running(self, tmp_path):
        m = self._make_memoria(tmp_path)
        status = m.dashboard_status()
        assert status["running"] is False

    def test_dashboard_url(self, tmp_path):
        m = self._make_memoria(tmp_path)
        url = m.dashboard_url()
        assert url.startswith("http://")

    def test_start_stop_dashboard(self, tmp_path):
        m = self._make_memoria(tmp_path)
        result = m.start_dashboard(port=19886)
        try:
            assert result["status"] == "started"
            status = m.dashboard_status()
            assert status["running"] is True
        finally:
            m.stop_dashboard()
        status = m.dashboard_status()
        assert status["running"] is False
