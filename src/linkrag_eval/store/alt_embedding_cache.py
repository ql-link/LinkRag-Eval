"""Golden V2 alt embedding SQLite sidecar。

用于候选池独立 embedding 来源。它只缓存 eval chunk 的 alt embedding 向量,
不写正式 Qdrant,也不参与被测系统主评测。
"""

from __future__ import annotations

import asyncio
import sqlite3
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class AltEmbeddingPoint:
    chunk_id: str
    dataset_id: int
    doc_id: int
    content_hash: str
    vector: list[float]


class AltEmbeddingCache:
    """SQLite alt embedding cache,主键为 ``(chunk_id, model_key)``。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    async def ensure_schema(self) -> None:
        await asyncio.to_thread(self._ensure_schema_sync)

    async def fetch_vectors(self, chunks: Sequence[object], *, model_key: str) -> dict[str, list[float]]:
        items = list(chunks)
        if not items:
            return {}
        return await asyncio.to_thread(self._fetch_vectors_sync, items, model_key)

    async def upsert_vectors(self, points: Sequence[AltEmbeddingPoint], *, model_key: str) -> int:
        pts = list(points)
        if not pts:
            return 0
        return await asyncio.to_thread(self._upsert_vectors_sync, pts, model_key)

    async def count(self, *, model_key: str, dataset_ids: Sequence[int] | None = None) -> int:
        return await asyncio.to_thread(self._count_sync, model_key, list(dataset_ids or []))

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.path)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=NORMAL")
        con.execute("PRAGMA temp_store=MEMORY")
        return con

    def _ensure_schema_sync(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS alt_embedding_cache(
                    chunk_id TEXT NOT NULL,
                    model_key TEXT NOT NULL,
                    dataset_id INTEGER NOT NULL,
                    doc_id INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    dim INTEGER NOT NULL,
                    vector BLOB NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(chunk_id, model_key)
                )
                """
            )
            con.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_alt_embedding_dataset_model
                ON alt_embedding_cache(dataset_id, model_key)
                """
            )

    def _fetch_vectors_sync(self, chunks: list[object], model_key: str) -> dict[str, list[float]]:
        self._ensure_schema_sync()
        expected_hash = {str(c.chunk_id): str(c.content_hash) for c in chunks}
        out: dict[str, list[float]] = {}
        with self._connect() as con:
            for batch in _batched(list(expected_hash), 800):
                placeholders = ",".join("?" for _ in batch)
                rows = con.execute(
                    f"""
                    SELECT chunk_id, content_hash, dim, vector
                    FROM alt_embedding_cache
                    WHERE model_key = ? AND chunk_id IN ({placeholders})
                    """,
                    [model_key, *batch],
                ).fetchall()
                for chunk_id, content_hash, dim, blob in rows:
                    cid = str(chunk_id)
                    if expected_hash.get(cid) != str(content_hash):
                        continue
                    vec = _blob_to_vector(blob)
                    if len(vec) == int(dim):
                        out[cid] = vec
        return out

    def _upsert_vectors_sync(self, points: list[AltEmbeddingPoint], model_key: str) -> int:
        self._ensure_schema_sync()
        with self._connect() as con:
            con.executemany(
                """
                INSERT INTO alt_embedding_cache(
                    chunk_id, model_key, dataset_id, doc_id, content_hash, dim, vector, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chunk_id, model_key) DO UPDATE SET
                    dataset_id = excluded.dataset_id,
                    doc_id = excluded.doc_id,
                    content_hash = excluded.content_hash,
                    dim = excluded.dim,
                    vector = excluded.vector,
                    updated_at = CURRENT_TIMESTAMP
                """,
                [
                    (
                        p.chunk_id,
                        model_key,
                        int(p.dataset_id),
                        int(p.doc_id),
                        p.content_hash,
                        len(p.vector),
                        _vector_to_blob(p.vector),
                    )
                    for p in points
                ],
            )
        return len(points)

    def _count_sync(self, model_key: str, dataset_ids: list[int]) -> int:
        self._ensure_schema_sync()
        with self._connect() as con:
            if not dataset_ids:
                return int(
                    con.execute(
                        "SELECT COUNT(*) FROM alt_embedding_cache WHERE model_key = ?",
                        (model_key,),
                    ).fetchone()[0]
                )
            placeholders = ",".join("?" for _ in dataset_ids)
            return int(
                con.execute(
                    f"""
                    SELECT COUNT(*) FROM alt_embedding_cache
                    WHERE model_key = ? AND dataset_id IN ({placeholders})
                    """,
                    [model_key, *dataset_ids],
                ).fetchone()[0]
            )


def alt_embedding_model_key(*, base_url: str, model: str, dim: int) -> str:
    """非密钥模型指纹。用于区分不同 alt embedding 空间。"""
    return f"{model.strip()}@{base_url.rstrip('/')}#dim={int(dim)}"


def _vector_to_blob(values: Sequence[float]) -> bytes:
    arr = array("f", [float(v) for v in values])
    return arr.tobytes()


def _blob_to_vector(blob: bytes) -> list[float]:
    arr = array("f")
    arr.frombytes(blob)
    return [float(v) for v in arr]


def _batched(items: list[str], n: int):
    for start in range(0, len(items), n):
        yield items[start : start + n]
