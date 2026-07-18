from __future__ import annotations

from linkrag_eval.retrieval.learning_to_rank.experiment import (
    FEATURE_NAMES,
    _candidate_features,
    _fold,
    _render_external_html,
    _render_html,
    rank_with_hybrid_protection,
    tune_hybrid_protection,
)


def row(doc_id: int = 10) -> dict:
    return {
        "sample_id": f"q-{doc_id}",
        "query": "订单ABC-2025为什么不能退款",
        "scenario": "exact_identifier",
        "expected_chunk_ids": ["target"],
        "expected_doc_ids": [doc_id],
        "routes": {
            "dense": [
                {
                    "chunk_id": "dense-only",
                    "doc_id": 1,
                    "dataset_id": 992000,
                    "score": 0.9,
                    "rank": 0,
                },
                {
                    "chunk_id": "target",
                    "doc_id": doc_id,
                    "dataset_id": 992000,
                    "score": 0.2,
                    "rank": 1,
                },
            ],
            "sparse": [
                {
                    "chunk_id": "target",
                    "doc_id": doc_id,
                    "dataset_id": 992000,
                    "score": 5.0,
                    "rank": 0,
                }
            ],
            "bm25": [],
        },
        "failed_sources": [],
    }


def test_candidate_features_include_positive_and_route_overlap() -> None:
    contents = {
        "dense-only": "订单XYZ-2024允许退款，没有其他限制。",
        "target": "订单ABC-2025不能退款，版本v2.1规则明确禁止退款。",
    }
    chunk_ids, features, labels = _candidate_features(row(), contents)

    assert features.shape == (2, len(FEATURE_NAMES))
    assert labels.tolist() == [0, 1]
    target_index = chunk_ids.index("target")
    route_count_index = FEATURE_NAMES.index("route_count")
    exact_index = FEATURE_NAMES.index("scenario_exact")
    identifier_index = FEATURE_NAMES.index("identifier_exact_coverage")
    number_index = FEATURE_NAMES.index("number_exact_coverage")
    negation_index = FEATURE_NAMES.index("negation_overlap_coverage")
    assert features[target_index, route_count_index] == 2
    assert features[target_index, exact_index] == 1
    assert features[target_index, identifier_index] == 1
    assert features[target_index, number_index] == 1
    assert features[target_index, negation_index] == 1


def test_candidate_features_require_content_sidecar() -> None:
    try:
        _candidate_features(row())
    except ValueError as exc:
        assert "candidate_difference_v2" in str(exc)
    else:
        raise AssertionError("missing candidate contents must fail")


def test_fold_is_stable_for_same_evidence_document() -> None:
    assert _fold(row(10), 5) == _fold({**row(10), "sample_id": "another"}, 5)


def test_rank_with_hybrid_protection_reserves_baseline_top_candidate() -> None:
    ranked = rank_with_hybrid_protection(
        ["hybrid", "ltr"],
        [0.1, 0.9],
        [1.0, 0.0],
        [1.0, 0.0],
        blend_alpha=1.0,
        protect_baseline_top_k=1,
    )

    assert ranked == ["hybrid", "ltr"]


def test_tune_hybrid_protection_prefers_configuration_with_more_hits() -> None:
    prediction = {
        "baseline_hit_at_10": 1.0,
        "baseline_mrr": 1.0,
        "expected_chunk_ids": ["target"],
        "candidate_chunk_ids": ["target", *[f"n-{index}" for index in range(10)]],
        "candidate_ltr_scores": [0.0, *[float(index) for index in range(10)]],
        "candidate_baseline_scores": [1.0, *([0.0] * 10)],
        "candidate_baseline_rr": [1.0, *([0.0] * 10)],
    }

    tuned = tune_hybrid_protection(
        [prediction], blend_alphas=(1.0,), protect_top_ks=(0, 1)
    )

    assert tuned["best"]["protect_baseline_top_k"] == 1
    assert tuned["best"]["hit_at_10"] == 1.0


def test_render_html_includes_scenario_and_candidate_coverage() -> None:
    report = {
        "overall": {
            "baseline_hit_at_10": 0.6,
            "ltr_hit_at_10": 0.7,
            "delta_hit_at_10": 0.1,
            "baseline_mrr": 0.3,
            "ltr_mrr": 0.4,
            "candidate_union_coverage": 0.9,
        },
        "transitions": {"gained": 2, "lost": 1},
        "folds": 1,
        "fold_reports": [
            {
                "fold": 0,
                "valid_queries": 10,
                "baseline_hit_at_10": 0.6,
                "ltr_hit_at_10": 0.7,
                "delta_hit_at_10": 0.1,
                "baseline_mrr": 0.3,
                "ltr_mrr": 0.4,
            }
        ],
        "scenario_overall": {
            "long_sparse": {
                "n": 10,
                "baseline_hit_at_10": 0.6,
                "ltr_hit_at_10": 0.7,
                "delta_hit_at_10": 0.1,
                "candidate_union_coverage": 0.9,
            }
        },
        "feature_importance": [{"feature": "dense_rr", "importance": 3}],
    }

    rendered = _render_html(report)

    assert "长描述/多条件" in rendered
    assert "候选池覆盖率" in rendered


def test_render_external_html_marks_separate_evaluation() -> None:
    report = {
        "train_samples": 420,
        "test_samples": 116,
        "historical_baseline_hit_at_10": 0.3965,
        "overall": {
            "baseline_hit_at_10": 0.4,
            "ltr_hit_at_10": 0.45,
            "delta_hit_at_10": 0.05,
            "baseline_mrr": 0.2,
            "ltr_mrr": 0.25,
            "candidate_union_coverage": 0.9,
            "delta_mrr": -0.01,
        },
        "evidence_overlap_test_samples": 2,
        "strict_no_evidence_overlap": {
            "n": 114,
            "baseline_hit_at_10": 0.39,
            "ltr_hit_at_10": 0.44,
            "delta_hit_at_10": 0.05,
            "baseline_mrr": 0.2,
            "ltr_mrr": 0.19,
        },
        "transitions": {"gained": 8, "lost": 2},
        "scenario_overall": {
            "paraphrase": {
                "n": 116,
                "baseline_hit_at_10": 0.4,
                "ltr_hit_at_10": 0.45,
                "delta_hit_at_10": 0.05,
                "candidate_union_coverage": 0.9,
            }
        },
    }

    rendered = _render_external_html(report)

    assert "跨 Query 集泛化测试" in rendered
    assert "39.65%" in rendered
    assert "排除证据重叠" in rendered
    assert "MRR@10 下降" in rendered
