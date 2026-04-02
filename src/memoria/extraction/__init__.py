"""Extraction module — entity extraction providers, deduplication, conflict detection, and enrichment."""

from .providers import ExtractionProvider, RegexExtractor, LLMExtractor, HybridExtractor
from .dedup import MemoryDeduplicator
from .conflicts import ConflictType, Conflict, ResolutionStrategy, ConflictDetector
from .enricher import MemoryCategory, MemoryEnricher

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
