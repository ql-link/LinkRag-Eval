"""EvalVectorStore 编排:注入 fake index_store,验证构点/前缀护栏/dense+sparse 时序。

需 rag 可 import(构 IndexedPoint),但不连真 Qdrant(fake 记录调用)。
rag 不在环境时整文件跳过。
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

pytest.importorskip("src", reason="需安装 toLink-Rag(pip install -e <path>)")

from linkrag_eval.compute.protocol import (
    Bm25Tokens,
    SparseVec,
)
from linkrag_eval.config import EvalSettings
from linkrag_eval.store.vector_store import (
    EvalPoint,
    EvalVectorStore,
    build_eval_vector_store,
)


class _FakeIndexStore:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def ensure_collection(self, *, vector_size):
        self.calls.append(("ensure_collection", vector_size))

    async def upsert_points(self, *, points):
        self.calls.append(("upsert_points", list(points)))

    async def ensure_sparse_vector_schema(self, *, vector_name):
        self.calls.append(("ensure_sparse_schema", vector_name))

    async def upsert_sparse_vectors(self, *, points):
        self.calls.append(("upsert_sparse", list(points)))

    async def delete_points(self, *, chunk_ids):
        self.calls.append(("delete", list(chunk_ids)))


class _FakeBm25Store:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def ensure_collection(self):
        self.calls.append(("ensure_bm25_collection",))

    async def upsert_chunks(self, points):
        self.calls.append(("upsert_bm25", list(points)))


def _store(fake) -> EvalVectorStore:
    return EvalVectorStore(
        prefix="eval_kb_bucket",
        bucket_count=16,
        user_id=990001,
        index_store=fake,
        sparse_vector_name="sparse_text",
    )


def test_prefix_guard_rejects_non_eval() -> None:
    with pytest.raises(RuntimeError):
        EvalVectorStore(prefix="kb_bucket", bucket_count=16, user_id=990001, index_store=_FakeIndexStore())


async def test_upsert_dense_and_sparse_sequencing() -> None:
    fake = _FakeIndexStore()
    store = _store(fake)
    points = [
        EvalPoint(chunk_id="a", doc_id=1, dense=[0.1, 0.2], sparse=SparseVec([1, 3], [0.5, 0.9])),
        EvalPoint(chunk_id="b", doc_id=1, dense=[0.3, 0.4], sparse=None),
    ]
    await store.upsert(dataset_id=990131, points=points)

    names = [c[0] for c in fake.calls]
    assert names == ["ensure_collection", "upsert_points", "ensure_sparse_schema", "upsert_sparse"]

    # ensure_collection 用首点维度
    assert fake.calls[0] == ("ensure_collection", 2)
    assert store.bucket_id == 9
    assert store.collection_name == "eval_kb_bucket_9"
    # dense:两点都写,payload 含 set_id=dataset_id / doc_id / user_id
    dense_points = fake.calls[1][1]
    assert len(dense_points) == 2
    assert dense_points[0].payload == {
        "chunk_id": "a", "user_id": 990001, "set_id": 990131, "doc_id": 1
    }
    # sparse:仅带 sparse 的点(a),named vector
    sparse_points = fake.calls[3][1]
    assert len(sparse_points) == 1
    assert sparse_points[0].chunk_id == "a"
    assert sparse_points[0].vector_name == "sparse_text"
    assert sparse_points[0].sparse_vector.indices == [1, 3]


async def test_upsert_empty_noop() -> None:
    fake = _FakeIndexStore()
    await _store(fake).upsert(dataset_id=1, points=[])
    assert fake.calls == []


async def test_dense_only_skips_sparse() -> None:
    fake = _FakeIndexStore()
    await _store(fake).upsert(
        dataset_id=1, points=[EvalPoint(chunk_id="a", doc_id=1, dense=[0.1, 0.2])]
    )
    assert [c[0] for c in fake.calls] == ["ensure_collection", "upsert_points"]


async def test_upsert_writes_sqlite_bm25_when_tokens_present() -> None:
    fake = _FakeIndexStore()
    bm25 = _FakeBm25Store()
    store = EvalVectorStore(
        prefix="eval_kb_bucket",
        bucket_count=16,
        user_id=990001,
        index_store=fake,
        bm25_store=bm25,
        bm25_mode="sqlite_fts5",
        bm25_sqlite_path="runs/test-bm25.sqlite3",
    )
    await store.upsert(
        dataset_id=990131,
        points=[
            EvalPoint(
                chunk_id="a",
                doc_id=1,
                dense=[0.1, 0.2],
                bm25_tokens=Bm25Tokens(coarse="暖气 滤网", fine="暖气 滤网"),
            )
        ],
    )
    assert [c[0] for c in bm25.calls] == ["ensure_bm25_collection", "upsert_bm25"]
    point = bm25.calls[1][1][0]
    assert point.chunk_id == "a"
    assert point.tokens == Bm25Tokens(coarse="暖气 滤网", fine="暖气 滤网")


def test_build_eval_vector_store_uses_eval_sparse_vector_name(monkeypatch) -> None:
    fake = _FakeIndexStore()
    monkeypatch.setattr(
        "linkrag_eval.store.vector_store._build_index_store", lambda *_args: fake
    )
    settings = EvalSettings(
        _env_file=None,
        qdrant_prefix="eval_kb_bucket",
        sparse_vector_name="eval_sparse_text",
    )
    store = build_eval_vector_store(settings=settings)
    # 只替换底层存储构造，保留配置字段到 EvalVectorStore 的真实装配。
    configured = EvalVectorStore(
        prefix=settings.qdrant_prefix,
        bucket_count=settings.qdrant_bucket_count,
        user_id=settings.user_id,
        index_store=fake,
        sparse_vector_name=settings.sparse_vector_name,
    )
    assert store._store is fake
    assert configured._sparse_name == "eval_sparse_text"
    assert store._sparse_name == "eval_sparse_text"


async def test_bm25_tokens_require_enabled_store_before_any_write() -> None:
    fake = _FakeIndexStore()
    with pytest.raises(ValueError, match="需要启用 sqlite_fts5"):
        await _store(fake).upsert(
            dataset_id=990131,
            points=[EvalPoint(
                chunk_id="a", doc_id=1, dense=[0.1, 0.2],
                bm25_tokens=Bm25Tokens(coarse="滤网", fine="滤网"),
            )],
        )
    assert fake.calls == []


_PRIVATE_ERROR = "private-message https://user:secret@private.invalid/qdrant?api_key=secret"


class _FailingIndexStore(_FakeIndexStore):
    def __init__(self, errors, *, sparse=False, recognized=False) -> None:
        super().__init__()
        self.errors = list(errors)
        self.sparse = sparse
        self.recognized = recognized
        self.attempts: list[tuple] = []
        self.classified: list[Exception] = []

    def _is_transient_error(self, error):
        self.classified.append(error)
        return self.recognized

    async def _write(self, points, *, sparse):
        self.attempts.append((sparse, points))
        if sparse == self.sparse and self.errors:
            raise self.errors.pop(0)

    async def upsert_points(self, *, points):
        await self._write(points, sparse=False)

    async def upsert_sparse_vectors(self, *, points):
        await self._write(points, sparse=True)


def _sdk_error(source_type=httpx.ReadTimeout, *, cause=False):
    error = ResponseHandlingException(source_type(_PRIVATE_ERROR))
    if cause:
        outer = RuntimeError(_PRIVATE_ERROR)
        outer.__cause__ = error
        return outer
    return error


def _record_backoff(monkeypatch):
    delays = []

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr("linkrag_eval.store.vector_store.asyncio.sleep", sleep)
    return delays


@pytest.mark.parametrize("source_type", [
    httpx.ReadTimeout, httpx.ConnectError, httpx.RemoteProtocolError,
])
@pytest.mark.parametrize("cause", [False, True], ids=["sdk", "explicit-cause"])
@pytest.mark.parametrize("sparse", [False, True], ids=["dense", "sparse"])
async def test_sdk_transport_retry_reuses_points_and_redacts_logs(
    monkeypatch, caplog, source_type, cause, sparse,
) -> None:
    error = _sdk_error(source_type, cause=cause)
    fake = _FailingIndexStore([error, error], sparse=sparse)
    points = [object()]
    delays = _record_backoff(monkeypatch)

    await _store(fake)._upsert_vectors(points, sparse=sparse)

    assert delays == [1, 2]
    assert len(fake.attempts) == 3
    assert all(route == sparse and attempted is points for route, attempted in fake.attempts)
    assert len(caplog.records) == 2
    route = "sparse" if sparse else "dense"
    assert [record.getMessage() for record in caplog.records] == [
        f"Qdrant {route} write retry 2/3 ({source_type.__name__})",
        f"Qdrant {route} write retry 3/3 ({source_type.__name__})",
    ]
    assert all(record.exc_info is None for record in caplog.records)
    for private in ("private-message", "https://", "user:secret", "api_key"):
        assert private not in caplog.text


@pytest.mark.parametrize("sparse", [False, True], ids=["dense", "sparse"])
async def test_transport_retry_exhaustion_has_three_total_attempts(monkeypatch, sparse) -> None:
    errors = [_sdk_error(cause=True) for _ in range(3)]
    fake = _FailingIndexStore(errors, sparse=sparse)
    delays = _record_backoff(monkeypatch)

    with pytest.raises(RuntimeError) as caught:
        await _store(fake)._upsert_vectors([object()], sparse=sparse)

    assert caught.value is errors[-1]
    assert len(fake.attempts) == 3
    assert delays == [1, 2]


@pytest.mark.parametrize("cause", [False, True], ids=["sdk", "explicit-cause"])
async def test_primitive_recognized_error_does_not_get_outer_retries(monkeypatch, cause) -> None:
    error = _sdk_error(cause=cause)
    fake = _FailingIndexStore([error], recognized=True)
    delays = _record_backoff(monkeypatch)

    with pytest.raises(type(error)) as caught:
        await _store(fake)._upsert_vectors([object()])

    assert caught.value is error
    assert fake.classified == [error.__cause__ if cause else error]
    assert len(fake.attempts) == 1
    assert delays == []


@pytest.mark.parametrize("error", [
    UnexpectedResponse(400, "Bad Request", _PRIVATE_ERROR.encode(), httpx.Headers()),
    UnexpectedResponse(503, "Unavailable", _PRIVATE_ERROR.encode(), httpx.Headers()),
    ValueError(_PRIVATE_ERROR),
    httpx.LocalProtocolError(_PRIVATE_ERROR),
    ResponseHandlingException(ValueError(_PRIVATE_ERROR)),
    ResponseHandlingException(httpx.LocalProtocolError(_PRIVATE_ERROR)),
    httpx.ReadTimeout(_PRIVATE_ERROR),
], ids=["http-400", "http-503", "value", "local-protocol", "sdk-value", "sdk-local", "raw-timeout"])
async def test_non_sdk_transport_errors_are_not_retried(monkeypatch, caplog, error) -> None:
    fake = _FailingIndexStore([error])
    delays = _record_backoff(monkeypatch)

    with pytest.raises(type(error)) as caught:
        await _store(fake)._upsert_vectors([object()])

    assert caught.value is error
    assert len(fake.attempts) == 1
    assert delays == []
    assert caplog.records == []


@pytest.mark.parametrize("chain", ["__cause__", "__context__"])
@pytest.mark.parametrize("error_type", ["unexpected-response", "http-status"])
async def test_http_response_with_old_transport_chain_is_not_retried(
    monkeypatch, chain, error_type,
) -> None:
    if error_type == "unexpected-response":
        error = UnexpectedResponse(503, "Unavailable", _PRIVATE_ERROR.encode(), httpx.Headers())
    else:
        request = httpx.Request("POST", "https://private.invalid/qdrant")
        error = httpx.HTTPStatusError(
            _PRIVATE_ERROR, request=request, response=httpx.Response(503, request=request),
        )
    setattr(error, chain, _sdk_error())
    fake = _FailingIndexStore([error])
    delays = _record_backoff(monkeypatch)

    with pytest.raises(type(error)) as caught:
        await _store(fake)._upsert_vectors([object()])

    assert caught.value is error
    assert len(fake.attempts) == 1
    assert delays == []


async def test_value_error_with_old_transport_context_is_not_retried(monkeypatch) -> None:
    error = ValueError(_PRIVATE_ERROR)
    error.__context__ = _sdk_error()
    fake = _FailingIndexStore([error])
    delays = _record_backoff(monkeypatch)

    with pytest.raises(ValueError) as caught:
        await _store(fake)._upsert_vectors([object()])

    assert caught.value is error
    assert len(fake.attempts) == 1
    assert delays == []


async def test_sparse_retry_does_not_repeat_successful_dense_write(monkeypatch) -> None:
    fake = _FailingIndexStore([_sdk_error()], sparse=True)
    delays = _record_backoff(monkeypatch)

    await _store(fake).upsert(
        dataset_id=990131,
        points=[EvalPoint(
            chunk_id="a", doc_id=1, dense=[0.1, 0.2], sparse=SparseVec([1], [0.5]),
        )],
    )

    assert [sparse for sparse, _ in fake.attempts] == [False, True, True]
    assert fake.attempts[1][1] is fake.attempts[2][1]
    assert delays == [1]


async def test_write_cancellation_propagates_without_retry(monkeypatch, caplog) -> None:
    error = asyncio.CancelledError()
    fake = _FailingIndexStore([error])
    delays = _record_backoff(monkeypatch)

    with pytest.raises(asyncio.CancelledError) as caught:
        await _store(fake)._upsert_vectors([object()])

    assert caught.value is error
    assert len(fake.attempts) == 1
    assert delays == []
    assert caplog.records == []


async def test_task_cancellation_during_backoff_stops_further_writes(monkeypatch) -> None:
    fake = _FailingIndexStore([_sdk_error()])
    backoff_started = asyncio.Event()
    never_release = asyncio.Event()
    delays = []

    async def sleep(delay):
        delays.append(delay)
        backoff_started.set()
        await never_release.wait()

    monkeypatch.setattr("linkrag_eval.store.vector_store.asyncio.sleep", sleep)
    task = asyncio.create_task(_store(fake)._upsert_vectors([object()]))
    try:
        await asyncio.wait_for(backoff_started.wait(), timeout=1)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert len(fake.attempts) == 1
    assert delays == [1]
