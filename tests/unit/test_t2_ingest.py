"""流式入库的故障边界、实际索引续接与输入原样性；不访问远端服务。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from linkrag_eval.compute.protocol import DenseVec, SparseVec
from linkrag_eval.runners.t2_ingest import (
    T2IngestError,
    _safe_cause_chain,
    ingest_t2_collection,
    ingest_t2_passages,
)
from linkrag_eval.store.ids import eval_chunk_id
from linkrag_eval.store.indexer import EvalVectorIndexer

DATASET = 994000
DOC_BASE = 9940000000000


class MemoryRepo:
    def __init__(self):
        self.rows = {}
        self.requests = []

    async def fetch_ingest_rows(self, dataset_id, chunk_ids):
        self.requests.append(list(chunk_ids))
        return [self.rows[cid] for cid in chunk_ids if cid in self.rows]

    async def upsert_chunks(self, rows):
        self.rows.update((r.chunk_id, r) for r in rows)
        return len(rows)

    async def mark_chunks_pending(self, *, dataset_id, chunk_ids):
        count = 0
        for cid in set(chunk_ids):
            row = self.rows.get(cid)
            if row is not None and row.dataset_id == dataset_id:
                self.rows[cid] = replace(
                    row, dense_indexed=False, sparse_indexed=False, bm25_indexed=False,
                    dense_input_chars=None, sparse_input_chars=None,
                )
                count += 1
        return count

    async def verify_dataset_count(self, *, dataset_id, expected_count):
        if len(self.rows) != expected_count or any(
            row.dataset_id != dataset_id for row in self.rows.values()
        ):
            raise ValueError("语料表实际数量或范围不匹配")


class Presence:
    def __init__(self):
        self.rows = {}
        self.count_checks = []

    async def fetch_indexed_rows(
        self, *, dataset_id, chunk_ids, user_id=None, expected_doc_ids=None
    ):
        return {cid: self.rows[cid] for cid in chunk_ids if cid in self.rows}

    async def verify_collection_count(self, *, dataset_id, expected_count):
        self.count_checks.append((dataset_id, expected_count))
        if len(self.rows) != expected_count:
            raise ValueError("实际点数量不匹配")

    async def verify_dataset_count(self, *, dataset_id, expected_count, user_id):
        self.count_checks.append((dataset_id, user_id, expected_count))
        if len(self.rows) != expected_count:
            raise ValueError("实际BM25行数量不匹配")


class Computer:
    def __init__(self):
        self.batches = []
        self.on_encode = None

    async def compute_dense(self, contents):
        if self.on_encode:
            self.on_encode()
        self.batches.append(list(contents))
        return [DenseVec([float(len(text)), 1.0], input_chars=len(text)) for text in contents]

    async def compute_sparse(self, contents):
        return [SparseVec([1], [1.0], input_chars=len(text)) for text in contents]


class Writer:
    def __init__(self, vectors, bm25):
        self.vectors, self.bm25 = vectors, bm25
        self.calls = []
        self.fail_call = None
        self.omit_bm25 = False

    async def upsert(self, *, dataset_id, points):
        self.calls.append([p.chunk_id for p in points])
        self.vectors.rows.update((p.chunk_id, p.doc_id) for p in points)
        if len(self.calls) == self.fail_call:
            raise RuntimeError("private endpoint details must not reach the public failure record")
        if not self.omit_bm25:
            self.bm25.rows.update((p.chunk_id, p.doc_id) for p in points)


@pytest.fixture
def setup():
    repo, vectors, bm25, computer = MemoryRepo(), Presence(), Presence(), Computer()
    writer = Writer(vectors, bm25)
    indexer = EvalVectorIndexer(
        computer=computer, vector_store=writer, corpus_repo=repo, bm25_mode="sqlite_fts5"
    )
    kwargs = {
        "dataset_id": DATASET, "doc_id_base": DOC_BASE, "batch_size": 2,
        "corpus_repo": repo, "indexer": indexer, "vector_store": vectors, "bm25_store": bm25,
        "user_id": 990001, "expected_passage_count": 3,
    }
    return kwargs, repo, vectors, bm25, computer, writer


def source():
    return iter([("0007", "  原文\t含制表符  "), ("8", ""), ("9", "末段")])


async def test_streams_bounded_batches_and_keeps_original_text(setup):
    kwargs, repo, _, _, computer, _ = setup
    consumed = 0
    progress = []

    def passages():
        nonlocal consumed
        for item in source():
            consumed += 1
            yield item

    def check_bounded():
        completed = progress[-1]["processed_passages"] if progress else 0
        assert consumed <= completed + kwargs["batch_size"]

    computer.on_encode = check_bounded
    result = await ingest_t2_passages(passages=passages(), on_progress=progress.append, **kwargs)
    assert result == {
        "processed_passages": 3, "indexed_passages": 3, "skipped_passages": 0,
        "completed_batches": 2,
    }
    assert computer.batches == [["  原文\t含制表符  ", ""], ["末段"]]
    assert [r.source_passage_id for r in repo.rows.values()] == ["0007", "8", "9"]
    assert [r.doc_id for r in repo.rows.values()] == [DOC_BASE, DOC_BASE + 1, DOC_BASE + 2]
    assert all(r.ordinal == 0 for r in repo.rows.values())
    assert max(map(len, repo.requests)) <= 2
    assert progress[0]["processed_passages"] == 2


async def test_resume_skips_only_actual_complete_rows(setup):
    kwargs, _, _, _, computer, writer = setup
    await ingest_t2_passages(passages=source(), **kwargs)
    first_calls = len(writer.calls)
    result = await ingest_t2_passages(passages=source(), **kwargs)
    assert result["skipped_passages"] == 3
    assert result["indexed_passages"] == 0
    assert len(writer.calls) == first_calls
    assert len(computer.batches) == 2


@pytest.mark.parametrize("changes", [
    {"dense_input_chars": None},
    {"sparse_input_chars": None},
    {"dense_input_chars": None, "sparse_input_chars": None},
    {"dense_input_chars": 1, "sparse_input_chars": None},
    {"dense_input_chars": True},
    {"sparse_input_chars": True},
    {"dense_input_chars": 0},
    {"sparse_input_chars": 0},
    {"dense_input_chars": -1},
    {"sparse_input_chars": 10_000},
    {"dense_input_chars": 1.0},
    {"sparse_input_chars": "1"},
    {"char_len": None},
    {"char_len": -1},
    {"char_len": 10_000},
])
async def test_invalid_encoding_receipt_reencodes_only_the_affected_passage(setup, changes):
    kwargs, repo, _, _, computer, writer = setup
    await ingest_t2_passages(passages=source(), **kwargs)
    cid = eval_chunk_id(DATASET, DOC_BASE, 0)
    original = repo.rows[cid]
    repo.rows[cid] = replace(original, **changes)
    previous_calls = len(writer.calls)
    computer.batches.clear()

    result = await ingest_t2_passages(passages=source(), **kwargs)

    assert result["indexed_passages"] == 1
    assert result["skipped_passages"] == 2
    assert computer.batches == [[original.content]]
    assert len(writer.calls) == previous_calls + 1
    assert writer.calls[-1] == [cid]
    assert repo.rows[cid] == original


@pytest.mark.parametrize("truncated_routes", [
    ("dense",), ("sparse",), ("dense", "sparse"),
])
async def test_valid_truncated_receipts_are_kept_and_skipped(setup, truncated_routes):
    kwargs, repo, _, _, computer, writer = setup
    await ingest_t2_passages(passages=source(), **kwargs)
    cid = eval_chunk_id(DATASET, DOC_BASE, 0)
    original = repo.rows[cid]
    truncated = replace(original, **{f"{route}_input_chars": 1 for route in truncated_routes})
    repo.rows[cid] = truncated
    previous_calls = len(writer.calls)
    computer.batches.clear()

    result = await ingest_t2_passages(passages=source(), **kwargs)

    assert result["indexed_passages"] == 0
    assert result["skipped_passages"] == 3
    assert computer.batches == []
    assert len(writer.calls) == previous_calls
    assert repo.rows[cid] == truncated
    assert truncated.content == original.content
    assert truncated.char_len == len(original.content)


async def test_empty_original_can_complete_only_with_explicit_zero_receipts(setup):
    # 仅验证 runner 的空原文边界；fake 成功不代表真实服务支持空输入。
    kwargs, repo, _, _, computer, _ = setup
    await ingest_t2_passages(passages=source(), **kwargs)
    cid = eval_chunk_id(DATASET, DOC_BASE + 1, 0)
    row = repo.rows[cid]
    assert row.content == ""
    assert row.char_len == row.dense_input_chars == row.sparse_input_chars == 0
    assert type(row.dense_input_chars) is int and type(row.sparse_input_chars) is int
    computer.batches.clear()

    result = await ingest_t2_passages(passages=source(), **kwargs)

    assert result["skipped_passages"] == 3
    assert result["indexed_passages"] == 0
    assert computer.batches == []


@pytest.mark.parametrize("field", ["dense_input_chars", "sparse_input_chars"])
@pytest.mark.parametrize("invalid", [None, False, 1])
async def test_empty_original_with_unknown_boolean_or_positive_receipt_is_reencoded(
    setup, field, invalid,
):
    kwargs, repo, _, _, computer, _ = setup
    await ingest_t2_passages(passages=source(), **kwargs)
    cid = eval_chunk_id(DATASET, DOC_BASE + 1, 0)
    original = repo.rows[cid]
    repo.rows[cid] = replace(original, **{field: invalid})
    computer.batches.clear()

    result = await ingest_t2_passages(passages=source(), **kwargs)

    assert result["indexed_passages"] == 1
    assert result["skipped_passages"] == 2
    assert computer.batches == [[""]]
    assert repo.rows[cid] == original


@pytest.mark.parametrize("route", ["dense", "sparse"])
async def test_reencoding_without_a_known_receipt_cannot_complete(setup, monkeypatch, route):
    kwargs, repo, _, _, computer, writer = setup
    await ingest_t2_passages(passages=source(), **kwargs)
    cid = eval_chunk_id(DATASET, DOC_BASE, 0)
    original = repo.rows[cid]
    repo.rows[cid] = replace(original, **{f"{route}_input_chars": None})
    encode = getattr(computer, f"compute_{route}")

    async def encode_without_receipt(contents):
        return [replace(vector, input_chars=None) for vector in await encode(contents)]

    monkeypatch.setattr(computer, f"compute_{route}", encode_without_receipt)
    progress = []
    before = len(writer.calls)
    with pytest.raises(T2IngestError) as error:
        await ingest_t2_passages(passages=source(), on_progress=progress.append, **kwargs)

    assert error.value.phase == "completion_check"
    assert error.value.progress["processed_passages"] == 0
    assert error.value.progress["completed_batches"] == 0
    assert progress == []
    assert len(writer.calls) == before + 1
    assert getattr(repo.rows[cid], f"{route}_input_chars") is None
    assert repo.rows[cid].content == original.content

    monkeypatch.setattr(computer, f"compute_{route}", encode)
    resumed = await ingest_t2_passages(passages=source(), **kwargs)
    assert resumed["indexed_passages"] == 1
    assert resumed["skipped_passages"] == 2
    assert repo.rows[cid] == original


async def test_failed_reencoding_clears_old_completion_flags_and_receipts(setup):
    kwargs, repo, _, bm25, _, writer = setup
    await ingest_t2_passages(passages=source(), **kwargs)
    cid = eval_chunk_id(DATASET, DOC_BASE, 0)
    original = repo.rows[cid]
    del bm25.rows[cid]
    writer.fail_call = len(writer.calls) + 1

    with pytest.raises(T2IngestError) as error:
        await ingest_t2_passages(passages=source(), **kwargs)

    assert error.value.phase == "index"
    assert error.value.progress["processed_passages"] == 0
    assert repo.rows[cid] == replace(
        original, dense_indexed=False, sparse_indexed=False, bm25_indexed=False,
        dense_input_chars=None, sparse_input_chars=None,
    )
    writer.fail_call = None
    resumed = await ingest_t2_passages(passages=source(), **kwargs)
    assert resumed["indexed_passages"] == 1
    assert resumed["skipped_passages"] == 2
    assert repo.rows[cid] == original


@pytest.mark.parametrize("missing", ["vector", "bm25", "flag"])
async def test_stale_sqlite_completion_is_repaired_from_actual_presence(setup, missing):
    kwargs, repo, vectors, bm25, _, writer = setup
    await ingest_t2_passages(passages=source(), **kwargs)
    cid = eval_chunk_id(DATASET, DOC_BASE + 1, 0)
    if missing == "vector":
        del vectors.rows[cid]
    elif missing == "bm25":
        del bm25.rows[cid]
    else:
        repo.rows[cid] = replace(repo.rows[cid], bm25_indexed=False)
    result = await ingest_t2_passages(passages=source(), **kwargs)
    assert result["indexed_passages"] == 1
    assert result["skipped_passages"] == 2
    assert writer.calls[-1] == [cid]
    assert cid in vectors.rows and cid in bm25.rows
    assert repo.rows[cid].bm25_indexed


@pytest.mark.parametrize("field,value", [
    ("content", "改过的正文"), ("source_passage_id", "different"),
    ("doc_id", 12), ("dataset_id", 1), ("ordinal", 1),
])
async def test_conflicting_existing_identity_stops_without_overwriting(setup, field, value):
    kwargs, repo, _, _, _, writer = setup
    await ingest_t2_passages(passages=source(), **kwargs)
    cid = eval_chunk_id(DATASET, DOC_BASE, 0)
    bad = replace(repo.rows[cid], **{field: value})
    repo.rows[cid] = bad
    before = len(writer.calls)
    with pytest.raises(T2IngestError) as error:
        await ingest_t2_passages(passages=source(), **kwargs)
    assert error.value.phase == "resume_check"
    assert error.value.progress["processed_passages"] == 0
    assert len(writer.calls) == before
    assert repo.rows[cid] is bad


async def test_partial_remote_failure_keeps_prefix_and_explicit_resume_repairs(setup):
    kwargs, repo, _, _, _, writer = setup
    writer.fail_call = 2
    progress = []
    with pytest.raises(T2IngestError) as error:
        await ingest_t2_passages(passages=source(), on_progress=progress.append, **kwargs)
    assert len(writer.calls) == 2  # 失败批未自动重试
    assert len(repo.rows) == 2
    assert error.value.phase == "index"
    assert error.value.progress["processed_passages"] == 2
    assert error.value.failed_batch == {"first_position": 2, "passage_count": 1}
    assert "private endpoint" not in str(error.value)
    assert error.value.cause_chain == [{"error_type": "RuntimeError"}]
    assert len(progress) == 1
    writer.fail_call = None
    result = await ingest_t2_passages(passages=source(), **kwargs)
    assert result["skipped_passages"] == 2
    assert result["indexed_passages"] == 1
    assert len(repo.rows) == 3


def test_safe_cause_chain_unwraps_sdk_source_without_messages():
    import httpx
    from qdrant_client.http.exceptions import ResponseHandlingException

    inner = httpx.ReadTimeout("private endpoint and original input")
    sdk_error = ResponseHandlingException(inner)
    outer = RuntimeError("private endpoint and original input")
    outer.__cause__ = sdk_error
    assert _safe_cause_chain(outer) == [
        {"error_type": "RuntimeError"}, {"error_type": "ResponseHandlingException"},
        {"error_type": "ReadTimeout"},
    ]


def test_safe_cause_chain_records_only_numeric_status_and_breaks_cycles():
    class StatusError(RuntimeError):
        status_code = 503

    error = StatusError("private response")
    error.__cause__ = error
    assert _safe_cause_chain(error) == [{"error_type": "StatusError", "http_status": 503}]


@pytest.mark.parametrize("reason,status", [
    ("http_error", 403), ("account_overdue", 403), ("invalid_response_schema", 200),
])
def test_safe_cause_chain_keeps_sparse_status_and_fixed_reason_only(reason, status):
    import json

    from linkrag_eval.llm.sparse_client import SparseEncodeError

    error = SparseEncodeError("private body credential URL", status_code=status, reason=reason)
    chain = _safe_cause_chain(error)
    assert chain == [{"error_type": "SparseEncodeError", "http_status": status, "reason": reason}]
    assert "private" not in json.dumps(chain)
    error.reason = "private body credential URL"
    assert _safe_cause_chain(error) == [{"error_type": "SparseEncodeError", "http_status": status}]


def test_safe_cause_chain_ignores_arbitrary_exception_reason():
    error = RuntimeError("private body")
    error.reason = "http_error"
    assert _safe_cause_chain(error) == [{"error_type": "RuntimeError"}]


async def test_success_return_with_missing_actual_index_does_not_advance(setup):
    kwargs, _, _, _, _, writer = setup
    writer.omit_bm25 = True
    with pytest.raises(T2IngestError) as error:
        await ingest_t2_passages(passages=source(), **kwargs)
    assert error.value.phase == "completion_check"
    assert error.value.progress["processed_passages"] == 0


@pytest.mark.parametrize("extra_store", ["vector", "corpus", "bm25"])
async def test_eof_rejects_extra_rows_even_when_every_expected_id_is_complete(setup, extra_store):
    kwargs, repo, vectors, bm25, _, _ = setup
    await ingest_t2_passages(passages=source(), **kwargs)
    if extra_store == "corpus":
        old_row = next(iter(repo.rows.values()))
        repo.rows["extra"] = replace(old_row, chunk_id="extra", doc_id=555)
    else:
        (vectors if extra_store == "vector" else bm25).rows["extra"] = 555
    with pytest.raises(T2IngestError) as error:
        await ingest_t2_passages(passages=source(), **kwargs)
    assert error.value.phase == "final_scope_check"
    assert error.value.progress["processed_passages"] == 3
    assert error.value.progress["skipped_passages"] == 3


async def test_count_check_runs_only_after_source_eof(setup):
    kwargs, _, vectors, bm25, _, _ = setup
    eof_seen = False

    def passages():
        nonlocal eof_seen
        yield from source()
        assert not vectors.count_checks and not bm25.count_checks
        eof_seen = True

    result = await ingest_t2_passages(passages=passages(), **kwargs)
    assert eof_seen and result["processed_passages"] == 3
    assert vectors.count_checks == [(DATASET, 3)]
    assert bm25.count_checks == [(DATASET, 990001, 3)]


@pytest.mark.parametrize("missing_store", ["vector", "corpus", "bm25"])
async def test_final_count_catches_disappearance_after_last_batch(setup, missing_store):
    kwargs, repo, vectors, bm25, _, _ = setup
    cid = eval_chunk_id(DATASET, DOC_BASE, 0)

    def disappear_after_last_batch(progress):
        if progress["processed_passages"] == 3:
            storage = {"vector": vectors, "corpus": repo, "bm25": bm25}[missing_store]
            del storage.rows[cid]

    with pytest.raises(T2IngestError) as error:
        await ingest_t2_passages(
            passages=source(), on_progress=disappear_after_last_batch, **kwargs
        )
    assert error.value.phase == "final_scope_check"


async def test_actual_doc_conflict_is_not_treated_as_a_missing_point(setup):
    kwargs, _, vectors, _, _, writer = setup
    await ingest_t2_passages(passages=source(), **kwargs)
    vectors.rows[eval_chunk_id(DATASET, DOC_BASE, 0)] = 123
    before = len(writer.calls)
    with pytest.raises(T2IngestError) as error:
        await ingest_t2_passages(passages=source(), **kwargs)
    assert error.value.phase == "resume_check"
    assert len(writer.calls) == before


@pytest.mark.parametrize("missing_local", ["flag", "row"])
@pytest.mark.parametrize("conflict_index", ["vector", "bm25"])
async def test_actual_doc_conflict_is_checked_even_without_local_completion(
    setup, missing_local, conflict_index
):
    kwargs, repo, vectors, bm25, _, writer = setup
    await ingest_t2_passages(passages=source(), **kwargs)
    cid = eval_chunk_id(DATASET, DOC_BASE, 0)
    if missing_local == "flag":
        repo.rows[cid] = replace(repo.rows[cid], bm25_indexed=False)
    else:
        del repo.rows[cid]
    (vectors if conflict_index == "vector" else bm25).rows[cid] = 123
    before = len(writer.calls)
    with pytest.raises(T2IngestError) as error:
        await ingest_t2_passages(passages=source(), **kwargs)
    assert error.value.phase == "resume_check"
    assert len(writer.calls) == before


@pytest.mark.parametrize("expected", [2, 4])
async def test_incorrect_full_source_count_is_a_failure(setup, expected):
    kwargs, _, _, _, _, _ = setup
    with pytest.raises(T2IngestError) as error:
        await ingest_t2_passages(passages=source(), **{**kwargs, "expected_passage_count": expected})
    assert error.value.phase == "read"


async def test_file_generator_is_closed_after_failure(setup, monkeypatch, tmp_path):
    kwargs, _, _, _, _, writer = setup
    writer.fail_call = 1
    closed = []

    def reader(path):
        try:
            yield from source()
        finally:
            closed.append(True)

    monkeypatch.setattr("linkrag_eval.golden.opensource.datasets.iter_t2_collection", reader)
    with pytest.raises(T2IngestError):
        await ingest_t2_collection(collection_path=tmp_path / "source.tsv", **kwargs)
    assert closed == [True]


async def test_real_local_stores_recover_missing_fts_row_without_reencoding_complete_rows(tmp_path):
    import sqlite3

    from linkrag_eval.store.corpus_repo import EvalCorpusRepo
    from linkrag_eval.store.engine import get_eval_engine
    from linkrag_eval.store.sqlite_bm25 import SQLiteBm25Point, SQLiteBm25Store

    url = f"sqlite+aiosqlite:///{tmp_path}/corpus.sqlite3"
    repo = EvalCorpusRepo(url=url)
    await repo.init_schema()
    bm25 = SQLiteBm25Store(tmp_path / "bm25.sqlite3")
    vectors, computer = Presence(), Computer()

    class LocalWriter:
        async def upsert(self, *, dataset_id, points):
            vectors.rows.update((p.chunk_id, p.doc_id) for p in points)
            await bm25.ensure_collection()
            await bm25.upsert_chunks([
                SQLiteBm25Point(
                    chunk_id=p.chunk_id, doc_id=p.doc_id, user_id=990001,
                    dataset_id=dataset_id, chunk_type="text", tokens=p.bm25_tokens,
                )
                for p in points
            ])

    indexer = EvalVectorIndexer(
        computer=computer, vector_store=LocalWriter(), corpus_repo=repo, bm25_mode="sqlite_fts5"
    )
    source_path = tmp_path / "collection.tsv"
    source_path.write_text("pid\ttext\n0007\t  正文\t保持  \n8\t\n9\t末段\n", encoding="utf-8")
    kwargs = {
        "collection_path": source_path, "dataset_id": DATASET, "doc_id_base": DOC_BASE,
        "batch_size": 2, "corpus_repo": repo, "indexer": indexer, "vector_store": vectors,
        "bm25_store": bm25, "user_id": 990001, "expected_passage_count": 3,
    }
    try:
        await ingest_t2_collection(**kwargs)
        missing = eval_chunk_id(DATASET, DOC_BASE + 1, 0)
        with sqlite3.connect(bm25.path) as con:
            con.execute("DELETE FROM bm25_fts WHERE chunk_id = ?", (missing,))
        computer.batches.clear()
        result = await ingest_t2_collection(**kwargs)
        assert result["indexed_passages"] == 1
        assert result["skipped_passages"] == 2
        assert computer.batches == [[""]]
        assert await bm25.fetch_indexed_rows(
            dataset_id=DATASET, chunk_ids=[missing], user_id=990001
        ) == {missing: DOC_BASE + 1}
        row = (await repo.fetch_ingest_rows(DATASET, [missing]))[0]
        assert row.content == "" and row.source_passage_id == "8"
        assert row.dense_indexed and row.sparse_indexed and row.bm25_indexed
    finally:
        await get_eval_engine(url).dispose()
