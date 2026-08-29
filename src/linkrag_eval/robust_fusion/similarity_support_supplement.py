"""Preregistered primitives for the one allowed Dev similarity supplement.

The supplement is an intent-to-calibrate design.  All 72 new paired families
remain in the denominator: malformed, missing, or relation-invalid items count
as misses rather than disappearing from the common-support calculation.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from linkrag_eval.robust_fusion.similarity_dev_calibration import canonical_json

SUPPLEMENT_VERSION = "ROBUST-FUSION-SIMILARITY-SUPPORT-SUPPLEMENT-2026-08-29-v1"
SUPPLEMENT_RUN_ID = "internal-v6-dev-similarity-support-supplement-v1-20260829"
V1_RUN_ID = "internal-v6-dev-similarity-calibration-v1-20260829"
V1_FAMILY_COUNT = 28
V1_EQUIVALENT_HITS = 5
V1_CONFLICT_HITS = 16
SUPPLEMENT_FAMILY_COUNT = 72
COMBINED_FAMILY_COUNT = 100
MINIMUM_COVERAGE = 0.60
PLANNING_SUCCESS_PROBABILITY = 0.80
TARGET_ATTAINMENT_PROBABILITY = 0.80
CONFLICT_TYPES = (
    "version_or_time",
    "numeric",
    "negation_or_direction",
    "applicability_or_condition",
)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def binomial_tail_probability(n: int, minimum_successes: int, p: float) -> float:
    return sum(
        math.comb(n, successes)
        * p**successes
        * (1.0 - p) ** (n - successes)
        for successes in range(minimum_successes, n + 1)
    )


def support_requirements(new_family_count: int) -> dict[str, int]:
    combined_denominator = V1_FAMILY_COUNT + new_family_count
    combined_hits_required = math.ceil(MINIMUM_COVERAGE * combined_denominator)
    return {
        "new_family_count": new_family_count,
        "combined_denominator_each_relation": combined_denominator,
        "combined_hits_required_each_relation": combined_hits_required,
        "new_equivalent_hits_required": combined_hits_required - V1_EQUIVALENT_HITS,
        "new_conflict_hits_required": combined_hits_required - V1_CONFLICT_HITS,
    }


def attainment_probability(new_family_count: int, p: float) -> dict[str, float]:
    requirements = support_requirements(new_family_count)
    equivalent = binomial_tail_probability(
        new_family_count, requirements["new_equivalent_hits_required"], p
    )
    conflict = binomial_tail_probability(
        new_family_count, requirements["new_conflict_hits_required"], p
    )
    return {
        "equivalent": equivalent,
        "factual_conflict": conflict,
        "both_independence_diagnostic": equivalent * conflict,
        "both_bonferroni_lower_bound": max(0.0, equivalent + conflict - 1.0),
    }


def fixed_sample_size_design() -> dict[str, Any]:
    lower_bound = next(
        n
        for n in range(1, SUPPLEMENT_FAMILY_COUNT + 1)
        if V1_EQUIVALENT_HITS + n
        >= math.ceil(MINIMUM_COVERAGE * (V1_FAMILY_COUNT + n))
    )
    eligible = []
    for n in range(lower_bound, SUPPLEMENT_FAMILY_COUNT + 1):
        probability = attainment_probability(n, PLANNING_SUCCESS_PROBABILITY)
        if probability["both_bonferroni_lower_bound"] >= TARGET_ATTAINMENT_PROBABILITY:
            eligible.append(n)
    if eligible != [SUPPLEMENT_FAMILY_COUNT]:
        raise RuntimeError(f"fixed-sample derivation drift: {eligible}")
    requirements = support_requirements(SUPPLEMENT_FAMILY_COUNT)
    sensitivity = {
        f"p={p:.2f}": attainment_probability(SUPPLEMENT_FAMILY_COUNT, p)
        for p in (0.75, 0.80, 0.85, 0.90)
    }
    return {
        "v1_fixed_counts": {
            "families_per_relation": V1_FAMILY_COUNT,
            "equivalent_common_support_hits": V1_EQUIVALENT_HITS,
            "factual_conflict_common_support_hits": V1_CONFLICT_HITS,
        },
        "mathematical_all_hit_lower_bound_new_paired_families": lower_bound,
        "planning_success_definition": (
            "a new family succeeds on a relation only if its formal relation review is valid, "
            "its score is present, and that candidate lies in the final combined common-support interval"
        ),
        "planning_success_probability": PLANNING_SUCCESS_PROBABILITY,
        "target_joint_attainment_probability_lower_bound": TARGET_ATTAINMENT_PROBABILITY,
        "joint_probability_method": (
            "Bonferroni lower bound P(E and C) >= P(E)+P(C)-1; no independence assumption"
        ),
        "selected_fixed_new_paired_families": SUPPLEMENT_FAMILY_COUNT,
        "selected_is_first_n_meeting_target_within_cap": True,
        "total_dev_query_families_after_supplement": COMBINED_FAMILY_COUNT,
        "total_dev_query_family_cap": 100,
        "requirements": requirements,
        "selected_attainment_probability": attainment_probability(
            SUPPLEMENT_FAMILY_COUNT, PLANNING_SUCCESS_PROBABILITY
        ),
        "sensitivity": sensitivity,
        "interpretation": (
            "The 0.80 planning rate is a design alternative, not an observed guarantee. "
            "At p=0.75 the cap is underpowered; thresholds are not lowered and no third cycle is allowed."
        ),
    }


def _long_context(family_id: str, language: str) -> str:
    if language == "zh":
        sentence = (
            f"{family_id}仅用于本次开发校准；附录逐项说明记录编号、录入顺序、复核日期、"
            "字段定义、单位口径和归档流程，这些背景句不改变开头陈述的唯一事实槽。"
        )
    else:
        sentence = (
            f"{family_id} is used only for this Dev calibration. The appendix repeats the record "
            "identifier, entry order, review date, field definition, unit convention, and archive "
            "procedure; none of these background details changes the single fact stated first."
        )
    return " " + " ".join(sentence for _ in range(7))


def _family_texts(
    conflict_type: str, index: int, family_id: str, language: str, length: str
) -> dict[str, str]:
    entity = f"CAL-{conflict_type[:3].upper()}-{index + 1:02d}"
    suffix = _long_context(family_id, language) if length == "long" else ""
    if conflict_type == "numeric":
        correct, incorrect = str(20 + index), str(23 + index)
        if language == "zh":
            query = f"校准登记表中，设备 {entity} 在标准模式下的认证续航是多少小时？"
            reference = f"封存登记表确认，设备 {entity} 在标准模式下的认证续航为 {correct} 小时。"
            template = f"按照封存登记表，设备 {entity} 在标准模式下的认证续航是 {{VALUE}} 小时。"
        else:
            query = f"What is the certified standby duration of {entity} in standard mode?"
            reference = f"The sealed registry certifies {entity} for {correct} hours in standard mode."
            template = f"According to the sealed registry, {entity} has a certified standby duration of {{VALUE}} hours in standard mode."
    elif conflict_type == "version_or_time":
        correct, incorrect = f"2024-{(index % 9) + 1:02d}-15", f"2025-{(index % 9) + 1:02d}-15"
        if language == "zh":
            query = f"校准登记表中，规程 {entity} 的生效日期是哪一天？"
            reference = f"封存登记表记载，规程 {entity} 的生效日期为 {correct}。"
            template = f"按照封存登记表，规程 {entity} 的生效日期是 {{VALUE}}。"
        else:
            query = f"On what date does procedure {entity} take effect?"
            reference = f"The sealed registry records {correct} as the effective date of procedure {entity}."
            template = f"According to the sealed registry, procedure {entity} takes effect on {{VALUE}}."
    elif conflict_type == "negation_or_direction":
        correct, incorrect = ("enabled", "disabled") if index % 2 == 0 else ("disabled", "enabled")
        if language == "zh":
            zh = {"enabled": "启用", "disabled": "停用"}
            correct, incorrect = zh[correct], zh[incorrect]
            query = f"校准登记表中，控制项 {entity} 在维护模式下是什么状态？"
            reference = f"封存登记表确认，控制项 {entity} 在维护模式下处于{correct}状态。"
            template = f"按照封存登记表，控制项 {entity} 在维护模式下处于{{VALUE}}状态。"
        else:
            query = f"What is the state of control {entity} in maintenance mode?"
            reference = f"The sealed registry confirms that control {entity} is {correct} in maintenance mode."
            template = f"According to the sealed registry, control {entity} is {{VALUE}} in maintenance mode."
    else:
        correct, incorrect = ("North zone", "South zone") if index % 2 == 0 else ("South zone", "North zone")
        if language == "zh":
            zh = {"North zone": "北区", "South zone": "南区"}
            correct, incorrect = zh[correct], zh[incorrect]
            query = f"校准登记表中，条款 {entity} 适用于哪个区域？"
            reference = f"封存登记表确认，条款 {entity} 仅适用于{correct}。"
            template = f"按照封存登记表，条款 {entity} 仅适用于{{VALUE}}。"
        else:
            query = f"Which region is covered by clause {entity}?"
            reference = f"The sealed registry confirms that clause {entity} applies only to the {correct}."
            template = f"According to the sealed registry, clause {entity} applies only to the {{VALUE}}."
    return {
        "query": query,
        "reference": reference + suffix,
        "candidate_template": template + suffix,
        "correct_value": correct,
        "incorrect_value": incorrect,
    }


def generate_paired_families() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ordinal = 0
    for conflict_type_index, conflict_type in enumerate(CONFLICT_TYPES):
        for index in range(18):
            ordinal += 1
            family_id = f"RF-SIM-SUP-F{ordinal:03d}"
            length = "short" if index < 9 else "long"
            language = "zh" if (index + conflict_type_index) % 2 == 0 else "en"
            texts = _family_texts(conflict_type, index, family_id, language, length)
            equivalent = texts["candidate_template"].replace(
                "{VALUE}", texts["correct_value"]
            )
            conflict = texts["candidate_template"].replace(
                "{VALUE}", texts["incorrect_value"]
            )
            rows.append(
                {
                    "query_family_id": family_id,
                    "query_id": f"{family_id}-Q",
                    "target_equivalence_group_id": f"{family_id}-G",
                    "reference_id": f"{family_id}-R",
                    "equivalent_candidate_id": f"{family_id}-C1",
                    "conflict_candidate_id": f"{family_id}-C2",
                    "query_origin": "deterministic_synthetic_microfact_dev_only",
                    "language": language,
                    "length_stratum_preregistered": length,
                    "conflict_type_preregistered": conflict_type,
                    "query": texts["query"],
                    "reference": texts["reference"],
                    "equivalent_candidate": equivalent,
                    "factual_conflict_candidate": conflict,
                    "candidate_surface_template_sha256": sha256_text(
                        texts["candidate_template"]
                    ),
                    "correct_value_sha256": sha256_text(texts["correct_value"]),
                    "incorrect_value_sha256": sha256_text(texts["incorrect_value"]),
                    "query_sha256": sha256_text(texts["query"]),
                    "reference_sha256": sha256_text(texts["reference"]),
                    "equivalent_candidate_sha256": sha256_text(equivalent),
                    "factual_conflict_candidate_sha256": sha256_text(conflict),
                }
            )
    validate_paired_families(rows)
    return rows


def validate_paired_families(rows: Sequence[Mapping[str, Any]]) -> None:
    if len(rows) != SUPPLEMENT_FAMILY_COUNT:
        raise RuntimeError("supplement must contain exactly 72 paired families")
    family_ids = [str(row.get("query_family_id", "")) for row in rows]
    if len(set(family_ids)) != len(family_ids) or any(not value for value in family_ids):
        raise RuntimeError("empty or duplicate supplement family ID")
    if any("gatea" in value.lower() or "blind" in value.lower() for value in family_ids):
        raise RuntimeError("confirmatory namespace leaked into Dev supplement")
    counts = Counter(
        (str(row["conflict_type_preregistered"]), str(row["length_stratum_preregistered"]))
        for row in rows
    )
    expected = {(conflict, length): 9 for conflict in CONFLICT_TYPES for length in ("short", "long")}
    if counts != expected:
        raise RuntimeError(f"supplement strata drift: {counts}")
    if Counter(str(row["language"]) for row in rows) != {"en": 36, "zh": 36}:
        raise RuntimeError("supplement language balance drift")
    content_hashes: set[str] = set()
    for row in rows:
        equivalent = str(row["equivalent_candidate"])
        conflict = str(row["factual_conflict_candidate"])
        if equivalent == conflict:
            raise RuntimeError(f"paired candidates are identical: {row['query_family_id']}")
        for field in ("query", "reference", "equivalent_candidate", "factual_conflict_candidate"):
            value = str(row[field])
            if not value.strip() or sha256_text(value) != row[f"{field}_sha256"]:
                raise RuntimeError(f"content/hash drift: {row['query_family_id']}:{field}")
            if field != "query":
                if sha256_text(value) in content_hashes:
                    raise RuntimeError(f"duplicate content: {row['query_family_id']}:{field}")
                content_hashes.add(sha256_text(value))


def select_similarity_audit_sample(
    rows: Sequence[Mapping[str, Any]], *, per_role_length_cell: int = 12
) -> list[dict[str, Any]]:
    """Select 48 rows by frozen role/length quotas and model-gap extremes."""

    cells: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for role in ("equivalent", "factual_conflict"):
        for length in ("short", "long"):
            cells[(role, length)] = [
                row
                for row in rows
                if row["construction_role"] == role
                and row["length_stratum_preregistered"] == length
            ]
    selected: list[dict[str, Any]] = []
    for key, cell in sorted(cells.items()):
        ordered = sorted(
            cell,
            key=lambda row: (float(row["encoder_percentile_gap"]), str(row["candidate_id"])),
        )
        if len(ordered) < per_role_length_cell:
            raise RuntimeError(f"similarity audit cell too small: {key}")
        low_count = per_role_length_cell // 2
        picks = ordered[:low_count] + ordered[-(per_role_length_cell - low_count) :]
        selected.extend(dict(row) for row in picks)
    if len(selected) != 48 or len({row["candidate_id"] for row in selected}) != 48:
        raise RuntimeError("similarity audit sample is incomplete or duplicated")
    return sorted(selected, key=lambda row: str(row["candidate_id"]))


def preregistration_protocol() -> dict[str, Any]:
    return {
        "protocol_version": SUPPLEMENT_VERSION,
        "run_id": SUPPLEMENT_RUN_ID,
        "purpose": "the sole pre-Gate Dev common-support supplement for P2-01",
        "v1_disposition": {
            "status": "PERMANENT_FORMAL_INCONCLUSIVE_READ_ONLY",
            "equivalent_coverage": V1_EQUIVALENT_HITS / V1_FAMILY_COUNT,
            "factual_conflict_coverage": V1_CONFLICT_HITS / V1_FAMILY_COUNT,
            "may_overwrite_filter_or_readjudicate": False,
        },
        "population": {
            "source": "72 deterministic synthetic calibration-only microfact Query families",
            "query_family_namespace": "RF-SIM-SUP-F001..RF-SIM-SUP-F072",
            "split_role": "internal-v6-dev-only",
            "gate_a_or_blind_eligibility": False,
            "external_model_or_api_generation": False,
            "family_count": SUPPLEMENT_FAMILY_COUNT,
            "language_quota": {"zh": 36, "en": 36},
            "length_quota": {"short": 36, "long": 36},
            "conflict_type_quota": {name: 18 for name in CONFLICT_TYPES},
        },
        "paired_construction": {
            "per_family": "one unique target reference, one equivalent candidate, one factual-conflict candidate",
            "surface_matching": "the two candidates share one literal template and differ only at the single registered fact value",
            "retention": "all 72 families fixed before encoder scores; no score-based replacement, deletion, or expansion",
            "formal_relation_truth": "construction roles are not truth; two independent handbook-v2 relation reviews and arbitration establish final labels",
        },
        "estimand_and_models": {
            "estimand": "S_qg(c)=max_h_in_A_qg cosine(z(c),z(h))",
            "main": "intfloat/multilingual-e5-base@d128750597153bb5987e10b1c3493a34e5a4502a",
            "audit": "sentence-transformers/distiluse-base-multilingual-cased-v2@bfe45d0732ca50787611c0fe107ba278c7f3f889",
            "roles_exchangeable": False,
            "ddof": 1,
            "common_support": "intersection of combined relation-specific observed min/max ranges",
            "minimum_coverage_each_relation": MINIMUM_COVERAGE,
        },
        "fixed_sample_size": fixed_sample_size_design(),
        "exclusions_and_missing": {
            "post_score_exclusions": "none",
            "mechanical_duplicate_or_schema_failure": "terminal INCONCLUSIVE; no replacement",
            "invalid_or_non_unique_reference": "family is a miss on both relation denominators",
            "relation_invalid_or_unresolved_candidate": "candidate is a miss for its relation; family is not replaced",
            "missing_or_nonfinite_score": "miss for that relation",
            "fixed_denominator_each_relation": COMBINED_FAMILY_COUNT,
        },
        "combination": {
            "retain_v1": "all 28 v1 eligible equivalent and all 28 v1 eligible conflict candidates",
            "retain_supplement": "all 72 preregistered families under intent-to-calibrate missing-as-miss rules",
            "reports": ["v1", "supplement-only", "combined"],
            "formal_numeric_freeze_basis": "combined only",
            "standardization_and_bands": "combined formally valid candidate scores; ddof=1; pooled q25/q75 with q30/q70 and q20/q80 sensitivity",
        },
        "human_governance": {
            "relation_review": "A/B independently review all 144 candidate rows under handbook v2; all disagreements or uncertainty are arbitrated",
            "similarity_review": "A/B independently rate 48 opaque text pairs, 12 per construction-role x length cell, split between lowest/highest encoder percentile-gap regions",
            "scale": "same frozen 1-5 scale and thresholds as v1",
            "separation": "relation-label packages and similarity-rating packages are physically separate; model scores, bands, construction goals, and facilitator registries are hidden",
            "similarity_adjudication": "score difference >=2 or either uncertain is mandatory; every other non-exact row is also adjudicated for one final score",
            "human_validity": "supplement-only and combined v1+supplement must each pass the unchanged v1 inter-reviewer and six measurement-validity thresholds",
        },
        "unique_stop_rule": {
            "PASS": "combined common-support, supplement human validity, and combined human validity all PASS; freeze numbers once and proceed only to readiness review",
            "FAIL_OR_INCONCLUSIVE": "P2-01/P2-04 remain incomplete, Gate A remains unauthorized, and no third P2 supplement is permitted",
            "early_stopping_or_adaptive_expansion": False,
        },
        "forbidden": ["Gate A", "Gate B", "Blind read", "Reranker effect", "D1-D3", "A0", "M1"],
    }


def protocol_sha256() -> str:
    return sha256_text(canonical_json(preregistration_protocol()))
