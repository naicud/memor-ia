"""Plugin registry — manages enabled/disabled plugins and their lifecycle."""

from __future__ import annotations

import logging
import threading
from typing import Any

from memoria.plugins.interface import MemoriaPlugin

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Central registry for loaded plugins.

    Thread-safe.  Plugins are activated via :meth:`activate` and
    deactivated via :meth:`deactivate`.  Active plugins receive
    lifecycle and event callbacks.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._plugins: dict[str, MemoriaPlugin] = {}
        self._active: set[str] = set()
        self._memoria_ref: Any = None

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, plugin: MemoriaPlugin) -> bool:
        """Register a plugin.  Returns True if newly registered."""
        with self._lock:
            if plugin.name in self._plugins:
                logger.warning("Plugin %s already registered", plugin.name)
                return False
            self._plugins[plugin.name] = plugin
            logger.info("Registered plugin: %s v%s", plugin.name, plugin.version)
            return True

    def unregister(self, name: str) -> bool:
        """Unregister (and deactivate if active).  Returns True if found."""
        with self._lock:
            if name not in self._plugins:
                return False
            if name in self._active:
                plugin = self._plugins[name]
                try:
                    plugin.on_shutdown()
                except Exception as exc:
                    logger.error("Error shutting down plugin %s: %s", name, exc)
                self._active.discard(name)
            del self._plugins[name]
            return True

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------

    def activate(self, name: str, memoria: Any = None) -> bool:
        """Activate a registered plugin.  Returns True if activated."""
        with self._lock:
            if name not in self._plugins:
                return False
            if name in self._active:
                return True  # already active
            plugin = self._plugins[name]
            ref = memoria or self._memoria_ref
            try:
                plugin.on_startup(ref)
            except Exception as exc:
                logger.error("Plugin %s startup failed: %s", name, exc)
                return False
            self._active.add(name)
            return True

    def deactivate(self, name: str) -> bool:
        """Deactivate an active plugin.  Returns True if deactivated."""
        with self._lock:
            if name not in self._active:
                return False
            plugin = self._plugins[name]
            try:
                plugin.on_shutdown()
            except Exception as exc:
                logger.error("Plugin %s shutdown error: %s", name, exc)
            self._active.discard(name)
            return True

    def activate_all(self, memoria: Any = None) -> int:
        """Activate all registered plugins.  Returns count activated."""
        with self._lock:
            names = list(self._plugins.keys())
        count = 0
        for name in names:
            if self.activate(name, memoria):
                count += 1
        return count

    def deactivate_all(self) -> int:
        """Deactivate all active plugins.  Returns count deactivated."""
        with self._lock:
            names = list(self._active)
        count = 0
        for name in names:
            if self.deactivate(name):
                count += 1
        return count

    def set_memoria_ref(self, memoria: Any) -> None:
        """Set the Memoria reference for plugin activation."""
        self._memoria_ref = memoria

    # ------------------------------------------------------------------
    # Event dispatch
    # ------------------------------------------------------------------

    def dispatch_memory_created(
        self, memory_id: str, content: str, metadata: dict[str, Any]
    ) -> None:
        """Notify all active plugins about memory creation."""
        for plugin in self._get_active_plugins():
            try:
                plugin.on_memory_created(memory_id, content, metadata)
            except Exception as exc:
                logger.error(
                    "Plugin %s.on_memory_created failed: %s", plugin.name, exc
                )

    def dispatch_memory_searched(
        self, query: str, results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Notify active plugins and allow result modification."""
        current = results
        for plugin in self._get_active_plugins():
            try:
                current = plugin.on_memory_searched(query, current)
            except Exception as exc:
                logger.error(
                    "Plugin %s.on_memory_searched failed: %s", plugin.name, exc
                )
        return current

    def dispatch_memory_deleted(self, memory_id: str) -> None:
        """Notify all active plugins about memory deletion."""
        for plugin in self._get_active_plugins():
            try:
                plugin.on_memory_deleted(memory_id)
            except Exception as exc:
                logger.error(
                    "Plugin %s.on_memory_deleted failed: %s", plugin.name, exc
                )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_plugins(self) -> list[dict[str, Any]]:
        """Return info for all registered plugins."""
        with self._lock:
            return [
                {**p.info(), "active": p.name in self._active}
                for p in self._plugins.values()
            ]

    def get_plugin(self, name: str) -> MemoriaPlugin | None:
        with self._lock:
            return self._plugins.get(name)

    def is_active(self, name: str) -> bool:
        with self._lock:
            return name in self._active

    def count(self) -> int:
        with self._lock:
            return len(self._plugins)

    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    def get_all_tools(self) -> list[dict[str, Any]]:
        """Collect MCP tool definitions from all active plugins."""
        tools: list[dict[str, Any]] = []
        for plugin in self._get_active_plugins():
            try:
                tools.extend(plugin.register_tools())
            except Exception as exc:
                logger.error(
                    "Plugin %s.register_tools failed: %s", plugin.name, exc
                )
        return tools

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "registered": len(self._plugins),
                "active": len(self._active),
                "plugins": list(self._plugins.keys()),
                "active_plugins": list(self._active),
            }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_active_plugins(self) -> list[MemoriaPlugin]:
        with self._lock:
            return [
                self._plugins[name]
                for name in self._active
                if name in self._plugins
            ]
