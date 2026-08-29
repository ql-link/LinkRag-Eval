"""Structural validation and descriptive fingerprints for provider routes.

Provider-managed Dense/Sparse values are not subject to a numerical replay
acceptance threshold. A route snapshot is generated once, validated for
structural integrity and then hash-sealed. Pairwise replay metrics remain
available for diagnostics only and must never decide snapshot acceptance or
trigger a rerun.
"""

from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Sequence
from typing import Any

PROVIDER_ROUTE_POLICY_ID = (
    "ROBUST-FUSION-PROVIDER-ROUTE-SNAPSHOT-POLICY-2026-08-29-v2"
)


def _as_float32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def _float32_vector(values: Sequence[float], *, expected_dim: int) -> list[float]:
    if len(values) != expected_dim:
        raise ValueError(f"dense vector dimension drift: {len(values)} != {expected_dim}")
    converted = [_as_float32(value) for value in values]
    if not all(math.isfinite(value) for value in converted):
        raise ValueError("dense vector contains NaN or Inf")
    return converted


def _vector_sha256(values: Sequence[float]) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(struct.pack("<f", value))
    return digest.hexdigest()


def _l2_norm(values: Sequence[float]) -> float:
    return math.sqrt(math.fsum(value * value for value in values))


def _normalized(values: Sequence[float]) -> list[float]:
    norm = _l2_norm(values)
    if norm == 0:
        raise ValueError("dense vector has zero norm")
    return [value / norm for value in values]


def dense_vector_fingerprint(
    values_raw: Sequence[float], *, expected_dim: int
) -> dict[str, Any]:
    """Validate one Dense vector and return a value-free canonical fingerprint."""

    values = _float32_vector(values_raw, expected_dim=expected_dim)
    norm = _l2_norm(values)
    if norm == 0:
        raise ValueError("dense vector has zero norm")
    return {
        "dimension": len(values),
        "float32_sha256": _vector_sha256(values),
        "l2_norm": norm,
        "structural_validation": "PASS",
    }


def sparse_vector_fingerprint(
    indices_raw: Sequence[int],
    values_raw: Sequence[float],
    *,
    top_k: int,
) -> dict[str, Any]:
    """Validate one sparse vector and return a value-free canonical fingerprint."""

    if top_k <= 0:
        raise ValueError("sparse top_k must be positive")
    if not indices_raw:
        raise ValueError("sparse vector is empty")
    if len(indices_raw) != len(values_raw):
        raise ValueError("sparse vector index/value length mismatch")
    indices = [int(index) for index in indices_raw]
    if any(index != converted for index, converted in zip(indices_raw, indices)):
        raise ValueError("sparse vector index is not an integer")
    if (
        indices != sorted(indices)
        or len(indices) != len(set(indices))
        or any(index < 0 for index in indices)
    ):
        raise ValueError("sparse vector index contract invalid")
    if len(indices) > top_k:
        raise ValueError("sparse vector exceeds top_k")
    values = [_as_float32(value) for value in values_raw]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("sparse vector contains NaN or Inf")
    if not any(value != 0.0 for value in values):
        raise ValueError("sparse vector has no nonzero weights")
    digest = hashlib.sha256()
    for index, value in zip(indices, values):
        digest.update(struct.pack("<qf", index, value))
    return {
        "nonzero_count": len(indices),
        "canonical_sparse_float32_sha256": digest.hexdigest(),
        "structural_validation": "PASS",
    }


def dense_replay_metrics(
    left_raw: Sequence[float], right_raw: Sequence[float], *, expected_dim: int
) -> dict[str, Any]:
    """Describe two canonical float32 vectors without applying an acceptance gate."""

    left = _float32_vector(left_raw, expected_dim=expected_dim)
    right = _float32_vector(right_raw, expected_dim=expected_dim)
    left_bytes = [struct.pack("<f", value) for value in left]
    right_bytes = [struct.pack("<f", value) for value in right]
    deltas = [abs(a - b) for a, b in zip(left, right)]
    max_index = max(range(expected_dim), key=deltas.__getitem__)
    delta_norm = _l2_norm([a - b for a, b in zip(left, right)])
    left_norm = _l2_norm(left)
    right_norm = _l2_norm(right)
    relative_l2_delta = delta_norm / max(left_norm, right_norm, 1e-12)
    left_unit = _normalized(left)
    right_unit = _normalized(right)
    normalized_delta = _l2_norm([a - b for a, b in zip(left_unit, right_unit)])
    cosine = math.fsum(a * b for a, b in zip(left_unit, right_unit))
    cosine = min(1.0, max(-1.0, cosine))
    symmetric_relative = [
        delta / max(abs(a), abs(b), 1e-12)
        for a, b, delta in zip(left, right, deltas)
    ]
    metrics: dict[str, Any] = {
        "left_float32_sha256": _vector_sha256(left),
        "right_float32_sha256": _vector_sha256(right),
        "exact_float32_match": left_bytes == right_bytes,
        "changed_component_count": sum(a != b for a, b in zip(left_bytes, right_bytes)),
        "max_absolute_component_delta": deltas[max_index],
        "max_absolute_component_delta_index": max_index,
        "max_symmetric_relative_component_delta": max(symmetric_relative),
        "l2_delta": delta_norm,
        "relative_l2_delta": relative_l2_delta,
        "normalized_query_l2_delta": normalized_delta,
        "cosine_similarity": cosine,
        "cosine_distance": 1.0 - cosine,
        # For any unit candidate c: |c·q1 - c·q2| <= ||q1-q2||_2.
        "max_single_candidate_cosine_score_delta_bound": normalized_delta,
        "numeric_comparison_role": "DESCRIPTIVE_ONLY",
        "numeric_gate_applied": False,
    }
    return metrics
