"""eval 召回装配:复用生产 RecallPipeline,指向 **eval 前缀** Qdrant,query 侧注入 **eval 编码器**。

是允许 import rag 的 adapter 之一(召回真链路=被测对象)。装配口径对齐生产
``recall_pipeline_provider``,但两处替换以解耦:
- **Qdrant 指向 eval 前缀**:facade 注入 eval 前缀的 ``QdrantIndexStore``(eval client + router)。
- **query 编码走 eval llm**:dense/sparse 的 per-user resolver(读 llm_user_config,黑名单内)
  换成"无视 user_id、返回 eval 编码器"的 resolver——dense 注入 eval dense embedder(它有
  ``aembed_query_detailed``),sparse 注入 :class:`_EvalSparseQueryService`(把 eval sparse 输出
  转成 rag ``SparseVector``)。写入侧(EvalVectorStore)与召回侧共用同一 eval 编码器口径。

融合/排序由生产 RecallPipeline 按请求级参数执行(RRF/weighted_score 均可)。bm25 路在
``EVAL_BM25_MODE=qdrant_bm25`` 时装配生产 Qdrant BM25 retriever,指向 eval 独立
BM25 collection;``stub`` 时只装 dense+sparse 两路。

护栏:Qdrant 前缀必须含 ``eval``,否则拒绝装配——防打到生产 collection。
"""

from __future__ import annotations

from types import SimpleNamespace
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


class _EvalBm25Retriever:
    """把生产 Qdrant BM25 backend 适配成 RecallPipeline Retriever,避开 ES adapter 路径。"""

    source = "bm25"

    def __init__(self, *, backend: Any, tokenizer: Any) -> None:
        self._backend = backend
        self._tokenizer = tokenizer

    async def recall(
        self,
        query: str,
        dataset_ids: list[int],
        doc_ids: list[int] | None = None,
        *,
        user_id: int,
        top_k: int,
        score_threshold_override: float | None = None,
    ) -> list[Any]:
        from src.core.pipeline.recall.models import RetrieverHit

        tokens = self._tokenize(query)
        if not tokens or not dataset_ids:
            return []
        doc_iter: list[int | None] = list(doc_ids) if doc_ids else [None]
        hits: list[Any] = []
        for dataset_id in dataset_ids:
            for doc_id in doc_iter:
                got = await self._backend.recall_topk_chunks(
                    SimpleNamespace(
                        user_id=user_id,
                        dataset_id=dataset_id,
                        tokens=tokens,
                        top_k=top_k,
                        doc_id=doc_id,
                    )
                )
                hits.extend(
                    RetrieverHit(
                        chunk_id=h.chunk_id,
                        doc_id=h.doc_id,
                        dataset_id=dataset_id,
                        score=h.score,
                        source=self.source,
                    )
                    for h in got
                )
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]

    def _tokenize(self, query: str) -> list[str]:
        tokenized = self._tokenizer.tokenize(query)
        return [tok for tok in tokenized.coarse_tokens.split() if tok]


def build_eval_recall_pipeline(
    *,
    settings: Any | None = None,
    dense_encoder: Any | None = None,
    sparse_encoder: Any | None = None,
    dense_score_threshold: float | None = None,
    sparse_score_threshold: float | None = None,
    bm25_tokenizer: Any | None = None,
    strict: bool = False,
):
    """装配指向 eval 前缀、用 eval 编码器的 RecallPipeline。"""
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
    if dense_score_threshold is None:
        dense_score_threshold = getattr(settings, "recall_dense_score_threshold", 0.0)
    if sparse_score_threshold is None:
        sparse_score_threshold = getattr(settings, "recall_sparse_score_threshold", 0.40)

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
    retrievers = []
    if getattr(settings, "bm25_mode", "stub") == "qdrant_bm25":
        retrievers.append(_build_qdrant_bm25_retriever(settings, tokenizer=bm25_tokenizer))
    elif getattr(settings, "bm25_mode", "stub") == "sparse_proxy":
        raise NotImplementedError("EVAL_BM25_MODE=sparse_proxy 未实现;请使用 stub 或 qdrant_bm25。")
    retrievers.extend([dense, sparse])
    return RecallPipeline([*retrievers], RecallPipelineConfig(strict=strict))


def _build_qdrant_bm25_retriever(settings: Any, *, tokenizer: Any | None = None):
    if "eval" not in settings.qdrant_bm25_collection:
        raise RuntimeError(
            f"Qdrant BM25 collection {settings.qdrant_bm25_collection!r} 不含 'eval';拒绝装配。"
        )
    from qdrant_client import AsyncQdrantClient

    from src.core.storage.qdrant_bm25 import (
        Bm25SparseEncoder,
        QdrantBm25Retriever,
        QdrantBm25Store,
    )

    client = AsyncQdrantClient(url=settings.qdrant_host, api_key=None)
    store = QdrantBm25Store(
        client=client,
        collection_name=settings.qdrant_bm25_collection,
        vector_name=settings.qdrant_bm25_vector_name,
    )
    encoder = Bm25SparseEncoder(
        k1=settings.bm25_k1,
        b=settings.bm25_b,
        avgdl_coarse=settings.bm25_avgdl,
        avgdl_fine=settings.bm25_avgdl_fine,
        coarse_boost=settings.bm25_coarse_boost,
    )
    if tokenizer is None:
        from src.core.preprocessor.ragflow_tokenizer import RagFlowTokenizer

        tokenizer = RagFlowTokenizer()
    return _EvalBm25Retriever(
        backend=QdrantBm25Retriever(store=store, encoder=encoder),
        tokenizer=tokenizer,
    )


def build_eval_recall_evaluable(top_k: int, **kwargs):
    """装配 + 包成 RecallEvaluable(评测调用面)。"""
    from linkrag_eval.retrieval.recall_adapter import RecallEvaluable
    settings = kwargs.get("settings")
    if settings is None:
        from linkrag_eval.config import get_settings

        settings = get_settings()
    dense_threshold = kwargs.get(
        "dense_score_threshold", getattr(settings, "recall_dense_score_threshold", None)
    )
    sparse_threshold = kwargs.get(
        "sparse_score_threshold", getattr(settings, "recall_sparse_score_threshold", None)
    )
    return RecallEvaluable(
        build_eval_recall_pipeline(**kwargs),
        top_k,
        bm25_top_k=getattr(settings, "recall_bm25_top_k", top_k),
        dense_top_k=getattr(settings, "recall_dense_top_k", top_k),
        sparse_top_k=getattr(settings, "recall_sparse_top_k", top_k),
        dense_score_threshold=dense_threshold,
        sparse_score_threshold=sparse_threshold,
        fusion_strategy=getattr(settings, "recall_fusion_strategy", "rrf"),
        fusion_weights={
            "dense": getattr(settings, "recall_dense_weight", 0.5),
            "sparse": getattr(settings, "recall_sparse_weight", 0.3),
            "bm25": getattr(settings, "recall_bm25_weight", 0.0),
        },
    )
