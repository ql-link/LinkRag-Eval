from __future__ import annotations

import math
from pathlib import Path

import pytest

from linkrag_eval.robust_fusion.r2_similarity_diagnostic import (
    clustered_bootstrap,
    detect_language,
    human_distribution,
    influence_diagnostics,
    kendall_tau_b,
    normalize_surface,
    spearman,
    surface_metrics,
)
from scripts.run_robust_fusion_r2_similarity_diagnostic import (
    OUTPUT_ROOT,
    run,
    verify_pre_execution_lock,
)


def diagnostic_rows() -> list[dict[str, object]]:
    rows = []
    for index, (human, main, audit) in enumerate(
        ((1, 0.1, 0.2), (2, 0.2, 0.3), (4, 0.4, 0.5), (5, 0.5, 0.4)),
        start=1,
    ):
        rows.append(
            {
                "family_id": f"F{index}",
                "human_score": human,
                "main_similarity": main,
                "audit_similarity": audit,
                "length_stratum": "short" if index % 2 else "long",
                "language": "zh" if index <= 2 else "en",
            }
        )
    return rows


def test_surface_normalization_language_and_single_slot_proxy() -> None:
    assert normalize_surface("Ａ  \n B") == "A B"
    assert detect_language("封存登记表") == "zh"
    assert detect_language("sealed registry") == "en"
    metrics = surface_metrics(
        "Procedure CAL-01 takes effect on 2024-01-15.",
        "Procedure CAL-01 takes effect on 2025-01-15.",
    )
    assert metrics["single_slot_proxy"] is True
    assert 0 < metrics["normalized_levenshtein"] <= 0.20
    assert metrics["prefix_suffix_coverage"] >= 0.60


def test_tie_entropy_and_ceiling_are_mechanical() -> None:
    summary = human_distribution([4, 4, 5, 5])
    assert summary["unique_value_count"] == 2
    assert summary["pairwise_tie_fraction"] == pytest.approx(2 / 6)
    assert summary["ceiling_fraction_score_5"] == 0.5
    assert 0 < summary["normalized_entropy"] <= 1


def test_spearman_and_kendall_handle_ties_and_constants() -> None:
    assert spearman([1, 2, 3, 4], [1, 2, 3, 4]) == pytest.approx(1.0)
    assert kendall_tau_b([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert spearman([1, 1, 1], [1, 2, 3]) is None
    assert kendall_tau_b([1, 1, 1], [1, 2, 3]) is None


def test_clustered_bootstrap_is_deterministic() -> None:
    rows = diagnostic_rows()
    first = clustered_bootstrap(rows, seed=17, iterations=200)
    second = clustered_bootstrap(rows, seed=17, iterations=200)
    assert first == second
    interval = first["intervals"]["main_human_spearman"]
    assert 0 < interval["valid_iterations"] <= 200
    assert -1 <= interval["lower_2_5"] <= interval["upper_97_5"] <= 1


def test_influence_reports_fixed_strata_and_family_effects() -> None:
    result = influence_diagnostics(diagnostic_rows())
    assert len(result["leave_one_length_language_stratum_out"]) == 4
    assert result["leave_one_family_out_largest_main"] is not None
    assert math.isfinite(result["full"]["main_human"]["spearman"])


def test_locked_input_manifest_verifies_and_alternate_output_is_rejected(
    tmp_path: Path,
) -> None:
    verified = verify_pre_execution_lock()
    assert len(verified["input_records"]) == 28
    assert all("blind" not in row["path"].lower() for row in verified["input_records"])
    with pytest.raises(RuntimeError, match="output root is fixed"):
        run(tmp_path)


def test_append_only_real_output_refuses_repeat_after_materialization() -> None:
    if not (OUTPUT_ROOT / "manifest.json").exists():
        pytest.skip("formal exploratory diagnostic has not been materialized yet")
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        run()
