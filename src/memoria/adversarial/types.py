"""Data types for the Adversarial Memory Protection module."""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class ThreatLevel(Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ThreatType(Enum):
    INJECTION = "injection"
    POISONING = "poisoning"
    CONTRADICTION = "contradiction"
    HALLUCINATION = "hallucination"
    MANIPULATION = "manipulation"
    OVERFLOW = "overflow"
    EXFILTRATION = "exfiltration"


class VerificationStatus(Enum):
    VERIFIED = "verified"
    SUSPICIOUS = "suspicious"
    REJECTED = "rejected"
    PENDING = "pending"


class IntegrityStatus(Enum):
    INTACT = "intact"
    TAMPERED = "tampered"
    CORRUPTED = "corrupted"
    UNKNOWN = "unknown"


@dataclass
class ThreatDetection:
    threat_type: ThreatType
    threat_level: ThreatLevel
    description: str
    evidence: List[str] = field(default_factory=list)
    confidence: float = 0.0
    timestamp: float = field(default_factory=time.time)
    source_content: str = ""
    recommended_action: str = "review"


@dataclass
class ConsistencyReport:
    is_consistent: bool
    contradictions: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 1.0
    checked_against: int = 0
    timestamp: float = field(default_factory=time.time)


@dataclass
class IntegrityRecord:
    content_hash: str
    content_id: str
    status: IntegrityStatus = IntegrityStatus.INTACT
    created_at: float = field(default_factory=time.time)
    last_verified: float = field(default_factory=time.time)
    verification_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnomalyReport:
    is_anomalous: bool
    anomaly_score: float = 0.0
    anomalies: List[Dict[str, Any]] = field(default_factory=list)
    baseline_stats: Dict[str, float] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
