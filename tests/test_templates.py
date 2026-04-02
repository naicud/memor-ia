"""Tests for memory templates: schema, registry, builtins, and integration."""
from __future__ import annotations

import pytest

from memoria.templates.builtins import BUILTIN_TEMPLATES
from memoria.templates.registry import TemplateRegistry
from memoria.templates.schema import FieldSpec, MemoryTemplate

# ===================================================================
# FieldSpec
# ===================================================================

class TestFieldSpec:
    def test_defaults(self):
        f = FieldSpec(name="test")
        assert f.type == "string"
        assert not f.required
        assert f.description == ""
        assert f.default is None

    def test_required_field(self):
        f = FieldSpec(name="lang", type="string", required=True, description="Language")
        assert f.required
        assert f.description == "Language"


# ===================================================================
# MemoryTemplate
# ===================================================================

class TestMemoryTemplate:
    def setup_method(self):
        self.tmpl = MemoryTemplate(
            name="test_template",
            description="A test template",
            category="test",
            fields=[
                FieldSpec(name="title", required=True, description="Title"),
                FieldSpec(name="body", description="Body text"),
                FieldSpec(name="priority", default="medium"),
            ],
            content_template="Title: {title}\nBody: {body}\nPriority: {priority}",
            tags=["test"],
        )

    def test_validate_valid_data(self):
        errors = self.tmpl.validate({"title": "Hello", "body": "World"})
        assert errors == []

    def test_validate_missing_required(self):
        errors = self.tmpl.validate({"body": "no title"})
        assert len(errors) == 1
        assert "title" in errors[0]

    def test_validate_wrong_type(self):
        errors = self.tmpl.validate({"title": 123})
        assert len(errors) == 1
        assert "string" in errors[0]

    def test_render(self):
        result = self.tmpl.render({"title": "Hello", "body": "World"})
        assert "Title: Hello" in result
        assert "Body: World" in result
        assert "Priority: medium" in result  # default

    def test_render_missing_optional_uses_default(self):
        result = self.tmpl.render({"title": "Only Title"})
        assert "Title: Only Title" in result
        assert "Priority: medium" in result

    def test_render_extra_keys(self):
        result = self.tmpl.render({"title": "Hi", "extra": "data"})
        assert "Title: Hi" in result

    def test_to_dict(self):
        d = self.tmpl.to_dict()
        assert d["name"] == "test_template"
        assert len(d["fields"]) == 3
        assert d["tags"] == ["test"]

    def test_from_dict_roundtrip(self):
        d = self.tmpl.to_dict()
        restored = MemoryTemplate.from_dict(d)
        assert restored.name == self.tmpl.name
        assert len(restored.fields) == len(self.tmpl.fields)
        assert restored.content_template == self.tmpl.content_template

    def test_from_dict_minimal(self):
        t = MemoryTemplate.from_dict({"name": "minimal"})
        assert t.name == "minimal"
        assert t.fields == []
        assert t.category == "general"


# ===================================================================
# TemplateRegistry
# ===================================================================

class TestTemplateRegistry:
    def test_builtins_loaded(self):
        reg = TemplateRegistry()
        templates = reg.list()
        assert len(templates) >= 10

    def test_get_builtin(self):
        reg = TemplateRegistry()
        tmpl = reg.get("coding_preference")
        assert tmpl is not None
        assert tmpl.name == "coding_preference"
        assert tmpl.builtin is True

    def test_get_nonexistent(self):
        reg = TemplateRegistry()
        assert reg.get("nonexistent") is None

    def test_register_custom(self):
        reg = TemplateRegistry()
        custom = MemoryTemplate(name="custom_test", description="Custom")
        reg.register(custom)
        assert reg.get("custom_test") is not None

    def test_unregister(self):
        reg = TemplateRegistry()
        custom = MemoryTemplate(name="to_remove", description="Temp")
        reg.register(custom)
        assert reg.unregister("to_remove") is True
        assert reg.get("to_remove") is None

    def test_unregister_nonexistent(self):
        reg = TemplateRegistry()
        assert reg.unregister("no_such_template") is False

    def test_list_by_category(self):
        reg = TemplateRegistry()
        dev_templates = reg.list(category="developer")
        assert all(t["category"] == "developer" for t in dev_templates)
        assert len(dev_templates) >= 3  # coding_preference, project_context, api_endpoint

    def test_count(self):
        reg = TemplateRegistry()
        assert reg.count >= 10

    def test_register_overwrites(self):
        reg = TemplateRegistry()
        v1 = MemoryTemplate(name="dup", description="Version 1")
        v2 = MemoryTemplate(name="dup", description="Version 2")
        reg.register(v1)
        reg.register(v2)
        assert reg.get("dup").description == "Version 2"


# ===================================================================
# Built-in templates validation
# ===================================================================

class TestBuiltinTemplates:
    def test_all_have_names(self):
        for t in BUILTIN_TEMPLATES:
            assert t.name, f"Template missing name: {t}"

    def test_all_are_builtin(self):
        for t in BUILTIN_TEMPLATES:
            assert t.builtin is True

    def test_all_have_fields(self):
        for t in BUILTIN_TEMPLATES:
            assert len(t.fields) >= 1, f"{t.name} has no fields"

    def test_all_have_content_template(self):
        for t in BUILTIN_TEMPLATES:
            assert t.content_template, f"{t.name} has no content template"

    def test_all_renderable_with_required(self):
        for t in BUILTIN_TEMPLATES:
            data = {f.name: f"test_{f.name}" for f in t.fields if f.required}
            content = t.render(data)
            assert content, f"{t.name} rendered empty"

    def test_unique_names(self):
        names = [t.name for t in BUILTIN_TEMPLATES]
        assert len(names) == len(set(names))

    def test_exactly_10_builtins(self):
        assert len(BUILTIN_TEMPLATES) == 10


# ===================================================================
# Memoria integration
# ===================================================================

class TestMemoriaTemplateIntegration:
    def test_template_list(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        templates = m.template_list()
        assert len(templates) >= 10
        assert all("name" in t for t in templates)

    def test_template_list_by_category(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        dev = m.template_list(category="developer")
        assert all(t["category"] == "developer" for t in dev)

    def test_template_apply(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        result = m.template_apply(
            "coding_preference",
            {"language": "Python", "framework": "FastAPI"},
            namespace="test",
        )
        assert result["status"] == "created"
        assert result["template"] == "coding_preference"

    def test_template_apply_missing_required(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        result = m.template_apply("coding_preference", {})
        assert "error" in result
        assert "Validation" in result["error"]

    def test_template_apply_nonexistent(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        result = m.template_apply("nonexistent_template", {})
        assert "error" in result

    def test_template_create(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        result = m.template_create(
            name="standup",
            description="Daily standup",
            fields=[
                {"name": "yesterday", "required": True},
                {"name": "today", "required": True},
                {"name": "blockers"},
            ],
            content_template="Yesterday: {yesterday}\nToday: {today}\nBlockers: {blockers}",
            tags=["standup"],
        )
        assert result["status"] == "created"
        assert result["name"] == "standup"
        assert result["fields"] == 3

        # Now use it
        apply_result = m.template_apply(
            "standup",
            {"yesterday": "Fixed bug", "today": "Add feature"},
            namespace="test",
        )
        assert apply_result["status"] == "created"

    def test_template_registry_lazy_init(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        r1 = m._get_template_registry()
        r2 = m._get_template_registry()
        assert r1 is r2
