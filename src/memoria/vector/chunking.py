"""Smart text splitting for embedding."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class TextChunk:
    text: str
    start: int
    end: int
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Generic text chunking
# ---------------------------------------------------------------------------


def chunk_text(
    text: str,
    max_chars: int = 500,
    overlap: int = 50,
) -> list[TextChunk]:
    """Split text into overlapping chunks.

    Strategy:
    1. Split by paragraph boundaries first.
    2. If a paragraph > *max_chars*, split by sentences.
    3. If a sentence > *max_chars*, split by words.
    4. Merge small consecutive pieces up to *max_chars*.
    5. Apply *overlap* between chunks for context continuity.
    """
    if not text or not text.strip():
        return []

    paragraphs = re.split(r"\n\s*\n", text)
    pieces: list[str] = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_chars:
            pieces.append(para)
        else:
            pieces.extend(_split_long(para, max_chars))

    # Merge small consecutive pieces
    merged = _merge_pieces(pieces, max_chars)

    # Build chunks with positional info
    chunks: list[TextChunk] = []
    offset = 0
    for i, piece in enumerate(merged):
        start = text.find(piece, offset)
        if start == -1:
            start = offset
        end = start + len(piece)
        chunks.append(TextChunk(text=piece, start=start, end=end))
        # Move offset forward, but step back by overlap for next search
        offset = max(start + 1, end - overlap)

    return chunks


# ---------------------------------------------------------------------------
# Markdown-aware chunking
# ---------------------------------------------------------------------------

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def chunk_markdown(text: str, max_chars: int = 500) -> list[TextChunk]:
    """Split markdown by headers, preserving structure."""
    if not text or not text.strip():
        return []

    sections: list[tuple[int, str]] = []
    last_pos = 0
    for m in _HEADER_RE.finditer(text):
        if m.start() > last_pos:
            sections.append((last_pos, text[last_pos : m.start()].strip()))
        last_pos = m.start()

    # Remainder after last header
    if last_pos < len(text):
        sections.append((last_pos, text[last_pos:].strip()))

    chunks: list[TextChunk] = []
    for pos, section in sections:
        if not section:
            continue
        if len(section) <= max_chars:
            chunks.append(
                TextChunk(text=section, start=pos, end=pos + len(section))
            )
        else:
            for sub in chunk_text(section, max_chars=max_chars, overlap=0):
                chunks.append(
                    TextChunk(
                        text=sub.text,
                        start=pos + sub.start,
                        end=pos + sub.end,
                    )
                )
    return chunks


# ---------------------------------------------------------------------------
# Code-aware chunking
# ---------------------------------------------------------------------------

_CODE_BOUNDARY_RE = re.compile(
    r"^(?:def |class |async def |function |export |const |let |var )",
    re.MULTILINE,
)


def chunk_code(text: str, max_chars: int = 500) -> list[TextChunk]:
    """Split code by function/class boundaries."""
    if not text or not text.strip():
        return []

    boundaries = [m.start() for m in _CODE_BOUNDARY_RE.finditer(text)]
    if not boundaries:
        return chunk_text(text, max_chars=max_chars, overlap=0)

    # Ensure we capture any preamble before the first boundary
    if boundaries[0] != 0:
        boundaries.insert(0, 0)

    sections: list[tuple[int, str]] = []
    for i, start in enumerate(boundaries):
        end = boundaries[i + 1] if i + 1 < len(boundaries) else len(text)
        section = text[start:end].strip()
        if section:
            sections.append((start, section))

    chunks: list[TextChunk] = []
    for pos, section in sections:
        if len(section) <= max_chars:
            chunks.append(
                TextChunk(text=section, start=pos, end=pos + len(section))
            )
        else:
            for sub in chunk_text(section, max_chars=max_chars, overlap=0):
                chunks.append(
                    TextChunk(
                        text=sub.text,
                        start=pos + sub.start,
                        end=pos + sub.end,
                    )
                )
    return chunks


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _split_long(text: str, max_chars: int) -> list[str]:
    """Split a long paragraph into sentence- or word-level pieces."""
    sentences = _SENTENCE_RE.split(text)
    pieces: list[str] = []
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if len(sent) <= max_chars:
            pieces.append(sent)
        else:
            # Last resort: word-level splitting
            words = sent.split()
            chunk: list[str] = []
            length = 0
            for w in words:
                if length + len(w) + 1 > max_chars and chunk:
                    pieces.append(" ".join(chunk))
                    chunk = []
                    length = 0
                chunk.append(w)
                length += len(w) + 1
            if chunk:
                pieces.append(" ".join(chunk))
    return pieces


def _merge_pieces(pieces: list[str], max_chars: int) -> list[str]:
    """Merge consecutive small pieces until they approach *max_chars*."""
    if not pieces:
        return []
    merged: list[str] = [pieces[0]]
    for piece in pieces[1:]:
        if len(merged[-1]) + len(piece) + 2 <= max_chars:
            merged[-1] = merged[-1] + "\n\n" + piece
        else:
            merged.append(piece)
    return merged
