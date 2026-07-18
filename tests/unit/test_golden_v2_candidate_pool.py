"""Golden V2 candidate pool:seeds + chunks → candidate_pool jsonl。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from linkrag_eval.cli import _build_alt_embedding_searcher
from linkrag_eval.golden_v2 import build_candidate_pool, build_live_candidate_pool
from linkrag_eval.store.alt_embedding_cache import AltEmbeddingCache


@dataclass(frozen=True)
class _Hit:
    chunk_id: str
    score: float


class _FakeAltEmbedder:
    def __init__(self) -> None:
        self.batch_calls = 0

    async def aembed(self, texts):
        self.batch_calls += 1
        mapping = {
            "目标内容": [1.0, 0.0],
            "干扰内容": [0.0, 1.0],
            "其他数据集": [1.0, 0.0],
        }
        return [mapping[t] for t in texts]

    async def aembed_query(self, text):
        assert text == "目标 query"
        return [1.0, 0.0]


def _write_jsonl(path, rows) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_build_candidate_pool_merges_bm25_and_random(tmp_path) -> None:
    seeds = tmp_path / "query_seeds.jsonl"
    chunks = tmp_path / "chunk_records.jsonl"
    out = tmp_path / "candidate_pool.jsonl"
    _write_jsonl(
        seeds,
        [{"seed_id": "q1", "query": "政策办理多久", "source": "spark_pregen"}],
    )
    _write_jsonl(
        chunks,
        [
            {
                "chunk_id": "c1",
                "dataset_id": 990901,
                "doc_id": 1,
                "content": "政策办理时限为 7 个工作日。",
            },
            {
                "chunk_id": "c2",
                "dataset_id": 990901,
                "doc_id": 2,
                "content": "会员积分每月有抵扣上限。",
            },
        ],
    )

    report = build_candidate_pool(
        seeds,
        chunks_path=chunks,
        out=out,
        report_out=tmp_path / "report.json",
        bm25_top_n=1,
        random_n=2,
        seed=1,
    )

    assert report.queries == 1
    assert report.candidates == 2
    row = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert row["query_id"] == "q1"
    assert row["role"] == "realistic"
    by_id = {c["chunk_id"]: c for c in row["candidates"]}
    assert "bm25_local" in by_id["c1"]["sources"]
    assert "random_neighbor" in set().union(*(set(c["sources"]) for c in row["candidates"]))
    assert row["dataset_ids"] == [990901]


def test_build_candidate_pool_marks_hard_role(tmp_path) -> None:
    seeds = tmp_path / "hard.jsonl"
    chunks = tmp_path / "chunks.jsonl"
    _write_jsonl(
        seeds,
        [{"seed_id": "h1", "query": "没关键词的问题", "hard_reason": "no_keyword"}],
    )
    _write_jsonl(
        chunks,
        [{"chunk_id": "c1", "dataset_id": 1, "doc_id": 1, "content": "正文"}],
    )
    build_candidate_pool(seeds, chunks_path=chunks, out=tmp_path / "out.jsonl")
    row = json.loads((tmp_path / "out.jsonl").read_text(encoding="utf-8"))
    assert row["role"] == "hard"
    assert row["hard_reason"] == "no_keyword"


@pytest.mark.asyncio
async def test_build_live_candidate_pool_merges_routes_and_counts_missing(tmp_path) -> None:
    seeds = tmp_path / "query_seeds.jsonl"
    out = tmp_path / "candidate_pool.jsonl"
    _write_jsonl(
        seeds,
        [{"seed_id": "q1", "query": "政策办理多久", "dataset_ids": [990901]}],
    )
    chunks = [
        {
            "chunk_id": "c1",
            "dataset_id": 990901,
            "doc_id": 1,
            "content": "政策办理时限为 7 个工作日。",
        },
        {
            "chunk_id": "c2",
            "dataset_id": 990901,
            "doc_id": 2,
            "content": "会员积分每月有抵扣上限。",
        },
    ]

    async def route_search(query, dataset_ids, source, top_n):
        assert query == "政策办理多久"
        assert dataset_ids == [990901]
        hits = {
            "bm25": [_Hit("c1", 3.0), _Hit("missing", 2.0)],
            "dense": [_Hit("c1", 0.9), _Hit("c2", 0.2)],
        }[source]
        return hits[:top_n]

    report = await build_live_candidate_pool(
        seeds,
        chunks=chunks,
        route_search=route_search,
        out=out,
        report_out=tmp_path / "report.json",
        sources=["bm25", "dense"],
        route_top_n=5,
        random_n=1,
        source_labels={"bm25": "bm25_sqlite_fts5", "dense": "current_dense"},
        score_thresholds={"dense": 0.0, "alt_embedding": None},
    )

    assert report.mode == "live"
    assert report.routes == ["bm25", "dense"]
    assert report.score_thresholds == {"dense": 0.0, "alt_embedding": None}
    assert report.missing_chunks == 1
    assert report.source_candidate_counts == {
        "bm25_sqlite_fts5": 1,
        "current_dense": 2,
        "random_neighbor": 1,
    }
    assert report.source_query_coverage == {
        "bm25_sqlite_fts5": 1,
        "current_dense": 1,
        "random_neighbor": 1,
    }
    assert report.candidates_per_query == {"min": 2.0, "median": 2.0, "max": 2.0}
    row = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    by_id = {c["chunk_id"]: c for c in row["candidates"]}
    assert {"bm25_sqlite_fts5", "current_dense"}.issubset(set(by_id["c1"]["sources"]))
    assert "current_dense" in by_id["c2"]["sources"]
    assert row["dataset_ids"] == [990901]


@pytest.mark.asyncio
async def test_build_live_candidate_pool_can_ignore_seed_dataset_scope(tmp_path) -> None:
    seeds = tmp_path / "query_seeds.jsonl"
    out = tmp_path / "candidate_pool.jsonl"
    _write_jsonl(
        seeds,
        [{"seed_id": "q1", "query": "跨域证据", "dataset_ids": [990901]}],
    )
    chunks = [
        {
            "chunk_id": "c1",
            "dataset_id": 990901,
            "doc_id": 1,
            "content": "原始数据集内容",
        },
        {
            "chunk_id": "c2",
            "dataset_id": 990902,
            "doc_id": 2,
            "content": "跨域证据内容",
        },
    ]
    seen_dataset_ids = []

    async def route_search(query, dataset_ids, source, top_n):
        assert query == "跨域证据"
        del source, top_n
        seen_dataset_ids.append(dataset_ids)
        return [_Hit("c2", 0.9)]

    report = await build_live_candidate_pool(
        seeds,
        chunks=chunks,
        route_search=route_search,
        out=out,
        sources=["dense"],
        route_top_n=1,
        random_n=0,
        use_seed_dataset_ids=False,
    )

    assert report.queries == 1
    assert seen_dataset_ids == [[990901, 990902]]
    row = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert row["dataset_ids"] == [990902]


@pytest.mark.asyncio
async def test_build_live_candidate_pool_preserves_explicit_role(tmp_path) -> None:
    seeds = tmp_path / "query_seeds.jsonl"
    out = tmp_path / "candidate_pool.jsonl"
    _write_jsonl(
        seeds,
        [
            {
                "seed_id": "q1",
                "query": "多约束真实问题",
                "role": "realistic",
                "hard_reason": "multi_constraint",
            }
        ],
    )
    chunks = [
        {"chunk_id": "c1", "dataset_id": 1, "doc_id": 1, "content": "证据"}
    ]

    async def route_search(query, dataset_ids, source, top_n):
        del query, dataset_ids, source, top_n
        return [_Hit("c1", 0.9)]

    await build_live_candidate_pool(
        seeds,
        chunks=chunks,
        route_search=route_search,
        out=out,
        sources=["dense"],
        route_top_n=1,
        random_n=0,
    )

    row = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert row["role"] == "realistic"
    assert row["hard_reason"] == "multi_constraint"


@pytest.mark.asyncio
async def test_alt_embedding_searcher_ranks_and_filters_dataset() -> None:
    chunks = [
        SimpleNamespace(chunk_id="c1", dataset_id=1, doc_id=11, content="目标内容", content_hash="h1"),
        SimpleNamespace(chunk_id="c2", dataset_id=1, doc_id=12, content="干扰内容", content_hash="h2"),
        SimpleNamespace(chunk_id="c3", dataset_id=2, doc_id=21, content="其他数据集", content_hash="h3"),
    ]
    searcher = await _build_alt_embedding_searcher(chunks, embedder=_FakeAltEmbedder())

    hits = await searcher.search("目标 query", [1], 2)

    assert [h.chunk_id for h in hits] == ["c1", "c2"]
    assert hits[0].score > hits[1].score


@pytest.mark.asyncio
async def test_alt_embedding_searcher_uses_cache(tmp_path) -> None:
    chunks = [
        SimpleNamespace(chunk_id="c1", dataset_id=1, doc_id=11, content="目标内容", content_hash="h1"),
        SimpleNamespace(chunk_id="c2", dataset_id=1, doc_id=12, content="干扰内容", content_hash="h2"),
    ]
    cache = AltEmbeddingCache(tmp_path / "alt.sqlite3")
    embedder = _FakeAltEmbedder()
    await _build_alt_embedding_searcher(chunks, embedder=embedder, cache=cache, model_key="m")
    assert embedder.batch_calls == 1

    await _build_alt_embedding_searcher(chunks, embedder=embedder, cache=cache, model_key="m")
    assert embedder.batch_calls == 1
