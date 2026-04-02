"""Zero-dependency HTTP server for the Memoria dashboard."""

from __future__ import annotations

import http.server
import json
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from memoria.dashboard.api import DashboardAPI

STATIC_DIR = Path(__file__).parent / "static"


class _DashboardHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler serving REST API and static dashboard files."""

    api: DashboardAPI
    static_dir: Path = STATIC_DIR

    def log_message(self, format: str, *args: Any) -> None:
        pass  # suppress default logging

    def _send_json(self, status: int, data: dict) -> None:
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, filepath: Path, content_type: str) -> None:
        try:
            data = filepath.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self._send_json(404, {"error": "File not found"})

    def _parse_query(self) -> dict[str, str]:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        return {k: v[0] for k, v in qs.items()}

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/"):
            query = self._parse_query()
            status, data = self.api.route("GET", path, query=query)
            self._send_json(status, data)
            return

        self._serve_static(path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = None
        if content_length > 0:
            raw = self.rfile.read(content_length)
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                self._send_json(400, {"error": "Invalid JSON"})
                return

        query = self._parse_query()
        status, data = self.api.route("POST", parsed.path, body=body, query=query)
        self._send_json(status, data)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        query = self._parse_query()
        status, data = self.api.route("DELETE", parsed.path, query=query)
        self._send_json(status, data)

    def _serve_static(self, path: str) -> None:
        if path == "/" or path == "":
            path = "/index.html"

        filepath = self.static_dir / path.lstrip("/")

        if not filepath.is_file():
            filepath = self.static_dir / "index.html"

        if not filepath.is_file():
            self._send_json(404, {"error": "Not found"})
            return

        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json",
            ".png": "image/png",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
        }
        ext = filepath.suffix.lower()
        ct = content_types.get(ext, "application/octet-stream")
        self._send_file(filepath, ct)


class DashboardServer:
    """Manages the dashboard HTTP server lifecycle."""

    def __init__(self, memoria: Any, host: str = "127.0.0.1", port: int = 8080) -> None:
        self._memoria = memoria
        self._host = host
        self._port = port
        self._server: http.server.HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._start_time: float | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self._port}"

    def start(self) -> dict:
        """Start the dashboard server in a background thread."""
        if self._running:
            return {"status": "already_running", "url": self.url}

        api = DashboardAPI(self._memoria)

        handler_class = type(
            "_Handler",
            (_DashboardHandler,),
            {"api": api, "static_dir": STATIC_DIR},
        )

        self._server = http.server.HTTPServer((self._host, self._port), handler_class)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self._running = True
        self._start_time = time.time()

        return {"status": "started", "url": self.url, "host": self._host, "port": self._port}

    def stop(self) -> dict:
        """Stop the dashboard server."""
        if not self._running or self._server is None:
            return {"status": "not_running"}

        self._server.shutdown()
        self._server.server_close()
        if self._thread:
            self._thread.join(timeout=5)
        self._running = False
        self._server = None
        self._thread = None

        uptime = time.time() - (self._start_time or time.time())
        self._start_time = None
        return {"status": "stopped", "uptime_seconds": round(uptime, 1)}

    def status(self) -> dict:
        """Get dashboard server status."""
        if not self._running:
            return {"running": False}

        uptime = time.time() - (self._start_time or time.time())
        return {
            "running": True,
            "url": self.url,
            "host": self._host,
            "port": self._port,
            "uptime_seconds": round(uptime, 1),
        }
