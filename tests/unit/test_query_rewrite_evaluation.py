from __future__ import annotations

from pathlib import Path

from linkrag_eval.golden.schema import GoldenSample
from linkrag_eval.models import Layer, RankedHit, StageOutput
from linkrag_eval.query_rewrite.evaluation import (
    evaluate_rewrite_pairs,
    protect_candidates,
)
from linkrag_eval.query_rewrite.schema import QueryRewritePlan
from linkrag_eval.retrieval.tuning import RouteHit


def _ranked(chunk_ids: list[str]) -> list[RankedHit]:
    return [
        RankedHit(
            chunk_id=chunk_id,
            doc_id=index,
            dataset_id=992000,
            rank=index,
            score=1 - index / 100,
        )
        for index, chunk_id in enumerate(chunk_ids)
    ]


def test_protected_candidate_replaces_unprotected_tail() -> None:
    ranked = _ranked([f"c{i}" for i in range(20)])
    per_source = {
        "dense": [],
        "sparse": [
            RouteHit("c15", 15, 992000, 10.0, "sparse"),
            RouteHit("c16", 16, 992000, 9.0, "sparse"),
        ],
        "bm25": [],
    }

    protected = protect_candidates(
        ranked,
        per_source,
        {"dense": 0, "sparse": 2, "bm25": 0},
        final_top_k=10,
        extra_protected=["c8"],
    )

    ids = [hit.chunk_id for hit in protected]
    assert len(ids) == 10
    assert {"c15", "c16"} <= set(ids)
    assert "c8" in ids
    assert "c9" not in ids


class FakePairEvaluator:
    final_top_k = 10
    include_original = True
    top_ks = {"dense": 150, "sparse": 50, "bm25": 100}
    thresholds = {"dense": 0.3, "sparse": 0.2, "bm25": 0.0}
    use_plan_weights = True
    use_candidate_protection = True
    original_protected_top_k = 5

    async def run_pair(self, sample, plan):
        original_ids = [] if sample.id == "gain" else ["target"]
        rewritten_ids = ["target"] if sample.id == "gain" else []
        return (
            StageOutput(layer=Layer.RETRIEVAL, query=sample.query, ranked=_ranked(original_ids)),
            StageOutput(layer=Layer.RETRIEVAL, query=sample.query, ranked=_ranked(rewritten_ids)),
        )


def _sample(sample_id: str) -> GoldenSample:
    return GoldenSample(
        id=sample_id,
        query=f"query {sample_id}",
        user_id=990001,
        dataset_ids=[992000],
        expected_chunk_ids=["target"],
        expected_doc_ids=[1],
    )


def _plan(sample: GoldenSample) -> QueryRewritePlan:
    return QueryRewritePlan.fallback_plan(
        sample_id=sample.id,
        original_query=sample.query,
    )


async def test_pair_report_counts_gained_and_lost(tmp_path: Path) -> None:
    samples = [_sample("gain"), _sample("lost")]

    payload = await evaluate_rewrite_pairs(
        samples,
        plans={sample.id: _plan(sample) for sample in samples},
        evaluator=FakePairEvaluator(),
        out_dir=tmp_path,
    )

    assert payload["transitions"]["gained"] == 1
    assert payload["transitions"]["lost"] == 1
    assert payload["delta"]["hit_at_10"] == 0.0
    assert payload["clean_subset"]["samples"] == 2
    assert (tmp_path / "query_rewrite_pair_report.html").exists()
