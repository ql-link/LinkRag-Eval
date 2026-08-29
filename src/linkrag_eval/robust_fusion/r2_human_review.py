"""Fail-closed parsing, comparison, and assembly for R2 human submissions."""

from __future__ import annotations

import csv
import hashlib
import io
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from linkrag_eval.robust_fusion.r2_measurement import (
    finalize_measurement,
    similarity_agreement,
)
from linkrag_eval.robust_fusion.r2_measurement_power_v2 import (
    design_gates,
    measurement_statistics,
)

EXECUTOR_ID = "ROBUST-FUSION-R2-HUMAN-REVIEW-FINALIZATION-2026-08-29-v1"
RELATION_FIELDS = (
    "audit_id",
    "valid_reference",
    "unique_target_group",
    "target_relation",
    "conflict_type",
    "uncertain",
    "notes",
)
SIMILARITY_FIELDS = ("audit_id", "similarity_1_to_7", "uncertain", "notes")
RELATION_COMPARE_FIELDS = (
    "valid_reference",
    "unique_target_group",
    "target_relation",
    "conflict_type",
)
CONFLICT_TYPES = {
    "numeric",
    "version_time",
    "negation_direction",
    "applicability_condition",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def parse_csv_bytes(value: bytes, fields: Sequence[str]) -> list[dict[str, str]]:
    try:
        text = value.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise RuntimeError("submission is not UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if tuple(reader.fieldnames or ()) != tuple(fields):
        raise RuntimeError("submission header mismatch")
    rows = list(reader)
    if reader.restkey is not None or any(None in row for row in rows):
        raise RuntimeError("submission contains extra columns")
    return rows


def _require_exact_scalar(value: str, *, field: str, audit_id: str) -> None:
    if value != value.strip():
        raise RuntimeError(f"submission whitespace drift: {audit_id}/{field}")


def validate_relation_rows(
    rows: Sequence[Mapping[str, str]], expected_ids: set[str]
) -> list[dict[str, str]]:
    if len(rows) != 256:
        raise RuntimeError("relation submission fixed denominator must be 256")
    identifiers = [str(row["audit_id"]) for row in rows]
    if len(set(identifiers)) != 256 or set(identifiers) != expected_ids:
        raise RuntimeError("relation audit IDs missing, extra, or duplicated")
    output: list[dict[str, str]] = []
    for source in rows:
        row = {field: str(source[field]) for field in RELATION_FIELDS}
        audit_id = row["audit_id"]
        for field in RELATION_FIELDS:
            _require_exact_scalar(row[field], field=field, audit_id=audit_id)
        if row["valid_reference"] not in {"yes", "no"}:
            raise RuntimeError(f"invalid valid_reference enum: {audit_id}")
        if row["unique_target_group"] not in {"yes", "no"}:
            raise RuntimeError(f"invalid unique_target_group enum: {audit_id}")
        if row["target_relation"] not in {"equivalent", "factual_conflict"}:
            raise RuntimeError(f"invalid target_relation enum: {audit_id}")
        if row["target_relation"] == "equivalent" and row["conflict_type"]:
            raise RuntimeError(f"equivalent relation requires blank conflict_type: {audit_id}")
        if (
            row["target_relation"] == "factual_conflict"
            and row["conflict_type"] not in CONFLICT_TYPES
        ):
            raise RuntimeError(f"factual conflict requires frozen conflict_type: {audit_id}")
        if row["uncertain"] not in {"yes", "no"}:
            raise RuntimeError(f"invalid uncertain enum: {audit_id}")
        if row["uncertain"] == "yes" and not row["notes"]:
            raise RuntimeError(f"uncertain relation requires notes: {audit_id}")
        output.append(row)
    return output


def validate_similarity_rows(
    rows: Sequence[Mapping[str, str]], expected_ids: set[str]
) -> list[dict[str, str]]:
    if len(rows) != 256:
        raise RuntimeError("similarity submission fixed denominator must be 256")
    identifiers = [str(row["audit_id"]) for row in rows]
    if len(set(identifiers)) != 256 or set(identifiers) != expected_ids:
        raise RuntimeError("similarity audit IDs missing, extra, or duplicated")
    output: list[dict[str, str]] = []
    for source in rows:
        row = {field: str(source[field]) for field in SIMILARITY_FIELDS}
        audit_id = row["audit_id"]
        for field in SIMILARITY_FIELDS:
            _require_exact_scalar(row[field], field=field, audit_id=audit_id)
        if row["similarity_1_to_7"] not in {str(value) for value in range(1, 8)}:
            raise RuntimeError(f"invalid similarity score: {audit_id}")
        if row["uncertain"] not in {"yes", "no"}:
            raise RuntimeError(f"invalid uncertain enum: {audit_id}")
        if row["uncertain"] == "yes" and not row["notes"]:
            raise RuntimeError(f"uncertain similarity requires notes: {audit_id}")
        output.append(row)
    return output


def validate_registry(
    registry: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str], dict[str, dict[str, Any]]]:
    if len(registry) != 1024:
        raise RuntimeError("blind registry fixed denominator must be 1024")
    expected_keys = {
        "audit_id",
        "reviewer",
        "task",
        "candidate_id",
        "family_id",
        "package_ordinal",
    }
    audit_ids: set[str] = set()
    packages: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    counts = Counter()
    for source in registry:
        if set(source) != expected_keys:
            raise RuntimeError("blind registry schema drift")
        row = dict(source)
        audit_id = str(row["audit_id"])
        reviewer = str(row["reviewer"])
        task = str(row["task"])
        candidate_id = str(row["candidate_id"])
        if reviewer not in {"A", "B"} or task not in {"relation", "similarity"}:
            raise RuntimeError("blind registry reviewer/task drift")
        if audit_id in audit_ids:
            raise RuntimeError("blind registry audit IDs are not physically isolated")
        audit_ids.add(audit_id)
        key = (reviewer, task)
        packages.setdefault(key, {})[audit_id] = row
        counts[(candidate_id, reviewer, task)] += 1
        if str(row["family_id"]) != candidate_id.split("::", 1)[0]:
            raise RuntimeError("blind registry family/candidate identity drift")
    candidate_ids = {str(row["candidate_id"]) for row in registry}
    if len(candidate_ids) != 256:
        raise RuntimeError("blind registry candidate denominator drift")
    if any(counts[(candidate, reviewer, task)] != 1 for candidate in candidate_ids for reviewer in ("A", "B") for task in ("relation", "similarity")):
        raise RuntimeError("blind registry candidate coverage drift")
    if set(packages) != {
        ("A", "relation"),
        ("B", "relation"),
        ("A", "similarity"),
        ("B", "similarity"),
    } or any(len(rows) != 256 for rows in packages.values()):
        raise RuntimeError("blind registry package denominator drift")
    return packages


def compare_submissions(
    *,
    registry_packages: Mapping[tuple[str, str], Mapping[str, Mapping[str, Any]]],
    relation_a: Sequence[Mapping[str, str]],
    relation_b: Sequence[Mapping[str, str]],
    similarity_a: Sequence[Mapping[str, str]],
    similarity_b: Sequence[Mapping[str, str]],
    family_strata: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    submissions = {
        ("A", "relation"): {str(row["audit_id"]): dict(row) for row in relation_a},
        ("B", "relation"): {str(row["audit_id"]): dict(row) for row in relation_b},
        ("A", "similarity"): {str(row["audit_id"]): dict(row) for row in similarity_a},
        ("B", "similarity"): {str(row["audit_id"]): dict(row) for row in similarity_b},
    }
    for key, rows in submissions.items():
        if set(rows) != set(registry_packages[key]):
            raise RuntimeError(f"submission/registry ID drift: {key}")
    by_candidate: dict[str, dict[tuple[str, str], tuple[dict[str, Any], dict[str, str]]]] = {}
    for key, registry in registry_packages.items():
        for audit_id, registry_row in registry.items():
            candidate_id = str(registry_row["candidate_id"])
            by_candidate.setdefault(candidate_id, {})[key] = (
                dict(registry_row),
                submissions[key][audit_id],
            )
    if len(by_candidate) != 256 or any(len(value) != 4 for value in by_candidate.values()):
        raise RuntimeError("candidate submission coverage drift")

    relation_cases = []
    similarity_cases = []
    relation_field_matches = Counter()
    relation_exact = 0
    similarity_exact = 0
    similarity_within_one = 0
    similarity_a_ordered = []
    similarity_b_ordered = []
    strata = Counter()
    final_human = []
    for candidate_id in sorted(by_candidate):
        entries = by_candidate[candidate_id]
        relation_a_registry, rel_a = entries[("A", "relation")]
        _relation_b_registry, rel_b = entries[("B", "relation")]
        _similarity_a_registry, sim_a = entries[("A", "similarity")]
        _similarity_b_registry, sim_b = entries[("B", "similarity")]
        family_id = str(relation_a_registry["family_id"])
        if any(str(row[0]["family_id"]) != family_id for row in entries.values()):
            raise RuntimeError("cross-package family identity drift")
        metadata = dict(family_strata[family_id])
        relation_diff_fields = [
            field for field in RELATION_COMPARE_FIELDS if rel_a[field] != rel_b[field]
        ]
        relation_uncertain = rel_a["uncertain"] == "yes" or rel_b["uncertain"] == "yes"
        for field in RELATION_COMPARE_FIELDS:
            relation_field_matches[field] += int(rel_a[field] == rel_b[field])
        if not relation_diff_fields:
            relation_exact += 1
        if relation_diff_fields or relation_uncertain:
            relation_cases.append(
                {
                    "candidate_id": candidate_id,
                    "family_id": family_id,
                    "audit_id_a": rel_a["audit_id"],
                    "audit_id_b": rel_b["audit_id"],
                    "differing_fields": relation_diff_fields,
                    "uncertain_a": rel_a["uncertain"],
                    "uncertain_b": rel_b["uncertain"],
                    "reviewer_a": {field: rel_a[field] for field in RELATION_COMPARE_FIELDS},
                    "reviewer_b": {field: rel_b[field] for field in RELATION_COMPARE_FIELDS},
                    "strata": metadata,
                }
            )
            strata[("relation", metadata["dataset_role"], metadata["length_language"])] += 1

        score_a = int(sim_a["similarity_1_to_7"])
        score_b = int(sim_b["similarity_1_to_7"])
        similarity_a_ordered.append(score_a)
        similarity_b_ordered.append(score_b)
        similarity_exact += int(score_a == score_b)
        similarity_within_one += int(abs(score_a - score_b) <= 1)
        similarity_uncertain = sim_a["uncertain"] == "yes" or sim_b["uncertain"] == "yes"
        if score_a != score_b or similarity_uncertain:
            similarity_cases.append(
                {
                    "candidate_id": candidate_id,
                    "family_id": family_id,
                    "audit_id_a": sim_a["audit_id"],
                    "audit_id_b": sim_b["audit_id"],
                    "score_a": score_a,
                    "score_b": score_b,
                    "absolute_difference": abs(score_a - score_b),
                    "uncertain_a": sim_a["uncertain"],
                    "uncertain_b": sim_b["uncertain"],
                    "strata": metadata,
                }
            )
            strata[("similarity", metadata["dataset_role"], metadata["length_language"])] += 1
        final_human.append(
            {
                "candidate_id": candidate_id,
                "family_id": family_id,
                "relation_a": rel_a,
                "relation_b": rel_b,
                "similarity_a": sim_a,
                "similarity_b": sim_b,
            }
        )
    agreement = similarity_agreement(similarity_a_ordered, similarity_b_ordered)
    return {
        "status": (
            "VALIDATED_ZERO_ADJUDICATION_READY_FOR_FINALIZER"
            if not relation_cases and not similarity_cases
            else "AWAITING_HUMAN_ADJUDICATION"
        ),
        "fixed_candidate_denominator": 256,
        "relation": {
            "exact_all_four_fields": relation_exact,
            "field_exact_counts": dict(sorted(relation_field_matches.items())),
            "uncertain_candidates": sum(
                1
                for row in relation_cases
                if row["uncertain_a"] == "yes" or row["uncertain_b"] == "yes"
            ),
            "adjudication_count": len(relation_cases),
        },
        "similarity": {
            "exact_score_count": similarity_exact,
            "within_one_count": similarity_within_one,
            "uncertain_candidates": sum(
                1
                for row in similarity_cases
                if row["uncertain_a"] == "yes" or row["uncertain_b"] == "yes"
            ),
            "adjudication_count": len(similarity_cases),
            **agreement,
        },
        "adjudication_count_unique_candidates": len(
            {row["candidate_id"] for row in relation_cases + similarity_cases}
        ),
        "adjudication_strata": [
            {
                "task": key[0],
                "dataset_role": key[1],
                "length_language": key[2],
                "count": count,
            }
            for key, count in sorted(strata.items())
        ],
        "relation_cases": relation_cases,
        "similarity_cases": similarity_cases,
        "final_human": final_human,
    }


def build_zero_adjudication_rows(
    comparison: Mapping[str, Any],
    automatic_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if comparison["status"] != "VALIDATED_ZERO_ADJUDICATION_READY_FOR_FINALIZER":
        raise RuntimeError("zero-adjudication finalizer requires empty adjudication sets")
    if comparison["relation"]["adjudication_count"] or comparison["similarity"]["adjudication_count"]:
        raise RuntimeError("zero-adjudication finalizer cannot auto-resolve differences")
    automatic = {str(row["candidate_id"]): dict(row) for row in automatic_rows}
    if len(automatic) != 256:
        raise RuntimeError("automatic candidate denominator drift")
    rows = []
    for record in comparison["final_human"]:
        candidate_id = str(record["candidate_id"])
        rel_a = record["relation_a"]
        rel_b = record["relation_b"]
        sim_a = record["similarity_a"]
        sim_b = record["similarity_b"]
        if any(rel_a[field] != rel_b[field] for field in RELATION_COMPARE_FIELDS):
            raise RuntimeError("relation difference cannot be auto-adjudicated")
        if sim_a["similarity_1_to_7"] != sim_b["similarity_1_to_7"]:
            raise RuntimeError("similarity difference cannot be auto-adjudicated")
        if "yes" in {rel_a["uncertain"], rel_b["uncertain"], sim_a["uncertain"], sim_b["uncertain"]}:
            raise RuntimeError("uncertain value cannot be auto-adjudicated")
        auto = automatic[candidate_id]
        rows.append(
            {
                "candidate_id": candidate_id,
                "family_id": str(record["family_id"]),
                "dataset": str(auto["dataset_role"]),
                "length_language": str(auto["length_language"]),
                "condition_cell": str(auto["condition_cell"]),
                "relation": rel_a["target_relation"],
                "human_score": int(sim_a["similarity_1_to_7"]),
                "e5": float(auto["main_similarity"]),
                "distiluse": float(auto["audit_similarity"]),
                "relation_valid": (
                    rel_a["valid_reference"] == "yes"
                    and rel_a["unique_target_group"] == "yes"
                ),
                "similarity_valid": True,
                "human_provenance": {
                    "relation_audit_id_a": rel_a["audit_id"],
                    "relation_audit_id_b": rel_b["audit_id"],
                    "relation_value_a": {
                        field: rel_a[field] for field in RELATION_COMPARE_FIELDS
                    },
                    "relation_value_b": {
                        field: rel_b[field] for field in RELATION_COMPARE_FIELDS
                    },
                    "similarity_audit_id_a": sim_a["audit_id"],
                    "similarity_audit_id_b": sim_b["audit_id"],
                    "similarity_value_a": int(sim_a["similarity_1_to_7"]),
                    "similarity_value_b": int(sim_b["similarity_1_to_7"]),
                },
            }
        )
    if len(rows) != 256 or len({row["candidate_id"] for row in rows}) != 256:
        raise RuntimeError("final human fixed denominator drift")
    return rows


def final_measurement_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result = finalize_measurement(rows, seed=2026082911, bootstrap_iterations=9999)
    sensitivity_rows = [{**row, "e5": row["distiluse"]} for row in rows]
    sensitivity: dict[str, Any]
    if any(
        not row["relation_valid"]
        or not row["similarity_valid"]
        or not math.isfinite(float(row["distiluse"]))
        for row in rows
    ):
        sensitivity = {"status": "NOT_ESTIMABLE_INVALID_FIXED_DENOMINATOR"}
    else:
        sensitivity = {
            "status": "SENSITIVITY_ONLY_NO_ALTERNATIVE_PASS",
            "statistics": measurement_statistics(sensitivity_rows),
            "design_gates": design_gates(sensitivity_rows),
        }
    return {
        "executor_id": EXECUTOR_ID,
        "formal": result,
        "distiluse_sensitivity": sensitivity,
        "readiness_run": False,
        "gate_a_run": False,
        "blind_read": False,
    }
