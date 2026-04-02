"""Metadata extraction for multi-modal attachments.

Extracts basic metadata from images, audio, and documents without
requiring heavy external dependencies (PIL, ffprobe, etc. are optional).
Falls back gracefully when libraries are not available.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def extract_metadata(
    data: bytes,
    filename: str,
    mime_type: str,
) -> dict[str, Any]:
    """Extract metadata from binary content.

    Returns a dict with mime-type-specific fields:
    - Images: width, height, format (if PIL available)
    - Audio: duration, channels, sample_rate (if mutagen available)
    - Documents: line_count, char_count, word_count (for text types)

    Falls back to basic metadata (size, extension) if no library is available.
    """
    meta: dict[str, Any] = {
        "size_bytes": len(data),
        "extension": Path(filename).suffix.lower(),
    }

    if mime_type.startswith("image/"):
        meta.update(_extract_image_metadata(data, mime_type))
    elif mime_type.startswith("audio/"):
        meta.update(_extract_audio_metadata(data, mime_type))
    elif mime_type.startswith("text/") or mime_type in (
        "application/json",
        "application/pdf",
    ):
        meta.update(_extract_text_metadata(data, mime_type))

    return meta


def _extract_image_metadata(data: bytes, mime_type: str) -> dict[str, Any]:
    """Try to extract image dimensions using PIL, fall back to basic info."""
    meta: dict[str, Any] = {"type_family": "image"}
    try:
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(data))
        meta["width"] = img.width
        meta["height"] = img.height
        meta["format"] = img.format or "unknown"
        meta["mode"] = img.mode
    except (ImportError, Exception):
        # PIL not available or image can't be parsed
        meta["width"] = None
        meta["height"] = None
        meta["format"] = mime_type.split("/")[-1]
    return meta


def _extract_audio_metadata(data: bytes, mime_type: str) -> dict[str, Any]:
    """Try to extract audio metadata, fall back to basic info."""
    meta: dict[str, Any] = {"type_family": "audio"}
    try:
        import io

        import mutagen

        f = io.BytesIO(data)
        audio = mutagen.File(f)
        if audio is not None:
            meta["duration_seconds"] = round(audio.info.length, 2) if hasattr(audio.info, "length") else None
            meta["channels"] = getattr(audio.info, "channels", None)
            meta["sample_rate"] = getattr(audio.info, "sample_rate", None)
            meta["bitrate"] = getattr(audio.info, "bitrate", None)
        else:
            meta["duration_seconds"] = None
    except (ImportError, Exception):
        meta["duration_seconds"] = None
        meta["format"] = mime_type.split("/")[-1]
    return meta


def _extract_text_metadata(data: bytes, mime_type: str) -> dict[str, Any]:
    """Extract metadata from text-based content."""
    meta: dict[str, Any] = {"type_family": "document"}
    try:
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        meta["line_count"] = len(lines)
        meta["char_count"] = len(text)
        meta["word_count"] = len(text.split())
        if mime_type == "application/json":
            import json
            json.loads(text)
            meta["valid_json"] = True
    except Exception:
        meta["line_count"] = None
        meta["char_count"] = None
    return meta
