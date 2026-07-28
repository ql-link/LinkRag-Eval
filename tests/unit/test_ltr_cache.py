from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from linkrag_eval.golden.schema import GoldenSample
from linkrag_eval.retrieval.learning_to_rank.cache import cache_ltr_candidates


@dataclass
class _Hit:
    chunk_id: str
    doc_id: int = 1
    dataset_id: int = 992000
    score: float = 1.0


class _Retriever:
    def __init__(self, source: str, calls: list[tuple[str, str, int]]) -> None:
        self.source = source
        self.calls = calls

    async def recall(self, query, _datasets, _filters, *, user_id, top_k, score_threshold_override):
        assert user_id == 990001
        assert score_threshold_override == 0.0
        self.calls.append((query, self.source, top_k))
        return [_Hit(f"{self.source}-{query}")]


@pytest.mark.asyncio
async def test_query_routing_uses_per_sample_top_k(monkeypatch, tmp_path) -> None:
    calls: list[tuple[str, str, int]] = []
    pipeline = SimpleNamespace(
        _retrievers=[_Retriever(source, calls) for source in ("dense", "sparse", "bm25")]
    )
    monkeypatch.setattr(
        "linkrag_eval.retrieval.recall_factory.build_eval_recall_pipeline",
        lambda **_kwargs: pipeline,
    )
    samples = [
        GoldenSample(
            id="short",
            query="退款异常金额",
            user_id=990001,
            dataset_ids=[992000],
            expected_chunk_ids=["target-short"],
        ),
        GoldenSample(
            id="number",
            query="滞留 24 小时后怎么处理",
            user_id=990001,
            dataset_ids=[992000],
            expected_chunk_ids=["target-number"],
        ),
    ]
    settings = SimpleNamespace(
        recall_dense_top_k=200,
        recall_sparse_top_k=50,
        recall_bm25_top_k=200,
    )

    report = await cache_ltr_candidates(
        samples,
        settings=settings,
        out=tmp_path / "candidates.jsonl",
        use_query_routing=True,
    )

    assert ("退款异常金额", "dense", 300) in calls
    assert ("退款异常金额", "sparse", 100) in calls
    assert ("退款异常金额", "bm25", 225) in calls
    assert ("滞留 24 小时后怎么处理", "dense", 275) in calls
    assert ("滞留 24 小时后怎么处理", "sparse", 50) in calls
    assert ("滞留 24 小时后怎么处理", "bm25", 200) in calls
    assert report["query_routing"] is True
    assert report["average_theoretical_candidate_budget"] == 575.0
