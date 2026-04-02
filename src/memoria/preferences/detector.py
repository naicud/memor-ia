"""Preference detection from user interactions."""
from __future__ import annotations

import re
import time

from .types import (
    Preference,
    PreferenceCategory,
    PreferenceEvidence,
    PreferenceSource,
)


class PreferenceDetector:
    """Automatically detects user preferences from interaction data."""

    EXPLICIT_PATTERNS: list[tuple[str, str]] = [
        (r"(?:i\s+)?prefer\s+(\w+(?:\s+\w+)?)", "extract_preference"),
        (r"use\s+(\w+(?:\s+\w+)?)\s+instead\s+of", "extract_preference"),
        (r"(?:i\s+)?(?:like|love|enjoy)\s+using?\s+(\w+(?:\s+\w+)?)", "extract_preference"),
        (r"always\s+use\s+(\w+(?:\s+\w+)?)", "extract_preference"),
        (r"(?:switch|move)\s+to\s+(\w+(?:\s+\w+)?)", "extract_preference"),
    ]

    KNOWN_LANGUAGES = {
        "python", "javascript", "typescript", "java", "go", "rust", "ruby",
        "swift", "kotlin", "c++", "c#", "php", "scala", "elixir", "haskell",
        "zig", "dart", "lua",
    }
    KNOWN_FRAMEWORKS = {
        "react", "vue", "angular", "svelte", "next.js", "django", "flask",
        "fastapi", "express", "nestjs", "spring", "rails", "laravel", "gin",
        "actix", "phoenix", "tailwind", "pytorch", "tensorflow",
    }
    KNOWN_TOOLS = {
        "git", "docker", "kubernetes", "npm", "yarn", "pip", "cargo",
        "postgres", "redis", "mongodb", "mysql", "aws", "gcp", "azure",
        "terraform", "vscode", "vim", "neovim", "emacs",
    }
    KNOWN_STYLES = {
        "snake_case", "camelcase", "pascalcase", "tabs", "spaces",
        "2-spaces", "4-spaces", "semicolons", "no-semicolons",
        "single-quotes", "double-quotes",
    }
    KNOWN_WORKFLOWS = {
        "tdd", "bdd", "pair-programming", "code-review", "ci-cd",
        "trunk-based", "gitflow", "feature-branches", "monorepo",
    }

    _ALL_KNOWN: dict[str, PreferenceCategory] = {
        **{v: PreferenceCategory.LANGUAGE for v in KNOWN_LANGUAGES},
        **{v: PreferenceCategory.FRAMEWORK for v in KNOWN_FRAMEWORKS},
        **{v: PreferenceCategory.TOOL for v in KNOWN_TOOLS},
        **{v: PreferenceCategory.STYLE for v in KNOWN_STYLES},
        **{v: PreferenceCategory.WORKFLOW for v in KNOWN_WORKFLOWS},
    }

    def __init__(self) -> None:
        pass

    def detect_from_message(
        self, user_id: str, message: str, timestamp: float = 0.0,
    ) -> list[Preference]:
        """Detect preferences from a user message."""
        if not message or not user_id:
            return []

        ts = timestamp or time.time()
        results: list[Preference] = []
        seen: set[str] = set()

        # Explicit patterns
        for pattern, _ in self.EXPLICIT_PATTERNS:
            for m in re.finditer(pattern, message, re.IGNORECASE):
                value = m.group(1).strip()
                if not value or value.lower() in seen:
                    continue
                seen.add(value.lower())
                category = self._categorize(value)
                pref_id = self._generate_id(user_id, category, value.lower())
                results.append(Preference(
                    preference_id=pref_id,
                    user_id=user_id,
                    category=category,
                    key=category.value,
                    value=value.lower(),
                    confidence=0.6,
                    observation_count=1,
                    evidence=[PreferenceEvidence(
                        source=PreferenceSource.EXPLICIT,
                        signal=message,
                        timestamp=ts,
                    )],
                    created_at=ts,
                    updated_at=ts,
                ))

        # Implicit detection — scan for known vocabulary not yet captured
        words = set(re.findall(r'\b[\w.#+\-]+\b', message.lower()))

        for word in words:
            if word in seen:
                continue
            if word in self._ALL_KNOWN:
                seen.add(word)
                category = self._ALL_KNOWN[word]
                pref_id = self._generate_id(user_id, category, word)
                results.append(Preference(
                    preference_id=pref_id,
                    user_id=user_id,
                    category=category,
                    key=category.value,
                    value=word,
                    confidence=0.3,
                    observation_count=1,
                    evidence=[PreferenceEvidence(
                        source=PreferenceSource.IMPLICIT,
                        signal=message,
                        timestamp=ts,
                    )],
                    created_at=ts,
                    updated_at=ts,
                ))

        return results

    def detect_from_code(
        self, user_id: str, code: str, language: str = "",
        timestamp: float = 0.0,
    ) -> list[Preference]:
        """Detect style preferences from code."""
        if not code or not user_id:
            return []

        ts = timestamp or time.time()
        results: list[Preference] = []
        seen_keys: set[str] = set()

        def _add(key: str, value: str) -> None:
            if key in seen_keys:
                return
            seen_keys.add(key)
            pref_id = self._generate_id(user_id, PreferenceCategory.STYLE, key)
            results.append(Preference(
                preference_id=pref_id,
                user_id=user_id,
                category=PreferenceCategory.STYLE,
                key=key,
                value=value,
                confidence=0.4,
                observation_count=1,
                evidence=[PreferenceEvidence(
                    source=PreferenceSource.IMPLICIT,
                    signal="detected from code",
                    timestamp=ts,
                )],
                created_at=ts,
                updated_at=ts,
            ))

        # Indentation
        indent_matches = re.findall(r'^( +)\S', code, re.MULTILINE)
        if indent_matches:
            first_indent = len(indent_matches[0])
            if first_indent == 2:
                _add("indentation", "2-spaces")
            elif first_indent == 4:
                _add("indentation", "4-spaces")
        elif re.search(r'^\t+\S', code, re.MULTILINE):
            _add("indentation", "tabs")

        # Naming convention
        identifiers = re.findall(r'\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b', code)
        camel_ids = re.findall(r'\b([a-z][a-z0-9]*(?:[A-Z][a-z0-9]*)+)\b', code)
        if identifiers and len(identifiers) > len(camel_ids):
            _add("naming", "snake_case")
        elif camel_ids and len(camel_ids) > len(identifiers):
            _add("naming", "camelCase")

        # Quotes
        single_quotes = len(re.findall(r"'[^']*'", code))
        double_quotes = len(re.findall(r'"[^"]*"', code))
        if single_quotes > double_quotes and single_quotes > 0:
            _add("quotes", "single-quotes")
        elif double_quotes > single_quotes and double_quotes > 0:
            _add("quotes", "double-quotes")

        # Semicolons
        lines = code.strip().split('\n')
        semicolon_lines = sum(1 for l in lines if l.rstrip().endswith(';'))
        if semicolon_lines > len(lines) * 0.5:
            _add("semicolons", "semicolons")
        elif len(lines) > 2 and semicolon_lines == 0:
            _add("semicolons", "no-semicolons")

        # Type annotations (Python-style)
        if re.search(r'def\s+\w+\([^)]*:\s*\w+', code) or re.search(r'->\s*\w+', code):
            _add("type_annotations", "yes")

        return results

    def detect_from_choice(
        self, user_id: str, chosen: str, alternatives: list[str],
        category: PreferenceCategory = PreferenceCategory.TOOL,
        timestamp: float = 0.0,
    ) -> Preference:
        """Record an explicit choice the user made."""
        if not user_id or not chosen:
            raise ValueError("user_id and chosen must be non-empty")
        ts = timestamp or time.time()
        chosen_lower = chosen.lower().strip()
        alt_str = ", ".join(alternatives) if alternatives else "none"
        pref_id = self._generate_id(user_id, category, chosen_lower)

        return Preference(
            preference_id=pref_id,
            user_id=user_id,
            category=category,
            key=category.value,
            value=chosen_lower,
            confidence=0.7,
            observation_count=1,
            evidence=[PreferenceEvidence(
                source=PreferenceSource.EXPLICIT,
                signal=f"chose {chosen} over {alt_str}",
                timestamp=ts,
            )],
            created_at=ts,
            updated_at=ts,
        )

    def _categorize(self, value: str) -> PreferenceCategory:
        """Determine the category of a detected preference value."""
        v = value.lower().strip()
        if v in self.KNOWN_LANGUAGES:
            return PreferenceCategory.LANGUAGE
        if v in self.KNOWN_FRAMEWORKS:
            return PreferenceCategory.FRAMEWORK
        if v in self.KNOWN_TOOLS:
            return PreferenceCategory.TOOL
        if v in self.KNOWN_STYLES:
            return PreferenceCategory.STYLE
        if v in self.KNOWN_WORKFLOWS:
            return PreferenceCategory.WORKFLOW
        return PreferenceCategory.TOOL

    def _generate_id(
        self, user_id: str, category: PreferenceCategory, key: str,
    ) -> str:
        """Generate deterministic preference ID."""
        return f"pref-{user_id}-{category.value}-{key}"
