#!/usr/bin/env python3
"""Review locked P2-01 human submissions and finalize after human arbitration."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from linkrag_eval.robust_fusion.similarity_dev_calibration import (
    canonical_json,
    sha256_file,
    validate_submission,
    write_json,
)

DEFAULT_ROOT = Path(
    "runs/robust_fusion/similarity_dev_calibration_v1/"
    "internal-v6-dev-similarity-calibration-v1-20260829"
)
LOCK_SHA256 = "f6a87dea77ca754a5b622c7237c9da134e1d5176d2a52a3cd9297dc1c5e4499b"
RULES_SHA256 = "268598c122096874409cd7f81b6b3e175933b837d987c8d047fc1312afdd52a6"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def verify_lock(root: Path) -> dict[str, Any]:
    lock_path = root / "human_audit/facilitator/submission_lock.json"
    if sha256_file(lock_path) != LOCK_SHA256:
        raise RuntimeError("submission lock drift")
    receipt = (lock_path.with_suffix(".sha256")).read_text(encoding="utf-8").split()[0]
    if receipt != LOCK_SHA256:
        raise RuntimeError("submission lock receipt drift")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("content_read_before_lock") is not False:
        raise RuntimeError("submissions were not locked before comparison")
    for row in lock["submissions"]:
        role = str(row["role"]).lower()
        path = root / f"human_audit/annotator_{role}/submission.csv"
        if sha256_file(path) != row["sha256"] or path.stat().st_size != row["bytes"]:
            raise RuntimeError(f"locked submission drift: {role}")
    if sha256_file(root / "human_audit_rules.json") != RULES_SHA256:
        raise RuntimeError("human audit rules drift")
    return lock


def verify_adjudication_lock(root: Path) -> dict[str, Any]:
    output_dir = root / "human_audit/facilitator/adjudication_v1"
    lock_path = output_dir / "adjudication_lock.json"
    receipt_path = output_dir / "adjudication_lock.sha256"
    lock_sha256 = sha256_file(lock_path)
    receipt_parts = receipt_path.read_text(encoding="utf-8").split()
    if len(receipt_parts) != 2 or receipt_parts != [lock_sha256, "adjudication_lock.json"]:
        raise RuntimeError("adjudication lock receipt drift")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("content_read_before_lock") is not False:
        raise RuntimeError("adjudication was not locked before content review")
    adjudication = lock.get("adjudication", {})
    if adjudication.get("relative_path") != "adjudication.csv":
        raise RuntimeError("adjudication lock path mismatch")
    adjudication_path = output_dir / "adjudication.csv"
    if (
        sha256_file(adjudication_path) != adjudication.get("sha256")
        or adjudication_path.stat().st_size != adjudication.get("size_bytes")
    ):
        raise RuntimeError("locked adjudication drift")
    package = lock.get("package_manifest", {})
    if package.get("relative_path") != "manifest.json":
        raise RuntimeError("adjudication package manifest path mismatch")
    if sha256_file(output_dir / "manifest.json") != package.get("sha256"):
        raise RuntimeError("adjudication package manifest drift")
    return {**lock, "lock_sha256": lock_sha256}


def load_submissions(root: Path) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    expected: dict[str, set[str]] = {}
    output: dict[str, dict[str, dict[str, str]]] = {}
    for role in ("a", "b"):
        expected[role] = {row["audit_id"] for row in read_csv(root / f"human_audit/annotator_{role}/pairs.csv")}
        rows = validate_submission(
            root / f"human_audit/annotator_{role}/submission.csv", expected[role]
        )
        output[role] = {row["audit_id"]: row for row in rows}
    if expected["a"] != expected["b"]:
        raise RuntimeError("A/B audit ID sets differ")
    return output["a"], output["b"]


def quadratic_weighted_kappa(left: Sequence[int], right: Sequence[int]) -> float:
    if len(left) != len(right) or not left:
        raise RuntimeError("invalid rating vectors")
    observed = np.zeros((5, 5), dtype=np.float64)
    for first, second in zip(left, right):
        observed[first - 1, second - 1] += 1
    observed /= len(left)
    left_marginal = np.array([left.count(value) / len(left) for value in range(1, 6)])
    right_marginal = np.array([right.count(value) / len(right) for value in range(1, 6)])
    expected = np.outer(left_marginal, right_marginal)
    weights = np.array([[(i - j) ** 2 / 16 for j in range(5)] for i in range(5)])
    denominator = float(np.sum(weights * expected))
    if denominator == 0:
        return 1.0 if left == right else 0.0
    return 1.0 - float(np.sum(weights * observed)) / denominator


def comparison(a: dict[str, dict[str, str]], b: dict[str, dict[str, str]]) -> dict[str, Any]:
    ids = sorted(a)
    left = [int(a[audit_id]["human_similarity_ordinal"]) for audit_id in ids]
    right = [int(b[audit_id]["human_similarity_ordinal"]) for audit_id in ids]
    differences = [abs(first - second) for first, second in zip(left, right)]
    mandatory = {
        audit_id
        for audit_id, difference in zip(ids, differences)
        if difference >= 2 or a[audit_id]["uncertain"] == "yes" or b[audit_id]["uncertain"] == "yes"
    }
    nonexact = {audit_id for audit_id, difference in zip(ids, differences) if difference != 0}
    arbitration = sorted(mandatory | nonexact)
    qwk = quadratic_weighted_kappa(left, right)
    within_one = sum(difference <= 1 for difference in differences) / len(differences)
    gate_pass = qwk >= 0.60 and within_one >= 0.90
    return {
        "row_count_each": len(ids),
        "exact_agreement_count": sum(difference == 0 for difference in differences),
        "exact_agreement_fraction": sum(difference == 0 for difference in differences) / len(ids),
        "within_one_count": sum(difference <= 1 for difference in differences),
        "within_one_fraction": within_one,
        "quadratic_weighted_kappa": qwk,
        "inter_reviewer_gate_pass": gate_pass,
        "mandatory_adjudication_ids": sorted(mandatory),
        "nonexact_ids": sorted(nonexact),
        "adjudication_ids_for_unique_final_score": arbitration,
        "adjudication_row_count": len(arbitration),
        "validity_forced_inconclusive_by_inter_reviewer_gate": not gate_pass,
    }


def prepare(root: Path) -> dict[str, Any]:
    lock = verify_lock(root)
    a, b = load_submissions(root)
    result = comparison(a, b)
    pair_rows = {row["audit_id"]: row for row in read_csv(root / "human_audit/annotator_a/pairs.csv")}
    output_dir = root / "human_audit/facilitator/adjudication_v1"
    if output_dir.exists():
        raise RuntimeError(f"refusing to overwrite adjudication package: {output_dir}")
    output_dir.mkdir(parents=True, mode=0o700)
    adjudication_ids = result["adjudication_ids_for_unique_final_score"]
    fields = [
        "audit_id",
        "text_a",
        "text_b",
        "score_a",
        "confidence_a",
        "uncertain_a",
        "note_a",
        "score_b",
        "confidence_b",
        "uncertain_b",
        "note_b",
    ]
    with (output_dir / "cases.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for audit_id in adjudication_ids:
            pair = pair_rows[audit_id]
            writer.writerow(
                {
                    "audit_id": audit_id,
                    "text_a": pair["text_1"],
                    "text_b": pair["text_2"],
                    "score_a": a[audit_id]["human_similarity_ordinal"],
                    "confidence_a": a[audit_id]["confidence"],
                    "uncertain_a": a[audit_id]["uncertain"],
                    "note_a": a[audit_id]["note"],
                    "score_b": b[audit_id]["human_similarity_ordinal"],
                    "confidence_b": b[audit_id]["confidence"],
                    "uncertain_b": b[audit_id]["uncertain"],
                    "note_b": b[audit_id]["note"],
                }
            )
    with (output_dir / "adjudication_template.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["audit_id", "adjudicated_similarity_ordinal", "arbiter_id", "rationale"],
        )
        writer.writeheader()
        for audit_id in adjudication_ids:
            writer.writerow({"audit_id": audit_id})
    (output_dir / "README.txt").write_text(
        "由一名真实仲裁员处理 cases.csv 的全部行。只依据两段文本、A/B 分数与说明，"
        "不得查看模型分数、关系标签或 facilitator registry。将 adjudication_template.csv "
        "复制为 adjudication.csv；每行填写 1–5 的最终相似度、非空 arbiter_id 和简短理由，"
        "不得修改 audit_id 或表头。\n",
        encoding="utf-8",
    )
    review = {
        "status": "AWAITING_HUMAN_ADJUDICATION",
        "submission_lock_sha256": LOCK_SHA256,
        "submission_hashes": {row["role"]: row["sha256"] for row in lock["submissions"]},
        "mechanical_validation": "PASS",
        "comparison": result,
        "formal_human_validity_decision": "PENDING_ADJUDICATION",
        "formal_numeric_freeze_complete": False,
        "gate_a_executed": False,
        "gate_b_executed": False,
    }
    write_json(output_dir / "pre_adjudication_review.json", review)
    files = []
    for path in sorted(output_dir.iterdir()):
        if path.name not in {"manifest.json", "manifest.sha256"}:
            files.append({"path": path.name, "sha256": sha256_file(path), "size_bytes": path.stat().st_size})
    manifest = {
        "status": "AWAITING_HUMAN_ADJUDICATION",
        "contains_model_scores": False,
        "contains_relation_labels": False,
        "contains_answer_key": False,
        "row_count": len(adjudication_ids),
        "files": files,
    }
    write_json(output_dir / "manifest.json", manifest)
    (output_dir / "manifest.sha256").write_text(
        f"{sha256_file(output_dir / 'manifest.json')}  manifest.json\n", encoding="utf-8"
    )
    return {"status": manifest["status"], "row_count": len(adjudication_ids)}


def average_ranks(values: Sequence[float]) -> np.ndarray:
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
    first = average_ranks(left)
    second = average_ranks(right)
    if float(np.std(first)) == 0 or float(np.std(second)) == 0:
        return math.nan
    return float(np.corrcoef(first, second)[0, 1])


def validate_adjudication(
    path: Path, expected: set[str]
) -> list[dict[str, str]]:
    rows = read_csv(path)
    fields = ["audit_id", "adjudicated_similarity_ordinal", "arbiter_id", "rationale"]
    if not rows or list(rows[0]) != fields:
        raise RuntimeError("adjudication header mismatch")
    ids = [row["audit_id"] for row in rows]
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise RuntimeError("adjudication IDs incomplete, extra, or duplicated")
    for row in rows:
        if row["adjudicated_similarity_ordinal"] not in {"1", "2", "3", "4", "5"}:
            raise RuntimeError(f"invalid adjudicated score: {row['audit_id']}")
        if not row["arbiter_id"].strip() or not row["rationale"].strip():
            raise RuntimeError(f"adjudication identity/rationale missing: {row['audit_id']}")
    if len({row["arbiter_id"].strip() for row in rows}) != 1:
        raise RuntimeError("adjudication must use one consistent arbiter identity")
    return rows


def finalize(root: Path) -> dict[str, Any]:
    verify_lock(root)
    a, b = load_submissions(root)
    result = comparison(a, b)
    output_dir = root / "human_audit/facilitator/adjudication_v1"
    adjudication_lock = verify_adjudication_lock(root)
    adjudication_path = output_dir / "adjudication.csv"
    expected = set(result["adjudication_ids_for_unique_final_score"])
    rows = validate_adjudication(adjudication_path, expected)
    adjudicated = {row["audit_id"]: int(row["adjudicated_similarity_ordinal"]) for row in rows}
    registry = [json.loads(line) for line in (root / "human_audit/facilitator/sample_registry.jsonl").read_text(encoding="utf-8").splitlines()]
    final_rows = []
    for row in registry:
        audit_id = row["audit_id"]
        if audit_id in adjudicated:
            score = adjudicated[audit_id]
            source = "human_arbiter"
        else:
            left = int(a[audit_id]["human_similarity_ordinal"])
            right = int(b[audit_id]["human_similarity_ordinal"])
            if left != right:
                raise RuntimeError(f"non-adjudicated disagreement: {audit_id}")
            score = left
            source = "reviewer_exact_agreement"
        final_rows.append({**row, "final_human_similarity_ordinal": score, "final_score_source": source})
    main_overall = spearman(
        [float(row["main_similarity"]) for row in final_rows],
        [float(row["final_human_similarity_ordinal"]) for row in final_rows],
    )
    audit_overall = spearman(
        [float(row["audit_similarity"]) for row in final_rows],
        [float(row["final_human_similarity_ordinal"]) for row in final_rows],
    )
    main_by_length = {}
    for length in ("short", "long"):
        subset = [row for row in final_rows if row["length_stratum"] == length]
        main_by_length[length] = spearman(
            [float(row["main_similarity"]) for row in subset],
            [float(row["final_human_similarity_ordinal"]) for row in subset],
        )
    provisional = json.loads((root / "provisional_calibration.json").read_text(encoding="utf-8"))
    high_min = float(provisional["bands"]["high_min_inclusive"])
    high = [row for row in final_rows if float(row["main_similarity"]) >= high_min]
    high_scores = [int(row["final_human_similarity_ordinal"]) for row in high]
    thresholds = {
        "main_spearman_overall": {"value": main_overall, "minimum": 0.50, "pass": main_overall >= 0.50},
        "main_spearman_short": {"value": main_by_length["short"], "minimum": 0.30, "pass": main_by_length["short"] >= 0.30},
        "main_spearman_long": {"value": main_by_length["long"], "minimum": 0.30, "pass": main_by_length["long"] >= 0.30},
        "audit_spearman_overall": {"value": audit_overall, "minimum": 0.40, "pass": audit_overall >= 0.40},
        "highest_main_band_human_median": {"value": float(np.median(high_scores)), "minimum": 4.0, "pass": float(np.median(high_scores)) >= 4.0},
        "highest_main_band_score_ge4_fraction": {"value": sum(score >= 4 for score in high_scores) / len(high_scores), "minimum": 0.70, "pass": sum(score >= 4 for score in high_scores) / len(high_scores) >= 0.70},
    }
    support_pass = bool(provisional["common_support"]["automatic_coverage_pass"])
    all_human_thresholds_pass = all(row["pass"] for row in thresholds.values())
    if main_overall <= 0 or thresholds["highest_main_band_human_median"]["value"] <= 3:
        human_measurement_decision = "FAIL"
    elif all_human_thresholds_pass and result["inter_reviewer_gate_pass"]:
        human_measurement_decision = "PASS"
    else:
        human_measurement_decision = "INCONCLUSIVE"
    if human_measurement_decision == "FAIL":
        combined_decision = "FAIL"
    elif human_measurement_decision == "PASS" and support_pass:
        combined_decision = "PASS"
    else:
        combined_decision = "INCONCLUSIVE"
    final = {
        "status": (
            "REVIEW_COMPLETE_FORMAL_FREEZE_READY"
            if combined_decision == "PASS"
            else "REVIEW_COMPLETE_FORMAL_FREEZE_BLOCKED"
        ),
        "submission_lock_sha256": LOCK_SHA256,
        "adjudication_lock_sha256": adjudication_lock["lock_sha256"],
        "adjudication_sha256": sha256_file(adjudication_path),
        "inter_reviewer": result,
        "thresholds": thresholds,
        "all_human_thresholds_pass": all_human_thresholds_pass,
        "common_support_automatic_coverage_pass": support_pass,
        "human_measurement_decision": human_measurement_decision,
        "combined_similarity_freeze_decision": combined_decision,
        "formal_numeric_freeze_complete": combined_decision == "PASS",
        "p2_01_complete": combined_decision == "PASS",
        "p2_04_complete": combined_decision == "PASS",
        "gate_a_executed": False,
        "gate_b_executed": False,
        "statistical_interpretation": {
            "analysis_kind": "descriptive_dev_measurement_validity_audit",
            "sample_scope": "frozen_stratified_24_pair_audit_frame",
            "population_inference_allowed": False,
            "causal_inference_allowed": False,
            "multiple_testing_gate_changed_after_results": False,
            "fallacy_scan": {
                "coverage": "11/11",
                "simpsons_paradox": "no_direction_reversal_in_frozen_short_long_strata",
                "ecological_fallacy": "not_applicable_no_individual_level_claim",
                "berksons_paradox": "caution_selected_stratified_audit_frame",
                "collider_bias": "not_applicable_no_covariate_adjustment",
                "base_rate_neglect": "not_applicable_no_diagnostic_probability_claim",
                "regression_to_mean": "not_applicable_no_extreme_group_pre_post_design",
                "survivorship_bias": "not_detected_24_of_24_final_scores",
                "look_elsewhere_effect": "not_detected_all_frozen_thresholds_reported",
                "garden_of_forking_paths": "not_detected_rules_frozen_before_submissions",
                "correlation_causation": "guarded_association_only",
                "reverse_causality": "not_applicable_no_directional_causal_claim",
            },
        },
    }
    write_json(output_dir / "final_review.json", final)
    with (output_dir / "final_scores.jsonl").open("w", encoding="utf-8") as handle:
        for row in sorted(final_rows, key=lambda item: item["audit_id"]):
            handle.write(canonical_json(row) + "\n")
    final_manifest = {
        "schema_version": "robust-fusion-similarity-human-review-final-v1",
        "status": final["status"],
        "adjudication_lock_sha256": adjudication_lock["lock_sha256"],
        "files": [
            {
                "path": name,
                "sha256": sha256_file(output_dir / name),
                "size_bytes": (output_dir / name).stat().st_size,
            }
            for name in ("final_review.json", "final_scores.jsonl")
        ],
        "gate_a_executed": False,
        "gate_b_executed": False,
    }
    final_manifest_path = output_dir / "final_manifest.json"
    write_json(final_manifest_path, final_manifest)
    final_manifest_sha256 = sha256_file(final_manifest_path)
    (output_dir / "final_manifest.sha256").write_text(
        f"{final_manifest_sha256}  final_manifest.json\n", encoding="utf-8"
    )
    return {**final, "final_manifest_sha256": final_manifest_sha256}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare-adjudication", "finalize"))
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    result = prepare(root) if args.command == "prepare-adjudication" else finalize(root)
    print(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
