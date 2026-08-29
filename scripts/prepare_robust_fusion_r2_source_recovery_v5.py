#!/usr/bin/env python3
"""Seal conservative R2 source recovery v5 before any v5 provider response."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.r2_source_generation import build_slot_registry, canonical_json
from linkrag_eval.robust_fusion.r2_source_recovery_v5 import (
    PROMPT_CONTRACT_ID_V5,
    SOURCE_PROTOCOL_ID_V5,
    build_request_v5,
    verify_inherited_v4_proposal,
)
from linkrag_eval.robust_fusion.similarity_dev_calibration import sha256_file, write_json
from scripts.prepare_robust_fusion_r2_source_recovery_v3 import (
    EXPECTED_PARSER_SOURCE_SHA,
    EXPECTED_R2_PREREG_SHA,
    EXPECTED_SLOT_REGISTRY_SHA,
    PARSER_SOURCE,
    V1_PREP,
)
from scripts.prepare_robust_fusion_r2_source_recovery_v4 import (
    verify as verify_v4_preparation,
)
from scripts.run_robust_fusion_r2_measurement import verify_preregistration

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_preparation_v5/"
    "robust-fusion-r2-source-recovery-preparation-v5-20260829"
)
LIVE_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_v5/robust-fusion-r2-source-recovery-v5-20260829"
)
SPEC = REPO_ROOT / "docs/plans/robust-fusion-r2-source-recovery-v5.md"
AUTHORIZATION = REPO_ROOT / "docs/plans/robust-fusion-r2-source-authorization-amendment-v2.json"
R2_PREREG = REPO_ROOT / (
    "runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/"
    "preregistration/manifest.json"
)
EXCLUSION = REPO_ROOT / (
    "runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/"
    "exclusions/registry.json"
)
V4_PREP = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_preparation_v4/"
    "robust-fusion-r2-source-recovery-preparation-v4-20260829"
)
V4_LIVE = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_v4/robust-fusion-r2-source-recovery-v4-20260829"
)
V3_DIAGNOSTIC = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_v3_diagnostic_v1/"
    "robust-fusion-r2-source-recovery-v3-diagnostic-v1-20260829"
)
V4_DIAGNOSTIC = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_v4_diagnostic_v1/"
    "robust-fusion-r2-source-recovery-v4-diagnostic-v1-20260829"
)
APPEND_ONLY_INPUTS = {
    V4_PREP / "manifest.json": "01b32fc16758418cb6dc2659bc61560786fd7018d307cff5ef81198401dd99cf",
    V4_PREP / "lock.json": "9b6d9b479fdac01209efbe3efaefb44bf823178fbeda17cc9f3ea4a4c73184ce",
    V4_PREP / "receipt.json": "02c58a5b406fb0ab90a2b497b6fa8e9c507f5f24e2e626653b1bbb07cfdd31f1",
    V4_LIVE / "authorization_receipt_snapshot.json": (
        "f1ddcef8e4e9770d9d6f968b6e75068e60abb6a0776646963d25dceb2cc3f635"
    ),
    V4_LIVE / "call_audit.jsonl": (
        "3c3cb03dc85eed353d0a2c6c01d5d58c66f67754b12b4faae3955d8f136a3a86"
    ),
    V4_LIVE / "response_archive_synthetic_only.jsonl": (
        "8f0d2cea12e97587d3d54728d3ab0323a9a515d0653d34b934be0c70ae1b6111"
    ),
    V4_LIVE / "attempt_scoped_stage_locks.jsonl": (
        "a06f09597055819540ea72ced30bdd986e3640a6f58be0d2dc9a1270fbe52842"
    ),
    V4_LIVE / "complete_assembly_attempts_not_truth.jsonl": (
        "1f9964fe8ffc473bac85b0333c552c4e06f562c18f4aa9b9b9bff4292d93a43e"
    ),
    V4_LIVE / "accepted_proposals_not_truth.jsonl": (
        "d1e15f11394ed15e2db8248987ba50310472ce206bb433d835144c7c6c98ee6b"
    ),
    V4_LIVE / "terminal_error.json": (
        "c192fc455f0e8d26a48717ab1ff5150e3e032eb0fe239e21dcb75934561acae0"
    ),
    V3_DIAGNOSTIC / "per_response_mechanical_diagnostic.jsonl": (
        "11e19f39ea150587753404bc3ef4b281c649ad2aa6eb47ea057635954eefddfe"
    ),
    V3_DIAGNOSTIC / "summary.json": (
        "8e9df39f0113b837c56935f198dde8c91f56bd0e3505dbf5f3554ea890cfa6f6"
    ),
    V3_DIAGNOSTIC / "manifest.json": (
        "da2e9992c60a00bef92dc1f33ce60c7e571429ce18f8c8534d0bd910d5aaa790"
    ),
    V4_DIAGNOSTIC / "reconstructed_request_metadata.jsonl": (
        "d303cc831bd386b71372e1b9a5f8735996457febb1a0d96911f8f21f322cae22"
    ),
    V4_DIAGNOSTIC / "response_mechanical_diagnostic.jsonl": (
        "76b4fd2f1f79753a63097006fd3294c2f9998d025ae8cc9a06502921d6d6bb01"
    ),
    V4_DIAGNOSTIC / "summary.json": (
        "3f90b6467df8f60d06a5fb7db66f79abe174e1e6fffbc307cbf0aa6bf0ace2bd"
    ),
    V4_DIAGNOSTIC / "manifest.json": (
        "46483eb3945113865f3f90465169af88a0186f7dce5a5fd014ac992d02098063"
    ),
}
CODE = (
    "src/linkrag_eval/robust_fusion/r2_source_recovery_v5.py",
    "scripts/prepare_robust_fusion_r2_source_recovery_v5.py",
    "scripts/run_robust_fusion_r2_source_recovery_v5.py",
    "tests/unit/test_robust_fusion_r2_source_recovery_v5.py",
)


def _sidecar(path: Path) -> None:
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{sha256_file(path)}  {path.name}\n", encoding="utf-8"
    )


def verify_append_only_inputs() -> None:
    verify_v4_preparation()
    for path, expected in APPEND_ONLY_INPUTS.items():
        if sha256_file(path) != expected:
            raise RuntimeError(
                f"v2/v3/v4 append-only evidence drift: {path.relative_to(REPO_ROOT)}"
            )


def assert_no_v5_live_root_before_seal(path: Path = LIVE_ROOT) -> None:
    if path.exists():
        raise RuntimeError("v5 live root exists before seal; refusing retrospective seal")


def _dry_request_plan() -> dict[str, Any]:
    hashes: list[str] = []
    strategy_rows: list[dict[str, Any]] = []
    for slot in build_slot_registry()[1:]:
        reference = (
            "甲" * (70 if slot["length_stratum"] == "short" else 200)
            if slot["language"] == "zh"
            else " ".join(["synthetic"] * (40 if slot["length_stratum"] == "short" else 120))
        )
        query = "虚构问题" if slot["language"] == "zh" else "Synthetic question"
        equivalent = (
            "乙" + reference[1:]
            if slot["language"] == "zh"
            else "fictional " + " ".join(reference.split()[1:])
        )
        for stage, locked in (
            ("R", {}),
            ("E", {"query": query, "reference": reference}),
            (
                "C",
                {
                    "query": query,
                    "reference": reference,
                    "equivalent_candidate": equivalent,
                },
            ),
        ):
            previous = None
            stage_hashes = []
            for response_attempt in (1, 2):
                body = build_request_v5(
                    slot,
                    stage=stage,
                    orchestration_attempt=1,
                    response_attempt=response_attempt,
                    locked_fields=locked,
                    previous_failure=previous,
                )
                digest = _digest(canonical_json(body).encode())
                hashes.append(digest)
                stage_hashes.append(digest)
                prompt = json.loads(body["messages"][1]["content"])
                strategy_rows.append(
                    {
                        "slot_id": slot["slot_id"],
                        "stage": stage,
                        "response_attempt": response_attempt,
                        "request_sha256": digest,
                        "scheduled_strategy": prompt["recovery_directive"]["scheduled_strategy"],
                    }
                )
                previous = {
                    "category": "schema",
                    "detail": "stage_exact_fields",
                    "metrics": {"expected_field_count": 1 if stage != "R" else 2},
                }
            if stage_hashes[0] == stage_hashes[1]:
                raise RuntimeError("v5 retry payload is not substantive")
    if len(hashes) != 762 or len(set(hashes)) != len(hashes):
        raise RuntimeError("v5 dry request identity collision")
    return {
        "status": "AUTHORIZED_ZERO_NETWORK_SUBSTANTIVE_RETRY_DRY_RUN_COMPLETE",
        "network_calls": 0,
        "api_key_read": False,
        "inherited_slots_not_called": 1,
        "new_fixed_slots": 127,
        "fixed_candidate_denominator": 256,
        "planned_dry_requests": len(hashes),
        "request_plan_sha256": _digest("\n".join(hashes).encode()),
        "strategy_plan_sha256": _digest(canonical_json(strategy_rows).encode()),
    }


def _digest(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()


def seal() -> dict[str, Any]:
    if OUTPUT_ROOT.exists():
        raise RuntimeError("R2 source recovery v5 preparation exists; refusing overwrite")
    assert_no_v5_live_root_before_seal()
    verify_preregistration()
    verify_append_only_inputs()
    if sha256_file(PARSER_SOURCE) != EXPECTED_PARSER_SOURCE_SHA:
        raise RuntimeError("frozen parser source drift")
    if sha256_file(R2_PREREG) != EXPECTED_R2_PREREG_SHA:
        raise RuntimeError("scientific preregistration drift")
    if sha256_file(V1_PREP / "slot_registry.jsonl") != EXPECTED_SLOT_REGISTRY_SHA:
        raise RuntimeError("fixed slot mapping drift")
    exclusion = json.loads(EXCLUSION.read_text(encoding="utf-8"))
    _inherited, inheritance_receipt = verify_inherited_v4_proposal(V4_LIVE, exclusion)
    dry_run = _dry_request_plan()

    OUTPUT_ROOT.mkdir(parents=True, mode=0o700)
    write_json(OUTPUT_ROOT / "inherited_r2src_001_verification.json", inheritance_receipt)
    _sidecar(OUTPUT_ROOT / "inherited_r2src_001_verification.json")
    write_json(OUTPUT_ROOT / "dry_run.json", dry_run)
    _sidecar(OUTPUT_ROOT / "dry_run.json")
    inputs = [
        SPEC,
        AUTHORIZATION,
        R2_PREREG,
        EXCLUSION,
        PARSER_SOURCE,
        V1_PREP / "slot_registry.jsonl",
        *APPEND_ONLY_INPUTS,
        *(REPO_ROOT / relative for relative in CODE),
        OUTPUT_ROOT / "inherited_r2src_001_verification.json",
        OUTPUT_ROOT / "dry_run.json",
    ]
    files = []
    for path in inputs:
        if not path.is_file():
            raise RuntimeError(f"missing v5 recovery input: {path}")
        files.append(
            {
                "path": str(path.relative_to(REPO_ROOT)),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    for relative in CODE:
        source = REPO_ROOT / relative
        snapshot = OUTPUT_ROOT / "code_snapshot" / relative
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, snapshot)
        files.append(
            {
                "path": str(snapshot.relative_to(REPO_ROOT)),
                "size_bytes": snapshot.stat().st_size,
                "sha256": sha256_file(snapshot),
                "snapshot_of": relative,
            }
        )
    manifest = {
        "research_id": "ROBUST-FUSION-R2-2026-08-29",
        "source_protocol_id": SOURCE_PROTOCOL_ID_V5,
        "prompt_contract_id": PROMPT_CONTRACT_ID_V5,
        "status": "AUTHORIZED_CONSERVATIVE_V5_SEALED",
        "sealed_before_any_v5_provider_response": True,
        "network_calls_at_seal": 0,
        "api_key_read_at_seal": False,
        "scientific_prereg_changed": False,
        "parser_changed": False,
        "fixed_slots": 128,
        "inherited_v4_slots": 1,
        "new_v5_slots": 127,
        "fixed_candidate_denominator": 256,
        "slot_002_starts_with_fresh_r": True,
        "permanent_lock_rule": "FIRST_COMPLETE_MECHANICALLY_VALID_OBJECT_ONLY",
        "files": files,
    }
    write_json(OUTPUT_ROOT / "manifest.json", manifest)
    _sidecar(OUTPUT_ROOT / "manifest.json")
    lock = {
        "status": "SEALED_BEFORE_ANY_V5_SOURCE_API_RESPONSE",
        "manifest_sha256": sha256_file(OUTPUT_ROOT / "manifest.json"),
        "parser_source_sha256": sha256_file(PARSER_SOURCE),
        "scientific_preregistration_manifest_sha256": sha256_file(R2_PREREG),
        "slot_registry_sha256": sha256_file(V1_PREP / "slot_registry.jsonl"),
        "append_only_input_hashes": {
            str(path.relative_to(REPO_ROOT)): digest for path, digest in APPEND_ONLY_INPUTS.items()
        },
        "sealed_at_unix_ns": time.time_ns(),
        "external_timestamp_claimed": False,
    }
    write_json(OUTPUT_ROOT / "lock.json", lock)
    _sidecar(OUTPUT_ROOT / "lock.json")
    receipt = {
        "receipt_type": "local_result_before_conservative_v5_source_recovery_receipt",
        "manifest_sha256": sha256_file(OUTPUT_ROOT / "manifest.json"),
        "lock_sha256": sha256_file(OUTPUT_ROOT / "lock.json"),
        "network_calls": 0,
        "api_key_read": False,
        "v5_live_root_present_at_seal": False,
    }
    write_json(OUTPUT_ROOT / "receipt.json", receipt)
    _sidecar(OUTPUT_ROOT / "receipt.json")
    return {**lock, "receipt_sha256": sha256_file(OUTPUT_ROOT / "receipt.json")}


def verify() -> dict[str, Any]:
    manifest = json.loads((OUTPUT_ROOT / "manifest.json").read_text(encoding="utf-8"))
    for row in manifest["files"]:
        path = REPO_ROOT / row["path"]
        if path.stat().st_size != row["size_bytes"] or sha256_file(path) != row["sha256"]:
            raise RuntimeError(f"sealed source recovery v5 drift: {row['path']}")
    lock = json.loads((OUTPUT_ROOT / "lock.json").read_text(encoding="utf-8"))
    if lock["manifest_sha256"] != sha256_file(OUTPUT_ROOT / "manifest.json"):
        raise RuntimeError("source recovery v5 manifest/lock drift")
    verify_append_only_inputs()
    return lock


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("seal", "verify"))
    args = parser.parse_args()
    result = seal() if args.command == "seal" else verify()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
