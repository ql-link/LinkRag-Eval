from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from linkrag_eval.retrieval.learning_to_rank.features import (
    ENGLISH_FEATURE_VERSION,
    FEATURE_VERSION,
)

spec = importlib.util.spec_from_file_location("nevir_compare_feature_versions", Path(__file__).parents[2] / "scripts/nevir_compare_feature_versions.py")
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


def prediction(qid, relation):
    return {"source_query_id": qid, "source_group_id": "source", "pair_id": qid[:-1],
            "direction": qid[-1], "exclusion_reasons": ["missing"] if relation == "unavailable" else [],
            "candidate_count": 3, "preference_relation": relation}


def test_comparison_preserves_missing_ties_and_all_four_cells():
    states = [("correct", "correct"), ("wrong", "correct"), ("correct", "wrong"),
              ("tie", "wrong"), ("unavailable", "unavailable"), ("correct", "tie")]
    a = [prediction(f"p{i//2}q{i%2}", x) for i, (x, _) in enumerate(states)]
    b = [prediction(r["source_query_id"], y) for r, (_, y) in zip(a, states, strict=True)]
    result, records = comparison.compare_predictions(a, b)
    assert result["four_cells"] == {"both_correct": 1, "corrected": 1, "harmed": 2,
                                     "neither_strictly_correct": 1, "not_evaluable": 1}
    assert result["net_corrected"] == -1 and result["covered_queries"] == 5
    assert result["covered_pairs"] == 2 and result["english"]["paired_correct"] == 1
    assert len(records) == 6 and all(r["human_adjudication"] == "pending" for r in records)


def test_comparison_rejects_different_population_or_association():
    a = [prediction("p0q0", "correct")]
    for key, value in [("source_query_id", "other"), ("source_group_id", "other"),
                       ("pair_id", "other"), ("exclusion_reasons", ["missing"])]:
        b = deepcopy(a)
        b[0][key] = value
        with pytest.raises(ValueError):
            comparison.compare_predictions(a, b)


def test_feature_response_rejects_unplanned_column_or_weight_change():
    row = SimpleNamespace(query_id="q", method_view={}, chunk_ids=["a", "b"],
                          selected_indices=[0, 1], exclusion_reasons=[], features=np.zeros((2, 38), dtype=np.float32))
    a = SimpleNamespace(feature_version=FEATURE_VERSION, queries=[row], groups=[2],
                        y=np.array([1, 0]), weights=np.ones(2))
    b = deepcopy(a)
    b.feature_version = ENGLISH_FEATURE_VERSION
    b.queries[0].features[0, 29] = 1
    assert comparison.compare_features(a, b)["negation_overlap_coverage"]["changed_queries"] == 1
    b.queries[0].features[0, 0] = 1
    with pytest.raises(ValueError, match="unexpected feature"):
        comparison.compare_features(a, b)
    b.queries[0].features[0, 0] = 0
    b.weights[0] = 2
    with pytest.raises(ValueError, match="weights differ"):
        comparison.compare_features(a, b)


def test_historical_counts_are_required():
    dataset = SimpleNamespace(role="train", summary={"eligible_query_count": 1868})
    with pytest.raises(ValueError, match="eligible_query_count"):
        comparison.check_dataset(dataset, {"eligible_query_count": 1869})
