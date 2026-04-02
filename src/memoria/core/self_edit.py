"""Self-editing memory — agent-driven memory management.

Implements Letta-style agentic memory where the agent can:
- Keep: Mark memories as important
- Discard: Delete irrelevant memories
- Compress: Summarize and replace verbose memories
- Promote: Move memories to higher tiers
- Budget: Manage total memory within limits
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class EditAction(str, Enum):
    KEEP = "keep"
    DISCARD = "discard"
    COMPRESS = "compress"
    PROMOTE = "promote"
    DEMOTE = "demote"
    MERGE = "merge"


@dataclass
class EditDecision:
    """A decision about what to do with a memory."""

    memory_id: str
    action: EditAction
    reason: str = ""
    new_content: str = ""  # For compress/merge
    target_tier: str = ""  # For promote/demote
    confidence: float = 0.5
    merged_ids: list[str] = field(default_factory=list)  # For merge: all source IDs


@dataclass
class MemoryBudget:
    """Budget constraints for memory management."""

    max_working_memories: int = 50
    max_recall_memories: int = 500
    max_archival_memories: int = 5000
    max_total_tokens: int = 100000
    compress_threshold: float = 0.85
    forget_threshold: float = 0.95


class SelfEditingMemory:
    """Agent-driven memory management with budget constraints.

    The agent can make explicit decisions about its own memories,
    or the system can make automatic decisions based on importance
    scores and budget constraints.
    """

    def __init__(self, budget: Optional[MemoryBudget] = None):
        self._budget = budget or MemoryBudget()
        self._edit_history: list[EditDecision] = []
        self._max_edit_history = 500

    # -- Explicit edits ------------------------------------------------------

    def keep(self, memory_id: str, reason: str = "") -> EditDecision:
        """Mark a memory as important (boost importance)."""
        decision = EditDecision(
            memory_id=memory_id,
            action=EditAction.KEEP,
            reason=reason,
            confidence=1.0,
        )
        self._record(decision)
        return decision

    def discard(self, memory_id: str, reason: str = "") -> EditDecision:
        """Mark a memory for deletion."""
        decision = EditDecision(
            memory_id=memory_id,
            action=EditAction.DISCARD,
            reason=reason,
            confidence=1.0,
        )
        self._record(decision)
        return decision

    def compress(
        self, memory_id: str, new_content: str, reason: str = ""
    ) -> EditDecision:
        """Replace a memory with a compressed version."""
        decision = EditDecision(
            memory_id=memory_id,
            action=EditAction.COMPRESS,
            reason=reason,
            new_content=new_content,
            confidence=0.8,
        )
        self._record(decision)
        return decision

    def promote(
        self, memory_id: str, target_tier: str, reason: str = ""
    ) -> EditDecision:
        """Move a memory to a higher tier."""
        decision = EditDecision(
            memory_id=memory_id,
            action=EditAction.PROMOTE,
            reason=reason,
            target_tier=target_tier,
            confidence=0.7,
        )
        self._record(decision)
        return decision

    def demote(
        self, memory_id: str, target_tier: str, reason: str = ""
    ) -> EditDecision:
        """Move a memory to a lower tier."""
        decision = EditDecision(
            memory_id=memory_id,
            action=EditAction.DEMOTE,
            reason=reason,
            target_tier=target_tier,
            confidence=0.7,
        )
        self._record(decision)
        return decision

    def merge(
        self, memory_ids: list[str], merged_content: str, reason: str = ""
    ) -> EditDecision:
        """Merge multiple memories into one."""
        if not memory_ids:
            raise ValueError("memory_ids must not be empty")
        decision = EditDecision(
            memory_id=memory_ids[0],
            action=EditAction.MERGE,
            reason=reason,
            new_content=merged_content,
            confidence=0.6,
            merged_ids=list(memory_ids),
        )
        self._record(decision)
        return decision

    # -- Automatic management ------------------------------------------------

    def auto_manage(
        self,
        memories: list[dict[str, Any]],
        importance_scores: dict[str, float],
    ) -> list[EditDecision]:
        """Automatically generate edit decisions based on importance and budget.

        Each memory dict must have at minimum an ``"id"`` key.
        Optional keys: ``"tier"`` (working/recall/archival), ``"token_count"``.

        Steps:
        1. Check budget usage
        2. If over compress_threshold: compress low-importance memories
        3. If over forget_threshold: discard lowest-importance memories
        4. If high-importance in low tier: suggest promotion
        """
        decisions: list[EditDecision] = []

        # Build counts per tier
        tier_counts: Counter[str] = Counter()
        for mem in memories:
            tier_counts[mem.get("tier", "recall")] += 1

        budget_info = self.check_budget(dict(tier_counts))

        # Sort memories by importance ascending (lowest first)
        scored = [
            (mem, importance_scores.get(mem["id"], 0.0)) for mem in memories
        ]
        scored.sort(key=lambda x: x[1])

        action_needed = budget_info.get("action_needed", "none")
        processed_ids: set[str] = set()

        if action_needed == "forget":
            target_removals = self._removals_needed(tier_counts, budget_info)
            for mem, score in scored:
                if target_removals <= 0:
                    break
                if score < 0.15:
                    d = EditDecision(
                        memory_id=mem["id"],
                        action=EditAction.DISCARD,
                        reason=f"auto: importance {score:.3f} below threshold, budget pressure",
                        confidence=0.5,
                    )
                    decisions.append(d)
                    self._record(d)
                    processed_ids.add(mem["id"])
                    target_removals -= 1

        if action_needed in ("compress", "forget"):
            for mem, score in scored:
                if mem["id"] in processed_ids:
                    continue
                if 0.05 <= score < 0.20:
                    d = EditDecision(
                        memory_id=mem["id"],
                        action=EditAction.COMPRESS,
                        reason=f"auto: importance {score:.3f}, budget at compress threshold",
                        confidence=0.4,
                    )
                    decisions.append(d)
                    self._record(d)
                    processed_ids.add(mem["id"])

        # Promotion: high importance in low tier
        for mem, score in scored:
            if mem["id"] in processed_ids:
                continue
            tier = mem.get("tier", "recall")
            if score >= 0.7 and tier in ("recall", "archival"):
                target = "working" if tier == "recall" else "recall"
                d = EditDecision(
                    memory_id=mem["id"],
                    action=EditAction.PROMOTE,
                    reason=f"auto: importance {score:.3f} warrants promotion",
                    target_tier=target,
                    confidence=0.5,
                )
                decisions.append(d)
                self._record(d)
                processed_ids.add(mem["id"])

        return decisions

    def check_budget(self, memory_counts: dict[str, int]) -> dict[str, Any]:
        """Check current budget usage.

        ``memory_counts`` maps tier name to count (e.g. {"working": 30}).
        """
        working = memory_counts.get("working", 0)
        recall = memory_counts.get("recall", 0)
        archival = memory_counts.get("archival", 0)

        def _usage(current: int, maximum: int) -> dict[str, Any]:
            return {
                "current": current,
                "max": maximum,
                "usage": current / maximum if maximum > 0 else 0.0,
            }

        w = _usage(working, self._budget.max_working_memories)
        r = _usage(recall, self._budget.max_recall_memories)
        a = _usage(archival, self._budget.max_archival_memories)

        max_usage = max(w["usage"], r["usage"], a["usage"])

        if max_usage >= self._budget.forget_threshold:
            action = "forget"
        elif max_usage >= self._budget.compress_threshold:
            action = "compress"
        else:
            action = "none"

        return {
            "working": w,
            "recall": r,
            "archival": a,
            "action_needed": action,
        }

    # -- Edit history --------------------------------------------------------

    def get_edit_history(self, limit: int = 50) -> list[EditDecision]:
        """Get recent edit decisions (most recent first)."""
        return list(reversed(self._edit_history[-limit:]))

    def get_edits_for_memory(self, memory_id: str) -> list[EditDecision]:
        """Get all edit decisions for a specific memory."""
        return [d for d in self._edit_history if d.memory_id == memory_id]

    # -- Statistics ----------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        """Return self-edit statistics."""
        action_counts: Counter[str] = Counter()
        for d in self._edit_history:
            action_counts[d.action.value] += 1
        return {
            "total_edits": len(self._edit_history),
            "edits_by_action": dict(action_counts),
            "budget": {
                "max_working_memories": self._budget.max_working_memories,
                "max_recall_memories": self._budget.max_recall_memories,
                "max_archival_memories": self._budget.max_archival_memories,
                "max_total_tokens": self._budget.max_total_tokens,
                "compress_threshold": self._budget.compress_threshold,
                "forget_threshold": self._budget.forget_threshold,
            },
        }

    # -- internal ------------------------------------------------------------

    def _record(self, decision: EditDecision) -> None:
        self._edit_history.append(decision)
        # Rotate: keep only the most recent entries
        if len(self._edit_history) > self._max_edit_history:
            self._edit_history = self._edit_history[-self._max_edit_history :]

    @staticmethod
    def _removals_needed(
        tier_counts: Counter[str], budget_info: dict[str, Any]
    ) -> int:
        """Estimate how many memories to remove to get under forget threshold."""
        removals = 0
        for tier in ("working", "recall", "archival"):
            info = budget_info.get(tier, {})
            usage = info.get("usage", 0.0)
            if usage >= 0.95:
                current = info.get("current", 0)
                maximum = info.get("max", 1)
                target = int(maximum * 0.80)
                removals += max(0, current - target)
        return max(removals, 1)  # at least 1
