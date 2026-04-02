"""MEMORIA Preference Engine — structured preference learning with confidence evolution."""
from __future__ import annotations

from .detector import PreferenceDetector
from .resolver import ConflictResolver
from .store import PreferenceStore
from .types import (
    Preference,
    PreferenceCategory,
    PreferenceConflict,
    PreferenceEvidence,
    PreferenceQuery,
    PreferenceSource,
)

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
