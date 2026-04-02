"""Plugin discovery and loading via Python entry points."""

from __future__ import annotations

import logging

from memoria.plugins.interface import MemoriaPlugin

logger = logging.getLogger(__name__)


def discover_plugins(group: str = "memoria.plugins") -> list[MemoriaPlugin]:
    """Discover and instantiate all plugins registered under the entry-point group.

    Parameters
    ----------
    group : str
        The entry-point group to scan (default: ``memoria.plugins``).

    Returns
    -------
    list[MemoriaPlugin]
        Instantiated plugin objects.  Plugins that fail to load are
        logged and skipped.
    """
    try:
        from importlib.metadata import entry_points
    except ImportError:
        from importlib_metadata import entry_points  # type: ignore[no-redef]

    plugins: list[MemoriaPlugin] = []
    eps = entry_points(group=group)

    for ep in eps:
        try:
            cls = ep.load()
            instance = cls()
            if not isinstance(instance, MemoriaPlugin):
                logger.warning(
                    "Entry point %s does not implement MemoriaPlugin — skipped",
                    ep.name,
                )
                continue
            plugins.append(instance)
            logger.info("Discovered plugin: %s v%s", instance.name, instance.version)
        except Exception as exc:
            logger.error("Failed to load plugin %s: %s", ep.name, exc)

    return plugins


def load_plugin(plugin_class: type) -> MemoriaPlugin:
    """Manually instantiate and validate a plugin class.

    Parameters
    ----------
    plugin_class : type
        A class that subclasses MemoriaPlugin.

    Returns
    -------
    MemoriaPlugin
        The instantiated plugin.

    Raises
    ------
    TypeError
        If the class does not subclass MemoriaPlugin.
    """
    instance = plugin_class()
    if not isinstance(instance, MemoriaPlugin):
        raise TypeError(
            f"{plugin_class.__name__} does not implement MemoriaPlugin"
        )
    return instance
