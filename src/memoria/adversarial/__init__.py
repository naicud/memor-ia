"""Adversarial Memory Protection module for MEMORIA."""

from .detector import PoisonDetector
from .hallucination import HallucinationGuard
from .tamper import TamperProof
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
from .verifier import ConsistencyVerifier

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
