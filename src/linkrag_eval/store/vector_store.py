"""eval 前缀 Qdrant 的写入器(``EvalVectorStore``)。

复用生产 ``QdrantIndexStore`` + point 模型(白名单 Qdrant 原语),
用 **eval 独立前缀** 实例化,绕开所有写 pipeline,自己构 ``IndexedPoint`` / ``SparseIndexedPoint``
直接 upsert。写读口径与生产一致——因为召回侧(recall_factory)复用同一 ``QdrantIndexStore``。

不经 ``ChunkRecordDB``:payload 只需 ``chunk_id/user_id/set_id/doc_id``,直接构点(见 point_factory._payload)。
dense 是 named ``dense`` 向量、sparse 是 named(名取自 ``EVAL_SPARSE_VECTOR_NAME``,默认
``sparse_text``)。BM25 使用 eval 自持 SQLite FTS5 sidecar；当前 LinkRag 已删除的旧
``qdrant_bm25`` 模块不会在这里恢复。

护栏:前缀必须含 ``eval``,否则构造期拒跑——防写串生产 collection。
本文件是允许 import toLink-Rag 的三个 adapter 之一(Qdrant 原语)。rag import 全部惰性,
使包在无 rag 环境仍可导入;注入 ``index_store`` fake 即可单测编排,不连真 Qdrant。
"""

from __future__ import annotations

import zlib
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
    """把 eval 点写进 eval 前缀 Qdrant collection(dense unnamed + sparse named)。"""

    def __init__(
        self,
        *,
        prefix: str,
        bucket_count: int,
        user_id: int,
        qdrant_host: str | None = None,
        api_key: str | None = None,
        index_store: Any | None = None,
        sparse_vector_name: str | None = None,
        qdrant_bm25_store: Any | None = None,
        bm25_encoder: Any | None = None,
        bm25_mode: str = "qdrant_bm25",
        bm25_collection: str | None = None,
        bm25_vector_name: str | None = None,
        bm25_sqlite_path: str | None = None,
        bm25_sqlite_coarse_weight: float = 2.0,
        bm25_sqlite_fine_weight: float = 1.0,
        bm25_k1: float = 1.2,
        bm25_b: float = 0.75,
        bm25_avgdl: float = 200.0,
        bm25_avgdl_fine: float = 220.0,
        bm25_coarse_boost: float = 2.0,
    ) -> None:
        if "eval" not in prefix:
            raise RuntimeError(
                f"EvalVectorStore 前缀 {prefix!r} 不含 'eval';为防写串生产,拒绝构造。"
            )
        self._prefix = prefix
        self._user_id = user_id
        self._bucket_id = _route_bucket(bucket_count, user_id)
        self._collection_name = _collection_name(prefix, self._bucket_id)
        self._store = index_store or _build_index_store(
            self._collection_name, qdrant_host, api_key
        )
        self._sparse_name = sparse_vector_name or "sparse_text"
        if bm25_collection is not None and "eval" not in bm25_collection:
            raise RuntimeError(
                f"Qdrant BM25 collection {bm25_collection!r} 不含 'eval';为防写串生产,拒绝构造。"
            )
        self._bm25_store = qdrant_bm25_store
        self._bm25_encoder = bm25_encoder
        self._bm25_mode = bm25_mode
        self._bm25_collection = bm25_collection
        self._bm25_vector_name = bm25_vector_name or "bm25_text"
        self._bm25_sqlite_path = bm25_sqlite_path
        self._bm25_sqlite_coarse_weight = bm25_sqlite_coarse_weight
        self._bm25_sqlite_fine_weight = bm25_sqlite_fine_weight
        self._bm25_k1 = bm25_k1
        self._bm25_b = bm25_b
        self._bm25_avgdl = bm25_avgdl
        self._bm25_avgdl_fine = bm25_avgdl_fine
        self._bm25_coarse_boost = bm25_coarse_boost
        self._qdrant_host = qdrant_host
        self._api_key = api_key
        self._collection_ready = False
        self._sparse_ready = False
        self._bm25_ready = False

    @property
    def bucket_id(self) -> int:
        return self._bucket_id

    @property
    def collection_name(self) -> str:
        return self._collection_name

    async def upsert(self, *, dataset_id: int, points: Sequence[EvalPoint]) -> None:
        """写一批点:ensure collection → upsert dense → (有 sparse 则)ensure schema + upsert sparse。

        幂等:point id = 确定性 chunk_id,重灌覆盖。dense/sparse 共用同一 point(sparse 走
        ``update_vectors`` 追加,不覆盖 dense)。
        """
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
            points=[self._dense_point(p, dataset_id) for p in pts],
        )

        sparse_pts = [p for p in pts if p.sparse is not None]
        if sparse_pts:
            if not self._sparse_ready:
                await self._store.ensure_sparse_vector_schema(
                    vector_name=self._sparse_name
                )
                self._sparse_ready = True
            await self._store.upsert_sparse_vectors(
                points=[self._sparse_point(p, dataset_id) for p in sparse_pts],
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

    # —— 构点(惰性 import rag 原语)——
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
        bm25_items = [p for p in points if p.bm25_tokens is not None]
        if not bm25_items:
            return []
        if self._bm25_mode == "sqlite_fts5":
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
                for p in bm25_items
                if p.bm25_tokens is not None
            ]
        raise NotImplementedError(
            "EVAL_BM25_MODE=qdrant_bm25 依赖的生产模块已删除；"
            "当前 eval BM25 适配使用自持 sqlite_fts5。"
        )

    def _ensure_bm25_store(self):
        if self._bm25_mode == "sqlite_fts5":
            if self._bm25_sqlite_path is None and self._bm25_store is None:
                raise RuntimeError("启用 sqlite_fts5 写入需配置 EVAL_BM25_SQLITE_PATH。")
            if self._bm25_store is None:
                self._bm25_store = _build_sqlite_bm25_store(
                    path=self._bm25_sqlite_path,
                    coarse_weight=self._bm25_sqlite_coarse_weight,
                    fine_weight=self._bm25_sqlite_fine_weight,
                )
            return self._bm25_store
        raise NotImplementedError(
            "EVAL_BM25_MODE=qdrant_bm25 依赖的生产模块已删除；请使用 sqlite_fts5。"
        )


# —— 默认装配:此处(允许的 adapter 文件)惰性触碰 rag / qdrant-client ——
def _route_bucket(bucket_count: int, user_id: int) -> int:
    """重放历史 eval collection 的固定路由，不依赖已删除的生产 BucketRouter。

    旧契约的公开规则就是 ``crc32(str(user_id)) % bucket_count``。这里保留该数据布局
    兼容性，但只把结果解析成现行 ``QdrantIndexStore(collection_name=...)`` 所需的
    显式 collection 名；不会在生产仓库恢复旧抽象。
    """

    if bucket_count <= 0:
        raise ValueError("bucket_count 必须为正整数。")
    return zlib.crc32(str(user_id).encode("utf-8")) % bucket_count


def _collection_name(prefix: str, bucket_id: int) -> str:
    return f"{prefix}_{bucket_id}"


def resolve_eval_qdrant_collection(*, prefix: str, bucket_count: int, user_id: int) -> str:
    """返回当前 eval 路由常量对应的显式 Qdrant collection 名。"""

    if "eval" not in prefix:
        raise RuntimeError(f"Qdrant eval 前缀 {prefix!r} 不含 'eval';拒绝解析。")
    return _collection_name(prefix, _route_bucket(bucket_count, user_id))


def _build_index_store(
    collection_name: str, qdrant_host: str | None, api_key: str | None
):
    from qdrant_client import AsyncQdrantClient
    from src.core.storage.qdrant import QdrantIndexStore

    client = AsyncQdrantClient(url=qdrant_host, api_key=(api_key or None))
    return QdrantIndexStore(
        client=client,
        collection_name=collection_name,
    )


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
        prefix=settings.qdrant_prefix,
        bucket_count=settings.qdrant_bucket_count,
        user_id=settings.user_id,
        qdrant_host=settings.qdrant_host,
        sparse_vector_name=settings.sparse_vector_name,
        bm25_mode=settings.bm25_mode,
        bm25_collection=settings.qdrant_bm25_collection,
        bm25_vector_name=settings.qdrant_bm25_vector_name,
        bm25_sqlite_path=settings.bm25_sqlite_path,
        bm25_sqlite_coarse_weight=settings.bm25_sqlite_coarse_weight,
        bm25_sqlite_fine_weight=settings.bm25_sqlite_fine_weight,
        bm25_k1=settings.bm25_k1,
        bm25_b=settings.bm25_b,
        bm25_avgdl=settings.bm25_avgdl,
        bm25_avgdl_fine=settings.bm25_avgdl_fine,
        bm25_coarse_boost=settings.bm25_coarse_boost,
    )
