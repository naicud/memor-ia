"""Template registry — load, register, list, and look up memory templates."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memoria.templates.schema import MemoryTemplate

log = logging.getLogger(__name__)


class TemplateRegistry:
    """Central registry for memory templates.

    Built-in templates are loaded on first access via :meth:`_ensure_builtins`.
    Custom templates can be registered with :meth:`register`.
    """

    def __init__(self) -> None:
        self._templates: dict[str, MemoryTemplate] = {}
        self._builtins_loaded = False

    def _ensure_builtins(self) -> None:
        if self._builtins_loaded:
            return
        from memoria.templates.builtins import BUILTIN_TEMPLATES
        for tmpl in BUILTIN_TEMPLATES:
            self._templates[tmpl.name] = tmpl
        self._builtins_loaded = True
        log.debug("Loaded %d built-in templates", len(BUILTIN_TEMPLATES))

    def register(self, template: MemoryTemplate) -> None:
        """Register a custom template (overwrites if name exists)."""
        self._ensure_builtins()
        self._templates[template.name] = template
        log.info("Registered template: %s", template.name)

    def get(self, name: str) -> MemoryTemplate | None:
        """Look up a template by name."""
        self._ensure_builtins()
        return self._templates.get(name)

    def list(self, *, category: str | None = None) -> list[dict]:
        """Return metadata for all templates, optionally filtered by category."""
        self._ensure_builtins()
        out = []
        for t in self._templates.values():
            if category and t.category != category:
                continue
            out.append({
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "fields": len(t.fields),
                "tags": t.tags,
                "builtin": t.builtin,
            })
        return sorted(out, key=lambda x: x["name"])

    def unregister(self, name: str) -> bool:
        """Remove a template. Returns True if removed, False if not found."""
        self._ensure_builtins()
        if name in self._templates:
            if self._templates[name].builtin:
                log.warning("Removing built-in template: %s", name)
            del self._templates[name]
            return True
        return False

    @property
    def count(self) -> int:
        self._ensure_builtins()
        return len(self._templates)
