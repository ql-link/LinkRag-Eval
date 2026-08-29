#!/usr/bin/env python3
"""Seal direct Codex authorship v7 before any R2SRC-003+ body is written."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.r2_source_authorship_v7 import (
    AUTHORIZATION_QUOTE,
    MODEL_ID,
    SOURCE_PROTOCOL_ID_V7,
    SOURCE_THREAD_ID,
    TASK_THREAD_ID,
    verify_inherited_v6_proposals,
)
from linkrag_eval.robust_fusion.r2_source_generation import (
    build_slot_registry,
    validate_slot_registry,
)
from linkrag_eval.robust_fusion.similarity_dev_calibration import (
    sha256_file,
    write_json,
    write_jsonl,
)
from scripts.prepare_robust_fusion_r2_source_recovery_v3 import (
    EXPECTED_PARSER_SOURCE_SHA,
    EXPECTED_R2_PREREG_SHA,
    EXPECTED_SLOT_REGISTRY_SHA,
    PARSER_SOURCE,
    V1_PREP,
)
from scripts.prepare_robust_fusion_r2_source_recovery_v6 import verify as verify_v6_preparation
from scripts.run_robust_fusion_r2_measurement import verify_preregistration

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_authorship_preparation_v7_codex/"
    "robust-fusion-r2-source-authorship-preparation-v7-codex-20260829"
)
LIVE_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_authorship_v7_codex/"
    "robust-fusion-r2-source-authorship-v7-codex-20260829"
)
SPEC = REPO_ROOT / "docs/plans/robust-fusion-r2-source-authorship-v7-codex.md"
V4_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_v4/robust-fusion-r2-source-recovery-v4-20260829"
)
V6_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_v6/robust-fusion-r2-source-recovery-v6-20260829"
)
V6_PREP = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_preparation_v6/"
    "robust-fusion-r2-source-recovery-preparation-v6-20260829"
)
EXCLUSION = REPO_ROOT / (
    "runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/"
    "exclusions/registry.json"
)
CODE_FILES = (
    "src/linkrag_eval/robust_fusion/r2_source_authorship_v7.py",
    "scripts/prepare_robust_fusion_r2_source_authorship_v7.py",
    "scripts/run_robust_fusion_r2_source_authorship_v7.py",
    "tests/unit/test_robust_fusion_r2_source_authorship_v7.py",
)


def _tree_manifest(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": str(path.relative_to(REPO_ROOT)),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def _sidecar(path: Path) -> None:
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{sha256_file(path)}  {path.name}\n", encoding="utf-8"
    )


def seal() -> dict[str, Any]:
    if OUTPUT_ROOT.exists() or LIVE_ROOT.exists():
        raise RuntimeError("v7 preparation/live root already exists; refusing retrospective seal")
    verify_v6_preparation()
    verify_preregistration()
    if sha256_file(PARSER_SOURCE) != EXPECTED_PARSER_SOURCE_SHA:
        raise RuntimeError("unchanged parser source drift")
    if sha256_file(V1_PREP / "slot_registry.jsonl") != EXPECTED_SLOT_REGISTRY_SHA:
        raise RuntimeError("sealed slot registry drift")
    prereg = REPO_ROOT / (
        "runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/"
        "preregistration/manifest.json"
    )
    if sha256_file(prereg) != EXPECTED_R2_PREREG_SHA:
        raise RuntimeError("scientific preregistration manifest drift")
    exclusion = json.loads(EXCLUSION.read_text(encoding="utf-8"))
    inherited, inherited_receipt = verify_inherited_v6_proposals(V4_ROOT, V6_ROOT, exclusion)
    slots = build_slot_registry()
    validate_slot_registry(slots)

    OUTPUT_ROOT.mkdir(parents=True, mode=0o700)
    snapshot = OUTPUT_ROOT / "code_snapshot"
    snapshot.mkdir()
    for relative in (str(SPEC.relative_to(REPO_ROOT)), *CODE_FILES):
        source = REPO_ROOT / relative
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    shutil.copy2(V1_PREP / "slot_registry.jsonl", OUTPUT_ROOT / "slot_registry.jsonl")
    write_jsonl(OUTPUT_ROOT / "inherited_accepted_rows.jsonl", inherited)
    write_json(OUTPUT_ROOT / "inherited_verification.json", inherited_receipt)
    frozen_inputs = {
        "parser_source": {
            "path": str(PARSER_SOURCE.relative_to(REPO_ROOT)),
            "sha256": EXPECTED_PARSER_SOURCE_SHA,
        },
        "scientific_preregistration": {
            "path": str(prereg.relative_to(REPO_ROOT)),
            "sha256": EXPECTED_R2_PREREG_SHA,
        },
        "exclusion_registry": {
            "path": str(EXCLUSION.relative_to(REPO_ROOT)),
            "sha256": sha256_file(EXCLUSION),
        },
        "v6_preparation_manifest": {
            "path": str((V6_PREP / "manifest.json").relative_to(REPO_ROOT)),
            "sha256": sha256_file(V6_PREP / "manifest.json"),
        },
        "v6_live_files": _tree_manifest(V6_ROOT),
    }
    write_json(OUTPUT_ROOT / "frozen_inputs.json", frozen_inputs)
    manifest = {
        "source_protocol_id": SOURCE_PROTOCOL_ID_V7,
        "status": "SEALED_BEFORE_ANY_R2SRC_003_PLUS_TEXT",
        "sealed_before_authored_text": True,
        "network_calls": 0,
        "external_generator_calls_authorized_or_performed_by_v7": False,
        "authorization_quote": AUTHORIZATION_QUOTE,
        "authorized_by": "research_lead_user",
        "source_thread_id": SOURCE_THREAD_ID,
        "task_thread_id": TASK_THREAD_ID,
        "authorship_role": "codex_direct_authorship",
        "model_id": MODEL_ID,
        "fixed_slots": 128,
        "inherited_nonreplaceable_slots": ["R2SRC-001", "R2SRC-002"],
        "new_authored_slots": 126,
        "proposal_is_truth": False,
        "programmatic_text_rewriting_allowed": False,
        "failed_v2_v6_response_bodies_read": False,
        "slot_registry_sha256": sha256_file(OUTPUT_ROOT / "slot_registry.jsonl"),
        "inherited_rows_sha256": sha256_file(OUTPUT_ROOT / "inherited_accepted_rows.jsonl"),
        "inherited_verification_sha256": sha256_file(OUTPUT_ROOT / "inherited_verification.json"),
        "frozen_inputs_sha256": sha256_file(OUTPUT_ROOT / "frozen_inputs.json"),
        "snapshot_files": _tree_manifest(snapshot),
    }
    write_json(OUTPUT_ROOT / "manifest.json", manifest)
    _sidecar(OUTPUT_ROOT / "manifest.json")
    lock = {
        "status": "V7_AUTHORSHIP_PROTOCOL_LOCKED_RESULT_BEFORE_TEXT",
        "manifest_sha256": sha256_file(OUTPUT_ROOT / "manifest.json"),
        "locked_at_unix_ns": time.time_ns(),
        "external_timestamp_claimed": False,
    }
    write_json(OUTPUT_ROOT / "lock.json", lock)
    _sidecar(OUTPUT_ROOT / "lock.json")
    receipt = {
        "receipt_type": "local_result_before_authorship_receipt",
        "source_protocol_id": SOURCE_PROTOCOL_ID_V7,
        "manifest_sha256": lock["manifest_sha256"],
        "lock_sha256": sha256_file(OUTPUT_ROOT / "lock.json"),
        "r2src_003_plus_text_present_at_seal": False,
    }
    write_json(OUTPUT_ROOT / "receipt.json", receipt)
    _sidecar(OUTPUT_ROOT / "receipt.json")
    return {**lock, "receipt_sha256": sha256_file(OUTPUT_ROOT / "receipt.json")}


def verify() -> dict[str, Any]:
    manifest = json.loads((OUTPUT_ROOT / "manifest.json").read_text(encoding="utf-8"))
    for row in manifest["snapshot_files"]:
        if (
            sha256_file(
                REPO_ROOT
                / row["path"].replace(
                    str(OUTPUT_ROOT.relative_to(REPO_ROOT)) + "/code_snapshot/", ""
                )
            )
            != row["sha256"]
        ):
            raise RuntimeError(f"v7 sealed source drift: {row['path']}")
    if sha256_file(OUTPUT_ROOT / "slot_registry.jsonl") != manifest["slot_registry_sha256"]:
        raise RuntimeError("v7 slot registry snapshot drift")
    frozen = json.loads((OUTPUT_ROOT / "frozen_inputs.json").read_text(encoding="utf-8"))
    for key in (
        "parser_source",
        "scientific_preregistration",
        "exclusion_registry",
        "v6_preparation_manifest",
    ):
        row = frozen[key]
        if sha256_file(REPO_ROOT / row["path"]) != row["sha256"]:
            raise RuntimeError(f"v7 frozen input drift: {key}")
    for row in frozen["v6_live_files"]:
        if sha256_file(REPO_ROOT / row["path"]) != row["sha256"]:
            raise RuntimeError(f"v6 append-only evidence drift: {row['path']}")
    lock = json.loads((OUTPUT_ROOT / "lock.json").read_text(encoding="utf-8"))
    if lock["manifest_sha256"] != sha256_file(OUTPUT_ROOT / "manifest.json"):
        raise RuntimeError("v7 manifest/lock drift")
    return lock


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("seal", "verify"))
    args = parser.parse_args()
    print(
        json.dumps(
            seal() if args.command == "seal" else verify(), ensure_ascii=False, sort_keys=True
        )
    )


if __name__ == "__main__":
    main()
