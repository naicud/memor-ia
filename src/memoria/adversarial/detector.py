"""PoisonDetector — detects memory poisoning and injection attempts."""

import dataclasses
import re
import threading
from collections import deque
from typing import Any, Dict, List, Optional

from .types import ThreatDetection, ThreatLevel, ThreatType

_MAX_DETECTIONS = 10000
_MAX_PATTERNS = 10000


class PoisonDetector:
    """Detects memory poisoning and injection attempts using regex patterns and heuristics."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._detections: deque = deque(maxlen=_MAX_DETECTIONS)
        self._custom_patterns: deque = deque(maxlen=_MAX_PATTERNS)
        self._stats: Dict[str, int] = {
            "total_scans": 0,
            "threats_detected": 0,
            "by_type": {},
            "by_level": {},
        }

        self._builtin_patterns: List[Dict[str, Any]] = [
            # SQL injection
            {"name": "sql_drop", "pattern": r"(?i)\bDROP\s+TABLE\b", "type": ThreatType.INJECTION, "level": ThreatLevel.CRITICAL},
            {"name": "sql_delete", "pattern": r"(?i);\s*DELETE\b", "type": ThreatType.INJECTION, "level": ThreatLevel.HIGH},
            {"name": "sql_union", "pattern": r"(?i)\bUNION\s+SELECT\b", "type": ThreatType.INJECTION, "level": ThreatLevel.HIGH},
            {"name": "sql_or_true", "pattern": r"(?i)\bOR\s+1\s*=\s*1\b", "type": ThreatType.INJECTION, "level": ThreatLevel.HIGH},
            {"name": "sql_or_quote", "pattern": r"(?i)'\s*OR\s*''\s*=\s*'", "type": ThreatType.INJECTION, "level": ThreatLevel.HIGH},
            # Prompt injection
            {"name": "prompt_ignore", "pattern": r"(?i)\bignore\s+previous\b", "type": ThreatType.INJECTION, "level": ThreatLevel.HIGH},
            {"name": "prompt_system", "pattern": r"(?i)\bsystem\s+prompt\b", "type": ThreatType.INJECTION, "level": ThreatLevel.MEDIUM},
            {"name": "prompt_you_are", "pattern": r"(?i)\byou\s+are\s+now\b", "type": ThreatType.MANIPULATION, "level": ThreatLevel.MEDIUM},
            {"name": "prompt_forget", "pattern": r"(?i)\bforget\s+everything\b", "type": ThreatType.MANIPULATION, "level": ThreatLevel.HIGH},
            {"name": "prompt_disregard", "pattern": r"(?i)\bdisregard\s+instructions\b", "type": ThreatType.INJECTION, "level": ThreatLevel.HIGH},
            # Command injection
            {"name": "cmd_rm", "pattern": r"(?i);\s*rm\s+-rf\b", "type": ThreatType.INJECTION, "level": ThreatLevel.CRITICAL},
            {"name": "cmd_cat", "pattern": r"(?i)\|\s*cat\s+/etc", "type": ThreatType.INJECTION, "level": ThreatLevel.HIGH},
            {"name": "cmd_subshell", "pattern": r"\$\([^)]+\)", "type": ThreatType.INJECTION, "level": ThreatLevel.HIGH},
            {"name": "cmd_backtick", "pattern": r"`[^`]+`", "type": ThreatType.INJECTION, "level": ThreatLevel.MEDIUM},
            # Exfiltration
            {"name": "exfil_send", "pattern": r"(?i)\b(send|transmit|exfiltrate|extract)\s+(all\s+)?(data|information|credentials|secrets|passwords)\b", "type": ThreatType.EXFILTRATION, "level": ThreatLevel.HIGH},
            {"name": "exfil_dump", "pattern": r"(?i)\bdump\s+(all\s+)?(memory|data|database)\b", "type": ThreatType.EXFILTRATION, "level": ThreatLevel.HIGH},
        ]

    def scan_content(self, content: str, context: Optional[Dict] = None) -> ThreatDetection:
        """Scan text for injection patterns and return a ThreatDetection."""
        if context is not None:
            context = dict(context)

        with self._lock:
            self._stats["total_scans"] += 1

        if not content:
            return ThreatDetection(
                threat_type=ThreatType.INJECTION,
                threat_level=ThreatLevel.NONE,
                description="Empty content — no threat.",
                confidence=1.0,
                source_content="",
                recommended_action="allow",
            )

        evidence: List[str] = []
        worst_level = ThreatLevel.NONE
        worst_type = ThreatType.INJECTION
        matched_names: List[str] = []

        all_patterns = list(self._builtin_patterns)
        with self._lock:
            all_patterns.extend(list(self._custom_patterns))

        for pat in all_patterns:
            try:
                if re.search(pat["pattern"], content):
                    evidence.append(f"Matched pattern: {pat['name']}")
                    matched_names.append(pat["name"])
                    if self._level_rank(pat["level"]) > self._level_rank(worst_level):
                        worst_level = pat["level"]
                        worst_type = pat["type"]
            except re.error:
                continue

        # Overflow detection
        if len(content) > 10000:
            evidence.append("Content length exceeds 10000 characters")
            if self._level_rank(ThreatLevel.MEDIUM) > self._level_rank(worst_level):
                worst_level = ThreatLevel.MEDIUM
                worst_type = ThreatType.OVERFLOW

        # Repetitive pattern detection
        if len(content) > 500:
            chunk = content[:200]
            if content.count(chunk[:50]) > 10:
                evidence.append("Highly repetitive content detected")
                if self._level_rank(ThreatLevel.MEDIUM) > self._level_rank(worst_level):
                    worst_level = ThreatLevel.MEDIUM
                    worst_type = ThreatType.OVERFLOW

        confidence = min(1.0, len(evidence) * 0.3) if evidence else 1.0

        if worst_level == ThreatLevel.NONE:
            description = "No threats detected."
            action = "allow"
            confidence = 1.0
        elif worst_level in (ThreatLevel.LOW, ThreatLevel.MEDIUM):
            description = f"Potential threat detected: {', '.join(matched_names[:5])}"
            action = "review"
        else:
            description = f"Threat detected: {', '.join(matched_names[:5])}"
            action = "block"

        detection = ThreatDetection(
            threat_type=worst_type,
            threat_level=worst_level,
            description=description,
            evidence=list(evidence),
            confidence=confidence,
            source_content=content[:500],
            recommended_action=action,
        )

        if worst_level != ThreatLevel.NONE:
            with self._lock:
                stored = dataclasses.replace(detection, evidence=list(detection.evidence))
                self._detections.append(stored)
                self._stats["threats_detected"] += 1
                type_key = worst_type.value
                self._stats["by_type"][type_key] = self._stats["by_type"].get(type_key, 0) + 1
                level_key = worst_level.value
                self._stats["by_level"][level_key] = self._stats["by_level"].get(level_key, 0) + 1

        return detection

    def scan_batch(self, contents: List[str]) -> List[ThreatDetection]:
        """Batch-scan multiple content strings."""
        contents = list(contents)
        return [self.scan_content(c) for c in contents]

    def register_pattern(
        self, name: str, pattern: str, threat_type: ThreatType, threat_level: ThreatLevel
    ) -> None:
        """Register a custom detection pattern."""
        entry = {
            "name": name,
            "pattern": pattern,
            "type": threat_type,
            "level": threat_level,
        }
        with self._lock:
            self._custom_patterns.append(entry)

    def get_threat_stats(self) -> Dict[str, Any]:
        """Return detection statistics."""
        with self._lock:
            return {
                "total_scans": self._stats["total_scans"],
                "threats_detected": self._stats["threats_detected"],
                "by_type": dict(self._stats["by_type"]),
                "by_level": dict(self._stats["by_level"]),
                "detection_count": len(self._detections),
            }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        with self._lock:
            detections = []
            for d in self._detections:
                detections.append({
                    "threat_type": d.threat_type.value,
                    "threat_level": d.threat_level.value,
                    "description": d.description,
                    "evidence": list(d.evidence),
                    "confidence": d.confidence,
                    "timestamp": d.timestamp,
                    "source_content": d.source_content,
                    "recommended_action": d.recommended_action,
                })
            custom = []
            for p in self._custom_patterns:
                custom.append({
                    "name": p["name"],
                    "pattern": p["pattern"],
                    "type": p["type"].value,
                    "level": p["level"].value,
                })
            return {
                "detections": detections,
                "custom_patterns": custom,
                "stats": {
                    "total_scans": self._stats["total_scans"],
                    "threats_detected": self._stats["threats_detected"],
                    "by_type": dict(self._stats["by_type"]),
                    "by_level": dict(self._stats["by_level"]),
                },
            }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PoisonDetector":
        """Deserialize from a dict."""
        obj = cls()
        custom_patterns = data.get("custom_patterns", [])
        if not isinstance(custom_patterns, list):
            custom_patterns = []
        for p in custom_patterns:
            if not isinstance(p, dict):
                continue
            try:
                obj.register_pattern(
                    name=p["name"],
                    pattern=p["pattern"],
                    threat_type=ThreatType(p["type"]),
                    threat_level=ThreatLevel(p["level"]),
                )
            except (KeyError, ValueError):
                continue
        detections = data.get("detections", [])
        if not isinstance(detections, list):
            detections = []
        for d in detections:
            if not isinstance(d, dict):
                continue
            try:
                det = ThreatDetection(
                    threat_type=ThreatType(d["threat_type"]),
                    threat_level=ThreatLevel(d["threat_level"]),
                    description=d["description"],
                    evidence=list(d.get("evidence", [])),
                    confidence=d.get("confidence", 0.0),
                    timestamp=d.get("timestamp", 0.0),
                    source_content=d.get("source_content", ""),
                    recommended_action=d.get("recommended_action", "review"),
                )
                obj._detections.append(det)
            except (KeyError, ValueError, TypeError):
                continue
        stats = data.get("stats", {})
        if isinstance(stats, dict):
            obj._stats["total_scans"] = stats.get("total_scans", 0)
            obj._stats["threats_detected"] = stats.get("threats_detected", 0)
            obj._stats["by_type"] = dict(stats.get("by_type", {}))
            obj._stats["by_level"] = dict(stats.get("by_level", {}))
        return obj

    # ------------------------------------------------------------------
    @staticmethod
    def _level_rank(level: ThreatLevel) -> int:
        return {
            ThreatLevel.NONE: 0,
            ThreatLevel.LOW: 1,
            ThreatLevel.MEDIUM: 2,
            ThreatLevel.HIGH: 3,
            ThreatLevel.CRITICAL: 4,
        }.get(level, 0)
