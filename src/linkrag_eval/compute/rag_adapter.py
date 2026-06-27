""":class:`ProductComputer` 的默认实现——**唯一允许 import toLink-Rag(src.*)的文件**。

把 rag 的纯计算函数封装成产物级接口:
- chunk 切分 → ``ChunkingEngine.aprocess``(rag)
- bm25 分词 → ``RagFlowTokenizer.tokenize``(rag)
- dense / sparse 向量 → 注入的 :class:`DenseEncoder` / :class:`SparseEncoder`(eval 自带 llm 模块,
  EVAL_EMBED_* / EVAL_SPARSE_* 配置)。生产 dense 系统工厂读 src.config、sparse 无系统工厂(只
  per-user),为统一与彻底解耦,二者均由 eval 的 llm 模块承载,**不经 rag**。

故本文件对 rag 的依赖只剩 chunk 切分与 bm25 分词两处。rag 改了这两处签名,只打穿本文件
+ 契约测试,在一处修。
"""

from __future__ import annotations

from typing import Any, Sequence

from linkrag_eval.compute.protocol import (
    Bm25Tokens,
    DenseEncoder,
    DenseVec,
    EvalChunk,
    SparseEncoder,
    SparseVec,
)


class SparseEncoderNotConfigured(RuntimeError):
    """未注入 sparse 编码器(未配置 EVAL_SPARSE_*)。见 decoupling-plan 风险 C。"""


class DenseEncoderNotConfigured(RuntimeError):
    """未注入 dense 编码器(未配置 EVAL_EMBED_*)。"""


class RagProductComputer:
    """默认产物计算器。chunk/bm25 复用 rag 纯函数;dense/sparse 由 eval llm 注入缝提供。

    Args:
        dense_encoder / sparse_encoder: eval 自带编码器(按 EVAL_EMBED_* / EVAL_SPARSE_* 配置);
            缺省自动装配,未配置则延迟到调用时报清晰错误。
        chunking_engine_factory / tokenizer_factory: 测试可注入 fake。
    """

    def __init__(
        self,
        *,
        dense_encoder: DenseEncoder | None = None,
        sparse_encoder: SparseEncoder | None = None,
        chunking_engine_factory: Any | None = None,
        tokenizer_factory: Any | None = None,
    ) -> None:
        self._dense_encoder = dense_encoder if dense_encoder is not None else _try_build_dense()
        self._sparse_encoder = sparse_encoder if sparse_encoder is not None else _try_build_sparse()
        self._chunker_factory = chunking_engine_factory or _default_chunking_engine
        self._tokenizer_factory = tokenizer_factory or _default_tokenizer
        self._tokenizer = None

    # —— chunk 切分(rag)——
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

    # —— dense 向量(eval llm 注入缝)——
    async def compute_dense(self, contents: Sequence[str]) -> list[DenseVec]:
        if self._dense_encoder is None:
            raise DenseEncoderNotConfigured(
                "compute_dense 需注入 DenseEncoder:请配置 EVAL_EMBED_*。"
            )
        if not contents:
            return []
        vecs = await self._dense_encoder.aembed(list(contents))
        if len(vecs) != len(contents):
            raise ValueError(f"dense 数量不符:got {len(vecs)}, expected {len(contents)}")
        return [DenseVec(values=list(v)) for v in vecs]

    # —— sparse 向量(eval llm 注入缝)——
    async def compute_sparse(self, contents: Sequence[str]) -> list[SparseVec]:
        if self._sparse_encoder is None:
            raise SparseEncoderNotConfigured(
                "compute_sparse 需注入 SparseEncoder:请配置 EVAL_SPARSE_*。"
            )
        if not contents:
            return []
        vecs = await self._sparse_encoder.aencode(list(contents))
        if len(vecs) != len(contents):
            raise ValueError(f"sparse 数量不符:got {len(vecs)}, expected {len(contents)}")
        return list(vecs)

    # —— bm25 分词(rag)——
    def compute_bm25_tokens(self, content: str) -> Bm25Tokens:
        tok = self._ensure_tokenizer()
        t = tok.tokenize(content)
        return Bm25Tokens(coarse=t.coarse_tokens, fine=t.fine_tokens)

    @property
    def dense_dim(self) -> int:
        return self._dense_encoder.dim if self._dense_encoder is not None else 0

    @property
    def fingerprint(self) -> dict:
        return {
            "dense_model": getattr(self._dense_encoder, "model_name", None),
            "sparse_encoder": getattr(self._sparse_encoder, "model_name", None),
        }

    def _ensure_tokenizer(self):
        if self._tokenizer is None:
            self._tokenizer = self._tokenizer_factory()
        return self._tokenizer


# —— eval llm 编码器缺省装配(未配置不在构造期失败;调用时再报)——
def _try_build_dense():
    from linkrag_eval.llm.dense_client import build_dense_embedder

    try:
        return build_dense_embedder()
    except Exception:
        return None


def _try_build_sparse():
    from linkrag_eval.llm.sparse_client import build_sparse_encoder

    try:
        return build_sparse_encoder()
    except Exception:
        return None


# —— rag 纯函数(chunk 切分 / bm25 分词):此处(且仅此处)触碰 rag,惰性 import ——
def _default_chunking_engine():
    from src.core.splitter.factory import _create_structured_chunking_engine
    from src.core.splitter.llm_embedding_client import create_lazy_system_embedding_client

    return _create_structured_chunking_engine(embedder=create_lazy_system_embedding_client())


def _default_tokenizer():
    from src.core.preprocessor.ragflow_tokenizer import RagFlowTokenizer

    return RagFlowTokenizer()
