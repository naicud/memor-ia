"""Tests for the multi-modal memory (attachment) module.

Covers: types, storage, metadata extraction, Memoria integration.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from memoria.multimodal.metadata import extract_metadata
from memoria.multimodal.storage import AttachmentStore
from memoria.multimodal.types import (
    ALL_SUPPORTED_TYPES,
    MAX_ATTACHMENT_SIZE,
    Attachment,
    AttachmentRef,
)

# ═══════════════════════════════════════════════════════════════════════════
# Types
# ═══════════════════════════════════════════════════════════════════════════


class TestAttachment:
    """Tests for Attachment dataclass."""

    def test_defaults(self):
        att = Attachment()
        assert att.attachment_id.startswith("att_")
        assert att.memory_id == ""
        assert att.mime_type == "application/octet-stream"
        assert att.size == 0

    def test_to_dict(self):
        att = Attachment(
            attachment_id="att_test",
            memory_id="m1",
            filename="test.png",
            mime_type="image/png",
            size=1024,
            sha256="abc123",
        )
        d = att.to_dict()
        assert d["attachment_id"] == "att_test"
        assert d["memory_id"] == "m1"
        assert d["mime_type"] == "image/png"
        assert d["size"] == 1024

    def test_from_dict(self):
        d = {
            "attachment_id": "att_x",
            "memory_id": "m2",
            "filename": "doc.pdf",
            "mime_type": "application/pdf",
            "size": 2048,
            "sha256": "def456",
        }
        att = Attachment.from_dict(d)
        assert att.attachment_id == "att_x"
        assert att.filename == "doc.pdf"

    def test_from_dict_missing_fields(self):
        att = Attachment.from_dict({})
        assert att.attachment_id == ""
        assert att.mime_type == "application/octet-stream"

    def test_roundtrip(self):
        att = Attachment(
            attachment_id="att_rt",
            memory_id="m3",
            filename="audio.webm",
            mime_type="audio/webm",
            size=5000,
            sha256="xyz",
            description="voice note",
            metadata={"duration": 12.5},
        )
        d = att.to_dict()
        att2 = Attachment.from_dict(d)
        assert att2.attachment_id == att.attachment_id
        assert att2.metadata == {"duration": 12.5}


class TestAttachmentRef:
    """Tests for AttachmentRef."""

    def test_create_and_dict(self):
        ref = AttachmentRef(
            attachment_id="att_1",
            mime_type="image/png",
            filename="pic.png",
            size=100,
            sha256="abc",
        )
        d = ref.to_dict()
        assert d["attachment_id"] == "att_1"
        assert d["size"] == 100

    def test_frozen(self):
        ref = AttachmentRef("a", "b", "c", 0, "d")
        with pytest.raises(AttributeError):
            ref.size = 999


class TestSupportedTypes:
    """Tests for type constants."""

    def test_image_types_exist(self):
        assert "image/png" in ALL_SUPPORTED_TYPES
        assert "image/jpeg" in ALL_SUPPORTED_TYPES

    def test_audio_types_exist(self):
        assert "audio/webm" in ALL_SUPPORTED_TYPES
        assert "audio/mp3" in ALL_SUPPORTED_TYPES

    def test_document_types_exist(self):
        assert "application/pdf" in ALL_SUPPORTED_TYPES
        assert "text/plain" in ALL_SUPPORTED_TYPES

    def test_max_size(self):
        assert MAX_ATTACHMENT_SIZE == 50 * 1024 * 1024


# ═══════════════════════════════════════════════════════════════════════════
# AttachmentStore
# ═══════════════════════════════════════════════════════════════════════════


class TestAttachmentStore:
    """Tests for AttachmentStore file operations."""

    def test_store_and_retrieve_metadata(self, tmp_path):
        store = AttachmentStore(tmp_path / "att")
        data = b"hello world"
        att = store.store(data, memory_id="m1", filename="test.txt", mime_type="text/plain")
        assert att.memory_id == "m1"
        assert att.filename == "test.txt"
        assert att.size == len(data)
        assert att.sha256 == hashlib.sha256(data).hexdigest()

        meta = store.get_metadata(att.attachment_id)
        assert meta is not None
        assert meta.attachment_id == att.attachment_id

    def test_store_and_retrieve_blob(self, tmp_path):
        store = AttachmentStore(tmp_path / "att")
        data = b"\x89PNG fake image data"
        att = store.store(data, memory_id="m1", filename="img.png", mime_type="image/png")
        blob = store.get_blob(att.attachment_id)
        assert blob == data

    def test_store_with_custom_id(self, tmp_path):
        store = AttachmentStore(tmp_path / "att")
        att = store.store(
            b"data", memory_id="m1", filename="f.txt",
            attachment_id="custom_id_123",
        )
        assert att.attachment_id == "custom_id_123"

    def test_store_with_description(self, tmp_path):
        store = AttachmentStore(tmp_path / "att")
        att = store.store(
            b"data", memory_id="m1", filename="f.txt",
            description="A test file",
        )
        assert att.description == "A test file"

    def test_store_too_large_raises(self, tmp_path):
        store = AttachmentStore(tmp_path / "att")
        # Don't actually allocate 50MB, just test the check
        with patch.object(store, 'store', wraps=store.store):
            with pytest.raises(ValueError, match="too large"):
                store.store(
                    b"x" * (MAX_ATTACHMENT_SIZE + 1),
                    memory_id="m1",
                    filename="huge.bin",
                )

    def test_get_metadata_nonexistent(self, tmp_path):
        store = AttachmentStore(tmp_path / "att")
        assert store.get_metadata("nonexistent") is None

    def test_get_blob_nonexistent(self, tmp_path):
        store = AttachmentStore(tmp_path / "att")
        assert store.get_blob("nonexistent") is None

    def test_list_by_memory(self, tmp_path):
        store = AttachmentStore(tmp_path / "att")
        store.store(b"a", memory_id="m1", filename="a.txt")
        store.store(b"b", memory_id="m1", filename="b.txt")
        store.store(b"c", memory_id="m2", filename="c.txt")

        m1_atts = store.list_by_memory("m1")
        assert len(m1_atts) == 2
        m2_atts = store.list_by_memory("m2")
        assert len(m2_atts) == 1

    def test_list_all(self, tmp_path):
        store = AttachmentStore(tmp_path / "att")
        store.store(b"a", memory_id="m1", filename="a.txt")
        store.store(b"b", memory_id="m1", filename="b.txt")
        store.store(b"c", memory_id="m2", filename="c.txt")

        all_atts = store.list_all()
        assert len(all_atts) == 3

    def test_list_all_pagination(self, tmp_path):
        store = AttachmentStore(tmp_path / "att")
        for i in range(5):
            store.store(f"data{i}".encode(), memory_id="m1", filename=f"f{i}.txt")

        page1 = store.list_all(limit=2, offset=0)
        page2 = store.list_all(limit=2, offset=2)
        page3 = store.list_all(limit=2, offset=4)
        assert len(page1) == 2
        assert len(page2) == 2
        assert len(page3) == 1

    def test_count(self, tmp_path):
        store = AttachmentStore(tmp_path / "att")
        assert store.count() == 0
        store.store(b"a", memory_id="m1", filename="a.txt")
        store.store(b"b", memory_id="m1", filename="b.txt")
        assert store.count() == 2

    def test_delete(self, tmp_path):
        store = AttachmentStore(tmp_path / "att")
        att = store.store(b"data", memory_id="m1", filename="f.txt")
        assert store.delete(att.attachment_id) is True
        assert store.get_metadata(att.attachment_id) is None
        assert store.get_blob(att.attachment_id) is None

    def test_delete_nonexistent(self, tmp_path):
        store = AttachmentStore(tmp_path / "att")
        assert store.delete("nope") is False

    def test_delete_by_memory(self, tmp_path):
        store = AttachmentStore(tmp_path / "att")
        store.store(b"a", memory_id="m1", filename="a.txt")
        store.store(b"b", memory_id="m1", filename="b.txt")
        store.store(b"c", memory_id="m2", filename="c.txt")

        count = store.delete_by_memory("m1")
        assert count == 2
        assert store.count() == 1

    def test_make_ref(self, tmp_path):
        store = AttachmentStore(tmp_path / "att")
        att = store.store(b"data", memory_id="m1", filename="f.txt")
        ref = store.make_ref(att)
        assert ref.attachment_id == att.attachment_id
        assert ref.sha256 == att.sha256

    def test_disk_usage(self, tmp_path):
        store = AttachmentStore(tmp_path / "att")
        store.store(b"x" * 100, memory_id="m1", filename="a.bin")
        store.store(b"y" * 200, memory_id="m1", filename="b.bin")
        usage = store.disk_usage()
        assert usage == 300

    def test_directory_structure(self, tmp_path):
        store = AttachmentStore(tmp_path / "att")
        store.store(b"data", memory_id="m1", filename="test.txt")
        assert (tmp_path / "att" / "blobs").is_dir()
        assert (tmp_path / "att" / "meta").is_dir()

    def test_blob_extension_preserved(self, tmp_path):
        store = AttachmentStore(tmp_path / "att")
        store.store(b"png-data", memory_id="m1", filename="photo.png")
        # Blob file should have .png extension
        blobs = list((tmp_path / "att" / "blobs").iterdir())
        assert any(b.suffix == ".png" for b in blobs)


# ═══════════════════════════════════════════════════════════════════════════
# Metadata Extraction
# ═══════════════════════════════════════════════════════════════════════════


class TestMetadataExtraction:
    """Tests for metadata extraction."""

    def test_text_metadata(self):
        data = b"hello world\nsecond line\nthird"
        meta = extract_metadata(data, "test.txt", "text/plain")
        assert meta["size_bytes"] == len(data)
        assert meta["extension"] == ".txt"
        assert meta["line_count"] == 3
        assert meta["word_count"] == 5
        assert meta["type_family"] == "document"

    def test_json_metadata(self):
        data = b'{"key": "value"}'
        meta = extract_metadata(data, "data.json", "application/json")
        assert meta["valid_json"] is True
        assert meta["type_family"] == "document"

    def test_json_invalid(self):
        data = b"not json{{"
        meta = extract_metadata(data, "bad.json", "application/json")
        assert meta["type_family"] == "document"
        assert "valid_json" not in meta

    def test_image_without_pil(self):
        data = b"\x89PNG fake data"
        with patch.dict("sys.modules", {"PIL": None, "PIL.Image": None}):
            meta = extract_metadata(data, "img.png", "image/png")
        assert meta["type_family"] == "image"
        assert meta["extension"] == ".png"

    def test_audio_without_mutagen(self):
        data = b"fake audio"
        with patch.dict("sys.modules", {"mutagen": None}):
            meta = extract_metadata(data, "sound.mp3", "audio/mpeg")
        assert meta["type_family"] == "audio"

    def test_unknown_type(self):
        data = b"binary stuff"
        meta = extract_metadata(data, "unknown.bin", "application/octet-stream")
        assert meta["size_bytes"] == len(data)
        assert meta["extension"] == ".bin"

    def test_csv_metadata(self):
        data = b"name,age\nalice,30\nbob,25"
        meta = extract_metadata(data, "data.csv", "text/csv")
        assert meta["line_count"] == 3
        assert meta["type_family"] == "document"

    def test_markdown_metadata(self):
        data = b"# Title\n\nSome content here."
        meta = extract_metadata(data, "readme.md", "text/markdown")
        assert meta["word_count"] == 5


# ═══════════════════════════════════════════════════════════════════════════
# Memoria Integration
# ═══════════════════════════════════════════════════════════════════════════


class TestMemoriaMultimodal:
    """Tests for Memoria attachment methods."""

    def _make_memoria(self, tmp_path):
        from memoria import Memoria
        return Memoria(project_dir=str(tmp_path))

    def test_add_attachment(self, tmp_path):
        m = self._make_memoria(tmp_path)
        result = m.add_attachment(
            memory_id="m1",
            data=b"test content",
            filename="note.txt",
            mime_type="text/plain",
            description="A test note",
        )
        assert "attachment_id" in result
        assert result["memory_id"] == "m1"
        assert result["filename"] == "note.txt"
        assert result["size"] == 12

    def test_get_attachment(self, tmp_path):
        m = self._make_memoria(tmp_path)
        added = m.add_attachment("m1", b"data", "f.txt")
        result = m.get_attachment(added["attachment_id"])
        assert result is not None
        assert result["filename"] == "f.txt"

    def test_get_attachment_not_found(self, tmp_path):
        m = self._make_memoria(tmp_path)
        assert m.get_attachment("nonexistent") is None

    def test_get_attachment_data(self, tmp_path):
        m = self._make_memoria(tmp_path)
        added = m.add_attachment("m1", b"binary content", "f.bin")
        data = m.get_attachment_data(added["attachment_id"])
        assert data == b"binary content"

    def test_list_attachments_all(self, tmp_path):
        m = self._make_memoria(tmp_path)
        before = len(m.list_attachments())
        m.add_attachment("m1", b"a", "a.txt")
        m.add_attachment("m2", b"b", "b.txt")
        atts = m.list_attachments()
        assert len(atts) == before + 2

    def test_list_attachments_by_memory(self, tmp_path):
        m = self._make_memoria(tmp_path)
        unique_mem = f"m1-{id(self)}"
        m.add_attachment(unique_mem, b"a", "a.txt")
        m.add_attachment(unique_mem, b"b", "b.txt")
        m.add_attachment("m2-other", b"c", "c.txt")
        atts = m.list_attachments(memory_id=unique_mem)
        assert len(atts) == 2

    def test_delete_attachment(self, tmp_path):
        m = self._make_memoria(tmp_path)
        added = m.add_attachment("m1", b"data", "f.txt")
        result = m.delete_attachment(added["attachment_id"])
        assert result["status"] == "deleted"
        assert m.get_attachment(added["attachment_id"]) is None

    def test_delete_attachment_not_found(self, tmp_path):
        m = self._make_memoria(tmp_path)
        result = m.delete_attachment("nope")
        assert result["status"] == "not_found"

    def test_attachment_stats(self, tmp_path):
        m = self._make_memoria(tmp_path)
        before_count = m.attachment_stats()["total_attachments"]
        before_usage = m.attachment_stats()["disk_usage_bytes"]
        m.add_attachment("m1", b"x" * 100, "a.bin")
        m.add_attachment("m1", b"y" * 200, "b.bin")
        stats = m.attachment_stats()
        assert stats["total_attachments"] == before_count + 2
        assert stats["disk_usage_bytes"] == before_usage + 300

    def test_attachment_metadata_extraction(self, tmp_path):
        m = self._make_memoria(tmp_path)
        text_data = b"line1\nline2\nline3"
        result = m.add_attachment("m1", text_data, "notes.txt", mime_type="text/plain")
        assert result["metadata"]["line_count"] == 3
        assert result["metadata"]["word_count"] == 3
