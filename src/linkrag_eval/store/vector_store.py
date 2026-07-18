"""eval 前缀 Qdrant 的写入器(``EvalVectorStore``)。

复用生产 ``QdrantIndexStore`` + ``BucketRouter`` + point 模型(白名单 Qdrant 原语),
用 **eval 独立前缀** 实例化,绕开所有写 pipeline,自己构 ``IndexedPoint`` / ``SparseIndexedPoint``
直接 upsert。写读口径与生产一致——因为召回侧(recall_factory)复用同一 ``QdrantIndexStore``。

不经 ``ChunkRecordDB``:payload 只需 ``chunk_id/user_id/set_id/doc_id``,直接构点(见 point_factory._payload)。
dense 是 unnamed 向量、sparse 是 named(名取自 ``EVAL_SPARSE_VECTOR_NAME``,默认 ``sparse_text``)。
BM25 可写旧 Qdrant sparse collection,也可写推荐的 SQLite FTS5 sidecar。

护栏:前缀必须含 ``eval``,否则构造期拒跑——防写串生产 collection。
本文件是允许 import toLink-Rag 的三个 adapter 之一(Qdrant 原语)。rag import 全部惰性,
使包在无 rag 环境仍可导入;注入 ``index_store`` fake 即可单测编排,不连真 Qdrant。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

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
        self._bucket_id = _route_bucket(prefix, bucket_count, user_id)
        self._store = index_store or _build_index_store(prefix, bucket_count, qdrant_host, api_key)
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

    @property
    def bucket_id(self) -> int:
        return self._bucket_id

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

        await self._store.ensure_collection(bucket_id=self._bucket_id, vector_size=vector_size)
        await self._store.upsert_points(
            bucket_id=self._bucket_id,
            points=[self._dense_point(p, dataset_id) for p in pts],
        )

        sparse_pts = [p for p in pts if p.sparse is not None]
        if sparse_pts:
            await self._store.ensure_sparse_vector_schema(
                bucket_id=self._bucket_id, vector_name=self._sparse_name
            )
            await self._store.upsert_sparse_vectors(
                bucket_id=self._bucket_id,
                points=[self._sparse_point(p, dataset_id) for p in sparse_pts],
            )

        bm25_points = self._bm25_points(dataset_id, pts)
        if bm25_points:
            bm25_store = self._ensure_bm25_store()
            await bm25_store.ensure_collection()
            await bm25_store.upsert_chunks(bm25_points)

    async def delete(self, *, chunk_ids: Sequence[str]) -> None:
        """按 chunk_id 删点(定向清理;幂等重灌通常无需调用)。"""
        ids = list(chunk_ids)
        if ids:
            await self._store.delete_points(bucket_id=self._bucket_id, chunk_ids=ids)

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
            bucket_id=self._bucket_id,
            vector=[float(x) for x in p.dense],
            payload=self._payload(p, dataset_id),
        )

    def _sparse_point(self, p: EvalPoint, dataset_id: int):
        from src.core.encoding.sparse.models import SparseVector
        from src.core.storage.qdrant.models import SparseIndexedPoint

        assert p.sparse is not None
        return SparseIndexedPoint(
            chunk_id=p.chunk_id,
            bucket_id=self._bucket_id,
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
        encoder = self._ensure_bm25_encoder()
        out: list[Any] = []
        for p in bm25_items:
            assert p.bm25_tokens is not None
            vector = encoder.encode_document(
                p.bm25_tokens.coarse.split(), p.bm25_tokens.fine.split()
            )
            if not vector.indices:
                continue
            out.append(_bm25_point_cls()(
                chunk_id=p.chunk_id,
                doc_id=p.doc_id,
                user_id=self._user_id,
                dataset_id=dataset_id,
                chunk_type=p.chunk_type,
                sparse_vector=vector,
            ))
        return out

    def _ensure_bm25_encoder(self):
        if self._bm25_encoder is None:
            self._bm25_encoder = _build_bm25_encoder(
                k1=self._bm25_k1,
                b=self._bm25_b,
                avgdl_coarse=self._bm25_avgdl,
                avgdl_fine=self._bm25_avgdl_fine,
                coarse_boost=self._bm25_coarse_boost,
            )
        return self._bm25_encoder

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
        if self._bm25_collection is None and self._bm25_store is None:
            raise RuntimeError("启用 qdrant_bm25 写入需配置 EVAL_QDRANT_BM25_COLLECTION。")
        if self._bm25_store is None:
            self._bm25_store = _build_bm25_store(
                qdrant_host=self._qdrant_host,
                api_key=self._api_key,
                collection_name=self._bm25_collection,
                vector_name=self._bm25_vector_name,
            )
        return self._bm25_store


# —— 默认装配:此处(允许的 adapter 文件)惰性触碰 rag / qdrant-client ——
def _route_bucket(prefix: str, bucket_count: int, user_id: int) -> int:
    from src.core.storage.qdrant.bucket_router import BucketRouter

    return BucketRouter(prefix=prefix, bucket_count=bucket_count).route_user(user_id).bucket_id


def _build_index_store(prefix: str, bucket_count: int, qdrant_host: str | None, api_key: str | None):
    from qdrant_client import AsyncQdrantClient

    from src.core.storage.qdrant import QdrantIndexStore
    from src.core.storage.qdrant.bucket_router import BucketRouter

    client = AsyncQdrantClient(url=qdrant_host, api_key=(api_key or None))
    return QdrantIndexStore(
        client=client,
        bucket_router=BucketRouter(prefix=prefix, bucket_count=bucket_count),
        host=qdrant_host or "",
    )


def _build_bm25_store(
    *,
    qdrant_host: str | None,
    api_key: str | None,
    collection_name: str | None,
    vector_name: str,
):
    from qdrant_client import AsyncQdrantClient

    from src.core.storage.qdrant_bm25 import QdrantBm25Store

    client = AsyncQdrantClient(url=qdrant_host, api_key=(api_key or None))
    return QdrantBm25Store(
        client=client,
        collection_name=collection_name,
        vector_name=vector_name,
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


def _build_bm25_encoder(
    *,
    k1: float,
    b: float,
    avgdl_coarse: float,
    avgdl_fine: float,
    coarse_boost: float,
):
    from src.core.storage.qdrant_bm25 import Bm25SparseEncoder

    return Bm25SparseEncoder(
        k1=k1,
        b=b,
        avgdl_coarse=avgdl_coarse,
        avgdl_fine=avgdl_fine,
        coarse_boost=coarse_boost,
    )


def _bm25_point_cls():
    from src.core.storage.qdrant_bm25 import Bm25Point

    return Bm25Point


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
