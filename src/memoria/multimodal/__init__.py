"""Multi-modal memory module for MEMORIA.

Provides binary attachment storage, metadata extraction, and indexing
so AI agents can work with images, audio, files — not just text.
"""

from memoria.multimodal.metadata import extract_metadata
from memoria.multimodal.storage import AttachmentStore
from memoria.multimodal.types import Attachment, AttachmentRef

__all__ = [
    "Attachment",
    "AttachmentRef",
    "AttachmentStore",
    "extract_metadata",
]
