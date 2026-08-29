#!/usr/bin/env python3
"""Seal prompt-only R2 source recovery v3 before any v3 provider response."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.r2_source_generation import (
    build_slot_registry,
    parse_and_validate_proposal,
)
from linkrag_eval.robust_fusion.r2_source_recovery_v3 import (
    PROMPT_CONTRACT_ID_V3,
    SOURCE_PROTOCOL_ID_V3,
    build_request_v3,
)
from linkrag_eval.robust_fusion.similarity_dev_calibration import sha256_file, write_json
from scripts.prepare_robust_fusion_r2_source_execution_v2 import verify as verify_v2_preparation
from scripts.prepare_robust_fusion_r2_source_generation import verify as verify_v1_preparation
from scripts.run_robust_fusion_r2_measurement import verify_preregistration

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_preparation_v3/"
    "robust-fusion-r2-source-recovery-preparation-v3-20260829"
)
SPEC = REPO_ROOT / "docs/plans/robust-fusion-r2-source-recovery-v3.md"
FAILURE_RECORD = REPO_ROOT / (
    "docs/reports/robust_fusion_r2_source_execution_v2_failure_2026_08_29.json"
)
AUTHORIZATION = REPO_ROOT / "docs/plans/robust-fusion-r2-source-authorization-amendment-v2.json"
R2_PREREG = REPO_ROOT / (
    "runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/"
    "preregistration/manifest.json"
)
EXCLUSION = REPO_ROOT / (
    "runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/"
    "exclusions/registry.json"
)
V1_PREP = REPO_ROOT / (
    "runs/robust_fusion/r2_source_generation_preparation_v1/"
    "robust-fusion-r2-source-generation-preparation-v1-20260829"
)
V2_PREP = REPO_ROOT / (
    "runs/robust_fusion/r2_source_execution_preparation_v2/"
    "robust-fusion-r2-source-execution-preparation-v2-20260829"
)
V2_LIVE = REPO_ROOT / (
    "runs/robust_fusion/r2_source_execution_v2/robust-fusion-r2-source-execution-v2-20260829"
)
V2_LIVE_HASHES = {
    "authorization_receipt_snapshot.json": (
        "18a214a599d632921b46a8d75bf7147181382b43eff5f96d0613746323439ef2"
    ),
    "call_audit.jsonl": "bbbb578a74f491630e5a69d7e056dca678ad3f63adb840f4d314d6482d712483",
    "response_archive_synthetic_only.jsonl": (
        "79e7f2bb1ac09b33cedc9ae2fef7e9ec7e115514e2fe43b108f72fa2d4e4a447"
    ),
    "accepted_proposals_not_truth.jsonl": (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ),
    "terminal_error.json": "417b4a2d441f0f45d3ff3d4626b0db578f976218c48d6cec15b635ceaa603a92",
}
PARSER_SOURCE = REPO_ROOT / "src/linkrag_eval/robust_fusion/r2_source_generation.py"
EXPECTED_PARSER_SOURCE_SHA = "34ba67706fb5ddb0b7ac7924b153e00c8f26ca34f60914bd31cdf7efd57de65c"
EXPECTED_R2_PREREG_SHA = "b3c75dee6140c7aa57b865e592054ff5534405872efef4769b9636cccd09c71b"
EXPECTED_SLOT_REGISTRY_SHA = "c717641388cf0264ff75b17bec4d4b986a32a309fc6dfe8ab7b13ccbafc29f37"
CODE = (
    "src/linkrag_eval/robust_fusion/r2_source_recovery_v3.py",
    "scripts/prepare_robust_fusion_r2_source_recovery_v3.py",
    "scripts/run_robust_fusion_r2_source_recovery_v3.py",
    "tests/unit/test_robust_fusion_r2_source_recovery_v3.py",
)


def _sidecar(path: Path) -> None:
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{sha256_file(path)}  {path.name}\n", encoding="utf-8"
    )


def verify_v2_append_only() -> None:
    for name, expected in V2_LIVE_HASHES.items():
        if sha256_file(V2_LIVE / name) != expected:
            raise RuntimeError(f"v2 append-only evidence drift: {name}")


def _dry_fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    slot = build_slot_registry()[0]
    fixture = {
        "slot_id": slot["slot_id"],
        "dataset_role": slot["dataset_role"],
        "language": slot["language"],
        "length_stratum": slot["length_stratum"],
        "conflict_type": slot["conflict_type"],
        "edit_level": slot["edit_level"],
        "query": "雾桥镇的灯塔维护券何时启用，每户每季能领取几张？",
        "reference": "雾桥镇公共事务所公告，灯塔维护券自二〇二七年五月起启用，登记家庭每季度最多领取两张，并须在月底前在线确认。",
        "equivalent_candidate": "雾桥镇公共事务所说明，灯塔维护券自二〇二七年五月起启用，登记家庭每季度最多申领两张，并须于月底前线上确认。",
        "factual_conflict_candidate": "雾桥镇公共事务所通告，灯塔维护券自二〇二七年五月起启用，登记家庭每季度最多领取五张，并须在月底前在线确认。",
    }
    exclusion = json.loads(EXCLUSION.read_text(encoding="utf-8"))
    parsed = parse_and_validate_proposal(
        json.dumps(fixture, ensure_ascii=False),
        slot=slot,
        exclusion_registry=exclusion,
    )
    return fixture, {
        "status": "DRY_STRUCTURAL_FIXTURE_PASS",
        "proposal_sha256": parsed["proposal_sha256"],
        "truth_status": parsed["truth_status"],
        "provider_calls": 0,
    }


def seal() -> dict[str, Any]:
    if OUTPUT_ROOT.exists():
        raise RuntimeError("R2 source recovery v3 preparation exists; refusing overwrite")
    verify_preregistration()
    verify_v1_preparation()
    verify_v2_preparation()
    verify_v2_append_only()
    if sha256_file(PARSER_SOURCE) != EXPECTED_PARSER_SOURCE_SHA:
        raise RuntimeError("frozen parser source drift")
    if sha256_file(R2_PREREG) != EXPECTED_R2_PREREG_SHA:
        raise RuntimeError("scientific preregistration drift")
    if sha256_file(V1_PREP / "slot_registry.jsonl") != EXPECTED_SLOT_REGISTRY_SHA:
        raise RuntimeError("fixed slot mapping drift")
    first_request = build_request_v3(build_slot_registry()[0], attempt=1, prior_failure=None)
    serialized = json.dumps(first_request, ensure_ascii=False)
    required_prompt_terms = (
        "pairwise_distinct",
        "never copy reference",
        "syntactic reordering",
        "change exactly one numeric factual slot",
    )
    if any(term not in serialized for term in required_prompt_terms):
        raise RuntimeError("v3 prompt contract is incomplete")
    fixture, fixture_receipt = _dry_fixture()
    OUTPUT_ROOT.mkdir(parents=True, mode=0o700)
    write_json(OUTPUT_ROOT / "dry_structural_fixture.json", fixture)
    _sidecar(OUTPUT_ROOT / "dry_structural_fixture.json")
    write_json(OUTPUT_ROOT / "dry_structural_fixture_receipt.json", fixture_receipt)
    _sidecar(OUTPUT_ROOT / "dry_structural_fixture_receipt.json")
    inputs = [
        SPEC,
        FAILURE_RECORD,
        AUTHORIZATION,
        R2_PREREG,
        EXCLUSION,
        PARSER_SOURCE,
        V1_PREP / "slot_registry.jsonl",
        V2_PREP / "manifest.json",
        V2_PREP / "lock.json",
        *(V2_LIVE / name for name in V2_LIVE_HASHES),
        *(REPO_ROOT / row for row in CODE),
        OUTPUT_ROOT / "dry_structural_fixture.json",
        OUTPUT_ROOT / "dry_structural_fixture_receipt.json",
    ]
    files = []
    for path in inputs:
        if not path.is_file():
            raise RuntimeError(f"missing v3 recovery input: {path}")
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
        "source_protocol_id": SOURCE_PROTOCOL_ID_V3,
        "prompt_contract_id": PROMPT_CONTRACT_ID_V3,
        "status": "AUTHORIZED_PROMPT_ONLY_V3_SEALED",
        "sealed_before_any_v3_provider_response": True,
        "network_calls_at_seal": 0,
        "api_key_read_at_seal": False,
        "scientific_prereg_changed": False,
        "parser_changed": False,
        "fixed_slots": 128,
        "fixed_candidate_denominator": 256,
        "files": files,
    }
    write_json(OUTPUT_ROOT / "manifest.json", manifest)
    _sidecar(OUTPUT_ROOT / "manifest.json")
    lock = {
        "status": "SEALED_BEFORE_ANY_V3_SOURCE_API_RESPONSE",
        "manifest_sha256": sha256_file(OUTPUT_ROOT / "manifest.json"),
        "parser_source_sha256": sha256_file(PARSER_SOURCE),
        "v2_append_only_hashes": V2_LIVE_HASHES,
        "sealed_at_unix_ns": time.time_ns(),
        "external_timestamp_claimed": False,
    }
    write_json(OUTPUT_ROOT / "lock.json", lock)
    _sidecar(OUTPUT_ROOT / "lock.json")
    receipt = {
        "receipt_type": "local_result_before_prompt_only_recovery_receipt",
        "manifest_sha256": sha256_file(OUTPUT_ROOT / "manifest.json"),
        "lock_sha256": sha256_file(OUTPUT_ROOT / "lock.json"),
        "network_calls": 0,
        "api_key_read": False,
    }
    write_json(OUTPUT_ROOT / "receipt.json", receipt)
    _sidecar(OUTPUT_ROOT / "receipt.json")
    return {**lock, "receipt_sha256": sha256_file(OUTPUT_ROOT / "receipt.json")}


def verify() -> dict[str, Any]:
    manifest = json.loads((OUTPUT_ROOT / "manifest.json").read_text(encoding="utf-8"))
    for row in manifest["files"]:
        path = REPO_ROOT / row["path"]
        if path.stat().st_size != row["size_bytes"] or sha256_file(path) != row["sha256"]:
            raise RuntimeError(f"sealed source recovery v3 drift: {row['path']}")
    lock = json.loads((OUTPUT_ROOT / "lock.json").read_text(encoding="utf-8"))
    if lock["manifest_sha256"] != sha256_file(OUTPUT_ROOT / "manifest.json"):
        raise RuntimeError("source recovery v3 manifest/lock drift")
    verify_v2_append_only()
    return lock


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("seal", "verify"))
    args = parser.parse_args()
    result = seal() if args.command == "seal" else verify()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
