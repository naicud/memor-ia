"""Cross-Domain Behavioral Fusion — data types."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SignalType(Enum):
    """Types of behavioral signals from products."""

    USAGE = "usage"
    BEHAVIORAL = "behavioral"
    TEMPORAL = "temporal"
    EMOTIONAL = "emotional"
    PREFERENCE = "preference"
    PERFORMANCE = "performance"


class CorrelationType(Enum):
    """Types of cross-product correlations."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    TEMPORAL = "temporal"
    CAUSAL = "causal"
    COMPLEMENTARY = "complementary"


class ChurnRisk(Enum):
    """User churn risk levels (ordered none → critical)."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class WorkflowType(Enum):
    """Types of cross-product workflows."""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    CONDITIONAL = "conditional"
    RECURRING = "recurring"


@dataclass
class BehavioralSignal:
    """A single behavioral signal from a product."""

    source_product: str
    signal_type: SignalType
    name: str
    value: float
    timestamp: float
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class UnifiedUserModel:
    """Unified model of a user across all products."""

    user_id: str = "default"
    total_signals: int = 0
    products_active: list[str] = field(default_factory=list)
    dominant_patterns: list[str] = field(default_factory=list)
    engagement_score: float = 0.0
    consistency_score: float = 0.0
    cross_product_activity: float = 0.0
    last_updated: float = 0.0
    signal_breakdown: dict[str, int] = field(default_factory=dict)


@dataclass
class Correlation:
    """A detected correlation between two cross-product signals."""

    signal_a: str
    signal_b: str
    correlation_type: CorrelationType
    strength: float = 0.0
    confidence: float = 0.0
    evidence_count: int = 0
    description: str = ""


@dataclass
class DetectedWorkflow:
    """A detected cross-product workflow pattern."""

    workflow_id: str
    name: str
    workflow_type: WorkflowType
    steps: list[str] = field(default_factory=list)
    frequency: int = 0
    avg_duration_seconds: float = 0.0
    last_seen: float = 0.0
    confidence: float = 0.0


@dataclass
class ChurnPrediction:
    """Churn risk prediction for a specific product."""

    product_id: str
    risk_level: ChurnRisk
    probability: float = 0.0
    days_until_likely_churn: int = -1
    warning_signals: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    confidence: float = 0.0
