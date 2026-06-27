"""评测自持库的异步引擎与建表入口(MySQL)。

后端:MySQL,**与生产同一服务器、独立库 ``tolink_rag_eval_db``**(库级隔离,类比 Qdrant
前缀隔离)。连接参数由 ``EVAL_DB_*`` 配置构建(``mysql+aiomysql``),复用生产服务器/账号、
只换库名。与生产解耦:独立引擎,不复用 ``src.database``,不读生产 ``Settings``;只写 eval 库,
**绝不碰生产 ``tolink_rag_db`` 的表**。

库需先建好(utf8mb4)::

    CREATE DATABASE IF NOT EXISTS tolink_rag_eval_db
      DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

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
    """评测库 URL:显式入参优先(测试常传 sqlite),否则由 ``EVAL_DB_*`` 构建 MySQL DSN。"""
    if url:
        return url
    from linkrag_eval.config import get_settings

    return get_settings().mysql_dsn()


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
