"""Preference types for the MEMORIA preference engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class PreferenceCategory(Enum):
    LANGUAGE = "language"
    FRAMEWORK = "framework"
    TOOL = "tool"
    STYLE = "style"
    WORKFLOW = "workflow"
    COMMUNICATION = "communication"
    ARCHITECTURE = "architecture"
    TESTING = "testing"
    ENVIRONMENT = "environment"


class PreferenceSource(Enum):
    EXPLICIT = "explicit"
    IMPLICIT = "implicit"
    INFERRED = "inferred"
    CORRECTED = "corrected"


@dataclass
class PreferenceEvidence:
    """A single piece of evidence for a preference."""
    source: PreferenceSource
    signal: str
    timestamp: float = 0.0
    context: str = ""


@dataclass
class Preference:
    """A learned user preference with confidence tracking."""
    preference_id: str
    user_id: str
    category: PreferenceCategory
    key: str
    value: str
    confidence: float = 0.3
    observation_count: int = 1
    evidence: list[PreferenceEvidence] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0
    contradicted_by: str = ""
    active: bool = True
    context: str = ""


@dataclass
class PreferenceConflict:
    """Represents two contradicting preferences."""
    preference_a: Preference
    preference_b: Preference
    resolution: str = ""
    resolution_reason: str = ""


@dataclass
class PreferenceQuery:
    """Query for preferences."""
    user_id: str
    category: PreferenceCategory | None = None
    key: str = ""
    context: str = ""
    min_confidence: float = 0.0
    active_only: bool = True
