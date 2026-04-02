from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DreamPhase(Enum):
    SCAN = "scan"
    REPLAY = "replay"
    CONSOLIDATE = "consolidate"
    SYNTHESIZE = "synthesize"
    JOURNAL = "journal"
    COMPLETE = "complete"


class ConsolidationAction(Enum):
    PROMOTE = "promote"
    COMPRESS = "compress"
    FORGET = "forget"
    CONNECT = "connect"
    MERGE = "merge"
    KEEP = "keep"


@dataclass
class MemoryCandidate:
    """A memory being evaluated during dream."""

    memory_id: str
    content: str
    tier: str = "working"
    importance: float = 0.5
    access_count: int = 0
    last_accessed: float = 0.0
    created_at: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class ConsolidationDecision:
    """Decision made about a memory during consolidation."""

    memory_id: str
    action: ConsolidationAction
    reason: str = ""
    score: float = 0.0
    new_content: str = ""
    target_tier: str = ""
    linked_to: str = ""
    merged_with: list[str] = field(default_factory=list)


@dataclass
class InsightSeed:
    """A potential insight discovered during synthesis."""

    title: str
    description: str
    insight_type: str = "connection"  # connection, pattern, gap, prediction
    confidence: float = 0.5
    source_memories: list[str] = field(default_factory=list)
    suggested_action: str = ""


@dataclass
class DreamJournalEntry:
    """Immutable record of a dream cycle."""

    cycle_id: str
    started_at: float = 0.0
    completed_at: float = 0.0
    phase: str = ""
    memories_scanned: int = 0
    decisions: list[ConsolidationDecision] = field(default_factory=list)
    insights: list[InsightSeed] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


@dataclass
class DreamResult:
    """Complete result of a dream cycle."""

    cycle_id: str
    success: bool = True
    phases_completed: list[str] = field(default_factory=list)
    total_scanned: int = 0
    promoted: int = 0
    compressed: int = 0
    forgotten: int = 0
    connected: int = 0
    merged: int = 0
    kept: int = 0
    insights_generated: int = 0
    duration_seconds: float = 0.0
    journal_entry: DreamJournalEntry | None = None
