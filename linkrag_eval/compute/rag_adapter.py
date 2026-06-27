""":class:`ProductComputer` 的默认实现——**唯一允许 import toLink-Rag(src.*)的文件**。

把 rag 的纯计算函数封装成产物级接口:
- chunk 切分 → ``ChunkingEngine.aprocess``
- dense 向量 → ``create_chunk_embedding_pipeline().aembed_chunks``(系统配置 embedder)
- bm25 分词 → ``RagFlowTokenizer.tokenize``
- sparse 向量 → 注入的 :class:`SparseEncoder`(生产无系统工厂,见下)

rag 改了内部签名,只打穿本文件 + 契约测试(tests/contract/),在一处修。
"""

from __future__ import annotations

from typing import Any, Sequence

from linkrag_eval.compute.protocol import (
    Bm25Tokens,
    DenseVec,
    EvalChunk,
    SparseEncoder,
    SparseVec,
)


class SparseEncoderNotConfigured(RuntimeError):
    """未注入 sparse 编码器。生产 sparse 无系统配置工厂(只有 per-user,在黑名单内),
    eval 须按 EVAL_ 配置自带一个 :class:`SparseEncoder` 注入。见 decoupling-plan 风险 C / bm25 待定项。"""


class RagProductComputer:
    """默认产物计算器。dense/chunks/bm25 复用 rag 系统级纯函数;sparse 由注入缝提供。

    Args:
        sparse_encoder: 稀疏编码器(eval 自带,按 EVAL_ 配置)。缺省时调用 ``compute_sparse`` 抛错。
        dense_pipeline_factory / chunking_engine_factory / tokenizer_factory: 测试可注入 fake。
    """

    def __init__(
        self,
        *,
        sparse_encoder: SparseEncoder | None = None,
        dense_pipeline_factory: Any | None = None,
        chunking_engine_factory: Any | None = None,
        tokenizer_factory: Any | None = None,
    ) -> None:
        # 缺省装配 eval 自带的 config 驱动 sparse 编码器(生产无系统工厂)。
        if sparse_encoder is None:
            from linkrag_eval.llm.sparse_client import build_sparse_encoder

            try:
                sparse_encoder = build_sparse_encoder()
            except Exception:
                # 未配置 EVAL_SPARSE_* 时不在构造期失败;compute_sparse 调用时再报清晰错误。
                sparse_encoder = None
        self._sparse_encoder = sparse_encoder
        self._dense_factory = dense_pipeline_factory or _default_dense_pipeline
        self._chunker_factory = chunking_engine_factory or _default_chunking_engine
        self._tokenizer_factory = tokenizer_factory or _default_tokenizer
        self._dense_pipeline = None
        self._tokenizer = None

    # —— chunk 切分 ——
    async def compute_chunks(
        self, text: str, *, source_file: str | None = None
    ) -> list[EvalChunk]:
        engine = self._chunker_factory()
        chunks = await engine.aprocess(text, source_file=source_file)
        return [
            EvalChunk(
                content=c.content,
                ordinal=i,
                start_line=getattr(c, "start_line", None),
                end_line=getattr(c, "end_line", None),
                metadata=dict(getattr(c, "metadata", {}) or {}),
            )
            for i, c in enumerate(chunks)
        ]

    # —— dense 向量 ——
    async def compute_dense(self, contents: Sequence[str]) -> list[DenseVec]:
        pipeline = self._ensure_dense()
        chunks = [_text_to_rag_chunk(t) for t in contents]
        embedded = await pipeline.aembed_chunks(chunks)
        if len(embedded) != len(contents):
            raise ValueError(
                f"dense 数量不符:got {len(embedded)}, expected {len(contents)}"
            )
        return [DenseVec(values=list(e.embedding)) for e in embedded]

    # —— sparse 向量(注入缝)——
    async def compute_sparse(self, contents: Sequence[str]) -> list[SparseVec]:
        if self._sparse_encoder is None:
            raise SparseEncoderNotConfigured(
                "compute_sparse 需注入 SparseEncoder:生产 sparse 无系统配置工厂。"
            )
        if not contents:
            return []
        vecs = await self._sparse_encoder.aencode(list(contents))
        if len(vecs) != len(contents):
            raise ValueError(f"sparse 数量不符:got {len(vecs)}, expected {len(contents)}")
        return list(vecs)

    # —— bm25 分词 ——
    def compute_bm25_tokens(self, content: str) -> Bm25Tokens:
        tok = self._ensure_tokenizer()
        t = tok.tokenize(content)
        return Bm25Tokens(coarse=t.coarse_tokens, fine=t.fine_tokens)

    @property
    def dense_dim(self) -> int:
        return getattr(self._ensure_dense(), "embedding_dim", 0) or _settings_dense_dim()

    @property
    def fingerprint(self) -> dict:
        p = self._ensure_dense()
        return {
            "dense_model": getattr(p, "embedding_model", None),
            "sparse_encoder": (
                getattr(self._sparse_encoder, "model_name", None)
                if self._sparse_encoder
                else None
            ),
        }

    # —— 内部:惰性单例 ——
    def _ensure_dense(self):
        if self._dense_pipeline is None:
            self._dense_pipeline = self._dense_factory()
        return self._dense_pipeline

    def _ensure_tokenizer(self):
        if self._tokenizer is None:
            self._tokenizer = self._tokenizer_factory()
        return self._tokenizer


# —— 默认工厂:此处(且仅此处)触碰 rag。惰性 import,避免模块加载即拉起 rag 重依赖。——
def _default_dense_pipeline():
    from src.core.splitter.factory import create_chunk_embedding_pipeline

    return create_chunk_embedding_pipeline()


def _default_chunking_engine():
    from src.core.splitter.factory import _create_structured_chunking_engine
    from src.core.splitter.llm_embedding_client import create_lazy_system_embedding_client

    return _create_structured_chunking_engine(embedder=create_lazy_system_embedding_client())


def _default_tokenizer():
    from src.core.preprocessor.ragflow_tokenizer import RagFlowTokenizer

    return RagFlowTokenizer()


def _text_to_rag_chunk(text: str):
    from src.core.splitter.models import Chunk

    return Chunk(content=text, start_line=0, end_line=0)


def _settings_dense_dim() -> int:
    from src.config import settings

    return int(getattr(settings, "DENSE_VECTOR_DIMENSION", 1024))
