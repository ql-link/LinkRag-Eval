"""LinkRag-Eval 运行时配置。

独立于生产 ``src.config``:只读 ``EVAL_*`` 环境变量(样例见 .env.eval.example),
真值放 ``.env.eval``(gitignored)。所有模块经 :func:`get_settings` 取配置,不直接读 env。

护栏:Qdrant 前缀必须含 ``eval``——构造期校验,防写串生产 collection。
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EvalSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.eval", env_prefix="EVAL_", extra="ignore")

    # —— Qdrant(同 host,eval 独立前缀)——
    qdrant_host: str = Field(default="http://localhost:36333")
    qdrant_prefix: str = Field(default="eval_kb_bucket")
    qdrant_bucket_count: int = Field(default=16)
    sparse_vector_name: str = Field(default="sparse_text")
    qdrant_bm25_collection: str = Field(default="eval_bm25")
    qdrant_bm25_vector_name: str = Field(default="bm25_text")
    bm25_sqlite_path: str = Field(default="runs/bm25_eval.sqlite3")

    # —— eval 自持元数据/结果库(MySQL:同生产服务器、独立库 tolink_rag_eval_db)——
    db_host: str = Field(default="127.0.0.1")
    db_port: int = Field(default=3306)
    db_user: str = Field(default="root")
    db_password: str = Field(default="")
    db_name: str = Field(default="tolink_rag_eval_db")
    db_url: str = Field(default="")  # 完整 DSN 覆盖;否则由上面字段构建(mysql+aiomysql)

    # —— judge LLM(测量仪器,解耦于生产解析链;base_url 为完整 chat completions 端点)——
    judge_base_url: str = Field(default="")
    judge_api_key: str = Field(default="")
    judge_model: str = Field(default="")
    judge_timeout_s: float = Field(default=90.0)  # 推理模型偏慢
    judge_max_retries: int = Field(default=6)  # 瞬时错误(429/5xx)退避重试
    judge_concurrency: int = Field(default=6)  # DeepSeek 端点并发保守默认值

    # —— query rewrite planner(eval 实验能力,独立于 judge 与生产用户模型配置)——
    rewrite_base_url: str = Field(default="")  # 完整 chat completions 端点
    rewrite_api_key: str = Field(default="")
    rewrite_model: str = Field(default="")
    rewrite_timeout_s: float = Field(default=90.0)
    rewrite_max_retries: int = Field(default=3)
    rewrite_concurrency: int = Field(default=4)
    rewrite_temperature: float = Field(default=0.0)
    rewrite_max_tokens: int = Field(default=900)
    rewrite_prompt_version: str = Field(default="query-rewrite-v1")

    # —— rerank(eval 自持 HTTP 客户端;绝不解析生产用户模型配置)——
    rerank_provider: str = Field(default="dashscope")  # dashscope | standard
    rerank_base_url: str = Field(default="")  # 完整 provider rerank 端点
    rerank_api_key: str = Field(default="")
    rerank_model: str = Field(default="")
    rerank_timeout_ms: int = Field(default=60000)
    rerank_max_candidates: int = Field(default=80)
    rerank_max_document_chars: int = Field(default=1200)

    # —— dense embedder(eval 自带 llm 模块,模型可选;写入与召回 query 必用同一份)——
    embed_base_url: str = Field(default="")  # OpenAI 兼容 base,自动补 /embeddings
    embed_api_key: str = Field(default="")
    embed_model: str = Field(default="text-embedding-v4")
    embed_dim: int = Field(default=1024)
    embed_batch_size: int = Field(default=10)  # text-embedding-v4 单批上限 10
    embed_timeout_ms: int = Field(default=60000)

    # —— 候选池专用 alt embedding(独立于当前被测 dense,不写正式 Qdrant)——
    alt_embed_provider: str = Field(default="openai")
    alt_embed_base_url: str = Field(default="")
    alt_embed_api_key: str = Field(default="")
    alt_embed_model: str = Field(default="")
    alt_embed_dim: int = Field(default=1024)
    alt_embed_batch_size: int = Field(default=10)
    alt_embed_timeout_ms: int = Field(default=60000)
    alt_embed_sqlite_path: str = Field(default="runs/alt_embedding_eval.sqlite3")

    # —— sparse 编码器(eval 自带 llm 模块,模型可选;生产无系统工厂故 eval 自持)——
    sparse_provider: str = Field(default="ark")  # ark(doubao-vision/volcengine)| ...
    sparse_base_url: str = Field(default="")  # 完整端点;缺省回退 provider 默认
    sparse_api_key: str = Field(default="")
    sparse_model: str = Field(default="")
    sparse_top_k: int = Field(default=256)
    sparse_min_weight: float = Field(default=0.0)
    sparse_timeout_ms: int = Field(default=60000)

    # —— 召回装配阈值(过滤低质量分路命中;默认来自 2026-07-02 活栈网格搜索)——
    recall_dense_score_threshold: float = Field(default=0.30)
    recall_sparse_score_threshold: float = Field(default=0.20)
    recall_dense_top_k: int = Field(default=150)
    recall_sparse_top_k: int = Field(default=50)
    recall_bm25_top_k: int = Field(default=100)
    recall_fusion_strategy: str = Field(default="weighted_score")
    recall_dense_weight: float = Field(default=0.70)
    recall_sparse_weight: float = Field(default=0.15)
    recall_bm25_weight: float = Field(default=0.15)

    # —— 路由常量(非真实用户,仅 bucket 分区)——
    user_id: int = Field(default=990001)

    # —— bm25 模式:stub | sparse_proxy | qdrant_bm25 | sqlite_fts5 ——
    bm25_mode: str = Field(default="stub")
    bm25_k1: float = Field(default=1.2)
    bm25_b: float = Field(default=0.75)
    bm25_avgdl: float = Field(default=200.0)
    bm25_avgdl_fine: float = Field(default=220.0)
    bm25_coarse_boost: float = Field(default=2.0)
    bm25_sqlite_coarse_weight: float = Field(default=2.0)
    bm25_sqlite_fine_weight: float = Field(default=1.0)

    @field_validator("qdrant_prefix", "qdrant_bm25_collection")
    @classmethod
    def _prefix_must_be_eval(cls, v: str) -> str:
        """护栏:前缀必须含 'eval',否则拒绝——防写串生产。"""
        if "eval" not in v:
            raise ValueError(
                f"Qdrant eval 标识 {v!r} 不含 'eval';为防写串生产 collection,必须含 'eval'。"
            )
        return v

    @field_validator("bm25_mode")
    @classmethod
    def _bm25_mode_known(cls, v: str) -> str:
        allowed = {"stub", "sparse_proxy", "qdrant_bm25", "sqlite_fts5"}
        if v not in allowed:
            raise ValueError(f"EVAL_BM25_MODE={v!r} 非法;应为 {sorted(allowed)} 之一。")
        return v

    @field_validator("recall_fusion_strategy")
    @classmethod
    def _fusion_strategy_known(cls, v: str) -> str:
        normalized = v.strip().lower()
        allowed = {"rrf", "weighted_score"}
        if normalized not in allowed:
            raise ValueError(
                f"EVAL_RECALL_FUSION_STRATEGY={v!r} 非法;应为 {sorted(allowed)} 之一。"
            )
        return normalized

    @field_validator("rerank_provider")
    @classmethod
    def _rerank_provider_known(cls, v: str) -> str:
        normalized = v.strip().lower()
        if normalized not in {"dashscope", "standard"}:
            raise ValueError("EVAL_RERANK_PROVIDER 仅支持 'dashscope' 或 'standard'。")
        return normalized

    @field_validator("alt_embed_provider")
    @classmethod
    def _alt_embed_provider_known(cls, v: str) -> str:
        normalized = v.strip().lower()
        allowed = {"openai", "bge_m3_http", "bge_m3", "bgem3"}
        if normalized not in allowed:
            raise ValueError(f"EVAL_ALT_EMBED_PROVIDER={v!r} 非法;应为 {sorted(allowed)} 之一。")
        return "bge_m3_http" if normalized in {"bge_m3", "bgem3"} else normalized

    def mysql_dsn(self) -> str:
        """eval 库异步 DSN(mysql+aiomysql)。``EVAL_DB_URL`` 覆盖优先,否则由字段构建。"""
        if self.db_url:
            return self.db_url
        from urllib.parse import quote_plus

        pwd = quote_plus(self.db_password)
        return (
            f"mysql+aiomysql://{self.db_user}:{pwd}@{self.db_host}:{self.db_port}"
            f"/{self.db_name}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> EvalSettings:
    """进程内单例。测试可 ``get_settings.cache_clear()`` 后重载。"""
    return EvalSettings()
