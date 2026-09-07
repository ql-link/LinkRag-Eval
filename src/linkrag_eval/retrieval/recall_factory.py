"""eval 召回装配:复用生产 RecallPipeline,指向 **eval collection** Qdrant,query 侧注入 **eval 编码器**。

是允许 import rag 的 adapter 之一(召回真链路=被测对象)。装配口径对齐生产
``recall_pipeline_provider``,但两处替换以解耦:
- **Qdrant 指向 eval collection**:按冻结 routing 常量解析显式 collection 名，再注入
  现行 ``QdrantIndexStore(collection_name=...)``。
- **query 编码走 eval llm**:dense 直接注入 eval dense embedding pipeline(它有
  ``aembed_query_detailed``),sparse 注入 :class:`_EvalSparseQueryService`(把 eval sparse 输出
  转成 rag ``SparseVector``),不读取生产 Dataset/per-user 配置。写入侧(EvalVectorStore)
  与召回侧共用同一 eval 编码器口径。

融合/排序由生产 RecallPipeline 按固定 weighted score 与请求级权重执行。BM25 路在
``sqlite_fts5`` 时装配 eval 自持 SQLite FTS5；``stub`` 时只装 dense+sparse 两路。

护栏:Qdrant 前缀必须含 ``eval``,否则拒绝装配——防打到生产 collection。
"""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from types import SimpleNamespace
from typing import Any


class _EvalSparseQueryService:
    """把 eval sparse 编码器适配成生产 facade 期望的 sparse 服务:``vectorize_query`` + ``model_name``。"""

    def __init__(self, encoder: Any, *, vector_name: str = "sparse_text") -> None:
        self._enc = encoder
        self.vector_name = vector_name

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


class _EvalReadinessGate:
    """Eval 独立语料的可见性门禁。

    生产门禁会查询生产 MySQL 的解析任务状态。eval 命中只来自已完成 ingest 的独立
    语料，因此保持融合顺序原样放行，避免重新引入生产库依赖。
    """

    async def filter_visible_hits(self, hits, *, user_id: int):
        del user_id
        return list(hits)


class _EvalBm25Retriever:
    """把 eval SQLite FTS5 后端适配成生产 RecallPipeline 的 Retriever。"""

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
        dataset_contexts: dict[int, object] | None = None,
    ) -> list[Any]:
        from src.core.pipeline.recall.models import RetrieverHit

        # RecallPipeline 统一透传数据集上下文；eval BM25 使用显式 dataset_ids，
        # 不读取生产数据集配置。
        del dataset_contexts, score_threshold_override
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


def _validate_recall_settings(settings: Any) -> None:
    if "eval" not in settings.qdrant_prefix:
        raise RuntimeError(
            f"召回装配前缀 {settings.qdrant_prefix!r} 不含 'eval';为防打到生产 collection,拒绝装配。"
        )
    if settings.bm25_mode not in {"stub", "sqlite_fts5"}:
        raise ValueError(f"不支持的 BM25 模式: {settings.bm25_mode!r}")


@asynccontextmanager
async def open_eval_recall_pipeline(*, settings: Any):
    """在本次异步调用内创建并关闭三路召回所持有的网络客户端。"""
    from qdrant_client import AsyncQdrantClient

    from linkrag_eval.llm.dense_client import build_dense_embedder
    from linkrag_eval.llm.sparse_client import build_sparse_encoder

    _validate_recall_settings(settings)
    async with AsyncExitStack() as resources:
        dense = build_dense_embedder(settings)
        resources.push_async_callback(dense.aclose)
        sparse = build_sparse_encoder(settings)
        resources.push_async_callback(sparse.aclose)
        client = AsyncQdrantClient(url=settings.qdrant_host, api_key=None, trust_env=False)
        resources.push_async_callback(client.close)
        yield build_eval_recall_pipeline(
            settings=settings, dense_encoder=dense, sparse_encoder=sparse, qdrant_client=client,
        )


def build_eval_recall_pipeline(
    *,
    settings: Any | None = None,
    dense_encoder: Any | None = None,
    sparse_encoder: Any | None = None,
    qdrant_client: Any | None = None,
    dense_score_threshold: float | None = None,
    sparse_score_threshold: float | None = None,
    bm25_tokenizer: Any | None = None,
    strict: bool = False,
):
    """装配 RecallPipeline；注入客户端由调用方持有，短期调用宜用 open 入口。"""
    if settings is None:
        from linkrag_eval.config import get_settings

        settings = get_settings()
    _validate_recall_settings(settings)
    if dense_encoder is None:
        from linkrag_eval.llm.dense_client import build_dense_embedder

        dense_encoder = build_dense_embedder(settings)
    if sparse_encoder is None:
        from linkrag_eval.llm.sparse_client import build_sparse_encoder

        sparse_encoder = build_sparse_encoder(settings)
    if dense_score_threshold is None:
        dense_score_threshold = settings.recall_dense_score_threshold
    if sparse_score_threshold is None:
        sparse_score_threshold = settings.recall_sparse_score_threshold

    from qdrant_client import AsyncQdrantClient
    from src.core.pipeline.recall import RecallPipeline, RecallPipelineConfig
    from src.core.storage.qdrant import QdrantIndexStore
    from src.core.storage.vector import compose_vector_storage_facade
    from src.core.storage.vector.dense_retriever import DenseRetriever
    from src.core.storage.vector.sparse_retriever import SparseRetriever

    from linkrag_eval.store.vector_store import resolve_eval_qdrant_collection

    collection_name = resolve_eval_qdrant_collection(
        prefix=settings.qdrant_prefix,
        bucket_count=settings.qdrant_bucket_count,
        user_id=settings.user_id,
    )
    # 显式 eval 端点直连；本机系统代理可能无法访问 Tailscale 私网。
    client = qdrant_client if qdrant_client is not None else AsyncQdrantClient(
        url=settings.qdrant_host, api_key=None, trust_env=False,
    )
    store = QdrantIndexStore(client=client, collection_name=collection_name)

    _sparse_service = _EvalSparseQueryService(
        sparse_encoder, vector_name=settings.sparse_vector_name
    )

    dense = DenseRetriever(
        backend=compose_vector_storage_facade(
            qdrant_store=store,
            embedding_pipeline=dense_encoder,
        ),
        score_threshold=dense_score_threshold,
    )
    sparse_backend = compose_vector_storage_facade(
        qdrant_store=store,
    )
    # 生产 facade 在调用 resolver 前需要 vector_name。这里显式挂 eval service,
    # 避免回退读取生产 settings 中的 sparse vector name。
    sparse_backend._sparse_vector_service = _sparse_service
    sparse = SparseRetriever(backend=sparse_backend, score_threshold=sparse_score_threshold)
    retrievers = []
    if settings.bm25_mode == "sqlite_fts5":
        retrievers.append(_build_sqlite_bm25_retriever(settings, tokenizer=bm25_tokenizer))
    retrievers.extend([dense, sparse])
    return RecallPipeline(
        [*retrievers],
        RecallPipelineConfig(strict=strict),
        readiness_gate=_EvalReadinessGate(),
    )


def _build_sqlite_bm25_retriever(settings: Any, *, tokenizer: Any | None = None):
    from linkrag_eval.store.sqlite_bm25 import SQLiteBm25Store, SQLiteBm25Tokenizer

    if tokenizer is None:
        tokenizer = SQLiteBm25Tokenizer()
    return _EvalBm25Retriever(
        backend=SQLiteBm25Store(
            settings.bm25_sqlite_path,
            coarse_weight=settings.bm25_sqlite_coarse_weight,
            fine_weight=settings.bm25_sqlite_fine_weight,
        ),
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
        "dense_score_threshold", settings.recall_dense_score_threshold
    )
    sparse_threshold = kwargs.get(
        "sparse_score_threshold", settings.recall_sparse_score_threshold
    )
    enabled_sources = kwargs.pop("enabled_sources", None)
    return RecallEvaluable(
        build_eval_recall_pipeline(**kwargs),
        top_k,
        bm25_top_k=settings.recall_bm25_top_k,
        dense_top_k=settings.recall_dense_top_k,
        sparse_top_k=settings.recall_sparse_top_k,
        dense_score_threshold=dense_threshold,
        sparse_score_threshold=sparse_threshold,
        enabled_sources=enabled_sources,
        fusion_weights={
            "dense": settings.recall_dense_weight,
            "sparse": settings.recall_sparse_weight,
            "bm25": settings.recall_bm25_weight,
        },
    )
