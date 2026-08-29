#!/usr/bin/env python3
"""Seal the v7.1 source-lock implementation before it writes formal source data."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.r2_source_lock_v7_1 import SOURCE_LOCK_EXECUTOR_ID
from linkrag_eval.robust_fusion.similarity_dev_calibration import sha256_file, write_json
from scripts.run_robust_fusion_r2_source_authorship_v7 import LIVE_ROOT, verify_preparation

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_lock_preparation_v7_1/"
    "robust-fusion-r2-source-lock-preparation-v7-1-20260829"
)
SPEC = REPO_ROOT / "docs/plans/robust-fusion-r2-source-lock-v7-1.md"
V7_PREP = REPO_ROOT / (
    "runs/robust_fusion/r2_source_authorship_preparation_v7_codex/"
    "robust-fusion-r2-source-authorship-preparation-v7-codex-20260829"
)
CODE_FILES = (
    "src/linkrag_eval/robust_fusion/r2_source_lock_v7_1.py",
    "scripts/prepare_robust_fusion_r2_source_lock_v7_1.py",
    "scripts/run_robust_fusion_r2_source_lock_v7_1.py",
    "tests/unit/test_robust_fusion_r2_source_lock_v7_1.py",
)
LEDGER_FILES = (
    "accepted_proposals_not_truth.jsonl",
    "authorship_attempts_not_truth.jsonl",
    "authorship_audit.jsonl",
    "generator_provenance.jsonl",
)


def _entry(path: Path) -> dict[str, Any]:
    return {"path": str(path.relative_to(REPO_ROOT)), "sha256": sha256_file(path), "size_bytes": path.stat().st_size}


def seal() -> dict[str, Any]:
    verify_preparation()
    if OUTPUT_ROOT.exists():
        raise RuntimeError("v7.1 preparation already exists; replay refused")
    if (LIVE_ROOT / "data_lock").exists():
        raise RuntimeError("formal source data already exists; retrospective seal refused")
    accepted = LIVE_ROOT / "accepted_proposals_not_truth.jsonl"
    if sum(1 for line in accepted.read_text(encoding="utf-8").splitlines() if line) != 128:
        raise RuntimeError("v7 accepted denominator incomplete")
    OUTPUT_ROOT.mkdir(parents=True, mode=0o700)
    snapshot = OUTPUT_ROOT / "code_snapshot"
    snapshot.mkdir()
    snapshot_files = (str(SPEC.relative_to(REPO_ROOT)), *CODE_FILES)
    for relative in snapshot_files:
        source = REPO_ROOT / relative
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    manifest = {
        "status": "R2_SOURCE_LOCK_V7_1_IMPLEMENTATION_SEALED_BEFORE_FORMAL_DATA",
        "source_lock_executor_id": SOURCE_LOCK_EXECUTOR_ID,
        "sealed_at_unix": time.time(),
        "correction_scope": "cross-family final duplicate-check scope only",
        "scientific_preregistration_changed": False,
        "parser_changed": False,
        "accepted_proposals_changed": False,
        "failed_v7_lock_created_data_root": False,
        "v7_preparation_manifest": _entry(V7_PREP / "manifest.json"),
        "v7_preparation_receipt": _entry(V7_PREP / "receipt.json"),
        "input_ledgers": [_entry(LIVE_ROOT / name) for name in LEDGER_FILES],
        "snapshot_files": [
            _entry(snapshot / relative) for relative in snapshot_files
        ],
    }
    write_json(OUTPUT_ROOT / "manifest.json", manifest)
    receipt = {
        "status": "LOCKED",
        "source_lock_executor_id": SOURCE_LOCK_EXECUTOR_ID,
        "manifest_sha256": sha256_file(OUTPUT_ROOT / "manifest.json"),
        "formal_data_existed_at_seal": False,
    }
    write_json(OUTPUT_ROOT / "receipt.json", receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(seal(), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
