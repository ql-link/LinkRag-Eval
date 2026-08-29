#!/usr/bin/env python3
"""Append, validate, and lock directly authored R2 source proposals v7."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.r2_source_authorship_v7 import (
    AUTHORSHIP_ROLE,
    MODEL_ID,
    SOURCE_PROTOCOL_ID_V7,
    materialize_v7_families,
    proposal_attempt_sha256,
    verify_inherited_v6_proposals,
)
from linkrag_eval.robust_fusion.r2_source_generation import (
    PROPOSAL_FIELDS,
    build_slot_registry,
    canonical_json,
)
from linkrag_eval.robust_fusion.similarity_dev_calibration import (
    sha256_file,
    write_json,
    write_jsonl,
)
from scripts.prepare_robust_fusion_r2_source_authorship_v7 import (
    EXCLUSION,
    LIVE_ROOT,
    OUTPUT_ROOT,
    V4_ROOT,
    V6_ROOT,
)
from scripts.prepare_robust_fusion_r2_source_authorship_v7 import (
    verify as verify_preparation,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def append_jsonl_fsync(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json(row) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def initialize() -> dict[str, Any]:
    verify_preparation()
    if LIVE_ROOT.exists():
        raise RuntimeError("v7 live root exists; initialize replay refused")
    exclusion = json.loads(EXCLUSION.read_text(encoding="utf-8"))
    inherited, receipt = verify_inherited_v6_proposals(V4_ROOT, V6_ROOT, exclusion)
    LIVE_ROOT.mkdir(parents=True, mode=0o700)
    shutil.copy2(OUTPUT_ROOT / "manifest.json", LIVE_ROOT / "preparation_manifest_snapshot.json")
    for name in (
        "authorship_attempts_not_truth.jsonl",
        "authorship_audit.jsonl",
        "generator_provenance.jsonl",
    ):
        (LIVE_ROOT / name).touch(exist_ok=False)
    source_bytes = (V6_ROOT / "accepted_proposals_not_truth.jsonl").read_bytes()
    with (LIVE_ROOT / "accepted_proposals_not_truth.jsonl").open("xb") as handle:
        handle.write(source_bytes)
        handle.flush()
        os.fsync(handle.fileno())
    if (
        sha256_file(LIVE_ROOT / "accepted_proposals_not_truth.jsonl")
        != receipt["accepted_ledger_sha256"]
    ):
        raise RuntimeError("v7 inherited accepted byte copy drift")
    for slot_id, model, protocol, proposal_hash in (
        (
            "R2SRC-001",
            "deepseek-v4-flash",
            "ROBUST-FUSION-R2-SOURCE-RECOVERY-2026-08-29-v4",
            inherited[0]["proposal_sha256"],
        ),
        (
            "R2SRC-002",
            "deepseek-v4-pro",
            "ROBUST-FUSION-R2-SOURCE-RECOVERY-2026-08-29-v6",
            inherited[1]["proposal_sha256"],
        ),
    ):
        append_jsonl_fsync(
            LIVE_ROOT / "generator_provenance.jsonl",
            {
                "slot_id": slot_id,
                "proposal_sha256": proposal_hash,
                "generator_model": model,
                "generator_source_protocol_id": protocol,
                "imported_into_source_protocol_id": SOURCE_PROTOCOL_ID_V7,
                "byte_exact_inherited_accepted_row": True,
                "replaceable": False,
            },
        )
    return {"status": "V7_INITIALIZED_AWAITING_R2SRC_003", "accepted_slots": 2}


def submit_batch(path: Path) -> dict[str, Any]:
    verify_preparation()
    if not LIVE_ROOT.is_dir() or (LIVE_ROOT / "data_lock").exists():
        raise RuntimeError("v7 is not in an appendable authorship state")
    exclusion = json.loads(EXCLUSION.read_text(encoding="utf-8"))
    accepted_path = LIVE_ROOT / "accepted_proposals_not_truth.jsonl"
    accepted = _read_jsonl(accepted_path)
    slots = build_slot_registry()
    inputs = _read_jsonl(path)
    if not inputs:
        raise RuntimeError("empty authored proposal batch")
    results: list[dict[str, Any]] = []
    for raw in inputs:
        expected_index = len(accepted)
        if expected_index >= len(slots):
            raise RuntimeError("fixed source denominator already filled")
        slot = slots[expected_index]
        if raw.get("slot_id") != slot["slot_id"]:
            raise RuntimeError("authored slots must be submitted once in fixed order")
        prior_attempts = [
            row
            for row in _read_jsonl(LIVE_ROOT / "authorship_attempts_not_truth.jsonl")
            if row["slot_id"] == slot["slot_id"]
        ]
        attempt = len(prior_attempts) + 1
        draft = {key: raw[key] for key in PROPOSAL_FIELDS if key in raw}
        receipt = {
            "source_protocol_id": SOURCE_PROTOCOL_ID_V7,
            "event": "AUTHORSHIP_DRAFT_HASHED_BEFORE_VALIDATION",
            "slot_id": slot["slot_id"],
            "attempt": attempt,
            "draft_sha256": proposal_attempt_sha256(draft),
            "proposal_not_truth": draft,
            "programmatic_text_rewriting_performed": False,
        }
        append_jsonl_fsync(LIVE_ROOT / "authorship_attempts_not_truth.jsonl", receipt)
        from linkrag_eval.robust_fusion.r2_source_authorship_v7 import validate_authored_proposal

        try:
            proposal = validate_authored_proposal(
                draft,
                slot=slot,
                exclusion_registry=exclusion,
                accepted_proposals=accepted,
                attempt=attempt,
            )
        except ValueError as exc:
            failure = str(exc)
            append_jsonl_fsync(
                LIVE_ROOT / "authorship_audit.jsonl",
                {
                    "source_protocol_id": SOURCE_PROTOCOL_ID_V7,
                    "event": "MECHANICAL_REJECTION_RETAINED",
                    "slot_id": slot["slot_id"],
                    "attempt": attempt,
                    "draft_sha256": receipt["draft_sha256"],
                    "mechanical_failure": failure,
                    "revision_must_be_versioned": True,
                },
            )
            raise RuntimeError(f"{slot['slot_id']} mechanical rejection: {failure}") from exc
        append_jsonl_fsync(accepted_path, proposal)
        append_jsonl_fsync(
            LIVE_ROOT / "authorship_audit.jsonl",
            {
                "source_protocol_id": SOURCE_PROTOCOL_ID_V7,
                "event": "FIRST_COMPLETE_MECHANICAL_PASS_PERMANENTLY_LOCKED",
                "slot_id": slot["slot_id"],
                "attempt": attempt,
                "draft_sha256": receipt["draft_sha256"],
                "proposal_sha256": proposal["proposal_sha256"],
                "replaceable": False,
            },
        )
        append_jsonl_fsync(
            LIVE_ROOT / "generator_provenance.jsonl",
            {
                "slot_id": slot["slot_id"],
                "proposal_sha256": proposal["proposal_sha256"],
                "generator_model": MODEL_ID,
                "generator_source_protocol_id": SOURCE_PROTOCOL_ID_V7,
                "authorship_role": AUTHORSHIP_ROLE,
                "source_attempt_version": proposal["source_attempt_version"],
                "proposal_is_truth": False,
            },
        )
        accepted.append(proposal)
        results.append({"slot_id": slot["slot_id"], "proposal_sha256": proposal["proposal_sha256"]})
    return {
        "status": "V7_AUTHORSHIP_BATCH_ACCEPTED",
        "batch_sha256": sha256_file(path),
        "accepted_in_batch": len(results),
        "accepted_total": len(accepted),
        "last_slot_id": results[-1]["slot_id"],
    }


def lock_data() -> dict[str, Any]:
    verify_preparation()
    data_root = LIVE_ROOT / "data_lock"
    if data_root.exists():
        raise RuntimeError("v7 data lock exists; replay refused")
    proposals = _read_jsonl(LIVE_ROOT / "accepted_proposals_not_truth.jsonl")
    if len(proposals) != 128:
        raise RuntimeError("v7 source denominator incomplete")
    exclusion = json.loads(EXCLUSION.read_text(encoding="utf-8"))
    families, validation = materialize_v7_families(proposals, exclusion)
    provenance = _read_jsonl(LIVE_ROOT / "generator_provenance.jsonl")
    if len(provenance) != 128:
        raise RuntimeError("v7 generator provenance denominator drift")
    data_root.mkdir()
    write_jsonl(data_root / "families.jsonl", families)
    write_json(data_root / "validation.json", validation)
    write_jsonl(data_root / "generator_provenance.jsonl", provenance)
    files = []
    for path in (
        LIVE_ROOT / "accepted_proposals_not_truth.jsonl",
        LIVE_ROOT / "authorship_attempts_not_truth.jsonl",
        LIVE_ROOT / "authorship_audit.jsonl",
        LIVE_ROOT / "generator_provenance.jsonl",
        data_root / "families.jsonl",
        data_root / "validation.json",
        data_root / "generator_provenance.jsonl",
    ):
        files.append(
            {
                "path": str(path.relative_to(LIVE_ROOT)),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    manifest = {
        "status": "R2_SOURCE_DATA_LOCK_COMPLETE_AWAITING_ENCODERS",
        "source_protocol_id": SOURCE_PROTOCOL_ID_V7,
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
            "manifest_sha256": sha256_file(data_root / "manifest.json"),
            "locked_at_unix_ns": time.time_ns(),
        },
    )
    return {
        "status": manifest["status"],
        "manifest_sha256": sha256_file(data_root / "manifest.json"),
        "lock_sha256": sha256_file(data_root / "lock.json"),
        "validation": validation,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("initialize", "submit-batch", "lock-data"))
    parser.add_argument("--input", type=Path)
    args = parser.parse_args()
    if args.command == "initialize":
        result = initialize()
    elif args.command == "submit-batch":
        if args.input is None:
            raise RuntimeError("submit-batch requires --input")
        result = submit_batch(args.input)
    else:
        result = lock_data()
    print(canonical_json(result))


if __name__ == "__main__":
    main()
