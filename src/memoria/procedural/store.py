"""Procedural memory storage — tool patterns, workflow templates, and skill tracking."""

from __future__ import annotations

import time
import uuid
from collections import Counter
from typing import Optional

from .types import (
    Procedure,
    ProcedureStatus,
    ToolPattern,
    WorkflowStep,
    WorkflowTemplate,
)

_MAX_RECENT_SEQUENCE = 100


def _word_overlap(a: str, b: str) -> float:
    """Return word-overlap ratio between two strings."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a and not words_b:
        return 0.0
    return len(words_a & words_b) / max(len(words_a), len(words_b), 1)


def _generate_id() -> str:
    return uuid.uuid4().hex[:12]


class ProceduralMemory:
    """Learned behaviors, tool patterns, and workflow templates.

    Supports:
    - Recording tool usage patterns (what tool, what context, success/fail)
    - Learning workflow templates from repeated sequences
    - Skill acquisition tracking (observation → learning → mastered)
    - Pattern-based auto-suggestions ("you usually do X here")
    - Procedure retrieval by context matching
    """

    def __init__(
        self,
        min_observations: int = 3,
        confidence_threshold: float = 0.7,
    ) -> None:
        self._tool_patterns: dict[str, list[ToolPattern]] = {}
        self._workflows: dict[str, WorkflowTemplate] = {}
        self._procedures: dict[str, Procedure] = {}
        self._recent_tool_sequence: list[dict] = []
        self._min_observations = min_observations
        self._confidence_threshold = confidence_threshold

    # ── Tool Pattern Learning ──────────────────────────────────────────

    def record_tool_use(
        self,
        tool_name: str,
        input_data: str,
        result: str,
        success: bool = True,
        context: str = "",
        duration_ms: float = 0,
    ) -> ToolPattern:
        """Record a tool use and update/create patterns."""
        patterns = self._tool_patterns.setdefault(tool_name, [])

        # Find matching pattern via word overlap on input_template
        matched: Optional[ToolPattern] = None
        best_overlap = 0.0
        for p in patterns:
            overlap = _word_overlap(p.input_template, input_data)
            if overlap > 0.3 and overlap > best_overlap:
                best_overlap = overlap
                matched = p

        if matched is not None:
            matched.update_stats(success, duration_ms)
            if context and not matched.context_trigger:
                matched.context_trigger = context
            if not success and result and result not in matched.common_errors:
                matched.common_errors.append(result)
                if len(matched.common_errors) > 50:
                    matched.common_errors = matched.common_errors[-50:]
            pattern = matched
        else:
            pattern = ToolPattern(
                tool_name=tool_name,
                pattern_id=_generate_id(),
                input_template=input_data,
                context_trigger=context,
                success_rate=1.0 if success else 0.0,
                use_count=1,
                avg_duration_ms=duration_ms,
            )
            if not success and result:
                pattern.common_errors.append(result)
            patterns.append(pattern)

        # Track recent sequence for workflow detection
        self._recent_tool_sequence.append(
            {
                "tool_name": tool_name,
                "input_data": input_data,
                "context": context,
                "success": success,
                "timestamp": time.time(),
            }
        )
        if len(self._recent_tool_sequence) > _MAX_RECENT_SEQUENCE:
            self._recent_tool_sequence = self._recent_tool_sequence[
                -_MAX_RECENT_SEQUENCE:
            ]

        return pattern

    def get_tool_patterns(self, tool_name: str) -> list[ToolPattern]:
        """Get all learned patterns for a tool."""
        return list(self._tool_patterns.get(tool_name, []))

    def suggest_tool(self, context: str) -> Optional[ToolPattern]:
        """Suggest the best tool pattern for the given context."""
        if not context:
            return None

        best: Optional[ToolPattern] = None
        best_score = 0.0

        for patterns in self._tool_patterns.values():
            for p in patterns:
                if not p.context_trigger:
                    continue
                overlap = _word_overlap(context, p.context_trigger)
                if overlap <= 0:
                    continue
                score = overlap * p.success_rate
                if score > best_score and p.success_rate >= self._confidence_threshold:
                    best_score = score
                    best = p

        return best

    # ── Workflow Learning ──────────────────────────────────────────────

    def detect_workflow(self, min_length: int = 2) -> Optional[WorkflowTemplate]:
        """Detect repeated tool sequences and create workflow template.

        Only counts contiguous, non-overlapping occurrences to avoid
        false positives from patterns scattered across unrelated contexts.
        """
        if len(self._recent_tool_sequence) < min_length * 2:
            return None

        tool_names = [e["tool_name"] for e in self._recent_tool_sequence]

        for length in range(min(len(tool_names) // 2, 10), min_length - 1, -1):
            for start in range(len(tool_names) - length + 1):
                subseq = tool_names[start : start + length]
                # Count non-overlapping occurrences and track positions
                positions: list[int] = []
                i = 0
                while i <= len(tool_names) - length:
                    if tool_names[i : i + length] == subseq:
                        positions.append(i)
                        i += length
                    else:
                        i += 1

                if len(positions) < self._min_observations:
                    continue

                # Verify at least min_observations contiguous occurrences
                # (consecutive positions where next == prev + length)
                max_contiguous = 1
                current_run = 1
                for j in range(1, len(positions)):
                    if positions[j] == positions[j - 1] + length:
                        current_run += 1
                        max_contiguous = max(max_contiguous, current_run)
                    else:
                        current_run = 1

                if max_contiguous < self._min_observations:
                    continue

                # Check if we already have this workflow
                subseq_key = "→".join(subseq)
                for wf in self._workflows.values():
                    existing_key = "→".join(s.tool_name for s in wf.steps)
                    if existing_key == subseq_key:
                        return wf

                steps = [
                    WorkflowStep(
                        step_index=idx,
                        tool_name=name,
                        description=f"Step {idx + 1}: {name}",
                    )
                    for idx, name in enumerate(subseq)
                ]
                wf = WorkflowTemplate(
                    workflow_id=_generate_id(),
                    name=f"auto-{subseq_key}",
                    description=f"Auto-detected workflow: {subseq_key}",
                    steps=steps,
                    success_count=max_contiguous,
                )
                self._workflows[wf.workflow_id] = wf
                return wf

        return None

    def add_workflow(
        self,
        name: str,
        steps: list[dict],
        description: str = "",
        trigger_context: str = "",
        tags: list[str] | None = None,
    ) -> WorkflowTemplate:
        """Manually register a workflow template."""
        workflow_steps = [
            WorkflowStep(
                step_index=i,
                tool_name=s.get("tool_name", ""),
                description=s.get("description", ""),
                input_template=s.get("input_template", ""),
                expected_output=s.get("expected_output", ""),
                is_optional=s.get("is_optional", False),
                condition=s.get("condition", ""),
            )
            for i, s in enumerate(steps)
        ]

        wf = WorkflowTemplate(
            workflow_id=_generate_id(),
            name=name,
            description=description,
            steps=workflow_steps,
            trigger_context=trigger_context,
            tags=tags or [],
        )
        self._workflows[wf.workflow_id] = wf
        return wf

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowTemplate]:
        """Get a workflow by ID."""
        return self._workflows.get(workflow_id)

    def find_workflows(
        self,
        context: str = "",
        tags: list[str] | None = None,
    ) -> list[WorkflowTemplate]:
        """Find relevant workflows by context or tags."""
        results: list[tuple[float, WorkflowTemplate]] = []

        for wf in self._workflows.values():
            score = 0.0

            if context and wf.trigger_context:
                score += _word_overlap(context, wf.trigger_context)

            if tags:
                tag_set = set(tags)
                wf_tag_set = set(wf.tags)
                if tag_set & wf_tag_set:
                    score += len(tag_set & wf_tag_set) / max(
                        len(tag_set), len(wf_tag_set), 1
                    )

            if score > 0:
                results.append((score, wf))

        results.sort(key=lambda x: x[0], reverse=True)
        return [wf for _, wf in results]

    def update_workflow_outcome(self, workflow_id: str, success: bool) -> None:
        """Record workflow execution outcome."""
        wf = self._workflows.get(workflow_id)
        if wf is None:
            return
        if success:
            wf.success_count += 1
        else:
            wf.fail_count += 1
        wf.last_used = time.time()

    # ── Procedure Management ───────────────────────────────────────────

    def register_procedure(
        self,
        name: str,
        description: str,
        related_tools: list[str] | None = None,
        preconditions: list[str] | None = None,
        postconditions: list[str] | None = None,
    ) -> Procedure:
        """Register a new procedure (skill)."""
        proc = Procedure(
            procedure_id=_generate_id(),
            name=name,
            description=description,
            related_tools=related_tools or [],
            preconditions=preconditions or [],
            postconditions=postconditions or [],
        )
        self._procedures[proc.procedure_id] = proc
        return proc

    def observe_procedure(self, procedure_id: str) -> None:
        """Record an observation of a procedure being used."""
        proc = self._procedures.get(procedure_id)
        if proc is None:
            return
        proc.observation_count += 1
        if (
            proc.observation_count >= self._min_observations
            and proc.status == ProcedureStatus.LEARNING
        ):
            proc.status = ProcedureStatus.LEARNED

    def execute_procedure(self, procedure_id: str, success: bool = True) -> None:
        """Record a procedure execution."""
        proc = self._procedures.get(procedure_id)
        if proc is None:
            return
        proc.execution_count += 1
        proc.last_executed = time.time()
        if success:
            proc.success_count += 1
        if proc.execution_count > 0:
            proc.confidence = max(0.0, min(1.0, proc.success_count / proc.execution_count))

    def get_procedure(self, procedure_id: str) -> Optional[Procedure]:
        """Get a procedure by ID."""
        return self._procedures.get(procedure_id)

    def list_procedures(
        self, status: Optional[ProcedureStatus] = None
    ) -> list[Procedure]:
        """List procedures, optionally filtered by status."""
        procs = list(self._procedures.values())
        if status is not None:
            procs = [p for p in procs if p.status == status]
        return procs

    def suggest_procedure(self, context: str) -> Optional[Procedure]:
        """Suggest a relevant procedure for the context."""
        if not context:
            return None

        best: Optional[Procedure] = None
        best_score = 0.0

        for proc in self._procedures.values():
            if proc.status in (ProcedureStatus.DEPRECATED, ProcedureStatus.FAILED):
                continue
            desc_overlap = _word_overlap(context, proc.description)
            name_overlap = _word_overlap(context, proc.name)
            score = max(desc_overlap, name_overlap)
            if score > best_score:
                best_score = score
                best = proc

        return best if best_score > 0 else None

    # ── Statistics ─────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Return procedural memory statistics."""
        status_counts: dict[str, int] = Counter()
        for proc in self._procedures.values():
            status_counts[proc.status.value] += 1

        # Top tools by total use_count
        tool_uses: list[tuple[str, int]] = []
        for tool_name, patterns in self._tool_patterns.items():
            total = sum(p.use_count for p in patterns)
            tool_uses.append((tool_name, total))
        tool_uses.sort(key=lambda x: x[1], reverse=True)

        return {
            "total_tool_patterns": sum(
                len(p) for p in self._tool_patterns.values()
            ),
            "tools_tracked": list(self._tool_patterns.keys()),
            "total_workflows": len(self._workflows),
            "total_procedures": len(self._procedures),
            "procedures_by_status": dict(status_counts),
            "top_tools": tool_uses[:10],
        }

    # ── Maintenance ────────────────────────────────────────────────────

    def deprecate_stale(self, max_age_days: int = 90) -> int:
        """Mark patterns/procedures not used in *max_age_days* as deprecated."""
        cutoff = time.time() - (max_age_days * 86400)
        count = 0

        for patterns in self._tool_patterns.values():
            for p in patterns:
                if p.last_used < cutoff and p.use_count > 0:
                    p.use_count = 0
                    count += 1

        for proc in self._procedures.values():
            if proc.status in (ProcedureStatus.DEPRECATED, ProcedureStatus.FAILED):
                continue
            last_active = max(proc.last_executed, proc.created_at)
            if last_active < cutoff:
                proc.status = ProcedureStatus.DEPRECATED
                count += 1

        return count
