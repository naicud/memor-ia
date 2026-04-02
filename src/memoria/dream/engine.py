from __future__ import annotations

import time
import uuid

from .journal import DreamJournal
from .replay import MemoryReplay
from .synthesis import InsightSynthesizer
from .types import (
    ConsolidationAction,
    ConsolidationDecision,
    DreamJournalEntry,
    DreamPhase,
    DreamResult,
    MemoryCandidate,
)


class DreamEngine:
    """Orchestrates memory consolidation cycles — the 'sleep' of the AI agent."""

    def __init__(
        self,
        forget_threshold: float = 0.2,
        compress_threshold: float = 0.4,
        promote_threshold: float = 0.8,
        merge_similarity: float = 0.85,
        max_insights: int = 10,
    ):
        self._forget = forget_threshold
        self._compress = compress_threshold
        self._promote = promote_threshold
        self._merge_sim = merge_similarity
        self._max_insights = max_insights
        self._replay = MemoryReplay()
        self._synthesizer = InsightSynthesizer(max_insights=max_insights)
        self._journal = DreamJournal()

    def dream(
        self, memories: list[MemoryCandidate], scope: str = "recent"
    ) -> DreamResult:
        """Run a complete dream cycle. Returns DreamResult with all actions taken."""
        cycle_id = f"dream-{uuid.uuid4().hex[:8]}"
        start = time.time()
        phases: list[str] = []

        # Phase 1: SCAN
        scanned = self._scan(memories, scope)
        phases.append(DreamPhase.SCAN.value)

        # Phase 2: REPLAY
        scored = self._replay.score_batch(scanned, now=start)
        score_map = {m.memory_id: s for m, s in scored}
        phases.append(DreamPhase.REPLAY.value)

        # Phase 3: CONSOLIDATE
        similar = self._replay.find_similar_pairs(scanned, self._merge_sim)
        decisions = self._consolidate(scored, similar)
        phases.append(DreamPhase.CONSOLIDATE.value)

        # Phase 4: SYNTHESIZE
        insights = self._synthesizer.synthesize(scanned, score_map)
        phases.append(DreamPhase.SYNTHESIZE.value)

        # Phase 5: JOURNAL
        end = time.time()
        tally = self._tally(decisions)
        journal_entry = DreamJournalEntry(
            cycle_id=cycle_id,
            started_at=start,
            completed_at=end,
            phase=DreamPhase.COMPLETE.value,
            memories_scanned=len(scanned),
            decisions=decisions,
            insights=insights,
            stats=tally,
        )
        self._journal.record(journal_entry)
        phases.append(DreamPhase.JOURNAL.value)

        # Phase 6: COMPLETE
        phases.append(DreamPhase.COMPLETE.value)

        return DreamResult(
            cycle_id=cycle_id,
            success=True,
            phases_completed=phases,
            total_scanned=len(scanned),
            promoted=tally.get("promoted", 0),
            compressed=tally.get("compressed", 0),
            forgotten=tally.get("forgotten", 0),
            connected=tally.get("connected", 0),
            merged=tally.get("merged", 0),
            kept=tally.get("kept", 0),
            insights_generated=len(insights),
            duration_seconds=end - start,
            journal_entry=journal_entry,
        )

    def quick_dream(self, memories: list[MemoryCandidate]) -> DreamResult:
        """Abbreviated dream — skip synthesis. For frequent micro-consolidation."""
        cycle_id = f"quick-{uuid.uuid4().hex[:8]}"
        start = time.time()
        phases: list[str] = []

        # SCAN
        scanned = self._scan(memories, "recent")
        phases.append(DreamPhase.SCAN.value)

        # REPLAY
        scored = self._replay.score_batch(scanned, now=start)
        phases.append(DreamPhase.REPLAY.value)

        # CONSOLIDATE
        similar = self._replay.find_similar_pairs(scanned, self._merge_sim)
        decisions = self._consolidate(scored, similar)
        phases.append(DreamPhase.CONSOLIDATE.value)

        # JOURNAL (no synthesis)
        end = time.time()
        tally = self._tally(decisions)
        journal_entry = DreamJournalEntry(
            cycle_id=cycle_id,
            started_at=start,
            completed_at=end,
            phase=DreamPhase.COMPLETE.value,
            memories_scanned=len(scanned),
            decisions=decisions,
            insights=[],
            stats=tally,
        )
        self._journal.record(journal_entry)
        phases.append(DreamPhase.JOURNAL.value)

        phases.append(DreamPhase.COMPLETE.value)

        return DreamResult(
            cycle_id=cycle_id,
            success=True,
            phases_completed=phases,
            total_scanned=len(scanned),
            promoted=tally.get("promoted", 0),
            compressed=tally.get("compressed", 0),
            forgotten=tally.get("forgotten", 0),
            connected=tally.get("connected", 0),
            merged=tally.get("merged", 0),
            kept=tally.get("kept", 0),
            insights_generated=0,
            duration_seconds=end - start,
            journal_entry=journal_entry,
        )

    @property
    def journal(self) -> DreamJournal:
        return self._journal

    # ── private helpers ──────────────────────────────────────────

    def _scan(
        self, memories: list[MemoryCandidate], scope: str
    ) -> list[MemoryCandidate]:
        """Filter memories by scope."""
        if not memories:
            return []
        if scope == "all":
            return list(memories)
        # Default "recent": return all (the caller pre-filters)
        return list(memories)

    def _consolidate(
        self,
        scored: list[tuple[MemoryCandidate, float]],
        similar_pairs: list[tuple[str, str, float]],
    ) -> list[ConsolidationDecision]:
        """Make consolidation decisions based on scores and similarity."""
        decisions: list[ConsolidationDecision] = []
        merged_ids: set[str] = set()

        # Handle merges first
        for id_a, id_b, sim in similar_pairs:
            if id_a not in merged_ids and id_b not in merged_ids:
                decisions.append(
                    ConsolidationDecision(
                        memory_id=id_a,
                        action=ConsolidationAction.MERGE,
                        reason=f"High similarity ({sim:.2f}) with {id_b}",
                        score=sim,
                        merged_with=[id_b],
                    )
                )
                merged_ids.add(id_b)

        for memory, score in scored:
            if memory.memory_id in merged_ids:
                continue

            if score < self._forget:
                decisions.append(
                    ConsolidationDecision(
                        memory_id=memory.memory_id,
                        action=ConsolidationAction.FORGET,
                        reason=f"Score {score:.2f} below forget threshold {self._forget}",
                        score=score,
                    )
                )
            elif score < self._compress:
                decisions.append(
                    ConsolidationDecision(
                        memory_id=memory.memory_id,
                        action=ConsolidationAction.COMPRESS,
                        reason=f"Score {score:.2f} below compress threshold {self._compress}",
                        score=score,
                        new_content=f"[compressed] {memory.content[:50]}",
                    )
                )
            elif score >= self._promote:
                target = (
                    "archival" if memory.tier == "recall" else "recall"
                )
                decisions.append(
                    ConsolidationDecision(
                        memory_id=memory.memory_id,
                        action=ConsolidationAction.PROMOTE,
                        reason=f"Score {score:.2f} above promote threshold {self._promote}",
                        score=score,
                        target_tier=target,
                    )
                )
            else:
                decisions.append(
                    ConsolidationDecision(
                        memory_id=memory.memory_id,
                        action=ConsolidationAction.KEEP,
                        reason=f"Score {score:.2f} within keep range",
                        score=score,
                    )
                )

        return decisions

    @staticmethod
    def _tally(decisions: list[ConsolidationDecision]) -> dict:
        """Count decisions by action type."""
        tally = {
            "promoted": 0,
            "compressed": 0,
            "forgotten": 0,
            "connected": 0,
            "merged": 0,
            "kept": 0,
        }
        for d in decisions:
            key = d.action.value
            if key == "promote":
                tally["promoted"] += 1
            elif key == "compress":
                tally["compressed"] += 1
            elif key == "forget":
                tally["forgotten"] += 1
            elif key == "connect":
                tally["connected"] += 1
            elif key == "merge":
                tally["merged"] += 1
            elif key == "keep":
                tally["kept"] += 1
        return tally
