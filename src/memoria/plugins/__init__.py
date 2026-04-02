"""Plugin system for MEMORIA.

Allows community extensions via Python entry points.  Plugins can:
- Register custom MCP tools
- Hook into memory lifecycle events (created, searched, deleted)
- Provide custom storage backends
"""

from memoria.plugins.interface import MemoriaPlugin
from memoria.plugins.loader import discover_plugins, load_plugin
from memoria.plugins.registry import PluginRegistry

__all__ = [
    "MemoriaPlugin",
    "PluginRegistry",
    "discover_plugins",
    "load_plugin",
]
