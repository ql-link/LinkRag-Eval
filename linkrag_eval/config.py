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
    model_config = SettingsConfigDict(
        env_file=".env.eval", env_prefix="EVAL_", extra="ignore"
    )

    # —— Qdrant(同 host,eval 独立前缀)——
    qdrant_host: str = Field(default="http://localhost:36333")
    qdrant_prefix: str = Field(default="eval_kb_bucket")
    qdrant_bucket_count: int = Field(default=16)

    # —— eval 自持元数据/结果库(独立 Postgres)——
    pg_dsn: str = Field(default="")

    # —— judge LLM(解耦,纯环境变量)——
    judge_base_url: str = Field(default="")
    judge_api_key: str = Field(default="")
    judge_model: str = Field(default="")

    # —— 系统 embedder(dense 写入与召回 query 编码必须同一份)——
    embed_base_url: str = Field(default="")
    embed_api_key: str = Field(default="")
    embed_model: str = Field(default="text-embedding-v4")
    embed_dim: int = Field(default=1024)

    # —— sparse 编码器(eval 自带 llm 模块,模型可选;生产无系统工厂故 eval 自持)——
    sparse_provider: str = Field(default="ark")  # ark(doubao-vision/volcengine)| ...
    sparse_base_url: str = Field(default="")  # 完整端点;缺省回退 provider 默认
    sparse_api_key: str = Field(default="")
    sparse_model: str = Field(default="")
    sparse_top_k: int = Field(default=256)
    sparse_min_weight: float = Field(default=0.0)
    sparse_timeout_ms: int = Field(default=60000)

    # —— 路由常量(非真实用户,仅 bucket 分区)——
    user_id: int = Field(default=990001)

    # —— bm25 模式:stub | sparse_proxy | qdrant_bm25 ——
    bm25_mode: str = Field(default="stub")

    @field_validator("qdrant_prefix")
    @classmethod
    def _prefix_must_be_eval(cls, v: str) -> str:
        """护栏:前缀必须含 'eval',否则拒绝——防写串生产。"""
        if "eval" not in v:
            raise ValueError(
                f"EVAL_QDRANT_PREFIX={v!r} 不含 'eval';为防写串生产 collection,前缀必须含 'eval'。"
            )
        return v

    @field_validator("bm25_mode")
    @classmethod
    def _bm25_mode_known(cls, v: str) -> str:
        allowed = {"stub", "sparse_proxy", "qdrant_bm25"}
        if v not in allowed:
            raise ValueError(f"EVAL_BM25_MODE={v!r} 非法;应为 {sorted(allowed)} 之一。")
        return v


@lru_cache
def get_settings() -> EvalSettings:
    """进程内单例。测试可 ``get_settings.cache_clear()`` 后重载。"""
    return EvalSettings()
