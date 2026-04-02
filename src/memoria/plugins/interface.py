"""Plugin interface (ABC) for MEMORIA extensions.

All plugins must subclass :class:`MemoriaPlugin` and implement
the required ``name`` and ``version`` properties.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MemoriaPlugin(ABC):
    """Base class for MEMORIA plugins.

    Lifecycle
    ---------
    1. ``on_startup(memoria)`` — called when the plugin is activated
    2. Event hooks (``on_memory_created``, etc.) — called during operation
    3. ``on_shutdown()`` — called on graceful shutdown

    Extension points
    ----------------
    - ``register_tools()`` — return MCP tool definitions
    - ``register_backends()`` — return custom storage backends
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique plugin name (e.g., 'memoria-slack')."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """Semantic version string (e.g., '1.0.0')."""
        ...

    @property
    def description(self) -> str:
        """Optional human-readable description."""
        return ""

    @property
    def author(self) -> str:
        """Optional author name."""
        return ""

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def on_startup(self, memoria: Any) -> None:
        """Called when the plugin is activated with a Memoria instance."""

    def on_shutdown(self) -> None:
        """Called on graceful shutdown."""

    # ------------------------------------------------------------------
    # Event hooks
    # ------------------------------------------------------------------

    def on_memory_created(
        self,
        memory_id: str,
        content: str,
        metadata: dict[str, Any],
    ) -> None:
        """Hook: after a memory is created."""

    def on_memory_searched(
        self,
        query: str,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Hook: modify search results before returning.

        Must return the (possibly modified) results list.
        """
        return results

    def on_memory_deleted(
        self,
        memory_id: str,
    ) -> None:
        """Hook: after a memory is deleted."""

    # ------------------------------------------------------------------
    # Extension registration
    # ------------------------------------------------------------------

    def register_tools(self) -> list[dict[str, Any]]:
        """Return MCP tool definitions this plugin provides.

        Each dict should have at minimum:
        - ``name``: tool name
        - ``description``: tool description
        - ``handler``: async callable(params) -> str
        """
        return []

    def register_backends(self) -> dict[str, Any]:
        """Return custom storage backends.

        Keys are backend type names (e.g., 'vector', 'graph'),
        values are backend instances or factories.
        """
        return {}

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def info(self) -> dict[str, Any]:
        """Return plugin metadata as a dict."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "tools": len(self.register_tools()),
            "backends": list(self.register_backends().keys()),
        }
