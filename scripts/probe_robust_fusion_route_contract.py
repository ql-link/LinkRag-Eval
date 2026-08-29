#!/usr/bin/env python3
"""Probe structural contracts for the actual Dense/Sparse/BM25 research routes."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from linkrag_eval.config import EvalSettings
from linkrag_eval.llm.dense_client import OpenAIDenseEmbedder
from linkrag_eval.llm.sparse_client import ArkSparseEncoder
from linkrag_eval.robust_fusion.replay_contract import (
    PROVIDER_ROUTE_POLICY_ID,
    dense_vector_fingerprint,
    sparse_vector_fingerprint,
)

ARTIFACT_VERSION = "ROBUST-FUSION-ROUTE-CONTRACT-PREFLIGHT-2026-08-29-v3"
SCIENTIFIC_PROTOCOL = "ROBUST-FUSION-RESEARCH-2026-08-29-v26"
ENGINEERING_PROTOCOL = "ROBUST-FUSION-ENGINEERING-2026-08-29-v17"
EXPECTED_DENSE_MODEL = "text-embedding-v4"
EXPECTED_SPARSE_MODEL = "doubao-embedding-vision-251215"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fixed_inputs() -> list[tuple[str, str]]:
    return [
        ("zh_short", "年假规则"),
        ("zh_condition", "2026年3月后，仅限已认证企业版账户，额度不是1000而是3000。"),
        ("en_condition", "Verified enterprise accounts are not eligible before March 2026."),
        ("identifier", "订单ABC-2025为什么不能退款"),
    ]


async def run_probe(settings: EvalSettings) -> dict[str, Any]:
    if settings.embed_model != EXPECTED_DENSE_MODEL:
        raise RuntimeError(
            f"Gate A dense model drift: {settings.embed_model!r} != {EXPECTED_DENSE_MODEL!r}"
        )
    if not settings.embed_api_key.strip() or not settings.embed_base_url.strip():
        raise RuntimeError("EVAL_EMBED_API_KEY/EVAL_EMBED_BASE_URL 未配置")
    if settings.sparse_provider.strip().lower() != "ark":
        raise RuntimeError(
            "Gate A Learned Sparse 必须使用真实 ark/豆包在线口径；BGE-M3 或其他 provider 被拒绝"
        )
    if settings.sparse_model != EXPECTED_SPARSE_MODEL:
        raise RuntimeError(
            f"Gate A sparse model drift: {settings.sparse_model!r} != {EXPECTED_SPARSE_MODEL!r}"
        )
    if settings.bm25_mode != "sqlite_fts5":
        raise RuntimeError(f"Gate A BM25 mode drift: {settings.bm25_mode!r} != 'sqlite_fts5'")
    if not settings.sparse_api_key.strip():
        raise RuntimeError("EVAL_SPARSE_API_KEY 未配置")

    dense_endpoint = settings.embed_base_url.rstrip("/")
    dense_encoder = OpenAIDenseEmbedder(
        api_key=settings.embed_api_key,
        model=settings.embed_model,
        base_url=dense_endpoint,
        dim=settings.embed_dim,
        batch_size=settings.embed_batch_size,
        concurrency=settings.embed_concurrency,
        timeout_ms=settings.embed_timeout_ms,
        max_retries=0,
    )
    sparse_endpoint = settings.sparse_base_url or ArkSparseEncoder.DEFAULT_ENDPOINT
    sparse_encoder = ArkSparseEncoder(
        api_key=settings.sparse_api_key,
        model=settings.sparse_model,
        base_url=sparse_endpoint,
        top_k=settings.sparse_top_k,
        min_weight=settings.sparse_min_weight,
        timeout_ms=settings.sparse_timeout_ms,
        max_retries=0,
        concurrency=settings.sparse_concurrency,
    )
    items = fixed_inputs()
    try:
        dense_vectors = await dense_encoder.aembed([text for _, text in items])
        sparse_vectors = await sparse_encoder.aencode([text for _, text in items])
    finally:
        await dense_encoder.aclose()
        await sparse_encoder.aclose()

    if len(dense_vectors) != len(items):
        raise RuntimeError(
            f"Dense response count drift: {len(dense_vectors)} != {len(items)}"
        )
    if len(sparse_vectors) != len(items):
        raise RuntimeError(
            f"Sparse response count drift: {len(sparse_vectors)} != {len(items)}"
        )

    dense_rows = []
    sparse_rows = []
    for (probe_id, text), dense_vector, sparse_vector in zip(
        items, dense_vectors, sparse_vectors
    ):
        dense_rows.append(
            {
                "probe_id": probe_id,
                "input_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                **dense_vector_fingerprint(
                    dense_vector, expected_dim=settings.embed_dim
                ),
            }
        )

        sparse_rows.append(
            {
                "probe_id": probe_id,
                "input_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                **sparse_vector_fingerprint(
                    sparse_vector.indices,
                    sparse_vector.values,
                    top_k=settings.sparse_top_k,
                ),
            }
        )

    return {
        "artifact_version": ARTIFACT_VERSION,
        "scientific_protocol": SCIENTIFIC_PROTOCOL,
        "engineering_protocol": ENGINEERING_PROTOCOL,
        "status": "LOCAL_CONFIG_AND_LIVE_PROVIDER_STRUCTURE_PASS",
        "gate_a_executed": False,
        "outcome_data_read": False,
        "provider_route_governance": {
            "policy_id": PROVIDER_ROUTE_POLICY_ID,
            "numeric_acceptance_threshold": None,
            "numeric_comparison_role": "DESCRIPTIVE_ONLY",
            "snapshot_policy": "ONE_AUTHORIZED_GENERATION_THEN_HASH_SEAL",
            "rerun_due_to_numeric_difference": "FORBIDDEN",
            "run_selection_by_numeric_output": "FORBIDDEN",
            "automatic_retry_count": 0,
            "encoder_method_call_count": 2,
        },
        "routes": {
            "dense": {
                "provider_contract": "OpenAI-compatible online embeddings",
                "model": settings.embed_model,
                "dimension": settings.embed_dim,
                "endpoint_identity_sha256": hashlib.sha256(
                    dense_endpoint.encode("utf-8")
                ).hexdigest(),
                "policy_id": PROVIDER_ROUTE_POLICY_ID,
                "numeric_replay_gate": "NONE",
                "probe_vectors": dense_rows,
            },
            "learned_sparse": {
                "provider": "ark",
                "model": settings.sparse_model,
                "top_k": settings.sparse_top_k,
                "min_weight": settings.sparse_min_weight,
                "endpoint_identity_sha256": hashlib.sha256(
                    sparse_endpoint.encode("utf-8")
                ).hexdigest(),
                "request_schema": "multimodal text input + sparse_embedding enabled",
                "response_schema": "data.sparse_embedding[index,value]",
                "online_weight_revision_visibility": "MODEL_ID_ONLY_PROVIDER_MANAGED_WEIGHTS",
                "policy_id": PROVIDER_ROUTE_POLICY_ID,
                "numeric_replay_gate": "NONE",
                "probe_vectors": sparse_rows,
            },
            "bm25": {
                "provider": "eval_sqlite_fts5",
                "mode": settings.bm25_mode,
                "coarse_weight": settings.bm25_sqlite_coarse_weight,
                "fine_weight": settings.bm25_sqlite_fine_weight,
            },
        },
        "excluded_inputs": {
            "alt_embedding": "historical candidate-generation sidecar; not a Gate A route",
            "bge_m3": "retired by research-owner decision; forbidden as route or similarity encoder",
        },
        "secrets_persisted": False,
        "remaining_hard_gates": [
            "freeze provider-visible request/output snapshot hashes with each candidate snapshot",
            "complete Dev-only validity and band calibration for the qualified non-BGE similarity encoders",
            "formal contract-lock still requires both repositories clean and a green CI run",
        ],
    }


async def async_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runs/robust_fusion/contracts/route-contract-preflight-v3"),
    )
    args = parser.parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    output_root = args.output_root
    if not output_root.is_absolute():
        output_root = repository_root / output_root
    if output_root.exists():
        raise RuntimeError(f"refusing to overwrite existing output: {output_root}")
    output_root.mkdir(parents=True)
    manifest = await run_probe(EvalSettings())
    script_path = Path(__file__).resolve()
    manifest["generator"] = {
        "relative_path": str(script_path.relative_to(repository_root)),
        "sha256": sha256_file(script_path),
        "replay_contract_relative_path": "src/linkrag_eval/robust_fusion/replay_contract.py",
        "replay_contract_sha256": sha256_file(
            repository_root / "src/linkrag_eval/robust_fusion/replay_contract.py"
        ),
    }
    manifest_path = output_root / "manifest.json"
    manifest_path.write_text(canonical_json(manifest) + "\n", encoding="utf-8")
    digest = sha256_file(manifest_path)
    (output_root / "manifest.sha256").write_text(
        f"{digest}  manifest.json\n", encoding="utf-8"
    )
    print(
        canonical_json(
            {
                "artifact_version": ARTIFACT_VERSION,
                "status": manifest["status"],
                "manifest_sha256": digest,
                "output_root": str(output_root),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(async_main()))
