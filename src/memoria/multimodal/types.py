"""Data types for multi-modal memory attachments."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

# Supported MIME type families
SUPPORTED_IMAGE_TYPES = frozenset({
    "image/png", "image/jpeg", "image/gif", "image/webp",
    "image/svg+xml", "image/bmp", "image/tiff",
})

SUPPORTED_AUDIO_TYPES = frozenset({
    "audio/webm", "audio/mpeg", "audio/mp3", "audio/wav",
    "audio/ogg", "audio/flac", "audio/aac",
})

SUPPORTED_DOCUMENT_TYPES = frozenset({
    "application/pdf", "text/plain", "text/markdown",
    "text/csv", "application/json",
})

ALL_SUPPORTED_TYPES = SUPPORTED_IMAGE_TYPES | SUPPORTED_AUDIO_TYPES | SUPPORTED_DOCUMENT_TYPES

# Max attachment size: 50 MB
MAX_ATTACHMENT_SIZE = 50 * 1024 * 1024


@dataclass
class Attachment:
    """A binary attachment linked to a memory.

    Attributes
    ----------
    attachment_id : str
        Unique identifier (auto-generated).
    memory_id : str
        ID of the parent memory.
    filename : str
        Original filename.
    mime_type : str
        MIME content type.
    size : int
        Size in bytes.
    sha256 : str
        SHA-256 hex digest of the content.
    description : str
        Human-readable description.
    metadata : dict
        Extracted metadata (EXIF, duration, dimensions, etc.).
    created_at : float
        Unix timestamp of creation.
    """

    attachment_id: str = field(default_factory=lambda: f"att_{uuid4().hex[:12]}")
    memory_id: str = ""
    filename: str = ""
    mime_type: str = "application/octet-stream"
    size: int = 0
    sha256: str = ""
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attachment_id": self.attachment_id,
            "memory_id": self.memory_id,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "size": self.size,
            "sha256": self.sha256,
            "description": self.description,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Attachment:
        return cls(
            attachment_id=d.get("attachment_id", ""),
            memory_id=d.get("memory_id", ""),
            filename=d.get("filename", ""),
            mime_type=d.get("mime_type", "application/octet-stream"),
            size=d.get("size", 0),
            sha256=d.get("sha256", ""),
            description=d.get("description", ""),
            metadata=d.get("metadata", {}),
            created_at=d.get("created_at", 0.0),
        )


@dataclass(frozen=True)
class AttachmentRef:
    """Lightweight reference to an attachment (stored in memory markdown)."""

    attachment_id: str
    mime_type: str
    filename: str
    size: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "attachment_id": self.attachment_id,
            "mime_type": self.mime_type,
            "filename": self.filename,
            "size": self.size,
            "sha256": self.sha256,
        }
