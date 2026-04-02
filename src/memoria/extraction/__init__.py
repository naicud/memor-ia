"""Extraction module — entity extraction providers, deduplication, conflict detection, and enrichment."""

from .conflicts import Conflict, ConflictDetector, ConflictType, ResolutionStrategy
from .dedup import MemoryDeduplicator
from .enricher import MemoryCategory, MemoryEnricher
from .providers import ExtractionProvider, HybridExtractor, LLMExtractor, RegexExtractor

__all__ = [
    # providers
    "ExtractionProvider",
    "RegexExtractor",
    "LLMExtractor",
    "HybridExtractor",
    # dedup
    "MemoryDeduplicator",
    # conflicts
    "ConflictType",
    "Conflict",
    "ResolutionStrategy",
    "ConflictDetector",
    # enricher
    "MemoryCategory",
    "MemoryEnricher",
]
