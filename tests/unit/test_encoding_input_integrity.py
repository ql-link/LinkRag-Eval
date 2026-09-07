"""编码前缀恢复的本地组合验收：真实入库/SQL/FTS，HTTP 与 Qdrant 使用替身。

HTTP mock 的字符门槛只用于触发已证实的错误响应，不表示实际服务的 token 上限。
本测试证明客户端发出的内容和本地数据不变量，不推断真实服务内部分词或召回质量。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from linkrag_eval.compute.rag_adapter import RagProductComputer
from linkrag_eval.golden.opensource.coverage import (
    join_candidate_qrels,
    summarize_label_coverage,
)
from linkrag_eval.golden.opensource.datasets import iter_t2_collection, read_t2_qrels
from linkrag_eval.llm.dense_client import OpenAIDenseEmbedder
from linkrag_eval.llm.sparse_client import ArkSparseEncoder
from linkrag_eval.runners.t2_ingest import ingest_t2_collection
from linkrag_eval.store.corpus_repo import EvalCorpusRepo
from linkrag_eval.store.ids import content_hash, eval_chunk_id
from linkrag_eval.store.indexer import EvalVectorIndexer
from linkrag_eval.store.models import EvalBase
from linkrag_eval.store.sqlite_bm25 import SQLiteBm25Point, SQLiteBm25Store
from linkrag_eval.store.vector_store import EvalPoint

DATASET_ID = 995901
DOC_ID_BASE = 9959010000
USER_ID = 990001
PREFIX_POLICY = "prefix_on_length_error"
# 不同线路用不同门槛，防止 Dense 缩短后直接把同一副本送入 Sparse。
DENSE_MOCK_LIMIT = 128
SPARSE_MOCK_LIMIT = 320
DENSE_LENGTH_ERROR = {
    "error": {
        "code": "InvalidParameter",
        "type": "InvalidParameter",
        "param": None,
        "message": (
            "<400> InternalError.Algo.InvalidParameter: "
            "Range of input length should be [1, 33000]"
        ),
    }
}
SPARSE_LENGTH_ERROR = {
    "error": {
        "code": "InvalidParameter",
        "message": (
            "Total tokens of image and text exceed max message tokens. Request id: fixture"
        ),
        "param": "",
    }
}


class _VectorSink:
    """只替代 Qdrant；FTS 必须消费 indexer 的实际产物，不能从 fixture 重算。"""

    def __init__(self, bm25_store: SQLiteBm25Store):
        self.bm25_store = bm25_store
        self.points: dict[str, EvalPoint] = {}

    async def upsert(self, *, dataset_id: int, points: Sequence[EvalPoint]) -> None:
        assert dataset_id == DATASET_ID
        bm25_points = []
        for point in points:
            assert point.bm25_tokens is not None
            assert point.sparse is not None
            assert len(point.dense) == 2
            assert point.chunk_id not in self.points
            self.points[point.chunk_id] = point
            bm25_points.append(SQLiteBm25Point(
                chunk_id=point.chunk_id, doc_id=point.doc_id, user_id=USER_ID,
                dataset_id=dataset_id, chunk_type=point.chunk_type, tokens=point.bm25_tokens,
            ))
        await self.bm25_store.upsert_chunks(bm25_points)

    async def fetch_indexed_rows(
        self, *, dataset_id: int, chunk_ids: Sequence[str], expected_doc_ids: dict[str, int]
    ) -> dict[str, int]:
        assert dataset_id == DATASET_ID
        found = {cid: self.points[cid].doc_id for cid in chunk_ids if cid in self.points}
        assert all(doc_id == expected_doc_ids[cid] for cid, doc_id in found.items())
        return found

    async def verify_collection_count(self, *, dataset_id: int, expected_count: int) -> None:
        assert dataset_id == DATASET_ID
        assert len(self.points) == expected_count


def _prefix_attempts(text: str, limit: int | None) -> list[str]:
    """独立列出协议要求的请求序列；门槛仅属于测试中的服务替身。"""
    attempts = [text]
    while limit is not None and len(attempts[-1]) > limit:
        previous = attempts[-1]
        attempts.append(previous[:len(previous) // 2])
    return attempts


class _MockServices:
    def __init__(self, dense_policy: str, sparse_policy: str):
        self.dense_limit = DENSE_MOCK_LIMIT if dense_policy == PREFIX_POLICY else None
        self.sparse_limit = SPARSE_MOCK_LIMIT if sparse_policy == PREFIX_POLICY else None
        self.dense_attempts: list[list[str]] = []
        self.sparse_attempts: list[str] = []
        self.dense_successes: list[str] = []
        self.sparse_successes: list[str] = []

    def dense(self, request: httpx.Request) -> httpx.Response:
        assert request.url.host == "dense.invalid"
        batch = json.loads(request.content)["input"]
        self.dense_attempts.append(batch)
        if self.dense_limit is not None and any(len(text) > self.dense_limit for text in batch):
            return httpx.Response(400, json=DENSE_LENGTH_ERROR)
        self.dense_successes.extend(batch)
        # 相同前缀返回相同向量；不能靠按原始 PID 制造不同向量来掩盖实体合并。
        return httpx.Response(200, json={"data": [
            {"index": index, "embedding": [float(len(text)), 1.0]}
            for index, text in enumerate(batch)
        ]})

    def sparse(self, request: httpx.Request) -> httpx.Response:
        assert request.url.host == "sparse.invalid"
        payload = json.loads(request.content)
        assert payload["sparse_embedding"] == {"type": "enabled"}
        assert len(payload["input"]) == 1
        assert payload["input"][0]["type"] == "text"
        text = payload["input"][0]["text"]
        self.sparse_attempts.append(text)
        if self.sparse_limit is not None and len(text) > self.sparse_limit:
            return httpx.Response(400, json=SPARSE_LENGTH_ERROR)
        self.sparse_successes.append(text)
        return httpx.Response(200, json={"data": {
            "sparse_embedding": [{"index": 7, "value": float(len(text))}],
        }})

    def assert_requests(self, passages: list[tuple[str, str]]) -> None:
        originals = [text for _, text in passages]
        dense_chains = [_prefix_attempts(text, self.dense_limit) for text in originals]
        sparse_chains = [_prefix_attempts(text, self.sparse_limit) for text in originals]
        expected_dense = [originals]
        if self.dense_limit is not None:
            expected_dense += [[text] for chain in dense_chains for text in chain]
        # Dense 批次原样失败后，各单条仍先全文；短项不能跟着同行长项被缩短。
        assert self.dense_attempts == expected_dense
        # 包括两路均启用的情况：Sparse 每条首次发送仍是原文，不是 Dense 成功前缀。
        assert self.sparse_attempts == [text for chain in sparse_chains for text in chain]
        assert self.dense_successes == [chain[-1] for chain in dense_chains]
        assert self.sparse_successes == [chain[-1] for chain in sparse_chains]
        if self.dense_limit is not None:
            assert self.dense_successes[0] == self.dense_successes[1]
            assert self.dense_successes[0] != originals[0]
        if self.sparse_limit is not None:
            assert self.sparse_successes[0] == self.sparse_successes[1]
            assert self.sparse_successes[0] != originals[0]


async def _ingest_and_check(
    *, run_dir: Path, collection_path: Path, qrels_path: Path,
    passages: list[tuple[str, str]], dense_policy: str, sparse_policy: str,
    service,
):
    run_dir.mkdir()
    engine = create_async_engine(f"sqlite+aiosqlite:///{run_dir}/corpus.sqlite3")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(EvalBase.metadata.create_all)
        repo = EvalCorpusRepo(sessionmaker=async_sessionmaker(engine, expire_on_commit=False))
        bm25 = SQLiteBm25Store(run_dir / "bm25.sqlite3")
        await bm25.ensure_collection()
        vectors = _VectorSink(bm25)
        async with (
            httpx.AsyncClient(transport=httpx.MockTransport(service.dense)) as dense_http,
            httpx.AsyncClient(transport=httpx.MockTransport(service.sparse)) as sparse_http,
        ):
            computer = RagProductComputer(
                dense_encoder=OpenAIDenseEmbedder(
                    api_key="test-only", model="dense-mock", base_url="https://dense.invalid",
                    dim=2, batch_size=len(passages), concurrency=1, max_retries=0,
                    input_length_policy=dense_policy, http_client=dense_http,
                ),
                sparse_encoder=ArkSparseEncoder(
                    api_key="test-only", model="sparse-mock", base_url="https://sparse.invalid",
                    concurrency=1, max_retries=0, input_length_policy=sparse_policy,
                    http_client=sparse_http,
                ),
            )
            indexer = EvalVectorIndexer(
                computer=computer, vector_store=vectors, corpus_repo=repo,
                with_sparse=True, bm25_mode="sqlite_fts5",
            )
            progress = await ingest_t2_collection(
                collection_path=collection_path, dataset_id=DATASET_ID, doc_id_base=DOC_ID_BASE,
                batch_size=len(passages), corpus_repo=repo, indexer=indexer, vector_store=vectors,
                bm25_store=bm25, user_id=USER_ID, expected_passage_count=len(passages),
            )
        assert progress == {
            "processed_passages": len(passages), "indexed_passages": len(passages),
            "skipped_passages": 0, "completed_batches": 1,
        }
        service.assert_requests(passages)
        # 与原始字面正文逐条比，不仅比较两组结果（两组都错也可能相等）。
        rows = await repo.fetch_chunks_for_datasets([DATASET_ID])
        by_pid = {row.source_passage_id: row for row in rows}
        assert len(rows) == len(by_pid) == len(passages)
        assert set(by_pid) == {pid for pid, _ in passages}
        snapshot = []
        for position, (pid, original) in enumerate(passages):
            row = by_pid[pid]
            chunk_id = eval_chunk_id(DATASET_ID, DOC_ID_BASE + position, 0)
            assert row.dataset_id == DATASET_ID
            assert row.doc_id == DOC_ID_BASE + position
            assert row.ordinal == 0
            assert row.chunk_id == chunk_id
            assert row.content == original
            assert row.char_len == len(original)
            assert row.content_hash == content_hash(original)
            assert row.dense_indexed and row.sparse_indexed and row.bm25_indexed
            assert row.dense_input_chars == len(service.dense_successes[position])
            assert row.sparse_input_chars == len(service.sparse_successes[position])
            point = vectors.points[chunk_id]
            assert point.dense == [float(row.dense_input_chars), 1.0]
            assert point.sparse.indices == [7]
            assert point.sparse.values == [float(row.sparse_input_chars)]
            assert point.sparse.input_chars == row.sparse_input_chars
            snapshot.append((pid, row.dataset_id, row.doc_id, row.ordinal, row.chunk_id, row.content))

        # 三个正文仅尾词不同，即使编码前缀完全相同也必须保留三个不同实体。
        tail_pids = {"tailalpha": "0000", "tailbravo": "0001", "tailomega": "0004"}
        for token, pid in tail_pids.items():
            hits = await bm25.recall_topk_chunks(SimpleNamespace(
                dataset_id=DATASET_ID, doc_id=None, tokens=[token], top_k=len(passages),
            ))
            assert [hit.chunk_id for hit in hits] == [by_pid[pid].chunk_id]

        # 标签映射从真实 SQL 返回值构建，不能直接拿期望 PID 造出正确关联。
        keys = [(DATASET_ID, by_pid[pid].chunk_id) for pid, _ in passages]
        source_rows = await repo.fetch_candidate_rows(keys)
        joined = join_candidate_qrels(
            source_query_id="0009", candidate_keys=keys,
            source_rows=[
                (row["dataset_id"], row["chunk_id"], row["source_passage_id"])
                for row in source_rows
            ],
            qrels=read_t2_qrels(qrels_path),
        )
        assert joined.candidate_keys == tuple(keys)
        assert joined.grades == {keys[grade]: grade for grade in range(4)}
        assert joined.issues == {}
        assert keys[4] not in joined.grades
        coverage = summarize_label_coverage([joined])
        assert coverage["overall"]["pool"] == {
            "total": 5, "grade_counts": {"0": 1, "1": 1, "2": 1, "3": 1},
            "judged": 4, "unjudged": 1,
            "issue_counts": {"mapping_missing": 0, "mapping_ambiguous": 0, "qrel_conflict": 0},
            "coverage": 0.8,
        }
        return snapshot, joined, coverage
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    ("dense_policy", "sparse_policy"),
    [(PREFIX_POLICY, "reject"), ("reject", PREFIX_POLICY), (PREFIX_POLICY, PREFIX_POLICY)],
    ids=["dense-only", "sparse-only", "both"],
)
async def test_encoding_prefix_keeps_full_corpus_bm25_and_qrel_identity(
    tmp_path: Path, dense_policy: str, sparse_policy: str,
) -> None:
    shared = "  中文🙂 shared words \t" * 64
    passages = [
        ("0000", shared + "tailalpha  "),
        ("0001", shared + "tailbravo  "),
        ("0002", "\t短文 控制🙂  "),
        ("0003", "short control  "),
        ("0004", shared + "tailomega  "),
    ]
    collection_path = tmp_path / "collection.tsv"
    qrels_path = tmp_path / "qrels.tsv"
    collection_text = "".join(f"{pid}\t{text}\n" for pid, text in passages)
    qrels_text = "".join(
        f"0009\t0\t{pid}\t{grade}\n" for grade, (pid, _) in enumerate(passages[:4])
    )
    collection_path.write_text(collection_text, encoding="utf-8")
    qrels_path.write_text(qrels_text, encoding="utf-8")
    assert list(iter_t2_collection(collection_path)) == passages

    # reject 对照的 mock 接受全文；每次都从全新三路存储开始，避免续接绕过编码。
    baseline = await _ingest_and_check(
        run_dir=tmp_path / "reject", collection_path=collection_path, qrels_path=qrels_path,
        passages=passages, dense_policy="reject", sparse_policy="reject",
        service=_MockServices("reject", "reject"),
    )
    recovered = await _ingest_and_check(
        run_dir=tmp_path / "prefix", collection_path=collection_path, qrels_path=qrels_path,
        passages=passages, dense_policy=dense_policy, sparse_policy=sparse_policy,
        service=_MockServices(dense_policy, sparse_policy),
    )
    assert recovered == baseline
    assert list(iter_t2_collection(collection_path)) == passages
    assert collection_path.read_bytes() == collection_text.encode("utf-8")
    assert qrels_path.read_bytes() == qrels_text.encode("utf-8")
