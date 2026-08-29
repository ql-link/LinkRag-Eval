"""Pure, post-lock finalization rules for the one Dev similarity supplement.

This module implements a missing executor for the already-frozen protocol.  It
does not amend the preregistration.  In particular, a preregistered
``construction_role`` identifies a fixed denominator slot only; human A/B
agreement supplies the final relation truth.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

RELATIONS = ("equivalent", "factual_conflict")
MINIMUM_COVERAGE = 0.60


def _average_ranks(values: Sequence[float]) -> np.ndarray:
    order = sorted(range(len(values)), key=lambda index: (values[index], index))
    ranks = np.zeros(len(values), dtype=np.float64)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + end - 1) / 2
        for position in range(start, end):
            ranks[order[position]] = rank
        start = end
    return ranks


def spearman(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return math.nan
    first = _average_ranks(left)
    second = _average_ranks(right)
    if float(np.std(first)) == 0 or float(np.std(second)) == 0:
        return math.nan
    return float(np.corrcoef(first, second)[0, 1])


def quadratic_weighted_kappa(left: Sequence[int], right: Sequence[int]) -> float:
    if len(left) != len(right) or not left:
        raise RuntimeError("invalid rating vectors")
    observed = np.zeros((5, 5), dtype=np.float64)
    for first, second in zip(left, right, strict=True):
        observed[first - 1, second - 1] += 1
    observed /= len(left)
    left_marginal = np.array([left.count(value) / len(left) for value in range(1, 6)])
    right_marginal = np.array([right.count(value) / len(right) for value in range(1, 6)])
    expected = np.outer(left_marginal, right_marginal)
    weights = np.array([[(i - j) ** 2 / 16 for j in range(5)] for i in range(5)])
    denominator = float(np.sum(weights * expected))
    if denominator == 0:
        return 1.0 if list(left) == list(right) else 0.0
    return 1.0 - float(np.sum(weights * observed)) / denominator


def inter_reviewer_summary(
    a: Mapping[str, Mapping[str, str]],
    b: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    if set(a) != set(b) or not a:
        raise RuntimeError("A/B similarity ID sets differ or are empty")
    ids = sorted(a)
    left = [int(a[audit_id]["human_similarity_ordinal"]) for audit_id in ids]
    right = [int(b[audit_id]["human_similarity_ordinal"]) for audit_id in ids]
    differences = [abs(first - second) for first, second in zip(left, right, strict=True)]
    mandatory = [
        audit_id
        for audit_id, difference in zip(ids, differences, strict=True)
        if difference >= 2
        or a[audit_id]["uncertain"] == "yes"
        or b[audit_id]["uncertain"] == "yes"
    ]
    nonexact = [
        audit_id
        for audit_id, difference in zip(ids, differences, strict=True)
        if difference != 0
    ]
    within_one_count = sum(difference <= 1 for difference in differences)
    qwk = quadratic_weighted_kappa(left, right)
    within_one = within_one_count / len(ids)
    return {
        "row_count_each": len(ids),
        "exact_agreement_count": sum(difference == 0 for difference in differences),
        "exact_agreement_fraction": sum(difference == 0 for difference in differences)
        / len(ids),
        "within_one_count": within_one_count,
        "within_one_fraction": within_one,
        "quadratic_weighted_kappa": qwk,
        "inter_reviewer_gate_pass": qwk >= 0.60 and within_one >= 0.90,
        "mandatory_adjudication_ids": sorted(mandatory),
        "nonexact_ids": sorted(nonexact),
        "adjudication_ids_for_unique_final_score": sorted(set(mandatory) | set(nonexact)),
    }


def require_zero_adjudication(
    review: Mapping[str, Any],
    relation_a: Sequence[Mapping[str, str]],
    relation_b: Sequence[Mapping[str, str]],
    similarity_a: Sequence[Mapping[str, str]],
    similarity_b: Sequence[Mapping[str, str]],
    *,
    expected_relation_rows: int,
    expected_similarity_rows: int,
) -> None:
    if review.get("relation_rows_each") != expected_relation_rows or review.get(
        "similarity_rows_each"
    ) != expected_similarity_rows:
        raise RuntimeError("pre-adjudication row-count drift")
    for key in (
        "relation_adjudication_ids",
        "similarity_mandatory_adjudication_ids",
        "similarity_adjudication_ids_for_unique_final_score",
    ):
        if review.get(key) != []:
            raise RuntimeError(f"zero-adjudication finalizer refuses non-empty {key}")
    if not (
        len(relation_a) == len(relation_b) == expected_relation_rows
        and len(similarity_a) == len(similarity_b) == expected_similarity_rows
    ):
        raise RuntimeError("validated submission row count drift")

    relation_b_by_id = {row["relation_audit_id"]: row for row in relation_b}
    if len(relation_b_by_id) != expected_relation_rows:
        raise RuntimeError("relation B duplicate IDs")
    fields = (
        "target_reference_status",
        "target_group_status",
        "target_relation",
        "conflict_type",
    )
    for row in relation_a:
        audit_id = row["relation_audit_id"]
        other = relation_b_by_id.get(audit_id)
        if other is None or any(row[field] != other[field] for field in fields):
            raise RuntimeError(f"zero-adjudication relation disagreement: {audit_id}")
        if row["uncertain"] != "no" or other["uncertain"] != "no":
            raise RuntimeError(f"zero-adjudication relation uncertainty: {audit_id}")

    similarity_b_by_id = {row["similarity_audit_id"]: row for row in similarity_b}
    if len(similarity_b_by_id) != expected_similarity_rows:
        raise RuntimeError("similarity B duplicate IDs")
    for row in similarity_a:
        audit_id = row["similarity_audit_id"]
        other = similarity_b_by_id.get(audit_id)
        if other is None or row["human_similarity_ordinal"] != other[
            "human_similarity_ordinal"
        ]:
            raise RuntimeError(f"zero-adjudication similarity disagreement: {audit_id}")
        if row["uncertain"] != "no" or other["uncertain"] != "no":
            raise RuntimeError(f"zero-adjudication similarity uncertainty: {audit_id}")


def build_final_relation_records(
    registry: Sequence[Mapping[str, Any]],
    relation_a: Sequence[Mapping[str, str]],
    relation_b: Sequence[Mapping[str, str]],
    scores_by_candidate: Mapping[str, Mapping[str, Any]],
    *,
    submission_hashes: Mapping[str, str],
) -> list[dict[str, Any]]:
    a_by_id = {row["relation_audit_id"]: row for row in relation_a}
    b_by_id = {row["relation_audit_id"]: row for row in relation_b}
    if set(a_by_id) != set(b_by_id) or set(a_by_id) != {
        row["relation_audit_id"] for row in registry
    }:
        raise RuntimeError("relation registry/submission ID drift")
    output = []
    fields = (
        "target_reference_status",
        "target_group_status",
        "target_relation",
        "conflict_type",
    )
    for registry_row in sorted(registry, key=lambda row: row["relation_audit_id"]):
        audit_id = registry_row["relation_audit_id"]
        candidate_id = registry_row["candidate_id"]
        left = a_by_id[audit_id]
        right = b_by_id[audit_id]
        if any(left[field] != right[field] for field in fields):
            raise RuntimeError(f"relation disagreement reached final record builder: {audit_id}")
        score = scores_by_candidate.get(candidate_id)
        main_similarity = None if score is None else float(score["main_similarity"])
        if main_similarity is not None and not math.isfinite(main_similarity):
            main_similarity = None
        final_truth = {field: left[field] for field in fields}
        output.append(
            {
                "relation_audit_id": audit_id,
                "query_family_id": registry_row["query_family_id"],
                "candidate_id": candidate_id,
                "preregistered_denominator_slot": registry_row["construction_role"],
                "final_relation_truth": final_truth,
                "main_similarity": main_similarity,
                "final_truth_source": "locked_reviewer_exact_agreement",
                "locked_a": {
                    "submission_sha256": submission_hashes["relation_a"],
                    **{field: left[field] for field in fields},
                    "reviewer_id": left["reviewer_id"],
                    "uncertain": left["uncertain"],
                },
                "locked_b": {
                    "submission_sha256": submission_hashes["relation_b"],
                    **{field: right[field] for field in fields},
                    "reviewer_id": right["reviewer_id"],
                    "uncertain": right["uncertain"],
                },
            }
        )
    return output


def build_final_similarity_records(
    registry: Sequence[Mapping[str, Any]],
    similarity_a: Sequence[Mapping[str, str]],
    similarity_b: Sequence[Mapping[str, str]],
    scores_by_candidate: Mapping[str, Mapping[str, Any]],
    *,
    submission_hashes: Mapping[str, str],
) -> list[dict[str, Any]]:
    a_by_id = {row["similarity_audit_id"]: row for row in similarity_a}
    b_by_id = {row["similarity_audit_id"]: row for row in similarity_b}
    if set(a_by_id) != set(b_by_id) or set(a_by_id) != {
        row["similarity_audit_id"] for row in registry
    }:
        raise RuntimeError("similarity registry/submission ID drift")
    output = []
    for registry_row in sorted(registry, key=lambda row: row["similarity_audit_id"]):
        audit_id = registry_row["similarity_audit_id"]
        candidate_id = registry_row["candidate_id"]
        left = a_by_id[audit_id]
        right = b_by_id[audit_id]
        if left["human_similarity_ordinal"] != right["human_similarity_ordinal"]:
            raise RuntimeError(f"similarity disagreement reached final record builder: {audit_id}")
        score = scores_by_candidate.get(candidate_id)
        if score is None:
            raise RuntimeError(f"human similarity candidate score missing: {candidate_id}")
        for key in ("main_similarity", "audit_similarity"):
            if not math.isfinite(float(score[key])):
                raise RuntimeError(f"non-finite human similarity model score: {candidate_id}:{key}")
        output.append(
            {
                "similarity_audit_id": audit_id,
                "query_family_id": registry_row["query_family_id"],
                "candidate_id": candidate_id,
                "main_similarity": float(score["main_similarity"]),
                "audit_similarity": float(score["audit_similarity"]),
                "length_stratum": registry_row["length_stratum_preregistered"],
                "final_human_similarity_ordinal": int(left["human_similarity_ordinal"]),
                "final_score_source": "locked_reviewer_exact_agreement",
                "locked_a": {
                    "submission_sha256": submission_hashes["similarity_a"],
                    "human_similarity_ordinal": int(left["human_similarity_ordinal"]),
                    "confidence": left["confidence"],
                    "uncertain": left["uncertain"],
                },
                "locked_b": {
                    "submission_sha256": submission_hashes["similarity_b"],
                    "human_similarity_ordinal": int(right["human_similarity_ordinal"]),
                    "confidence": right["confidence"],
                    "uncertain": right["uncertain"],
                },
            }
        )
    return output


def support_summary(
    rows: Sequence[Mapping[str, Any]],
    *,
    denominator_each_relation: int,
) -> dict[str, Any]:
    by_slot = {
        relation: [row for row in rows if row["preregistered_denominator_slot"] == relation]
        for relation in RELATIONS
    }
    counts = {relation: len(by_slot[relation]) for relation in RELATIONS}
    if any(count != denominator_each_relation for count in counts.values()):
        raise RuntimeError(
            f"fixed denominator slot drift: expected {denominator_each_relation}, observed {counts}"
        )
    observed: dict[str, list[float]] = {}
    diagnostics = {}
    for relation in RELATIONS:
        matched = [
            row
            for row in by_slot[relation]
            if row["final_relation_truth"]["target_reference_status"] == "valid"
            and row["final_relation_truth"]["target_group_status"] == "unique"
            and row["final_relation_truth"]["target_relation"] == relation
            and row.get("main_similarity") is not None
            and math.isfinite(float(row["main_similarity"]))
        ]
        observed[relation] = [float(row["main_similarity"]) for row in matched]
        diagnostics[relation] = {
            "fixed_denominator": denominator_each_relation,
            "formally_valid_score_count": len(matched),
            "miss_count_before_support_interval": denominator_each_relation - len(matched),
        }

    interval: list[float] | None = None
    if all(observed[relation] for relation in RELATIONS):
        low = max(min(observed[relation]) for relation in RELATIONS)
        high = min(max(observed[relation]) for relation in RELATIONS)
        if low < high:
            interval = [low, high]
    hits = {}
    coverage = {}
    for relation in RELATIONS:
        hits[relation] = (
            0
            if interval is None
            else sum(interval[0] <= value <= interval[1] for value in observed[relation])
        )
        coverage[relation] = hits[relation] / denominator_each_relation
        diagnostics[relation]["common_support_hit_count"] = hits[relation]
        diagnostics[relation]["total_miss_count"] = denominator_each_relation - hits[relation]
    passed = interval is not None and all(
        coverage[relation] >= MINIMUM_COVERAGE for relation in RELATIONS
    )
    return {
        "rule": "intersection_of_relation_specific_observed_min_max_ranges",
        "interval_inclusive": interval,
        "minimum_coverage_each_relation": MINIMUM_COVERAGE,
        "fixed_denominator_each_relation": denominator_each_relation,
        "hit_count_by_relation": hits,
        "coverage_by_relation": coverage,
        "diagnostics": diagnostics,
        "automatic_coverage_pass": passed,
    }


def numeric_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    eligible = [
        row
        for row in rows
        if row["final_relation_truth"]["target_reference_status"] == "valid"
        and row["final_relation_truth"]["target_group_status"] == "unique"
        and row["final_relation_truth"]["target_relation"]
        == row["preregistered_denominator_slot"]
        and row.get("main_similarity") is not None
        and math.isfinite(float(row["main_similarity"]))
    ]
    values = [float(row["main_similarity"]) for row in eligible]
    if len(values) < 2:
        raise RuntimeError("formal numeric summary needs at least two eligible scores")
    standard_deviation = float(np.std(values, ddof=1))
    if not math.isfinite(standard_deviation) or standard_deviation <= 0:
        raise RuntimeError("formal numeric standard deviation is invalid")

    def quantile(q: float) -> float:
        return float(np.quantile(np.asarray(values, dtype=np.float64), q, method="linear"))

    q20, q25, q30 = quantile(0.20), quantile(0.25), quantile(0.30)
    q70, q75, q80 = quantile(0.70), quantile(0.75), quantile(0.80)
    return {
        "eligible_candidate_count": len(values),
        "standardization": {
            "mean": float(np.mean(values)),
            "standard_deviation": standard_deviation,
            "ddof": 1,
        },
        "bands": {
            "rule": "pooled_formally_valid_equivalent_and_conflict_candidates_q25_q75",
            "low_max_inclusive": q25,
            "high_min_inclusive": q75,
            "ambiguous_interval": [q25, q75],
        },
        "adjacent_sensitivity_boundaries": [
            {
                "name": "wider_high_low",
                "low_max_inclusive": q30,
                "high_min_inclusive": q70,
            },
            {
                "name": "narrower_high_low",
                "low_max_inclusive": q20,
                "high_min_inclusive": q80,
            },
        ],
    }


def human_validity_summary(
    final_rows: Sequence[Mapping[str, Any]],
    a: Mapping[str, Mapping[str, str]],
    b: Mapping[str, Mapping[str, str]],
    *,
    high_min_inclusive: float,
    scope: str,
) -> dict[str, Any]:
    final_ids = [row["similarity_audit_id"] for row in final_rows]
    if (
        set(a) != set(b)
        or len(a) != len(final_rows)
        or len(final_ids) != len(set(final_ids))
        or set(final_ids) != set(a)
    ):
        raise RuntimeError(f"human validity row/ID drift: {scope}")
    inter = inter_reviewer_summary(a, b)
    human_scores = [float(row["final_human_similarity_ordinal"]) for row in final_rows]
    main_scores = [float(row["main_similarity"]) for row in final_rows]
    audit_scores = [float(row["audit_similarity"]) for row in final_rows]
    main_overall = spearman(main_scores, human_scores)
    audit_overall = spearman(audit_scores, human_scores)
    main_by_length = {}
    for length in ("short", "long"):
        subset = [row for row in final_rows if row["length_stratum"] == length]
        main_by_length[length] = spearman(
            [float(row["main_similarity"]) for row in subset],
            [float(row["final_human_similarity_ordinal"]) for row in subset],
        )
    high_scores = [
        int(row["final_human_similarity_ordinal"])
        for row in final_rows
        if float(row["main_similarity"]) >= high_min_inclusive
    ]
    high_median = float(np.median(high_scores)) if high_scores else math.nan
    high_ge4 = (
        sum(score >= 4 for score in high_scores) / len(high_scores)
        if high_scores
        else math.nan
    )

    def threshold(value: float, minimum: float) -> dict[str, Any]:
        return {
            "value": value,
            "minimum": minimum,
            "pass": math.isfinite(value) and value >= minimum,
        }

    thresholds = {
        "main_spearman_overall": threshold(main_overall, 0.50),
        "main_spearman_short": threshold(main_by_length["short"], 0.30),
        "main_spearman_long": threshold(main_by_length["long"], 0.30),
        "audit_spearman_overall": threshold(audit_overall, 0.40),
        "highest_main_band_human_median": threshold(high_median, 4.0),
        "highest_main_band_score_ge4_fraction": threshold(high_ge4, 0.70),
    }
    all_thresholds_pass = all(item["pass"] for item in thresholds.values())
    if (math.isfinite(main_overall) and main_overall <= 0) or (
        math.isfinite(high_median) and high_median <= 3
    ):
        decision = "FAIL"
    elif all_thresholds_pass and inter["inter_reviewer_gate_pass"]:
        decision = "PASS"
    else:
        decision = "INCONCLUSIVE"
    return {
        "scope": scope,
        "sample_size": len(final_rows),
        "highest_main_band_boundary": high_min_inclusive,
        "highest_main_band_sample_size": len(high_scores),
        "inter_reviewer": inter,
        "thresholds": thresholds,
        "all_human_thresholds_pass": all_thresholds_pass,
        "human_measurement_decision": decision,
    }


def terminal_decision(
    *,
    combined_support_pass: bool,
    supplement_human_decision: str,
    combined_human_decision: str,
) -> str:
    human = (supplement_human_decision, combined_human_decision)
    if "FAIL" in human:
        return "FAIL"
    if combined_support_pass and human == ("PASS", "PASS"):
        return "PASS"
    return "INCONCLUSIVE"
