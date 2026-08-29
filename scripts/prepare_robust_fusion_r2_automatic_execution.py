#!/usr/bin/env python3
"""Seal R2 automatic execution code after source lock and before encoder output."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.r2_automatic_execution import AUTOMATIC_EXECUTOR_ID
from linkrag_eval.robust_fusion.similarity_dev_calibration import sha256_file, write_json
from scripts.run_robust_fusion_r2_measurement import OUTPUT_ROOT, verify_preregistration

REPO_ROOT = Path(__file__).resolve().parents[1]
PREP_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_automatic_preparation_v1/"
    "robust-fusion-r2-automatic-preparation-v1-20260829"
)
SOURCE_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_authorship_v7_codex/"
    "robust-fusion-r2-source-authorship-v7-codex-20260829/data_lock"
)
QUALIFICATION_ROOT = REPO_ROOT / "runs/robust_fusion/contracts/similarity-encoder-qualification-v3"
SPEC = REPO_ROOT / "docs/plans/robust-fusion-r2-automatic-execution-v1.md"
CODE_FILES = (
    "src/linkrag_eval/robust_fusion/r2_automatic_execution.py",
    "scripts/prepare_robust_fusion_r2_automatic_execution.py",
    "scripts/run_robust_fusion_r2_automatic_execution.py",
    "tests/unit/test_robust_fusion_r2_automatic_execution.py",
    "src/linkrag_eval/robust_fusion/r2_measurement.py",
    "scripts/run_robust_fusion_similarity_dev_calibration.py",
)


def _entry(path: Path) -> dict[str, Any]:
    return {"path": str(path.relative_to(REPO_ROOT)), "sha256": sha256_file(path), "size_bytes": path.stat().st_size}


def seal() -> dict[str, Any]:
    verify_preregistration()
    if PREP_ROOT.exists():
        raise RuntimeError("R2 automatic preparation already exists; replay refused")
    if (OUTPUT_ROOT / "automatic").exists() or (OUTPUT_ROOT / "human_packages").exists():
        raise RuntimeError("R2 automatic/human outputs exist; retrospective seal refused")
    source_lock = json.loads((SOURCE_ROOT / "lock.json").read_text(encoding="utf-8"))
    if source_lock.get("status") != "LOCKED_BEFORE_E5_DISTILUSE_OR_HUMAN_REVIEW":
        raise RuntimeError("R2 formal source lock missing")
    PREP_ROOT.mkdir(parents=True, mode=0o700)
    snapshot = PREP_ROOT / "code_snapshot"
    snapshot.mkdir()
    snapshot_files = (str(SPEC.relative_to(REPO_ROOT)), *CODE_FILES)
    for relative in snapshot_files:
        source = REPO_ROOT / relative
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    manifest = {
        "status": "R2_AUTOMATIC_EXECUTION_SEALED_BEFORE_ENCODER_OUTPUT",
        "automatic_executor_id": AUTOMATIC_EXECUTOR_ID,
        "sealed_at_unix_ns": time.time_ns(),
        "single_execution": True,
        "scientific_preregistration_changed": False,
        "source_lock": [_entry(SOURCE_ROOT / name) for name in ("manifest.json", "lock.json", "families.jsonl", "validation.json")],
        "qualification": [_entry(QUALIFICATION_ROOT / name) for name in ("manifest.json", "manifest.sha256")],
        "snapshot_files": [_entry(snapshot / relative) for relative in snapshot_files],
    }
    write_json(PREP_ROOT / "manifest.json", manifest)
    receipt = {
        "status": "LOCKED",
        "automatic_executor_id": AUTOMATIC_EXECUTOR_ID,
        "manifest_sha256": sha256_file(PREP_ROOT / "manifest.json"),
        "encoder_outputs_existed_at_seal": False,
    }
    write_json(PREP_ROOT / "receipt.json", receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(seal(), ensure_ascii=False, sort_keys=True, separators=(",", ":")))

