"""Corrected R2 power simulation with orthogonal conflict/edit allocation.

V1 remains immutable but is invalid for preregistration because conflict type
and edit level were inadvertently coupled. This module changes only the
synthetic frame allocation; all estimands and thresholds are inherited.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

import numpy as np

from linkrag_eval.robust_fusion.r2_measurement_power import (
    DATASET_CELL_QUOTAS,
    DATASETS,
    LENGTH_LANGUAGES,
    RELATIONS,
    design_gates,
    measurement_statistics,
    pooled_spearman,
    stratified_family_bootstrap_lower,
)

CONFLICT_TYPES = (
    "numeric",
    "version_time",
    "negation_direction",
    "applicability_condition",
)


def build_frame() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    family_ordinal = 0
    for cell_index, length_language in enumerate(LENGTH_LANGUAGES):
        combinations = [
            (conflict_type, edit_level)
            for conflict_type in CONFLICT_TYPES
            for edit_level in range(1, 5)
            for _replicate in range(2)
        ]
        combination_index = 0
        for dataset in DATASETS:
            quota = DATASET_CELL_QUOTAS[dataset][cell_index]
            for _within_cell in range(quota):
                conflict_type, edit_level = combinations[combination_index]
                family_id = f"SIM2-F{family_ordinal + 1:03d}"
                for relation in RELATIONS:
                    rows.append(
                        {
                            "family_id": family_id,
                            "dataset": dataset,
                            "length_language": length_language,
                            "condition_cell": f"{dataset}__{length_language}",
                            "relation": relation,
                            "conflict_type": conflict_type,
                            "edit_level": edit_level,
                        }
                    )
                family_ordinal += 1
                combination_index += 1
        if combination_index != 32:
            raise AssertionError("each length×language cell must contain 32 families")
    if family_ordinal != 128 or len(rows) != 256:
        raise AssertionError("fixed R2 simulation frame must be 128 families/256 rows")
    return rows


def _base_human_score(edit_level: int, relation: str) -> int:
    equivalent = {1: 7, 2: 6, 3: 5, 4: 4}[edit_level]
    return equivalent if relation == "equivalent" else max(4, equivalent - 1)


def simulate_dataset(
    *, rng: np.random.Generator, noise_sd: float, rater_noise_sd: float
) -> list[dict[str, Any]]:
    rows = build_frame()
    family_effects = {
        family_id: float(rng.normal(0, 0.15))
        for family_id in {str(row["family_id"]) for row in rows}
    }
    cell_parameters = {
        cell: (float(rng.normal(0, 0.7)), float(rng.uniform(0.65, 1.45)))
        for cell in {str(row["condition_cell"]) for row in rows}
    }
    for row in rows:
        latent_human = _base_human_score(int(row["edit_level"]), str(row["relation"]))
        observed = int(np.clip(np.rint(latent_human + rng.normal(0, rater_noise_sd)), 1, 7))
        row["human_score"] = observed
        shift, scale = cell_parameters[str(row["condition_cell"])]
        row["e5"] = shift + scale * (
            (observed - 4.0)
            + family_effects[str(row["family_id"])]
            + float(rng.normal(0, noise_sd))
        )
    return rows


def calibrate_noise(
    *, target_rho: float, seed: int, rater_noise_sd: float, repetitions: int = 60
) -> dict[str, float]:
    low, high = 0.02, 8.0
    achieved = 0.0
    for step in range(24):
        midpoint = (low + high) / 2
        values = []
        for repetition in range(repetitions):
            rows = simulate_dataset(
                rng=np.random.default_rng(seed + step * 1000 + repetition),
                noise_sd=midpoint,
                rater_noise_sd=rater_noise_sd,
            )
            statistic = pooled_spearman(rows)
            if statistic is None:
                raise AssertionError("synthetic calibration frame became non-estimable")
            values.append(statistic)
        achieved = float(np.mean(values))
        if achieved > target_rho:
            low = midpoint
        else:
            high = midpoint
    return {"noise_sd": (low + high) / 2, "calibration_mean_rho": achieved}


def run_power_simulation(config: Mapping[str, Any]) -> dict[str, Any]:
    outer_iterations = int(config["outer_iterations"])
    bootstrap_iterations = int(config["bootstrap_iterations"])
    seed = int(config["seed"])
    rater_noise_sd = float(config["rater_noise_sd"])
    gates = config["gates"]
    scenario_results: list[dict[str, Any]] = []
    for scenario_index, target_rho in enumerate(config["target_rhos"]):
        calibration = calibrate_noise(
            target_rho=float(target_rho),
            seed=seed + scenario_index * 100_000,
            rater_noise_sd=rater_noise_sd,
        )
        pass_counts = defaultdict(int)
        observed_rhos: list[float] = []
        observed_taus: list[float] = []
        valid_lower_bounds: list[float] = []
        for iteration in range(outer_iterations):
            rng = np.random.default_rng(seed + scenario_index * 1_000_000 + iteration)
            rows = simulate_dataset(
                rng=rng,
                noise_sd=float(calibration["noise_sd"]),
                rater_noise_sd=rater_noise_sd,
            )
            statistics = measurement_statistics(rows)
            design = design_gates(rows)
            rho = float(statistics["pooled_spearman"])
            tau = float(statistics["pooled_kendall_tau_b"])
            lower, valid_bootstraps = stratified_family_bootstrap_lower(
                rows,
                rng=np.random.default_rng(
                    seed + 50_000_000 + scenario_index * 1_000_000 + iteration
                ),
                iterations=bootstrap_iterations,
            )
            observed_rhos.append(rho)
            observed_taus.append(tau)
            if lower is not None:
                valid_lower_bounds.append(lower)
            checks = {
                "point": rho >= float(gates["spearman_point_minimum"]),
                "lower": lower is not None and lower > float(gates["spearman_lower_minimum"]),
                "kendall": tau >= float(gates["kendall_point_minimum"]),
                "direction": all(
                    value is not None and value > 0
                    for key in ("length_language_directions", "relation_directions")
                    for value in statistics[key].values()
                ),
                "stability": all(
                    value is not None and rho - value <= float(gates["max_leave_one_cell_drop"])
                    for value in statistics["leave_one_length_language_out"].values()
                ),
                "caliper": bool(design["caliper_pass"]),
                "resolution": bool(design["resolution_pass"]),
                "support": bool(design["common_support"]["all_4_length_language_aggregates_pass"]),
                "valid_bootstrap": valid_bootstraps >= bootstrap_iterations * 0.90,
            }
            for name, passed in checks.items():
                pass_counts[name] += int(passed)
            pass_counts["full"] += int(all(checks.values()))
        probabilities = {
            name: count / outer_iterations for name, count in sorted(pass_counts.items())
        }
        scenario_results.append(
            {
                "target_population_rho": float(target_rho),
                "calibration": calibration,
                "outer_iterations": outer_iterations,
                "observed_pooled_spearman_mean": float(np.mean(observed_rhos)),
                "observed_pooled_spearman_sd": float(np.std(observed_rhos, ddof=1)),
                "observed_pooled_kendall_mean": float(np.mean(observed_taus)),
                "bootstrap_lower_mean": float(np.mean(valid_lower_bounds)),
                "pass_probabilities": probabilities,
                "monte_carlo_se_full": math.sqrt(
                    probabilities["full"] * (1 - probabilities["full"]) / outer_iterations
                ),
            }
        )
    return {
        "status": "POWER_SIMULATION_V2_COMPLETE_SYNTHETIC_ONLY",
        "v1_disposition": "INVALID_FOR_PREREGISTRATION_FRAME_ALLOCATION_BUG",
        "frame": {
            "families": 128,
            "candidate_rows": 256,
            "condition_cells": 12,
            "dataset_cell_quotas": DATASET_CELL_QUOTAS,
            "conflict_edit_allocation": "each length×language: 4 conflict×4 edit×2",
        },
        "estimand": {
            "standardization": "within dataset×length×language, ddof=1",
            "pooling": "three dataset statistics arithmetic mean",
            "bootstrap": "family-clustered, stratified within 12 cells, recompute standardization",
        },
        "config": dict(config),
        "scenarios": scenario_results,
    }
