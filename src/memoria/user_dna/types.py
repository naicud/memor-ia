"""User DNA types — dataclasses for behavioral fingerprinting."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CodingStyle:
    """Detected coding style preferences."""

    naming_convention: str = "unknown"  # snake_case, camelCase, PascalCase, kebab-case
    docstring_style: str = "unknown"  # google, numpy, sphinx, none
    import_style: str = "unknown"  # grouped, alphabetical, mixed
    error_handling: str = "unknown"  # try-except, assertions, result-types, mixed
    testing_approach: str = "unknown"  # tdd, write-after, minimal, comprehensive
    avg_function_length: float = 0.0  # lines per function
    comment_density: float = 0.0  # comments per 100 LOC
    type_annotation_usage: float = 0.0  # 0.0–1.0 usage frequency
    preferred_patterns: list[str] = field(default_factory=list)


@dataclass
class CommunicationProfile:
    """How the user communicates."""

    verbosity: float = 5.0  # 1-10 scale
    formality: float = 5.0  # 1-10 (casual → formal)
    question_frequency: float = 0.0  # questions per 10 messages
    explanation_depth: str = "medium"  # brief, medium, detailed
    patience_level: float = 7.0  # 1-10
    preferred_language: str = "en"
    uses_emoji: bool = False
    prefers_examples: bool = True
    frustration_indicators: int = 0


@dataclass
class ExpertiseSnapshot:
    """Expertise level in a single domain."""

    domain: str
    level: float = 0.0  # 0-1 expertise
    confidence: float = 0.5
    evidence_count: int = 0
    first_seen: float = 0.0
    last_seen: float = 0.0
    growth_rate: float = 0.0  # positive = improving


@dataclass
class SessionRhythm:
    """When and how the user works."""

    peak_hours: list[int] = field(default_factory=list)
    avg_session_minutes: float = 0.0
    avg_messages_per_session: float = 0.0
    preferred_session_days: list[str] = field(default_factory=list)
    context_switch_frequency: float = 0.0
    focus_duration_minutes: float = 0.0


@dataclass
class InteractionFingerprint:
    """Aggregate interaction statistics."""

    total_interactions: int = 0
    total_sessions: int = 0
    first_interaction: float = 0.0
    last_interaction: float = 0.0
    avg_message_length: float = 0.0
    code_to_text_ratio: float = 0.0
    common_intents: list[str] = field(default_factory=list)
    error_recovery_style: str = "unknown"


@dataclass
class UserDNA:
    """Complete behavioral fingerprint of a user."""

    user_id: str
    version: int = 1
    created_at: float = 0.0
    updated_at: float = 0.0
    coding_style: CodingStyle = field(default_factory=CodingStyle)
    communication: CommunicationProfile = field(default_factory=CommunicationProfile)
    expertise: list[ExpertiseSnapshot] = field(default_factory=list)
    rhythm: SessionRhythm = field(default_factory=SessionRhythm)
    fingerprint: InteractionFingerprint = field(default_factory=InteractionFingerprint)
    raw_signals: list[dict] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
