"""Tests for memoria.procedural — tool patterns, workflows, and procedures."""

from __future__ import annotations

import time

import pytest

from memoria.procedural.store import ProceduralMemory, _word_overlap
from memoria.procedural.types import (
    Procedure,
    ProcedureStatus,
    ToolPattern,
    WorkflowStep,
    WorkflowTemplate,
)


# ── Helpers ────────────────────────────────────────────────────────────


def _make_memory(**kwargs) -> ProceduralMemory:
    defaults = {"min_observations": 3, "confidence_threshold": 0.7}
    defaults.update(kwargs)
    return ProceduralMemory(**defaults)


# ── ToolPattern dataclass ──────────────────────────────────────────────


class TestToolPattern:
    def test_update_stats_single_success(self) -> None:
        tp = ToolPattern(
            tool_name="grep",
            pattern_id="abc",
            input_template="search file",
            context_trigger="find code",
            success_rate=0.0,
            use_count=0,
        )
        tp.update_stats(success=True, duration_ms=100)
        assert tp.use_count == 1
        assert tp.success_rate == 1.0
        assert tp.avg_duration_ms == 100

    def test_update_stats_running_average(self) -> None:
        tp = ToolPattern(
            tool_name="grep",
            pattern_id="abc",
            input_template="search",
            context_trigger="",
            success_rate=0.0,
            use_count=0,
        )
        tp.update_stats(True, duration_ms=100)
        tp.update_stats(False, duration_ms=200)
        assert tp.use_count == 2
        assert tp.success_rate == pytest.approx(0.5)
        assert tp.avg_duration_ms == pytest.approx(150.0)

    def test_update_stats_no_duration(self) -> None:
        tp = ToolPattern(
            tool_name="bash",
            pattern_id="xyz",
            input_template="run",
            context_trigger="",
        )
        tp.update_stats(True, duration_ms=0)
        assert tp.avg_duration_ms == 0.0


# ── WorkflowTemplate properties ───────────────────────────────────────


class TestWorkflowTemplate:
    def test_success_rate_no_executions(self) -> None:
        wf = WorkflowTemplate(workflow_id="w1", name="test", description="")
        assert wf.success_rate == 0.0

    def test_success_rate_with_data(self) -> None:
        wf = WorkflowTemplate(
            workflow_id="w1",
            name="test",
            description="",
            success_count=7,
            fail_count=3,
        )
        assert wf.success_rate == pytest.approx(0.7)

    def test_step_count(self) -> None:
        wf = WorkflowTemplate(
            workflow_id="w1",
            name="test",
            description="",
            steps=[
                WorkflowStep(0, "a", "step a"),
                WorkflowStep(1, "b", "step b"),
            ],
        )
        assert wf.step_count == 2


# ── Tool pattern recording & matching ──────────────────────────────────


class TestRecordToolUse:
    def test_creates_new_pattern(self) -> None:
        mem = _make_memory()
        p = mem.record_tool_use("grep", "search for auth", "found 3 results")
        assert p.tool_name == "grep"
        assert p.use_count == 1
        assert p.success_rate == 1.0

    def test_matches_existing_pattern(self) -> None:
        mem = _make_memory()
        p1 = mem.record_tool_use("grep", "search for auth code", "ok")
        p2 = mem.record_tool_use("grep", "search for auth logic", "ok")
        # High word overlap → same pattern updated
        assert p1.pattern_id == p2.pattern_id
        assert p1.use_count == 2

    def test_creates_separate_pattern_low_overlap(self) -> None:
        mem = _make_memory()
        p1 = mem.record_tool_use("grep", "search for auth", "ok")
        p2 = mem.record_tool_use("grep", "deploy production server", "ok")
        assert p1.pattern_id != p2.pattern_id
        patterns = mem.get_tool_patterns("grep")
        assert len(patterns) == 2

    def test_records_failure(self) -> None:
        mem = _make_memory()
        p = mem.record_tool_use(
            "bash", "run tests", "exit code 1", success=False
        )
        assert p.success_rate == 0.0
        assert "exit code 1" in p.common_errors

    def test_tracks_context(self) -> None:
        mem = _make_memory()
        p = mem.record_tool_use(
            "grep", "find pattern", "ok", context="debugging error"
        )
        assert p.context_trigger == "debugging error"

    def test_tracks_duration(self) -> None:
        mem = _make_memory()
        p = mem.record_tool_use(
            "bash", "build project", "ok", duration_ms=5000
        )
        assert p.avg_duration_ms == 5000

    def test_recent_sequence_capped(self) -> None:
        mem = _make_memory()
        for i in range(150):
            mem.record_tool_use("tool", f"input {i}", "ok")
        assert len(mem._recent_tool_sequence) == 100


# ── Tool suggestion ────────────────────────────────────────────────────


class TestSuggestTool:
    def test_suggests_matching_pattern(self) -> None:
        mem = _make_memory(confidence_threshold=0.5)
        # Build a pattern with high success rate
        for _ in range(5):
            mem.record_tool_use(
                "grep",
                "search code for bugs",
                "found",
                context="debugging errors in code",
            )
        suggestion = mem.suggest_tool("debugging errors")
        assert suggestion is not None
        assert suggestion.tool_name == "grep"

    def test_returns_none_empty_context(self) -> None:
        mem = _make_memory()
        assert mem.suggest_tool("") is None

    def test_returns_none_no_patterns(self) -> None:
        mem = _make_memory()
        assert mem.suggest_tool("anything") is None

    def test_filters_below_confidence(self) -> None:
        mem = _make_memory(confidence_threshold=0.9)
        # Record with 50% success rate
        mem.record_tool_use("bash", "deploy", "ok", context="deploy app")
        mem.record_tool_use(
            "bash", "deploy", "fail", success=False, context="deploy app"
        )
        suggestion = mem.suggest_tool("deploy app")
        assert suggestion is None


# ── Workflow creation (manual) ─────────────────────────────────────────


class TestAddWorkflow:
    def test_creates_workflow(self) -> None:
        mem = _make_memory()
        wf = mem.add_workflow(
            name="test-deploy",
            steps=[
                {"tool_name": "bash", "description": "build"},
                {"tool_name": "bash", "description": "deploy"},
            ],
            description="Build and deploy",
            trigger_context="deploy to production",
            tags=["deploy"],
        )
        assert wf.name == "test-deploy"
        assert wf.step_count == 2
        assert wf.tags == ["deploy"]

    def test_get_workflow_by_id(self) -> None:
        mem = _make_memory()
        wf = mem.add_workflow("w", [{"tool_name": "bash", "description": "x"}])
        retrieved = mem.get_workflow(wf.workflow_id)
        assert retrieved is not None
        assert retrieved.name == "w"

    def test_get_workflow_missing(self) -> None:
        mem = _make_memory()
        assert mem.get_workflow("nonexistent") is None

    def test_update_workflow_outcome_success(self) -> None:
        mem = _make_memory()
        wf = mem.add_workflow("w", [{"tool_name": "a", "description": "x"}])
        mem.update_workflow_outcome(wf.workflow_id, success=True)
        assert wf.success_count == 1

    def test_update_workflow_outcome_failure(self) -> None:
        mem = _make_memory()
        wf = mem.add_workflow("w", [{"tool_name": "a", "description": "x"}])
        mem.update_workflow_outcome(wf.workflow_id, success=False)
        assert wf.fail_count == 1

    def test_update_workflow_outcome_missing_id(self) -> None:
        mem = _make_memory()
        mem.update_workflow_outcome("nope", success=True)  # no error


# ── Workflow search ────────────────────────────────────────────────────


class TestFindWorkflows:
    def test_find_by_context(self) -> None:
        mem = _make_memory()
        mem.add_workflow(
            "deploy",
            [{"tool_name": "bash", "description": "deploy"}],
            trigger_context="deploy production server",
            tags=["deploy"],
        )
        mem.add_workflow(
            "test",
            [{"tool_name": "pytest", "description": "test"}],
            trigger_context="run test suite",
            tags=["test"],
        )
        results = mem.find_workflows(context="deploy server")
        assert len(results) >= 1
        assert results[0].name == "deploy"

    def test_find_by_tags(self) -> None:
        mem = _make_memory()
        mem.add_workflow(
            "deploy",
            [{"tool_name": "bash", "description": "d"}],
            tags=["deploy", "ci"],
        )
        results = mem.find_workflows(tags=["deploy"])
        assert len(results) == 1
        assert results[0].name == "deploy"

    def test_find_no_match(self) -> None:
        mem = _make_memory()
        mem.add_workflow(
            "deploy",
            [{"tool_name": "bash", "description": "d"}],
            trigger_context="deploy",
        )
        results = mem.find_workflows(context="completely unrelated topic")
        assert len(results) == 0


# ── Workflow auto-detection ────────────────────────────────────────────


class TestDetectWorkflow:
    def test_detects_repeated_sequence(self) -> None:
        mem = _make_memory(min_observations=3)
        # Repeat the same sequence 3 times
        for _ in range(3):
            mem.record_tool_use("grep", "find", "ok")
            mem.record_tool_use("edit", "change", "ok")
        wf = mem.detect_workflow(min_length=2)
        assert wf is not None
        assert wf.step_count == 2

    def test_no_detection_insufficient_repeats(self) -> None:
        mem = _make_memory(min_observations=5)
        for _ in range(2):
            mem.record_tool_use("grep", "find", "ok")
            mem.record_tool_use("edit", "change", "ok")
        wf = mem.detect_workflow(min_length=2)
        assert wf is None

    def test_no_detection_short_sequence(self) -> None:
        mem = _make_memory()
        mem.record_tool_use("grep", "find", "ok")
        assert mem.detect_workflow(min_length=2) is None

    def test_returns_existing_workflow_on_redetect(self) -> None:
        mem = _make_memory(min_observations=2)
        for _ in range(4):
            mem.record_tool_use("grep", "find", "ok")
            mem.record_tool_use("edit", "change", "ok")
        wf1 = mem.detect_workflow(min_length=2)
        wf2 = mem.detect_workflow(min_length=2)
        assert wf1 is not None
        assert wf1.workflow_id == wf2.workflow_id


# ── Procedure lifecycle ────────────────────────────────────────────────


class TestProcedureLifecycle:
    def test_register_procedure(self) -> None:
        mem = _make_memory()
        proc = mem.register_procedure(
            name="code-review",
            description="Review code changes for bugs",
            related_tools=["grep", "view"],
            preconditions=["changes staged"],
            postconditions=["review complete"],
        )
        assert proc.status == ProcedureStatus.LEARNING
        assert proc.name == "code-review"
        assert proc.related_tools == ["grep", "view"]

    def test_observe_transitions_to_learned(self) -> None:
        mem = _make_memory(min_observations=3)
        proc = mem.register_procedure("skill", "do a thing")
        for _ in range(3):
            mem.observe_procedure(proc.procedure_id)
        assert proc.status == ProcedureStatus.LEARNED
        assert proc.observation_count == 3

    def test_observe_stays_learning_below_threshold(self) -> None:
        mem = _make_memory(min_observations=5)
        proc = mem.register_procedure("skill", "do a thing")
        mem.observe_procedure(proc.procedure_id)
        mem.observe_procedure(proc.procedure_id)
        assert proc.status == ProcedureStatus.LEARNING

    def test_observe_missing_procedure(self) -> None:
        mem = _make_memory()
        mem.observe_procedure("nonexistent")  # no error

    def test_execute_updates_confidence(self) -> None:
        mem = _make_memory()
        proc = mem.register_procedure("skill", "do")
        mem.execute_procedure(proc.procedure_id, success=True)
        mem.execute_procedure(proc.procedure_id, success=True)
        mem.execute_procedure(proc.procedure_id, success=False)
        assert proc.execution_count == 3
        assert proc.success_count == 2
        assert proc.confidence == pytest.approx(2 / 3)

    def test_execute_missing_procedure(self) -> None:
        mem = _make_memory()
        mem.execute_procedure("nonexistent")  # no error

    def test_get_procedure(self) -> None:
        mem = _make_memory()
        proc = mem.register_procedure("skill", "desc")
        assert mem.get_procedure(proc.procedure_id) is proc

    def test_get_procedure_missing(self) -> None:
        mem = _make_memory()
        assert mem.get_procedure("nope") is None


# ── Procedure listing & filtering ──────────────────────────────────────


class TestListProcedures:
    def test_list_all(self) -> None:
        mem = _make_memory()
        mem.register_procedure("a", "desc a")
        mem.register_procedure("b", "desc b")
        assert len(mem.list_procedures()) == 2

    def test_filter_by_status(self) -> None:
        mem = _make_memory(min_observations=1)
        p1 = mem.register_procedure("a", "desc a")
        p2 = mem.register_procedure("b", "desc b")
        mem.observe_procedure(p1.procedure_id)
        # p1 is now LEARNED, p2 still LEARNING
        learned = mem.list_procedures(status=ProcedureStatus.LEARNED)
        learning = mem.list_procedures(status=ProcedureStatus.LEARNING)
        assert len(learned) == 1
        assert learned[0].name == "a"
        assert len(learning) == 1


# ── Procedure suggestion ──────────────────────────────────────────────


class TestSuggestProcedure:
    def test_suggests_matching_procedure(self) -> None:
        mem = _make_memory()
        mem.register_procedure("code-review", "Review code changes for quality")
        mem.register_procedure("deploy", "Deploy application to server")
        suggestion = mem.suggest_procedure("review code")
        assert suggestion is not None
        assert suggestion.name == "code-review"

    def test_returns_none_empty_context(self) -> None:
        mem = _make_memory()
        assert mem.suggest_procedure("") is None

    def test_returns_none_no_procedures(self) -> None:
        mem = _make_memory()
        assert mem.suggest_procedure("anything") is None

    def test_skips_deprecated(self) -> None:
        mem = _make_memory()
        proc = mem.register_procedure("old", "old process")
        proc.status = ProcedureStatus.DEPRECATED
        assert mem.suggest_procedure("old process") is None


# ── Statistics ─────────────────────────────────────────────────────────


class TestStats:
    def test_empty_stats(self) -> None:
        mem = _make_memory()
        s = mem.stats()
        assert s["total_tool_patterns"] == 0
        assert s["tools_tracked"] == []
        assert s["total_workflows"] == 0
        assert s["total_procedures"] == 0

    def test_populated_stats(self) -> None:
        mem = _make_memory()
        mem.record_tool_use("grep", "search code", "ok")
        mem.record_tool_use("grep", "search code again", "ok")
        mem.record_tool_use("bash", "run tests", "ok")
        mem.add_workflow("w", [{"tool_name": "a", "description": "x"}])
        mem.register_procedure("p", "desc")
        s = mem.stats()
        assert s["total_tool_patterns"] >= 2
        assert "grep" in s["tools_tracked"]
        assert "bash" in s["tools_tracked"]
        assert s["total_workflows"] == 1
        assert s["total_procedures"] == 1
        assert len(s["top_tools"]) >= 1
        assert s["procedures_by_status"]["learning"] == 1


# ── Stale deprecation ─────────────────────────────────────────────────


class TestDeprecateStale:
    def test_deprecates_old_procedure(self) -> None:
        mem = _make_memory()
        proc = mem.register_procedure("old-skill", "old stuff")
        # Backdate creation
        proc.created_at = time.time() - (100 * 86400)
        count = mem.deprecate_stale(max_age_days=90)
        assert count >= 1
        assert proc.status == ProcedureStatus.DEPRECATED

    def test_keeps_recent_procedure(self) -> None:
        mem = _make_memory()
        proc = mem.register_procedure("new-skill", "new stuff")
        count = mem.deprecate_stale(max_age_days=90)
        assert count == 0
        assert proc.status == ProcedureStatus.LEARNING

    def test_skips_already_deprecated(self) -> None:
        mem = _make_memory()
        proc = mem.register_procedure("dep", "d")
        proc.status = ProcedureStatus.DEPRECATED
        proc.created_at = time.time() - (100 * 86400)
        count = mem.deprecate_stale(max_age_days=90)
        assert count == 0

    def test_deprecates_old_tool_pattern(self) -> None:
        mem = _make_memory()
        p = mem.record_tool_use("grep", "old search", "ok")
        p.last_used = time.time() - (100 * 86400)
        count = mem.deprecate_stale(max_age_days=90)
        assert count >= 1
        assert p.use_count == 0


# ── Word overlap helper ───────────────────────────────────────────────


class TestWordOverlap:
    def test_identical_strings(self) -> None:
        assert _word_overlap("hello world", "hello world") == 1.0

    def test_partial_overlap(self) -> None:
        result = _word_overlap("hello world", "hello there")
        assert 0 < result < 1

    def test_no_overlap(self) -> None:
        assert _word_overlap("hello", "world") == 0.0

    def test_empty_strings(self) -> None:
        assert _word_overlap("", "") == 0.0

    def test_case_insensitive(self) -> None:
        assert _word_overlap("Hello World", "hello world") == 1.0


# ── Edge cases ─────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_get_tool_patterns_unknown_tool(self) -> None:
        mem = _make_memory()
        assert mem.get_tool_patterns("nonexistent") == []

    def test_find_workflows_no_context_no_tags(self) -> None:
        mem = _make_memory()
        mem.add_workflow("w", [{"tool_name": "a", "description": "x"}])
        results = mem.find_workflows()
        assert results == []

    def test_add_workflow_empty_steps(self) -> None:
        mem = _make_memory()
        wf = mem.add_workflow("empty", [])
        assert wf.step_count == 0

    def test_procedure_id_uniqueness(self) -> None:
        mem = _make_memory()
        ids = set()
        for i in range(50):
            proc = mem.register_procedure(f"proc-{i}", f"desc-{i}")
            ids.add(proc.procedure_id)
        assert len(ids) == 50
