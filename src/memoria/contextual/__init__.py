"""Contextual Intelligence Engine for MEMORIA.

Provides real-time cross-product situation awareness, intent inference,
proactive assistance, and smart handoffs between products/agents.
"""

from .assistant import ProactiveAssistant
from .awareness import SituationAwareness
from .handoff import SmartHandoff
from .intent import IntentInference
from .types import (
    AssistanceType,
    HandoffContext,
    HandoffReason,
    InferredIntent,
    IntentConfidence,
    ProactiveAssistance,
    SituationSnapshot,
    SituationType,
)

__all__ = [
    "AssistanceType",
    "HandoffContext",
    "HandoffReason",
    "InferredIntent",
    "IntentConfidence",
    "IntentInference",
    "ProactiveAssistance",
    "ProactiveAssistant",
    "SituationAwareness",
    "SituationSnapshot",
    "SituationType",
    "SmartHandoff",
]
