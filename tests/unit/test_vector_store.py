"""EvalVectorStore 编排:按最新 LinkRag 单 collection 接口验证构点、护栏与时序。"""

from __future__ import annotations

import pytest

pytest.importorskip("src", reason="需安装钉住的 LinkRag")

from linkrag_eval.compute.protocol import Bm25Tokens, SparseVec
from linkrag_eval.config import EvalSettings
from linkrag_eval.store.vector_store import EvalPoint, EvalVectorStore, build_eval_vector_store


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
        collection_name="eval_linkrag_chunks",
        user_id=990001,
        index_store=fake,
        sparse_vector_name="sparse_text",
    )


def test_collection_guard_rejects_non_eval() -> None:
    with pytest.raises(RuntimeError):
        EvalVectorStore(
            collection_name="linkrag_chunks",
            user_id=990001,
            index_store=_FakeIndexStore(),
        )


async def test_upsert_dense_and_sparse_uses_latest_single_collection_api() -> None:
    fake = _FakeIndexStore()
    store = _store(fake)
    points = [
        EvalPoint(chunk_id="a", doc_id=1, dense=[0.1, 0.2], sparse=SparseVec([1, 3], [0.5, 0.9])),
        EvalPoint(chunk_id="b", doc_id=1, dense=[0.3, 0.4], sparse=None),
    ]
    await store.upsert(dataset_id=990131, points=points)

    assert [c[0] for c in fake.calls] == [
        "ensure_collection", "upsert_points", "ensure_sparse_schema", "upsert_sparse"
    ]
    assert fake.calls[0] == ("ensure_collection", 2)
    dense_points = fake.calls[1][1]
    assert dense_points[0].payload == {
        "chunk_id": "a", "user_id": 990001, "set_id": 990131, "doc_id": 1
    }
    assert not hasattr(dense_points[0], "bucket_id")
    sparse_points = fake.calls[3][1]
    assert sparse_points[0].vector_name == "sparse_text"
    assert sparse_points[0].sparse_vector.indices == [1, 3]
    assert not hasattr(sparse_points[0], "bucket_id")


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


async def test_delete_uses_latest_signature_without_bucket_id() -> None:
    fake = _FakeIndexStore()
    await _store(fake).delete(chunk_ids=["a", "b"])
    assert fake.calls == [("delete", ["a", "b"])]


async def test_upsert_writes_sqlite_bm25_when_tokens_present() -> None:
    fake = _FakeIndexStore()
    bm25 = _FakeBm25Store()
    store = EvalVectorStore(
        collection_name="eval_linkrag_chunks",
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


def test_removed_bm25_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="qdrant_bm25"):
        EvalVectorStore(
            collection_name="eval_linkrag_chunks",
            user_id=990001,
            index_store=_FakeIndexStore(),
            bm25_mode="qdrant_bm25",
        )


def test_build_eval_vector_store_uses_collection_and_sparse_names() -> None:
    settings = EvalSettings(
        _env_file=None,
        qdrant_collection_name="eval_contract_chunks",
        sparse_vector_name="eval_sparse_text",
    )
    store = build_eval_vector_store(settings=settings)
    assert store.collection_name == "eval_contract_chunks"
    assert store._sparse_name == "eval_sparse_text"
