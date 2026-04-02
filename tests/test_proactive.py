"""Tests for the Proactive Intelligence Engine (Layer 5).

Covers: Profiler, PatternAnalyzer, SuggestionEngine, TriggerSystem,
        InsightGenerator, and Memoria integration.
"""

from __future__ import annotations

import time
import pytest
from unittest.mock import MagicMock, patch

from memoria.proactive.profiler import ClientProfile, Profiler
from memoria.proactive.analyzer import Pattern, PatternAnalyzer
from memoria.proactive.suggestions import Suggestion, SuggestionEngine
from memoria.proactive.triggers import Trigger, TriggerSystem
from memoria.proactive.insights import Insight, InsightGenerator


# ===================================================================
# 1. Profiler tests (~12)
# ===================================================================


class TestProfiler:
    """Client profiling tests."""

    def test_create_profile_from_messages(self):
        p = Profiler()
        p.update_from_message("u1", "I'm working with python and django today")
        profile = p.get_profile("u1")
        assert profile.user_id == "u1"
        assert "python" in profile.primary_languages
        assert "django" in profile.primary_frameworks
        assert profile.interaction_count == 1

    def test_detect_tools(self):
        p = Profiler()
        p.update_from_message("u1", "I use docker and git for deployment")
        profile = p.get_profile("u1")
        assert "docker" in profile.preferred_tools
        assert "git" in profile.preferred_tools

    def test_detect_expertise_beginner(self):
        p = Profiler()
        for _ in range(4):
            p.update_from_message("u1", "What is a function? How do I use variables?")
        assert p.detect_expertise("u1") == "beginner"

    def test_detect_expertise_expert(self):
        p = Profiler()
        p.update_from_message("u1", "I need to implement a mutex with coroutine and semaphore")
        p.update_from_message("u1", "The monoid pattern with functor composition")
        p.update_from_message("u1", "Using monad transformers for dependency injection")
        assert p.detect_expertise("u1") == "expert"

    def test_detect_expertise_intermediate_default(self):
        p = Profiler()
        p.update_from_message("u1", "Let me write some code")
        assert p.detect_expertise("u1") == "intermediate"

    def test_track_working_hours(self):
        p = Profiler()
        ts = 1700000000.0  # Some fixed timestamp
        p.update_from_session("u1", {"timestamp": ts, "duration": 30.0})
        profile = p.get_profile("u1")
        assert len(profile.working_hours) > 0
        assert profile.average_session_length == 30.0

    def test_preference_extraction(self):
        p = Profiler()
        p.update_from_message("u1", "I prefer typescript over javascript")
        profile = p.get_profile("u1")
        assert len(profile.preferences) > 0
        assert any("typescript" in v.lower() for v in profile.preferences.values())

    def test_preference_extraction_i_like(self):
        p = Profiler()
        p.update_from_message("u1", "I like using vim for editing")
        profile = p.get_profile("u1")
        assert len(profile.preferences) > 0

    def test_serialize_deserialize_roundtrip(self):
        p = Profiler()
        p.update_from_message("u1", "I use python and docker")
        data = p.serialize("u1")
        assert data["user_id"] == "u1"
        assert "python" in data["primary_languages"]

        p2 = Profiler()
        restored = p2.deserialize(data)
        assert restored.user_id == "u1"
        assert "python" in restored.primary_languages
        assert "docker" in restored.preferred_tools

    def test_multiple_users_isolation(self):
        p = Profiler()
        p.update_from_message("u1", "I use python and react")
        p.update_from_message("u2", "I use rust and angular")

        p1 = p.get_profile("u1")
        p2 = p.get_profile("u2")

        assert "python" in p1.primary_languages
        assert "rust" not in p1.primary_languages
        assert "rust" in p2.primary_languages
        assert "python" not in p2.primary_languages

    def test_session_topics(self):
        p = Profiler()
        p.update_from_session("u1", {
            "timestamp": time.time(),
            "duration": 60.0,
            "topics": ["testing", "CI/CD"],
        })
        profile = p.get_profile("u1")
        assert "testing" in profile.topics_of_interest
        assert "CI/CD" in profile.topics_of_interest

    def test_working_pattern_analysis(self):
        p = Profiler()
        for i in range(5):
            p.update_from_session("u1", {
                "timestamp": 1700000000.0 + i * 3600,
                "duration": 45.0,
            })
        pattern = p.get_working_pattern("u1")
        assert pattern["total_sessions"] == 5
        assert pattern["average_session_length"] == 45.0
        assert len(pattern["peak_hours"]) > 0

    def test_working_pattern_empty(self):
        p = Profiler()
        pattern = p.get_working_pattern("u_new")
        assert pattern["total_sessions"] == 0
        assert pattern["peak_hours"] == []

    def test_role_filtering(self):
        """Only 'user' messages should extract tech terms."""
        p = Profiler()
        p.update_from_message("u1", "python and docker are great", role="assistant")
        profile = p.get_profile("u1")
        assert "python" not in profile.primary_languages
        assert profile.interaction_count == 1


# ===================================================================
# 2. PatternAnalyzer tests (~12)
# ===================================================================


class TestPatternAnalyzer:
    """Pattern detection tests."""

    def test_record_and_detect_query_repetitions(self):
        a = PatternAnalyzer()
        for _ in range(5):
            a.record_query("how to deploy docker")
        patterns = a.detect_repetitions(min_count=3)
        assert len(patterns) >= 1
        assert any(p.pattern_type == "repetition" for p in patterns)

    def test_repetition_below_threshold(self):
        a = PatternAnalyzer()
        a.record_query("unique query 1")
        a.record_query("unique query 2")
        patterns = a.detect_repetitions(min_count=3)
        assert len(patterns) == 0

    def test_action_repetition(self):
        a = PatternAnalyzer()
        for _ in range(4):
            a.record_action("run_tests")
        patterns = a.detect_repetitions(min_count=3)
        assert any("run_tests" in p.description for p in patterns)

    def test_detect_sequences(self):
        a = PatternAnalyzer()
        for _ in range(3):
            a.record_action("edit_file")
            a.record_action("run_tests")
        patterns = a.detect_sequences()
        assert len(patterns) >= 1
        assert any(p.pattern_type == "sequence" for p in patterns)

    def test_sequence_too_short(self):
        a = PatternAnalyzer()
        a.record_action("edit_file")
        patterns = a.detect_sequences(min_length=2)
        assert len(patterns) == 0

    def test_temporal_pattern_detection(self):
        a = PatternAnalyzer()
        import datetime
        base_ts = datetime.datetime(2024, 1, 15, 9, 0, 0).timestamp()
        for i in range(5):
            a.record_action("frontend_work", "react", timestamp=base_ts + i * 60)
        patterns = a.detect_temporal_patterns()
        assert len(patterns) >= 1
        assert any(p.pattern_type == "temporal" for p in patterns)

    def test_detect_all_combines(self):
        a = PatternAnalyzer()
        for _ in range(5):
            a.record_query("deploy to prod")
        for _ in range(3):
            a.record_action("edit_file")
            a.record_action("run_tests")

        all_patterns = a.detect_all()
        types = {p.pattern_type for p in all_patterns}
        assert "repetition" in types
        assert "sequence" in types

    def test_confidence_threshold(self):
        a = PatternAnalyzer()
        for _ in range(3):
            a.record_query("test query")
        a.detect_repetitions(min_count=3)

        high = a.get_patterns(min_confidence=0.9)
        low = a.get_patterns(min_confidence=0.1)
        assert len(low) >= len(high)

    def test_empty_history(self):
        a = PatternAnalyzer()
        assert a.detect_repetitions() == []
        assert a.detect_sequences() == []
        assert a.detect_temporal_patterns() == []
        assert a.detect_all() == []

    def test_get_patterns_empty(self):
        a = PatternAnalyzer()
        assert a.get_patterns() == []

    def test_query_normalisation(self):
        """Queries should be normalised (lowered, stripped) for repetition."""
        a = PatternAnalyzer()
        for _ in range(3):
            a.record_query("  Deploy Docker  ")
        patterns = a.detect_repetitions(min_count=3)
        assert len(patterns) >= 1

    def test_detect_all_deduplicates(self):
        a = PatternAnalyzer()
        for _ in range(5):
            a.record_query("same query")
        result = a.detect_all()
        names = [p.name for p in result]
        assert len(names) == len(set(names))


# ===================================================================
# 3. SuggestionEngine tests (~12)
# ===================================================================


class TestSuggestionEngine:
    """Suggestion generation tests."""

    def _engine_with_patterns(self):
        analyzer = PatternAnalyzer()
        for _ in range(6):
            analyzer.record_query("deploy docker")
        analyzer.detect_repetitions(min_count=3)

        profiler = Profiler()
        profiler.update_from_message("u1", "I use python and docker")

        return SuggestionEngine(profiler=profiler, analyzer=analyzer)

    def test_generate_from_patterns(self):
        engine = self._engine_with_patterns()
        suggestions = engine.generate("u1")
        assert len(suggestions) > 0
        assert any(s.suggestion_type == "automation" for s in suggestions)

    def test_generate_from_profile_growth(self):
        profiler = Profiler()
        profile = profiler.get_profile("u1")
        profile.areas_for_growth = ["kubernetes"]
        profile.interaction_count = 10

        engine = SuggestionEngine(profiler=profiler)
        suggestions = engine.generate("u1")
        assert any("kubernetes" in s.title.lower() for s in suggestions)

    def test_generate_from_profile_beginner(self):
        profiler = Profiler()
        for _ in range(6):
            profiler.update_from_message("u1", "What is a variable? How do I start?")

        engine = SuggestionEngine(profiler=profiler)
        suggestions = engine.generate("u1")
        assert any(s.suggestion_type == "learning" for s in suggestions)

    def test_cooldown_mechanism(self):
        engine = self._engine_with_patterns()
        s1 = engine.generate("u1")
        assert len(s1) > 0

        # Second call within cooldown should filter previously emitted
        s2 = engine.generate("u1")
        # Previously emitted IDs should be filtered
        s1_ids = {s.id for s in s1}
        s2_ids = {s.id for s in s2}
        # Overlap should be empty (cooled down)
        assert len(s1_ids & s2_ids) == 0

    def test_acknowledge(self):
        engine = self._engine_with_patterns()
        suggestions = engine.generate("u1")
        if suggestions:
            sid = suggestions[0].id
            engine.acknowledge(sid, user_id="u1")
            assert engine._emitted["u1"][sid] > 0

    def test_dismiss(self):
        engine = self._engine_with_patterns()
        suggestions = engine.generate("u1")
        if suggestions:
            sid = suggestions[0].id
            engine.dismiss(sid, user_id="u1")
            # Dismissed suggestions never return
            s2 = engine.generate("u1")
            assert all(s.id != sid for s in s2)

    def test_priority_ordering(self):
        engine = self._engine_with_patterns()
        suggestions = engine.generate("u1", limit=10)
        if len(suggestions) >= 2:
            for i in range(len(suggestions) - 1):
                assert suggestions[i].priority >= suggestions[i + 1].priority

    def test_limit_parameter(self):
        engine = self._engine_with_patterns()
        suggestions = engine.generate("u1", limit=1)
        assert len(suggestions) <= 1

    def test_empty_engine(self):
        engine = SuggestionEngine()
        suggestions = engine.generate("u1")
        assert suggestions == []

    def test_generate_with_context_no_pipeline(self):
        engine = SuggestionEngine()
        suggestions = engine.generate("u1", current_context="some context")
        assert isinstance(suggestions, list)

    def test_suggestion_fields(self):
        engine = self._engine_with_patterns()
        suggestions = engine.generate("u1")
        for s in suggestions:
            assert s.id
            assert s.title
            assert s.description
            assert s.suggestion_type in {
                "optimization", "reminder", "learning", "automation", "insight"
            }
            assert 0.0 <= s.priority <= 1.0
            assert s.source

    def test_preference_suggestion(self):
        profiler = Profiler()
        profile = profiler.get_profile("u1")
        profile.preferences = {"vim": "vim"}
        profile.interaction_count = 15

        engine = SuggestionEngine(profiler=profiler)
        suggestions = engine.generate("u1")
        assert any(s.suggestion_type == "insight" for s in suggestions)


# ===================================================================
# 4. TriggerSystem tests (~10)
# ===================================================================


class TestTriggerSystem:
    """Event-driven trigger system tests."""

    def _make_trigger(self, name="test_trigger", event_type="memory.updated"):
        fired = []
        return Trigger(
            name=name,
            event_type=event_type,
            condition=lambda data: data.get("fire", False),
            action=lambda data: fired.append(data),
            cooldown_s=1.0,
        ), fired

    def test_register_unregister(self):
        ts = TriggerSystem()
        t, _ = self._make_trigger()
        ts.register(t)
        assert len(ts.get_active_triggers()) == 1

        ts.unregister("test_trigger")
        assert len(ts.get_active_triggers()) == 0

    def test_evaluate_matching_event(self):
        ts = TriggerSystem()
        t, fired = self._make_trigger()
        ts.register(t)

        result = ts.evaluate("memory.updated", {"fire": True})
        assert "test_trigger" in result
        assert len(fired) == 1

    def test_evaluate_non_matching_condition(self):
        ts = TriggerSystem()
        t, fired = self._make_trigger()
        ts.register(t)

        result = ts.evaluate("memory.updated", {"fire": False})
        assert result == []
        assert len(fired) == 0

    def test_evaluate_wrong_event_type(self):
        ts = TriggerSystem()
        t, fired = self._make_trigger(event_type="agent.spawned")
        ts.register(t)

        result = ts.evaluate("memory.updated", {"fire": True})
        assert result == []

    def test_cooldown_prevents_rapid_refire(self):
        ts = TriggerSystem()
        t, fired = self._make_trigger()
        t.cooldown_s = 9999  # Long cooldown
        ts.register(t)

        ts.evaluate("memory.updated", {"fire": True})
        assert len(fired) == 1

        ts.evaluate("memory.updated", {"fire": True})
        assert len(fired) == 1  # Cooldown blocks second fire

    def test_enable_disable(self):
        ts = TriggerSystem()
        t, fired = self._make_trigger()
        ts.register(t)

        ts.disable("test_trigger")
        ts.evaluate("memory.updated", {"fire": True})
        assert len(fired) == 0

        ts.enable("test_trigger")
        ts.evaluate("memory.updated", {"fire": True})
        assert len(fired) == 1

    def test_fire_history(self):
        ts = TriggerSystem()
        t, _ = self._make_trigger()
        t.cooldown_s = 0
        ts.register(t)

        ts.evaluate("memory.updated", {"fire": True})
        ts.evaluate("memory.updated", {"fire": True})

        history = ts.get_fire_history()
        assert history["test_trigger"] == 2

    def test_repetition_trigger_factory(self):
        t = TriggerSystem.repetition_trigger(threshold=3)
        assert t.name == "builtin_repetition"
        assert t.event_type == "memory.recalled"

        # Simulate counting
        for _ in range(2):
            assert t.condition({"query": "hello"}) is False
        assert t.condition({"query": "hello"}) is True

    def test_idle_trigger_factory(self):
        t = TriggerSystem.idle_trigger(timeout_s=1.0)
        assert t.name == "builtin_idle"
        # First call sets last_activity
        assert t.condition({}) is False

    def test_context_overflow_trigger_factory(self):
        t = TriggerSystem.context_overflow_trigger(threshold=0.8)
        assert t.name == "builtin_context_overflow"
        assert t.condition({"context_usage": 0.9}) is True
        assert t.condition({"context_usage": 0.5}) is False

    def test_message_bus_integration(self):
        from memoria.comms.bus import MessageBus, Event, EventType

        bus = MessageBus()
        ts = TriggerSystem(bus=bus)

        fired = []
        t = Trigger(
            name="bus_trigger",
            event_type=EventType.MEMORY_UPDATED.value,
            condition=lambda data: True,
            action=lambda data: fired.append(data),
            cooldown_s=0,
        )
        ts.register(t)
        ts.start()

        bus.publish(Event(
            type=EventType.MEMORY_UPDATED,
            source="test",
            data={"key": "value"},
        ))

        assert len(fired) == 1
        ts.stop()

    def test_wildcard_event_type(self):
        ts = TriggerSystem()
        fired = []
        t = Trigger(
            name="wildcard",
            event_type="*",
            condition=lambda data: True,
            action=lambda data: fired.append(1),
            cooldown_s=0,
        )
        ts.register(t)
        ts.evaluate("anything.here", {})
        assert len(fired) == 1


# ===================================================================
# 5. InsightGenerator tests (~8)
# ===================================================================


class _FakeKG:
    """Minimal KnowledgeGraph stub for insight tests."""

    def __init__(self, entities=None, relations=None):
        self._entities = entities or []
        self._relations = relations or {}
        self._profiles = {}
        self.is_memory_backend = True

    def stats(self):
        return {"nodes": len(self._entities), "edges": 0}

    def find_entity(self, name):
        if name == "":
            return self._entities
        return [e for e in self._entities if name.lower() in e.get("name", "").lower()]

    def get_related(self, entity_name, rel_type=None, depth=1):
        return self._relations.get(entity_name, [])

    def get_entity_profile(self, name):
        return self._profiles.get(name, {
            "entity": {"name": name},
            "outgoing_relations": [],
            "incoming_relations": [],
            "related_count": 0,
        })


class TestInsightGenerator:
    """Cross-database insight generation tests."""

    def test_hidden_connections(self):
        kg = _FakeKG(
            entities=[
                {"name": "React"},
                {"name": "GraphQL"},
            ],
            relations={
                "React": [{"name": "Frontend"}],
                "GraphQL": [{"name": "Frontend"}],
            },
        )
        gen = InsightGenerator(kg=kg)
        insights = gen.find_hidden_connections("u1")
        assert len(insights) >= 1
        assert any(i.insight_type == "connection" for i in insights)

    def test_no_connections_when_directly_linked(self):
        kg = _FakeKG(
            entities=[
                {"name": "A"},
                {"name": "B"},
            ],
            relations={
                "A": [{"name": "B"}, {"name": "C"}],
                "B": [{"name": "A"}, {"name": "C"}],
            },
        )
        gen = InsightGenerator(kg=kg)
        insights = gen.find_hidden_connections("u1")
        # A and B are directly linked, so no hidden connection
        assert len(insights) == 0

    def test_knowledge_gap_detection(self):
        kg = _FakeKG(entities=[{"name": "Docker"}])
        kg._profiles["Docker"] = {
            "entity": {"name": "Docker"},
            "outgoing_relations": [{"name": "deploy"}],
            "incoming_relations": [],
            "related_count": 1,
        }
        gen = InsightGenerator(kg=kg)
        insights = gen.identify_knowledge_gaps("u1")
        assert len(insights) >= 1
        assert any(i.insight_type == "gap" for i in insights)

    def test_detect_trends_with_temporal(self):
        kg = _FakeKG()
        gen = InsightGenerator(kg=kg)
        with patch("memoria.graph.temporal.get_trending_concepts") as mock_trend:
            mock_trend.return_value = [
                {"name": "React", "interaction_count": 10},
                {"name": "TypeScript", "interaction_count": 8},
            ]
            insights = gen.detect_trends(days=7)
            assert len(insights) >= 1
            assert any(i.insight_type == "trend" for i in insights)

    def test_expertise_map(self):
        kg = _FakeKG(entities=[
            {"name": "Python", "interaction_count": 10},
            {"name": "Rust", "interaction_count": 5},
        ])
        gen = InsightGenerator(kg=kg)
        emap = gen.generate_expertise_map("u1")
        assert "Python" in emap
        assert "Rust" in emap
        assert emap["Python"] >= emap["Rust"]

    def test_generate_all_combines(self):
        kg = _FakeKG(entities=[{"name": "Docker"}])
        kg._profiles["Docker"] = {
            "entity": {"name": "Docker"},
            "outgoing_relations": [{"name": "deploy"}],
            "incoming_relations": [],
            "related_count": 1,
        }
        gen = InsightGenerator(kg=kg)
        all_insights = gen.generate_all("u1")
        assert isinstance(all_insights, list)

    def test_empty_graph_graceful(self):
        gen = InsightGenerator()
        assert gen.find_hidden_connections("u1") == []
        assert gen.identify_knowledge_gaps("u1") == []
        assert gen.detect_trends() == []
        assert gen.generate_expertise_map("u1") == {}
        assert gen.generate_all("u1") == []

    def test_empty_kg_graceful(self):
        kg = _FakeKG(entities=[])
        gen = InsightGenerator(kg=kg)
        assert gen.find_hidden_connections("u1") == []
        assert gen.generate_expertise_map("u1") == {}


# ===================================================================
# 6. Memoria integration tests
# ===================================================================


class TestMemoriaIntegration:
    """Test that proactive methods are wired into the Memoria class."""

    def test_suggest_returns_list(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        result = m.suggest("some context", user_id="u1")
        assert isinstance(result, list)

    def test_profile_returns_client_profile(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        profile = m.profile(user_id="u1")
        assert isinstance(profile, ClientProfile)
        assert profile.user_id == "u1"

    def test_insights_returns_list(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        result = m.insights(user_id="u1")
        assert isinstance(result, list)

    def test_lazy_init_profiler(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        assert not hasattr(m, "_profiler")
        m.profile("u1")
        assert hasattr(m, "_profiler")

    def test_lazy_init_suggestion_engine(self, tmp_path):
        from memoria import Memoria
        m = Memoria(project_dir=str(tmp_path))
        assert not hasattr(m, "_suggestion_engine")
        m.suggest("ctx", user_id="u1")
        assert hasattr(m, "_suggestion_engine")
