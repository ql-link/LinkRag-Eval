"""eval 前缀 Qdrant 的写入器(``EvalVectorStore``)。

复用生产 ``QdrantIndexStore`` + ``BucketRouter`` + point 模型(白名单 Qdrant 原语),
用 **eval 独立前缀** 实例化,绕开所有写 pipeline,自己构 ``IndexedPoint`` / ``SparseIndexedPoint``
直接 upsert。写读口径与生产一致——因为召回侧(recall_factory)复用同一 ``QdrantIndexStore``。

不经 ``ChunkRecordDB``:payload 只需 ``chunk_id/user_id/set_id/doc_id``,直接构点(见 point_factory._payload)。
dense 是 unnamed 向量、sparse 是 named(名取自 ``EVAL_SPARSE_VECTOR_NAME``,默认 ``sparse_text``)。

护栏:前缀必须含 ``eval``,否则构造期拒跑——防写串生产 collection。
本文件是允许 import toLink-Rag 的三个 adapter 之一(Qdrant 原语)。rag import 全部惰性,
使包在无 rag 环境仍可导入;注入 ``index_store`` fake 即可单测编排,不连真 Qdrant。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from linkrag_eval.compute.protocol import SparseVec


@dataclass(frozen=True)
class EvalPoint:
    """一个待写入的 eval 点:确定性 chunk_id + dense(+ 可选 sparse)+ 归属 doc。"""

    chunk_id: str
    doc_id: int
    dense: list[float]
    sparse: SparseVec | None = None


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
    )
