"""产物计算契约。

eval 全仓只依赖本文件的抽象;唯一实现 :class:`RagProductComputer`(rag_adapter.py)是
唯一 import toLink-Rag 的类。所有 ``compute_*`` 纯计算:输入文本/chunk,输出向量/token,
**不写任何存储**。测试注入 fake。

为什么有 sparse 注入缝(:class:`SparseEncoder`):生产 sparse 只有 per-user 入口
(``aresolve_user_sparse_vector_service``,读用户配置表,在黑名单内),没有系统配置工厂。
故 sparse 的编码器由调用方按 EVAL_ 配置注入,不从 rag 直接取。详见 AGENTS.md / decoupling-plan。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class EvalChunk:
    """一个评测 chunk 的最小载体。``ordinal`` 是 doc 内序号(参与 uuid5 chunk_id)。"""

    content: str
    ordinal: int
    start_line: int | None = None
    end_line: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DenseVec:
    """稠密向量产物。"""

    values: list[float]


@dataclass(frozen=True)
class SparseVec:
    """稀疏向量产物(Qdrant named sparse 口径:index→weight)。"""

    indices: list[int]
    values: list[float]


@dataclass(frozen=True)
class Bm25Tokens:
    """BM25 预分词产物:粗/细粒度 token 串(ES/Qdrant-BM25 共用口径)。"""

    coarse: str
    fine: str


@runtime_checkable
class SparseEncoder(Protocol):
    """稀疏编码缝:文本 → SparseVec。生产无系统工厂,故由 eval 按 EVAL_ 配置注入实现。"""

    async def aencode(self, texts: Sequence[str]) -> list[SparseVec]: ...


@runtime_checkable
class DenseEncoder(Protocol):
    """稠密编码缝:文本 → 向量。dense 并入 eval llm 模块(与 sparse 统一),由 EVAL_EMBED_* 注入。

    写入侧(compute_dense)与召回 query 侧共用本编码器同一口径,保证向量空间一致。
    """

    async def aembed(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def aembed_query(self, text: str) -> list[float]: ...

    @property
    def dim(self) -> int: ...

    @property
    def model_name(self) -> str: ...


@runtime_checkable
class ProductComputer(Protocol):
    """eval 唯一依赖的产物计算契约。默认实现 = RagProductComputer。"""

    async def compute_chunks(
        self, text: str, *, source_file: str | None = None
    ) -> list[EvalChunk]: ...

    async def compute_dense(self, contents: Sequence[str]) -> list[DenseVec]: ...

    async def compute_sparse(self, contents: Sequence[str]) -> list[SparseVec]: ...

    def compute_bm25_tokens(self, content: str) -> Bm25Tokens: ...

    @property
    def dense_dim(self) -> int: ...

    @property
    def fingerprint(self) -> dict: ...
