"""Comprehensive tests for the MEMORIA User DNA module."""

from __future__ import annotations

import copy
import time

import pytest

from memoria.user_dna import (
    CodingStyle,
    CommunicationProfile,
    DNAAnalyzer,
    ExpertiseSnapshot,
    InteractionFingerprint,
    PassiveCollector,
    SessionRhythm,
    UserDNA,
    UserDNAStore,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def collector() -> PassiveCollector:
    return PassiveCollector()


@pytest.fixture()
def analyzer() -> DNAAnalyzer:
    return DNAAnalyzer()


@pytest.fixture()
def store() -> UserDNAStore:
    return UserDNAStore()


@pytest.fixture()
def dna() -> UserDNA:
    return UserDNA(user_id="u1")


# ===================================================================
# 1. TestCodingStyleTypes
# ===================================================================

class TestCodingStyleTypes:
    def test_defaults(self) -> None:
        cs = CodingStyle()
        assert cs.naming_convention == "unknown"
        assert cs.docstring_style == "unknown"
        assert cs.import_style == "unknown"
        assert cs.error_handling == "unknown"
        assert cs.testing_approach == "unknown"
        assert cs.avg_function_length == 0.0
        assert cs.comment_density == 0.0
        assert cs.type_annotation_usage == 0.0
        assert cs.preferred_patterns == []

    def test_mutable_default_independence(self) -> None:
        a = CodingStyle()
        b = CodingStyle()
        a.preferred_patterns.append("factory")
        assert b.preferred_patterns == []

    def test_custom_values(self) -> None:
        cs = CodingStyle(naming_convention="snake_case", avg_function_length=15.5)
        assert cs.naming_convention == "snake_case"
        assert cs.avg_function_length == 15.5


# ===================================================================
# 2. TestCommunicationProfile
# ===================================================================

class TestCommunicationProfile:
    def test_defaults(self) -> None:
        cp = CommunicationProfile()
        assert cp.verbosity == 5.0
        assert cp.formality == 5.0
        assert cp.question_frequency == 0.0
        assert cp.explanation_depth == "medium"
        assert cp.patience_level == 7.0
        assert cp.preferred_language == "en"
        assert cp.uses_emoji is False
        assert cp.prefers_examples is True
        assert cp.frustration_indicators == 0

    def test_custom_values(self) -> None:
        cp = CommunicationProfile(verbosity=9.0, formality=2.0, uses_emoji=True)
        assert cp.verbosity == 9.0
        assert cp.formality == 2.0
        assert cp.uses_emoji is True

    def test_frustration_counter(self) -> None:
        cp = CommunicationProfile()
        cp.frustration_indicators = 3
        assert cp.frustration_indicators == 3


# ===================================================================
# 3. TestExpertiseSnapshot
# ===================================================================

class TestExpertiseSnapshot:
    def test_required_domain(self) -> None:
        es = ExpertiseSnapshot(domain="python")
        assert es.domain == "python"
        assert es.level == 0.0
        assert es.confidence == 0.5
        assert es.growth_rate == 0.0

    def test_growth_tracking(self) -> None:
        es = ExpertiseSnapshot(domain="rust", level=0.3, growth_rate=0.1)
        assert es.growth_rate == 0.1

    def test_timestamps(self) -> None:
        now = time.time()
        es = ExpertiseSnapshot(domain="go", first_seen=now, last_seen=now)
        assert es.first_seen == es.last_seen


# ===================================================================
# 4. TestSessionRhythm
# ===================================================================

class TestSessionRhythm:
    def test_defaults(self) -> None:
        sr = SessionRhythm()
        assert sr.peak_hours == []
        assert sr.avg_session_minutes == 0.0
        assert sr.avg_messages_per_session == 0.0
        assert sr.preferred_session_days == []
        assert sr.context_switch_frequency == 0.0
        assert sr.focus_duration_minutes == 0.0

    def test_peak_hours_list_independence(self) -> None:
        a = SessionRhythm()
        b = SessionRhythm()
        a.peak_hours.append(9)
        assert b.peak_hours == []

    def test_focus_duration(self) -> None:
        sr = SessionRhythm(focus_duration_minutes=45.0)
        assert sr.focus_duration_minutes == 45.0


# ===================================================================
# 5. TestUserDNA
# ===================================================================

class TestUserDNA:
    def test_creation(self) -> None:
        dna = UserDNA(user_id="test-user")
        assert dna.user_id == "test-user"
        assert dna.version == 1
        assert isinstance(dna.coding_style, CodingStyle)
        assert isinstance(dna.communication, CommunicationProfile)
        assert isinstance(dna.rhythm, SessionRhythm)
        assert isinstance(dna.fingerprint, InteractionFingerprint)
        assert dna.expertise == []
        assert dna.raw_signals == []
        assert dna.tags == []

    def test_version_increment(self) -> None:
        dna = UserDNA(user_id="u1")
        dna.version += 1
        assert dna.version == 2

    def test_independent_sub_objects(self) -> None:
        a = UserDNA(user_id="a")
        b = UserDNA(user_id="b")
        a.coding_style.naming_convention = "snake_case"
        assert b.coding_style.naming_convention == "unknown"


# ===================================================================
# 6. TestPassiveCollectorMessages
# ===================================================================

class TestPassiveCollectorMessages:
    def test_basic_message(self, collector: PassiveCollector) -> None:
        sig = collector.collect_from_message("Hello world", timestamp=100.0)
        assert sig["type"] == "message"
        assert sig["role"] == "user"
        assert sig["timestamp"] == 100.0
        assert sig["length"] == 11
        assert sig["has_code"] is False
        assert sig["is_question"] is False

    def test_code_detection(self, collector: PassiveCollector) -> None:
        sig = collector.collect_from_message("def hello():\n    pass")
        assert sig["has_code"] is True

    def test_question_detection(self, collector: PassiveCollector) -> None:
        sig = collector.collect_from_message("How do I fix this?")
        assert sig["is_question"] is True

    def test_not_question(self, collector: PassiveCollector) -> None:
        sig = collector.collect_from_message("Fix the bug please.")
        assert sig["is_question"] is False

    def test_formality_casual(self, collector: PassiveCollector) -> None:
        sig = collector.collect_from_message("don't know, can't do it")
        assert sig["formality_score"] < 5.0

    def test_frustration_detection(self, collector: PassiveCollector) -> None:
        sig = collector.collect_from_message("Why doesn't this work!!! Still not working")
        assert sig["frustration_signals"] >= 2

    def test_no_frustration(self, collector: PassiveCollector) -> None:
        sig = collector.collect_from_message("Please help me understand this concept")
        assert sig["frustration_signals"] == 0

    def test_emoji_detection(self, collector: PassiveCollector) -> None:
        sig = collector.collect_from_message("Great job! 😊")
        assert sig["has_emoji"] is True

    def test_no_emoji(self, collector: PassiveCollector) -> None:
        sig = collector.collect_from_message("Great job!")
        assert sig["has_emoji"] is False

    def test_language_hints_python(self, collector: PassiveCollector) -> None:
        sig = collector.collect_from_message("def compute(self, x):\n    import math")
        assert "python" in sig["language_hints"]

    def test_language_hints_javascript(self, collector: PassiveCollector) -> None:
        sig = collector.collect_from_message("const result = function test() {}")
        assert "javascript" in sig["language_hints"]

    def test_empty_message(self, collector: PassiveCollector) -> None:
        sig = collector.collect_from_message("")
        assert sig["length"] == 0
        assert sig["has_code"] is False

    def test_signal_stored(self, collector: PassiveCollector) -> None:
        collector.collect_from_message("test")
        assert len(collector.get_signals()) == 1


# ===================================================================
# 7. TestPassiveCollectorCode
# ===================================================================

class TestPassiveCollectorCode:
    def test_snake_case_detection(self, collector: PassiveCollector) -> None:
        code = "def my_function():\n    my_var = compute_value()\n"
        sig = collector.collect_from_code(code)
        assert sig["naming_convention"] == "snake_case"

    def test_camel_case_detection(self, collector: PassiveCollector) -> None:
        code = "let myFunction = computeValue();\nlet anotherVar = getValue();\n"
        sig = collector.collect_from_code(code)
        assert sig["naming_convention"] == "camelCase"

    def test_docstring_google(self, collector: PassiveCollector) -> None:
        code = '"""\nSomething.\n\nArgs:\n    x: int\nReturns:\n    str\n"""\ndef foo(): pass'
        sig = collector.collect_from_code(code)
        assert sig["docstring_style"] == "google"

    def test_docstring_sphinx(self, collector: PassiveCollector) -> None:
        code = '"""\n:param x: an int\n:returns: a string\n"""\ndef foo(): pass'
        sig = collector.collect_from_code(code)
        assert sig["docstring_style"] == "sphinx"

    def test_docstring_none(self, collector: PassiveCollector) -> None:
        code = "def foo():\n    pass"
        sig = collector.collect_from_code(code)
        assert sig["docstring_style"] == "none"

    def test_type_hints(self, collector: PassiveCollector) -> None:
        code = "def foo(x: int, y: str) -> bool:\n    return True"
        sig = collector.collect_from_code(code)
        assert sig["type_hint_ratio"] > 0.0

    def test_function_count(self, collector: PassiveCollector) -> None:
        code = "def a():\n    pass\ndef b():\n    pass\ndef c():\n    pass\n"
        sig = collector.collect_from_code(code)
        assert sig["function_count"] == 3

    def test_comment_density(self, collector: PassiveCollector) -> None:
        code = "# comment 1\nx = 1\n# comment 2\ny = 2"
        sig = collector.collect_from_code(code)
        assert sig["comment_density"] == 50.0

    def test_error_handling_try_except(self, collector: PassiveCollector) -> None:
        code = "try:\n    x = 1\nexcept:\n    pass"
        sig = collector.collect_from_code(code)
        assert sig["error_handling"] == "try-except"

    def test_error_handling_assertions(self, collector: PassiveCollector) -> None:
        code = "assert x > 0\nassert y is not None"
        sig = collector.collect_from_code(code)
        assert sig["error_handling"] == "assertions"

    def test_error_handling_mixed(self, collector: PassiveCollector) -> None:
        code = "try:\n    assert x > 0\nexcept:\n    pass"
        sig = collector.collect_from_code(code)
        assert sig["error_handling"] == "mixed"

    def test_empty_code(self, collector: PassiveCollector) -> None:
        sig = collector.collect_from_code("")
        assert sig["type"] == "code"
        assert sig["naming_convention"] == "unknown"

    def test_language_auto_detect(self, collector: PassiveCollector) -> None:
        code = "def foo(self):\n    import os\n    pass"
        sig = collector.collect_from_code(code)
        assert sig["language"] == "python"


# ===================================================================
# 8. TestPassiveCollectorSession
# ===================================================================

class TestPassiveCollectorSession:
    def test_basic_session(self, collector: PassiveCollector) -> None:
        messages = [
            {"content": "hello world"},
            {"content": "how are you"},
        ]
        sig = collector.collect_from_session(messages, duration_minutes=30.0, timestamp=100.0)
        assert sig["type"] == "session"
        assert sig["message_count"] == 2
        assert sig["duration_minutes"] == 30.0
        assert sig["timestamp"] == 100.0

    def test_context_switches(self, collector: PassiveCollector) -> None:
        messages = [
            {"content": "Let us talk about Python decorators"},
            {"content": "Now let me ask about Kubernetes pods and deployments"},
        ]
        sig = collector.collect_from_session(messages)
        assert sig["context_switches"] >= 1

    def test_empty_session(self, collector: PassiveCollector) -> None:
        sig = collector.collect_from_session([])
        assert sig["message_count"] == 0
        assert sig["context_switches"] == 0

    def test_topic_detection(self, collector: PassiveCollector) -> None:
        messages = [
            {"content": "def foo(self):\n    import os"},
        ]
        sig = collector.collect_from_session(messages)
        assert "python" in sig["topics"]


# ===================================================================
# 9. TestPassiveCollectorLimits
# ===================================================================

class TestPassiveCollectorLimits:
    def test_max_signals_cap(self) -> None:
        c = PassiveCollector(max_raw_signals=5)
        for i in range(10):
            c.collect_from_message(f"msg {i}", timestamp=float(i + 1))
        signals = c.get_signals()
        assert len(signals) == 5

    def test_clear_old(self, collector: PassiveCollector) -> None:
        collector.collect_from_message("old", timestamp=10.0)
        collector.collect_from_message("new", timestamp=100.0)
        removed = collector.clear_old(before=50.0)
        assert removed == 1
        assert len(collector.get_signals()) == 1

    def test_clear_old_zero(self, collector: PassiveCollector) -> None:
        collector.collect_from_message("msg", timestamp=10.0)
        removed = collector.clear_old(before=0.0)
        assert removed == 0

    def test_get_signals_since(self, collector: PassiveCollector) -> None:
        collector.collect_from_message("old", timestamp=10.0)
        collector.collect_from_message("mid", timestamp=50.0)
        collector.collect_from_message("new", timestamp=100.0)
        signals = collector.get_signals(since=50.0)
        assert len(signals) == 2


# ===================================================================
# 10. TestDNAAnalyzerCommunication
# ===================================================================

class TestDNAAnalyzerCommunication:
    def test_verbosity_update(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        # Long messages → high verbosity
        signals = [{"type": "message", "length": 500, "formality_score": 5.0, "is_question": False, "frustration_signals": 0, "has_emoji": False, "timestamp": 100.0}]
        analyzer.analyze(dna, signals)
        assert dna.communication.verbosity > 5.0

    def test_formality_update(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        signals = [{"type": "message", "length": 50, "formality_score": 2.0, "is_question": False, "frustration_signals": 0, "has_emoji": False, "timestamp": 100.0}]
        analyzer.analyze(dna, signals)
        assert dna.communication.formality < 5.0

    def test_question_frequency(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        signals = [
            {"type": "message", "length": 20, "formality_score": 5.0, "is_question": True, "frustration_signals": 0, "has_emoji": False, "timestamp": 100.0},
            {"type": "message", "length": 20, "formality_score": 5.0, "is_question": True, "frustration_signals": 0, "has_emoji": False, "timestamp": 101.0},
        ]
        analyzer.analyze(dna, signals)
        assert dna.communication.question_frequency > 0.0

    def test_frustration_accumulates(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        signals = [{"type": "message", "length": 20, "formality_score": 5.0, "is_question": False, "frustration_signals": 3, "has_emoji": False, "timestamp": 100.0}]
        analyzer.analyze(dna, signals)
        assert dna.communication.frustration_indicators == 3
        assert dna.communication.patience_level < 7.0


# ===================================================================
# 11. TestDNAAnalyzerCodingStyle
# ===================================================================

class TestDNAAnalyzerCodingStyle:
    def test_naming_majority_vote(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        signals = [
            {"type": "code", "naming_convention": "snake_case", "timestamp": 1.0},
            {"type": "code", "naming_convention": "snake_case", "timestamp": 2.0},
            {"type": "code", "naming_convention": "camelCase", "timestamp": 3.0},
        ]
        analyzer.analyze(dna, signals)
        assert dna.coding_style.naming_convention == "snake_case"

    def test_docstring_majority_vote(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        signals = [
            {"type": "code", "docstring_style": "google", "timestamp": 1.0},
            {"type": "code", "docstring_style": "google", "timestamp": 2.0},
            {"type": "code", "docstring_style": "sphinx", "timestamp": 3.0},
        ]
        analyzer.analyze(dna, signals)
        assert dna.coding_style.docstring_style == "google"

    def test_error_handling_vote(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        signals = [
            {"type": "code", "error_handling": "try-except", "timestamp": 1.0},
            {"type": "code", "error_handling": "try-except", "timestamp": 2.0},
        ]
        analyzer.analyze(dna, signals)
        assert dna.coding_style.error_handling == "try-except"

    def test_type_annotation_running_avg(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        signals = [{"type": "code", "type_hint_ratio": 0.8, "timestamp": 1.0}]
        analyzer.analyze(dna, signals)
        assert dna.coding_style.type_annotation_usage > 0.0


# ===================================================================
# 12. TestDNAAnalyzerRhythm
# ===================================================================

class TestDNAAnalyzerRhythm:
    def test_session_duration(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        signals = [{"type": "session", "duration_minutes": 60.0, "message_count": 10, "context_switches": 2, "timestamp": 100.0}]
        analyzer.analyze(dna, signals)
        assert dna.rhythm.avg_session_minutes > 0.0

    def test_messages_per_session(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        signals = [{"type": "session", "duration_minutes": 30.0, "message_count": 20, "context_switches": 1, "timestamp": 100.0}]
        analyzer.analyze(dna, signals)
        assert dna.rhythm.avg_messages_per_session > 0.0

    def test_peak_hours(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        signals = [{"type": "session", "duration_minutes": 30.0, "message_count": 5, "context_switches": 0, "timestamp": 100.0}]
        analyzer.analyze(dna, signals)
        assert len(dna.rhythm.peak_hours) >= 1

    def test_context_switch_frequency(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        signals = [{"type": "session", "duration_minutes": 60.0, "message_count": 20, "context_switches": 5, "timestamp": 100.0}]
        analyzer.analyze(dna, signals)
        assert dna.rhythm.context_switch_frequency > 0.0


# ===================================================================
# 13. TestDNAAnalyzerExpertise
# ===================================================================

class TestDNAAnalyzerExpertise:
    def test_new_domain_from_code(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        signals = [{"type": "code", "language": "python", "timestamp": 100.0}]
        analyzer.analyze(dna, signals)
        domains = [e.domain for e in dna.expertise]
        assert "python" in domains

    def test_level_increases(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        for i in range(5):
            signals = [{"type": "code", "language": "python", "timestamp": 100.0 + i}]
            analyzer.analyze(dna, signals)
        py = next(e for e in dna.expertise if e.domain == "python")
        assert py.level > 0.1

    def test_multiple_domains(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        signals = [
            {"type": "code", "language": "python", "timestamp": 100.0},
            {"type": "code", "language": "rust", "timestamp": 101.0},
        ]
        analyzer.analyze(dna, signals)
        domains = {e.domain for e in dna.expertise}
        assert "python" in domains
        assert "rust" in domains

    def test_growth_rate(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        signals = [{"type": "code", "language": "go", "timestamp": 100.0}]
        analyzer.analyze(dna, signals)
        go_exp = next(e for e in dna.expertise if e.domain == "go")
        assert go_exp.growth_rate > 0.0


# ===================================================================
# 14. TestDNAAnalyzerTags
# ===================================================================

class TestDNAAnalyzerTags:
    def test_expert_tag(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        dna.expertise.append(ExpertiseSnapshot(domain="python", level=0.8))
        tags = analyzer.generate_tags(dna)
        assert "python-expert" in tags

    def test_intermediate_tag(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        dna.expertise.append(ExpertiseSnapshot(domain="rust", level=0.4))
        tags = analyzer.generate_tags(dna)
        assert "rust-intermediate" in tags

    def test_verbose_tag(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        dna.communication.verbosity = 8.0
        tags = analyzer.generate_tags(dna)
        assert "verbose" in tags

    def test_concise_tag(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        dna.communication.verbosity = 2.0
        tags = analyzer.generate_tags(dna)
        assert "concise" in tags

    def test_frustrated_tag(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        dna.communication.frustration_indicators = 10
        tags = analyzer.generate_tags(dna)
        assert "frustrated-user" in tags

    def test_night_owl_tag(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        dna.rhythm.peak_hours = [23, 0, 1]
        tags = analyzer.generate_tags(dna)
        assert "night-owl" in tags

    def test_early_bird_tag(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        dna.rhythm.peak_hours = [6, 7]
        tags = analyzer.generate_tags(dna)
        assert "early-bird" in tags

    def test_style_tag(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        dna.coding_style.naming_convention = "snake_case"
        tags = analyzer.generate_tags(dna)
        assert "style-snake_case" in tags

    def test_emoji_user_tag(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        dna.communication.uses_emoji = True
        tags = analyzer.generate_tags(dna)
        assert "emoji-user" in tags


# ===================================================================
# 15. TestDNAAnalyzerFull
# ===================================================================

class TestDNAAnalyzerFull:
    def test_end_to_end_collect_analyze(self) -> None:
        collector = PassiveCollector()
        analyzer = DNAAnalyzer()
        dna = UserDNA(user_id="e2e-user")

        # Collect message signals
        collector.collect_from_message("def hello_world(self):\n    import os", timestamp=100.0)
        collector.collect_from_message("How do I fix this bug?", timestamp=101.0)
        collector.collect_from_message("Thanks! 😊", timestamp=102.0)

        # Collect code signals
        collector.collect_from_code(
            "def my_func(x: int) -> str:\n    # compute result\n    my_var = x + 1\n    return str(my_var)\n",
            timestamp=103.0,
        )

        # Collect session signals
        collector.collect_from_session(
            [{"content": "hello"}, {"content": "world"}],
            duration_minutes=45.0,
            timestamp=104.0,
        )

        signals = collector.get_signals()
        assert len(signals) == 5

        analyzer.analyze(dna, signals)

        assert dna.version == 2
        assert dna.updated_at > 0
        assert len(dna.raw_signals) == 5
        assert len(dna.tags) > 0
        assert dna.fingerprint.total_interactions > 0

    def test_incremental_analysis(self) -> None:
        analyzer = DNAAnalyzer()
        dna = UserDNA(user_id="inc-user")

        # First batch
        signals1 = [{"type": "message", "length": 100, "formality_score": 3.0, "is_question": True, "frustration_signals": 0, "has_emoji": False, "timestamp": 100.0}]
        analyzer.analyze(dna, signals1)
        v1 = dna.version
        verb1 = dna.communication.verbosity

        # Second batch — different style
        signals2 = [{"type": "message", "length": 500, "formality_score": 8.0, "is_question": False, "frustration_signals": 0, "has_emoji": False, "timestamp": 200.0}]
        analyzer.analyze(dna, signals2)

        assert dna.version == v1 + 1
        assert dna.communication.verbosity != verb1

    def test_version_increments(self) -> None:
        analyzer = DNAAnalyzer()
        dna = UserDNA(user_id="ver-user")
        assert dna.version == 1

        signals = [{"type": "message", "length": 50, "formality_score": 5.0, "is_question": False, "frustration_signals": 0, "has_emoji": False, "timestamp": 100.0}]
        analyzer.analyze(dna, signals)
        assert dna.version == 2

        analyzer.analyze(dna, signals)
        assert dna.version == 3


# ===================================================================
# 16. TestUserDNAStore
# ===================================================================

class TestUserDNAStore:
    def test_get_creates_new(self, store: UserDNAStore) -> None:
        dna = store.get("new-user")
        assert dna.user_id == "new-user"
        assert dna.version == 1

    def test_get_returns_same(self, store: UserDNAStore) -> None:
        dna1 = store.get("u1")
        dna2 = store.get("u1")
        assert dna1 is dna2

    def test_save_and_retrieve(self, store: UserDNAStore) -> None:
        dna = store.get("u1")
        dna.version = 2
        dna.communication.verbosity = 9.0
        store.save(dna)
        retrieved = store.get("u1")
        assert retrieved.communication.verbosity == 9.0

    def test_save_creates_snapshot(self, store: UserDNAStore) -> None:
        dna = store.get("u1")
        original_version = dna.version
        dna.version = original_version + 1
        store.save(dna)
        history = store.get_history("u1")
        assert len(history) == 1
        assert history[0].version == original_version

    def test_history_limit(self, store: UserDNAStore) -> None:
        store_small = UserDNAStore(max_snapshots=3)
        dna = store_small.get("u1")
        for i in range(10):
            old_v = dna.version
            dna.version = old_v + 1
            store_small.save(dna)
        history = store_small.get_history("u1")
        assert len(history) <= 3

    def test_stats(self, store: UserDNAStore) -> None:
        store.get("u1")
        store.get("u2")
        s = store.stats()
        assert s["total_users"] == 2
        assert "u1" in s["users"]
        assert "u2" in s["users"]


# ===================================================================
# 17. TestUserDNAStoreExport
# ===================================================================

class TestUserDNAStoreExport:
    def test_export_existing(self, store: UserDNAStore) -> None:
        dna = store.get("u1")
        dna.coding_style.naming_convention = "snake_case"
        exported = store.export("u1")
        assert exported["user_id"] == "u1"
        assert exported["coding_style"]["naming_convention"] == "snake_case"

    def test_export_missing(self, store: UserDNAStore) -> None:
        exported = store.export("nonexistent")
        assert exported == {}

    def test_export_is_dict(self, store: UserDNAStore) -> None:
        store.get("u1")
        exported = store.export("u1")
        assert isinstance(exported, dict)
        assert "version" in exported
        assert "communication" in exported


# ===================================================================
# 18. TestUserDNAStoreCompare
# ===================================================================

class TestUserDNAStoreCompare:
    def test_compare_versions(self, store: UserDNAStore) -> None:
        dna = store.get("u1")
        dna.communication.verbosity = 3.0
        dna.version = 2
        store.save(dna)

        dna.communication.verbosity = 8.0
        dna.version = 3
        store.save(dna)

        result = store.compare("u1", 1, 2)
        assert "changes" in result
        assert len(result["changes"]) > 0

    def test_compare_missing_version(self, store: UserDNAStore) -> None:
        store.get("u1")
        result = store.compare("u1", 1, 999)
        assert "error" in result

    def test_evolution_tracking(self, store: UserDNAStore) -> None:
        analyzer = DNAAnalyzer()
        dna = store.get("u1")

        for i in range(3):
            signals = [{"type": "code", "language": "python", "timestamp": 100.0 + i}]
            analyzer.analyze(dna, signals)
            store.save(dna)

        evolution = store.get_evolution("u1", "python")
        assert len(evolution) >= 1
        # Levels should be non-decreasing
        levels = [e["level"] for e in evolution]
        assert all(levels[i] <= levels[i + 1] for i in range(len(levels) - 1))


# ===================================================================
# 19. TestEdgeCases
# ===================================================================

class TestEdgeCases:
    def test_empty_signals_no_crash(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        result = analyzer.analyze(dna, [])
        assert result.version == 1  # unchanged

    def test_unknown_signal_type(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        signals = [{"type": "alien", "data": "zzz", "timestamp": 100.0}]
        result = analyzer.analyze(dna, signals)
        assert result.version == 2  # still increments

    def test_malformed_signal(self, analyzer: DNAAnalyzer, dna: UserDNA) -> None:
        signals = [{}]
        result = analyzer.analyze(dna, signals)
        assert result is not None

    def test_none_message(self, collector: PassiveCollector) -> None:
        # Should handle None gracefully
        sig = collector.collect_from_message("")
        assert sig["type"] == "message"

    def test_store_unknown_user_evolution(self, store: UserDNAStore) -> None:
        evolution = store.get_evolution("ghost", "python")
        assert evolution == []

    def test_store_unknown_user_history(self, store: UserDNAStore) -> None:
        history = store.get_history("ghost")
        assert history == []

    def test_max_signals_boundary(self) -> None:
        c = PassiveCollector(max_raw_signals=1)
        c.collect_from_message("first", timestamp=1.0)
        c.collect_from_message("second", timestamp=2.0)
        signals = c.get_signals()
        assert len(signals) == 1
        assert signals[0]["timestamp"] == 2.0

    def test_deepcopy_independence(self) -> None:
        dna = UserDNA(user_id="u1")
        dna.expertise.append(ExpertiseSnapshot(domain="py", level=0.5))
        clone = copy.deepcopy(dna)
        clone.expertise[0].level = 1.0
        assert dna.expertise[0].level == 0.5
