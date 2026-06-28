"""Alembic 运行环境(LinkRag-Eval 独立评测库)。

DB URL 解析(同步 driver):``ALEMBIC_DATABASE_URL`` 环境变量优先,否则由 ``EVAL_DB_*``
配置构建并把 ``mysql+aiomysql`` 换成 ``mysql+pymysql``(迁移用同步驱动)。``target_metadata``
取 ``EvalBase.metadata``——评测库 schema 演进的唯一权威源,绝不碰生产 ``tolink_rag_db``。

只依赖 ``linkrag_eval.store.models``(纯 ORM,零 rag/零 src.* 依赖),与承重约定一致。
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from linkrag_eval.store.models import EvalBase

config = context.config


def _resolve_url() -> str | None:
    url = os.environ.get("ALEMBIC_DATABASE_URL")
    if url:
        return url
    # best-effort:缺 .env.eval 也允许离线生成,只在真正连库时才需要
    try:
        from linkrag_eval.config import get_settings

        dsn = get_settings().mysql_dsn()
        return dsn.replace("mysql+aiomysql://", "mysql+pymysql://")
    except Exception:  # noqa: BLE001
        return None


runtime_url = _resolve_url()
if runtime_url:
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
