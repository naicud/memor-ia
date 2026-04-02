"""Data types for GDPR operations."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum


class PIIType(Enum):
    """Categories of personally identifiable information."""
    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    IP_ADDRESS = "ip_address"


@dataclass
class PIIMatch:
    """A single PII detection result."""
    pii_type: PIIType
    value: str
    start: int
    end: int
    context: str = ""

    def redacted(self) -> str:
        """Return the value with middle characters replaced by asterisks."""
        if len(self.value) <= 4:
            return "****"
        return self.value[:2] + "*" * (len(self.value) - 4) + self.value[-2:]


@dataclass
class DeletionCertificate:
    """Proof of GDPR-compliant data deletion."""
    user_id: str
    requested_at: str
    completed_at: str
    subsystems_cleared: list[str] = field(default_factory=list)
    items_deleted: dict[str, int] = field(default_factory=dict)
    certificate_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    errors: list[str] = field(default_factory=list)

    @property
    def total_deleted(self) -> int:
        return sum(self.items_deleted.values())

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> dict:
        return {
            "certificate_id": self.certificate_id,
            "user_id": self.user_id,
            "requested_at": self.requested_at,
            "completed_at": self.completed_at,
            "subsystems_cleared": self.subsystems_cleared,
            "items_deleted": self.items_deleted,
            "total_deleted": self.total_deleted,
            "success": self.success,
            "errors": self.errors,
        }


@dataclass
class ExportBundle:
    """Exported user data bundle (right to data portability)."""
    user_id: str
    exported_at: str
    data: dict[str, list[dict]] = field(default_factory=dict)
    total_items: int = 0

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "exported_at": self.exported_at,
            "total_items": self.total_items,
            "data": self.data,
        }
