"""Semantic deduplication — detect and merge near-identical memories."""

from memoria.dedup.detector import DuplicateDetector, DuplicateMatch
from memoria.dedup.merger import MemoryMerger, MergeResult

__all__ = [
    "DuplicateDetector",
    "DuplicateMatch",
    "MemoryMerger",
    "MergeResult",
]
