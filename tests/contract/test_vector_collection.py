"""真实 rag/Qdrant 模型与 eval 显式 schema 的契约，所有 I/O 注入 fake。"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from qdrant_client import models

from linkrag_eval.compute.protocol import DenseVec, SparseVec
from linkrag_eval.store.vector_store import EvalPoint, EvalVectorStore

pytestmark = pytest.mark.contract


async def test_installed_primitive_preserves_named_vectors_after_eval_preparation(monkeypatch):
    from src.core.storage.qdrant import QdrantIndexStore, qdrant_store

    monkeypatch.setattr(
        qdrant_store,
        "settings",
        SimpleNamespace(
            QDRANT_HOST="localhost",
            QDRANT_PORT=6333,
            DENSE_VECTOR_QDRANT_VECTOR_NAME="dense",
            SPARSE_VECTOR_QDRANT_VECTOR_NAME="production_sparse_not_used",
        ),
    )

    class Client:
        def __init__(self):
            self.points = {}
            self.upsert_count = 0
            self.config = None
            self.payload_schema = {}

        async def collection_exists(self, *, collection_name):
            assert collection_name == "eval_contract_9"
            return self.config is not None

        async def create_collection(self, **kwargs):
            self.config = SimpleNamespace(
                params=SimpleNamespace(
                    vectors=kwargs["vectors_config"],
                    sparse_vectors=kwargs["sparse_vectors_config"],
                    on_disk_payload=kwargs["on_disk_payload"],
                ),
                hnsw_config=kwargs["hnsw_config"],
            )

        async def create_payload_index(self, *, collection_name, field_name, field_schema, wait):
            assert collection_name == "eval_contract_9" and wait is True
            self.payload_schema[field_name] = models.PayloadIndexInfo(
                data_type=models.PayloadSchemaType.INTEGER,
                params=field_schema,
                points=0,
            )

        async def get_collection(self, *, collection_name):
            return SimpleNamespace(config=self.config, payload_schema=self.payload_schema)

        async def count(self, *, collection_name, exact, count_filter=None):
            assert exact is True
            if count_filter is not None and count_filter.must_not:
                return models.CountResult(count=0)
            return models.CountResult(count=len(self.points))

        async def retrieve(self, *, collection_name, ids, with_payload, with_vectors):
            assert with_payload is with_vectors is False
            return [SimpleNamespace(id=cid) for cid in ids if cid in self.points]

        async def upsert(self, *, collection_name, points, wait):
            assert wait is True
            self.upsert_count += 1
            for point in points:
                self.points[point.id] = {"payload": point.payload, "vectors": dict(point.vector)}

        async def update_vectors(self, *, collection_name, points, wait):
            assert wait is True
            for point in points:
                self.points[point.id]["vectors"].update(point.vector)

    client = Client()
    target = EvalVectorStore(
        prefix="eval_contract",
        bucket_count=16,
        user_id=990001,
        index_store=QdrantIndexStore(client=client, collection_name="eval_contract_9"),
        sparse_vector_name="eval_sparse",
    )
    await target.prepare_collection(vector_size=2, dataset_id=7, on_disk=True)
    assert set(client.config.params.sparse_vectors) == {"eval_sparse"}
    await target.upsert(
        dataset_id=7,
        points=[EvalPoint("c", 10, [0.1, 0.2], sparse=SparseVec([1], [0.5]))],
    )
    await target.upsert(dataset_id=7, points=[EvalPoint("c", 10, [0.3, 0.4])])

    assert client.upsert_count == 1
    assert client.points["c"]["payload"] == {
        "chunk_id": "c",
        "user_id": 990001,
        "set_id": 7,
        "doc_id": 10,
    }
    assert client.points["c"]["vectors"] == {
        "dense": [0.3, 0.4],
        "eval_sparse": models.SparseVector(indices=[1], values=[0.5]),
    }
    await target.verify_collection_count(dataset_id=7, expected_count=1)


async def test_eval_client_timeout_reaches_real_sdk_request(monkeypatch):
    import qdrant_client
    from src.core.storage.qdrant import qdrant_store

    monkeypatch.setattr(
        qdrant_store,
        "settings",
        SimpleNamespace(
            QDRANT_HOST="localhost",
            QDRANT_PORT=6333,
            DENSE_VECTOR_QDRANT_VECTOR_NAME="dense",
        ),
    )
    observed_timeouts = []

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.host == "qdrant.invalid"
        assert request.url.path == "/collections/eval_contract_9/points"
        observed_timeouts.append(request.extensions["timeout"])
        return httpx.Response(200, json={"result": [], "status": "ok", "time": 0.0})

    real_client = qdrant_client.AsyncQdrantClient

    def offline_client(**kwargs):
        # 仅替换传输并关闭另起线程的版本探测；timeout 必须来自 eval 构造路径。
        return real_client(
            **kwargs,
            transport=httpx.MockTransport(handle),
            check_compatibility=False,
        )

    monkeypatch.setattr(qdrant_client, "AsyncQdrantClient", offline_client)
    target = EvalVectorStore(
        prefix="eval_contract",
        bucket_count=16,
        user_id=990001,
        qdrant_host="http://qdrant.invalid:6333",
    )
    chunk_id = "00000000-0000-0000-0000-000000000001"
    try:
        assert await target.fetch_indexed_rows(
            dataset_id=7,
            chunk_ids=[chunk_id],
            expected_doc_ids={chunk_id: 10},
        ) == {}
    finally:
        await target.aclose()

    assert observed_timeouts == [{"connect": 60, "read": 60, "write": 60, "pool": 60}]


@pytest.mark.parametrize("failed_route", ["dense", "eval_sparse"])
@pytest.mark.parametrize("failure_count", [1, 3], ids=["recovers", "exhausts"])
async def test_sdk_write_disconnect_reuses_encoded_vectors_and_stops_at_limit(
    monkeypatch, failed_route, failure_count,
):
    import qdrant_client
    from qdrant_client.http.exceptions import ResponseHandlingException
    from src.core.storage.qdrant import qdrant_store
    from src.core.storage.qdrant.exceptions import QdrantStoreError

    from linkrag_eval.store.ids import eval_chunk_id
    from linkrag_eval.store.indexer import EvalPassage, EvalVectorIndexer

    monkeypatch.setattr(
        qdrant_store,
        "settings",
        SimpleNamespace(
            QDRANT_HOST="localhost",
            QDRANT_PORT=6333,
            DENSE_VECTOR_QDRANT_VECTOR_NAME="dense",
            QDRANT_WRITE_MAX_ATTEMPTS=3,
        ),
    )
    delays = []

    async def no_delay(seconds):
        delays.append(seconds)
        assert len(delays) <= 2, "transport retries must be bounded"

    monkeypatch.setattr(asyncio, "sleep", no_delay)
    stored = {}
    created_points = []
    vector_requests = {"dense": [], "eval_sparse": []}

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "qdrant.invalid"
        body = json.loads(request.content)
        if request.method == "POST" and request.url.path.endswith("/points"):
            result = [{"id": cid} for cid in body["ids"] if cid in stored]
            return httpx.Response(200, json={"result": result, "status": "ok", "time": 0.0})
        assert request.method == "PUT"
        assert request.url.params["wait"] == "true"
        if request.url.path.endswith("/points"):
            for point in body["points"]:
                created_points.append(point)
                stored[point["id"]] = {"payload": point["payload"], "vector": point["vector"]}
        else:
            assert request.url.path.endswith("/points/vectors")
            [point] = body["points"]
            [route] = point["vector"]
            vector_requests[route].append(body)
            assert len(vector_requests[route]) <= 3, "vector writes must stop after three attempts"
            # 模拟服务已应用写入，但响应在传输中丢失；续试不能重建空点覆盖已存向量。
            stored[point["id"]]["vector"].update(point["vector"])
            if route == failed_route and len(vector_requests[route]) <= failure_count:
                raise httpx.RemoteProtocolError("", request=request)
        return httpx.Response(200, json={
            "result": {"operation_id": 1, "status": "completed"}, "status": "ok", "time": 0.0,
        })

    real_client = qdrant_client.AsyncQdrantClient

    def offline_client(**kwargs):
        return real_client(
            **kwargs, transport=httpx.MockTransport(handle), check_compatibility=False,
        )

    monkeypatch.setattr(qdrant_client, "AsyncQdrantClient", offline_client)
    computed = {"dense": 0, "sparse": 0}
    completed_rows = []
    bm25_writes = []
    pending_marks = []

    async def compute_dense(contents):
        computed["dense"] += 1
        return [DenseVec([0.1, 0.2], input_chars=len(text)) for text in contents]

    async def compute_sparse(contents):
        computed["sparse"] += 1
        return [SparseVec([1], [0.5], input_chars=len(text)) for text in contents]

    async def mark_pending(**kwargs):
        pending_marks.append(kwargs)

    async def save_rows(rows):
        completed_rows.extend(rows)

    async def ensure_bm25():
        pass

    async def write_bm25(points):
        bm25_writes.append(points)

    target = EvalVectorStore(
        prefix="eval_contract", bucket_count=16, user_id=990001,
        qdrant_host="http://qdrant.invalid:6333", sparse_vector_name="eval_sparse",
        bm25_mode="sqlite_fts5",
        bm25_store=SimpleNamespace(ensure_collection=ensure_bm25, upsert_chunks=write_bm25),
    )
    # 从已准备 collection 的写入边界开始；schema 准备由上方独立契约测试覆盖。
    target._collection_ready = target._sparse_ready = True
    target._prepared_dataset_id = 7
    target._prepared_vector_size = 2
    indexer = EvalVectorIndexer(
        computer=SimpleNamespace(compute_dense=compute_dense, compute_sparse=compute_sparse),
        vector_store=target,
        corpus_repo=SimpleNamespace(mark_chunks_pending=mark_pending, upsert_chunks=save_rows),
        bm25_mode="sqlite_fts5",
    )
    try:
        if failure_count == 3:
            with pytest.raises(QdrantStoreError) as error:
                await indexer.index_passages(7, [EvalPassage("pid", "contract passage", 10)])
            assert isinstance(error.value.__cause__, ResponseHandlingException)
            assert isinstance(error.value.__cause__.source, httpx.RemoteProtocolError)
        else:
            assert await indexer.index_passages(
                7, [EvalPassage("pid", "contract passage", 10)],
            ) == 1
    finally:
        await target.aclose()

    assert computed == {"dense": 1, "sparse": 1}
    assert len(pending_marks) == 1
    assert delays == ([1] if failure_count == 1 else [1, 2])
    assert len(vector_requests[failed_route]) == (2 if failure_count == 1 else 3)
    assert all(body == vector_requests[failed_route][0] for body in vector_requests[failed_route])
    other_route = "eval_sparse" if failed_route == "dense" else "dense"
    assert len(vector_requests[other_route]) == (0 if failed_route == "dense" and failure_count == 3 else 1)
    assert len(created_points) == 1
    chunk_id = eval_chunk_id(7, 10, 0)
    assert stored[chunk_id]["payload"] == {
        "chunk_id": chunk_id, "user_id": 990001, "set_id": 7, "doc_id": 10,
    }
    expected_vectors = {"dense": [0.1, 0.2]}
    if failed_route == "eval_sparse" or failure_count == 1:
        expected_vectors["eval_sparse"] = {"indices": [1], "values": [0.5]}
    assert stored[chunk_id]["vector"] == expected_vectors
    assert len(bm25_writes) == len(completed_rows) == (1 if failure_count == 1 else 0)
