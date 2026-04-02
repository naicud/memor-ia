"""MemoryTemplate schema and validation."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FieldSpec:
    """Specification for a single template field."""

    name: str
    type: str = "string"
    required: bool = False
    description: str = ""
    default: str | None = None


@dataclass
class MemoryTemplate:
    """A reusable memory template with field definitions and a content template.

    The *content_template* uses Python ``str.format_map`` placeholders,
    e.g. ``{language}``, ``{framework}``.
    """

    name: str
    description: str
    category: str = "general"
    fields: list[FieldSpec] = field(default_factory=list)
    content_template: str = ""
    tags: list[str] = field(default_factory=list)
    default_tier: str = "working"
    default_importance: float = 0.5
    builtin: bool = False

    def validate(self, data: dict) -> list[str]:
        """Return list of validation errors (empty = valid)."""
        errors: list[str] = []
        for f in self.fields:
            if f.required and f.name not in data:
                errors.append(f"Missing required field: {f.name}")
            if f.name in data and f.type == "string" and not isinstance(data[f.name], str):
                errors.append(f"Field {f.name} must be a string, got {type(data[f.name]).__name__}")
        return errors

    def render(self, data: dict) -> str:
        """Render the content template with the given field data.

        Missing optional fields are replaced with empty strings.
        """
        filled = {}
        for f in self.fields:
            filled[f.name] = data.get(f.name, f.default or "")
        # Also pass through any extra keys
        filled.update({k: v for k, v in data.items() if k not in filled})
        try:
            return self.content_template.format_map(filled)
        except KeyError as e:
            return self.content_template + f"\n[Template render error: missing key {e}]"

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "fields": [
                {
                    "name": f.name,
                    "type": f.type,
                    "required": f.required,
                    "description": f.description,
                    "default": f.default,
                }
                for f in self.fields
            ],
            "content_template": self.content_template,
            "tags": self.tags,
            "default_tier": self.default_tier,
            "default_importance": self.default_importance,
            "builtin": self.builtin,
        }

    @classmethod
    def from_dict(cls, d: dict) -> MemoryTemplate:
        """Deserialize from a dictionary."""
        fields = [
            FieldSpec(
                name=f["name"],
                type=f.get("type", "string"),
                required=f.get("required", False),
                description=f.get("description", ""),
                default=f.get("default"),
            )
            for f in d.get("fields", [])
        ]
        return cls(
            name=d["name"],
            description=d.get("description", ""),
            category=d.get("category", "general"),
            fields=fields,
            content_template=d.get("content_template", ""),
            tags=d.get("tags", []),
            default_tier=d.get("default_tier", "working"),
            default_importance=d.get("default_importance", 0.5),
            builtin=d.get("builtin", False),
        )
