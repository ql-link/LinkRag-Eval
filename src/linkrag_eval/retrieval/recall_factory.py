"""eval 召回装配:复用生产 RecallPipeline,指向 **eval 前缀** Qdrant,query 侧注入 **eval 编码器**。

是允许 import rag 的 adapter 之一(召回真链路=被测对象)。装配口径对齐生产
``recall_pipeline_provider``,但两处替换以解耦:
- **Qdrant 指向 eval 前缀**:facade 注入 eval 前缀的 ``QdrantIndexStore``(eval client + router)。
- **query 编码走 eval llm**:dense/sparse 的 per-user resolver(读 llm_user_config,黑名单内)
  换成"无视 user_id、返回 eval 编码器"的 resolver——dense 注入 eval dense embedder(它有
  ``aembed_query_detailed``),sparse 注入 :class:`_EvalSparseQueryService`(把 eval sparse 输出
  转成 rag ``SparseVector``)。写入侧(EvalVectorStore)与召回侧共用同一 eval 编码器口径。

融合/排序(RRF)仍是生产 RecallPipeline 原物——那正是被测对象。bm25 路 P1 ``stub``:
只装 dense+sparse 两路(生产 Qdrant BM25 未落地,见 decoupling-plan bm25 待定项)。

护栏:Qdrant 前缀必须含 ``eval``,否则拒绝装配——防打到生产 collection。
"""

from __future__ import annotations

from typing import Any


class _EvalSparseQueryService:
    """把 eval sparse 编码器适配成生产 facade 期望的 sparse 服务:``vectorize_query`` + ``model_name``。"""

    def __init__(self, encoder: Any) -> None:
        self._enc = encoder

    @property
    def model_name(self) -> str:
        """facade.search_sparse 读 ``service.model_name`` 上报。"""
        return getattr(self._enc, "model_name", "eval_sparse")

    async def vectorize_query(self, query: str):
        from src.core.encoding.sparse.models import SparseVector

        vecs = await self._enc.aencode([query])
        if not vecs:
            raise ValueError("sparse 编码 query 返回空。")
        sv = vecs[0]
        return SparseVector(indices=list(sv.indices), values=list(sv.values))


def build_eval_recall_pipeline(
    *,
    settings: Any | None = None,
    dense_encoder: Any | None = None,
    sparse_encoder: Any | None = None,
    dense_score_threshold: float = 0.0,
    sparse_score_threshold: float = 0.0,
    strict: bool = False,
):
    """装配指向 eval 前缀、用 eval 编码器的 RecallPipeline(dense+sparse 两路,bm25 P1 stub)。"""
    if settings is None:
        from linkrag_eval.config import get_settings

        settings = get_settings()
    if "eval" not in settings.qdrant_prefix:
        raise RuntimeError(
            f"召回装配前缀 {settings.qdrant_prefix!r} 不含 'eval';为防打到生产 collection,拒绝装配。"
        )
    if dense_encoder is None:
        from linkrag_eval.llm.dense_client import build_dense_embedder

        dense_encoder = build_dense_embedder(settings)
    if sparse_encoder is None:
        from linkrag_eval.llm.sparse_client import build_sparse_encoder

        sparse_encoder = build_sparse_encoder(settings)

    from qdrant_client import AsyncQdrantClient

    from src.core.pipeline.recall import RecallPipeline, RecallPipelineConfig
    from src.core.storage.qdrant import QdrantIndexStore
    from src.core.storage.qdrant.bucket_router import BucketRouter
    from src.core.storage.vector import compose_vector_storage_facade
    from src.core.storage.vector.dense_retriever import DenseRetriever
    from src.core.storage.vector.sparse_retriever import SparseRetriever

    router = BucketRouter(prefix=settings.qdrant_prefix, bucket_count=settings.qdrant_bucket_count)
    client = AsyncQdrantClient(url=settings.qdrant_host, api_key=None)
    store = QdrantIndexStore(client=client, bucket_router=router)

    async def _dense_resolver(_user_id: int):
        return dense_encoder

    _sparse_service = _EvalSparseQueryService(sparse_encoder)

    async def _sparse_resolver(_user_id: int):
        return _sparse_service

    dense = DenseRetriever(
        backend=compose_vector_storage_facade(
            qdrant_store=store, bucket_router=router, query_embedding_resolver=_dense_resolver
        ),
        score_threshold=dense_score_threshold,
    )
    sparse = SparseRetriever(
        backend=compose_vector_storage_facade(
            qdrant_store=store, bucket_router=router, query_sparse_resolver=_sparse_resolver
        ),
        score_threshold=sparse_score_threshold,
    )
    return RecallPipeline([dense, sparse], RecallPipelineConfig(strict=strict))


def build_eval_recall_evaluable(top_k: int, **kwargs):
    """装配 + 包成 RecallEvaluable(评测调用面)。"""
    from linkrag_eval.retrieval.recall_adapter import RecallEvaluable

    return RecallEvaluable(build_eval_recall_pipeline(**kwargs), top_k)
