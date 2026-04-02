"""Contextual Intelligence Engine — data types."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SituationType(Enum):
    WORKING = "working"
    EXPLORING = "exploring"
    TROUBLESHOOTING = "troubleshooting"
    LEARNING = "learning"
    REVIEWING = "reviewing"
    CREATING = "creating"
    MANAGING = "managing"
    IDLE = "idle"


class IntentConfidence(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class HandoffReason(Enum):
    TASK_COMPLETE = "task_complete"
    CONTEXT_SWITCH = "context_switch"
    EXPERTISE_NEEDED = "expertise_needed"
    USER_REQUEST = "user_request"
    PRODUCT_BOUNDARY = "product_boundary"
    ESCALATION = "escalation"


class AssistanceType(Enum):
    SUGGESTION = "suggestion"
    WARNING = "warning"
    SHORTCUT = "shortcut"
    REMINDER = "reminder"
    TUTORIAL = "tutorial"
    AUTOMATION = "automation"


@dataclass
class SituationSnapshot:
    situation_type: SituationType
    active_products: list[str] = field(default_factory=list)
    current_product: str = ""
    current_action: str = ""
    duration_seconds: float = 0.0
    context_signals: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    confidence: float = 0.0


@dataclass
class InferredIntent:
    intent: str
    confidence: float = 0.0
    confidence_level: IntentConfidence = IntentConfidence.LOW
    supporting_evidence: list[str] = field(default_factory=list)
    related_products: list[str] = field(default_factory=list)
    predicted_next_actions: list[str] = field(default_factory=list)
    timestamp: float = 0.0


@dataclass
class ProactiveAssistance:
    assistance_id: str
    assistance_type: AssistanceType
    title: str
    description: str
    relevance_score: float = 0.0
    target_product: str = ""
    action_url: str = ""
    expires_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class HandoffContext:
    handoff_id: str
    source_product: str
    target_product: str
    reason: HandoffReason
    context_data: dict[str, Any] = field(default_factory=dict)
    user_state: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    success: bool = False
    completion_time: float = 0.0
