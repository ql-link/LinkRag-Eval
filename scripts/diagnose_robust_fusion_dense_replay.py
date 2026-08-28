#!/usr/bin/env python3
"""Measure provider-managed Dense replay drift without changing Gate policy."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Any

from probe_robust_fusion_route_contract import (
    ENGINEERING_PROTOCOL,
    EXPECTED_DENSE_MODEL,
    SCIENTIFIC_PROTOCOL,
    fixed_inputs,
    sha256_file,
)

from linkrag_eval.config import EvalSettings
from linkrag_eval.llm.dense_client import OpenAIDenseEmbedder

ARTIFACT_VERSION = "ROBUST-FUSION-DENSE-REPLAY-DIAGNOSTIC-2026-08-29-v1"

# Frozen before observing this diagnostic run. These are diagnostic reference
# bounds, not an active Gate-A replay policy. A later protocol revision is still
# required before the formal preflight can accept numeric rather than exact replay.
TINY_DRIFT_REFERENCE = {
    "max_absolute_component_delta": 1e-6,
    "relative_l2_delta": 1e-5,
    "normalized_query_l2_delta": 1e-5,
    "cosine_distance": 1e-8,
    "max_single_candidate_cosine_score_delta_bound": 1e-5,
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def as_float32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def float32_vector(values: list[float], expected_dim: int) -> list[float]:
    if len(values) != expected_dim:
        raise RuntimeError(f"dense vector dimension drift: {len(values)} != {expected_dim}")
    converted = [as_float32(value) for value in values]
    if not all(math.isfinite(value) for value in converted):
        raise RuntimeError("dense vector contains NaN or Inf")
    return converted


def vector_sha256(values: list[float]) -> str:
    digest = hashlib.sha256()
    for value in values:
        digest.update(struct.pack("<f", value))
    return digest.hexdigest()


def l2_norm(values: list[float]) -> float:
    return math.sqrt(math.fsum(value * value for value in values))


def normalized(values: list[float]) -> list[float]:
    norm = l2_norm(values)
    if norm == 0:
        raise RuntimeError("dense vector has zero norm")
    return [value / norm for value in values]


def replay_metrics(left_raw: list[float], right_raw: list[float], expected_dim: int) -> dict[str, Any]:
    left = float32_vector(left_raw, expected_dim)
    right = float32_vector(right_raw, expected_dim)
    deltas = [abs(a - b) for a, b in zip(left, right)]
    max_index = max(range(expected_dim), key=deltas.__getitem__)
    delta_norm = l2_norm([a - b for a, b in zip(left, right)])
    left_norm = l2_norm(left)
    right_norm = l2_norm(right)
    relative_l2_delta = delta_norm / max(left_norm, right_norm, 1e-12)
    left_unit = normalized(left)
    right_unit = normalized(right)
    normalized_delta = l2_norm([a - b for a, b in zip(left_unit, right_unit)])
    cosine = math.fsum(a * b for a, b in zip(left_unit, right_unit))
    cosine = min(1.0, max(-1.0, cosine))
    cosine_distance = 1.0 - cosine
    symmetric_relative = [
        delta / max(abs(a), abs(b), 1e-12)
        for a, b, delta in zip(left, right, deltas)
    ]
    result = {
        "left_float32_sha256": vector_sha256(left),
        "right_float32_sha256": vector_sha256(right),
        "exact_float32_match": left == right,
        "changed_component_count": sum(a != b for a, b in zip(left, right)),
        "max_absolute_component_delta": deltas[max_index],
        "max_absolute_component_delta_index": max_index,
        "max_symmetric_relative_component_delta": max(symmetric_relative),
        "l2_delta": delta_norm,
        "relative_l2_delta": relative_l2_delta,
        "normalized_query_l2_delta": normalized_delta,
        "cosine_similarity": cosine,
        "cosine_distance": cosine_distance,
        # For any unit-length candidate c, |c·q1 - c·q2| <= ||q1-q2||_2.
        "max_single_candidate_cosine_score_delta_bound": normalized_delta,
    }
    result["within_predeclared_tiny_drift_reference"] = all(
        result[name] <= threshold for name, threshold in TINY_DRIFT_REFERENCE.items()
    )
    return result


async def run_diagnostic(settings: EvalSettings) -> dict[str, Any]:
    if settings.embed_model != EXPECTED_DENSE_MODEL:
        raise RuntimeError(
            f"Gate A dense model drift: {settings.embed_model!r} != {EXPECTED_DENSE_MODEL!r}"
        )
    if not settings.embed_api_key.strip() or not settings.embed_base_url.strip():
        raise RuntimeError("EVAL_EMBED_API_KEY/EVAL_EMBED_BASE_URL not configured")

    dense_endpoint = settings.embed_base_url.rstrip("/")
    encoder = OpenAIDenseEmbedder(
        api_key=settings.embed_api_key,
        model=settings.embed_model,
        base_url=dense_endpoint,
        dim=settings.embed_dim,
        batch_size=settings.embed_batch_size,
        concurrency=settings.embed_concurrency,
        timeout_ms=settings.embed_timeout_ms,
        max_retries=0,
    )
    items = fixed_inputs()
    try:
        first = await encoder.aembed([text for _, text in items])
        reversed_vectors = await encoder.aembed([text for _, text in reversed(items)])
    finally:
        await encoder.aclose()
    second = list(reversed(reversed_vectors))

    probes = []
    for (probe_id, text), left, right in zip(items, first, second):
        metrics = replay_metrics(left, right, settings.embed_dim)
        probes.append(
            {
                "probe_id": probe_id,
                "input_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "dimension": settings.embed_dim,
                **metrics,
            }
        )

    aggregate = {
        name: max(float(row[name]) for row in probes)
        for name in TINY_DRIFT_REFERENCE
    }
    aggregate["changed_probe_count"] = sum(not row["exact_float32_match"] for row in probes)
    aggregate["changed_component_count"] = sum(
        int(row["changed_component_count"]) for row in probes
    )
    aggregate["all_probes_within_predeclared_tiny_drift_reference"] = all(
        bool(row["within_predeclared_tiny_drift_reference"]) for row in probes
    )

    return {
        "artifact_version": ARTIFACT_VERSION,
        "scientific_protocol": SCIENTIFIC_PROTOCOL,
        "engineering_protocol": ENGINEERING_PROTOCOL,
        "status": "DIAGNOSTIC_COMPLETE_NO_POLICY_CHANGE",
        "authorization": "RESEARCH_OWNER_CONDITIONAL_TINY_DRIFT_DIAGNOSTIC_2026-08-29",
        "gate_a_executed": False,
        "outcome_data_read": False,
        "formal_exact_replay_policy_changed": False,
        "request_design": {
            "provider_contract": "OpenAI-compatible online embeddings",
            "model": settings.embed_model,
            "dimension": settings.embed_dim,
            "endpoint_identity_sha256": hashlib.sha256(
                dense_endpoint.encode("utf-8")
            ).hexdigest(),
            "external_request_count": 2,
            "automatic_retry_count": 0,
            "first_request_order": "canonical_fixed_probe_order",
            "second_request_order": "reverse_fixed_probe_order",
            "plaintext_inputs_persisted": False,
            "vectors_persisted": False,
        },
        "predeclared_tiny_drift_reference": {
            **TINY_DRIFT_REFERENCE,
            "policy_effect": "DIAGNOSTIC_ONLY_REQUIRES_LATER_PROTOCOL_FREEZE",
        },
        "aggregate": aggregate,
        "probes": probes,
        "interpretation_boundary": {
            "candidate_ids_or_scores_read": False,
            "actual_candidate_rank_stability_measured": False,
            "score_delta_is_mathematical_upper_bound_for_unit_candidate_vectors": True,
            "gate_a_remains_locked": True,
        },
        "secrets_persisted": False,
    }


async def async_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runs/robust_fusion/contracts/dense-replay-diagnostic-v1"),
    )
    args = parser.parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    output_root = args.output_root
    if not output_root.is_absolute():
        output_root = repository_root / output_root
    if output_root.exists():
        raise RuntimeError(f"refusing to overwrite existing output: {output_root}")
    output_root.mkdir(parents=True)

    try:
        manifest = await run_diagnostic(EvalSettings())
    except (RuntimeError, ValueError) as exc:
        failure = {
            "artifact_version": ARTIFACT_VERSION,
            "status": "DIAGNOSTIC_FAILED_NO_RETRY",
            "error_type": type(exc).__name__,
            "automatic_retry_count": 0,
            "gate_a_executed": False,
            "outcome_data_read": False,
            "secrets_persisted": False,
        }
        failure_path = output_root / "failure.json"
        failure_path.write_text(canonical_json(failure) + "\n", encoding="utf-8")
        print(canonical_json({"status": failure["status"], "error_type": failure["error_type"]}))
        return 1

    script_path = Path(__file__).resolve()
    formal_probe_path = repository_root / "scripts/probe_robust_fusion_route_contract.py"
    manifest["generator"] = {
        "relative_path": str(script_path.relative_to(repository_root)),
        "sha256": sha256_file(script_path),
        "formal_probe_relative_path": str(formal_probe_path.relative_to(repository_root)),
        "formal_probe_sha256": sha256_file(formal_probe_path),
    }
    manifest_path = output_root / "manifest.json"
    manifest_path.write_text(canonical_json(manifest) + "\n", encoding="utf-8")
    digest = sha256_file(manifest_path)
    (output_root / "manifest.sha256").write_text(f"{digest}  manifest.json\n", encoding="utf-8")
    print(
        canonical_json(
            {
                "artifact_version": ARTIFACT_VERSION,
                "status": manifest["status"],
                "all_probes_within_predeclared_tiny_drift_reference": manifest["aggregate"][
                    "all_probes_within_predeclared_tiny_drift_reference"
                ],
                "manifest_sha256": digest,
                "output_root": str(output_root),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))
