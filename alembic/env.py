"""Alembic 运行环境(LinkRag-Eval 独立评测库)。

DB URL 解析(同步 driver):程序化 ``config.attributes['database_url']`` 优先，
其次 ``ALEMBIC_DATABASE_URL`` 环境变量，否则读取 ``EVAL_DB_URL``。
最终 URL 统一校验为本地 SQLite，并把异步 driver 换成同步 driver；
配置错误直接终止，不回退到 ``alembic.ini`` 中的 URL。``target_metadata``
取 ``EvalBase.metadata``——评测库 schema 演进的唯一权威源,绝不碰生产 ``tolink_rag_db``。

只依赖 ``linkrag_eval.store.models``(纯 ORM,零 rag/零 src.* 依赖),与承重约定一致。
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from linkrag_eval.store.models import EvalBase

config = context.config


def _resolve_url() -> str:
    url = config.attributes.get("database_url")
    if url is None:
        url = os.environ.get("ALEMBIC_DATABASE_URL")
    if url is None:
        from linkrag_eval.config import get_settings

        url = get_settings().database_url()
    if not isinstance(url, str) or not url.startswith(("sqlite+aiosqlite:///", "sqlite:///")):
        raise ValueError("迁移只允许显式本地 SQLite URL")
    return url.replace("sqlite+aiosqlite://", "sqlite://", 1)


runtime_url = _resolve_url()
config.set_main_option("sqlalchemy.url", runtime_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = EvalBase.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
