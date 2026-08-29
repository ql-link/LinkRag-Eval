"""Deterministic, result-before power simulation for the R2 measurement gate.

This module uses synthetic ordinal outcomes only.  It must never read R1/R2
candidate text, encoder output, human submissions, Gate A, or Blind artifacts.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from linkrag_eval.robust_fusion.r2_similarity_diagnostic import (
    kendall_tau_b,
    spearman,
)

LENGTH_LANGUAGES = ("short_zh", "long_zh", "short_en", "long_en")
DATASETS = ("public_general", "public_domain", "internal_control")
DATASET_CELL_QUOTAS = {
    "public_general": (11, 11, 11, 11),
    "public_domain": (11, 11, 10, 10),
    "internal_control": (10, 10, 11, 11),
}
RELATIONS = ("equivalent", "factual_conflict")


def build_frame() -> list[dict[str, Any]]:
    """Build the fixed 128-family/256-candidate synthetic planning frame."""
    rows: list[dict[str, Any]] = []
    family_ordinal = 0
    for dataset in DATASETS:
        for cell_index, length_language in enumerate(LENGTH_LANGUAGES):
            quota = DATASET_CELL_QUOTAS[dataset][cell_index]
            for within_cell in range(quota):
                conflict_type = (
                    "numeric",
                    "version_time",
                    "negation_direction",
                    "applicability_condition",
                )[(family_ordinal + within_cell) % 4]
                edit_level = (family_ordinal + within_cell) % 4 + 1
                family_id = f"SIM-F{family_ordinal + 1:03d}"
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
    if family_ordinal != 128 or len(rows) != 256:
        raise AssertionError("fixed R2 simulation frame must be 128 families/256 rows")
    return rows


def _standardize_by_cell(rows: Sequence[Mapping[str, Any]]) -> list[float] | None:
    output = [0.0] * len(rows)
    by_cell: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        by_cell[str(row["condition_cell"])].append(index)
    for indices in by_cell.values():
        values = np.asarray([float(rows[index]["e5"]) for index in indices])
        if len(values) < 2:
            return None
        deviation = float(np.std(values, ddof=1))
        if not math.isfinite(deviation) or deviation == 0:
            return None
        average = float(np.mean(values))
        for index in indices:
            output[index] = (float(rows[index]["e5"]) - average) / deviation
    return output


def _dataset_macro(
    rows: Sequence[Mapping[str, Any]], standardized: Sequence[float], statistic: str
) -> float | None:
    values: list[float] = []
    for dataset in DATASETS:
        indices = [index for index, row in enumerate(rows) if row["dataset"] == dataset]
        automatic = [standardized[index] for index in indices]
        human = [float(rows[index]["human_score"]) for index in indices]
        value = spearman(automatic, human) if statistic == "spearman" else kendall_tau_b(
            automatic, human
        )
        if value is None:
            return None
        values.append(value)
    return float(np.mean(values))


def pooled_spearman(rows: Sequence[Mapping[str, Any]]) -> float | None:
    """Compute only the primary statistic for bootstrap/calibration hot paths."""
    standardized = _standardize_by_cell(rows)
    return (
        None
        if standardized is None
        else _dataset_macro(rows, standardized, "spearman")
    )


def measurement_statistics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    standardized = _standardize_by_cell(rows)
    if standardized is None:
        return {"estimable": False}
    pooled_spearman = _dataset_macro(rows, standardized, "spearman")
    pooled_kendall = _dataset_macro(rows, standardized, "kendall")
    if pooled_spearman is None or pooled_kendall is None:
        return {"estimable": False}

    length_language_directions: dict[str, float | None] = {}
    for cell in LENGTH_LANGUAGES:
        indices = [
            index for index, row in enumerate(rows) if row["length_language"] == cell
        ]
        length_language_directions[cell] = spearman(
            [standardized[index] for index in indices],
            [float(rows[index]["human_score"]) for index in indices],
        )

    leave_one_out: dict[str, float | None] = {}
    for excluded in LENGTH_LANGUAGES:
        retained = [row for row in rows if row["length_language"] != excluded]
        retained_standardized = _standardize_by_cell(retained)
        leave_one_out[excluded] = (
            None
            if retained_standardized is None
            else _dataset_macro(retained, retained_standardized, "spearman")
        )

    relation_directions: dict[str, float | None] = {}
    for relation in RELATIONS:
        retained = [row for row in rows if row["relation"] == relation]
        retained_standardized = _standardize_by_cell(retained)
        relation_directions[relation] = (
            None
            if retained_standardized is None
            else _dataset_macro(retained, retained_standardized, "spearman")
        )

    return {
        "estimable": True,
        "pooled_spearman": pooled_spearman,
        "pooled_kendall_tau_b": pooled_kendall,
        "length_language_directions": length_language_directions,
        "leave_one_length_language_out": leave_one_out,
        "relation_directions": relation_directions,
    }


def common_support(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    standardized = _standardize_by_cell(rows)
    if standardized is None:
        return {"estimable": False}

    def summarize(group_key: str) -> dict[str, Any]:
        groups: dict[str, list[tuple[Mapping[str, Any], float]]] = defaultdict(list)
        for index, row in enumerate(rows):
            groups[str(row[group_key])].append((row, standardized[index]))
        details: dict[str, Any] = {}
        all_pass = True
        for cell, cell_rows in sorted(groups.items()):
            relation_values = {
                relation: [value for row, value in cell_rows if row["relation"] == relation]
                for relation in RELATIONS
            }
            lower = max(min(values) for values in relation_values.values())
            upper = min(max(values) for values in relation_values.values())
            coverage = {
                relation: sum(lower <= value <= upper for value in values) / len(values)
                if lower <= upper
                else 0.0
                for relation, values in relation_values.items()
            }
            passed = all(value >= 0.60 for value in coverage.values())
            all_pass = all_pass and passed
            details[cell] = {
                "lower": lower,
                "upper": upper,
                "coverage": coverage,
                "pass": passed,
            }
        return {"all_pass": all_pass, "groups": details}

    length_language = summarize("length_language")
    condition_cells = summarize("condition_cell")
    return {
        "estimable": True,
        "all_4_length_language_aggregates_pass": length_language["all_pass"],
        "length_language_aggregates": length_language["groups"],
        "all_12_condition_cells_pass_diagnostic": condition_cells["all_pass"],
        "condition_cells_diagnostic": condition_cells["groups"],
    }


def design_gates(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_family: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_family[str(row["family_id"])].append(row)
    family_caliper: dict[str, bool] = {}
    for family_id, family_rows in by_family.items():
        scores = [int(row["human_score"]) for row in family_rows]
        family_caliper[family_id] = min(scores) >= 4 and max(scores) - min(scores) <= 1
    overall_caliper = sum(family_caliper.values()) / 128
    cell_caliper: dict[str, float] = {}
    for cell in LENGTH_LANGUAGES:
        identifiers = {
            str(row["family_id"]) for row in rows if row["length_language"] == cell
        }
        cell_caliper[cell] = sum(family_caliper[item] for item in identifiers) / len(identifiers)

    resolution: dict[str, Any] = {}
    resolution_pass = True
    for cell in LENGTH_LANGUAGES:
        scores = [int(row["human_score"]) for row in rows if row["length_language"] == cell]
        counts = {value: scores.count(value) for value in set(scores)}
        maximum_fraction = max(counts.values()) / len(scores)
        passed = len(counts) >= 4 and maximum_fraction <= 0.60
        resolution_pass = resolution_pass and passed
        resolution[cell] = {
            "unique_categories": len(counts),
            "maximum_category_fraction": maximum_fraction,
            "pass": passed,
        }
    support = common_support(rows)
    return {
        "caliper_overall": overall_caliper,
        "caliper_by_length_language": cell_caliper,
        "caliper_pass": overall_caliper >= 0.80
        and all(value >= 0.75 for value in cell_caliper.values()),
        "resolution": resolution,
        "resolution_pass": resolution_pass,
        "common_support": support,
    }


def stratified_family_bootstrap_lower(
    rows: Sequence[Mapping[str, Any]], *, rng: np.random.Generator, iterations: int
) -> tuple[float | None, int]:
    families: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    cell_families: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        family_id = str(row["family_id"])
        families[family_id].append(row)
    for family_id, family_rows in families.items():
        cell_families[str(family_rows[0]["condition_cell"])].append(family_id)
    values: list[float] = []
    for _ in range(iterations):
        sampled_rows: list[dict[str, Any]] = []
        draw_ordinal = 0
        for cell in sorted(cell_families):
            identifiers = sorted(cell_families[cell])
            for sampled_index in rng.integers(0, len(identifiers), size=len(identifiers)):
                source_id = identifiers[int(sampled_index)]
                for row in families[source_id]:
                    copied = dict(row)
                    copied["family_id"] = f"BOOT-{draw_ordinal:03d}"
                    sampled_rows.append(copied)
                draw_ordinal += 1
        statistic = pooled_spearman(sampled_rows)
        if statistic is not None:
            values.append(statistic)
    if len(values) < max(10, math.ceil(iterations * 0.90)):
        return None, len(values)
    return float(np.quantile(values, 0.05, method="linear")), len(values)


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
    """Calibrate noise without using any empirical R1/R2 result."""
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
            point_pass = rho >= float(gates["spearman_point_minimum"])
            lower_pass = lower is not None and lower > float(gates["spearman_lower_minimum"])
            tau_pass = tau >= float(gates["kendall_point_minimum"])
            direction_pass = all(
                value is not None and value > 0
                for value in statistics["length_language_directions"].values()
            ) and all(
                value is not None and value > 0
                for value in statistics["relation_directions"].values()
            )
            stability_pass = all(
                value is not None and rho - value <= float(gates["max_leave_one_cell_drop"])
                for value in statistics["leave_one_length_language_out"].values()
            )
            for name, passed in {
                "point": point_pass,
                "lower": lower_pass,
                "kendall": tau_pass,
                "direction": direction_pass,
                "stability": stability_pass,
                "caliper": bool(design["caliper_pass"]),
                "resolution": bool(design["resolution_pass"]),
                "support": bool(
                    design["common_support"]["all_4_length_language_aggregates_pass"]
                ),
            }.items():
                pass_counts[name] += int(passed)
            full_pass = all(
                (
                    point_pass,
                    lower_pass,
                    tau_pass,
                    direction_pass,
                    stability_pass,
                    bool(design["caliper_pass"]),
                    bool(design["resolution_pass"]),
                    bool(
                        design["common_support"][
                            "all_4_length_language_aggregates_pass"
                        ]
                    ),
                )
            )
            pass_counts["full"] += int(full_pass)
            pass_counts["valid_bootstrap"] += int(valid_bootstraps >= bootstrap_iterations * 0.90)
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
                "bootstrap_lower_mean": (
                    None
                    if not valid_lower_bounds
                    else float(np.mean(valid_lower_bounds))
                ),
                "pass_probabilities": probabilities,
                "monte_carlo_se_full": math.sqrt(
                    probabilities["full"] * (1 - probabilities["full"]) / outer_iterations
                ),
            }
        )
    return {
        "status": "POWER_SIMULATION_COMPLETE_SYNTHETIC_ONLY",
        "frame": {
            "families": 128,
            "candidate_rows": 256,
            "condition_cells": 12,
            "dataset_cell_quotas": DATASET_CELL_QUOTAS,
        },
        "estimand": {
            "standardization": "within dataset×length×language, ddof=1",
            "dataset_statistic": "Spearman/Kendall tau-b over candidate rows; each family contributes exactly two rows",
            "pooling": "arithmetic mean of the three dataset statistics",
            "bootstrap": "family-clustered and stratified within all 12 cells; recompute standardization",
        },
        "config": dict(config),
        "scenarios": scenario_results,
    }
