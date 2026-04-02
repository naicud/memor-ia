"""PII (Personally Identifiable Information) scanner."""
from __future__ import annotations

import re

from memoria.gdpr.types import PIIMatch, PIIType

# Compiled regex patterns for each PII type
_PATTERNS: dict[PIIType, re.Pattern[str]] = {
    PIIType.EMAIL: re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    ),
    PIIType.PHONE: re.compile(
        r"\b\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}\b"
    ),
    PIIType.SSN: re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    PIIType.CREDIT_CARD: re.compile(
        r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"
    ),
    PIIType.IP_ADDRESS: re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    ),
}

# Context window around each match (chars before/after)
_CONTEXT_CHARS = 30


class PIIScanner:
    """Scan text for personally identifiable information.

    Uses regex-based detection for common PII types.
    Not intended as a replacement for NER-based scanners in
    high-compliance environments, but sufficient for most use cases.
    """

    def __init__(
        self,
        types: list[PIIType] | None = None,
        extra_patterns: dict[str, str] | None = None,
    ) -> None:
        self._types = types or list(PIIType)
        self._extra: dict[str, re.Pattern[str]] = {}
        if extra_patterns:
            for name, pattern in extra_patterns.items():
                self._extra[name] = re.compile(pattern)

    def scan(self, text: str) -> list[PIIMatch]:
        """Return all PII matches found in *text*."""
        matches: list[PIIMatch] = []
        for pii_type in self._types:
            pattern = _PATTERNS.get(pii_type)
            if pattern is None:
                continue
            for m in pattern.finditer(text):
                ctx_start = max(0, m.start() - _CONTEXT_CHARS)
                ctx_end = min(len(text), m.end() + _CONTEXT_CHARS)
                matches.append(
                    PIIMatch(
                        pii_type=pii_type,
                        value=m.group(),
                        start=m.start(),
                        end=m.end(),
                        context=text[ctx_start:ctx_end],
                    )
                )
        # Extra custom patterns
        for name, pattern in self._extra.items():
            for m in pattern.finditer(text):
                ctx_start = max(0, m.start() - _CONTEXT_CHARS)
                ctx_end = min(len(text), m.end() + _CONTEXT_CHARS)
                matches.append(
                    PIIMatch(
                        pii_type=PIIType.EMAIL,  # fallback type
                        value=m.group(),
                        start=m.start(),
                        end=m.end(),
                        context=f"[custom:{name}] {text[ctx_start:ctx_end]}",
                    )
                )
        return matches

    def has_pii(self, text: str) -> bool:
        """Return True if *text* contains any PII."""
        for pii_type in self._types:
            pattern = _PATTERNS.get(pii_type)
            if pattern and pattern.search(text):
                return True
        for pattern in self._extra.values():
            if pattern.search(text):
                return True
        return False

    def redact(self, text: str) -> str:
        """Return *text* with all PII values replaced by redaction markers."""
        matches = self.scan(text)
        if not matches:
            return text
        # Sort by position descending to replace from end to start
        matches.sort(key=lambda m: m.start, reverse=True)
        result = text
        for match in matches:
            replacement = f"[{match.pii_type.value.upper()}_REDACTED]"
            result = result[: match.start] + replacement + result[match.end :]
        return result
