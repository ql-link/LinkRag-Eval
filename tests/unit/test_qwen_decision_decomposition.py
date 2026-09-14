"""Synthetic checks for attribution branches against the frozen ranking semantics."""

import importlib.util
from pathlib import Path

import pytest

from linkrag_eval.retrieval.learning_to_rank.llm_judge import resort


@pytest.fixture(scope="module")
def decomposition():
    path = (Path(__file__).resolve().parents[2]
            / "runs/post_recall/nevir-test-main-20260911/decompose_qwen.py")
    spec = importlib.util.spec_from_file_location("qwen_decomposition", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("fusion,judged,k,branch,final", [
    ({"p": 1, "o": 2}, {"p": 4, "o": 0}, 2, "qwen_different_scores", "strict_correct"),
    ({"p": 2, "o": 1}, {"p": 1, "o": 4}, 2, "qwen_different_scores", "reverse"),
    ({"p": 1, "o": 2}, {"p": 4, "o": 4}, 2, "qwen_tie_fusion", "reverse"),
    ({"p": 2, "o": 1}, {"p": 4, "o": 4}, 2, "qwen_tie_fusion", "strict_correct"),
    ({"p": 1, "o": 1}, {"p": 4, "o": 4}, 2, "qwen_tie_fusion", "model_tie"),
    ({"p": 2, "o": 1}, {"p": 0}, 1, "preferred_only_in_window", "strict_correct"),
    ({"p": 1, "o": 2}, {"o": 0}, 1, "other_only_in_window", "reverse"),
    ({"p": 1, "o": 1}, {"o": 4}, 1, "other_only_in_window", "reverse"),
    ({"p": 2, "o": 1, "z": 3}, {"z": 0}, 1, "both_outside_window", "strict_correct"),
    ({"p": 1, "o": 1, "z": 3}, {"z": 0}, 1, "both_outside_window", "model_tie"),
    ({"p": 1, "o": 2, "z": 3}, {"p": 4, "o": 0, "z": None}, 3,
     "whole_query_fallback", "reverse"),
    ({"p": 2, "o": 1, "z": 3}, {"z": None}, 1,
     "whole_query_fallback", "strict_correct"),
])
def test_actual_decision_key_matches_resort(decomposition, fusion, judged, k, branch, final):
    decision = decomposition.classify(fusion, judged, "p", "o", top_k=k)
    _, values, stats = resort(fusion, judged, top_k=k)
    assert decision["branch"] == branch
    assert decision["final"] == final == decomposition.relation(values["p"], values["o"])
    assert stats["fallback"] == (branch == "whole_query_fallback")
    assert decision["boundary_fusion_tie"] == (
        branch == "other_only_in_window" and fusion["p"] == fusion["o"]
    )


@pytest.mark.parametrize("judged,k", [
    ({"p": 4}, 2), ({"p": 4, "o": 0, "extra": 1}, 2),
    ({"p": True, "o": 0}, 2), ({"p": 4.0, "o": 0}, 2),
    ({"p": 5, "o": 0}, 2), ({"p": 4, "o": 0}, True),
    ({"p": 4, "o": 0}, 0),
])
def test_bad_evidence_is_rejected_not_silently_attributed(decomposition, judged, k):
    with pytest.raises(ValueError):
        decomposition.classify({"p": 1, "o": 2}, judged, "p", "o", top_k=k)


def test_correct_result_source_is_distinct_from_incremental_gain(decomposition):
    rows = [
        decomposition.classify({"p": 2, "o": 1}, {"p": 4, "o": 4}, "p", "o"),
        decomposition.classify({"p": 1, "o": 2}, {"p": 4, "o": 0}, "p", "o"),
        decomposition.classify({"p": 2, "o": 1}, {"p": 0, "o": 4}, "p", "o"),
    ]
    ties = decomposition.summarize(rows[:1])
    assert ties["strict_correct"] == 1
    assert ties["corrected"] == ties["damaged"] == ties["net_correct"] == 0
    total = decomposition.summarize(rows)
    assert total["strict_correct"] == total["fusion_correct"] == 2
    assert total["corrected"] == total["damaged"] == 1
    assert total["net_correct"] == 0
