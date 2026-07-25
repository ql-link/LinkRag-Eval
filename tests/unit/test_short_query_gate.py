from linkrag_eval.retrieval.learning_to_rank.short_query_gate import (
    ShortQueryFallbackConfig,
    apply_short_query_fallback,
    tune_short_query_fallback,
)


def test_low_confidence_short_query_falls_back() -> None:
    ranked, fallback, confidence = apply_short_query_fallback(
        query="退款时限", ltr_ranked=["bad","good"], ltr_scores=[0.51,0.50],
        hybrid_ranked=["good","bad"],
        config=ShortQueryFallbackConfig("v",10,0.1),
    )
    assert fallback and ranked[0] == "good" and confidence < 0.1


def test_tuner_selects_rule_only_from_prediction_rows() -> None:
    result=tune_short_query_fallback([{
        "query":"退款时限", "candidate_chunk_ids":["bad","good"],
        "candidate_ltr_scores":[0.51,0.50], "candidate_baseline_rr":[0.5,1.0],
        "expected_chunk_ids":["good"],
    }], thresholds=(0.1,), max_query_chars_values=(10,))
    assert result["best"]["fallback_count"] == 1
    assert result["best"]["hit_at_10"] == 1.0
