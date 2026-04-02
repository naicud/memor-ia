"""Tests for the plugin system.

Covers: MemoriaPlugin interface, PluginRegistry lifecycle, loader,
event dispatch, and Memoria integration.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from memoria.plugins.interface import MemoriaPlugin
from memoria.plugins.loader import load_plugin
from memoria.plugins.registry import PluginRegistry

# ═══════════════════════════════════════════════════════════════════════════
# Test plugin implementations
# ═══════════════════════════════════════════════════════════════════════════


class SamplePlugin(MemoriaPlugin):
    """Minimal valid plugin for testing."""

    @property
    def name(self) -> str:
        return "sample-plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "A sample plugin for testing"

    @property
    def author(self) -> str:
        return "Test Author"


class ToolPlugin(MemoriaPlugin):
    """Plugin that registers tools."""

    @property
    def name(self) -> str:
        return "tool-plugin"

    @property
    def version(self) -> str:
        return "0.1.0"

    def register_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "custom_tool",
                "description": "A custom tool",
                "handler": lambda params: "ok",
            }
        ]


class HookPlugin(MemoriaPlugin):
    """Plugin that tracks lifecycle hooks."""

    def __init__(self):
        self.started = False
        self.shutdown = False
        self.created_memories: list[str] = []
        self.deleted_memories: list[str] = []
        self.search_count = 0

    @property
    def name(self) -> str:
        return "hook-plugin"

    @property
    def version(self) -> str:
        return "0.2.0"

    def on_startup(self, memoria: Any) -> None:
        self.started = True

    def on_shutdown(self) -> None:
        self.shutdown = True

    def on_memory_created(self, memory_id: str, content: str, metadata: dict) -> None:
        self.created_memories.append(memory_id)

    def on_memory_searched(self, query: str, results: list) -> list:
        self.search_count += 1
        return results

    def on_memory_deleted(self, memory_id: str) -> None:
        self.deleted_memories.append(memory_id)


class BackendPlugin(MemoriaPlugin):
    """Plugin with custom backends."""

    @property
    def name(self) -> str:
        return "backend-plugin"

    @property
    def version(self) -> str:
        return "0.3.0"

    def register_backends(self) -> dict[str, Any]:
        return {"vector": "custom_vector_backend", "graph": "custom_graph_backend"}


class FailingPlugin(MemoriaPlugin):
    """Plugin that fails on startup."""

    @property
    def name(self) -> str:
        return "failing-plugin"

    @property
    def version(self) -> str:
        return "0.0.1"

    def on_startup(self, memoria: Any) -> None:
        raise RuntimeError("Startup failed!")


class NotAPlugin:
    """Not a plugin — doesn't subclass MemoriaPlugin."""
    pass


# ═══════════════════════════════════════════════════════════════════════════
# MemoriaPlugin Interface
# ═══════════════════════════════════════════════════════════════════════════


class TestMemoriaPlugin:
    """Tests for MemoriaPlugin ABC."""

    def test_sample_plugin_properties(self):
        p = SamplePlugin()
        assert p.name == "sample-plugin"
        assert p.version == "1.0.0"
        assert p.description == "A sample plugin for testing"
        assert p.author == "Test Author"

    def test_default_description_and_author(self):
        p = ToolPlugin()
        assert p.description == ""
        assert p.author == ""

    def test_info(self):
        p = SamplePlugin()
        info = p.info()
        assert info["name"] == "sample-plugin"
        assert info["version"] == "1.0.0"
        assert info["tools"] == 0
        assert info["backends"] == []

    def test_tool_plugin_info(self):
        p = ToolPlugin()
        info = p.info()
        assert info["tools"] == 1

    def test_backend_plugin_info(self):
        p = BackendPlugin()
        info = p.info()
        assert "vector" in info["backends"]
        assert "graph" in info["backends"]

    def test_default_hooks_are_noop(self):
        p = SamplePlugin()
        p.on_startup(None)
        p.on_shutdown()
        p.on_memory_created("id", "content", {})
        results = p.on_memory_searched("query", [{"a": 1}])
        assert results == [{"a": 1}]
        p.on_memory_deleted("id")

    def test_register_tools_default(self):
        assert SamplePlugin().register_tools() == []

    def test_register_backends_default(self):
        assert SamplePlugin().register_backends() == {}


# ═══════════════════════════════════════════════════════════════════════════
# Loader
# ═══════════════════════════════════════════════════════════════════════════


class TestLoader:
    """Tests for plugin loading."""

    def test_load_valid_plugin(self):
        p = load_plugin(SamplePlugin)
        assert isinstance(p, MemoriaPlugin)
        assert p.name == "sample-plugin"

    def test_load_invalid_class_raises(self):
        with pytest.raises(TypeError, match="does not implement MemoriaPlugin"):
            load_plugin(NotAPlugin)

    def test_discover_empty(self):
        from memoria.plugins.loader import discover_plugins
        with patch("importlib.metadata.entry_points", return_value=[]):
            plugins = discover_plugins()
        assert plugins == []

    def test_discover_with_plugin(self):
        from memoria.plugins.loader import discover_plugins
        mock_ep = MagicMock()
        mock_ep.name = "sample"
        mock_ep.load.return_value = SamplePlugin
        with patch("importlib.metadata.entry_points", return_value=[mock_ep]):
            plugins = discover_plugins()
        assert len(plugins) == 1
        assert plugins[0].name == "sample-plugin"

    def test_discover_skips_invalid(self):
        from memoria.plugins.loader import discover_plugins
        mock_ep = MagicMock()
        mock_ep.name = "bad"
        mock_ep.load.return_value = NotAPlugin
        with patch("importlib.metadata.entry_points", return_value=[mock_ep]):
            plugins = discover_plugins()
        assert len(plugins) == 0

    def test_discover_skips_failing_load(self):
        from memoria.plugins.loader import discover_plugins
        mock_ep = MagicMock()
        mock_ep.name = "broken"
        mock_ep.load.side_effect = ImportError("bad import")
        with patch("importlib.metadata.entry_points", return_value=[mock_ep]):
            plugins = discover_plugins()
        assert len(plugins) == 0


# ═══════════════════════════════════════════════════════════════════════════
# PluginRegistry
# ═══════════════════════════════════════════════════════════════════════════


class TestPluginRegistry:
    """Tests for PluginRegistry lifecycle."""

    def test_register_plugin(self):
        reg = PluginRegistry()
        p = SamplePlugin()
        assert reg.register(p) is True
        assert reg.count() == 1

    def test_register_duplicate(self):
        reg = PluginRegistry()
        p = SamplePlugin()
        reg.register(p)
        assert reg.register(p) is False
        assert reg.count() == 1

    def test_unregister(self):
        reg = PluginRegistry()
        reg.register(SamplePlugin())
        assert reg.unregister("sample-plugin") is True
        assert reg.count() == 0

    def test_unregister_not_found(self):
        reg = PluginRegistry()
        assert reg.unregister("nonexistent") is False

    def test_unregister_active_calls_shutdown(self):
        reg = PluginRegistry()
        p = HookPlugin()
        reg.register(p)
        reg.activate("hook-plugin")
        reg.unregister("hook-plugin")
        assert p.shutdown is True

    def test_activate(self):
        reg = PluginRegistry()
        p = HookPlugin()
        reg.register(p)
        assert reg.activate("hook-plugin") is True
        assert p.started is True
        assert reg.is_active("hook-plugin") is True

    def test_activate_not_registered(self):
        reg = PluginRegistry()
        assert reg.activate("nonexistent") is False

    def test_activate_already_active(self):
        reg = PluginRegistry()
        reg.register(SamplePlugin())
        reg.activate("sample-plugin")
        assert reg.activate("sample-plugin") is True

    def test_activate_failing_plugin(self):
        reg = PluginRegistry()
        reg.register(FailingPlugin())
        assert reg.activate("failing-plugin") is False
        assert reg.is_active("failing-plugin") is False

    def test_deactivate(self):
        reg = PluginRegistry()
        p = HookPlugin()
        reg.register(p)
        reg.activate("hook-plugin")
        assert reg.deactivate("hook-plugin") is True
        assert p.shutdown is True
        assert reg.is_active("hook-plugin") is False

    def test_deactivate_not_active(self):
        reg = PluginRegistry()
        assert reg.deactivate("nonexistent") is False

    def test_activate_all(self):
        reg = PluginRegistry()
        reg.register(SamplePlugin())
        reg.register(ToolPlugin())
        count = reg.activate_all()
        assert count == 2
        assert reg.active_count() == 2

    def test_deactivate_all(self):
        reg = PluginRegistry()
        reg.register(SamplePlugin())
        reg.register(ToolPlugin())
        reg.activate_all()
        count = reg.deactivate_all()
        assert count == 2
        assert reg.active_count() == 0

    def test_list_plugins(self):
        reg = PluginRegistry()
        reg.register(SamplePlugin())
        reg.register(ToolPlugin())
        reg.activate("sample-plugin")
        plugins = reg.list_plugins()
        assert len(plugins) == 2
        sample = next(p for p in plugins if p["name"] == "sample-plugin")
        assert sample["active"] is True
        tool = next(p for p in plugins if p["name"] == "tool-plugin")
        assert tool["active"] is False

    def test_get_plugin(self):
        reg = PluginRegistry()
        p = SamplePlugin()
        reg.register(p)
        assert reg.get_plugin("sample-plugin") is p
        assert reg.get_plugin("nonexistent") is None

    def test_get_all_tools(self):
        reg = PluginRegistry()
        reg.register(ToolPlugin())
        reg.activate("tool-plugin")
        tools = reg.get_all_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "custom_tool"

    def test_get_all_tools_inactive_excluded(self):
        reg = PluginRegistry()
        reg.register(ToolPlugin())
        tools = reg.get_all_tools()
        assert len(tools) == 0

    def test_stats(self):
        reg = PluginRegistry()
        reg.register(SamplePlugin())
        reg.register(ToolPlugin())
        reg.activate("sample-plugin")
        s = reg.stats()
        assert s["registered"] == 2
        assert s["active"] == 1
        assert "sample-plugin" in s["active_plugins"]


# ═══════════════════════════════════════════════════════════════════════════
# Event Dispatch
# ═══════════════════════════════════════════════════════════════════════════


class TestPluginEventDispatch:
    """Tests for plugin event hooks via registry."""

    def test_dispatch_memory_created(self):
        reg = PluginRegistry()
        p = HookPlugin()
        reg.register(p)
        reg.activate("hook-plugin")
        reg.dispatch_memory_created("m1", "content", {"tag": "test"})
        assert p.created_memories == ["m1"]

    def test_dispatch_memory_searched(self):
        reg = PluginRegistry()
        p = HookPlugin()
        reg.register(p)
        reg.activate("hook-plugin")
        results = reg.dispatch_memory_searched("query", [{"id": "m1"}])
        assert p.search_count == 1
        assert results == [{"id": "m1"}]

    def test_dispatch_memory_deleted(self):
        reg = PluginRegistry()
        p = HookPlugin()
        reg.register(p)
        reg.activate("hook-plugin")
        reg.dispatch_memory_deleted("m1")
        assert p.deleted_memories == ["m1"]

    def test_dispatch_skips_inactive(self):
        reg = PluginRegistry()
        p = HookPlugin()
        reg.register(p)
        # Not activated
        reg.dispatch_memory_created("m1", "content", {})
        assert p.created_memories == []

    def test_dispatch_handles_exception(self):
        class BadPlugin(MemoriaPlugin):
            @property
            def name(self): return "bad"
            @property
            def version(self): return "0"
            def on_memory_created(self, *a, **kw):
                raise RuntimeError("boom")

        reg = PluginRegistry()
        reg.register(BadPlugin())
        reg.activate("bad")
        # Should not raise
        reg.dispatch_memory_created("m1", "content", {})

    def test_search_hook_modifies_results(self):
        class FilterPlugin(MemoriaPlugin):
            @property
            def name(self): return "filter"
            @property
            def version(self): return "1"
            def on_memory_searched(self, query, results):
                return [r for r in results if r.get("score", 0) > 0.5]

        reg = PluginRegistry()
        reg.register(FilterPlugin())
        reg.activate("filter")
        results = reg.dispatch_memory_searched(
            "test", [{"id": "a", "score": 0.9}, {"id": "b", "score": 0.3}]
        )
        assert len(results) == 1
        assert results[0]["id"] == "a"


# ═══════════════════════════════════════════════════════════════════════════
# Memoria Integration
# ═══════════════════════════════════════════════════════════════════════════


class TestMemoriaPlugins:
    """Tests for Memoria plugin methods."""

    def _make_memoria(self, tmp_path):
        from memoria import Memoria
        return Memoria(project_dir=str(tmp_path))

    def test_plugin_register(self, tmp_path):
        m = self._make_memoria(tmp_path)
        result = m.plugin_register(SamplePlugin)
        assert result["name"] == "sample-plugin"
        assert result["version"] == "1.0.0"

    def test_plugin_list(self, tmp_path):
        m = self._make_memoria(tmp_path)
        m.plugin_register(SamplePlugin)
        m.plugin_register(ToolPlugin)
        plugins = m.plugin_list()
        names = [p["name"] for p in plugins]
        assert "sample-plugin" in names
        assert "tool-plugin" in names

    def test_plugin_unregister(self, tmp_path):
        m = self._make_memoria(tmp_path)
        m.plugin_register(SamplePlugin)
        result = m.plugin_unregister("sample-plugin")
        assert result["status"] == "removed"
        assert m.plugin_list() == []

    def test_plugin_unregister_not_found(self, tmp_path):
        m = self._make_memoria(tmp_path)
        result = m.plugin_unregister("nope")
        assert result["status"] == "not_found"

    def test_plugin_activate_deactivate(self, tmp_path):
        m = self._make_memoria(tmp_path)
        m.plugin_register(SamplePlugin)
        m.plugin_deactivate("sample-plugin")
        result = m.plugin_activate("sample-plugin")
        assert result["status"] == "activated"

    def test_plugin_stats(self, tmp_path):
        m = self._make_memoria(tmp_path)
        m.plugin_register(SamplePlugin)
        stats = m.plugin_stats()
        assert stats["registered"] == 1
        assert stats["active"] == 1

    def test_plugin_discover(self, tmp_path):
        m = self._make_memoria(tmp_path)
        with patch("importlib.metadata.entry_points", return_value=[]):
            result = m.plugin_discover()
        assert result == []
