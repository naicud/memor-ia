"""System prompt construction with memory injection.

Builds the system prompt with static/dynamic sections, memory recall,
and git context — matching the TypeScript dynamic boundary pattern.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional, Callable

# Constants matching TypeScript
SYSTEM_PROMPT_DYNAMIC_BOUNDARY = "<!-- DYNAMIC_BOUNDARY -->"


@dataclass
class PromptSection:
    """A section of the system prompt."""

    name: str
    content: str
    priority: int = 0
    cacheable: bool = True


@dataclass
class PromptConfig:
    """Configuration for prompt building."""

    include_memory: bool = True
    include_git_context: bool = True
    include_date: bool = True
    custom_system_prompt: Optional[str] = None
    append_system_prompt: Optional[str] = None
    override_system_prompt: Optional[str] = None
    memory_dir: Optional[str] = None
    cwd: str = "."


class PromptBuilder:
    """Build system prompts with memory injection.

    Prompt structure (matches TypeScript):
    1. Static sections (cacheable across requests)
    2. DYNAMIC_BOUNDARY marker
    3. Dynamic sections (user/session-specific)
       - Memory (MEMORY.md content + type instructions)
       - Git context (branch, status)
       - Date
       - Custom/append prompts
    """

    def __init__(self, config: PromptConfig | None = None):
        self._config = config or PromptConfig()
        self._sections: list[PromptSection] = []
        self._memory_loader: Callable | None = None

    def set_memory_loader(self, loader: Callable) -> None:
        """Set custom memory loader (for injection)."""
        self._memory_loader = loader

    def add_section(self, section: PromptSection) -> None:
        """Add a prompt section."""
        self._sections.append(section)

    def build(self) -> str:
        """Build the complete system prompt."""
        if self._config.override_system_prompt:
            return self._config.override_system_prompt

        parts: list[str] = []

        # Cacheable sections (static)
        cacheable = sorted(
            [s for s in self._sections if s.cacheable],
            key=lambda s: -s.priority,
        )
        for section in cacheable:
            if section.content:
                parts.append(section.content)

        # Dynamic boundary
        parts.append(SYSTEM_PROMPT_DYNAMIC_BOUNDARY)

        # Dynamic sections
        dynamic = sorted(
            [s for s in self._sections if not s.cacheable],
            key=lambda s: -s.priority,
        )
        for section in dynamic:
            if section.content:
                parts.append(section.content)

        # Memory injection
        if self._config.include_memory:
            memory_content = self._load_memory()
            if memory_content:
                parts.append(memory_content)

        # Git context
        if self._config.include_git_context:
            git_ctx = self._get_git_context()
            if git_ctx:
                parts.append(git_ctx)

        # Date
        if self._config.include_date:
            parts.append(f"Current date: {date.today().isoformat()}")

        # Custom append
        if self._config.append_system_prompt:
            parts.append(self._config.append_system_prompt)

        return "\n\n".join(p for p in parts if p)

    def build_memory_prompt(
        self, memory_dir: str, entrypoint_content: str = ""
    ) -> str:
        """Build the memory section of the system prompt.

        Includes:
        1. Memory directory location
        2. Purpose description
        3. Type taxonomy (4 types)
        4. What NOT to save
        5. How to save (2-step process)
        6. When to access
        7. MEMORY.md content (truncated)
        """
        lines = [
            "## Memory System",
            f"Memory directory: {memory_dir}",
            "",
            "You have persistent memory across conversations.",
            "Memory is organized into 4 types:",
            "- **user**: Your role, goals, knowledge, preferences",
            "- **feedback**: Guidance (avoid & keep doing) with Why + How to apply",
            "- **project**: Ongoing work, goals, initiatives (NOT from code/git)",
            "- **reference**: Pointers to external systems",
            "",
            "### Memory Files",
            "Each memory file has frontmatter:",
            "```yaml",
            "---",
            'name: "Display Name"',
            'description: "One-line hook"',
            'type: "user|feedback|project|reference"',
            "---",
            "```",
            "",
            "### What NOT to save",
            "- Information derivable from code or git history",
            "- Temporary debugging notes",
            "- Duplicate information",
            "",
            "### How to save",
            "1. Create/edit memory file with appropriate type",
            "2. Update MEMORY.md index with pointer to new file",
            "",
        ]

        if entrypoint_content:
            lines.extend(
                [
                    "### Current MEMORY.md",
                    "```",
                    entrypoint_content,
                    "```",
                ]
            )

        return "\n".join(lines)

    def _load_memory(self) -> str | None:
        """Load memory content for injection."""
        if self._memory_loader:
            return self._memory_loader()

        if not self._config.memory_dir:
            return None

        # Default: read MEMORY.md
        entrypoint = Path(self._config.memory_dir) / "MEMORY.md"
        if entrypoint.exists():
            content = entrypoint.read_text(errors="replace")
            return self.build_memory_prompt(self._config.memory_dir, content)

        return self.build_memory_prompt(self._config.memory_dir)

    def _get_git_context(self) -> str | None:
        """Get git branch/status context."""
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=self._config.cwd,
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
                return f"Current git branch: {branch}"
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return None


# Convenience
def build_system_prompt(config: PromptConfig | None = None) -> str:
    """Build system prompt with default sections."""
    builder = PromptBuilder(config)
    return builder.build()
