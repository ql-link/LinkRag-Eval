"""eval 独立 Qdrant collection 的写入器(``EvalVectorStore``)。

只适配当前钉住的 LinkRag 单 collection 接口:复用 ``QdrantIndexStore`` 与 point 模型,
绕开生产写 pipeline,直接 upsert named dense / sparse 向量。BM25 仅支持 eval 自持的
SQLite FTS5 sidecar；LinkRag 已删除的 BucketRouter 与 qdrant_bm25 不再兼容。

护栏:collection 名必须含 ``eval``,否则构造期拒跑。本文件是允许 import LinkRag 的
adapter 之一；rag import 全部惰性，注入 ``index_store`` fake 即可单测而不连接 Qdrant。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from linkrag_eval.compute.protocol import Bm25Tokens, SparseVec


@dataclass(frozen=True)
class EvalPoint:
    """一个待写入的 eval 点:确定性 chunk_id + dense(+ 可选 sparse)+ 归属 doc。"""

    chunk_id: str
    doc_id: int
    dense: list[float]
    sparse: SparseVec | None = None
    bm25_tokens: Bm25Tokens | None = None
    chunk_type: str = "text"


class EvalVectorStore:
    """把 eval 点写进一个隔离 collection(named dense + named sparse)。"""

    def __init__(
        self,
        *,
        collection_name: str,
        user_id: int,
        qdrant_host: str | None = None,
        api_key: str | None = None,
        index_store: Any | None = None,
        sparse_vector_name: str | None = None,
        bm25_store: Any | None = None,
        bm25_mode: str = "stub",
        bm25_sqlite_path: str | None = None,
        bm25_sqlite_coarse_weight: float = 2.0,
        bm25_sqlite_fine_weight: float = 1.0,
    ) -> None:
        if "eval" not in collection_name:
            raise RuntimeError(
                f"EvalVectorStore collection {collection_name!r} 不含 'eval';"
                "为防写串生产,拒绝构造。"
            )
        if bm25_mode not in {"stub", "sqlite_fts5"}:
            raise ValueError(f"不支持的 bm25_mode: {bm25_mode!r}")
        self._collection_name = collection_name
        self._user_id = user_id
        self._store = index_store or _build_index_store(
            collection_name, qdrant_host, api_key
        )
        self._sparse_name = sparse_vector_name or "sparse_text"
        self._bm25_store = bm25_store
        self._bm25_mode = bm25_mode
        self._bm25_sqlite_path = bm25_sqlite_path
        self._bm25_sqlite_coarse_weight = bm25_sqlite_coarse_weight
        self._bm25_sqlite_fine_weight = bm25_sqlite_fine_weight
        self._collection_ready = False
        self._sparse_ready = False
        self._bm25_ready = False

    @property
    def collection_name(self) -> str:
        return self._collection_name

    async def upsert(self, *, dataset_id: int, points: Sequence[EvalPoint]) -> None:
        """写一批点:ensure collection → upsert dense → 可选 sparse / SQLite BM25。"""
        pts = list(points)
        if not pts:
            return
        vector_size = len(pts[0].dense)
        if vector_size <= 0:
            raise ValueError("dense 向量维度为 0,无法建 collection。")

        if not self._collection_ready:
            await self._store.ensure_collection(vector_size=vector_size)
            self._collection_ready = True
        await self._store.upsert_points(
            points=[self._dense_point(p, dataset_id) for p in pts]
        )

        sparse_pts = [p for p in pts if p.sparse is not None]
        if sparse_pts:
            if not self._sparse_ready:
                await self._store.ensure_sparse_vector_schema(vector_name=self._sparse_name)
                self._sparse_ready = True
            await self._store.upsert_sparse_vectors(
                points=[self._sparse_point(p, dataset_id) for p in sparse_pts]
            )

        bm25_points = self._bm25_points(dataset_id, pts)
        if bm25_points:
            bm25_store = self._ensure_bm25_store()
            if not self._bm25_ready:
                await bm25_store.ensure_collection()
                self._bm25_ready = True
            await bm25_store.upsert_chunks(bm25_points)

    async def delete(self, *, chunk_ids: Sequence[str]) -> None:
        """按 chunk_id 删点(定向清理;幂等重灌通常无需调用)。"""
        ids = list(chunk_ids)
        if ids:
            await self._store.delete_points(chunk_ids=ids)

    def _payload(self, p: EvalPoint, dataset_id: int) -> dict[str, int | str]:
        return {
            "chunk_id": p.chunk_id,
            "user_id": self._user_id,
            "set_id": dataset_id,
            "doc_id": p.doc_id,
        }

    def _dense_point(self, p: EvalPoint, dataset_id: int):
        from src.core.storage.qdrant.models import IndexedPoint

        return IndexedPoint(
            chunk_id=p.chunk_id,
            vector=[float(x) for x in p.dense],
            payload=self._payload(p, dataset_id),
        )

    def _sparse_point(self, p: EvalPoint, dataset_id: int):
        from src.core.encoding.sparse.models import SparseVector
        from src.core.storage.qdrant.models import SparseIndexedPoint

        assert p.sparse is not None
        return SparseIndexedPoint(
            chunk_id=p.chunk_id,
            vector_name=self._sparse_name,
            sparse_vector=SparseVector(
                indices=list(p.sparse.indices), values=list(p.sparse.values)
            ),
            payload=self._payload(p, dataset_id),
        )

    def _bm25_points(self, dataset_id: int, points: Sequence[EvalPoint]) -> list[Any]:
        if self._bm25_mode == "stub":
            return []
        from linkrag_eval.store.sqlite_bm25 import SQLiteBm25Point

        return [
            SQLiteBm25Point(
                chunk_id=p.chunk_id,
                doc_id=p.doc_id,
                user_id=self._user_id,
                dataset_id=dataset_id,
                chunk_type=p.chunk_type,
                tokens=p.bm25_tokens,
            )
            for p in points
            if p.bm25_tokens is not None
        ]

    def _ensure_bm25_store(self):
        if self._bm25_sqlite_path is None and self._bm25_store is None:
            raise RuntimeError("启用 sqlite_fts5 写入需配置 EVAL_BM25_SQLITE_PATH。")
        if self._bm25_store is None:
            self._bm25_store = _build_sqlite_bm25_store(
                path=self._bm25_sqlite_path,
                coarse_weight=self._bm25_sqlite_coarse_weight,
                fine_weight=self._bm25_sqlite_fine_weight,
            )
        return self._bm25_store


def _build_index_store(
    collection_name: str,
    qdrant_host: str | None,
    api_key: str | None,
):
    from qdrant_client import AsyncQdrantClient
    from src.core.storage.qdrant import QdrantIndexStore

    client = AsyncQdrantClient(url=qdrant_host, api_key=(api_key or None))
    return QdrantIndexStore(client=client, collection_name=collection_name)


def _build_sqlite_bm25_store(*, path: str | None, coarse_weight: float, fine_weight: float):
    from linkrag_eval.store.sqlite_bm25 import SQLiteBm25Store

    if not path:
        raise RuntimeError("EVAL_BM25_SQLITE_PATH 未配置。")
    return SQLiteBm25Store(
        path,
        coarse_weight=coarse_weight,
        fine_weight=fine_weight,
    )


def build_eval_vector_store(settings=None) -> EvalVectorStore:
    """按 EVAL_* 配置装配 EvalVectorStore。"""
    if settings is None:
        from linkrag_eval.config import get_settings

        settings = get_settings()
    return EvalVectorStore(
        collection_name=settings.qdrant_collection_name,
        user_id=settings.user_id,
        qdrant_host=settings.qdrant_host,
        sparse_vector_name=settings.sparse_vector_name,
        bm25_mode=settings.bm25_mode,
        bm25_sqlite_path=settings.bm25_sqlite_path,
        bm25_sqlite_coarse_weight=settings.bm25_sqlite_coarse_weight,
        bm25_sqlite_fine_weight=settings.bm25_sqlite_fine_weight,
    )
