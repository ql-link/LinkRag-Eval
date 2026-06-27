"""EvalVectorStore 编排:注入 fake index_store,验证构点/前缀护栏/dense+sparse 时序。

需 rag 可 import(构 IndexedPoint/BucketRouter),但不连真 Qdrant(fake 记录调用)。
rag 不在环境时整文件跳过。
"""

from __future__ import annotations

import pytest

pytest.importorskip("src", reason="需安装 toLink-Rag(pip install -e <path>)")

from linkrag_eval.compute.protocol import SparseVec  # noqa: E402
from linkrag_eval.store.vector_store import EvalPoint, EvalVectorStore  # noqa: E402


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
