"""app 编排:run_ingest / run_eval(注入 fake,不需 rag/活栈)。"""

from __future__ import annotations

import json

from linkrag_eval.app import format_retrieval_summary, run_eval, run_ingest
from linkrag_eval.config import EvalSettings
from linkrag_eval.metrics.retrieval import RecallAtK
from linkrag_eval.models import Layer, RankedHit, StageOutput


class _FakeIndexer:
    def __init__(self):
        self.batches = []

    async def index_passages(self, dataset_id, passages):
        self.batches.append((dataset_id, list(passages)))
        return len(passages)


class _FakeRepo:
    def __init__(self):
        self.registered = None

    async def register_dataset(self, dataset_id, **kw):
        self.registered = (dataset_id, kw)


def _write(tmp_path):
    coll = tmp_path / "c.tsv"
    coll.write_text("p1\t正文1\np2\t正文2\np3\t正文3\n", encoding="utf-8")
    man = tmp_path / "m.jsonl"
    man.write_text("\n".join(json.dumps(r) for r in [
        {"source_id": "p1", "doc_id": 10, "status": "success"},
        {"source_id": "p2", "doc_id": 11, "status": "failed"},   # 跳过
        {"source_id": "p3", "doc_id": 12, "status": "success"},
    ]), encoding="utf-8")
    return str(coll), str(man)


async def test_run_ingest_filters_and_batches(tmp_path) -> None:
    coll, man = _write(tmp_path)
    idx, repo = _FakeIndexer(), _FakeRepo()
    total = await run_ingest(
        990131, coll, man, indexer=idx, corpus_repo=repo,
        catalog={"name": "t", "source_type": "synth", "domain": "tech", "genre": None},
        batch=1,
    )
    assert total == 2  # 只 success 的 p1/p3
    assert repo.registered[0] == 990131
    # batch=1 → 2 批,doc_id 升序
    docs = [p.doc_id for b in idx.batches for p in b[1]]
    assert docs == [10, 12]


class _FakeRecall:
    layer = Layer.RETRIEVAL

    async def run(self, sample, *, upstream=None):
        # q1 命中 doc 1
        ranked = [RankedHit("c1", 1, 990131, 0, 0.9)]
        return StageOutput(layer=self.layer, query=sample.query, ranked=ranked)


class _Store:
    def save_snapshot(self, s): self.snap = s
    def save_report(self, r, c): ...
    def load_baseline(self, r): return None


async def test_run_eval_end_to_end(tmp_path) -> None:
    golden = tmp_path / "g.jsonl"
    golden.write_text(json.dumps(
        {"id": "q1", "query": "问", "user_id": 1, "dataset_ids": [990131], "expected_doc_ids": [1]}
    ), encoding="utf-8")

    result = await run_eval(
        str(golden), top_k=10, run_id="r1",
        evaluable=_FakeRecall(), metrics=[RecallAtK([1, 10])], store=_Store(),
    )
    recall = {(m.name, m.k): m.mean for m in result.metrics if m.name == "recall"}
    assert recall[("recall", 1)] == 1.0
    summary = format_retrieval_summary(result)
    assert "recall@1" in summary and "1.0000" in summary


async def test_run_eval_snapshot_records_recall_fusion_config(tmp_path) -> None:
    golden = tmp_path / "g.jsonl"
    golden.write_text(json.dumps(
        {"id": "q1", "query": "问", "user_id": 1, "dataset_ids": [990131], "expected_doc_ids": [1]}
    ), encoding="utf-8")
    settings = EvalSettings(_env_file=None)
    store = _Store()

    result = await run_eval(
        str(golden), top_k=10, run_id="r1",
        evaluable=_FakeRecall(), metrics=[RecallAtK([10])], store=store,
        settings=settings,
    )

    assert result.snapshot.route_top_ks == {"dense": 150, "sparse": 50}
    assert result.snapshot.route_score_thresholds == {"dense": 0.20, "sparse": 0.40}
    assert result.snapshot.fusion_strategy == "weighted_score"
    assert result.snapshot.fusion_weights == {"dense": 0.90, "sparse": 0.10, "bm25": 0.0}
