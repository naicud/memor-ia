"""Tests for the MEMORIA Preference Engine."""
from __future__ import annotations

import time
import pytest

from memoria.preferences import (
    ConflictResolver,
    Preference,
    PreferenceCategory,
    PreferenceConflict,
    PreferenceDetector,
    PreferenceEvidence,
    PreferenceQuery,
    PreferenceSource,
    PreferenceStore,
)


# ── 1. TestPreferenceCategory ──────────────────────────────────────────


class TestPreferenceCategory:
    def test_language_value(self):
        assert PreferenceCategory.LANGUAGE.value == "language"

    def test_framework_value(self):
        assert PreferenceCategory.FRAMEWORK.value == "framework"

    def test_tool_value(self):
        assert PreferenceCategory.TOOL.value == "tool"

    def test_style_value(self):
        assert PreferenceCategory.STYLE.value == "style"

    def test_workflow_value(self):
        assert PreferenceCategory.WORKFLOW.value == "workflow"

    def test_communication_value(self):
        assert PreferenceCategory.COMMUNICATION.value == "communication"

    def test_architecture_value(self):
        assert PreferenceCategory.ARCHITECTURE.value == "architecture"

    def test_testing_value(self):
        assert PreferenceCategory.TESTING.value == "testing"

    def test_environment_value(self):
        assert PreferenceCategory.ENVIRONMENT.value == "environment"

    def test_all_categories_count(self):
        assert len(PreferenceCategory) == 9


# ── 2. TestPreferenceSource ────────────────────────────────────────────


class TestPreferenceSource:
    def test_explicit_value(self):
        assert PreferenceSource.EXPLICIT.value == "explicit"

    def test_implicit_value(self):
        assert PreferenceSource.IMPLICIT.value == "implicit"

    def test_inferred_value(self):
        assert PreferenceSource.INFERRED.value == "inferred"

    def test_corrected_value(self):
        assert PreferenceSource.CORRECTED.value == "corrected"


# ── 3. TestPreferenceEvidence ──────────────────────────────────────────


class TestPreferenceEvidence:
    def test_creation(self):
        ev = PreferenceEvidence(
            source=PreferenceSource.EXPLICIT, signal="user said so",
        )
        assert ev.source == PreferenceSource.EXPLICIT
        assert ev.signal == "user said so"

    def test_defaults(self):
        ev = PreferenceEvidence(source=PreferenceSource.IMPLICIT, signal="x")
        assert ev.timestamp == 0.0
        assert ev.context == ""

    def test_with_context(self):
        ev = PreferenceEvidence(
            source=PreferenceSource.INFERRED, signal="derived",
            timestamp=100.0, context="web project",
        )
        assert ev.context == "web project"
        assert ev.timestamp == 100.0


# ── 4. TestPreference ──────────────────────────────────────────────────


class TestPreference:
    def test_creation(self):
        p = Preference(
            preference_id="pref-u1-tool-docker",
            user_id="u1",
            category=PreferenceCategory.TOOL,
            key="container",
            value="docker",
        )
        assert p.preference_id == "pref-u1-tool-docker"
        assert p.value == "docker"

    def test_default_confidence(self):
        p = Preference(
            preference_id="x", user_id="u1",
            category=PreferenceCategory.TOOL, key="k", value="v",
        )
        assert p.confidence == 0.3

    def test_active_flag_default(self):
        p = Preference(
            preference_id="x", user_id="u1",
            category=PreferenceCategory.TOOL, key="k", value="v",
        )
        assert p.active is True

    def test_evidence_default_empty(self):
        p = Preference(
            preference_id="x", user_id="u1",
            category=PreferenceCategory.TOOL, key="k", value="v",
        )
        assert p.evidence == []


# ── 5. TestPreferenceConflict ──────────────────────────────────────────


class TestPreferenceConflict:
    def test_conflict_creation(self):
        a = Preference("pa", "u1", PreferenceCategory.TOOL, "db", "postgres")
        b = Preference("pb", "u1", PreferenceCategory.TOOL, "db", "mysql")
        c = PreferenceConflict(preference_a=a, preference_b=b)
        assert c.resolution == ""
        assert c.preference_a.value == "postgres"
        assert c.preference_b.value == "mysql"


# ── 6. TestPreferenceQuery ─────────────────────────────────────────────


class TestPreferenceQuery:
    def test_query_construction(self):
        q = PreferenceQuery(user_id="u1", category=PreferenceCategory.LANGUAGE)
        assert q.user_id == "u1"
        assert q.category == PreferenceCategory.LANGUAGE
        assert q.active_only is True

    def test_query_defaults(self):
        q = PreferenceQuery(user_id="u1")
        assert q.category is None
        assert q.key == ""
        assert q.context == ""
        assert q.min_confidence == 0.0


# ── 7. TestPreferenceDetectorExplicit ──────────────────────────────────


class TestPreferenceDetectorExplicit:
    def setup_method(self):
        self.detector = PreferenceDetector()

    def test_prefer_pattern(self):
        prefs = self.detector.detect_from_message("u1", "I prefer Python")
        values = {p.value for p in prefs}
        assert "python" in values

    def test_use_instead_of(self):
        prefs = self.detector.detect_from_message(
            "u1", "use Docker instead of Podman",
        )
        values = {p.value for p in prefs}
        assert "docker" in values

    def test_always_use(self):
        prefs = self.detector.detect_from_message("u1", "I always use vim")
        values = {p.value for p in prefs}
        assert "vim" in values

    def test_explicit_has_higher_confidence(self):
        prefs = self.detector.detect_from_message("u1", "I prefer Python")
        explicit = [p for p in prefs if p.confidence > 0.5]
        assert len(explicit) >= 1

    def test_like_using(self):
        prefs = self.detector.detect_from_message("u1", "I like using rust")
        values = {p.value for p in prefs}
        assert "rust" in values


# ── 8. TestPreferenceDetectorImplicit ──────────────────────────────────


class TestPreferenceDetectorImplicit:
    def setup_method(self):
        self.detector = PreferenceDetector()

    def test_detect_tool_mention(self):
        prefs = self.detector.detect_from_message(
            "u1", "I set up the project with docker and redis",
        )
        values = {p.value for p in prefs}
        assert "docker" in values
        assert "redis" in values

    def test_detect_framework_mention(self):
        prefs = self.detector.detect_from_message(
            "u1", "The frontend uses react with tailwind",
        )
        values = {p.value for p in prefs}
        assert "react" in values
        assert "tailwind" in values

    def test_implicit_lower_confidence(self):
        prefs = self.detector.detect_from_message(
            "u1", "the project uses docker",
        )
        docker_prefs = [p for p in prefs if p.value == "docker"]
        assert docker_prefs
        # Implicit should have lower confidence than explicit
        assert docker_prefs[0].confidence <= 0.5


# ── 9. TestPreferenceDetectorCode ──────────────────────────────────────


class TestPreferenceDetectorCode:
    def setup_method(self):
        self.detector = PreferenceDetector()

    def test_detect_snake_case(self):
        code = """
def my_function():
    some_variable = 1
    another_thing = 2
    return some_variable + another_thing
"""
        prefs = self.detector.detect_from_code("u1", code)
        values = {p.value for p in prefs}
        assert "snake_case" in values

    def test_detect_4_spaces(self):
        code = "def foo():\n    x = 1\n    return x\n"
        prefs = self.detector.detect_from_code("u1", code)
        values = {p.value for p in prefs}
        assert "4-spaces" in values

    def test_detect_2_spaces(self):
        code = "function foo() {\n  const x = 1;\n  return x;\n}\n"
        prefs = self.detector.detect_from_code("u1", code)
        values = {p.value for p in prefs}
        assert "2-spaces" in values

    def test_detect_tabs(self):
        code = "function foo() {\n\tconst x = 1;\n\treturn x;\n}\n"
        prefs = self.detector.detect_from_code("u1", code)
        values = {p.value for p in prefs}
        assert "tabs" in values

    def test_detect_single_quotes(self):
        code = "x = 'hello'\ny = 'world'\nz = 'foo'\n"
        prefs = self.detector.detect_from_code("u1", code)
        values = {p.value for p in prefs}
        assert "single-quotes" in values

    def test_detect_semicolons(self):
        code = "const x = 1;\nconst y = 2;\nconst z = 3;\n"
        prefs = self.detector.detect_from_code("u1", code)
        values = {p.value for p in prefs}
        assert "semicolons" in values

    def test_detect_no_semicolons(self):
        code = "x = 1\ny = 2\nz = 3\n"
        prefs = self.detector.detect_from_code("u1", code)
        values = {p.value for p in prefs}
        assert "no-semicolons" in values

    def test_empty_code_returns_nothing(self):
        prefs = self.detector.detect_from_code("u1", "")
        assert prefs == []


# ── 10. TestPreferenceDetectorChoice ───────────────────────────────────


class TestPreferenceDetectorChoice:
    def setup_method(self):
        self.detector = PreferenceDetector()

    def test_explicit_choice(self):
        pref = self.detector.detect_from_choice(
            "u1", "PostgreSQL", ["MySQL", "SQLite"],
            category=PreferenceCategory.TOOL,
        )
        assert pref.value == "postgresql"
        assert pref.confidence == 0.7

    def test_choice_evidence(self):
        pref = self.detector.detect_from_choice(
            "u1", "React", ["Vue", "Angular"],
            category=PreferenceCategory.FRAMEWORK,
        )
        assert len(pref.evidence) == 1
        assert pref.evidence[0].source == PreferenceSource.EXPLICIT


# ── 11. TestPreferenceDetectorCategorize ───────────────────────────────


class TestPreferenceDetectorCategorize:
    def setup_method(self):
        self.detector = PreferenceDetector()

    def test_categorize_language(self):
        assert self.detector._categorize("python") == PreferenceCategory.LANGUAGE

    def test_categorize_framework(self):
        assert self.detector._categorize("react") == PreferenceCategory.FRAMEWORK

    def test_categorize_tool(self):
        assert self.detector._categorize("docker") == PreferenceCategory.TOOL

    def test_categorize_style(self):
        assert self.detector._categorize("snake_case") == PreferenceCategory.STYLE

    def test_categorize_workflow(self):
        assert self.detector._categorize("tdd") == PreferenceCategory.WORKFLOW

    def test_categorize_unknown_defaults_to_tool(self):
        assert self.detector._categorize("unknownxyz") == PreferenceCategory.TOOL


# ── 12. TestPreferenceStoreBasics ──────────────────────────────────────


class TestPreferenceStoreBasics:
    def setup_method(self):
        self.store = PreferenceStore()

    def test_upsert_and_get(self):
        pref = Preference(
            "pref-u1-tool-docker", "u1", PreferenceCategory.TOOL,
            "tool", "docker", confidence=0.5,
        )
        self.store.upsert(pref)
        result = self.store.get("u1", "pref-u1-tool-docker")
        assert result is not None
        assert result.value == "docker"

    def test_get_nonexistent_returns_none(self):
        assert self.store.get("u1", "nope") is None

    def test_query_by_category(self):
        self.store.upsert(Preference(
            "p1", "u1", PreferenceCategory.LANGUAGE, "language", "python",
        ))
        self.store.upsert(Preference(
            "p2", "u1", PreferenceCategory.TOOL, "tool", "docker",
        ))
        q = PreferenceQuery(user_id="u1", category=PreferenceCategory.LANGUAGE)
        results = self.store.query(q)
        assert len(results) == 1
        assert results[0].value == "python"

    def test_query_sorted_by_confidence(self):
        self.store.upsert(Preference(
            "p1", "u1", PreferenceCategory.TOOL, "tool1", "a", confidence=0.3,
        ))
        self.store.upsert(Preference(
            "p2", "u1", PreferenceCategory.TOOL, "tool2", "b", confidence=0.8,
        ))
        q = PreferenceQuery(user_id="u1")
        results = self.store.query(q)
        assert results[0].confidence >= results[1].confidence

    def test_query_min_confidence(self):
        self.store.upsert(Preference(
            "p1", "u1", PreferenceCategory.TOOL, "t", "a", confidence=0.2,
        ))
        self.store.upsert(Preference(
            "p2", "u1", PreferenceCategory.TOOL, "t2", "b", confidence=0.8,
        ))
        q = PreferenceQuery(user_id="u1", min_confidence=0.5)
        results = self.store.query(q)
        assert len(results) == 1
        assert results[0].value == "b"


# ── 13. TestPreferenceStoreConfidence ──────────────────────────────────


class TestPreferenceStoreConfidence:
    def setup_method(self):
        self.store = PreferenceStore(confidence_growth=0.1, confidence_decay=0.05)

    def test_boost_increases_confidence(self):
        pref = Preference(
            "p1", "u1", PreferenceCategory.TOOL, "t", "docker",
            confidence=0.5,
        )
        self.store.upsert(pref)
        new_conf = self.store.boost("u1", "p1")
        assert new_conf > 0.5

    def test_boost_with_explicit_amount(self):
        pref = Preference(
            "p1", "u1", PreferenceCategory.TOOL, "t", "docker",
            confidence=0.5,
        )
        self.store.upsert(pref)
        new_conf = self.store.boost("u1", "p1", amount=0.2)
        assert abs(new_conf - 0.7) < 0.01

    def test_boost_capped_at_099(self):
        pref = Preference(
            "p1", "u1", PreferenceCategory.TOOL, "t", "docker",
            confidence=0.98,
        )
        self.store.upsert(pref)
        new_conf = self.store.boost("u1", "p1", amount=0.5)
        assert new_conf == 0.99

    def test_boost_nonexistent_returns_zero(self):
        assert self.store.boost("u1", "nope") == 0.0

    def test_decay_reduces_confidence(self):
        pref = Preference(
            "p1", "u1", PreferenceCategory.TOOL, "t", "docker",
            confidence=0.5,
        )
        self.store.upsert(pref)
        self.store.decay_all("u1")
        result = self.store.get("u1", "p1")
        assert result is not None
        assert result.confidence < 0.5

    def test_decay_deactivates_low_confidence(self):
        pref = Preference(
            "p1", "u1", PreferenceCategory.TOOL, "t", "docker",
            confidence=0.04,
        )
        self.store.upsert(pref)
        self.store.decay_all("u1")
        result = self.store.get("u1", "p1")
        assert result is not None
        assert result.active is False

    def test_decay_returns_count(self):
        self.store.upsert(Preference(
            "p1", "u1", PreferenceCategory.TOOL, "t1", "a", confidence=0.5,
        ))
        self.store.upsert(Preference(
            "p2", "u1", PreferenceCategory.TOOL, "t2", "b", confidence=0.5,
        ))
        count = self.store.decay_all("u1")
        assert count == 2

    def test_upsert_same_value_boosts(self):
        pref1 = Preference(
            "p1", "u1", PreferenceCategory.TOOL, "t", "docker",
            confidence=0.5, evidence=[
                PreferenceEvidence(PreferenceSource.EXPLICIT, "first"),
            ],
        )
        self.store.upsert(pref1)
        pref2 = Preference(
            "p1", "u1", PreferenceCategory.TOOL, "t", "docker",
            confidence=0.5, evidence=[
                PreferenceEvidence(PreferenceSource.EXPLICIT, "second"),
            ],
        )
        result = self.store.upsert(pref2)
        assert result.confidence > 0.5
        assert result.observation_count == 2


# ── 14. TestPreferenceStoreTeach ───────────────────────────────────────


class TestPreferenceStoreTeach:
    def setup_method(self):
        self.store = PreferenceStore()

    def test_teach_creates_high_confidence(self):
        pref = self.store.teach(
            "u1", PreferenceCategory.LANGUAGE, "primary", "python",
        )
        assert pref.confidence == 0.9

    def test_teach_is_explicit_source(self):
        pref = self.store.teach(
            "u1", PreferenceCategory.TOOL, "editor", "vim",
        )
        assert pref.evidence[0].source == PreferenceSource.EXPLICIT

    def test_teach_with_context(self):
        pref = self.store.teach(
            "u1", PreferenceCategory.FRAMEWORK, "web", "django",
            context="python web projects",
        )
        assert pref.context == "python web projects"

    def test_teach_stored_and_retrievable(self):
        self.store.teach("u1", PreferenceCategory.TOOL, "db", "postgres")
        result = self.store.get("u1", "pref-u1-tool-db")
        assert result is not None
        assert result.value == "postgres"


# ── 15. TestPreferenceStoreContext ─────────────────────────────────────


class TestPreferenceStoreContext:
    def setup_method(self):
        self.store = PreferenceStore()

    def test_context_match_by_field(self):
        self.store.teach(
            "u1", PreferenceCategory.FRAMEWORK, "web", "django",
            context="web project",
        )
        results = self.store.get_for_context("u1", "building a web project")
        assert len(results) == 1
        assert results[0].value == "django"

    def test_context_match_by_value(self):
        self.store.teach(
            "u1", PreferenceCategory.LANGUAGE, "primary", "python",
        )
        results = self.store.get_for_context("u1", "need to write python code")
        assert len(results) >= 1

    def test_context_match_by_key(self):
        self.store.teach(
            "u1", PreferenceCategory.TOOL, "database", "postgres",
        )
        results = self.store.get_for_context("u1", "which database to use")
        assert len(results) >= 1

    def test_context_respects_min_confidence(self):
        pref = Preference(
            "p1", "u1", PreferenceCategory.TOOL, "editor", "vim",
            confidence=0.1,
        )
        self.store.upsert(pref)
        results = self.store.get_for_context("u1", "editor", min_confidence=0.5)
        assert len(results) == 0


# ── 16. TestPreferenceStoreExport ──────────────────────────────────────


class TestPreferenceStoreExport:
    def setup_method(self):
        self.store = PreferenceStore()

    def test_export_returns_dicts(self):
        self.store.teach("u1", PreferenceCategory.TOOL, "db", "postgres")
        exported = self.store.export("u1")
        assert len(exported) == 1
        assert isinstance(exported[0], dict)

    def test_export_contains_required_keys(self):
        self.store.teach("u1", PreferenceCategory.LANGUAGE, "lang", "python")
        exported = self.store.export("u1")
        d = exported[0]
        for key in [
            "preference_id", "user_id", "category", "key", "value",
            "confidence", "observation_count", "evidence", "active",
        ]:
            assert key in d

    def test_export_category_is_string(self):
        self.store.teach("u1", PreferenceCategory.TOOL, "tool", "docker")
        exported = self.store.export("u1")
        assert exported[0]["category"] == "tool"

    def test_export_empty_user(self):
        exported = self.store.export("nonexistent")
        assert exported == []


# ── 17. TestConflictDetection ──────────────────────────────────────────


class TestConflictDetection:
    def setup_method(self):
        self.resolver = ConflictResolver()

    def test_detect_conflict_same_key_different_value(self):
        a = Preference("pa", "u1", PreferenceCategory.TOOL, "db", "postgres")
        b = Preference("pb", "u1", PreferenceCategory.TOOL, "db", "mysql")
        conflict = self.resolver.detect_conflict(a, b)
        assert conflict is not None
        assert conflict.preference_a.value == "postgres"
        assert conflict.preference_b.value == "mysql"

    def test_no_conflict_same_value(self):
        a = Preference("pa", "u1", PreferenceCategory.TOOL, "db", "postgres")
        b = Preference("pb", "u1", PreferenceCategory.TOOL, "db", "postgres")
        assert self.resolver.detect_conflict(a, b) is None

    def test_no_conflict_different_key(self):
        a = Preference("pa", "u1", PreferenceCategory.TOOL, "db", "postgres")
        b = Preference("pb", "u1", PreferenceCategory.TOOL, "cache", "redis")
        assert self.resolver.detect_conflict(a, b) is None

    def test_no_conflict_different_category(self):
        a = Preference("pa", "u1", PreferenceCategory.LANGUAGE, "lang", "python")
        b = Preference("pb", "u1", PreferenceCategory.TOOL, "lang", "python")
        assert self.resolver.detect_conflict(a, b) is None


# ── 18. TestConflictResolutionConfidence ───────────────────────────────


class TestConflictResolutionConfidence:
    def setup_method(self):
        self.resolver = ConflictResolver()

    def test_higher_confidence_wins(self):
        a = Preference("pa", "u1", PreferenceCategory.TOOL, "db", "postgres", confidence=0.8)
        b = Preference("pb", "u1", PreferenceCategory.TOOL, "db", "mysql", confidence=0.4)
        conflict = PreferenceConflict(preference_a=a, preference_b=b)
        resolved = self.resolver.resolve(conflict, strategy="confidence")
        assert resolved.resolution == "a_wins"

    def test_lower_confidence_loses(self):
        a = Preference("pa", "u1", PreferenceCategory.TOOL, "db", "postgres", confidence=0.3)
        b = Preference("pb", "u1", PreferenceCategory.TOOL, "db", "mysql", confidence=0.9)
        conflict = PreferenceConflict(preference_a=a, preference_b=b)
        resolved = self.resolver.resolve(conflict, strategy="confidence")
        assert resolved.resolution == "b_wins"


# ── 19. TestConflictResolutionRecency ──────────────────────────────────


class TestConflictResolutionRecency:
    def setup_method(self):
        self.resolver = ConflictResolver()

    def test_more_recent_wins(self):
        a = Preference(
            "pa", "u1", PreferenceCategory.TOOL, "db", "postgres",
            updated_at=100.0,
        )
        b = Preference(
            "pb", "u1", PreferenceCategory.TOOL, "db", "mysql",
            updated_at=200.0,
        )
        conflict = PreferenceConflict(preference_a=a, preference_b=b)
        resolved = self.resolver.resolve(conflict, strategy="recency")
        assert resolved.resolution == "b_wins"

    def test_older_loses(self):
        a = Preference(
            "pa", "u1", PreferenceCategory.TOOL, "db", "postgres",
            updated_at=300.0,
        )
        b = Preference(
            "pb", "u1", PreferenceCategory.TOOL, "db", "mysql",
            updated_at=100.0,
        )
        conflict = PreferenceConflict(preference_a=a, preference_b=b)
        resolved = self.resolver.resolve(conflict, strategy="recency")
        assert resolved.resolution == "a_wins"


# ── 20. TestConflictResolutionFrequency ────────────────────────────────


class TestConflictResolutionFrequency:
    def setup_method(self):
        self.resolver = ConflictResolver()

    def test_more_observations_wins(self):
        a = Preference(
            "pa", "u1", PreferenceCategory.TOOL, "db", "postgres",
            observation_count=10,
        )
        b = Preference(
            "pb", "u1", PreferenceCategory.TOOL, "db", "mysql",
            observation_count=2,
        )
        conflict = PreferenceConflict(preference_a=a, preference_b=b)
        resolved = self.resolver.resolve(conflict, strategy="frequency")
        assert resolved.resolution == "a_wins"

    def test_fewer_observations_loses(self):
        a = Preference(
            "pa", "u1", PreferenceCategory.TOOL, "db", "postgres",
            observation_count=1,
        )
        b = Preference(
            "pb", "u1", PreferenceCategory.TOOL, "db", "mysql",
            observation_count=5,
        )
        conflict = PreferenceConflict(preference_a=a, preference_b=b)
        resolved = self.resolver.resolve(conflict, strategy="frequency")
        assert resolved.resolution == "b_wins"

    def test_manual_strategy_unresolved(self):
        a = Preference("pa", "u1", PreferenceCategory.TOOL, "db", "postgres")
        b = Preference("pb", "u1", PreferenceCategory.TOOL, "db", "mysql")
        conflict = PreferenceConflict(preference_a=a, preference_b=b)
        resolved = self.resolver.resolve(conflict, strategy="manual")
        assert resolved.resolution == "unresolved"


# ── 21. TestEndToEnd ───────────────────────────────────────────────────


class TestEndToEnd:
    def test_detect_store_query_flow(self):
        detector = PreferenceDetector()
        store = PreferenceStore()

        # Detect from message
        prefs = detector.detect_from_message(
            "u1", "I prefer Python for backend",
        )
        assert len(prefs) >= 1

        # Store detected preferences
        for p in prefs:
            store.upsert(p)

        # Query
        q = PreferenceQuery(user_id="u1", category=PreferenceCategory.LANGUAGE)
        results = store.query(q)
        python_prefs = [p for p in results if p.value == "python"]
        assert len(python_prefs) >= 1

    def test_detect_conflict_and_resolve(self):
        store = PreferenceStore()
        resolver = ConflictResolver()

        # Teach two conflicting preferences
        pref_a = store.teach("u1", PreferenceCategory.TOOL, "db", "postgres")
        pref_b = Preference(
            "pref-u1-tool-db-alt", "u1", PreferenceCategory.TOOL,
            "db", "mysql", confidence=0.5,
        )
        store.upsert(pref_b)

        # Detect conflict
        conflict = resolver.detect_conflict(pref_a, pref_b)
        assert conflict is not None

        # Resolve
        resolved = resolver.resolve(conflict, strategy="confidence")
        assert resolved.resolution == "a_wins"

    def test_full_lifecycle(self):
        detector = PreferenceDetector()
        store = PreferenceStore()
        resolver = ConflictResolver()

        # Step 1: Detect preferences from messages
        prefs1 = detector.detect_from_message("u1", "I always use docker")
        for p in prefs1:
            store.upsert(p)

        # Step 2: Detect from code
        code_prefs = detector.detect_from_code("u1", "def my_func():\n    x = 1\n")
        for p in code_prefs:
            store.upsert(p)

        # Step 3: Teach explicit preference
        store.teach("u1", PreferenceCategory.LANGUAGE, "primary", "python")

        # Step 4: Boost through repeated observation
        docker_prefs = [p for p in prefs1 if p.value == "docker"]
        if docker_prefs:
            store.boost("u1", docker_prefs[0].preference_id)

        # Step 5: Decay
        store.decay_all("u1")

        # Step 6: Query
        q = PreferenceQuery(user_id="u1", min_confidence=0.1)
        results = store.query(q)
        assert len(results) >= 1

        # Step 7: Export
        exported = store.export("u1")
        assert len(exported) >= 1

        # Step 8: Stats
        s = store.stats()
        assert s["total_preferences"] >= 1
        assert s["users"] == 1


# ── 22. TestEdgeCases ──────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_message(self):
        detector = PreferenceDetector()
        assert detector.detect_from_message("u1", "") == []

    def test_empty_user_id(self):
        detector = PreferenceDetector()
        assert detector.detect_from_message("", "I prefer Python") == []

    def test_empty_code(self):
        detector = PreferenceDetector()
        assert detector.detect_from_code("u1", "") == []

    def test_deactivate(self):
        store = PreferenceStore()
        store.teach("u1", PreferenceCategory.TOOL, "db", "postgres")
        assert store.deactivate("u1", "pref-u1-tool-db") is True
        result = store.get("u1", "pref-u1-tool-db")
        assert result is not None
        assert result.active is False

    def test_deactivate_nonexistent(self):
        store = PreferenceStore()
        assert store.deactivate("u1", "nope") is False

    def test_query_active_only(self):
        store = PreferenceStore()
        store.teach("u1", PreferenceCategory.TOOL, "db", "postgres")
        store.deactivate("u1", "pref-u1-tool-db")
        q = PreferenceQuery(user_id="u1", active_only=True)
        assert len(store.query(q)) == 0
        q2 = PreferenceQuery(user_id="u1", active_only=False)
        assert len(store.query(q2)) == 1

    def test_decay_empty_user(self):
        store = PreferenceStore()
        assert store.decay_all("nobody") == 0

    def test_stats_empty_store(self):
        store = PreferenceStore()
        s = store.stats()
        assert s["total_preferences"] == 0
        assert s["users"] == 0
        assert s["conflicts"] == 0

    def test_resolver_get_conflicts_empty(self):
        resolver = ConflictResolver()
        assert resolver.get_conflicts() == []

    def test_resolver_get_resolved_empty(self):
        resolver = ConflictResolver()
        assert resolver.get_resolved() == []

    def test_unknown_strategy_unresolved(self):
        resolver = ConflictResolver()
        a = Preference("pa", "u1", PreferenceCategory.TOOL, "db", "postgres")
        b = Preference("pb", "u1", PreferenceCategory.TOOL, "db", "mysql")
        conflict = PreferenceConflict(preference_a=a, preference_b=b)
        resolved = resolver.resolve(conflict, strategy="unknown_strategy")
        assert resolved.resolution == "unresolved"

    def test_generate_id_deterministic(self):
        detector = PreferenceDetector()
        id1 = detector._generate_id("u1", PreferenceCategory.TOOL, "docker")
        id2 = detector._generate_id("u1", PreferenceCategory.TOOL, "docker")
        assert id1 == id2
        assert id1 == "pref-u1-tool-docker"

    def test_confidence_never_reaches_one(self):
        store = PreferenceStore(confidence_growth=0.5)
        pref = Preference(
            "p1", "u1", PreferenceCategory.TOOL, "t", "docker",
            confidence=0.95,
        )
        store.upsert(pref)
        for _ in range(20):
            store.boost("u1", "p1")
        result = store.get("u1", "p1")
        assert result is not None
        assert result.confidence <= 0.99

    def test_store_conflicts_from_upsert(self):
        store = PreferenceStore()
        store.teach("u1", PreferenceCategory.TOOL, "db", "postgres")
        pref_b = Preference(
            "pref-u1-tool-db-v2", "u1", PreferenceCategory.TOOL,
            "db", "mysql", confidence=0.5,
        )
        store.upsert(pref_b)
        conflicts = store.get_conflicts()
        assert len(conflicts) >= 1
