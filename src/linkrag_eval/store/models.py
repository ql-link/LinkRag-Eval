"""评测自持存储 ORM(独立 ``EvalBase``,MySQL)。

搬迁自源仓库 ``src/evaluation/store/models.py``,改动:
- 后端定为 MySQL(同生产服务器、独立库 ``tolink_rag_eval_db``):自增代理键用纯
  ``BigInteger``(MySQL AUTO_INCREMENT),去掉 SQLite variant。
- ``eval_corpus_chunk.es_indexed`` → ``bm25_indexed``(对齐目标态无 ES、bm25 走 Qdrant)。
- ``eval_run`` 新增 ``computer_fingerprint``(dense 模型 / sparse encoder / bm25 mode 指纹)。

硬约束:独立 ``EvalBase``,不 import ``src.*``,零生产依赖;只建 eval 库的表,绝不碰生产
``tolink_rag_db``。枚举值以 ``String`` + 注释承载(改值不需 migration)。模型 dialect 无关
(单测仍用 SQLite 建表);MySQL 侧 utf8mb4 由库默认字符集 + 连接 ``charset=utf8mb4`` 保证。
schema 演进唯一入口是 alembic/。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class EvalBase(DeclarativeBase):
    """评测自持存储的独立声明基类,与生产 ``Base`` 互不相干。"""


class EvalDatasetDB(EvalBase):
    """语料编目。``dataset_id`` 即召回里的 ``set_id``(保留号段,非自增)。"""

    __tablename__ = "eval_dataset"

    dataset_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)  # opensource|synth|selfdoc
    domain: Mapped[str | None] = mapped_column(String(32), nullable=True)
    genre: Mapped[str | None] = mapped_column(String(32), nullable=True)
    relevance_type: Mapped[str] = mapped_column(String(8), nullable=False, default="binary")  # binary|graded
    batch: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ingestion_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class EvalCorpusChunkDB(EvalBase):
    """评测语料 chunk(取代复用生产 ``kb_document_chunk``)。

    无 ``user_id``(路由常量不入表)、无生命周期状态机、无向量模型列、无 ``bucket_id``
    (索引时按 chunk_id 现算);索引状态三个布尔(dense/sparse/bm25)。
    """

    __tablename__ = "eval_corpus_chunk"

    chunk_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    dataset_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # = set_id
    doc_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_passage_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    char_len: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_len: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dense_indexed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sparse_indexed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bm25_indexed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ingest_run_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_eval_corpus_dataset_doc", "dataset_id", "doc_id"),
    )


class EvalQueryDB(EvalBase):
    """黄金集 query。"""

    __tablename__ = "eval_query"

    query_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    primary_dataset_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    dataset_ids_json: Mapped[str] = mapped_column(Text, nullable=False)  # 召回 scope 完整列表
    text: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False, default="keyword")  # QuestionType
    golden_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    gate_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # passed|hard_case
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_eval_query_dataset_type", "primary_dataset_id", "type"),
    )


class EvalQrelDB(EvalBase):
    """相关性判定(qrel)。二值 grade=1;分级 0–3。reference 为 chunk_id 或 str(doc_id)。"""

    __tablename__ = "eval_qrel"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    query_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reference_kind: Mapped[str] = mapped_column(String(8), nullable=False, default="chunk")  # chunk|doc
    grade: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("query_id", "reference_id", "reference_kind", name="uk_eval_qrel"),
        Index("idx_eval_qrel_query", "query_id"),
    )


class EvalRunDB(EvalBase):
    """一轮运行 + 配置快照。snapshot 整块存(冻结契约)+ 打平可索引维度列。"""

    __tablename__ = "eval_run"

    run_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    git_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    dataset_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    layers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    baseline_run_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")  # running|done|failed
    snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 打平的可索引维度(与 snapshot_json 同源,供台账过滤)
    sparse_provider: Mapped[str | None] = mapped_column(String(128), nullable=True)
    top_k: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled_sources: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rrf_k: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rerank_top_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chat_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    judge_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    generator_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # 产物计算指纹:dense 模型 / sparse encoder / bm25 mode,供偏差归因(decoupling-plan 风险 C)
    computer_fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 运行质量:用于筛选可固化基线。clean = failed_samples=0 且 zero_ranked=0。
    run_quality: Mapped[str | None] = mapped_column(String(16), nullable=True)  # clean|non-clean
    failed_samples: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failed_sources_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    zero_ranked: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EvalMetricResultDB(EvalBase):
    """指标长表。联合主键与报告台账行对齐。"""

    __tablename__ = "eval_metric_result"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(96), nullable=False)
    layer: Mapped[str] = mapped_column(String(16), nullable=False)
    metric: Mapped[str] = mapped_column(String(32), nullable=False)
    k: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relevance_scale: Mapped[str] = mapped_column(String(8), nullable=False, default="binary")  # binary|graded
    type_bucket: Mapped[str] = mapped_column(String(24), nullable=False, default="__all__")
    value: Mapped[float] = mapped_column(Float, nullable=False)
    n: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint(
            "run_id", "layer", "metric", "k", "relevance_scale", "type_bucket",
            name="uk_eval_metric",
        ),
        Index("idx_eval_metric_metric_layer_k", "metric", "layer", "k"),
    )
