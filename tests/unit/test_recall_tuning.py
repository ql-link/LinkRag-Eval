"""召回参数搜索纯函数测试。"""

from __future__ import annotations

import pytest

from linkrag_eval.golden.schema import GoldenSample
from linkrag_eval.retrieval.tuning import (
    CachedSample,
    RouteHit,
    _html_report,
    iter_configs,
    run_grid,
    stage_output_for_config,
)


def _sample() -> GoldenSample:
    return GoldenSample(
        id="q1",
        query="query",
        user_id=1,
        dataset_ids=[990001],
        expected_doc_ids=[10],
    )


def test_grid_prefers_sparse_threshold_that_removes_noise() -> None:
    sample = _sample()
    cached = [
        CachedSample(
            sample=sample,
            dense_hits=[
                RouteHit("good", 10, 990001, 0.9, "dense"),
                RouteHit("bad", 20, 990001, 0.8, "dense"),
            ],
            sparse_hits=[
                RouteHit("bad", 20, 990001, 0.1, "sparse"),
            ],
        )
    ]

    results = run_grid(
        cached,
        iter_configs(
            dense_top_ks=[2],
            sparse_top_ks=[1],
            dense_thresholds=[0.0],
            sparse_thresholds=[0.0, 0.2],
            final_top_k=1,
            rrf_k=60,
        ),
    )

    assert results[0].sparse_threshold == 0.2
    assert results[0].recall_at_10 == 1.0


def test_stage_output_applies_route_topk_and_threshold() -> None:
    sample = _sample()
    cached = CachedSample(
        sample=sample,
        dense_hits=[
            RouteHit("d1", 1, 990001, 0.9, "dense"),
            RouteHit("d2", 2, 990001, 0.8, "dense"),
        ],
        sparse_hits=[
            RouteHit("s1", 3, 990001, 0.4, "sparse"),
            RouteHit("s2", 4, 990001, 0.1, "sparse"),
        ],
    )
    [config] = list(
        iter_configs(
            dense_top_ks=[1],
            sparse_top_ks=[2],
            dense_thresholds=[0.0],
            sparse_thresholds=[0.2],
            final_top_k=10,
            rrf_k=60,
        )
    )

    output = stage_output_for_config(cached, config)

    assert output.per_source_counts == {"dense": 1, "sparse": 1}
    assert {hit.chunk_id for hit in output.ranked} == {"d1", "s1"}


def test_weighted_score_uses_normalized_scores_and_active_weights() -> None:
    cached = CachedSample(
        sample=_sample(),
        dense_hits=[
            RouteHit("dense-best", 1, 990001, 0.9, "dense"),
            RouteHit("dense-tail", 2, 990001, 0.5, "dense"),
        ],
        sparse_hits=[
            RouteHit("sparse-best", 3, 990001, 9.0, "sparse"),
            RouteHit("sparse-tail", 4, 990001, 1.0, "sparse"),
        ],
    )
    [config] = list(
        iter_configs(
            dense_top_ks=[2],
            sparse_top_ks=[2],
            dense_thresholds=[0.0],
            sparse_thresholds=[0.0],
            final_top_k=4,
            rrf_k=60,
        )
    )

    output = stage_output_for_config(cached, config, fusion_strategy="weighted_score")

    assert [hit.chunk_id for hit in output.ranked] == [
        "dense-best",
        "sparse-best",
        "dense-tail",
        "sparse-tail",
    ]
    assert output.ranked[0].score == pytest.approx(0.625)
    assert output.ranked[1].score == pytest.approx(0.375)


def test_html_report_states_rrf_no_rerank_and_data_size() -> None:
    results = run_grid(
        [
            CachedSample(
                sample=_sample(),
                dense_hits=[RouteHit("good", 10, 990001, 0.9, "dense")],
                sparse_hits=[],
            )
        ],
        iter_configs(
            dense_top_ks=[20],
            sparse_top_ks=[5],
            dense_thresholds=[0.3],
            sparse_thresholds=[0.4],
            final_top_k=10,
            rrf_k=60,
        ),
    )
    payload = {
        "dataset": "combined_4domain_clean",
        "created_at": "2026-07-02T20:00:00",
        "args": {
            "dense_top_ks": [20],
            "sparse_top_ks": [5],
            "dense_thresholds": [0.3],
            "sparse_thresholds": [0.4],
            "final_top_k": 10,
            "rrf_k": 60,
            "concurrency": 4,
            "golden": "golden.jsonl",
            "corpus_chunks": 3200,
            "fusion": "RRF",
            "rerank": "none",
        },
        "n_samples": 394,
        "failed_source_samples": 0,
        "best": results[0].__dict__,
        "top20": [results[0].__dict__],
    }

    html = _html_report(payload, results)

    assert "融合算法为 <b>RRF</b>" in html
    assert "未启用 rerank" in html
    assert "394 条 golden query" in html
    assert "3200 chunks" in html
    assert "参数组合=1 组" in html
