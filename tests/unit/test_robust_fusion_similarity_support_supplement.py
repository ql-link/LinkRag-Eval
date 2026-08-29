from __future__ import annotations

import copy
from pathlib import Path

import pytest

from linkrag_eval.robust_fusion.similarity_support_supplement import (
    COMBINED_FAMILY_COUNT,
    SUPPLEMENT_FAMILY_COUNT,
    attainment_probability,
    fixed_sample_size_design,
    generate_paired_families,
    preregistration_protocol,
    select_similarity_audit_sample,
    support_requirements,
    validate_paired_families,
)
from scripts.run_robust_fusion_similarity_support_supplement import resolve_in_repo


def test_fixed_sample_size_is_first_defensible_n_within_cap() -> None:
    design = fixed_sample_size_design()
    assert design["mathematical_all_hit_lower_bound_new_paired_families"] == 30
    assert design["selected_fixed_new_paired_families"] == 72
    assert design["total_dev_query_families_after_supplement"] == 100
    assert design["selected_attainment_probability"]["both_bonferroni_lower_bound"] >= 0.80
    assert attainment_probability(71, 0.80)["both_bonferroni_lower_bound"] < 0.80
    assert support_requirements(72)["new_equivalent_hits_required"] == 55
    assert support_requirements(72)["new_conflict_hits_required"] == 44


def test_paired_generation_is_deterministic_balanced_and_surface_matched() -> None:
    first = generate_paired_families()
    second = generate_paired_families()
    assert first == second
    assert len(first) == SUPPLEMENT_FAMILY_COUNT
    assert len({row["query_family_id"] for row in first}) == 72
    assert sum(row["length_stratum_preregistered"] == "short" for row in first) == 36
    assert sum(row["length_stratum_preregistered"] == "long" for row in first) == 36
    assert sum(row["language"] == "zh" for row in first) == 36
    assert sum(row["language"] == "en" for row in first) == 36
    for row in first:
        assert row["equivalent_candidate"] != row["factual_conflict_candidate"]
        assert row["candidate_surface_template_sha256"]


def test_generation_rejects_missing_duplicates_and_confirmatory_namespace() -> None:
    rows = generate_paired_families()
    with pytest.raises(RuntimeError, match="exactly 72"):
        validate_paired_families(rows[:-1])
    duplicate = copy.deepcopy(rows)
    duplicate[1]["query_family_id"] = duplicate[0]["query_family_id"]
    with pytest.raises(RuntimeError, match="duplicate supplement family ID"):
        validate_paired_families(duplicate)
    confirmatory = copy.deepcopy(rows)
    confirmatory[0]["query_family_id"] = "BLIND-FAMILY"
    with pytest.raises(RuntimeError, match="confirmatory namespace"):
        validate_paired_families(confirmatory)


def test_preregistration_keeps_v1_and_fixed_denominators() -> None:
    protocol = preregistration_protocol()
    assert protocol["v1_disposition"]["status"] == "PERMANENT_FORMAL_INCONCLUSIVE_READ_ONLY"
    assert protocol["exclusions_and_missing"]["fixed_denominator_each_relation"] == COMBINED_FAMILY_COUNT
    assert protocol["unique_stop_rule"]["early_stopping_or_adaptive_expansion"] is False
    assert protocol["population"]["gate_a_or_blind_eligibility"] is False


def test_similarity_sample_has_frozen_role_length_quotas() -> None:
    rows = []
    for role in ("equivalent", "factual_conflict"):
        for length in ("short", "long"):
            for index in range(18):
                rows.append(
                    {
                        "candidate_id": f"{role}-{length}-{index:02d}",
                        "construction_role": role,
                        "length_stratum_preregistered": length,
                        "encoder_percentile_gap": index / 100,
                    }
                )
    sample = select_similarity_audit_sample(rows)
    assert len(sample) == 48
    for role in ("equivalent", "factual_conflict"):
        for length in ("short", "long"):
            assert sum(
                row["construction_role"] == role
                and row["length_stratum_preregistered"] == length
                for row in sample
            ) == 12


@pytest.mark.parametrize(
    "relative",
    (
        "data/robust_fusion/internal_stress_v6/gatea/input",
        "data/robust_fusion/internal_stress_v6/Gate-A/input",
        "data/robust_fusion/internal_stress_v6/blind/input",
    ),
)
def test_supplement_refuses_gate_a_and_blind_paths(relative: str) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    with pytest.raises(RuntimeError, match="refuses GateA/Blind"):
        resolve_in_repo(repo_root, Path(relative))
