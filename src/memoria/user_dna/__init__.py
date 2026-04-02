"""User DNA — behavioral fingerprinting and digital twin for users."""

from __future__ import annotations

from memoria.user_dna.analyzer import DNAAnalyzer
from memoria.user_dna.collector import PassiveCollector
from memoria.user_dna.store import UserDNAStore
from memoria.user_dna.types import (
    CodingStyle,
    CommunicationProfile,
    ExpertiseSnapshot,
    InteractionFingerprint,
    SessionRhythm,
    UserDNA,
)

__all__ = [
    # types
    "CodingStyle",
    "CommunicationProfile",
    "ExpertiseSnapshot",
    "InteractionFingerprint",
    "SessionRhythm",
    "UserDNA",
    # collector
    "PassiveCollector",
    # analyzer
    "DNAAnalyzer",
    # store
    "UserDNAStore",
]
