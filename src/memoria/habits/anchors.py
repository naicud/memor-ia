"""AnchorDetector — finds anchor behaviours that trigger action chains."""

from __future__ import annotations

import threading
import time
import uuid
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

from .types import AnchorBehavior, AnchorType

_TEMPORAL_KEYWORDS = frozenset(
    {
        "morning",
        "evening",
        "night",
        "alarm",
        "schedule",
        "timer",
        "daily",
        "wakeup",
        "wake_up",
        "bedtime",
        "noon",
        "midnight",
        "clock",
    }
)


class AnchorDetector:
    """Finds 'anchor behaviours' that trigger chains of subsequent actions.

    Analyses recorded action sequences to discover which initial actions
    reliably predict a specific chain of follow-up actions.
    """

    def __init__(
        self,
        min_trigger_count: int = 3,
        max_anchors: int = 100,
        max_sequences: int = 10000,
    ) -> None:
        self._lock = threading.RLock()
        self._sequences: List[Tuple[List[str], float, List[str]]] = []
        self._anchors: Dict[str, AnchorBehavior] = {}
        self._min_trigger_count = max(1, min_trigger_count)
        self._max_anchors = max(1, max_anchors)
        self._max_sequences = max(1, max_sequences)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_sequence(
        self,
        actions: List[str],
        timestamp: Optional[float] = None,
        products: Optional[List[str]] = None,
    ) -> None:
        """Record a sequence of actions that occurred together."""
        if not actions:
            return
        ts = timestamp if timestamp is not None else time.time()
        prods = list(products) if products else []
        with self._lock:
            if len(self._sequences) >= self._max_sequences:
                self._sequences = self._sequences[-(self._max_sequences // 2) :]
            self._sequences.append((list(actions), ts, prods))

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect_anchors(self, min_probability: float = 0.5) -> List[AnchorBehavior]:
        """Detect anchor behaviours that trigger predictable chains.

        For each unique first action in sequences:
        1. Count how often it appears as first action.
        2. Find the most common chain that follows (2-4 actions).
        3. probability = chain_count / total_appearances.
        4. If probability >= *min_probability* AND count >= *min_trigger_count*, anchor.
        """
        min_probability = max(0.0, min(1.0, min_probability))

        with self._lock:
            sequences = [(list(a), t, list(p)) for a, t, p in self._sequences]

        # Group sequences by first action
        first_action_groups: Dict[str, List[Tuple[List[str], float, List[str]]]] = (
            defaultdict(list)
        )
        for actions, ts, prods in sequences:
            first_action_groups[actions[0]].append((actions, ts, prods))

        detected: List[AnchorBehavior] = []

        for trigger, group in first_action_groups.items():
            total = len(group)
            if total < self._min_trigger_count:
                continue

            # Find best chain length (2-4 actions following trigger)
            best_chain: Optional[Tuple[str, ...]] = None
            best_count = 0

            for chain_len in range(2, 5):
                chain_counter: Counter[Tuple[str, ...]] = Counter()
                for actions, _, _ in group:
                    if len(actions) > chain_len:
                        chain = tuple(actions[1 : chain_len + 1])
                        chain_counter[chain] += 1
                    elif len(actions) > 1:
                        chain = tuple(actions[1:])
                        chain_counter[chain] += 1

                if chain_counter:
                    top_chain, top_count = chain_counter.most_common(1)[0]
                    if top_count > best_count:
                        best_count = top_count
                        best_chain = top_chain

            if best_chain is None or best_count < self._min_trigger_count:
                continue

            probability = best_count / total
            if probability < min_probability:
                continue

            # Compute avg delay (use timestamps within sequences — rough proxy)
            delays: List[float] = []
            for actions, ts, _ in group:
                if len(actions) > 1:
                    delays.append(0.0)  # no sub-action timestamps available
            avg_delay = sum(delays) / len(delays) if delays else 0.0

            # Collect products
            all_products: set[str] = set()
            for _, _, prods in group:
                all_products.update(prods)

            # Classify anchor type
            anchor_type = self._classify_anchor_type(trigger)

            anchor = AnchorBehavior(
                anchor_id=uuid.uuid4().hex,
                trigger_action=trigger,
                anchor_type=anchor_type,
                triggered_chain=list(best_chain),
                trigger_probability=round(probability, 4),
                avg_delay_seconds=round(avg_delay, 2),
                occurrence_count=best_count,
                products_involved=sorted(all_products),
            )
            detected.append(anchor)

        detected.sort(key=lambda a: a.trigger_probability, reverse=True)
        detected = detected[: self._max_anchors]

        with self._lock:
            self._anchors = {a.anchor_id: a for a in detected}

        return list(detected)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_anchors(
        self, anchor_type: Optional[AnchorType] = None
    ) -> List[AnchorBehavior]:
        """Return all anchors, optionally filtered by type."""
        with self._lock:
            anchors = list(self._anchors.values())
        if anchor_type is not None:
            anchors = [a for a in anchors if a.anchor_type == anchor_type]
        return anchors

    def get_anchor(self, anchor_id: str) -> Optional[AnchorBehavior]:
        """Return a single anchor by ID, or None."""
        with self._lock:
            return self._anchors.get(anchor_id)

    def predict_chain(self, trigger_action: str) -> Optional[List[str]]:
        """Given a trigger action, predict the chain that will follow."""
        with self._lock:
            for anchor in self._anchors.values():
                if anchor.trigger_action == trigger_action:
                    return list(anchor.triggered_chain)
        return None

    def get_anchor_summary(self) -> Dict:
        """Summary of detected anchor behaviours."""
        with self._lock:
            anchors = list(self._anchors.values())

        by_type: Dict[str, int] = defaultdict(int)
        products: set[str] = set()
        for a in anchors:
            by_type[a.anchor_type.value] += 1
            products.update(a.products_involved)

        top_anchors = sorted(anchors, key=lambda a: a.trigger_probability, reverse=True)[
            :5
        ]

        return {
            "total_anchors": len(anchors),
            "by_type": dict(by_type),
            "products_involved": sorted(products),
            "top_anchors": [
                {
                    "trigger": a.trigger_action,
                    "probability": a.trigger_probability,
                    "chain": a.triggered_chain,
                }
                for a in top_anchors
            ],
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_anchor_type(trigger: str) -> AnchorType:
        trigger_lower = trigger.lower()
        for kw in _TEMPORAL_KEYWORDS:
            if kw in trigger_lower:
                return AnchorType.TEMPORAL
        return AnchorType.SEQUENTIAL
