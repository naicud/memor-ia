"""Procedural memory data types — tool patterns, workflows, and procedures."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import time


class ProcedureStatus(str, Enum):
    """Lifecycle status of a learned procedure."""

    LEARNING = "learning"
    LEARNED = "learned"
    DEPRECATED = "deprecated"
    FAILED = "failed"


@dataclass
class ToolPattern:
    """A learned pattern of tool usage."""

    tool_name: str
    pattern_id: str
    input_template: str
    context_trigger: str
    success_rate: float = 0.0
    use_count: int = 0
    last_used: float = field(default_factory=time.time)
    avg_duration_ms: float = 0.0
    common_errors: list[str] = field(default_factory=list)

    def update_stats(self, success: bool, duration_ms: float = 0) -> None:
        """Update pattern statistics after a use."""
        self.use_count += 1
        self.last_used = time.time()

        # Running average for success_rate (clamp to guard float drift)
        self.success_rate += (float(success) - self.success_rate) / self.use_count
        self.success_rate = max(0.0, min(1.0, self.success_rate))

        # Running average for duration
        if duration_ms > 0:
            if self.avg_duration_ms == 0:
                self.avg_duration_ms = duration_ms
            else:
                self.avg_duration_ms += (duration_ms - self.avg_duration_ms) / self.use_count


@dataclass
class WorkflowStep:
    """A single step in a workflow template."""

    step_index: int
    tool_name: str
    description: str
    input_template: str = ""
    expected_output: str = ""
    is_optional: bool = False
    condition: str = ""


@dataclass
class WorkflowTemplate:
    """A learned multi-step workflow."""

    workflow_id: str
    name: str
    description: str
    steps: list[WorkflowStep] = field(default_factory=list)
    trigger_context: str = ""
    success_count: int = 0
    fail_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.fail_count
        return self.success_count / total if total > 0 else 0.0

    @property
    def step_count(self) -> int:
        return len(self.steps)


@dataclass
class Procedure:
    """A general learned procedure (skill)."""

    procedure_id: str
    name: str
    description: str
    status: ProcedureStatus = ProcedureStatus.LEARNING
    confidence: float = 0.0
    observation_count: int = 0
    execution_count: int = 0
    success_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_executed: float = 0.0
    preconditions: list[str] = field(default_factory=list)
    postconditions: list[str] = field(default_factory=list)
    related_tools: list[str] = field(default_factory=list)
