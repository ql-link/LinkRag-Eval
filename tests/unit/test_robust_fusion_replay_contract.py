from __future__ import annotations

from linkrag_eval.robust_fusion.replay_contract import (
    DENSE_REPLAY_TOLERANCE,
    dense_replay_metrics,
)


def test_dense_replay_exact_and_tiny_numeric_paths() -> None:
    exact = dense_replay_metrics([0.1, -0.2], [0.1, -0.2], expected_dim=2)
    tiny = dense_replay_metrics([0.1, -0.2], [0.10000001, -0.2], expected_dim=2)

    assert exact["exact_float32_match"] is True
    assert exact["within_frozen_numeric_tolerance"] is True
    assert tiny["exact_float32_match"] is False
    assert tiny["within_frozen_numeric_tolerance"] is True
    assert tiny["max_single_candidate_cosine_score_delta_bound"] <= 1e-5


def test_dense_replay_rejects_material_change() -> None:
    metrics = dense_replay_metrics([0.1, -0.2], [0.101, -0.2], expected_dim=2)

    assert metrics["exact_float32_match"] is False
    assert metrics["within_frozen_numeric_tolerance"] is False
    assert metrics["max_absolute_component_delta"] > DENSE_REPLAY_TOLERANCE[
        "max_absolute_component_delta"
    ]


def test_dense_replay_preserves_bitwise_signed_zero_distinction() -> None:
    metrics = dense_replay_metrics([0.0, 1.0], [-0.0, 1.0], expected_dim=2)

    assert metrics["exact_float32_match"] is False
    assert metrics["changed_component_count"] == 1
    assert metrics["within_frozen_numeric_tolerance"] is True
