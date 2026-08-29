#!/usr/bin/env python3
"""Run the sealed, correctly scoped v7.1 R2 source-data lock once."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.r2_source_lock_v7_1 import (
    SOURCE_LOCK_EXECUTOR_ID,
    materialize_v7_1_families,
)
from linkrag_eval.robust_fusion.similarity_dev_calibration import (
    sha256_file,
    write_json,
    write_jsonl,
)
from scripts.prepare_robust_fusion_r2_source_lock_v7_1 import (
    CODE_FILES,
    LEDGER_FILES,
    OUTPUT_ROOT,
    REPO_ROOT,
    SPEC,
)
from scripts.run_robust_fusion_r2_source_authorship_v7 import (
    EXCLUSION,
    LIVE_ROOT,
    verify_preparation,
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def verify_v7_1_preparation() -> dict[str, Any]:
    verify_preparation()
    receipt = json.loads((OUTPUT_ROOT / "receipt.json").read_text(encoding="utf-8"))
    manifest_path = OUTPUT_ROOT / "manifest.json"
    if sha256_file(manifest_path) != receipt["manifest_sha256"]:
        raise RuntimeError("v7.1 preparation manifest drift")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    current_files = (str(SPEC.relative_to(REPO_ROOT)), *CODE_FILES)
    for relative, sealed in zip(current_files, manifest["snapshot_files"], strict=True):
        if sha256_file(REPO_ROOT / relative) != sealed["sha256"]:
            raise RuntimeError(f"v7.1 implementation drift: {relative}")
    for name, sealed in zip(LEDGER_FILES, manifest["input_ledgers"], strict=True):
        if sha256_file(LIVE_ROOT / name) != sealed["sha256"]:
            raise RuntimeError(f"v7 input ledger drift: {name}")
    return receipt


def lock_data() -> dict[str, Any]:
    receipt = verify_v7_1_preparation()
    data_root = LIVE_ROOT / "data_lock"
    if data_root.exists():
        raise RuntimeError("v7 source data lock exists; replay refused")
    proposals = _read_jsonl(LIVE_ROOT / "accepted_proposals_not_truth.jsonl")
    if len(proposals) != 128:
        raise RuntimeError("v7 source denominator incomplete")
    exclusion = json.loads(EXCLUSION.read_text(encoding="utf-8"))
    families, validation = materialize_v7_1_families(proposals, exclusion)
    provenance = _read_jsonl(LIVE_ROOT / "generator_provenance.jsonl")
    if len(provenance) != 128:
        raise RuntimeError("v7 generator provenance denominator drift")
    data_root.mkdir()
    write_jsonl(data_root / "families.jsonl", families)
    write_json(data_root / "validation.json", validation)
    write_jsonl(data_root / "generator_provenance.jsonl", provenance)
    paths = [
        LIVE_ROOT / "accepted_proposals_not_truth.jsonl",
        LIVE_ROOT / "authorship_attempts_not_truth.jsonl",
        LIVE_ROOT / "authorship_audit.jsonl",
        LIVE_ROOT / "generator_provenance.jsonl",
        data_root / "families.jsonl",
        data_root / "validation.json",
        data_root / "generator_provenance.jsonl",
    ]
    files = [
        {
            "path": str(path.relative_to(LIVE_ROOT)),
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in paths
    ]
    manifest = {
        "status": "R2_SOURCE_DATA_LOCK_COMPLETE_AWAITING_ENCODERS",
        "source_protocol_id": "ROBUST-FUSION-R2-SOURCE-CODEX-AUTHORED-2026-08-29-v7",
        "source_lock_executor_id": SOURCE_LOCK_EXECUTOR_ID,
        "source_lock_preparation_manifest_sha256": receipt["manifest_sha256"],
        "fixed_families": 128,
        "fixed_candidate_denominator": 256,
        "inherited_slots": 2,
        "codex_authored_slots": 126,
        "proposal_is_truth": False,
        "first_complete_mechanical_pass_locked": True,
        "programmatic_text_rewriting_performed": False,
        "validation": validation,
        "files": files,
    }
    write_json(data_root / "manifest.json", manifest)
    write_json(
        data_root / "lock.json",
        {
            "status": "LOCKED_BEFORE_E5_DISTILUSE_OR_HUMAN_REVIEW",
            "source_lock_executor_id": SOURCE_LOCK_EXECUTOR_ID,
            "manifest_sha256": sha256_file(data_root / "manifest.json"),
            "families_sha256": sha256_file(data_root / "families.jsonl"),
            "fixed_families": 128,
            "fixed_candidate_denominator": 256,
        },
    )
    return {
        "status": manifest["status"],
        "manifest_sha256": sha256_file(data_root / "manifest.json"),
        "families_sha256": sha256_file(data_root / "families.jsonl"),
        "fixed_families": 128,
        "fixed_candidate_denominator": 256,
    }


if __name__ == "__main__":
    print(json.dumps(lock_data(), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
