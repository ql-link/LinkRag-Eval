"""评测自持库的异步引擎与建表入口。

默认后端是本地 ``runs/linkrag_eval.sqlite3``。它不依赖远端 MySQL，不复用
``src.database``，也不读生产 ``Settings``。

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

_ENGINES: set[AsyncEngine] = set()


def eval_database_url(url: str | None = None) -> str:
    """评测库 URL:显式入参优先，否则读取本地 ``EVAL_DB_URL``。"""
    if not url:
        from linkrag_eval.config import get_settings

        url = get_settings().database_url()
    if not url.startswith("sqlite+aiosqlite:///"):
        raise RuntimeError("评测运行库只允许本地 SQLite。")
    return url


@lru_cache(maxsize=4)
def get_eval_engine(url: str | None = None) -> AsyncEngine:
    """进程内缓存的评测异步引擎(按 url 缓存,便于测试传内存库)。"""
    database_url = eval_database_url(url)
    engine = create_async_engine(database_url, future=True)
    _ENGINES.add(engine)
    return engine


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


async def close_eval_engines() -> None:
    """释放进程内缓存的 eval DB 引擎。"""
    engines = list(_ENGINES)
    _ENGINES.clear()
    for engine in engines:
        await engine.dispose()
    get_eval_sessionmaker.cache_clear()
    get_eval_engine.cache_clear()
