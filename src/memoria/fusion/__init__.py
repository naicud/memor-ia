"""Cross-Domain Behavioral Fusion for MEMORIA.

Unifies behavioral signals from multiple products into a single user
model, discovers cross-product correlations, detects workflows, and
predicts churn risk.
"""

from .behavior_fusion import BehaviorFusion
from .churn import ChurnPredictor
from .correlator import CrossProductCorrelator
from .types import (
    BehavioralSignal,
    ChurnPrediction,
    ChurnRisk,
    Correlation,
    CorrelationType,
    DetectedWorkflow,
    SignalType,
    UnifiedUserModel,
    WorkflowType,
)
from .workflow_detector import WorkflowDetector

__all__ = [
    "BehaviorFusion",
    "BehavioralSignal",
    "ChurnPrediction",
    "ChurnPredictor",
    "ChurnRisk",
    "Correlation",
    "CorrelationType",
    "CrossProductCorrelator",
    "DetectedWorkflow",
    "SignalType",
    "UnifiedUserModel",
    "WorkflowDetector",
    "WorkflowType",
]
