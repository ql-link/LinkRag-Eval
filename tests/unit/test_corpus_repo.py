"""EvalCorpusRepo:对临时 SQLite 验证建表 / 编目 / 落库 / 幂等(不需 rag、不连 MySQL)。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import IntegrityError

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


async def test_mark_bm25_indexed(repo) -> None:
    r, _ = repo
    await r.init_schema()
    await r.upsert_chunks([
        CorpusChunkRow(chunk_id="c1", dataset_id=990101, doc_id=1, content="正文一", content_hash="h1"),
        CorpusChunkRow(chunk_id="c2", dataset_id=990101, doc_id=2, content="正文二", content_hash="h2"),
    ])

    assert await r.mark_bm25_indexed(["c1"]) == 1
    rows = await r.fetch_chunks_for_datasets([990101])
    by_id = {row.chunk_id: row for row in rows}
    assert by_id["c1"].bm25_indexed is True
    assert by_id["c2"].bm25_indexed is False


async def test_fetch_contents_by_ids_reads_only_requested_chunks(repo) -> None:
    r, _ = repo
    await r.init_schema()
    await r.upsert_chunks([
        CorpusChunkRow(chunk_id="c1", dataset_id=1, doc_id=1, content="正文一", content_hash="h1"),
        CorpusChunkRow(chunk_id="c2", dataset_id=1, doc_id=2, content="", content_hash="h2"),
    ])

    assert await r.fetch_contents_by_ids(["missing", "c2", "c1"]) == {"c1": "正文一"}


async def test_fetch_candidate_rows_preserves_empty_values_and_exact_dataset_scope(repo):
    r, _ = repo
    await r.init_schema()
    await r.upsert_chunks([
        CorpusChunkRow(chunk_id="a", dataset_id=1, doc_id=11, content="  正文\t ",
                       content_hash="h1", source_passage_id="0007"),
        CorpusChunkRow(chunk_id="b", dataset_id=1, doc_id=12, content="",
                       content_hash="h2", source_passage_id=None),
        CorpusChunkRow(chunk_id="other", dataset_id=2, doc_id=13, content="别的数据集",
                       content_hash="h3", source_passage_id="0007"),
    ])
    rows = await r.fetch_candidate_rows([(1, "b"), (1, "a"), (1, "a"), (1, "other"), (1, "missing")])
    assert {row["chunk_id"] for row in rows} == {"a", "b"}
    by_id = {row["chunk_id"]: row for row in rows}
    assert by_id["a"] == {
        "dataset_id": 1, "chunk_id": "a", "doc_id": 11, "content": "  正文\t ",
        "source_passage_id": "0007", "ordinal": 0,
    }
    assert by_id["b"]["content"] == ""
    assert by_id["b"]["source_passage_id"] is None
    assert await r.fetch_candidate_rows([]) == []


async def test_fetch_ingest_rows_is_batch_scoped_and_exposes_identity_conflicts(repo):
    r, _ = repo
    await r.init_schema()
    unfinished = CorpusChunkRow(
        chunk_id="requested", dataset_id=994000, doc_id=10,
        content="  原样正文\t ", content_hash="h1", source_passage_id="0007",
        ordinal=0, char_len=8, token_len=3, dense_indexed=True,
        dense_input_chars=4, sparse_input_chars=6,
        sparse_indexed=True, bm25_indexed=False, ingest_run_id="first-batch",
    )
    foreign = CorpusChunkRow(
        chunk_id="foreign", dataset_id=994001, doc_id=20,
        content="", content_hash="h2", source_passage_id=None,
    )
    await r.upsert_chunks([
        unfinished,
        foreign,
        CorpusChunkRow(
            chunk_id="not-requested", dataset_id=994000, doc_id=30,
            content="本批以外", content_hash="h3",
        ),
    ])

    actual = await r.fetch_ingest_rows(
        994000, ["requested", "missing", "foreign", "requested"]
    )

    assert {row.chunk_id: row for row in actual} == {
        "requested": unfinished, "foreign": foreign,
    }
    assert len(actual) == 2
    assert await r.fetch_ingest_rows(994000, []) == []


async def test_bulk_upsert_replaces_nullable_fields_flags_and_preserves_created_at(repo):
    r, url = repo
    await r.init_schema()
    await r.upsert_chunks([
        CorpusChunkRow(
            chunk_id="same", dataset_id=1, doc_id=10, content="原正文",
            content_hash="old-hash", source_passage_id="0001", ordinal=0,
            char_len=3, token_len=2, dense_indexed=True, sparse_indexed=True,
            dense_input_chars=3, sparse_input_chars=2,
            bm25_indexed=True, ingest_run_id="old-run",
        ),
    ])
    created_at = datetime(2001, 2, 3, 4, 5, 6, tzinfo=UTC).replace(tzinfo=None)
    sm = get_eval_sessionmaker(url)
    async with sm() as s:
        await s.execute(update(EvalCorpusChunkDB).values(created_at=created_at))
        await s.commit()
    replacement = CorpusChunkRow(
        chunk_id="same", dataset_id=2, doc_id=20, content="替换正文",
        content_hash="new-hash", ordinal=4,
    )

    assert await r.upsert_chunks([replacement]) == 1

    assert await r.fetch_ingest_rows(2, ["same"]) == [replacement]
    async with sm() as s:
        assert (
            await s.execute(select(EvalCorpusChunkDB.created_at))
        ).scalar_one() == created_at


async def test_bulk_upsert_uses_one_executemany_without_per_row_reads(repo):
    r, url = repo
    await r.init_schema()
    engine = get_eval_engine(url).sync_engine
    calls = []

    def record_execute(conn, cursor, statement, parameters, context, executemany):
        calls.append((statement, len(parameters), executemany))

    event.listen(engine, "before_cursor_execute", record_execute)
    try:
        assert await r.upsert_chunks([
            CorpusChunkRow(
                chunk_id=f"batch-{i}", dataset_id=994000, doc_id=i,
                content=f"条目{i}", content_hash=f"h{i}",
            )
            for i in range(128)
        ]) == 128
    finally:
        event.remove(engine, "before_cursor_execute", record_execute)

    assert len(calls) == 1
    statement, parameter_count, executemany = calls[0]
    assert statement.startswith("INSERT INTO eval_corpus_chunk")
    assert parameter_count == 128
    assert executemany is True


async def test_bulk_upsert_failure_rolls_back_the_whole_batch(repo):
    r, url = repo
    await r.init_schema()
    original = CorpusChunkRow(
        chunk_id="existing", dataset_id=1, doc_id=10, content="原正文", content_hash="h1",
    )
    await r.upsert_chunks([original])

    with pytest.raises(IntegrityError):
        await r.upsert_chunks([
            CorpusChunkRow(
                chunk_id="existing", dataset_id=1, doc_id=10,
                content="未提交改写", content_hash="h2",
            ),
            CorpusChunkRow(
                chunk_id="new", dataset_id=1, doc_id=11, content="未提交新增", content_hash="h3",
            ),
            CorpusChunkRow(
                chunk_id="invalid", dataset_id=1, doc_id=12,
                content=None, content_hash="h4",  # type: ignore[arg-type]
            ),
        ])

    assert await _count(url, EvalCorpusChunkDB) == 1
    assert await r.fetch_ingest_rows(1, ["existing", "new", "invalid"]) == [original]


async def test_verify_dataset_count_uses_actual_counts_without_body_or_flags(repo):
    r, url = repo
    await r.init_schema()
    await r.upsert_chunks([
        CorpusChunkRow(
            chunk_id=f"c{i}", dataset_id=994000, doc_id=i,
            content="只核对行数，不读正文", content_hash=f"h{i}",
        )
        for i in range(2)
    ])  # 三路标记均为 False，不能拿标记数量代替实际行数。
    engine = get_eval_engine(url).sync_engine
    statements = []

    def record_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(engine, "before_cursor_execute", record_execute)
    try:
        assert await r.verify_dataset_count(dataset_id=994000, expected_count=2) is None
    finally:
        event.remove(engine, "before_cursor_execute", record_execute)

    assert len(statements) == 1
    assert statements[0].startswith("select count(")
    assert statements[0].count("count(") == 2
    assert "content" not in statements[0]
    assert "indexed" not in statements[0]


@pytest.mark.parametrize("dataset_ids,expected_dataset_count", [
    ([], 0),
    ([994000], 1),
    ([994000, 994000, 994000], 3),
    ([994000, 994000, 994001], 2),
    ([994000, 994001], 1),
])
async def test_verify_dataset_count_rejects_missing_extra_and_foreign_rows(
    repo, dataset_ids, expected_dataset_count,
):
    r, _ = repo
    await r.init_schema()
    await r.upsert_chunks([
        CorpusChunkRow(
            chunk_id=f"c{i}", dataset_id=did, doc_id=i, content="正文", content_hash=f"h{i}",
        )
        for i, did in enumerate(dataset_ids)
    ])

    with pytest.raises(ValueError, match="独立语料库数量或归属不一致") as error:
        await r.verify_dataset_count(dataset_id=994000, expected_count=2)

    message = str(error.value)
    assert "expected_count=2" in message
    assert f"total_count={len(dataset_ids)}" in message
    assert f"dataset_count={expected_dataset_count}" in message
    assert f"other_dataset_count={len(dataset_ids) - expected_dataset_count}" in message


async def test_encoding_summary_counts_unique_completed_rows_and_keeps_unknown(repo):
    r, url = repo
    await r.init_schema()
    base = CorpusChunkRow(
        chunk_id="base", dataset_id=1, doc_id=1, content="abcdef", content_hash="h",
        char_len=6, dense_indexed=True, sparse_indexed=True, bm25_indexed=True,
    )
    lengths = [(3, 6), (6, 2), (2, 1), (6, 6), (None, 6), (6, None), (None, None), (1, None)]
    rows = [
        replace(base, chunk_id=f"c{i}", doc_id=i, dense_input_chars=dense,
                sparse_input_chars=sparse, char_len=None if i == 6 else 6)
        for i, (dense, sparse) in enumerate(lengths)
    ]
    rows += [replace(base, chunk_id="pending", dense_indexed=False)]
    rows += [replace(base, chunk_id="foreign", dataset_id=2, dense_input_chars=1, sparse_input_chars=1)]
    await r.upsert_chunks(rows)
    await r.upsert_chunks(rows)
    engine = get_eval_engine(url).sync_engine
    statements = []

    def record_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(engine, "before_cursor_execute", record_execute)
    try:
        summary = await r.summarize_encoding_inputs(dataset_id=1)
    finally:
        event.remove(engine, "before_cursor_execute", record_execute)
    assert summary == {
        "dataset_id": 1, "total_rows": 9, "completed_rows": 8, "incomplete_rows": 1,
        "dense": {"shortened": 3, "unchanged": 3, "unknown": 2},
        "sparse": {"shortened": 2, "unchanged": 3, "unknown": 3},
        "either_route_shortened": 4, "both_routes_unchanged": 1, "affected_status_unknown": 3,
    }
    assert len(statements) == 1 and "content" not in statements[0]
    empty = await r.summarize_encoding_inputs(dataset_id=999)
    assert empty["total_rows"] == empty["completed_rows"] == empty["either_route_shortened"] == 0


@pytest.mark.parametrize("char_len,dense_chars,sparse_chars", [
    (3, -1, 3), (3, 4, 3), (3, 0, 3), (3, 3, 0), (-1, None, None),
])
async def test_encoding_summary_rejects_invalid_observed_lengths(repo, char_len, dense_chars, sparse_chars):
    r, _ = repo
    await r.init_schema()
    await r.upsert_chunks([CorpusChunkRow(
        chunk_id="c1", dataset_id=1, doc_id=1, content="abc", content_hash="h",
        char_len=char_len, dense_input_chars=dense_chars, sparse_input_chars=sparse_chars,
        dense_indexed=True, sparse_indexed=True, bm25_indexed=True,
    )])
    with pytest.raises(ValueError, match="编码输入长度"):
        await r.summarize_encoding_inputs(dataset_id=1)


async def test_mark_pending_invalidates_only_requested_dataset_rows(repo):
    r, _ = repo
    await r.init_schema()
    original = CorpusChunkRow(
        chunk_id="target", dataset_id=1, doc_id=1, content="原始正文", content_hash="h",
        char_len=4, dense_input_chars=2, sparse_input_chars=3,
        dense_indexed=True, sparse_indexed=True, bm25_indexed=True,
    )
    foreign = replace(original, chunk_id="foreign", dataset_id=2)
    await r.upsert_chunks([original, foreign])
    assert await r.mark_chunks_pending(dataset_id=1, chunk_ids=["target", "target", "foreign", "missing"]) == 1
    by_id = {row.chunk_id: row for row in await r.fetch_ingest_rows(1, ["target", "foreign"])}
    assert by_id["target"] == replace(
        original, dense_indexed=False, sparse_indexed=False, bm25_indexed=False,
        dense_input_chars=None, sparse_input_chars=None,
    )
    assert by_id["foreign"] == foreign
