"""Hand-computed provenance checks; no data files, models or training involved."""

from __future__ import annotations

import json
import math
from copy import deepcopy

import numpy as np
import pytest

from linkrag_eval.retrieval.learning_to_rank.diagnostic_features import (
    SEMANTIC_STATUS,
    trace_features,
)
from linkrag_eval.retrieval.learning_to_rank.experiment import FEATURE_NAMES, build_online_features
from linkrag_eval.retrieval.learning_to_rank.features import ENGLISH_FEATURE_VERSION


def _input():
    contents = {"target": "AB—ab. cd", "peer": "abxy", "background": "zz"}
    routes = {}
    for source, pairs in {
        "dense": [("target", 0.9), ("peer", 0.6), ("background", 0.3)],
        "sparse": [("target", 3.0), ("peer", 1.0)],
        "bm25": [("target", 7.0), ("background", 7.0)],
    }.items():
        routes[source] = [
            {
                "chunk_id": cid,
                "score": score,
                "rank": index,
                "doc_id": 10 if cid != "background" else 20,
                "dataset_id": 1,
            }
            for index, (cid, score) in enumerate(pairs)
        ]
    return {"query": "ab ab，并且cd", "routes": routes, "candidate_contents": contents}


def _trace(inputs, targets=("target",)):
    ids, matrix = build_online_features(**inputs)
    result = trace_features(
        **inputs, target_chunk_ids=targets, reference_ids=ids, reference_features=matrix
    )
    json.dumps(result, ensure_ascii=False, allow_nan=False)
    return result


@pytest.mark.parametrize("query,content", [
    ("NOT ready", "It isn't ready."),
    ("isn’t allowed", "ISNʼT allowed"),
    ("not ready", "notable knot not2 not_a_token"),
    ("ABC-12. 1,234.50", "ABC-123 and ABC-12 cost 1234.50."),
    ("3.14", "13.14"),
    ("Dr. Lee paid 3.14. Beta ready.", "Beta ready. Dr. Lee paid 3.14."),
    ("A U.S. item costs 1,234.50.", "An item costs 1,234.50."),
    ("and an", "an"),
    ("J. Smith uses v2.1. Go now.", "Go now. J. Smith uses v2.1."),
])
def test_english_trace_uses_frozen_rules_and_original_offsets(query, content):
    inputs = _input()
    inputs["query"] = query
    inputs["candidate_contents"]["target"] = content
    original = deepcopy(inputs)
    ids, features = build_online_features(**inputs, feature_version=ENGLISH_FEATURE_VERSION)
    trace = trace_features(**inputs, target_chunk_ids=["target", "missing"], reference_ids=ids,
                           reference_features=features, feature_version=ENGLISH_FEATURE_VERSION)
    assert trace["verification"]["passed"] and trace["feature_version"] == ENGLISH_FEATURE_VERSION
    assert trace["targets"]["missing"]["status"] == "missing_from_pool"
    assert inputs == original
    for text_trace in (trace["query_trace"], trace["targets"]["target"]["text_trace"]):
        text = text_trace["raw_text"]
        spans = [*text_trace["condition_split"]["retained_clauses"],
                 *[m for v in text_trace["regex_extraction"].values() for m in v["matches"]],
                 *[m for matches in text_trace["literal_negations"]["occurrences"].values() for m in matches]]
        for span in spans:
            assert text[span["start"]:span["end"]] == span["quote"]
    json.dumps(trace, ensure_ascii=False, allow_nan=False)
    replay_ids, replay = build_online_features(**inputs, feature_version=ENGLISH_FEATURE_VERSION)
    assert ids == replay_ids
    np.testing.assert_array_equal(features, replay)


def test_english_trace_cannot_accept_legacy_matrix():
    inputs = _input()
    inputs["query"] = "not ready"
    inputs["candidate_contents"]["target"] = "cannot be ready"
    ids, old = build_online_features(**inputs)
    result = trace_features(**inputs, target_chunk_ids=["target"], reference_ids=ids,
                            reference_features=old, feature_version=ENGLISH_FEATURE_VERSION)
    assert not result["verification"]["passed"]
    assert result["targets"]["target"]["status"] == "blocked_reference_mismatch"


def test_all_38_columns_match_hand_computed_values_and_do_not_mutate_inputs():
    inputs = _input()
    original = deepcopy(inputs)
    ids, matrix = build_online_features(**inputs)
    preserved = matrix.copy()
    matrix.flags.writeable = False
    report = trace_features(
        **inputs, target_chunk_ids=["target"], reference_ids=ids, reference_features=matrix
    )
    assert inputs == original
    np.testing.assert_array_equal(matrix, preserved)
    replay_ids, replay = build_online_features(**inputs)
    assert replay_ids == ids
    np.testing.assert_array_equal(replay, preserved)
    assert report["verification"]["passed"]
    assert report["verification"]["max_abs_difference"] == 0.0
    assert [column["name"] for column in report["feature_dependencies"]] == FEATURE_NAMES
    assert len(report["feature_dependencies"]) == 38
    assert {column["semantic_classification"] for column in report["feature_dependencies"]} == {
        SEMANTIC_STATUS
    }
    actual = report["targets"]["target"]["feature_values"]
    expected = np.array(
        [
            0.9,
            math.log(4),
            math.log(8),  # raw / transformed scores
            1,
            1,
            1,  # route normalization
            1,
            1,
            1,  # reciprocal ranks
            0,
            0,
            0,  # missing
            3,
            1,
            1,
            1,
            1,  # counts and presence combinations
            0,
            0,
            0,  # reciprocal-rank gaps
            1 / 3,
            0.5,
            0,  # route top-two margins
            1,
            1,  # baseline score and reciprocal rank
            10,
            0,  # original query length / digit
            0,
            0,
            0,
            0,  # identifiers, numbers, literal negation coverage / mismatch
            0.5,
            1 / 3,
            1,
            1 / 3,  # bigrams, trigrams, conditions, distinctive bigrams
            1,
            1 / 6,
            math.log(10),  # same-doc peers / max Jaccard / original text length
        ],
        dtype=np.float32,
    )
    np.testing.assert_array_equal(np.array(list(actual.values()), dtype=np.float32), expected)
    json.dumps(report, ensure_ascii=False, allow_nan=False)


def test_occurrences_are_kept_before_set_coverage_and_pool_frequency_is_document_presence():
    report = _trace(_input())
    target = report["targets"]["target"]
    bigrams = target["text_trace"]["ngrams"]["2"]
    assert bigrams["unique_set"] == ["ab", "ba", "bc", "cd"]
    assert bigrams["by_gram"]["ab"]["count"] == 2
    assert [row["raw_span"] for row in bigrams["by_gram"]["ab"]["occurrences"]] == [
        {"start": 0, "end": 2, "quote": "AB"},
        {"start": 3, "end": 5, "quote": "ab"},
    ]
    coverage = target["text_features"]["query_bigram_coverage"]
    assert coverage["numerator"] == 3
    assert coverage["denominator"] == 6
    assert coverage["matched_set"] == ["ab", "ba", "cd"]
    pool = report["pool_summary"]
    assert pool["bigram_document_frequency"]["ab"] == 2  # Not three raw occurrences.
    assert set(pool["bigram_candidate_ids"]["ab"]) == {"target", "peer"}
    distinctive = target["text_features"]["distinctive_query_bigram_coverage"]
    assert distinctive["matched_set"] == ["ba", "cd"]
    assert distinctive["rejected_matched_set"] == ["ab"]
    same_doc = target["text_features"]["same_doc"]
    assert same_doc["peers"] == [
        {"chunk_id": "peer", "intersection_count": 1, "union_count": 6, "jaccard": 1 / 6}
    ]


def test_character_mapping_marks_case_expansion_and_cross_removed_boundaries():
    inputs = _input()
    inputs["query"] = "ab"
    inputs["candidate_contents"]["target"] = "İA— B. B"
    trace = _trace(inputs)["targets"]["target"]["text_trace"]
    assert trace["normalized_text"] == "i\u0307abb"
    mapping = trace["normalized_character_map"]
    assert (
        mapping[0] == mapping[1] == {"raw_start": 0, "raw_end": 1, "mapping": "lowercase_expansion"}
    )
    gram = trace["ngrams"]["2"]["by_gram"]["ab"]["occurrences"][0]
    assert gram["raw_span"] == {"start": 1, "end": 5, "quote": "A— B"}
    assert gram["raw_segments"] == [[1, 2], [4, 5]]
    assert gram["joins_removed_characters"]
    cross_sentence = trace["ngrams"]["2"]["by_gram"]["bb"]["occurrences"][0]
    assert cross_sentence["diagnostic_sentence_ids"] == [0, 1]
    assert not trace["diagnostic_sentences_used_by_features"]
    for size in ("2", "3"):
        for record in trace["ngrams"][size]["by_gram"].values():
            for occurrence in record["occurrences"]:
                raw = occurrence["raw_span"]
                assert trace["raw_text"][raw["start"] : raw["end"]] == raw["quote"]
                assert 0 <= raw["start"] < raw["end"] <= len(trace["raw_text"])


def test_actual_condition_split_and_diagnostic_sentences_are_separate():
    report = _trace(_input())
    split = report["query_trace"]["condition_split"]
    assert [part["quote"] for part in split["retained_clauses"]] == ["ab ab", "cd"]
    assert [part["quote"] for part in split["separators"]] == ["，", "并且"]
    coverage = report["targets"]["target"]["text_features"]["condition_coverage"]
    assert coverage["gate_open"]
    assert coverage["numerator"] == coverage["denominator_used"] == 2
    assert [part["denominator"] for part in coverage["clauses"]] == [2, 1]
    inputs = _input()
    inputs["query"] = "not open. not open"
    report = _trace(inputs)
    assert len(report["query_trace"]["diagnostic_sentences"]) == 2
    assert len(report["query_trace"]["condition_split"]["retained_clauses"]) == 1
    assert report["query_trace"]["literal_negations"]["unique_set"] == []
    coverage = report["targets"]["target"]["text_features"]["condition_coverage"]
    assert not coverage["gate_open"]
    assert coverage["denominator_used"] is None
    assert coverage["model_input_value"] == 0


def test_exact_coverage_is_lowercased_substring_search_not_content_token_equality():
    inputs = _input()
    inputs["query"] = "v1.2 12 12 不得，不"
    inputs["candidate_contents"]["target"] = "V1.2 312 不得"
    report = _trace(inputs)
    extraction = report["query_trace"]["regex_extraction"]["number"]
    assert extraction["unique_set"] == ["1.2", "12"]
    assert len(extraction["matches"]) == 3
    target = report["targets"]["target"]
    number = target["text_features"]["number_exact_coverage"]
    assert number["numerator"] == number["denominator"] == 2
    assert number["model_input_value"] == 1.0
    assert number["occurrences_by_needle"]["12"][0]["raw_span"] == {
        "start": 6,
        "end": 8,
        "quote": "12",
    }
    assert target["text_trace"]["regex_extraction"]["number"]["unique_set"] == ["1.2", "312"]
    assert report["query_trace"]["literal_negations"]["unique_set"] == ["不", "不得"]
    assert target["text_features"]["negation_overlap_coverage"]["denominator"] == 2
    assert target["text_features"]["negation_mismatch"]["model_input_value"] == 0


def test_route_and_baseline_normalization_use_different_pools_and_list_positions():
    inputs = _input()
    inputs["routes"]["dense"][1]["score"] = 0.6
    inputs["routes"]["dense"][2]["score"] = 0.0  # Removed only by baseline threshold.
    inputs["routes"]["dense"][0]["rank"] = 999  # Existing core ignores this field.
    report = _trace(inputs, targets=("peer",))
    dense = report["pool_summary"]["routes"]["dense"]
    assert dense["baseline_retained_ids"] == ["target", "peer"]
    row = report["targets"]["peer"]["route_trace"]["dense"]
    assert row["normalized"] == pytest.approx(2 / 3)
    assert row["baseline_normalized"] == 0
    assert row["effective_rank_one_based"] == 2
    assert dense["hits"][0]["supplied_rank"] == 999
    assert dense["hits"][0]["effective_rank_one_based"] == 1


@pytest.mark.parametrize("mismatch", ["values", "ids", "dtype", "shape", "nonfinite"])
def test_reference_mismatch_blocks_interpretation_without_relaxing_precision(mismatch):
    inputs = _input()
    ids, matrix = build_online_features(**inputs)
    if mismatch == "values":
        matrix[0, 0] = np.nextafter(matrix[0, 0], np.float32(np.inf))
    elif mismatch == "ids":
        ids = list(reversed(ids))
    elif mismatch == "dtype":
        matrix = matrix.astype(np.float64)
    elif mismatch == "shape":
        matrix = matrix[:1]
    else:
        matrix[0, 0] = np.nan
    report = trace_features(
        **inputs, target_chunk_ids=["target"], reference_ids=ids, reference_features=matrix
    )
    assert not report["verification"]["passed"]
    assert report["targets"]["target"]["status"] == "blocked_reference_mismatch"
    assert report["query_trace"] is report["pool_summary"] is None
    json.dumps(report, allow_nan=False)


def test_missing_targets_and_empty_union_are_retained_without_injecting_text():
    inputs = _input()
    inputs["candidate_contents"]["unrecalled"] = "Available outside the actual route union."
    report = _trace(inputs, targets=("target", "unrecalled"))
    assert report["verification"]["passed"]
    assert report["targets"]["unrecalled"]["status"] == "missing_from_pool"
    assert "unrecalled" not in report["pool_summary"]["candidate_ids"]
    inputs["routes"] = {source: [] for source in inputs["routes"]}
    report = _trace(inputs)
    assert report["verification"]["passed"]
    assert report["pool_summary"]["candidate_count"] == 0
    assert report["targets"]["target"]["status"] == "missing_from_pool"
