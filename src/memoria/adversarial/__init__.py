"""Adversarial Memory Protection module for MEMORIA."""

from .types import (
    AnomalyReport,
    ConsistencyReport,
    IntegrityRecord,
    IntegrityStatus,
    ThreatDetection,
    ThreatLevel,
    ThreatType,
    VerificationStatus,
)
from .detector import PoisonDetector
from .hallucination import HallucinationGuard
from .verifier import ConsistencyVerifier
from .tamper import TamperProof

__all__ = [
    # Types / enums
    "ThreatLevel",
    "ThreatType",
    "VerificationStatus",
    "IntegrityStatus",
    "ThreatDetection",
    "ConsistencyReport",
    "IntegrityRecord",
    "AnomalyReport",
    # Classes
    "PoisonDetector",
    "HallucinationGuard",
    "ConsistencyVerifier",
    "TamperProof",
]
