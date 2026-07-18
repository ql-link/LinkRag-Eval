from __future__ import annotations

import pytest

from linkrag_eval.query_rewrite.schema import QueryRewritePlan, extract_preserved_terms


def test_extracts_identifier_date_and_negation() -> None:
    terms = extract_preserved_terms("版本ABC-2025-017在2025-07-01后不能退款")

    assert "ABC-2025-017" in terms
    assert "2025-07-01" in terms
    assert "不能" in terms


def test_extracts_colloquial_negation() -> None:
    assert "没" in extract_preserved_terms("观察期还没结束")


def test_model_plan_preserves_missing_literals_in_bm25_query() -> None:
    plan = QueryRewritePlan.from_model_dict(
        {
            "query_type": "exact_identifier",
            "queries": {
                "dense": "查询认证规则",
                "sparse": "认证规则",
                "bm25": "认证规则",
            },
            "weights": {"dense": 3, "sparse": 3.5, "bm25": 3.5},
            "protected_candidates": {"dense": 2, "sparse": 3, "bm25": 3},
            "confidence": 0.8,
        },
        sample_id="q1",
        original_query="ABC-2025-017不能退款吗",
        model="rewrite-model",
        prompt_version="v1",
    )

    assert "ABC-2025-017" in plan.bm25_query
    assert "不能" in plan.bm25_query
    assert sum(plan.weights.values()) == pytest.approx(1.0)
    assert plan.weights == {"dense": 0.3, "sparse": 0.35, "bm25": 0.35}
    assert plan.protected_candidates == {"dense": 0, "sparse": 3, "bm25": 3}


def test_fallback_uses_original_query_for_all_routes() -> None:
    plan = QueryRewritePlan.fallback_plan(sample_id="q1", original_query="退款限制")

    assert plan.fallback
    assert {plan.route_query(route) for route in ("dense", "sparse", "bm25")} == {"退款限制"}
