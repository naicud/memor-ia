"""Contextual Intelligence Engine — situation awareness."""

import threading
import time
from typing import Any, Optional

from .types import SituationSnapshot, SituationType

_SITUATION_KEYWORDS: dict[SituationType, list[str]] = {
    SituationType.TROUBLESHOOTING: ["debug", "fix", "error", "bug", "issue", "crash", "fail"],
    SituationType.CREATING: ["create", "new", "add", "write", "build", "generate"],
    SituationType.EXPLORING: ["read", "view", "browse", "search", "explore", "find", "look"],
    SituationType.REVIEWING: ["review", "approve", "check", "inspect", "audit", "verify"],
    SituationType.LEARNING: ["learn", "tutorial", "docs", "guide", "help", "example"],
    SituationType.MANAGING: ["manage", "admin", "config", "setting", "deploy", "organize"],
}


class SituationAwareness:
    """Real-time cross-product situation awareness engine."""

    def __init__(
        self,
        max_snapshots: int = 1000,
        idle_threshold_seconds: float = 300.0,
        max_action_buffer: int = 2000,
    ) -> None:
        self._lock = threading.RLock()
        self._snapshots: list[SituationSnapshot] = []
        self._current: Optional[SituationSnapshot] = None
        self._action_buffer: list[tuple[str, str, float]] = []
        self._max_snapshots = max_snapshots
        self._idle_threshold = idle_threshold_seconds
        self._max_action_buffer = max_action_buffer

    def update(
        self,
        product_id: str,
        action: str,
        timestamp: Optional[float] = None,
        context_signals: Optional[dict[str, Any]] = None,
    ) -> SituationSnapshot:
        """Update situation awareness with a new action."""
        ts = timestamp if timestamp is not None else time.time()
        signals = context_signals if context_signals is not None else {}

        with self._lock:
            # Detect idle
            if self._action_buffer:
                last_ts = self._action_buffer[-1][2]
                if (ts - last_ts) > self._idle_threshold:
                    idle_snap = SituationSnapshot(
                        situation_type=SituationType.IDLE,
                        active_products=self._active_products(),
                        current_product=product_id,
                        current_action="",
                        duration_seconds=ts - last_ts,
                        context_signals={},
                        timestamp=last_ts,
                        confidence=0.9,
                    )
                    self._push_snapshot(idle_snap)

            self._action_buffer.append((product_id, action, ts))
            if len(self._action_buffer) > self._max_action_buffer:
                self._action_buffer = self._action_buffer[-self._max_action_buffer:]

            situation_type, confidence = self._classify(action)

            # Duration since last action from this product
            duration = 0.0
            for prod, _, prev_ts in reversed(self._action_buffer[:-1]):
                if prod == product_id:
                    duration = ts - prev_ts
                    break

            snapshot = SituationSnapshot(
                situation_type=situation_type,
                active_products=self._active_products(),
                current_product=product_id,
                current_action=action,
                duration_seconds=duration,
                context_signals=dict(signals),
                timestamp=ts,
                confidence=confidence,
            )
            self._push_snapshot(snapshot)
            self._current = snapshot
            return snapshot

    def get_current_situation(self) -> Optional[SituationSnapshot]:
        with self._lock:
            return self._current

    def get_situation_history(self, limit: int = 20) -> list[SituationSnapshot]:
        with self._lock:
            return list(self._snapshots[-limit:])

    def get_time_in_situation(self, situation_type: SituationType) -> float:
        """Total seconds spent in a given situation type."""
        with self._lock:
            total = 0.0
            for snap in self._snapshots:
                if snap.situation_type == situation_type:
                    total += snap.duration_seconds
            return total

    def get_situation_distribution(self) -> dict[str, float]:
        """Distribution of time across situation types as percentages."""
        with self._lock:
            totals: dict[str, float] = {st.value: 0.0 for st in SituationType}
            grand_total = 0.0
            for snap in self._snapshots:
                key = snap.situation_type.value
                totals[key] = totals.get(key, 0.0) + snap.duration_seconds
                grand_total += snap.duration_seconds
            if grand_total == 0.0:
                return totals
            return {k: (v / grand_total) * 100.0 for k, v in totals.items()}

    def detect_context_switch(self) -> bool:
        """Returns True if situation_type changed in the last 2 snapshots."""
        with self._lock:
            if len(self._snapshots) < 2:
                return False
            return (
                self._snapshots[-1].situation_type
                != self._snapshots[-2].situation_type
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _classify(self, action: str) -> tuple[SituationType, float]:
        action_lower = action.lower()
        best_type = SituationType.WORKING
        best_confidence = 0.4

        for sit_type, keywords in _SITUATION_KEYWORDS.items():
            for kw in keywords:
                if kw == action_lower or f" {kw} " in f" {action_lower} ":
                    if 0.9 > best_confidence:
                        best_type = sit_type
                        best_confidence = 0.9
                elif kw in action_lower:
                    if 0.6 > best_confidence:
                        best_type = sit_type
                        best_confidence = 0.6
        return best_type, best_confidence

    def _active_products(self) -> list[str]:
        seen: dict[str, None] = {}
        for prod, _, _ in self._action_buffer:
            if prod not in seen:
                seen[prod] = None
        return list(seen.keys())

    def _push_snapshot(self, snapshot: SituationSnapshot) -> None:
        self._snapshots.append(snapshot)
        if len(self._snapshots) > self._max_snapshots:
            self._snapshots = self._snapshots[-self._max_snapshots:]
