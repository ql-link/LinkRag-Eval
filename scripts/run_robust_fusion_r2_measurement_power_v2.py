#!/usr/bin/env python3
"""Seal and run the corrected synthetic-only R2 power simulation v2."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.r2_measurement_power_v2 import run_power_simulation
from linkrag_eval.robust_fusion.similarity_dev_calibration import (
    canonical_json,
    sha256_file,
    write_json,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_measurement_power_v2/robust-fusion-r2-measurement-power-v2-20260829"
)
SETUP_FILES = ("simulation_protocol.md", "simulation_config.json")
CODE_FILES = (
    "src/linkrag_eval/robust_fusion/r2_measurement_power.py",
    "src/linkrag_eval/robust_fusion/r2_measurement_power_v2.py",
    "scripts/run_robust_fusion_r2_measurement_power_v2.py",
    "tests/unit/test_robust_fusion_r2_measurement_power_v2.py",
)


def _sidecar(path: Path) -> None:
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{sha256_file(path)}  {path.name}\n", encoding="utf-8"
    )


def seal() -> dict[str, Any]:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    if (OUTPUT_ROOT / "simulation_setup_lock.json").exists():
        raise RuntimeError("v2 simulation setup already sealed; refusing overwrite")
    records = []
    for relative in (*SETUP_FILES, *CODE_FILES):
        path = OUTPUT_ROOT / relative if relative in SETUP_FILES else REPO_ROOT / relative
        if not path.is_file():
            raise RuntimeError(f"missing v2 simulation input: {path}")
        records.append({"path": str(path.relative_to(REPO_ROOT)), "sha256": sha256_file(path)})
        if relative in SETUP_FILES:
            _sidecar(path)
    lock = {
        "lock_id": "ROBUST-FUSION-R2-MEASUREMENT-POWER-SETUP-2026-08-29-v2",
        "status": "SEALED_BEFORE_ANY_R2_TEXT_SCORE_OR_HUMAN_RESULT",
        "sealed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "v1_disposition": "INVALID_FOR_PREREGISTRATION_FRAME_ALLOCATION_BUG",
        "files": records,
    }
    write_json(OUTPUT_ROOT / "simulation_setup_lock.json", lock)
    _sidecar(OUTPUT_ROOT / "simulation_setup_lock.json")
    return lock


def verify() -> dict[str, Any]:
    lock = json.loads((OUTPUT_ROOT / "simulation_setup_lock.json").read_text(encoding="utf-8"))
    for record in lock["files"]:
        if sha256_file(REPO_ROOT / record["path"]) != record["sha256"]:
            raise RuntimeError(f"sealed v2 simulation drift: {record['path']}")
    return lock


def run() -> dict[str, Any]:
    verify()
    final_names = ("simulation_results.json", "manifest.json", "receipt.json")
    if any((OUTPUT_ROOT / name).exists() for name in final_names):
        raise RuntimeError("v2 simulation already materialized; refusing overwrite/retry")
    config = json.loads((OUTPUT_ROOT / "simulation_config.json").read_text(encoding="utf-8"))
    results = run_power_simulation(config)
    write_json(OUTPUT_ROOT / "simulation_results.json", results)
    manifest = {
        "run_id": "robust-fusion-r2-measurement-power-v2-20260829",
        "status": results["status"],
        "result_sha256": sha256_file(OUTPUT_ROOT / "simulation_results.json"),
        "setup_lock_sha256": sha256_file(OUTPUT_ROOT / "simulation_setup_lock.json"),
        "command": "PYTHONPATH=src .venv/bin/python scripts/run_robust_fusion_r2_measurement_power_v2.py run",
    }
    write_json(OUTPUT_ROOT / "manifest.json", manifest)
    write_json(
        OUTPUT_ROOT / "receipt.json",
        {
            "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "manifest_sha256": sha256_file(OUTPUT_ROOT / "manifest.json"),
        },
    )
    for name in final_names:
        _sidecar(OUTPUT_ROOT / name)
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("seal", "verify", "run"))
    args = parser.parse_args()
    result = seal() if args.command == "seal" else verify() if args.command == "verify" else run()
    print(canonical_json(result))


if __name__ == "__main__":
    main()
