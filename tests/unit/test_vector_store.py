"""EvalVectorStore 编排:注入 fake index_store,验证构点/前缀护栏/dense+sparse 时序。

需 rag 可 import(构 IndexedPoint/BucketRouter),但不连真 Qdrant(fake 记录调用)。
rag 不在环境时整文件跳过。
"""

from __future__ import annotations

import pytest

pytest.importorskip("src", reason="需安装 toLink-Rag(pip install -e <path>)")

from linkrag_eval.compute.protocol import SparseVec  # noqa: E402
from linkrag_eval.compute.protocol import Bm25Tokens  # noqa: E402
from linkrag_eval.config import EvalSettings  # noqa: E402
from linkrag_eval.store.vector_store import EvalPoint, EvalVectorStore  # noqa: E402
from linkrag_eval.store.vector_store import build_eval_vector_store  # noqa: E402


class _FakeIndexStore:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def ensure_collection(self, *, bucket_id, vector_size):
        self.calls.append(("ensure_collection", bucket_id, vector_size))

    async def upsert_points(self, *, bucket_id, points):
        self.calls.append(("upsert_points", bucket_id, list(points)))

    async def ensure_sparse_vector_schema(self, *, bucket_id, vector_name):
        self.calls.append(("ensure_sparse_schema", bucket_id, vector_name))

    async def upsert_sparse_vectors(self, *, bucket_id, points):
        self.calls.append(("upsert_sparse", bucket_id, list(points)))

    async def delete_points(self, *, bucket_id, chunk_ids):
        self.calls.append(("delete", bucket_id, list(chunk_ids)))


class _FakeBm25Encoder:
    def encode_document(self, coarse_tokens, fine_tokens):
        from types import SimpleNamespace

        return SimpleNamespace(indices=[7], values=[1.5])


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


def _store_with_bm25(fake, bm25_store) -> EvalVectorStore:
    return EvalVectorStore(
        prefix="eval_kb_bucket",
        bucket_count=16,
        user_id=990001,
        index_store=fake,
        sparse_vector_name="sparse_text",
        qdrant_bm25_store=bm25_store,
        bm25_encoder=_FakeBm25Encoder(),
        bm25_collection="eval_bm25",
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
    assert fake.calls[0] == ("ensure_collection", store.bucket_id, 2)
    # dense:两点都写,payload 含 set_id=dataset_id / doc_id / user_id
    dense_points = fake.calls[1][2]
    assert len(dense_points) == 2
    assert dense_points[0].payload == {
        "chunk_id": "a", "user_id": 990001, "set_id": 990131, "doc_id": 1
    }
    # sparse:仅带 sparse 的点(a),named vector
    sparse_points = fake.calls[3][2]
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


async def test_upsert_writes_qdrant_bm25_when_tokens_present() -> None:
    fake = _FakeIndexStore()
    bm25 = _FakeBm25Store()
    await _store_with_bm25(fake, bm25).upsert(
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
    assert point.dataset_id == 990131
    assert point.user_id == 990001
    assert point.sparse_vector.indices == [7]


def test_bm25_collection_guard_rejects_non_eval() -> None:
    with pytest.raises(RuntimeError):
        EvalVectorStore(
            prefix="eval_kb_bucket",
            bucket_count=16,
            user_id=990001,
            index_store=_FakeIndexStore(),
            bm25_collection="prod_bm25",
        )


def test_build_eval_vector_store_uses_eval_sparse_vector_name() -> None:
    fake = _FakeIndexStore()
    settings = EvalSettings(
        qdrant_prefix="eval_kb_bucket",
        sparse_vector_name="eval_sparse_text",
    )
    store = build_eval_vector_store(settings=settings)
    # build_eval_vector_store 不暴露 index_store 注入;这里直测配置字段到构造参数的默认口径。
    configured = EvalVectorStore(
        prefix=settings.qdrant_prefix,
        bucket_count=settings.qdrant_bucket_count,
        user_id=settings.user_id,
        index_store=fake,
        sparse_vector_name=settings.sparse_vector_name,
    )
    assert configured._sparse_name == "eval_sparse_text"
    assert store._sparse_name == "eval_sparse_text"
