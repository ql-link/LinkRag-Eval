from __future__ import annotations

from linkrag_eval.retrieval.candidate_routing import (
    CandidateDepths,
    candidate_union_hit,
    classify_candidate_query,
    depths_for_query,
    has_exact_identifier,
)


def test_query_classifier_uses_exclusive_runtime_features() -> None:
    assert classify_candidate_query("订单版本 V2.3 如何回滚") == "exact_identifier"
    assert classify_candidate_query("滞留 24 小时后怎么处理") == "number_time"
    assert classify_candidate_query("退款异常金额") == "short_keyword"
    assert (
        classify_candidate_query("如果订单已拆分并且优惠券已核销，同时发生部分退款时是否重算")
        == "long_multi"
    )
    assert classify_candidate_query("用户改签失败后应如何继续处理补偿申请？") == "natural_default"


def test_depths_for_query_returns_frozen_short_query_profile() -> None:
    depths = depths_for_query("退款异常金额")
    assert depths == CandidateDepths(dense=300, sparse=100, bm25=225)


def test_exact_identifier_gate_rejects_plain_numbers_and_accepts_ids() -> None:
    assert has_exact_identifier("订单版本 V2.3 如何回滚")
    assert has_exact_identifier("查询工单 AB-20250716")
    assert not has_exact_identifier("3 分钟内提交三类诉求")
    assert not has_exact_identifier("滞留退运按目的地类型处理")


def test_candidate_union_hit_applies_rank_and_threshold() -> None:
    row = {
        "expected_chunk_ids": ["target"],
        "routes": {
            "dense": [{"chunk_id": "target", "score": 0.29}],
            "sparse": [{"chunk_id": "other", "score": 1.0}],
            "bm25": [
                {"chunk_id": "other", "score": 2.0},
                {"chunk_id": "target", "score": 1.0},
            ],
        },
    }
    assert candidate_union_hit(row, CandidateDepths(1, 1, 2))
    assert not candidate_union_hit(row, CandidateDepths(1, 1, 1))
