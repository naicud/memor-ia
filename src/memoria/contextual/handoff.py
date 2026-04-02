"""Contextual Intelligence Engine — smart handoff."""

import threading
import time
import uuid
from typing import Any, Optional

from .types import HandoffContext, HandoffReason


class SmartHandoff:
    """Manages intelligent context handoffs between products/agents."""

    def __init__(self, max_handoffs: int = 500, max_active: int = 100) -> None:
        self._lock = threading.RLock()
        self._handoff_history: list[HandoffContext] = []
        self._active_handoffs: dict[str, HandoffContext] = {}
        self._product_capabilities: dict[str, list[str]] = {}
        self._max_handoffs = max_handoffs
        self._max_active = max_active

    def register_product_capabilities(
        self, product_id: str, capabilities: list[str]
    ) -> None:
        """Register what a product can do."""
        with self._lock:
            self._product_capabilities[product_id] = list(capabilities)

    def initiate_handoff(
        self,
        source_product: str,
        target_product: str,
        reason: HandoffReason,
        context_data: Optional[dict[str, Any]] = None,
        user_state: Optional[dict[str, Any]] = None,
    ) -> HandoffContext:
        """Initiate a handoff from one product to another."""
        ts = time.time()

        with self._lock:
            hid = uuid.uuid4().hex
            handoff = HandoffContext(
                handoff_id=hid,
                source_product=source_product,
                target_product=target_product,
                reason=reason,
                context_data=dict(context_data) if context_data else {},
                user_state=dict(user_state) if user_state else {},
                timestamp=ts,
                success=False,
                completion_time=0.0,
            )
            self._active_handoffs[hid] = handoff
            if len(self._active_handoffs) > self._max_active:
                oldest_key = min(
                    self._active_handoffs,
                    key=lambda k: self._active_handoffs[k].timestamp,
                )
                del self._active_handoffs[oldest_key]
            self._handoff_history.append(handoff)
            if len(self._handoff_history) > self._max_handoffs:
                self._handoff_history = self._handoff_history[-self._max_handoffs:]
            return handoff

    def complete_handoff(
        self, handoff_id: str, success: bool = True
    ) -> Optional[HandoffContext]:
        """Mark handoff as complete."""
        with self._lock:
            handoff = self._active_handoffs.pop(handoff_id, None)
            if handoff is None:
                return None
            handoff.success = success
            handoff.completion_time = time.time()
            return handoff

    def suggest_handoff(
        self, current_product: str, user_need: str
    ) -> Optional[tuple[str, HandoffReason]]:
        """Suggest which product to hand off to based on user need."""
        need_lower = user_need.lower().strip()

        with self._lock:
            if not need_lower:
                return None

            best_product: Optional[str] = None
            best_score = 0

            for prod, caps in self._product_capabilities.items():
                if prod == current_product:
                    continue
                score = sum(1 for c in caps if c.lower() in need_lower or need_lower in c.lower())
                if score > best_score:
                    best_score = score
                    best_product = prod

            if best_product is not None:
                return best_product, HandoffReason.EXPERTISE_NEEDED
            return None

    def get_handoff_history(
        self, product_id: Optional[str] = None, limit: int = 20
    ) -> list[HandoffContext]:
        with self._lock:
            if product_id is not None:
                filtered = [
                    h
                    for h in self._handoff_history
                    if h.source_product == product_id
                    or h.target_product == product_id
                ]
                return filtered[-limit:]
            return list(self._handoff_history[-limit:])

    def get_active_handoffs(self) -> list[HandoffContext]:
        with self._lock:
            return list(self._active_handoffs.values())

    def get_handoff_success_rate(
        self, product_id: Optional[str] = None
    ) -> float:
        """Success rate of completed handoffs (0.0-1.0)."""
        with self._lock:
            completed = [
                h
                for h in self._handoff_history
                if h.completion_time > 0.0
            ]
            if product_id is not None:
                completed = [
                    h
                    for h in completed
                    if h.source_product == product_id
                    or h.target_product == product_id
                ]
            if not completed:
                return 0.0
            return sum(1 for h in completed if h.success) / len(completed)

    def get_handoff_summary(self) -> dict[str, Any]:
        """Summary of handoff state."""
        with self._lock:
            completed = [h for h in self._handoff_history if h.completion_time > 0.0]
            successes = sum(1 for h in completed if h.success)
            rate = successes / len(completed) if completed else 0.0

            # Most common routes
            routes: dict[str, int] = {}
            for h in self._handoff_history:
                route = f"{h.source_product}->{h.target_product}"
                routes[route] = routes.get(route, 0) + 1

            # Most common reasons
            reasons: dict[str, int] = {}
            for h in self._handoff_history:
                key = h.reason.value
                reasons[key] = reasons.get(key, 0) + 1

            return {
                "total": len(self._handoff_history),
                "active": len(self._active_handoffs),
                "completed": len(completed),
                "success_rate": rate,
                "most_common_routes": dict(
                    sorted(routes.items(), key=lambda x: x[1], reverse=True)
                ),
                "most_common_reasons": dict(
                    sorted(reasons.items(), key=lambda x: x[1], reverse=True)
                ),
            }
