#!/usr/bin/env python3
"""Seal EP-planned R2 source recovery v6 before any v6 provider response."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.r2_source_generation import (
    EXPECTED_BASE_URL,
    build_slot_registry,
    canonical_json,
)
from linkrag_eval.robust_fusion.r2_source_recovery_v6 import (
    EP_OPERATION_WHITELIST,
    EXPECTED_MODEL_V6,
    PROMPT_CONTRACT_ID_V6,
    SOURCE_PROTOCOL_ID_V6,
    build_request_v6,
    validate_ep_plan,
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
from scripts.prepare_robust_fusion_r2_source_recovery_v5 import (
    verify as verify_v5_preparation,
)
from scripts.run_robust_fusion_r2_measurement import verify_preregistration

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_preparation_v6/"
    "robust-fusion-r2-source-recovery-preparation-v6-20260829"
)
LIVE_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_v6/robust-fusion-r2-source-recovery-v6-20260829"
)
SPEC = REPO_ROOT / "docs/plans/robust-fusion-r2-source-recovery-v6.md"
AUTHORIZATION = REPO_ROOT / "docs/plans/robust-fusion-r2-source-authorization-amendment-v2.json"
R2_PREREG = REPO_ROOT / (
    "runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/"
    "preregistration/manifest.json"
)
EXCLUSION = REPO_ROOT / (
    "runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/"
    "exclusions/registry.json"
)
V4_LIVE = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_v4/robust-fusion-r2-source-recovery-v4-20260829"
)
V5_PREP = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_preparation_v5/"
    "robust-fusion-r2-source-recovery-preparation-v5-20260829"
)
V5_LIVE = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_v5/robust-fusion-r2-source-recovery-v5-20260829"
)
V5_FAILURE_REPORT = (
    REPO_ROOT / "docs/reports/robust_fusion_r2_source_recovery_v5_failure_2026_08_29.md"
)
APPEND_ONLY_INPUTS = {
    V5_PREP / "manifest.json": "6d01a708a1d30ceace22ac17223a3d8047751fb1df675eb7fa061e87a91bc038",
    V5_PREP / "lock.json": "d55ccccbc9a6a540b22227c2cafe5af11e4f008c3c14be43149b99e561b2b165",
    V5_PREP / "receipt.json": "66631541053704f3085393bda77a8c649868b3b18643f252231f37ac71bfa779",
    V5_PREP / "inherited_r2src_001_verification.json": (
        "b347b929aa7bfd949d84cbce2e37ee106ba4ad127e1039d3600d5c0c244fde2a"
    ),
    V5_PREP / "dry_run.json": ("bba4025c5d51b8dc359dbc421c8711d8f37c6187068f893af3841fe6b078514a"),
    V5_LIVE / "authorization_receipt_snapshot.json": (
        "cbe3909bda4f2d9e393a1b0256cb3077abca2d1ecedab66855150239c44123b1"
    ),
    V5_LIVE / "call_audit.jsonl": (
        "39cdbffbd7b79c858c7908d9e479ebdbf838add46a029f5e449d07674157c2ba"
    ),
    V5_LIVE / "response_archive_synthetic_only.jsonl": (
        "686b23926155baff47cc54b21e777e4792cb5e85b50919e4fd7ebee08af6c4d0"
    ),
    V5_LIVE / "attempt_scoped_stage_locks.jsonl": (
        "db7fb342373d03abb1f1bc5db8937d7897f14d66745e4f5828a0481213cffced"
    ),
    V5_LIVE / "complete_assembly_attempts_not_truth.jsonl": (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ),
    V5_LIVE / "accepted_proposals_not_truth.jsonl": (
        "d1e15f11394ed15e2db8248987ba50310472ce206bb433d835144c7c6c98ee6b"
    ),
    V5_LIVE / "inherited_r2src_001_hard_lock.json": (
        "b347b929aa7bfd949d84cbce2e37ee106ba4ad127e1039d3600d5c0c244fde2a"
    ),
    V5_LIVE / "terminal_error.json": (
        "5d8e88cbae6f12fb0ebe986415053bed514e0989bb4c0a4d23372e03ae46e3df"
    ),
    V5_FAILURE_REPORT: "fda4e5b6864a34b29cd6e3230eb6fb4bb65a3ab07ea087e57ddf67ea203b2ead",
}
CODE = (
    "src/linkrag_eval/robust_fusion/r2_source_recovery_v6.py",
    "scripts/prepare_robust_fusion_r2_source_recovery_v6.py",
    "scripts/run_robust_fusion_r2_source_recovery_v6.py",
    "tests/unit/test_robust_fusion_r2_source_recovery_v6.py",
)


def _sidecar(path: Path) -> None:
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{sha256_file(path)}  {path.name}\n", encoding="utf-8"
    )


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def verify_append_only_inputs() -> None:
    verify_v5_preparation()
    for path, expected in APPEND_ONLY_INPUTS.items():
        if sha256_file(path) != expected:
            raise RuntimeError(f"v2-v5 append-only evidence drift: {path.relative_to(REPO_ROOT)}")


def assert_no_v6_live_root_before_seal(path: Path = LIVE_ROOT) -> None:
    if path.exists():
        raise RuntimeError("v6 live root exists before seal; refusing retrospective seal")


def endpoint_model_contract() -> dict[str, Any]:
    slot = build_slot_registry()[1]
    body = build_request_v6(
        slot,
        stage="R",
        orchestration_attempt=1,
        response_attempt=1,
        locked_fields={},
        previous_failure=None,
    )
    required = {
        "model",
        "messages",
        "thinking",
        "response_format",
        "stream",
        "temperature",
        "top_p",
        "max_tokens",
    }
    if set(body) != required or body["model"] != EXPECTED_MODEL_V6:
        raise RuntimeError("v6 endpoint/model request schema drift")
    return {
        "status": "STATIC_ENDPOINT_MODEL_REQUEST_CONTRACT_PASS",
        "http_method": "POST",
        "base_url": EXPECTED_BASE_URL,
        "model_field": EXPECTED_MODEL_V6,
        "non_thinking": body["thinking"] == {"type": "disabled"},
        "json_mode": body["response_format"] == {"type": "json_object"},
        "request_body_sha256": _digest(canonical_json(body).encode()),
        "provider_probe_calls": 0,
        "network_calls": 0,
        "api_key_read": False,
        "model_availability_claimed_before_live_call": False,
    }


def _synthetic_context(slot: dict[str, Any]) -> tuple[str, str, dict[str, str], str]:
    if slot["language"] == "zh":
        reference = "雾桥凭证" + "甲乙丙丁戊己庚辛壬癸" * (
            7 if slot["length_stratum"] == "short" else 20
        )
        query = "这项完全虚构的规则是什么？"
        source_span = "雾桥凭证"
        replacement_span = "澄湾凭据"
        equivalent = "甲" + reference[1:]
    else:
        count = 40 if slot["length_stratum"] == "short" else 120
        reference = " ".join(f"synthetic{index}" for index in range(count))
        query = "What is this entirely fictional rule?"
        source_span = "synthetic1"
        replacement_span = "fictional1"
        equivalent = "fictional0 " + " ".join(reference.split()[1:])
    plan = {
        "operation_type": EP_OPERATION_WHITELIST[int(slot["edit_level"])][0],
        "source_span": source_span,
        "replacement_span": replacement_span,
    }
    return query, reference, plan, equivalent


def dry_request_plan() -> dict[str, Any]:
    hashes: list[str] = []
    rows: list[dict[str, Any]] = []
    for slot in build_slot_registry()[1:]:
        query, reference, plan, equivalent = _synthetic_context(slot)
        for stage, locked in (
            ("R", {}),
            ("EP", {"query": query, "reference": reference}),
            ("E", {"query": query, "reference": reference, "ep_plan": plan}),
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
            pair = []
            for response_attempt in (1, 2):
                body = build_request_v6(
                    slot,
                    stage=stage,
                    orchestration_attempt=1,
                    response_attempt=response_attempt,
                    locked_fields=locked,
                    previous_failure=previous,
                )
                if body["model"] != EXPECTED_MODEL_V6:
                    raise RuntimeError("v6 dry request model drift")
                digest = _digest(canonical_json(body).encode())
                hashes.append(digest)
                pair.append(digest)
                prompt = json.loads(body["messages"][1]["content"])
                rows.append(
                    {
                        "slot_id": slot["slot_id"],
                        "stage": stage,
                        "response_attempt": response_attempt,
                        "model": body["model"],
                        "request_sha256": digest,
                        "scheduled_strategy": prompt["recovery_directive"]["scheduled_strategy"],
                    }
                )
                previous = {
                    "category": "schema",
                    "detail": "stage_exact_fields",
                    "metrics": {"expected_field_count": 3 if stage == "EP" else 1},
                }
            if pair[0] == pair[1]:
                raise RuntimeError("v6 retry payload is not substantive")
    if len(hashes) != 1016 or len(set(hashes)) != len(hashes):
        raise RuntimeError("v6 dry request identity collision")
    fixture_slot = build_slot_registry()[1]
    _query, fixture_reference, fixture_plan, _equivalent = _synthetic_context(fixture_slot)
    validate_ep_plan(
        json.dumps(fixture_plan, ensure_ascii=False),
        slot=fixture_slot,
        reference=fixture_reference,
    )
    return {
        "status": "AUTHORIZED_ZERO_NETWORK_EP_PLANNED_DRY_RUN_COMPLETE",
        "network_calls": 0,
        "provider_probe_calls": 0,
        "api_key_read": False,
        "inherited_slots_not_called": 1,
        "new_fixed_slots": 127,
        "fixed_candidate_denominator": 256,
        "planned_dry_requests": len(hashes),
        "request_plan_sha256": _digest("\n".join(hashes).encode()),
        "strategy_plan_sha256": _digest(canonical_json(rows).encode()),
        "programmatic_text_rewriting_performed": False,
    }


def seal() -> dict[str, Any]:
    if OUTPUT_ROOT.exists():
        raise RuntimeError("R2 source recovery v6 preparation exists; refusing overwrite")
    assert_no_v6_live_root_before_seal()
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
    inheritance_receipt = {
        **inheritance_receipt,
        "generator_model": "deepseek-v4-flash",
        "generator_source_protocol_id": ("ROBUST-FUSION-R2-SOURCE-RECOVERY-2026-08-29-v4"),
    }
    endpoint_contract = endpoint_model_contract()
    dry_run = dry_request_plan()

    OUTPUT_ROOT.mkdir(parents=True, mode=0o700)
    write_json(OUTPUT_ROOT / "inherited_r2src_001_verification.json", inheritance_receipt)
    _sidecar(OUTPUT_ROOT / "inherited_r2src_001_verification.json")
    write_json(OUTPUT_ROOT / "endpoint_model_contract.json", endpoint_contract)
    _sidecar(OUTPUT_ROOT / "endpoint_model_contract.json")
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
        OUTPUT_ROOT / "endpoint_model_contract.json",
        OUTPUT_ROOT / "dry_run.json",
    ]
    files = []
    for path in inputs:
        if not path.is_file():
            raise RuntimeError(f"missing v6 recovery input: {path}")
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
        "source_protocol_id": SOURCE_PROTOCOL_ID_V6,
        "prompt_contract_id": PROMPT_CONTRACT_ID_V6,
        "status": "AUTHORIZED_OUTCOME_AWARE_ENGINEERING_V6_SEALED",
        "sealed_before_any_v6_provider_response": True,
        "network_calls_at_seal": 0,
        "provider_probe_calls_at_seal": 0,
        "api_key_read_at_seal": False,
        "scientific_prereg_changed": False,
        "parser_changed": False,
        "fixed_slots": 128,
        "inherited_flash_slots": 1,
        "new_pro_slots": 127,
        "fixed_candidate_denominator": 256,
        "slot_002_starts_with_fresh_r": True,
        "stage_order": ["R", "EP", "E", "C"],
        "permanent_lock_rule": "FIRST_COMPLETE_MECHANICALLY_VALID_OBJECT_ONLY",
        "programmatic_text_rewriting_allowed": False,
        "files": files,
    }
    write_json(OUTPUT_ROOT / "manifest.json", manifest)
    _sidecar(OUTPUT_ROOT / "manifest.json")
    lock = {
        "status": "SEALED_BEFORE_ANY_V6_SOURCE_API_RESPONSE",
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
        "receipt_type": "local_result_before_ep_planned_v6_source_recovery_receipt",
        "manifest_sha256": sha256_file(OUTPUT_ROOT / "manifest.json"),
        "lock_sha256": sha256_file(OUTPUT_ROOT / "lock.json"),
        "network_calls": 0,
        "provider_probe_calls": 0,
        "api_key_read": False,
        "v6_live_root_present_at_seal": False,
    }
    write_json(OUTPUT_ROOT / "receipt.json", receipt)
    _sidecar(OUTPUT_ROOT / "receipt.json")
    return {**lock, "receipt_sha256": sha256_file(OUTPUT_ROOT / "receipt.json")}


def verify() -> dict[str, Any]:
    manifest = json.loads((OUTPUT_ROOT / "manifest.json").read_text(encoding="utf-8"))
    for row in manifest["files"]:
        path = REPO_ROOT / row["path"]
        if path.stat().st_size != row["size_bytes"] or sha256_file(path) != row["sha256"]:
            raise RuntimeError(f"sealed source recovery v6 drift: {row['path']}")
    lock = json.loads((OUTPUT_ROOT / "lock.json").read_text(encoding="utf-8"))
    if lock["manifest_sha256"] != sha256_file(OUTPUT_ROOT / "manifest.json"):
        raise RuntimeError("source recovery v6 manifest/lock drift")
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
