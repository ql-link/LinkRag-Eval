#!/usr/bin/env python3
"""Seal authorized R2 source execution v2 before any provider response."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.r2_source_execution_v2 import (
    AUTHORIZATION_ID,
    SOURCE_PROTOCOL_ID_V2,
    dry_run_v2,
)
from linkrag_eval.robust_fusion.similarity_dev_calibration import sha256_file, write_json
from scripts.prepare_robust_fusion_r2_source_generation import verify as verify_v1_preparation
from scripts.run_robust_fusion_r2_measurement import verify_preregistration

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_execution_preparation_v2/"
    "robust-fusion-r2-source-execution-preparation-v2-20260829"
)
V1_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_generation_preparation_v1/"
    "robust-fusion-r2-source-generation-preparation-v1-20260829"
)
R2_PREREG = REPO_ROOT / (
    "runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/"
    "preregistration/manifest.json"
)
SPEC = REPO_ROOT / "docs/plans/robust-fusion-r2-source-execution-v2.md"
AUTHORIZATION = REPO_ROOT / "docs/plans/robust-fusion-r2-source-authorization-amendment-v2.json"
PRICE = REPO_ROOT / "docs/plans/robust-fusion-r2-source-generation-price-snapshot-v1.json"
CODE = (
    "src/linkrag_eval/robust_fusion/r2_source_execution_v2.py",
    "scripts/prepare_robust_fusion_r2_source_execution_v2.py",
    "scripts/run_robust_fusion_r2_source_execution_v2.py",
    "tests/unit/test_robust_fusion_r2_source_execution_v2.py",
)
EXPECTED_V1_MANIFEST_SHA = "9de5e8f29b76610a013cc6cdd085d65c22a588ea56bfa20040bee624c856f2db"
EXPECTED_V1_LOCK_SHA = "723a4b784676795c84925483ebb0262ead0e047e3ca4cd47d37774fe28110d1c"
EXPECTED_V1_DRY_LOCK_SHA = "5dafb5ec6894a2a3c03c5cbd9a088521d6bc125a36bd06a23ba17c1924948d05"
EXPECTED_R2_PREREG_SHA = "b3c75dee6140c7aa57b865e592054ff5534405872efef4769b9636cccd09c71b"


def _sidecar(path: Path) -> None:
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{sha256_file(path)}  {path.name}\n", encoding="utf-8"
    )


def seal() -> dict[str, Any]:
    if OUTPUT_ROOT.exists():
        raise RuntimeError("R2 source execution v2 preparation exists; refusing overwrite")
    verify_preregistration()
    verify_v1_preparation()
    retained = {
        "v1_manifest": V1_ROOT / "manifest.json",
        "v1_lock": V1_ROOT / "lock.json",
        "v1_dry_run_lock": V1_ROOT / "dry_run_lock.json",
        "r2_preregistration": R2_PREREG,
    }
    expected = {
        "v1_manifest": EXPECTED_V1_MANIFEST_SHA,
        "v1_lock": EXPECTED_V1_LOCK_SHA,
        "v1_dry_run_lock": EXPECTED_V1_DRY_LOCK_SHA,
        "r2_preregistration": EXPECTED_R2_PREREG_SHA,
    }
    for key, path in retained.items():
        if sha256_file(path) != expected[key]:
            raise RuntimeError(f"retained v1/prereg hash drift: {key}")
    authorization = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))
    if (
        authorization["authorization_id"] != AUTHORIZATION_ID
        or authorization["source_protocol_id"] != SOURCE_PROTOCOL_ID_V2
        or authorization["budget_and_total_call_limit"] is not None
        or authorization["authorized_by"] != "research_lead_user"
    ):
        raise RuntimeError("v2 authorization amendment schema/identity drift")
    dry = dry_run_v2()
    OUTPUT_ROOT.mkdir(parents=True, mode=0o700)
    inputs = [SPEC, AUTHORIZATION, PRICE, *retained.values(), *(REPO_ROOT / row for row in CODE)]
    files = []
    for path in inputs:
        if not path.is_file():
            raise RuntimeError(f"missing v2 execution input: {path}")
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
    write_json(OUTPUT_ROOT / "dry_run_receipt.json", dry)
    _sidecar(OUTPUT_ROOT / "dry_run_receipt.json")
    files.append(
        {
            "path": str((OUTPUT_ROOT / "dry_run_receipt.json").relative_to(REPO_ROOT)),
            "size_bytes": (OUTPUT_ROOT / "dry_run_receipt.json").stat().st_size,
            "sha256": sha256_file(OUTPUT_ROOT / "dry_run_receipt.json"),
        }
    )
    manifest = {
        "research_id": "ROBUST-FUSION-R2-2026-08-29",
        "source_protocol_id": SOURCE_PROTOCOL_ID_V2,
        "authorization_id": AUTHORIZATION_ID,
        "status": "AUTHORIZED_SOURCE_EXECUTION_V2_SEALED",
        "sealed_before_any_r2_provider_response": True,
        "network_calls_at_seal": 0,
        "api_key_read_at_seal": False,
        "budget_or_total_call_limit": None,
        "fixed_slots": 128,
        "fixed_candidate_denominator": 256,
        "files": files,
    }
    write_json(OUTPUT_ROOT / "manifest.json", manifest)
    _sidecar(OUTPUT_ROOT / "manifest.json")
    lock = {
        "status": "SEALED_BEFORE_ANY_R2_SOURCE_API_RESPONSE",
        "manifest_sha256": sha256_file(OUTPUT_ROOT / "manifest.json"),
        "authorization_sha256": sha256_file(AUTHORIZATION),
        "sealed_at_unix_ns": time.time_ns(),
        "external_timestamp_claimed": False,
    }
    write_json(OUTPUT_ROOT / "lock.json", lock)
    _sidecar(OUTPUT_ROOT / "lock.json")
    return lock


def verify() -> dict[str, Any]:
    manifest = json.loads((OUTPUT_ROOT / "manifest.json").read_text(encoding="utf-8"))
    for row in manifest["files"]:
        path = REPO_ROOT / row["path"]
        if path.stat().st_size != row["size_bytes"] or sha256_file(path) != row["sha256"]:
            raise RuntimeError(f"sealed source execution v2 drift: {row['path']}")
    lock = json.loads((OUTPUT_ROOT / "lock.json").read_text(encoding="utf-8"))
    if lock["manifest_sha256"] != sha256_file(OUTPUT_ROOT / "manifest.json"):
        raise RuntimeError("source execution v2 manifest/lock drift")
    if lock["authorization_sha256"] != sha256_file(AUTHORIZATION):
        raise RuntimeError("source execution v2 authorization drift")
    return lock


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("seal", "verify"))
    args = parser.parse_args()
    result = seal() if args.command == "seal" else verify()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
