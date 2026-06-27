"""评测自持库的异步引擎与建表入口(Postgres)。

后端:独立 Postgres 实例,DSN 取自 ``EVAL_PG_DSN``(经 :func:`linkrag_eval.config.get_settings`)。
与生产解耦:独立引擎,不复用 ``src.database``,不读生产 ``Settings``。

schema 演进权威入口是 alembic/(``EvalBase.metadata``)。:func:`init_eval_schema` 的
``create_all`` 仅供单测 / 本地快速起库——生产环境用 alembic upgrade。
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from linkrag_eval.store.models import EvalBase


def eval_database_url(url: str | None = None) -> str:
    """评测库 URL:显式入参优先,否则取 ``EVAL_PG_DSN``。"""
    if url:
        return url
    from linkrag_eval.config import get_settings

    dsn = get_settings().pg_dsn
    if not dsn:
        raise RuntimeError(
            "EVAL_PG_DSN 未配置;请在 .env.eval 设独立 Postgres DSN"
            "(如 postgresql+asyncpg://user:pass@host:5432/linkrag_eval)。"
        )
    return dsn


@lru_cache(maxsize=4)
def get_eval_engine(url: str | None = None) -> AsyncEngine:
    """进程内缓存的评测异步引擎(按 url 缓存,便于测试传内存库)。"""
    return create_async_engine(eval_database_url(url), future=True)


@lru_cache(maxsize=4)
def get_eval_sessionmaker(url: str | None = None) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_eval_engine(url), expire_on_commit=False, class_=AsyncSession
    )


async def init_eval_schema(url: str | None = None) -> None:
    """建起全部 ``eval_*`` 表(幂等)。仅供单测 / 本地;生产用 alembic upgrade。"""
    engine = get_eval_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(EvalBase.metadata.create_all)
