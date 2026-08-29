"""Fail-closed primitives for the preregistered R2 similarity measurement."""

from __future__ import annotations

import hashlib
import math
import random
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from linkrag_eval.robust_fusion.r2_measurement_power_v2 import (
    DATASET_CELL_QUOTAS,
    DATASETS,
    LENGTH_LANGUAGES,
    RELATIONS,
    design_gates,
    measurement_statistics,
    stratified_family_bootstrap_lower,
)
from linkrag_eval.robust_fusion.similarity import cosine_float64

RESEARCH_ID = "ROBUST-FUSION-R2-2026-08-29"
RECORD_ID = "ROBUST-FUSION-RESEARCH-R2-2026-08-29-v1"
RUN_ID = "robust-fusion-r2-measurement-v1-20260829"
MAIN_ENCODER = "intfloat/multilingual-e5-base@d128750597153bb5987e10b1c3493a34e5a4502a"
AUDIT_ENCODER = (
    "sentence-transformers/distiluse-base-multilingual-cased-v2@"
    "bfe45d0732ca50787611c0fe107ba278c7f3f889"
)
CONFLICT_TYPES = (
    "numeric",
    "version_time",
    "negation_direction",
    "applicability_condition",
)
REQUIRED_FAMILY_FIELDS = {
    "family_id",
    "dataset_role",
    "language",
    "length_stratum",
    "conflict_type",
    "edit_level",
    "query",
    "reference",
    "equivalent_candidate",
    "factual_conflict_candidate",
    "provenance_id",
    "source_record_sha256",
}


def normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def text_sha256(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def template_signature(text: str) -> str:
    normalized = normalize_text(text)
    normalized = re.sub(r"\d+(?:[./:-]\d+)*", "<num>", normalized)
    normalized = re.sub(r"\b[a-z]+\d+(?:\.\d+)*\b", "<version>", normalized)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def character_ngrams(text: str, size: int = 5) -> set[str]:
    normalized = re.sub(r"\s+", "", normalize_text(text))
    if len(normalized) <= size:
        return {normalized}
    return {normalized[index : index + size] for index in range(len(normalized) - size + 1)}


def jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return 1.0 if not union else len(left & right) / len(union)


def family_key(row: Mapping[str, Any]) -> str:
    parts = [
        normalize_text(str(row["query"])),
        normalize_text(str(row["reference"])),
        str(row["provenance_id"]),
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def validate_family_frame(
    rows: Sequence[Mapping[str, Any]], exclusion_registry: Mapping[str, Any]
) -> dict[str, Any]:
    if len(rows) != 128:
        raise RuntimeError("R2 fixed family denominator must be exactly 128")
    identifiers: set[str] = set()
    keys: set[str] = set()
    text_hashes: set[str] = set()
    template_hashes: set[str] = set()
    cell_counts = Counter()
    conflict_edit_counts = Counter()
    exclusion_keys = set(exclusion_registry["family_keys"])
    exclusion_texts = set(exclusion_registry["text_sha256"])
    exclusion_templates = set(exclusion_registry["template_sha256"])
    exclusion_ngrams = [set(value) for value in exclusion_registry["near_duplicate_ngrams"]]

    for row_number, row in enumerate(rows, 1):
        if set(row) != REQUIRED_FAMILY_FIELDS:
            raise RuntimeError(f"R2 family schema drift at row {row_number}")
        identifier = str(row["family_id"])
        if not identifier or identifier in identifiers:
            raise RuntimeError(f"missing/duplicate R2 family_id: {identifier}")
        identifiers.add(identifier)
        dataset = str(row["dataset_role"])
        language = str(row["language"])
        length = str(row["length_stratum"])
        if (
            dataset not in DATASETS
            or language not in {"zh", "en"}
            or length not in {"short", "long"}
        ):
            raise RuntimeError(f"invalid frozen stratum at row {row_number}")
        conflict = str(row["conflict_type"])
        edit_level = int(row["edit_level"])
        if conflict not in CONFLICT_TYPES or edit_level not in {1, 2, 3, 4}:
            raise RuntimeError(f"invalid conflict/edit stratum at row {row_number}")
        key = family_key(row)
        if key in keys or key in exclusion_keys:
            raise RuntimeError(f"R1/R2 family-key collision: {identifier}")
        keys.add(key)
        cell_counts[(dataset, f"{length}_{language}")] += 1
        conflict_edit_counts[(f"{length}_{language}", conflict, edit_level)] += 1
        for field in ("query", "reference", "equivalent_candidate", "factual_conflict_candidate"):
            value = str(row[field])
            if not value.strip():
                raise RuntimeError(f"empty R2 text: {identifier}/{field}")
            digest = text_sha256(value)
            signature = template_signature(value)
            grams = character_ngrams(value)
            if digest in exclusion_texts or signature in exclusion_templates:
                raise RuntimeError(f"R1 text/template collision: {identifier}/{field}")
            if any(jaccard(grams, previous) >= 0.82 for previous in exclusion_ngrams):
                raise RuntimeError(f"R1 near-duplicate collision: {identifier}/{field}")
            text_hashes.add(digest)
            template_hashes.add(signature)
    expected_cells = {
        (dataset, length_language): quota
        for dataset, quotas in DATASET_CELL_QUOTAS.items()
        for length_language, quota in zip(LENGTH_LANGUAGES, quotas, strict=True)
    }
    if dict(cell_counts) != expected_cells:
        raise RuntimeError("R2 dataset×length×language quota drift")
    for length_language in LENGTH_LANGUAGES:
        if (
            sum(
                count
                for (cell, _conflict, _edit), count in conflict_edit_counts.items()
                if cell == length_language
            )
            != 32
        ):
            raise RuntimeError(f"R2 length×language denominator drift: {length_language}")
        for conflict in CONFLICT_TYPES:
            counts = [
                conflict_edit_counts[(length_language, conflict, edit)] for edit in range(1, 5)
            ]
            if counts != [2, 2, 2, 2]:
                raise RuntimeError(f"R2 conflict quota drift: {length_language}/{conflict}")
    return {
        "families": len(rows),
        "candidates": len(rows) * 2,
        "family_keys_sha256": hashlib.sha256("\n".join(sorted(keys)).encode()).hexdigest(),
        "text_hashes_sha256": hashlib.sha256("\n".join(sorted(text_hashes)).encode()).hexdigest(),
        "template_hashes_sha256": hashlib.sha256(
            "\n".join(sorted(template_hashes)).encode()
        ).hexdigest(),
    }


def build_candidate_rows(families: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for family in families:
        base = {
            "family_id": str(family["family_id"]),
            "dataset": str(family["dataset_role"]),
            "length_language": f"{family['length_stratum']}_{family['language']}",
            "condition_cell": (
                f"{family['dataset_role']}__{family['length_stratum']}_{family['language']}"
            ),
            "query": str(family["query"]),
            "reference": str(family["reference"]),
        }
        for suffix, field in (
            ("A", "equivalent_candidate"),
            ("B", "factual_conflict_candidate"),
        ):
            output.append(
                {
                    **base,
                    "candidate_id": f"{family['family_id']}::{suffix}",
                    "candidate": str(family[field]),
                }
            )
    if len(output) != 256 or len({row["candidate_id"] for row in output}) != 256:
        raise RuntimeError("R2 candidate materialization denominator drift")
    return output


def build_blind_package_rows(
    candidates: Sequence[Mapping[str, Any]], *, reviewer: str, task: str
) -> list[dict[str, Any]]:
    if reviewer not in {"A", "B"} or task not in {"relation", "similarity"}:
        raise ValueError("invalid reviewer/task")
    if len(candidates) != 256:
        raise RuntimeError("blind package fixed denominator must be 256")
    seed = int.from_bytes(hashlib.sha256(f"R2::{reviewer}::{task}".encode()).digest()[:8])
    order = list(range(len(candidates)))
    random.Random(seed).shuffle(order)
    rows = []
    for ordinal, index in enumerate(order, 1):
        source = candidates[index]
        common = {
            "audit_id": f"R2-{task.upper()}-{ordinal:03d}",
            "candidate_id": source["candidate_id"],
            "query": source["query"],
            "reference": source["reference"],
            "candidate": source["candidate"],
        }
        if task == "relation":
            common.update(
                {
                    "valid_reference": "",
                    "unique_target_group": "",
                    "target_relation": "",
                    "conflict_type": "",
                    "uncertain": "",
                    "notes": "",
                }
            )
        else:
            common.update({"similarity_1_to_7": "", "uncertain": "", "notes": ""})
        rows.append(common)
    forbidden = {"construction_role", "e5", "distiluse", "similarity_band", "target_relation"}
    if task == "similarity" and any(forbidden & set(row) for row in rows):
        raise RuntimeError("similarity package leaked answer/model fields")
    return rows


def score_candidate_vectors(
    candidates: Sequence[Mapping[str, Any]],
    *,
    candidate_vectors: Mapping[str, Sequence[float]],
    reference_vectors: Mapping[str, Sequence[Sequence[float]]],
) -> list[dict[str, Any]]:
    output = []
    for row in candidates:
        candidate_id = str(row["candidate_id"])
        family_id = str(row["family_id"])
        vector = candidate_vectors.get(candidate_id)
        references = reference_vectors.get(family_id)
        if vector is None or not references:
            raise RuntimeError(f"missing candidate/reference vector: {candidate_id}")
        values = [cosine_float64(vector, reference) for reference in references]
        if not values or any(not math.isfinite(value) for value in values):
            raise RuntimeError(f"invalid similarity inputs: {candidate_id}")
        output.append({"candidate_id": candidate_id, "similarity": max(values)})
    return output


def similarity_agreement(reviewer_a: Sequence[int], reviewer_b: Sequence[int]) -> dict[str, float]:
    if len(reviewer_a) != 256 or len(reviewer_b) != 256:
        raise RuntimeError("similarity agreement fixed denominator must be 256")
    if any(score not in range(1, 8) for score in (*reviewer_a, *reviewer_b)):
        raise RuntimeError("similarity agreement score outside 1..7")
    observed = [[0 for _ in range(7)] for _ in range(7)]
    for left, right in zip(reviewer_a, reviewer_b, strict=True):
        observed[left - 1][right - 1] += 1
    left_counts = [sum(row) for row in observed]
    right_counts = [sum(observed[row][column] for row in range(7)) for column in range(7)]
    observed_weighted = sum(
        ((row - column) ** 2 / 36) * observed[row][column]
        for row in range(7)
        for column in range(7)
    )
    expected_weighted = sum(
        ((row - column) ** 2 / 36) * left_counts[row] * right_counts[column] / 256
        for row in range(7)
        for column in range(7)
    )
    qwk = (
        1.0
        if expected_weighted == 0 and observed_weighted == 0
        else (float("nan") if expected_weighted == 0 else 1 - observed_weighted / expected_weighted)
    )
    within_one = sum(abs(left - right) <= 1 for left, right in zip(reviewer_a, reviewer_b)) / 256
    return {
        "quadratic_weighted_kappa": qwk,
        "within_one_fraction": within_one,
        "pass": float(qwk >= 0.60 and within_one >= 0.90),
    }


def finalize_measurement(
    rows: Sequence[Mapping[str, Any]], *, seed: int = 2026082911, bootstrap_iterations: int = 9999
) -> dict[str, Any]:
    if len(rows) != 256:
        raise RuntimeError("R2 final fixed candidate denominator must be exactly 256")
    required = {
        "family_id",
        "dataset",
        "length_language",
        "condition_cell",
        "relation",
        "human_score",
        "e5",
        "relation_valid",
        "similarity_valid",
    }
    if any(not required.issubset(row) for row in rows):
        raise RuntimeError("R2 final row schema incomplete")
    invalid = [
        row
        for row in rows
        if not row["relation_valid"]
        or not row["similarity_valid"]
        or row["relation"] not in RELATIONS
        or not isinstance(row["human_score"], int)
        or not 1 <= int(row["human_score"]) <= 7
        or not math.isfinite(float(row["e5"]))
    ]
    if invalid:
        return {
            "status": "R2_MEASUREMENT_FAIL_TERMINAL",
            "reason": "missing_or_invalid_fixed_denominator_rows",
            "invalid_rows": len(invalid),
        }
    statistics = measurement_statistics(rows)
    if not statistics["estimable"]:
        return {"status": "R2_MEASUREMENT_INCONCLUSIVE_TERMINAL", "reason": "not_estimable"}
    import numpy as np

    lower, valid_bootstraps = stratified_family_bootstrap_lower(
        rows, rng=np.random.default_rng(seed), iterations=bootstrap_iterations
    )
    design = design_gates(rows)
    rho = float(statistics["pooled_spearman"])
    tau = float(statistics["pooled_kendall_tau_b"])
    hard_pass = {
        "spearman_point": rho >= 0.50,
        "spearman_lower": lower is not None and lower > 0.30,
        "kendall_point": tau >= 0.35,
        "directions": all(
            value is not None and value > 0
            for key in ("length_language_directions", "relation_directions")
            for value in statistics[key].values()
        ),
        "leave_one_stability": all(
            value is not None and rho - value <= 0.15
            for value in statistics["leave_one_length_language_out"].values()
        ),
        "caliper": bool(design["caliper_pass"]),
        "resolution": bool(design["resolution_pass"]),
        "common_support": bool(design["common_support"]["all_4_length_language_aggregates_pass"]),
        "bootstrap_complete": valid_bootstraps >= math.ceil(bootstrap_iterations * 0.99),
    }
    status = (
        "R2_MEASUREMENT_PASS_AWAITING_READINESS"
        if all(hard_pass.values())
        else "R2_MEASUREMENT_FAIL_TERMINAL"
        if any(
            not hard_pass[key]
            for key in ("spearman_point", "kendall_point", "caliper", "common_support")
        )
        else "R2_MEASUREMENT_INCONCLUSIVE_TERMINAL"
    )
    return {
        "status": status,
        "fixed_denominator": 256,
        "pooled_spearman": rho,
        "spearman_one_sided_95_lower": lower,
        "pooled_kendall_tau_b": tau,
        "valid_bootstrap_iterations": valid_bootstraps,
        "hard_gates": hard_pass,
        "statistics": statistics,
        "design_gates": design,
        "distiluse_role": "sensitivity_only_no_alternative_pass",
    }
