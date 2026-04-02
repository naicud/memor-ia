"""Binary attachment storage.

Stores attachment blobs in a flat directory alongside memory files.
Uses content-addressable storage (SHA-256) with metadata sidecar JSON.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from memoria.multimodal.types import (
    MAX_ATTACHMENT_SIZE,
    Attachment,
    AttachmentRef,
)


class AttachmentStore:
    """File-system backed attachment storage.

    Layout::

        {base_dir}/
        ├── blobs/            # Binary content (named by attachment_id)
        │   ├── att_abc123.png
        │   └── att_def456.webm
        └── meta/             # JSON metadata sidecars
            ├── att_abc123.json
            └── att_def456.json
    """

    def __init__(self, base_dir: str | Path) -> None:
        self._base = Path(base_dir)
        self._blobs = self._base / "blobs"
        self._meta = self._base / "meta"
        self._blobs.mkdir(parents=True, exist_ok=True)
        self._meta.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        return self._base

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    def store(
        self,
        data: bytes,
        *,
        memory_id: str,
        filename: str,
        mime_type: str = "application/octet-stream",
        description: str = "",
        attachment_id: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> Attachment:
        """Store a binary attachment.

        Parameters
        ----------
        data : bytes
            Raw binary content.
        memory_id : str
            Parent memory ID.
        filename : str
            Original filename.
        mime_type : str
            MIME type of the content.
        description : str
            Human-readable description.
        attachment_id : str | None
            Custom ID (auto-generated if None).
        extra_metadata : dict | None
            Additional metadata to merge.

        Returns
        -------
        Attachment
            The stored attachment record.

        Raises
        ------
        ValueError
            If the data exceeds MAX_ATTACHMENT_SIZE or mime_type is unsupported.
        """
        if len(data) > MAX_ATTACHMENT_SIZE:
            raise ValueError(
                f"Attachment too large: {len(data)} bytes "
                f"(max: {MAX_ATTACHMENT_SIZE} bytes)"
            )

        sha = hashlib.sha256(data).hexdigest()

        att = Attachment(
            memory_id=memory_id,
            filename=filename,
            mime_type=mime_type,
            size=len(data),
            sha256=sha,
            description=description,
            metadata=extra_metadata or {},
        )
        if attachment_id:
            att.attachment_id = attachment_id

        # Derive extension from filename
        ext = Path(filename).suffix or ""
        blob_name = f"{att.attachment_id}{ext}"

        # Write blob
        blob_path = self._blobs / blob_name
        blob_path.write_bytes(data)

        # Write metadata sidecar
        meta_path = self._meta / f"{att.attachment_id}.json"
        meta_data = att.to_dict()
        meta_data["blob_filename"] = blob_name
        meta_path.write_text(json.dumps(meta_data, indent=2, default=str))

        return att

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------

    def get_metadata(self, attachment_id: str) -> Attachment | None:
        """Get attachment metadata by ID."""
        meta_path = self._meta / f"{attachment_id}.json"
        if not meta_path.exists():
            return None
        data = json.loads(meta_path.read_text())
        return Attachment.from_dict(data)

    def get_blob(self, attachment_id: str) -> bytes | None:
        """Get attachment binary content by ID."""
        meta = self._get_meta_dict(attachment_id)
        if meta is None:
            return None
        blob_name = meta.get("blob_filename", "")
        blob_path = self._blobs / blob_name
        if not blob_path.exists():
            return None
        return blob_path.read_bytes()

    def _get_meta_dict(self, attachment_id: str) -> dict | None:
        meta_path = self._meta / f"{attachment_id}.json"
        if not meta_path.exists():
            return None
        return json.loads(meta_path.read_text())

    # ------------------------------------------------------------------
    # List / search
    # ------------------------------------------------------------------

    def list_by_memory(self, memory_id: str) -> list[Attachment]:
        """List all attachments for a given memory."""
        results = []
        for meta_file in self._meta.glob("*.json"):
            data = json.loads(meta_file.read_text())
            if data.get("memory_id") == memory_id:
                results.append(Attachment.from_dict(data))
        return sorted(results, key=lambda a: a.created_at)

    def list_all(self, *, limit: int = 100, offset: int = 0) -> list[Attachment]:
        """List all attachments with pagination."""
        all_meta = sorted(self._meta.glob("*.json"))
        page = all_meta[offset : offset + limit]
        results = []
        for meta_file in page:
            data = json.loads(meta_file.read_text())
            results.append(Attachment.from_dict(data))
        return results

    def count(self) -> int:
        """Return total number of stored attachments."""
        return len(list(self._meta.glob("*.json")))

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, attachment_id: str) -> bool:
        """Delete an attachment (blob + metadata).  Returns True if found."""
        meta = self._get_meta_dict(attachment_id)
        if meta is None:
            return False

        # Remove blob
        blob_name = meta.get("blob_filename", "")
        blob_path = self._blobs / blob_name
        if blob_path.exists():
            blob_path.unlink()

        # Remove metadata
        meta_path = self._meta / f"{attachment_id}.json"
        if meta_path.exists():
            meta_path.unlink()

        return True

    def delete_by_memory(self, memory_id: str) -> int:
        """Delete all attachments for a memory.  Returns count deleted."""
        attachments = self.list_by_memory(memory_id)
        for att in attachments:
            self.delete(att.attachment_id)
        return len(attachments)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def make_ref(self, attachment: Attachment) -> AttachmentRef:
        """Create a lightweight reference from a full attachment."""
        return AttachmentRef(
            attachment_id=attachment.attachment_id,
            mime_type=attachment.mime_type,
            filename=attachment.filename,
            size=attachment.size,
            sha256=attachment.sha256,
        )

    def disk_usage(self) -> int:
        """Return total disk usage in bytes for all blobs."""
        total = 0
        for blob in self._blobs.iterdir():
            if blob.is_file():
                total += blob.stat().st_size
        return total
