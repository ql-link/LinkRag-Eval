#!/usr/bin/env python3
"""Execute the sealed conservative R2 source recovery v5 exactly once."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values

from linkrag_eval.robust_fusion.r2_source_execution_v2 import (
    AUTHORIZATION_ID,
    PermanentProviderError,
    RecoverableTransportError,
)
from linkrag_eval.robust_fusion.r2_source_generation import (
    EXPECTED_BASE_URL,
    EXPECTED_MODEL,
    canonical_json,
)
from linkrag_eval.robust_fusion.r2_source_recovery_v5 import (
    SOURCE_PROTOCOL_ID_V5,
    execute_source_v5,
    materialize_and_validate_families,
    verify_inherited_v4_proposal,
)
from linkrag_eval.robust_fusion.similarity_dev_calibration import (
    sha256_file,
    write_json,
    write_jsonl,
)
from scripts.run_robust_fusion_r2_source_execution_v2 import validate_authorization

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_v5/robust-fusion-r2-source-recovery-v5-20260829"
)
PREPARATION_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_preparation_v5/"
    "robust-fusion-r2-source-recovery-preparation-v5-20260829"
)
V4_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_v4/robust-fusion-r2-source-recovery-v4-20260829"
)
EXCLUSION = REPO_ROOT / (
    "runs/robust_fusion/r2_measurement_v1/"
    "robust-fusion-r2-measurement-v1-20260829/exclusions/registry.json"
)


def append_jsonl_fsync(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json(row) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def initialize_live_root(path: Path = LIVE_ROOT) -> None:
    if path.exists():
        raise RuntimeError("source recovery v5 live root exists; command replay refused")
    path.mkdir(parents=True, mode=0o700)


def _write_bytes_fsync(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _load_provider() -> tuple[str, str, str]:
    values = dotenv_values(REPO_ROOT / ".env.eval")
    base_url = str(values.get("EVAL_JUDGE_BASE_URL") or "")
    model = str(values.get("EVAL_JUDGE_MODEL") or "")
    api_key = str(values.get("EVAL_JUDGE_API_KEY") or "")
    if base_url != EXPECTED_BASE_URL or model != EXPECTED_MODEL or not api_key:
        raise RuntimeError("provider configuration does not match sealed DeepSeek identity")
    return base_url, model, api_key


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8") as handle:
        return sum(1 for _line in handle)


def execute(authorization_path: Path, *, allow_paid_api: bool) -> dict[str, Any]:
    from scripts.prepare_robust_fusion_r2_source_recovery_v5 import (
        verify as verify_preparation,
    )

    verify_preparation()
    authorization = validate_authorization(authorization_path, allow_paid_api=allow_paid_api)
    exclusion = json.loads(EXCLUSION.read_text(encoding="utf-8"))
    inherited, inheritance_receipt = verify_inherited_v4_proposal(V4_ROOT, exclusion)
    base_url, _model, api_key = _load_provider()
    initialize_live_root()
    write_json(
        LIVE_ROOT / "authorization_receipt_snapshot.json",
        {
            **authorization,
            "source_sha256": sha256_file(authorization_path),
            "continued_for_source_protocol_id": SOURCE_PROTOCOL_ID_V5,
        },
    )
    write_json(LIVE_ROOT / "inherited_r2src_001_hard_lock.json", inheritance_receipt)

    audit_path = LIVE_ROOT / "call_audit.jsonl"
    response_path = LIVE_ROOT / "response_archive_synthetic_only.jsonl"
    stage_lock_path = LIVE_ROOT / "attempt_scoped_stage_locks.jsonl"
    attempt_path = LIVE_ROOT / "complete_assembly_attempts_not_truth.jsonl"
    proposal_path = LIVE_ROOT / "accepted_proposals_not_truth.jsonl"
    for path in (audit_path, response_path, stage_lock_path, attempt_path):
        path.touch(exist_ok=False)
    inherited_bytes = (V4_ROOT / "accepted_proposals_not_truth.jsonl").read_bytes()
    _write_bytes_fsync(proposal_path, inherited_bytes)
    if sha256_file(proposal_path) != sha256_file(V4_ROOT / "accepted_proposals_not_truth.jsonl"):
        raise RuntimeError("R2SRC-001 byte-exact inherited ledger copy drift")
    ledgers = (audit_path, response_path, stage_lock_path, attempt_path, proposal_path)

    def transport(body: dict[str, Any]) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=180.0) as client:
                response = client.post(
                    base_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
        except httpx.HTTPError as exc:
            raise RecoverableTransportError(type(exc).__name__) from exc
        if response.status_code in {408, 409, 425, 429} or response.status_code >= 500:
            retry_after = response.headers.get("Retry-After")
            delay = min(float(retry_after), 10.0) if retry_after and retry_after.isdigit() else 1.0
            time.sleep(delay)
            raise RecoverableTransportError(f"HTTP_{response.status_code}")
        if response.status_code >= 400:
            raise PermanentProviderError(f"permanent provider HTTP_{response.status_code}")
        try:
            value = response.json()
        except json.JSONDecodeError as exc:
            raise PermanentProviderError("provider envelope is not JSON") from exc
        if not isinstance(value, dict):
            raise PermanentProviderError("provider envelope must be an object")
        return value

    try:
        result = execute_source_v5(
            transport=transport,
            exclusion_registry=exclusion,
            inherited_proposal=inherited,
            audit_sink=lambda row: append_jsonl_fsync(audit_path, dict(row)),
            response_sink=lambda row: append_jsonl_fsync(response_path, dict(row)),
            stage_lock_sink=lambda row: append_jsonl_fsync(stage_lock_path, dict(row)),
            attempt_sink=lambda row: append_jsonl_fsync(attempt_path, dict(row)),
            proposal_sink=lambda row: append_jsonl_fsync(proposal_path, dict(row)),
        )
        proposals = result.pop("proposals")
        families, validation = materialize_and_validate_families(proposals, exclusion)
    except (Exception, KeyboardInterrupt) as exc:
        write_json(
            LIVE_ROOT / "terminal_error.json",
            {
                "status": "SOURCE_RECOVERY_V5_ABORTED_FAIL_CLOSED",
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
                "accepted_slots_persisted": _line_count(proposal_path),
                "complete_assembly_attempts_persisted": _line_count(attempt_path),
                "attempt_scoped_stage_locks_persisted": _line_count(stage_lock_path),
                "audit_events_persisted": _line_count(audit_path),
                "responses_persisted": _line_count(response_path),
                "command_level_retry_performed": False,
            },
        )
        raise

    data_root = LIVE_ROOT / "data_lock"
    data_root.mkdir()
    write_jsonl(data_root / "families.jsonl", families)
    write_json(data_root / "validation.json", validation)
    data_files = [
        {
            "path": str(path.relative_to(LIVE_ROOT)),
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        }
        for path in (*ledgers, data_root / "families.jsonl", data_root / "validation.json")
    ]
    write_json(
        data_root / "manifest.json",
        {
            "status": "R2_SOURCE_DATA_LOCK_COMPLETE_AWAITING_ENCODERS",
            "source_protocol_id": SOURCE_PROTOCOL_ID_V5,
            "authorization_id": AUTHORIZATION_ID,
            "preparation_manifest_sha256": sha256_file(PREPARATION_ROOT / "manifest.json"),
            "fixed_families": 128,
            "fixed_candidate_denominator": 256,
            "inherited_v4_slots": 1,
            "new_v5_slots": 127,
            "construction_role_is_truth": False,
            "first_complete_mechanically_valid_object_locked": True,
            "programmatic_text_rewriting_performed": False,
            "validation": validation,
            "files": data_files,
        },
    )
    write_json(
        data_root / "lock.json",
        {
            "status": "LOCKED_BEFORE_E5_DISTILUSE_OR_HUMAN_REVIEW",
            "manifest_sha256": sha256_file(data_root / "manifest.json"),
            "locked_at_unix_ns": time.time_ns(),
        },
    )
    result.update(
        {
            "status": "R2_SOURCE_DATA_LOCK_COMPLETE_AWAITING_ENCODERS",
            "data_manifest_sha256": sha256_file(data_root / "manifest.json"),
            "data_lock_sha256": sha256_file(data_root / "lock.json"),
            "family_validation": validation,
        }
    )
    write_json(LIVE_ROOT / "result.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("execute",))
    parser.add_argument("--authorization-receipt", type=Path, required=True)
    parser.add_argument("--allow-paid-api", action="store_true")
    args = parser.parse_args()
    print(canonical_json(execute(args.authorization_receipt, allow_paid_api=args.allow_paid_api)))


if __name__ == "__main__":
    main()
