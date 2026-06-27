"""EvalCorpusRepo:对临时 SQLite 验证建表 / 编目 / 落库 / 幂等(不需 rag、不连 PG)。"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from linkrag_eval.store.corpus_repo import CorpusChunkRow, EvalCorpusRepo
from linkrag_eval.store.engine import get_eval_engine, get_eval_sessionmaker
from linkrag_eval.store.models import EvalCorpusChunkDB, EvalDatasetDB


@pytest.fixture
def repo(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path}/eval.db"
    # 清掉 lru_cache 中可能的同名引擎,确保拿到本测试的库
    get_eval_engine.cache_clear()
    get_eval_sessionmaker.cache_clear()
    return EvalCorpusRepo(url=url), url


async def _count(url, model) -> int:
    sm = get_eval_sessionmaker(url)
    async with sm() as s:
        return (await s.execute(select(func.count()).select_from(model))).scalar_one()


async def test_register_and_upsert(repo) -> None:
    r, url = repo
    await r.init_schema()
    await r.register_dataset(990131, name="tech_synth", source_type="synth", domain="tech")
    rows = [
        CorpusChunkRow(
            chunk_id=f"c{i}", dataset_id=990131, doc_id=991310000 + i,
            content=f"内容{i}", content_hash="h", source_passage_id=f"p{i}",
            ordinal=0, dense_indexed=True, sparse_indexed=True, bm25_indexed=False,
        )
        for i in range(3)
    ]
    n = await r.upsert_chunks(rows)
    assert n == 3
    assert await _count(url, EvalDatasetDB) == 1
    assert await _count(url, EvalCorpusChunkDB) == 3


async def test_upsert_idempotent(repo) -> None:
    r, url = repo
    await r.init_schema()
    row = CorpusChunkRow(
        chunk_id="x", dataset_id=1, doc_id=1, content="a", content_hash="h"
    )
    await r.upsert_chunks([row])
    await r.upsert_chunks([row])  # 重灌
    assert await _count(url, EvalCorpusChunkDB) == 1  # merge,不重复


async def test_empty_upsert_noop(repo) -> None:
    r, _ = repo
    await r.init_schema()
    assert await r.upsert_chunks([]) == 0
