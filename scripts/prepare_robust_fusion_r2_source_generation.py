#!/usr/bin/env python3
"""Seal and dry-run R2 DeepSeek source generation without network access."""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.r2_source_generation import (
    SOURCE_PROTOCOL_ID,
    build_slot_registry,
    canonical_json,
    dry_run_summary,
)
from linkrag_eval.robust_fusion.similarity_dev_calibration import (
    sha256_file,
    write_json,
    write_jsonl,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_generation_preparation_v1/"
    "robust-fusion-r2-source-generation-preparation-v1-20260829"
)
SPEC = REPO_ROOT / "docs/plans/robust-fusion-r2-source-generation-implementation-v1.md"
PRICE = REPO_ROOT / "docs/plans/robust-fusion-r2-source-generation-price-snapshot-v1.json"
R2_PREREG = REPO_ROOT / (
    "runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/"
    "preregistration/manifest.json"
)
EXCLUSION = REPO_ROOT / (
    "runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/"
    "exclusions/registry.json"
)
CODE = (
    "src/linkrag_eval/robust_fusion/r2_source_generation.py",
    "scripts/prepare_robust_fusion_r2_source_generation.py",
    "scripts/run_robust_fusion_r2_source_generation.py",
    "tests/unit/test_robust_fusion_r2_source_generation.py",
)
EXPECTED_R2_PREREG_SHA = "b3c75dee6140c7aa57b865e592054ff5534405872efef4769b9636cccd09c71b"
EXPECTED_EXCLUSION_SHA = "f54115330edeabb077d149f09106051a210fb086669208dd5177839989c4fe16"


def _sidecar(path: Path) -> None:
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{sha256_file(path)}  {path.name}\n", encoding="utf-8"
    )


def seal() -> dict[str, Any]:
    if OUTPUT_ROOT.exists():
        raise RuntimeError("source-generation preparation root already exists")
    if sha256_file(R2_PREREG) != EXPECTED_R2_PREREG_SHA:
        raise RuntimeError("sealed R2 preregistration drift")
    if sha256_file(EXCLUSION) != EXPECTED_EXCLUSION_SHA:
        raise RuntimeError("R1 exclusion registry drift")
    OUTPUT_ROOT.mkdir(parents=True, mode=0o700)
    slots = build_slot_registry()
    write_jsonl(OUTPUT_ROOT / "slot_registry.jsonl", slots)
    files = []
    for path in (SPEC, PRICE, *(REPO_ROOT / item for item in CODE), R2_PREREG, EXCLUSION):
        if not path.is_file():
            raise RuntimeError(f"missing source preparation input: {path}")
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
    files.append(
        {
            "path": str((OUTPUT_ROOT / "slot_registry.jsonl").relative_to(REPO_ROOT)),
            "size_bytes": (OUTPUT_ROOT / "slot_registry.jsonl").stat().st_size,
            "sha256": sha256_file(OUTPUT_ROOT / "slot_registry.jsonl"),
        }
    )
    manifest = {
        "source_protocol_id": SOURCE_PROTOCOL_ID,
        "status": "OFFLINE_IMPLEMENTATION_SEALED_AWAITING_DRY_RUN",
        "network_calls_at_seal": 0,
        "api_key_read_at_seal": False,
        "files": files,
    }
    write_json(OUTPUT_ROOT / "manifest.json", manifest)
    _sidecar(OUTPUT_ROOT / "manifest.json")
    authorization_template = {
        "authorization_id": "FILL_AFTER_EXPLICIT_APPROVAL",
        "authorized_by": "FILL_AFTER_EXPLICIT_APPROVAL",
        "source_protocol_id": SOURCE_PROTOCOL_ID,
        "preparation_manifest_sha256": sha256_file(OUTPUT_ROOT / "manifest.json"),
        "price_snapshot_sha256": sha256_file(PRICE),
        "max_usd": 5.0,
        "authorized_at": "FILL_AFTER_EXPLICIT_APPROVAL",
    }
    write_json(OUTPUT_ROOT / "authorization_receipt_template.json", authorization_template)
    _sidecar(OUTPUT_ROOT / "authorization_receipt_template.json")
    lock = {
        "status": "SEALED_BEFORE_ANY_PAID_API_CALL_OR_R2_PROPOSAL",
        "manifest_sha256": sha256_file(OUTPUT_ROOT / "manifest.json"),
        "authorization_receipt_template_sha256": sha256_file(
            OUTPUT_ROOT / "authorization_receipt_template.json"
        ),
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
            raise RuntimeError(f"sealed source-generation preparation drift: {row['path']}")
    lock = json.loads((OUTPUT_ROOT / "lock.json").read_text(encoding="utf-8"))
    if lock["manifest_sha256"] != sha256_file(OUTPUT_ROOT / "manifest.json"):
        raise RuntimeError("source-generation lock chain drift")
    if lock["authorization_receipt_template_sha256"] != sha256_file(
        OUTPUT_ROOT / "authorization_receipt_template.json"
    ):
        raise RuntimeError("source-generation authorization template drift")
    dry_lock_path = OUTPUT_ROOT / "dry_run_lock.json"
    if dry_lock_path.exists():
        dry_lock = json.loads(dry_lock_path.read_text(encoding="utf-8"))
        dry_receipt = OUTPUT_ROOT / "dry_run_receipt.json"
        if (
            dry_lock["manifest_sha256"] != sha256_file(OUTPUT_ROOT / "manifest.json")
            or dry_lock["dry_run_receipt_sha256"] != sha256_file(dry_receipt)
        ):
            raise RuntimeError("source-generation dry-run lock drift")
    return lock


def dry_run() -> dict[str, Any]:
    verify()
    output = OUTPUT_ROOT / "dry_run_receipt.json"
    if output.exists():
        raise RuntimeError("dry-run receipt exists; refusing replay")
    price = json.loads(PRICE.read_text(encoding="utf-8"))
    result = dry_run_summary(price)
    write_json(output, result)
    _sidecar(output)
    dry_lock = {
        "status": "DRY_RUN_LOCKED_AWAITING_EXPLICIT_PAID_API_AUTHORIZATION",
        "manifest_sha256": sha256_file(OUTPUT_ROOT / "manifest.json"),
        "dry_run_receipt_sha256": sha256_file(output),
        "locked_at_unix_ns": time.time_ns(),
        "network_calls": 0,
        "api_key_read": False,
    }
    write_json(OUTPUT_ROOT / "dry_run_lock.json", dry_lock)
    _sidecar(OUTPUT_ROOT / "dry_run_lock.json")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("seal", "verify", "dry-run"))
    args = parser.parse_args()
    result = (
        seal() if args.command == "seal" else verify() if args.command == "verify" else dry_run()
    )
    print(canonical_json(result))


if __name__ == "__main__":
    main()
