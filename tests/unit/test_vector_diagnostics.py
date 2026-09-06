from __future__ import annotations

import pytest

from linkrag_eval.compute.vector_diagnostics import (
    dense_replay_metrics,
    dense_vector_fingerprint,
    sparse_vector_fingerprint,
)


def test_dense_fingerprint_validates_and_hashes_one_vector() -> None:
    fingerprint = dense_vector_fingerprint([1.0, 2.0], expected_dim=2)

    assert fingerprint["dimension"] == 2
    assert len(fingerprint["float32_sha256"]) == 64
    assert fingerprint["l2_norm"] == pytest.approx(5**0.5)
    assert fingerprint["structural_validation"] == "PASS"


def test_dense_replay_metrics_are_descriptive_for_exact_and_changed_values() -> None:
    exact = dense_replay_metrics([0.1, -0.2], [0.1, -0.2], expected_dim=2)
    changed = dense_replay_metrics([0.1, -0.2], [0.101, -0.2], expected_dim=2)

    assert exact["exact_float32_match"] is True
    assert exact["numeric_gate_applied"] is False
    assert changed["exact_float32_match"] is False
    assert changed["max_absolute_component_delta"] > 0
    assert changed["numeric_comparison_role"] == "DESCRIPTIVE_ONLY"
    assert changed["numeric_gate_applied"] is False


def test_dense_replay_preserves_bitwise_signed_zero_distinction() -> None:
    metrics = dense_replay_metrics([0.0, 1.0], [-0.0, 1.0], expected_dim=2)

    assert metrics["exact_float32_match"] is False
    assert metrics["changed_component_count"] == 1
    assert metrics["numeric_gate_applied"] is False


def test_dense_fingerprint_rejects_dimension_nonfinite_and_zero_norm() -> None:
    with pytest.raises(ValueError, match="dimension drift"):
        dense_vector_fingerprint([1.0], expected_dim=2)
    with pytest.raises(ValueError, match="NaN or Inf"):
        dense_vector_fingerprint([1.0, float("nan")], expected_dim=2)
    with pytest.raises(ValueError, match="zero norm"):
        dense_vector_fingerprint([0.0, 0.0], expected_dim=2)


def test_sparse_fingerprint_validates_and_hashes_one_vector() -> None:
    fingerprint = sparse_vector_fingerprint([2, 9], [0.5, 1.25], top_k=2)

    assert fingerprint["nonzero_count"] == 2
    assert len(fingerprint["canonical_sparse_float32_sha256"]) == 64
    assert fingerprint["structural_validation"] == "PASS"


@pytest.mark.parametrize(
    ("indices", "values", "message"),
    [
        ([], [], "empty"),
        ([2, 1], [0.5, 1.0], "index contract"),
        ([1, 1], [0.5, 1.0], "index contract"),
        ([-1], [0.5], "index contract"),
        ([1], [float("inf")], "NaN or Inf"),
        ([1], [0.0], "no nonzero weights"),
    ],
)
def test_sparse_fingerprint_rejects_structural_failures(
    indices: list[int], values: list[float], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        sparse_vector_fingerprint(indices, values, top_k=2)


def test_sparse_fingerprint_rejects_top_k_overflow() -> None:
    with pytest.raises(ValueError, match="exceeds top_k"):
        sparse_vector_fingerprint([1, 2], [0.5, 1.0], top_k=1)
