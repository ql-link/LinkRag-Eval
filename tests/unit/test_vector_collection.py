"""显式 Qdrant schema 与有界恢复核查：纯 fake client，不读取配置或连接服务。"""

from __future__ import annotations

import sys
from copy import deepcopy
from types import SimpleNamespace

import pytest
from qdrant_client import models

from linkrag_eval.compute.protocol import SparseVec
from linkrag_eval.store.vector_store import EvalPoint, EvalVectorStore, _build_index_store


def collection_info(*, size=2, sparse_name="eval_sparse", on_disk=True):
    return SimpleNamespace(
        config=SimpleNamespace(
            params=SimpleNamespace(
                vectors={
                    "dense": models.VectorParams(
                        size=size, distance=models.Distance.COSINE, on_disk=on_disk
                    )
                },
                sparse_vectors={
                    sparse_name: models.SparseVectorParams(
                        index=models.SparseIndexParams(on_disk=on_disk)
                    )
                },
                on_disk_payload=on_disk,
            ),
            hnsw_config=models.HnswConfigDiff(on_disk=on_disk),
        ),
        payload_schema={
            name: models.PayloadIndexInfo(
                data_type=models.PayloadSchemaType.INTEGER,
                params=models.IntegerIndexParams(type="integer", on_disk=on_disk),
                points=0,
            )
            for name in ("user_id", "set_id", "doc_id")
        },
    )


class FakeClient:
    def __init__(self, *, info=None, points=(), page_size=None):
        self.info = deepcopy(info)
        self.points = list(points)
        self.page_size = page_size
        self.calls = []

    async def collection_exists(self, **kwargs):
        self.calls.append(("collection_exists", kwargs))
        return self.info is not None

    async def create_collection(self, **kwargs):
        self.calls.append(("create_collection", kwargs))
        self.info = SimpleNamespace(
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors=kwargs["vectors_config"],
                    sparse_vectors=kwargs["sparse_vectors_config"],
                    on_disk_payload=kwargs["on_disk_payload"],
                ),
                hnsw_config=kwargs["hnsw_config"],
            ),
            payload_schema={},
        )
        return True

    async def create_payload_index(self, **kwargs):
        self.calls.append(("create_payload_index", kwargs))
        self.info.payload_schema[kwargs["field_name"]] = models.PayloadIndexInfo(
            data_type=models.PayloadSchemaType.INTEGER,
            params=kwargs["field_schema"],
            points=0,
        )

    async def get_collection(self, **kwargs):
        self.calls.append(("get_collection", kwargs))
        return self.info

    async def count(self, **kwargs):
        self.calls.append(("count", kwargs))
        assert kwargs["exact"] is True
        condition = kwargs.get("count_filter")
        if condition is None:
            count = len(self.points)
        elif condition.must_not:
            expected_scope = condition.must_not[0].must
            count = sum(
                any(p.payload.get(c.key) != c.match.value for c in expected_scope)
                for p in self.points
            )
        else:
            count = sum(
                all(p.payload.get(c.key) == c.match.value for c in condition.must)
                for p in self.points
            )
        return SimpleNamespace(count=count)

    async def retrieve(self, **kwargs):
        self.calls.append(("retrieve", kwargs))
        assert kwargs["with_vectors"] is False
        return [
            SimpleNamespace(id=point.id, payload=point.payload)
            for point in self.points
            if point.id in kwargs["ids"]
        ]

    async def close(self):
        self.calls.append(("close", {}))

    async def scroll(self, **kwargs):
        self.calls.append(("scroll", kwargs))
        assert kwargs["with_vectors"] is False
        matches = self.points
        for condition in kwargs["scroll_filter"].must:
            if isinstance(condition, models.HasIdCondition):
                matches = [point for point in matches if point.id in condition.has_id]
            elif isinstance(condition, models.HasVectorCondition):
                matches = [point for point in matches if condition.has_vector in point.vector_names]
            else:
                matches = [
                    point
                    for point in matches
                    if point.payload.get(condition.key) == condition.match.value
                ]
        start = kwargs["offset"] or 0
        end = start + min(kwargs["limit"], self.page_size or kwargs["limit"])
        # 向量存在性由服务端 filter 判定，返回记录不带向量或向量名。
        records = [SimpleNamespace(id=p.id, payload=p.payload) for p in matches[start:end]]
        return records, end if end < len(matches) else None


class FakeIndexStore:
    collection_name = "eval_exp_9"
    _dense_vector_name = "dense"

    def __init__(self, client):
        self._client = client
        self.writes = []

    async def _get_client(self):
        return self._client

    async def upsert_points(self, *, points):
        self.writes.append(("dense", list(points)))

    async def upsert_sparse_vectors(self, *, points):
        self.writes.append(("sparse", list(points)))


def store(client):
    return EvalVectorStore(
        prefix="eval_exp",
        bucket_count=16,
        user_id=990001,
        sparse_vector_name="eval_sparse",
        index_store=FakeIndexStore(client),
    )


async def test_aclose_closes_only_held_client_once_and_prevents_reopening():
    client = FakeClient()
    target = store(client)
    await target.aclose()
    await target.aclose()
    assert client.calls == [("close", {})]
    with pytest.raises(RuntimeError, match="已关闭"):
        await target.prepare_collection(vector_size=2, dataset_id=7, on_disk=True)
    with pytest.raises(RuntimeError, match="已关闭"):
        await target.upsert(dataset_id=7, points=[EvalPoint("c", 10, [0.1, 0.2])])
    assert client.calls == [("close", {})]


async def test_aclose_without_client_never_calls_lazy_getter():
    class LazyStore:
        _client = None

        async def _get_client(self):
            pytest.fail("关闭时不能创建 client")

    target = EvalVectorStore(
        prefix="eval_exp",
        bucket_count=16,
        user_id=990001,
        index_store=LazyStore(),
    )
    await target.aclose()
    await target.aclose()


@pytest.mark.parametrize("on_disk", [True, False])
async def test_prepare_creates_explicit_hybrid_schema_and_three_integer_indexes(on_disk):
    client = FakeClient()
    target = store(client)
    await target.prepare_collection(vector_size=2, dataset_id=7, on_disk=on_disk)

    create = next(args for method, args in client.calls if method == "create_collection")
    assert create["collection_name"] == "eval_exp_9"
    assert set(create["vectors_config"]) == {"dense"}
    dense = create["vectors_config"]["dense"]
    assert (dense.size, dense.distance, dense.on_disk) == (2, models.Distance.COSINE, on_disk)
    assert set(create["sparse_vectors_config"]) == {"eval_sparse"}
    assert create["sparse_vectors_config"]["eval_sparse"].index.on_disk is on_disk
    assert create["hnsw_config"].on_disk is on_disk
    assert create["on_disk_payload"] is on_disk
    indexes = [args for method, args in client.calls if method == "create_payload_index"]
    assert [item["field_name"] for item in indexes] == ["user_id", "set_id", "doc_id"]
    assert all(item["field_schema"].type == "integer" for item in indexes)
    assert all(item["field_schema"].on_disk is on_disk for item in indexes)
    assert all(item["wait"] is True for item in indexes)
    assert target._collection_ready is target._sparse_ready is True


async def test_existing_matching_collection_is_only_read_and_upsert_skips_rag_schema_defaults(
    monkeypatch,
):
    client = FakeClient(info=collection_info())
    target = store(client)
    await target.prepare_collection(vector_size=2, dataset_id=7, on_disk=True)
    assert [method for method, _ in client.calls] == [
        "collection_exists",
        "get_collection",
        "count",
    ]
    monkeypatch.setattr(target, "_dense_point", lambda point, dataset_id: point)
    monkeypatch.setattr(target, "_sparse_point", lambda point, dataset_id: point)
    await target.upsert(
        dataset_id=7,
        points=[EvalPoint("c", 3, [0.1, 0.2], sparse=SparseVec([1], [0.5]))],
    )
    assert [method for method, _ in target._store.writes] == ["dense", "sparse"]
    with pytest.raises(ValueError, match="维度"):
        await target.upsert(dataset_id=7, points=[EvalPoint("bad", 4, [0.1])])
    with pytest.raises(ValueError, match="dataset_id"):
        await target.upsert(dataset_id=8, points=[EvalPoint("bad", 4, [0.1, 0.2])])
    assert len(target._store.writes) == 2


@pytest.mark.parametrize(
    "mismatch",
    [
        "dense_name",
        "dense_size",
        "distance",
        "dense_disk",
        "sparse_name",
        "sparse_disk",
        "hnsw_disk",
        "payload_disk",
        "index_type",
        "index_disk",
        "index_lookup",
        "memory_override",
        "sparse_modifier",
    ],
)
async def test_existing_schema_mismatch_is_rejected_without_mutation(mismatch):
    info = collection_info()
    params = info.config.params
    dense = params.vectors["dense"]
    sparse = params.sparse_vectors["eval_sparse"]
    if mismatch == "dense_name":
        params.vectors = {"other": dense}
    elif mismatch == "dense_size":
        dense.size = 3
    elif mismatch == "distance":
        dense.distance = models.Distance.DOT
    elif mismatch == "dense_disk":
        dense.on_disk = False
    elif mismatch == "sparse_name":
        params.sparse_vectors = {"sparse_text": sparse}
    elif mismatch == "sparse_disk":
        sparse.index.on_disk = False
    elif mismatch == "hnsw_disk":
        info.config.hnsw_config.on_disk = False
    elif mismatch == "payload_disk":
        params.on_disk_payload = False
    elif mismatch == "index_type":
        info.payload_schema["doc_id"].data_type = models.PayloadSchemaType.KEYWORD
    elif mismatch == "index_disk":
        info.payload_schema["doc_id"].params.on_disk = False
    elif mismatch == "index_lookup":
        info.payload_schema["doc_id"].params.lookup = False
    elif mismatch == "memory_override":
        params.payload = SimpleNamespace(memory="cached")
    elif mismatch == "sparse_modifier":
        sparse.modifier = models.Modifier.IDF
    client = FakeClient(info=info)
    target = store(client)
    with pytest.raises(RuntimeError, match="schema 不一致"):
        await target.prepare_collection(vector_size=2, dataset_id=7, on_disk=True)
    assert [method for method, _ in client.calls] == ["collection_exists", "get_collection"]
    assert target._collection_ready is target._sparse_ready is False


@pytest.mark.parametrize("size", [0, -1, True, 2.5])
async def test_invalid_dimension_is_rejected_before_any_client_call(size):
    client = FakeClient()
    with pytest.raises(ValueError, match="vector_size"):
        await store(client).prepare_collection(vector_size=size, dataset_id=7, on_disk=True)
    assert client.calls == []


@pytest.mark.parametrize(
    "attribute,value",
    [
        ("collection_name", "production"),
        ("_dense_vector_name", "production_dense"),
    ],
)
async def test_primitive_target_drift_is_rejected_before_collection_access(attribute, value):
    client = FakeClient()
    target = store(client)
    setattr(target._store, attribute, value)
    with pytest.raises(RuntimeError, match="不一致"):
        await target.prepare_collection(vector_size=2, dataset_id=7, on_disk=True)
    assert client.calls == []


def point(cid, *, vector_names=("dense", "eval_sparse"), **payload):
    return SimpleNamespace(
        id=cid,
        vector_names=set(vector_names),
        payload={"chunk_id": cid, "user_id": 990001, "set_id": 7, "doc_id": 10, **payload},
    )


@pytest.mark.parametrize("payload", [{"user_id": 1}, {"set_id": 8}, {"set_id": None}])
async def test_prepare_rejects_other_or_missing_dataset_ownership_without_writes(payload):
    info = collection_info()
    del info.payload_schema["doc_id"]
    client = FakeClient(info=info, points=[point("existing", **payload)])
    target = store(client)
    with pytest.raises(RuntimeError, match="不属于指定"):
        await target.prepare_collection(vector_size=2, dataset_id=7, on_disk=True)
    assert [method for method, _ in client.calls] == [
        "collection_exists",
        "get_collection",
        "count",
    ]
    assert target._collection_ready is target._sparse_ready is False


async def test_prepare_resumes_interrupted_payload_indexes_without_recreating_collection():
    class InterruptedClient(FakeClient):
        fail_once = True

        async def create_payload_index(self, **kwargs):
            if kwargs["field_name"] == "set_id" and self.fail_once:
                self.fail_once = False
                raise TimeoutError("interrupted index creation")
            await super().create_payload_index(**kwargs)

    client = InterruptedClient()
    target = store(client)
    with pytest.raises(TimeoutError):
        await target.prepare_collection(vector_size=2, dataset_id=7, on_disk=True)
    assert set(client.info.payload_schema) == {"user_id"}
    assert target._collection_ready is target._sparse_ready is False
    first_calls = len(client.calls)

    await target.prepare_collection(vector_size=2, dataset_id=7, on_disk=True)
    assert set(client.info.payload_schema) == {"user_id", "set_id", "doc_id"}
    assert target._collection_ready is target._sparse_ready is True
    assert [method for method, _ in client.calls].count("create_collection") == 1
    assert [
        args["field_name"] for method, args in client.calls if method == "create_payload_index"
    ] == [
        "user_id",
        "set_id",
        "doc_id",
    ]
    assert [method for method, _ in client.calls[first_calls:]] == [
        "collection_exists",
        "get_collection",
        "count",
        "create_payload_index",
        "create_payload_index",
        "get_collection",
    ]


@pytest.mark.parametrize("mismatch", ["vector", "index_type", "index_disk"])
async def test_prepare_never_fills_missing_indexes_if_existing_schema_mismatches(mismatch):
    info = collection_info()
    del info.payload_schema["doc_id"]
    if mismatch == "vector":
        info.config.params.vectors["dense"].size = 3
    elif mismatch == "index_type":
        info.payload_schema["user_id"].data_type = models.PayloadSchemaType.KEYWORD
    else:
        info.payload_schema["user_id"].params.on_disk = False
    client = FakeClient(info=info)
    with pytest.raises(RuntimeError, match="schema 不一致"):
        await store(client).prepare_collection(vector_size=2, dataset_id=7, on_disk=True)
    assert [method for method, _ in client.calls] == ["collection_exists", "get_collection"]


@pytest.mark.parametrize("expected_count", [0, 2])
async def test_verify_collection_count_uses_only_exact_total_and_scope_counts(expected_count):
    client = FakeClient(
        info=collection_info(), points=[point(str(i)) for i in range(expected_count)]
    )
    target = store(client)
    await target.prepare_collection(vector_size=2, dataset_id=7, on_disk=True)
    client.calls.clear()
    await target.verify_collection_count(dataset_id=7, expected_count=expected_count)
    assert [method for method, _ in client.calls] == ["count", "count"]
    assert "count_filter" not in client.calls[0][1]
    scope = client.calls[1][1]["count_filter"].must
    assert [(item.key, item.match.value) for item in scope] == [("user_id", 990001), ("set_id", 7)]
    assert all(args["exact"] is True for _, args in client.calls)


@pytest.mark.parametrize(
    "points,total,scoped",
    [
        ([point("a")], 1, 1),
        ([point("a"), point("b"), point("c")], 3, 3),
        ([point("a"), point("foreign", set_id=8)], 2, 1),
        ([point("a"), point("b"), point("foreign", user_id=1)], 3, 2),
    ],
)
async def test_verify_count_rejects_missing_extra_or_new_foreign_points(points, total, scoped):
    client = FakeClient(info=collection_info())
    target = store(client)
    await target.prepare_collection(vector_size=2, dataset_id=7, on_disk=True)
    client.points = points
    client.calls.clear()
    with pytest.raises(RuntimeError, match=f"expected=2, total={total}, scoped={scoped}"):
        await target.verify_collection_count(dataset_id=7, expected_count=2)
    assert [method for method, _ in client.calls] == ["count", "count"]


async def test_verify_count_requires_preparation_for_same_dataset():
    client = FakeClient(info=collection_info())
    target = store(client)
    with pytest.raises(RuntimeError, match="prepare_collection"):
        await target.verify_collection_count(dataset_id=7, expected_count=0)
    assert client.calls == []
    await target.prepare_collection(vector_size=2, dataset_id=7, on_disk=True)
    client.calls.clear()
    with pytest.raises(RuntimeError, match="prepare_collection"):
        await target.verify_collection_count(dataset_id=8, expected_count=0)
    assert client.calls == []


@pytest.mark.parametrize("expected_count", [-1, True, 2.5])
async def test_verify_count_rejects_invalid_expected_count_before_access(expected_count):
    client = FakeClient()
    with pytest.raises(ValueError, match="expected_count"):
        await store(client).verify_collection_count(dataset_id=7, expected_count=expected_count)
    assert client.calls == []


def test_default_client_has_explicit_timeout_and_ignores_environment_proxy(
    monkeypatch,
):
    calls = {}
    sentinel = object()

    def client_factory(**kwargs):
        calls["client"] = kwargs
        return sentinel

    def index_factory(**kwargs):
        calls["index"] = kwargs
        return "index-store"

    monkeypatch.setattr("qdrant_client.AsyncQdrantClient", client_factory)
    monkeypatch.setitem(
        sys.modules, "src.core.storage.qdrant", SimpleNamespace(QdrantIndexStore=index_factory)
    )
    assert _build_index_store("eval_exp_9", "http://localhost:6333", None) == "index-store"
    assert calls["client"] == {
        "url": "http://localhost:6333", "api_key": None, "trust_env": False, "timeout": 60,
    }
    assert calls["index"] == {
        "client": sentinel, "collection_name": "eval_exp_9", "timeout": 60,
    }


async def test_fetch_indexed_rows_requires_both_vectors_and_exact_identity():
    points = [
        point("ok"),
        point("missing-dense", vector_names=("eval_sparse",)),
        point("missing-sparse", vector_names=("dense",)),
        point("wrong-sparse", vector_names=("dense", "sparse_text")),
        point("outside"),
    ]
    client = FakeClient(points=points)
    ids = [p.id for p in points if p.id != "outside"]
    assert await store(client).fetch_indexed_rows(
        dataset_id=7,
        chunk_ids=ids,
        expected_doc_ids=dict.fromkeys(ids, 10),
    ) == {"ok": 10}
    assert [method for method, _ in client.calls] == ["retrieve", "scroll"]
    request = client.calls[0][1]
    assert request["collection_name"] == "eval_exp_9"
    assert request["with_payload"] == ["chunk_id", "user_id", "set_id", "doc_id"]
    assert request["with_vectors"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {"user_id": 1},
        {"set_id": 8},
        {"chunk_id": "different"},
        {"doc_id": "10"},
        {"doc_id": True},
        {"doc_id": 11},
    ],
)
async def test_fetch_rejects_wrong_identity_even_if_one_vector_is_missing(payload):
    client = FakeClient(points=[point("c", vector_names=("dense",), **payload)])
    with pytest.raises(ValueError, match="身份与预期不一致"):
        await store(client).fetch_indexed_rows(
            dataset_id=7,
            chunk_ids=["c"],
            expected_doc_ids={"c": 10},
        )
    assert [method for method, _ in client.calls] == ["retrieve"]


@pytest.mark.parametrize("expected", [{}, {"other": 10}, {"c": "10"}, {"c": True}])
async def test_fetch_requires_exact_expected_doc_mapping_before_access(expected):
    client = FakeClient()
    with pytest.raises(ValueError, match="expected_doc_ids"):
        await store(client).fetch_indexed_rows(
            dataset_id=7,
            chunk_ids=["c"],
            expected_doc_ids=expected,
        )
    assert client.calls == []


async def test_fetch_empty_ids_never_uses_client():
    client = FakeClient()
    assert (
        await store(client).fetch_indexed_rows(
            dataset_id=7,
            chunk_ids=[],
            expected_doc_ids={},
        )
        == {}
    )
    assert client.calls == []


async def test_fetch_absent_points_skip_vector_filter_request():
    client = FakeClient()
    assert (
        await store(client).fetch_indexed_rows(
            dataset_id=7,
            chunk_ids=["missing"],
            expected_doc_ids={"missing": 10},
        )
        == {}
    )
    assert [method for method, _ in client.calls] == ["retrieve"]


async def test_fetch_is_bounded_by_deduplicated_ids_across_batches_and_pages():
    ids = [f"c{i}" for i in range(260)]
    client = FakeClient(points=[point(cid, doc_id=i) for i, cid in enumerate(ids)], page_size=100)
    result = await store(client).fetch_indexed_rows(
        dataset_id=7,
        chunk_ids=ids + ids[:5],
        expected_doc_ids={cid: i for i, cid in enumerate(ids)},
    )
    assert result == {cid: i for i, cid in enumerate(ids)}
    for method, request in client.calls:
        if method == "retrieve":
            assert 0 < len(request["ids"]) <= 256
            assert set(request["ids"]).issubset(ids)
        else:
            assert method == "scroll"
            id_filter = request["scroll_filter"].must[0]
            assert 0 < len(id_filter.has_id) <= 256
            assert set(id_filter.has_id).issubset(ids)
            assert request["limit"] <= 256
        assert request["with_vectors"] is False


async def test_unsupported_vector_filter_is_not_treated_as_indexed_or_absent():
    class UnsupportedClient(FakeClient):
        async def scroll(self, **kwargs):
            raise RuntimeError("unsupported has_vector")

    with pytest.raises(RuntimeError, match="unsupported has_vector"):
        await store(UnsupportedClient(points=[point("c")])).fetch_indexed_rows(
            dataset_id=7,
            chunk_ids=["c"],
            expected_doc_ids={"c": 10},
        )
