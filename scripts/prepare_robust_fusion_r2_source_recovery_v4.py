#!/usr/bin/env python3
"""Seal staged R2 source recovery v4 before any v4 provider response."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.r2_source_generation import build_slot_registry, canonical_json
from linkrag_eval.robust_fusion.r2_source_recovery_v4 import (
    PROMPT_CONTRACT_ID_V4,
    SOURCE_PROTOCOL_ID_V4,
    build_request_v4,
    validate_complete_proposal,
    validate_stage_response,
)
from linkrag_eval.robust_fusion.similarity_dev_calibration import sha256_file, write_json
from scripts.prepare_robust_fusion_r2_source_recovery_v3 import (
    EXPECTED_PARSER_SOURCE_SHA,
    EXPECTED_R2_PREREG_SHA,
    EXPECTED_SLOT_REGISTRY_SHA,
    PARSER_SOURCE,
    V1_PREP,
    verify_v2_append_only,
)
from scripts.prepare_robust_fusion_r2_source_recovery_v3 import (
    verify as verify_v3_preparation,
)
from scripts.run_robust_fusion_r2_measurement import verify_preregistration

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_preparation_v4/"
    "robust-fusion-r2-source-recovery-preparation-v4-20260829"
)
LIVE_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_v4/"
    "robust-fusion-r2-source-recovery-v4-20260829"
)
SPEC = REPO_ROOT / "docs/plans/robust-fusion-r2-source-recovery-v4.md"
AUTHORIZATION = REPO_ROOT / "docs/plans/robust-fusion-r2-source-authorization-amendment-v2.json"
R2_PREREG = REPO_ROOT / (
    "runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/"
    "preregistration/manifest.json"
)
EXCLUSION = REPO_ROOT / (
    "runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/"
    "exclusions/registry.json"
)
V3_PREP = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_preparation_v3/"
    "robust-fusion-r2-source-recovery-preparation-v3-20260829"
)
V3_LIVE = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_v3/"
    "robust-fusion-r2-source-recovery-v3-20260829"
)
V3_DIAGNOSTIC = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_v3_diagnostic_v1/"
    "robust-fusion-r2-source-recovery-v3-diagnostic-v1-20260829"
)
V3_APPEND_ONLY_FILES = {
    V3_PREP / "manifest.json": "d1861e1b0b932146296fbd3bdbfae370a5a295dd13a620dd38f6744b76d5036f",
    V3_PREP / "lock.json": "36aafea973cadc80c95922e5377af306d3a7c7a4287d62a19be73d76d7686e13",
    V3_PREP / "receipt.json": "51d8065fa1a5b1e150abe2d176f740db001f4ce3d201fabee118f83b5bc12e6c",
    V3_LIVE / "authorization_receipt_snapshot.json": (
        "5c77c3736219d15d43d6ebcf656553bba40add01786c9ad432889ccdca108681"
    ),
    V3_LIVE / "call_audit.jsonl": (
        "33462e2e73e264f42ea741698295b1e8e8017b63463aa6000374580ece023e86"
    ),
    V3_LIVE / "response_archive_synthetic_only.jsonl": (
        "e5eb7aa6062ab8a0113769da83c48da144588cb3c79ca24a588ab094e557d821"
    ),
    V3_LIVE / "accepted_proposals_not_truth.jsonl": (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    ),
    V3_LIVE / "coordinator_stop_decision.json": (
        "c9913338e53fae26e65c9e6a9e7a961ed40b6f0b9c48d21651695339f75800ac"
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
}
CODE = (
    "src/linkrag_eval/robust_fusion/r2_source_recovery_v4.py",
    "scripts/prepare_robust_fusion_r2_source_recovery_v4.py",
    "scripts/run_robust_fusion_r2_source_recovery_v4.py",
    "tests/unit/test_robust_fusion_r2_source_recovery_v4.py",
)


def _sidecar(path: Path) -> None:
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{sha256_file(path)}  {path.name}\n", encoding="utf-8"
    )


def verify_v3_append_only() -> None:
    verify_v2_append_only()
    for path, expected in V3_APPEND_ONLY_FILES.items():
        if sha256_file(path) != expected:
            raise RuntimeError(f"v3 append-only evidence drift: {path.relative_to(REPO_ROOT)}")


def assert_no_v4_live_root_before_seal(path: Path = LIVE_ROOT) -> None:
    if path.exists():
        raise RuntimeError("v4 live root exists before seal; refusing retrospective seal")


def _dry_fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    slot = build_slot_registry()[0]
    values = {
        "query": "雾桥镇的灯塔维护券何时启用，每户每季能领取几张？",
        "reference": (
            "雾桥镇公共事务所公告，灯塔维护券自二〇二七年五月起启用，"
            "登记家庭每季度最多领取两张，并须在月底前在线确认。"
        ),
        "equivalent_candidate": (
            "雾桥镇公共事务所说明，灯塔维护券自二〇二七年五月起启用，"
            "登记家庭每季度最多申领两张，并须于月底前线上确认。"
        ),
        "factual_conflict_candidate": (
            "雾桥镇公共事务所通告，灯塔维护券自二〇二七年五月起启用，"
            "登记家庭每季度最多领取五张，并须在月底前在线确认。"
        ),
    }
    exclusion = json.loads(EXCLUSION.read_text(encoding="utf-8"))
    locked: dict[str, str] = {}
    for stage, fields in (
        ("R", {key: values[key] for key in ("query", "reference")}),
        ("E", {"equivalent_candidate": values["equivalent_candidate"]}),
        ("C", {"factual_conflict_candidate": values["factual_conflict_candidate"]}),
    ):
        locked.update(
            validate_stage_response(
                json.dumps(fields, ensure_ascii=False),
                slot=slot,
                stage=stage,
                locked_fields=locked,
                exclusion_registry=exclusion,
                accepted_proposals=[],
            )
        )
    proposal = validate_complete_proposal(
        slot,
        locked,
        exclusion_registry=exclusion,
        accepted_proposals=[],
    )
    return values, {
        "status": "DRY_THREE_STAGE_STRUCTURAL_FIXTURE_PASS",
        "proposal_sha256": proposal["proposal_sha256"],
        "provider_calls": 0,
        "semantic_truth_assigned": False,
    }


def _dry_request_plan() -> dict[str, Any]:
    hashes = []
    for slot in build_slot_registry():
        if slot["language"] == "zh":
            reference = "甲" * (80 if slot["length_stratum"] == "short" else 220)
            query = "这项完全虚构的规则是什么？"
            equivalent = "乙" + reference[1:]
        else:
            words = 40 if slot["length_stratum"] == "short" else 120
            reference = " ".join(["synthetic"] * words)
            query = "What is this entirely fictional rule?"
            equivalent = "fictional " + " ".join(reference.split()[1:])
        locked: dict[str, str] = {}
        for stage in ("R", "E", "C"):
            body = build_request_v4(
                slot,
                stage=stage,
                orchestration_attempt=1,
                response_attempt=1,
                locked_fields=locked,
            )
            hashes.append(sha256_file_bytes(canonical_json(body).encode()))
            if stage == "R":
                locked.update({"query": query, "reference": reference})
            elif stage == "E":
                locked["equivalent_candidate"] = equivalent
    if len(hashes) != 384 or len(set(hashes)) != 384:
        raise RuntimeError("v4 dry request identity collision")
    return {
        "status": "AUTHORIZED_ZERO_NETWORK_THREE_STAGE_DRY_RUN_COMPLETE",
        "network_calls": 0,
        "api_key_read": False,
        "fixed_slots": 128,
        "fixed_candidate_denominator": 256,
        "stages": ["R", "E", "C"],
        "planned_first_attempt_requests": len(hashes),
        "request_plan_sha256": sha256_file_bytes("\n".join(hashes).encode()),
    }


def sha256_file_bytes(payload: bytes) -> str:
    import hashlib

    return hashlib.sha256(payload).hexdigest()


def seal() -> dict[str, Any]:
    if OUTPUT_ROOT.exists():
        raise RuntimeError("R2 source recovery v4 preparation exists; refusing overwrite")
    assert_no_v4_live_root_before_seal()
    verify_preregistration()
    verify_v3_preparation()
    verify_v3_append_only()
    if sha256_file(PARSER_SOURCE) != EXPECTED_PARSER_SOURCE_SHA:
        raise RuntimeError("frozen parser source drift")
    if sha256_file(R2_PREREG) != EXPECTED_R2_PREREG_SHA:
        raise RuntimeError("scientific preregistration drift")
    if sha256_file(V1_PREP / "slot_registry.jsonl") != EXPECTED_SLOT_REGISTRY_SHA:
        raise RuntimeError("fixed slot mapping drift")
    fixture, fixture_receipt = _dry_fixture()
    dry_run = _dry_request_plan()
    OUTPUT_ROOT.mkdir(parents=True, mode=0o700)
    write_json(OUTPUT_ROOT / "dry_three_stage_fixture.json", fixture)
    _sidecar(OUTPUT_ROOT / "dry_three_stage_fixture.json")
    write_json(OUTPUT_ROOT / "dry_three_stage_fixture_receipt.json", fixture_receipt)
    _sidecar(OUTPUT_ROOT / "dry_three_stage_fixture_receipt.json")
    write_json(OUTPUT_ROOT / "dry_run.json", dry_run)
    _sidecar(OUTPUT_ROOT / "dry_run.json")
    inputs = [
        SPEC,
        AUTHORIZATION,
        R2_PREREG,
        EXCLUSION,
        PARSER_SOURCE,
        V1_PREP / "slot_registry.jsonl",
        *V3_APPEND_ONLY_FILES,
        *(REPO_ROOT / relative for relative in CODE),
        OUTPUT_ROOT / "dry_three_stage_fixture.json",
        OUTPUT_ROOT / "dry_three_stage_fixture_receipt.json",
        OUTPUT_ROOT / "dry_run.json",
    ]
    files = []
    for path in inputs:
        if not path.is_file():
            raise RuntimeError(f"missing v4 recovery input: {path}")
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
        "source_protocol_id": SOURCE_PROTOCOL_ID_V4,
        "prompt_contract_id": PROMPT_CONTRACT_ID_V4,
        "status": "AUTHORIZED_THREE_STAGE_V4_SEALED",
        "sealed_before_any_v4_provider_response": True,
        "network_calls_at_seal": 0,
        "api_key_read_at_seal": False,
        "scientific_prereg_changed": False,
        "parser_changed": False,
        "fixed_slots": 128,
        "fixed_candidate_denominator": 256,
        "stage_lock_scope": "CURRENT_ORCHESTRATION_ATTEMPT_ONLY",
        "permanent_lock_rule": "FIRST_COMPLETE_MECHANICALLY_VALID_OBJECT_ONLY",
        "programmatic_text_rewriting_allowed": False,
        "files": files,
    }
    write_json(OUTPUT_ROOT / "manifest.json", manifest)
    _sidecar(OUTPUT_ROOT / "manifest.json")
    lock = {
        "status": "SEALED_BEFORE_ANY_V4_SOURCE_API_RESPONSE",
        "manifest_sha256": sha256_file(OUTPUT_ROOT / "manifest.json"),
        "parser_source_sha256": sha256_file(PARSER_SOURCE),
        "scientific_preregistration_manifest_sha256": sha256_file(R2_PREREG),
        "slot_registry_sha256": sha256_file(V1_PREP / "slot_registry.jsonl"),
        "v3_append_only_hashes": {
            str(path.relative_to(REPO_ROOT)): digest
            for path, digest in V3_APPEND_ONLY_FILES.items()
        },
        "sealed_at_unix_ns": time.time_ns(),
        "external_timestamp_claimed": False,
    }
    write_json(OUTPUT_ROOT / "lock.json", lock)
    _sidecar(OUTPUT_ROOT / "lock.json")
    receipt = {
        "receipt_type": "local_result_before_three_stage_source_recovery_receipt",
        "manifest_sha256": sha256_file(OUTPUT_ROOT / "manifest.json"),
        "lock_sha256": sha256_file(OUTPUT_ROOT / "lock.json"),
        "network_calls": 0,
        "api_key_read": False,
        "v4_live_root_present_at_seal": False,
    }
    write_json(OUTPUT_ROOT / "receipt.json", receipt)
    _sidecar(OUTPUT_ROOT / "receipt.json")
    return {**lock, "receipt_sha256": sha256_file(OUTPUT_ROOT / "receipt.json")}


def verify() -> dict[str, Any]:
    manifest = json.loads((OUTPUT_ROOT / "manifest.json").read_text(encoding="utf-8"))
    for row in manifest["files"]:
        path = REPO_ROOT / row["path"]
        if path.stat().st_size != row["size_bytes"] or sha256_file(path) != row["sha256"]:
            raise RuntimeError(f"sealed source recovery v4 drift: {row['path']}")
    lock = json.loads((OUTPUT_ROOT / "lock.json").read_text(encoding="utf-8"))
    if lock["manifest_sha256"] != sha256_file(OUTPUT_ROOT / "manifest.json"):
        raise RuntimeError("source recovery v4 manifest/lock drift")
    verify_v3_append_only()
    return lock


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("seal", "verify"))
    args = parser.parse_args()
    result = seal() if args.command == "seal" else verify()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
