"""活栈 smoke:显式开启后只读验证 eval MySQL/Qdrant 可达与隔离护栏。

默认 PR/本地单测跳过。运行:

    RUN_EVAL_INTEGRATION=1 python3 -m pytest tests/integration -q
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_EVAL_INTEGRATION") != "1",
        reason="需显式 RUN_EVAL_INTEGRATION=1 才连接真实 Qdrant/MySQL/embedder",
    ),
]


def test_live_settings_keep_eval_isolation() -> None:
    from linkrag_eval.config import get_settings

    settings = get_settings()
    assert "eval" in settings.qdrant_prefix
    assert settings.db_name == "tolink_rag_eval_db"
    assert settings.db_name != "tolink_rag_db"


async def test_eval_mysql_schema_is_reachable_and_current() -> None:
    from linkrag_eval.store.engine import close_eval_engines, get_eval_sessionmaker

    sessionmaker = get_eval_sessionmaker()
    try:
        async with sessionmaker() as session:
            db_name = (await session.execute(text("SELECT DATABASE()"))).scalar_one()
            assert db_name == "tolink_rag_eval_db"

            tables = (
                await session.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = DATABASE() AND table_name LIKE 'eval_%'"
                    )
                )
            ).scalars().all()
            assert {
                "eval_dataset",
                "eval_corpus_chunk",
                "eval_query",
                "eval_qrel",
                "eval_run",
                "eval_metric_result",
            }.issubset(set(tables))

            version = (
                await session.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one()
            assert version == "0003"
    finally:
        await close_eval_engines()


async def test_eval_qdrant_is_reachable() -> None:
    from qdrant_client import AsyncQdrantClient

    from linkrag_eval.config import get_settings

    settings = get_settings()
    client = AsyncQdrantClient(url=settings.qdrant_host, api_key=None)
    try:
        collections = await client.get_collections()
        names = {c.name for c in collections.collections}
        assert any(name.startswith(settings.qdrant_prefix) for name in names)
    finally:
        await client.close()
