"""MEMORIA Preference Engine — structured preference learning with confidence evolution."""
from __future__ import annotations

from .types import (
    Preference,
    PreferenceCategory,
    PreferenceConflict,
    PreferenceEvidence,
    PreferenceQuery,
    PreferenceSource,
)
from .detector import PreferenceDetector
from .store import PreferenceStore
from .resolver import ConflictResolver

__all__ = [
    "Preference",
    "PreferenceCategory",
    "PreferenceConflict",
    "PreferenceDetector",
    "PreferenceEvidence",
    "PreferenceQuery",
    "PreferenceSource",
    "PreferenceStore",
    "ConflictResolver",
]
