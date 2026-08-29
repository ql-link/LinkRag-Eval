"""Dev-only calibration primitives for target-group similarity measurement.

This module deliberately contains no model loader.  Callers inject the two
already-qualified encoder outputs, which keeps the scientific validation and
the expensive encoding step independently testable.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from linkrag_eval.robust_fusion.similarity import (
    cosine_float64,
    normalize_similarity_text,
    vector_float32_sha256,
)

CALIBRATION_VERSION = "ROBUST-FUSION-SIMILARITY-DEV-CALIBRATION-2026-08-29-v1"
ROUTE_RUN_ID = "internal-v6-dev-route-evidence-v5-20260829"
ROUTE_MANIFEST_SHA256 = "a2ee6147a791903fa0aceae3be7f3b6a7f54277a58f5241cb62d1e944974734d"
ROUTE_CONTENT_ROOT_SHA256 = "1bae0b158a16f5d0aab161cff28245283fd487c9a5f41f23a6c4d02305c57550"
RELEASE_MANIFEST_SHA256 = "ad32fbb08a6b076dced1e438ff51060c46073b932cd259ff89beb157e5453bac"
MAIN_MODEL_ID = "intfloat/multilingual-e5-base"
MAIN_REVISION = "d128750597153bb5987e10b1c3493a34e5a4502a"
AUDIT_MODEL_ID = "sentence-transformers/distiluse-base-multilingual-cased-v2"
AUDIT_REVISION = "bfe45d0732ca50787611c0fe107ba278c7f3f889"
QUALIFICATION_SHA256 = "931946bd244d794bf390d5c37f166308d010870b429919b1167131fd0ceb1f2a"

FORBIDDEN_METHOD_KEYS = {
    "source_query_id",
    "source_chunk_id",
    "source_relevance_label",
    "target_equivalence_group_id",
    "target_relation",
    "conflict_type",
    "adjudicability",
    "review_status",
    "handbook_version",
    "query_family_id",
    "document_family_id",
    "counterfactual_template_family_id",
    "origin",
    "pool_role",
    "similarity_band",
}
RELATIONS_FOR_MEASUREMENT = {"equivalent", "factual_conflict", "other_incorrect"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            raise RuntimeError(f"blank JSONL row: {path}:{line_number}")
        value = json.loads(line)
        if not isinstance(value, dict):
            raise TypeError(f"JSONL row is not an object: {path}:{line_number}")
        rows.append(value)
    return rows


def write_json(path: Path, value: Any) -> None:
    path.write_text(canonical_json(value) + "\n", encoding="utf-8")
    path.chmod(0o600)


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(canonical_json(dict(row)) + "\n")
    path.chmod(0o600)


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def ensure_method_view_safe(rows_by_file: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
    for filename, rows in rows_by_file.items():
        for index, row in enumerate(rows, 1):
            leaked = sorted(set(_walk_keys(row)) & FORBIDDEN_METHOD_KEYS)
            if leaked:
                raise RuntimeError(f"method/evaluation view leakage: {filename}:{index}:{leaked}")


def reject_confirmatory_path(path: Path) -> None:
    tokens = {part.lower().replace("_", "-") for part in path.resolve().parts}
    if any("gatea" in token or "gate-a" in token or "blind" in token for token in tokens):
        raise RuntimeError(f"Dev calibration refuses GateA/Blind path: {path}")


def _verify_receipt(path: Path, expected: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"frozen manifest SHA-256 mismatch: {path}: {actual}")
    receipt = path.with_suffix(".sha256")
    if not receipt.is_file() or receipt.read_text(encoding="utf-8").split()[0] != actual:
        raise RuntimeError(f"manifest receipt mismatch: {receipt}")


def load_frozen_dev_inputs(route_root: Path) -> dict[str, Any]:
    """Load the one authorized Dev input while enforcing view separation."""

    reject_confirmatory_path(route_root)
    manifest_path = route_root / "manifest.json"
    _verify_receipt(manifest_path, ROUTE_MANIFEST_SHA256)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {
        "run_id": ROUTE_RUN_ID,
        "split_role": "internal-v6-dev",
        "gate_eligibility": "NOT_ELIGIBLE",
        "content_root_sha256": ROUTE_CONTENT_ROOT_SHA256,
        "input_release_manifest_sha256": RELEASE_MANIFEST_SHA256,
        "method_evaluation_views_physically_separated": True,
        "formal_p4_02_snapshot": False,
        "gate_a_executed": False,
        "gate_b_executed": False,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise RuntimeError(f"unauthorized Dev manifest field: {key}={manifest.get(key)!r}")

    recorded = {row["path"]: row for row in manifest["files"]}
    required = (
        "method_view/queries.jsonl",
        "method_view/chunks.jsonl",
        "method_view/candidates.jsonl",
        "evaluation_view/relations.jsonl",
        "evaluation_view/families.jsonl",
    )
    for relative in required:
        path = route_root / relative
        row = recorded.get(relative)
        if row is None or not path.is_file() or sha256_file(path) != row["sha256"]:
            raise RuntimeError(f"frozen Dev input missing or changed: {relative}")

    queries = read_jsonl(route_root / required[0])
    chunks = read_jsonl(route_root / required[1])
    candidates = read_jsonl(route_root / required[2])
    relations = read_jsonl(route_root / required[3])
    families = read_jsonl(route_root / required[4])
    ensure_method_view_safe(
        {"queries.jsonl": queries, "chunks.jsonl": chunks, "candidates.jsonl": candidates}
    )
    return {
        "manifest": manifest,
        "queries": queries,
        "chunks": chunks,
        "candidates": candidates,
        "relations": relations,
        "families": families,
    }


def build_reference_sets(
    chunks: Sequence[Mapping[str, Any]], relations: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Freeze A_qg from adjudicated relevant_gold rows and return scored candidates."""

    chunks_by_id: dict[str, Mapping[str, Any]] = {}
    for row in chunks:
        chunk_id = str(row.get("chunk_id", ""))
        if not chunk_id or chunk_id in chunks_by_id:
            raise RuntimeError(f"empty or duplicate method chunk_id: {chunk_id!r}")
        chunks_by_id[chunk_id] = row

    seen_pairs: set[tuple[str, str]] = set()
    by_group: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    candidate_rows: list[dict[str, Any]] = []
    for row in relations:
        query_uid = str(row.get("query_uid", ""))
        chunk_id = str(row.get("chunk_id", ""))
        group_id = str(row.get("target_equivalence_group_id", ""))
        pair = (query_uid, chunk_id)
        if not query_uid or not chunk_id or not group_id:
            raise RuntimeError("missing query/chunk/target group in evaluation view")
        if pair in seen_pairs:
            raise RuntimeError(f"duplicate evaluation relation: {pair}")
        seen_pairs.add(pair)
        if chunk_id not in chunks_by_id:
            raise RuntimeError(f"evaluation relation has missing method chunk: {pair}")
        if row.get("source_relevance_label") == "relevant_gold":
            if row.get("target_relation") != "equivalent":
                raise RuntimeError(f"reference is not equivalent: {pair}")
            by_group[(query_uid, group_id)].append(row)
        elif row.get("target_relation") in RELATIONS_FOR_MEASUREMENT:
            merged = dict(row)
            merged["content"] = chunks_by_id[chunk_id]["content"]
            merged["content_sha256"] = chunks_by_id[chunk_id]["content_sha256"]
            candidate_rows.append(merged)

    all_groups = {
        (str(row["query_uid"]), str(row["target_equivalence_group_id"]))
        for row in relations
    }
    missing = sorted(all_groups - set(by_group))
    if missing:
        raise RuntimeError(f"empty/missing A_qg reference set: {missing[:3]}")

    reference_sets: list[dict[str, Any]] = []
    for (query_uid, group_id), members in sorted(by_group.items()):
        ordered = sorted(members, key=lambda row: str(row["source_chunk_id"]).encode("utf-8"))
        member_ids = [str(row["source_chunk_id"]) for row in ordered]
        if len(member_ids) != len(set(member_ids)):
            raise RuntimeError(f"duplicate A_qg member ID: {(query_uid, group_id)}")
        reference_sets.append(
            {
                "query_uid": query_uid,
                "target_equivalence_group_id": group_id,
                "member_order_rule": "official_record_id_utf8_bytes",
                "members": [
                    {
                        "official_record_id": row["source_chunk_id"],
                        "local_chunk_id": row["chunk_id"],
                        "raw_content_sha256": chunks_by_id[str(row["chunk_id"])][
                            "content_sha256"
                        ],
                        "content": chunks_by_id[str(row["chunk_id"])]["content"],
                        "relevance_status": row["source_relevance_label"],
                        "review_status": row["review_status"],
                    }
                    for row in ordered
                ],
                "set_membership_sha256": sha256_text(canonical_json(member_ids)),
            }
        )

    reference_keys = {
        (row["query_uid"], row["target_equivalence_group_id"]) for row in reference_sets
    }
    for candidate in candidate_rows:
        key = (candidate["query_uid"], candidate["target_equivalence_group_id"])
        if key not in reference_keys:
            raise RuntimeError(f"candidate has no A_qg: {key}")
    return reference_sets, sorted(
        candidate_rows, key=lambda row: (str(row["query_uid"]), str(row["chunk_id"]))
    )


def verify_encoder_roles(main: Mapping[str, Any], audit: Mapping[str, Any]) -> None:
    if (
        main.get("role") != "main_similarity_encoder"
        or main.get("model_id") != MAIN_MODEL_ID
        or main.get("revision") != MAIN_REVISION
    ):
        raise RuntimeError("main and audit encoder roles are fixed and may not be exchanged")
    if (
        audit.get("role") != "independent_audit_encoder"
        or audit.get("model_id") != AUDIT_MODEL_ID
        or audit.get("revision") != AUDIT_REVISION
    ):
        raise RuntimeError("main and audit encoder roles are fixed and may not be exchanged")


def score_candidates(
    reference_sets: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    vectors: Mapping[str, Sequence[float]],
    *,
    expected_dim: int,
) -> list[dict[str, Any]]:
    references = {
        (row["query_uid"], row["target_equivalence_group_id"]): row
        for row in reference_sets
    }
    output: list[dict[str, Any]] = []
    for candidate in candidates:
        key = (candidate["query_uid"], candidate["target_equivalence_group_id"])
        reference = references.get(key)
        if reference is None or not reference.get("members"):
            raise RuntimeError(f"candidate has empty reference set: {key}")
        candidate_id = str(candidate["chunk_id"])
        if candidate_id not in vectors:
            raise RuntimeError(f"missing candidate vector: {candidate_id}")
        scored: list[tuple[float, str, str]] = []
        for member in reference["members"]:
            reference_id = str(member["local_chunk_id"])
            if reference_id not in vectors:
                raise RuntimeError(f"missing reference vector: {reference_id}")
            score = cosine_float64(vectors[candidate_id], vectors[reference_id])
            scored.append((score, str(member["official_record_id"]), reference_id))
        scored.sort(key=lambda item: (-item[0], item[1].encode("utf-8")))
        best, official_id, local_id = scored[0]
        output.append(
            {
                "query_uid": candidate["query_uid"],
                "target_equivalence_group_id": candidate["target_equivalence_group_id"],
                "candidate_chunk_id": candidate_id,
                "candidate_raw_content_sha256": candidate["content_sha256"],
                "candidate_normalized_input_sha256": sha256_text(
                    normalize_similarity_text(str(candidate["content"]))
                ),
                "candidate_vector_sha256": vector_float32_sha256(
                    vectors[candidate_id], expected_dim=expected_dim
                ),
                "max_cosine_similarity": best,
                "argmax_reference_id": official_id,
                "argmax_reference_local_chunk_id": local_id,
                "target_relation": candidate["target_relation"],
                "conflict_type": candidate["conflict_type"],
                "source_relevance_label": candidate["source_relevance_label"],
            }
        )
    return output


def assign_length_strata(
    rows: Sequence[dict[str, Any]], token_counts: Mapping[str, int]
) -> dict[str, Any]:
    pair_lengths = [
        max(token_counts[row["candidate_chunk_id"]], token_counts[row["argmax_reference_local_chunk_id"]])
        for row in rows
    ]
    boundary = float(np.median(np.asarray(pair_lengths, dtype=np.float64)))
    for row, length in zip(rows, pair_lengths):
        row["pair_untruncated_token_count_max"] = length
        row["length_stratum"] = "short" if length <= boundary else "long"
    counts = Counter(row["length_stratum"] for row in rows)
    if not counts["short"] or not counts["long"]:
        raise RuntimeError("length stratification did not produce both short and long strata")
    return {
        "rule": "short_if_main_encoder_pair_max_untruncated_tokens_le_pooled_median_else_long",
        "boundary_tokens": boundary,
        "counts": dict(sorted(counts.items())),
    }


def _quantile(values: Sequence[float], q: float) -> float:
    return float(np.quantile(np.asarray(values, dtype=np.float64), q, method="linear"))


def _percentile_ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: (values[index], index))
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        average = ((start + end - 1) / 2) / max(1, len(values) - 1)
        for position in range(start, end):
            ranks[order[position]] = average
        start = end
    return ranks


def build_provisional_calibration(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Apply result-before-human rules without authorizing the numeric freeze."""

    eligible = [row for row in rows if row["target_relation"] in {"equivalent", "factual_conflict"}]
    values = [float(row["main_similarity"]) for row in eligible]
    equivalent = [float(row["main_similarity"]) for row in eligible if row["target_relation"] == "equivalent"]
    conflict = [float(row["main_similarity"]) for row in eligible if row["target_relation"] == "factual_conflict"]
    if len(equivalent) < 2 or len(conflict) < 2:
        raise RuntimeError("standardization needs at least two equivalent and conflict candidates")
    mean = float(np.mean(values))
    std = float(np.std(values, ddof=1))
    if not math.isfinite(std) or std <= 0:
        raise RuntimeError("standardization standard deviation is invalid")

    # Common support is the intersection of the *observed* relation-specific
    # ranges.  Trimming each side before intersecting can manufacture an empty
    # interval in small calibration samples.  Adequacy is handled separately
    # and conservatively by the frozen coverage floor below.
    support_low = max(min(equivalent), min(conflict))
    support_high = min(max(equivalent), max(conflict))
    if support_low >= support_high:
        raise RuntimeError("equivalent/conflict common support is empty")
    coverage = {
        "equivalent": sum(support_low <= value <= support_high for value in equivalent) / len(equivalent),
        "factual_conflict": sum(support_low <= value <= support_high for value in conflict) / len(conflict),
    }
    minimum_coverage = 0.60
    support_pass = all(value >= minimum_coverage for value in coverage.values())
    # Explanatory bands describe the pooled Dev distribution.  They do not
    # repair inadequate common support; the latter remains a separate gate.
    band_values = values
    bands = {
        "low_max_inclusive": _quantile(band_values, 0.25),
        "high_min_inclusive": _quantile(band_values, 0.75),
        "ambiguous_interval": [_quantile(band_values, 0.25), _quantile(band_values, 0.75)],
    }
    return {
        "status": (
            "PROVISIONAL_NUMBERS_AWAITING_BLIND_HUMAN_VALIDITY"
            if support_pass
            else "PROVISIONAL_NUMBERS_AUTOMATIC_COMMON_SUPPORT_FAIL_AWAITING_HUMAN_VALIDITY"
        ),
        "eligible_candidate_count": len(eligible),
        "equivalent_count": len(equivalent),
        "factual_conflict_count": len(conflict),
        "standardization": {"mean": mean, "standard_deviation": std, "ddof": 1},
        "common_support": {
            "rule": "intersection_of_relation_specific_observed_min_max_ranges",
            "interval_inclusive": [support_low, support_high],
            "coverage_by_relation": coverage,
            "minimum_coverage_each_relation": minimum_coverage,
            "automatic_coverage_pass": support_pass,
        },
        "bands": {
            "rule": "pooled_eligible_equivalent_and_conflict_candidates_q25_q75",
            **bands,
            "highest_band_requires_blind_human_near_neighbor_validity": True,
        },
        "adjacent_sensitivity_boundaries": [
            {
                "name": "wider_high_low",
                "low_max_inclusive": _quantile(band_values, 0.30),
                "high_min_inclusive": _quantile(band_values, 0.70),
            },
            {
                "name": "narrower_high_low",
                "low_max_inclusive": _quantile(band_values, 0.20),
                "high_min_inclusive": _quantile(band_values, 0.80),
            },
        ],
        "formal_numeric_freeze_allowed": False,
    }


def add_model_agreement(rows: Sequence[dict[str, Any]]) -> None:
    main = [float(row["main_similarity"]) for row in rows]
    audit = [float(row["audit_similarity"]) for row in rows]
    main_rank = _percentile_ranks(main)
    audit_rank = _percentile_ranks(audit)
    gaps = [abs(left - right) for left, right in zip(main_rank, audit_rank)]
    low = _quantile(gaps, 0.25)
    high = _quantile(gaps, 0.75)
    for row, left, right, gap in zip(rows, main_rank, audit_rank, gaps):
        row["main_percentile_rank"] = left
        row["audit_percentile_rank"] = right
        row["encoder_percentile_gap"] = gap
        row["encoder_agreement_region"] = (
            "agreement" if gap <= low else "disagreement" if gap >= high else "middle"
        )


def select_blind_human_sample(rows: Sequence[dict[str, Any]], *, per_cell: int = 4) -> list[dict[str, Any]]:
    """Select 24 rows: relation x relative-length, with model-gap extremes."""

    cells: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        cells[(row["target_relation"], row["length_stratum"])].append(row)
    required = {(relation, length) for relation in RELATIONS_FOR_MEASUREMENT for length in ("short", "long")}
    if set(cells) != required:
        raise RuntimeError(f"human-audit sampling frame missing cells: {sorted(required - set(cells))}")

    selected: list[dict[str, Any]] = []
    for key in sorted(cells):
        ordered = sorted(
            cells[key],
            key=lambda row: (float(row["encoder_percentile_gap"]), str(row["candidate_chunk_id"])),
        )
        if len(ordered) < per_cell:
            raise RuntimeError(f"human-audit cell too small: {key}: {len(ordered)}")
        picks = [ordered[0], ordered[-1]]
        remaining = [row for row in ordered if row not in picks]
        while len(picks) < per_cell:
            index = 0 if len(picks) % 2 == 0 else -1
            picks.append(remaining.pop(index))
        selected.extend(picks)

    # Ensure all conflict types are represented without changing relation/length quotas.
    needed_types = {"version_or_time", "numeric", "negation_or_direction", "applicability_or_condition"}
    present = Counter(row["conflict_type"] for row in selected if row["target_relation"] == "factual_conflict")
    for missing_type in sorted(needed_types - set(present)):
        candidates = sorted(
            [
                row
                for row in rows
                if row["target_relation"] == "factual_conflict"
                and row["conflict_type"] == missing_type
                and row not in selected
            ],
            key=lambda row: (-float(row["encoder_percentile_gap"]), str(row["candidate_chunk_id"])),
        )
        replaced = False
        for incoming in candidates:
            replaceable = sorted(
                [
                    row
                    for row in selected
                    if row["target_relation"] == "factual_conflict"
                    and row["length_stratum"] == incoming["length_stratum"]
                    and present[row["conflict_type"]] > 1
                ],
                key=lambda row: (float(row["encoder_percentile_gap"]), str(row["candidate_chunk_id"])),
            )
            if replaceable:
                outgoing = replaceable[0]
                selected.remove(outgoing)
                selected.append(incoming)
                present[outgoing["conflict_type"]] -= 1
                present[missing_type] += 1
                replaced = True
                break
        if not replaced:
            raise RuntimeError(f"cannot cover conflict type in blind sample: {missing_type}")

    if len(selected) != per_cell * 6 or len({row["candidate_chunk_id"] for row in selected}) != len(selected):
        raise RuntimeError("blind human sample is not unique and complete")
    return sorted(selected, key=lambda row: str(row["candidate_chunk_id"]))


def human_audit_rules(sample_size: int) -> dict[str, Any]:
    return {
        "frozen_before_human_submissions": True,
        "sample_size_per_researcher": sample_size,
        "scale": {
            "1": "different topic/entity/fact slot; not a semantic near-neighbor",
            "2": "same broad domain but different entity or fact slot",
            "3": "same entity/topic with partial fact-slot or condition overlap",
            "4": "same fact slot and highly similar meaning, with a material factual/condition difference possible",
            "5": "near-equivalent meaning or close paraphrase",
        },
        "submission_fields": {
            "human_similarity_ordinal": [1, 2, 3, 4, 5],
            "confidence": ["high", "medium", "low"],
            "uncertain": ["yes", "no"],
            "note": "optional; required when uncertain=yes",
        },
        "mechanical_acceptance": "all rows once; legal enums; no duplicate audit_id; note required for uncertainty",
        "inter_reviewer_gate": {
            "quadratic_weighted_kappa_min": 0.60,
            "within_one_point_agreement_min": 0.90,
            "action": "if either misses, adjudicate every non-exact row and mark validity INCONCLUSIVE",
        },
        "mandatory_adjudication": "all absolute score differences >=2 or either reviewer uncertain=yes",
        "model_validity_gate_after_adjudication": {
            "main_spearman_overall_min": 0.50,
            "main_spearman_each_length_min": 0.30,
            "audit_spearman_overall_min": 0.40,
            "highest_main_band_human_median_min": 4.0,
            "highest_main_band_human_score_ge4_fraction_min": 0.70,
            "decision": {
                "PASS": "all thresholds pass and common-support automatic coverage passes",
                "FAIL": "overall main rho <=0 or highest-band median <=3",
                "INCONCLUSIVE": "all other non-passing combinations",
            },
        },
        "post_submission_rule": "lock both physical submissions before any comparison",
        "formal_band_freeze_rule": (
            "accept the already-computed provisional numbers only after PASS; on FAIL/INCONCLUSIVE "
            "do not change encoder, estimand, support rule, or boundaries from these submissions"
        ),
    }


def validate_submission(path: Path, expected_ids: set[str]) -> list[dict[str, str]]:
    fields = ["audit_id", "human_similarity_ordinal", "confidence", "uncertain", "note"]
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != fields:
            raise RuntimeError(f"submission header mismatch: {path}")
        rows = list(reader)
    ids = [row["audit_id"] for row in rows]
    if len(ids) != len(set(ids)) or set(ids) != expected_ids:
        raise RuntimeError(f"submission IDs incomplete, extra, or duplicated: {path}")
    for row in rows:
        if row["human_similarity_ordinal"] not in {"1", "2", "3", "4", "5"}:
            raise RuntimeError(f"invalid similarity score: {path}:{row['audit_id']}")
        if row["confidence"] not in {"high", "medium", "low"}:
            raise RuntimeError(f"invalid confidence: {path}:{row['audit_id']}")
        if row["uncertain"] not in {"yes", "no"}:
            raise RuntimeError(f"invalid uncertainty: {path}:{row['audit_id']}")
        if row["uncertain"] == "yes" and not row["note"].strip():
            raise RuntimeError(f"uncertainty requires note: {path}:{row['audit_id']}")
    return rows
