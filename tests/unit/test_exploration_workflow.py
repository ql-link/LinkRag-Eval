"""探索文件编排的语义验证，不连接模型或召回服务。"""

from __future__ import annotations

import asyncio
import copy
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from linkrag_eval.runners.exploration_workflow import (
    build_exploration_coverage,
    prepare_exploration_candidates,
    select_queries,
    write_exploration_inputs,
)


def _row(qid, chunks=(), *, status="ready"):
    return {
        "source_query_id": qid,
        "sample_id": qid,
        "query": f"问题{qid}",
        "dataset_ids": [123],
        "status": status,
        "ranking_input_ready": status in {"ready", "empty"},
        "routes": {
            "dense": [
                {"dataset_id": 123, "chunk_id": cid, "doc_id": i + 1, "score": 0.8, "rank": i}
                for i, (cid, _) in enumerate(chunks)
            ],
            "sparse": [],
            "bm25": [],
        },
        "candidate_rows": [
            {
                "dataset_id": 123,
                "chunk_id": cid,
                "doc_id": i + 1,
                "source_passage_id": pid,
                "content": f"正文{cid}",
                "ordinal": 0,
            }
            for i, (cid, pid) in enumerate(chunks)
        ],
        "source_rows": [[123, cid, pid] for cid, pid in chunks],
        "failed_sources": ["dense"] if status == "failed" else [],
        "input_issues": [{"code": "candidate_execution_failed"}] if status == "failed" else [],
    }


def _files(tmp_path, rows, judgments):
    inputs = tmp_path / "inputs.jsonl"
    inputs.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    (tmp_path / "queries.jsonl").write_text(
        "".join(
            json.dumps({"source_query_id": row["source_query_id"], "query": row["query"]}) + "\n"
            for row in rows
        )
    )
    queries = tmp_path / "queries.tsv"
    queries.write_text(
        "qid\ttext\n" + "".join(f"{qid}\t问题{qid}\n" for qid in ["1", "2", "3", "4"])
    )
    qrels = tmp_path / "qrels.tsv"
    qrels.write_text("qid\t-\tpid\trel\n" + judgments)
    return {"inputs_path": inputs, "queries_path": queries, "qrels_path": qrels}


class FakeRanker:
    def __init__(self):
        self.calls = []

    async def rank(self, row, contents):
        assert set(row) == {"query", "routes"}
        self.calls.append(copy.deepcopy((row, contents)))
        return SimpleNamespace(
            ranked_chunk_ids=list(reversed(contents)),
            mode="fixture",
            model_version="fixture",
            elapsed_ms=1.0,
            reason=None,
        )


def test_sampling_uses_all_queries_and_preserves_original_text():
    queries = {"001": "  原样查询  ", "002": "没有标签的查询", "003": "只有零级判断"}
    first = select_queries(queries, sample_size=3, seed=9)
    assert first == queries
    assert list(first) == list(select_queries(queries, sample_size=3, seed=9))
    assert first["001"] == "  原样查询  "
    with pytest.raises(ValueError):
        select_queries(queries, sample_size=0, seed=9)


async def test_input_writer_keeps_failed_and_empty_queries_and_rejects_overwrite(tmp_path):
    received = []

    async def collect(**kwargs):
        assert set(kwargs) == {"source_query_id", "query", "dataset_ids", "sample_id"}
        received.append(kwargs)
        return _row(
            kwargs["source_query_id"],
            status="failed" if kwargs["source_query_id"] == "1" else "empty",
        )

    out_dir = tmp_path / "run"
    summary = await write_exploration_inputs(
        queries={"1": "问题1", "2": "问题2"},
        dataset_id=123,
        out_dir=out_dir,
        collect_input=collect,
        metadata={"seed": 3},
    )
    assert summary == {"query_count": 2, "input_status_counts": {"failed": 1, "empty": 1}}
    assert len((out_dir / "inputs.jsonl").read_text().splitlines()) == 2
    with pytest.raises(FileExistsError):
        await write_exploration_inputs(
            queries={}, dataset_id=123, out_dir=out_dir, collect_input=collect, metadata={}
        )
    assert len(received) == 2


async def test_end_to_end_coverage_keeps_zero_unknown_empty_and_failed_queries(tmp_path):
    rows = [
        _row("1", [("c1", "p1"), ("c2", "p2"), ("c3", "p3")]),
        _row("2", [("c4", "p4")]),
        _row("3", status="empty"),
        _row("4", status="failed"),
    ]
    paths = _files(tmp_path, rows, "1\t-\tp1\t0\n1\t-\tp2\t3\n2\t-\tp4\t0\n")
    ranker = FakeRanker()
    report = await build_exploration_coverage(**paths, ranker=ranker, k=2)
    full = report["observed_candidate_coverage"]
    assert full["query_count"] == 4
    assert full["overall"]["pool"]["total"] == 4
    assert full["overall"]["pool"]["judged"] == 3
    assert full["overall"]["pool"]["unjudged"] == 1
    assert full["overall"]["pool"]["grade_counts"]["0"] == 2
    assert full["per_query"][2]["pool"]["coverage"] is None
    assert report["baseline_coverage"]["query_count"] == 3
    assert report["baseline_coverage"]["overall"]["baseline_top_k"]["total"] == 3
    assert report["baseline_coverage"]["overall"]["baseline_top_k"]["judged"] == 2
    assert report["baseline_unavailable"] == [
        {"source_query_id": "4", "reason": "incomplete_input"}
    ]
    assert len(ranker.calls) == 2
    assert report["input_status_counts"] == {"ready": 2, "empty": 1, "failed": 1}

    paths["qrels_path"].write_text(paths["qrels_path"].read_text() + "1\t-\tp3\t2\n")
    changed_ranker = FakeRanker()
    changed = await build_exploration_coverage(**paths, ranker=changed_ranker, k=2)
    assert changed_ranker.calls == ranker.calls
    assert changed["observed_candidate_coverage"]["overall"]["pool"]["judged"] == 4


async def test_incomplete_contract_keeps_candidate_only_key_in_observed_counts(tmp_path):
    row = _row("1", [("c1", "p1")], status="incomplete")
    row["candidate_rows"].append(
        {
            "dataset_id": 123,
            "chunk_id": "c2",
            "doc_id": 2,
            "content": None,
            "source_passage_id": "p2",
            "ordinal": 0,
        }
    )
    row["input_issues"] = [{"code": "candidate_pool_mismatch"}]
    report = await build_exploration_coverage(**_files(tmp_path, [row], "1\t-\tp1\t0\n"))
    assert report["observed_candidate_coverage"]["overall"]["pool"]["total"] == 2
    assert report["input_status_counts"] == {"incomplete": 1}


async def test_wrong_source_queries_and_foreign_qrels_are_not_silently_filtered(tmp_path):
    paths = _files(tmp_path, [_row("1")], "9\t-\tp1\t3\n")
    with pytest.raises(ValueError, match="查询 ID"):
        await build_exploration_coverage(**paths)
    paths["qrels_path"].write_text("qid\t-\tpid\trel\n")
    paths["inputs_path"].write_text(json.dumps({**_row("1"), "query": "不同查询"}) + "\n")
    with pytest.raises(ValueError, match="不一致"):
        await build_exploration_coverage(**paths)


async def test_bad_baseline_is_reported_without_fabricating_top_k(tmp_path):
    class BadRanker:
        async def rank(self, row, contents):
            return SimpleNamespace(ranked_chunk_ids=["absent"])

    paths = _files(tmp_path, [_row("1", [("c1", "p1")])], "1\t-\tp1\t3\n")
    report = await build_exploration_coverage(**paths, ranker=BadRanker(), k=1)
    assert report["observed_candidate_coverage"]["overall"]["pool"]["judged"] == 1
    assert report["baseline_coverage"]["query_count"] == 0
    assert report["baseline_coverage"]["overall"]["baseline_top_k"]["coverage"] is None
    assert report["baseline_unavailable"][0]["reason"] == "ValueError"


def test_coverage_cli_does_not_load_live_configuration(tmp_path, monkeypatch):
    from linkrag_eval import cli, config

    def reject_settings():
        raise AssertionError("离线覆盖不得读取活栈配置")

    monkeypatch.setattr(config, "get_settings", reject_settings)
    paths = _files(tmp_path, [_row("1", [("c1", "p1")])], "1\t-\tp1\t0\n")
    out = tmp_path / "coverage.json"
    assert (
        cli.main(
            [
                "exploration",
                "coverage",
                "--inputs",
                str(paths["inputs_path"]),
                "--queries",
                str(paths["queries_path"]),
                "--qrels",
                str(paths["qrels_path"]),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    report = json.loads(out.read_text())
    assert report["observed_candidate_coverage"]["overall"]["pool"]["judged"] == 1
    assert report["baseline_coverage"] is None


async def test_interrupted_collection_keeps_unexecuted_selected_queries(tmp_path):
    async def collect(**kwargs):
        if kwargs["source_query_id"] == "2":
            raise RuntimeError("中途停止")
        return _row("1", [("c1", "p1")])

    out_dir = tmp_path / "run"
    with pytest.raises(RuntimeError):
        await write_exploration_inputs(
            queries={"1": "问题1", "2": "问题2"},
            dataset_id=123,
            out_dir=out_dir,
            collect_input=collect,
            metadata={},
        )
    queries = tmp_path / "queries.tsv"
    queries.write_text("qid\ttext\n1\t问题1\n2\t问题2\n")
    qrels = tmp_path / "qrels.tsv"
    qrels.write_text("qid\t-\tpid\trel\n1\t-\tp1\t0\n")
    report = await build_exploration_coverage(
        inputs_path=out_dir / "inputs.jsonl",
        queries_path=queries,
        qrels_path=qrels,
        ranker=FakeRanker(),
        k=1,
    )
    assert report["selected_query_count"] == 2
    assert report["observed_candidate_coverage"]["query_count"] == 2
    assert report["input_status_counts"] == {"ready": 1, "not_executed": 1}
    assert report["baseline_coverage"]["query_count"] == 1
    assert report["baseline_unavailable"] == [
        {"source_query_id": "2", "reason": "incomplete_input"}
    ]


@pytest.mark.parametrize("non_passage", [False, True])
async def test_current_contract_to_file_to_coverage_preserves_config_and_mapping(
    tmp_path, monkeypatch, non_passage
):
    from linkrag_eval.retrieval import recall_factory
    from linkrag_eval.store import corpus_repo

    queries = tmp_path / "queries.tsv"
    queries.write_text("qid\ttext\n001\t  原始查询  \n")
    collection = tmp_path / "collection.tsv"
    collection.write_text("pid\ttext\np1\t甲\np2\t乙\np3\t丙\n")
    qrels = tmp_path / "qrels.tsv"
    qrels.write_text("qid\t-\tpid\trel\n001\t-\tp1\t0\n001\t-\tp2\t3\n")
    hits = [
        SimpleNamespace(dataset_id=123, doc_id=i, chunk_id=f"c{i}", score=0.9 - i / 10)
        for i in range(1, 4)
    ]
    requests = []

    class Pipeline:
        async def execute(self, request):
            requests.append(request)
            return SimpleNamespace(
                candidate_hits=hits,
                hits=hits[:1],
                failed_sources=[],
                route_hits={"dense": hits[:2], "sparse": hits[1:], "bm25": []},
            )

    settings = SimpleNamespace(
        user_id=990001,
        bm25_mode="sqlite_fts5",
        embed_model="fixture",
        embed_dim=8,
        embed_input_length_policy="prefix_on_length_error",
        sparse_provider="fixture",
        sparse_model="fixture",
        sparse_input_length_policy="reject",
        sparse_top_k=256,
        sparse_min_weight=0.01,
        sparse_vector_name="sparse_text",
        bm25_sqlite_coarse_weight=2.0,
        bm25_sqlite_fine_weight=1.0,
        bm25_sqlite_path=str(tmp_path / "bm25.sqlite3"),
        qdrant_prefix="eval_fixture",
        qdrant_host="http://user:secret@localhost:6333",
        qdrant_bucket_count=16,
        recall_dense_top_k=4,
        recall_sparse_top_k=3,
        recall_bm25_top_k=2,
        recall_dense_score_threshold=0.35,
        recall_sparse_score_threshold=0.25,
        recall_dense_weight=0.6,
        recall_sparse_weight=0.3,
        recall_bm25_weight=0.1,
        database_url=lambda: f"sqlite+aiosqlite:///{tmp_path / 'corpus.sqlite3'}",
    )

    lifecycle = []

    @asynccontextmanager
    async def open_pipeline(**kwargs):
        assert kwargs == {"settings": settings}
        lifecycle.append("open")
        try:
            yield Pipeline()
        finally:
            lifecycle.append("close")

    async def fetch(keys):
        assert set(keys) == {(123, "c1"), (123, "c2"), (123, "c3")}
        return [
            {
                "dataset_id": 123,
                "chunk_id": f"c{i}",
                "doc_id": i,
                "content": f"原文{i}",
                "source_passage_id": f"p{i}",
                "ordinal": 1 if non_passage and i == 2 else 0,
            }
            for i in range(1, 4)
        ]

    monkeypatch.setattr(recall_factory, "open_eval_recall_pipeline", open_pipeline)
    monkeypatch.setattr(
        corpus_repo, "EvalCorpusRepo", lambda **kwargs: SimpleNamespace(fetch_candidate_rows=fetch)
    )
    out_dir = tmp_path / "run"
    await prepare_exploration_candidates(
        queries_path=queries,
        collection_path=collection,
        dataset_id=123,
        sample_size=1,
        seed=9,
        out_dir=out_dir,
        settings=settings,
    )
    assert lifecycle == ["open", "close"]
    assert len(requests) == 1
    req = requests[0]
    assert req.query == "  原始查询  "
    assert req.dataset_ids == [123]
    assert (req.dense_top_k, req.sparse_top_k, req.bm25_top_k, req.top_k) == (4, 3, 2, 9)
    assert (req.dense_score_threshold_override, req.sparse_score_threshold_override) == (0.35, 0.25)
    assert (
        req.fusion_dense_weight_override,
        req.fusion_sparse_weight_override,
        req.fusion_bm25_weight_override,
    ) == (0.6, 0.3, 0.1)
    assert req.enabled_sources == req.required_sources == ["dense", "sparse", "bm25"]
    metadata = json.loads((out_dir / "run.json").read_text())
    assert metadata["sparse"]["top_k"] == 256
    assert metadata["dense"]["input_length_policy"] == "prefix_on_length_error"
    assert metadata["sparse"]["input_length_policy"] == "reject"
    assert metadata["bm25_weights"] == {"coarse": 2.0, "fine": 1.0}
    assert metadata["storage"]["corpus_sqlite_path"] == str(tmp_path / "corpus.sqlite3")
    assert metadata["storage"]["qdrant_endpoint"] == {"host": "localhost", "port": 6333}
    assert "secret" not in json.dumps(metadata)
    assert metadata["collection_coverage"] == "not_established_by_candidate_collection"
    report = await build_exploration_coverage(
        inputs_path=out_dir / "inputs.jsonl",
        queries_path=queries,
        qrels_path=qrels,
        ranker=FakeRanker(),
        k=2,
    )
    pool = report["observed_candidate_coverage"]["overall"]["pool"]
    assert pool["total"] == 3  # 最终融合 hits 仅一条，三路并集仍完整。
    assert pool["grade_counts"]["0"] == 1
    assert pool["unjudged"] == 1
    if non_passage:
        assert pool["issue_counts"]["mapping_ambiguous"] == 1
        assert pool["grade_counts"]["3"] == 0
        assert report["baseline_unavailable"] == []
        assert (
            report["baseline_coverage"]["overall"]["baseline_top_k"]["issue_counts"][
                "mapping_ambiguous"
            ]
            == 1
        )
    else:
        assert pool["grade_counts"]["3"] == 1
        assert report["baseline_coverage"]["overall"]["baseline_top_k"]["total"] == 2


@pytest.mark.parametrize("cancelled", [False, True])
async def test_prepare_closes_pipeline_when_writing_fails_or_is_cancelled(
    tmp_path, monkeypatch, cancelled,
):
    from linkrag_eval.config import EvalSettings
    from linkrag_eval.retrieval import recall_factory
    from linkrag_eval.runners import exploration_workflow
    from linkrag_eval.store import corpus_repo

    queries = tmp_path / "queries.tsv"
    queries.write_text("qid\ttext\n1\t问题\n")
    collection = tmp_path / "collection.tsv"
    collection.write_text("pid\ttext\np1\t正文\n")
    settings = EvalSettings(_env_file=None, bm25_mode="sqlite_fts5")
    lifecycle = []
    writing = asyncio.Event()

    @asynccontextmanager
    async def open_pipeline(**_):
        lifecycle.append("open")
        try:
            yield object()
        finally:
            lifecycle.append("close")

    async def writer(**_):
        writing.set()
        if cancelled:
            await asyncio.Event().wait()
        raise OSError("output write failure")

    monkeypatch.setattr(recall_factory, "open_eval_recall_pipeline", open_pipeline)
    monkeypatch.setattr(exploration_workflow, "write_exploration_inputs", writer)
    monkeypatch.setattr(
        corpus_repo, "EvalCorpusRepo",
        lambda **_: SimpleNamespace(fetch_candidate_rows=lambda _: None),
    )
    task = asyncio.create_task(prepare_exploration_candidates(
        queries_path=queries, collection_path=collection, dataset_id=123, sample_size=1,
        seed=1, out_dir=tmp_path / "run", settings=settings,
    ))
    await asyncio.wait_for(writing.wait(), timeout=1)
    if cancelled:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        with pytest.raises(OSError, match="output write failure"):
            await task
    assert lifecycle == ["open", "close"]
