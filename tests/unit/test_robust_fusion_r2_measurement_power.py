from __future__ import annotations

import numpy as np
import pytest

from linkrag_eval.robust_fusion.r2_measurement_power import (
    DATASET_CELL_QUOTAS,
    build_frame,
    design_gates,
    measurement_statistics,
    run_power_simulation,
    simulate_dataset,
    stratified_family_bootstrap_lower,
)


def test_fixed_frame_has_128_families_256_rows_and_12_cells() -> None:
    rows = build_frame()
    assert len(rows) == 256
    assert len({row["family_id"] for row in rows}) == 128
    assert len({row["condition_cell"] for row in rows}) == 12
    assert sum(sum(quotas) for quotas in DATASET_CELL_QUOTAS.values()) == 128
    assert all(
        len([row for row in rows if row["family_id"] == family_id]) == 2
        for family_id in {row["family_id"] for row in rows}
    )


def test_condition_standardization_removes_cell_shift_and_scale() -> None:
    rows = build_frame()
    for index, row in enumerate(rows):
        row["human_score"] = 4 + row["edit_level"]
        row["e5"] = row["human_score"] * (1 + index % 3) + (index % 7) * 100
    # Arbitrary per-row shifts destroy the relationship, but the statistic remains bounded.
    result = measurement_statistics(rows)
    assert result["estimable"] is True
    assert -1 <= result["pooled_spearman"] <= 1


def test_caliper_floor_four_allows_four_categories_and_floor_five_did_not() -> None:
    rows = build_frame()
    for row in rows:
        row["human_score"] = 8 - int(row["edit_level"])
        if row["relation"] == "factual_conflict":
            row["human_score"] = max(4, row["human_score"] - 1)
        row["e5"] = float(row["human_score"])
    gates = design_gates(rows)
    assert gates["caliper_pass"] is True
    assert gates["resolution_pass"] is True
    assert min(row["human_score"] for row in rows) == 4
    assert len({row["human_score"] for row in rows}) == 4


def test_cluster_bootstrap_is_deterministic() -> None:
    rows = simulate_dataset(rng=np.random.default_rng(7), noise_sd=0.8, rater_noise_sd=0.25)
    first = stratified_family_bootstrap_lower(
        rows, rng=np.random.default_rng(19), iterations=39
    )
    second = stratified_family_bootstrap_lower(
        rows, rng=np.random.default_rng(19), iterations=39
    )
    assert first == second
    assert first[0] is not None
    assert first[1] == 39


def test_missing_cell_or_constant_encoder_fails_closed() -> None:
    rows = build_frame()
    for row in rows:
        row["human_score"] = 5
        row["e5"] = 1.0
    assert measurement_statistics(rows) == {"estimable": False}


@pytest.mark.parametrize("target", [0.30, 0.60])
def test_small_power_simulation_is_deterministic_and_synthetic(target: float) -> None:
    config = {
        "seed": 11029,
        "outer_iterations": 2,
        "bootstrap_iterations": 19,
        "rater_noise_sd": 0.35,
        "target_rhos": [target],
        "gates": {
            "spearman_point_minimum": 0.50,
            "spearman_lower_minimum": 0.30,
            "kendall_point_minimum": 0.35,
            "max_leave_one_cell_drop": 0.15,
        },
    }
    first = run_power_simulation(config)
    second = run_power_simulation(config)
    assert first == second
    assert first["frame"]["families"] == 128
    assert first["status"] == "POWER_SIMULATION_COMPLETE_SYNTHETIC_ONLY"
