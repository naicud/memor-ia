"""SQLite-based vector storage with optional sqlite-vec acceleration."""

from __future__ import annotations

import json
import math
import sqlite3
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import sqlite_vec

    HAS_SQLITE_VEC = True
except ImportError:
    HAS_SQLITE_VEC = False


@dataclass
class VectorRecord:
    id: str
    embedding: list[float]
    content: str
    metadata: dict = field(default_factory=dict)
    distance: float = 0.0


class VectorClient:
    """SQLite-based vector storage with optional sqlite-vec acceleration."""

    def __init__(self, db_path: str | Path | None = None, dimension: int = 384):
        self.dimension = dimension
        if db_path:
            self.db_path: Path | None = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        else:
            self.db_path = None
            self.conn = sqlite3.connect(":memory:", check_same_thread=False)

        self._use_vec = False
        if HAS_SQLITE_VEC:
            try:
                self.conn.enable_load_extension(True)
                sqlite_vec.load(self.conn)
                self._use_vec = True
            except (AttributeError, OSError):
                # enable_load_extension unavailable or extension load failed
                self._use_vec = False

        self._init_tables()

    def _init_tables(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS vec_metadata (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                user_id TEXT,
                memory_type TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        if self._use_vec:
            self.conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_embeddings
                USING vec0(id TEXT PRIMARY KEY, embedding float[{self.dimension}])
            """)
        else:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS vec_embeddings (
                    id TEXT PRIMARY KEY,
                    embedding TEXT NOT NULL
                )
            """)
        self.conn.commit()

    def insert(self, record: VectorRecord) -> None:
        """Insert a vector record."""
        self.conn.execute(
            "INSERT OR REPLACE INTO vec_metadata (id, content, metadata, user_id, memory_type) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                record.id,
                record.content,
                json.dumps(record.metadata),
                record.metadata.get("user_id"),
                record.metadata.get("memory_type"),
            ),
        )

        if self._use_vec:
            # sqlite-vec virtual tables don't support INSERT OR REPLACE;
            # delete first, then insert.
            blob = _floats_to_blob(record.embedding)
            self.conn.execute("DELETE FROM vec_embeddings WHERE id = ?", (record.id,))
            self.conn.execute(
                "INSERT INTO vec_embeddings (id, embedding) VALUES (?, ?)",
                (record.id, blob),
            )
        else:
            self.conn.execute(
                "INSERT OR REPLACE INTO vec_embeddings (id, embedding) VALUES (?, ?)",
                (record.id, json.dumps(record.embedding)),
            )
        self.conn.commit()

    def insert_batch(self, records: list[VectorRecord]) -> None:
        """Insert multiple vector records in a single transaction."""
        if not records:
            return

        self.conn.executemany(
            "INSERT OR REPLACE INTO vec_metadata (id, content, metadata, user_id, memory_type) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (
                    r.id,
                    r.content,
                    json.dumps(r.metadata),
                    r.metadata.get("user_id"),
                    r.metadata.get("memory_type"),
                )
                for r in records
            ],
        )

        if self._use_vec:
            # sqlite-vec virtual tables don't support INSERT OR REPLACE;
            # delete first, then insert.
            self.conn.executemany(
                "DELETE FROM vec_embeddings WHERE id = ?",
                [(r.id,) for r in records],
            )
            self.conn.executemany(
                "INSERT INTO vec_embeddings (id, embedding) VALUES (?, ?)",
                [(r.id, _floats_to_blob(r.embedding)) for r in records],
            )
        else:
            self.conn.executemany(
                "INSERT OR REPLACE INTO vec_embeddings (id, embedding) VALUES (?, ?)",
                [(r.id, json.dumps(r.embedding)) for r in records],
            )
        self.conn.commit()

    def search(
        self,
        query_embedding: list[float],
        limit: int = 5,
        offset: int = 0,
        user_id: str | None = None,
        memory_type: str | None = None,
    ) -> list[VectorRecord]:
        """Find nearest neighbours."""
        if self._use_vec:
            return self._search_vec(query_embedding, limit, offset, user_id, memory_type)
        return self._search_python(query_embedding, limit, offset, user_id, memory_type)

    def _search_vec(
        self,
        query_embedding: list[float],
        limit: int,
        offset: int,
        user_id: str | None,
        memory_type: str | None,
    ) -> list[VectorRecord]:
        blob = _floats_to_blob(query_embedding)
        rows = self.conn.execute(
            "SELECT id, distance FROM vec_embeddings "
            "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
            (blob, (limit + offset) * 5),
        ).fetchall()

        results: list[VectorRecord] = []
        for rid, dist in rows:
            meta_row = self.conn.execute(
                "SELECT content, metadata, user_id, memory_type FROM vec_metadata WHERE id = ?",
                (rid,),
            ).fetchone()
            if meta_row is None:
                continue
            content, raw_meta, row_uid, row_mt = meta_row
            if user_id and row_uid != user_id:
                continue
            if memory_type and row_mt != memory_type:
                continue
            metadata = json.loads(raw_meta) if raw_meta else {}

            emb_row = self.conn.execute(
                "SELECT embedding FROM vec_embeddings WHERE id = ?", (rid,)
            ).fetchone()
            embedding = _blob_to_floats(emb_row[0]) if emb_row else []

            results.append(
                VectorRecord(
                    id=rid,
                    embedding=embedding,
                    content=content,
                    metadata=metadata,
                    distance=dist,
                )
            )
            if len(results) >= limit + offset:
                break
        return results[offset:]

    def _search_python(
        self,
        query_embedding: list[float],
        limit: int,
        offset: int,
        user_id: str | None,
        memory_type: str | None,
    ) -> list[VectorRecord]:
        where_clauses = ["1=1"]
        params: list[str] = []
        if user_id:
            where_clauses.append("m.user_id = ?")
            params.append(user_id)
        if memory_type:
            where_clauses.append("m.memory_type = ?")
            params.append(memory_type)

        where_sql = " AND ".join(where_clauses)
        rows = self.conn.execute(
            f"SELECT e.id, e.embedding, m.content, m.metadata "
            f"FROM vec_embeddings e "
            f"JOIN vec_metadata m ON e.id = m.id "
            f"WHERE {where_sql}",
            params,
        ).fetchall()

        scored: list[tuple[float, VectorRecord]] = []
        for rid, raw_emb, content, raw_meta in rows:
            emb = json.loads(raw_emb)
            sim = _cosine_similarity(query_embedding, emb)
            dist = 1.0 - sim
            metadata = json.loads(raw_meta) if raw_meta else {}
            scored.append(
                (
                    dist,
                    VectorRecord(
                        id=rid,
                        embedding=emb,
                        content=content,
                        metadata=metadata,
                        distance=dist,
                    ),
                )
            )

        scored.sort(key=lambda t: t[0])
        return [rec for _, rec in scored[offset:offset + limit]]

    def delete(self, record_id: str) -> None:
        """Delete a record by id."""
        self.conn.execute("DELETE FROM vec_metadata WHERE id = ?", (record_id,))
        self.conn.execute("DELETE FROM vec_embeddings WHERE id = ?", (record_id,))
        self.conn.commit()

    def get(self, record_id: str) -> Optional[VectorRecord]:
        """Get a single record by id."""
        meta_row = self.conn.execute(
            "SELECT content, metadata FROM vec_metadata WHERE id = ?", (record_id,)
        ).fetchone()
        if meta_row is None:
            return None

        content, raw_meta = meta_row
        metadata = json.loads(raw_meta) if raw_meta else {}

        emb_row = self.conn.execute(
            "SELECT embedding FROM vec_embeddings WHERE id = ?", (record_id,)
        ).fetchone()
        if emb_row is None:
            return None

        if self._use_vec:
            embedding = _blob_to_floats(emb_row[0])
        else:
            embedding = json.loads(emb_row[0])

        return VectorRecord(
            id=record_id,
            embedding=embedding,
            content=content,
            metadata=metadata,
        )

    def count(self) -> int:
        """Count total records."""
        row = self.conn.execute("SELECT COUNT(*) FROM vec_metadata").fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> VectorClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Pure Python cosine similarity."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _floats_to_blob(vec: list[float]) -> bytes:
    """Pack list of floats to a little-endian binary blob for sqlite-vec."""
    return struct.pack(f"<{len(vec)}f", *vec)


def _blob_to_floats(blob: bytes) -> list[float]:
    """Unpack a little-endian binary blob back to a list of floats."""
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob))
