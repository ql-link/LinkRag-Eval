#!/usr/bin/env python3
"""Paid R2 source generator; fail-closed until an explicit receipt is supplied.

This file is sealed offline now. Do not execute it without later authorization.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import httpx
from dotenv import dotenv_values

from linkrag_eval.robust_fusion.r2_source_generation import (
    EXPECTED_BASE_URL,
    EXPECTED_MODEL,
    SOURCE_PROTOCOL_ID,
    canonical_json,
    execute_with_transport,
)
from linkrag_eval.robust_fusion.similarity_dev_calibration import (
    sha256_file,
    write_json,
    write_jsonl,
)
from scripts.prepare_robust_fusion_r2_source_generation import verify as verify_preparation

REPO_ROOT = Path(__file__).resolve().parents[1]
PREPARATION_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_generation_preparation_v1/"
    "robust-fusion-r2-source-generation-preparation-v1-20260829"
)
LIVE_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_generation_v1/robust-fusion-r2-source-generation-v1-20260829"
)


def validate_authorization(path: Path, *, allow_paid_api: bool) -> dict[str, object]:
    if not allow_paid_api:
        raise RuntimeError("paid API execution requires --allow-paid-api")
    if not path.is_file():
        raise RuntimeError("explicit authorization receipt is missing")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "authorization_id",
        "authorized_by",
        "source_protocol_id",
        "preparation_manifest_sha256",
        "price_snapshot_sha256",
        "max_usd",
        "authorized_at",
    }
    if set(receipt) != required:
        raise RuntimeError("authorization receipt schema drift")
    manifest_sha = (
        __import__("hashlib").sha256((PREPARATION_ROOT / "manifest.json").read_bytes()).hexdigest()
    )
    price_sha = (
        __import__("hashlib")
        .sha256(
            (
                REPO_ROOT / "docs/plans/robust-fusion-r2-source-generation-price-snapshot-v1.json"
            ).read_bytes()
        )
        .hexdigest()
    )
    if (
        receipt["source_protocol_id"] != SOURCE_PROTOCOL_ID
        or receipt["preparation_manifest_sha256"] != manifest_sha
        or receipt["price_snapshot_sha256"] != price_sha
        or float(receipt["max_usd"]) != 5.0
    ):
        raise RuntimeError("authorization receipt does not match sealed preparation")
    identity_fields = ("authorization_id", "authorized_by", "authorized_at")
    if any(
        not isinstance(receipt[field], str)
        or not receipt[field].strip()
        or receipt[field].startswith("FILL_")
        for field in identity_fields
    ):
        raise RuntimeError("authorization receipt has not been completed by the approver")
    return receipt


def initialize_live_root(path: Path = LIVE_ROOT) -> None:
    if path.exists():
        raise RuntimeError("live source-generation root exists; replay/overwrite refused")
    path.mkdir(parents=True, mode=0o700)


def append_audit_event(path: Path, event: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json(event) + "\n")
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


def execute(authorization_path: Path, *, allow_paid_api: bool) -> dict[str, object]:
    verify_preparation()
    dry_lock = PREPARATION_ROOT / "dry_run_lock.json"
    if not dry_lock.is_file():
        raise RuntimeError("sealed zero-network dry-run is missing")
    receipt = validate_authorization(authorization_path, allow_paid_api=allow_paid_api)
    preparation_manifest = PREPARATION_ROOT / "manifest.json"
    preparation_lock = PREPARATION_ROOT / "lock.json"
    if not preparation_manifest.is_file() or not preparation_lock.is_file():
        raise RuntimeError("sealed offline preparation is missing")
    base_url, _model, api_key = _load_provider()
    exclusion_path = REPO_ROOT / (
        "runs/robust_fusion/r2_measurement_v1/"
        "robust-fusion-r2-measurement-v1-20260829/exclusions/registry.json"
    )
    exclusion = json.loads(exclusion_path.read_text(encoding="utf-8"))
    initialize_live_root()
    write_json(
        LIVE_ROOT / "authorization_receipt_snapshot.json",
        {**receipt, "source_path_sha256": sha256_file(authorization_path)},
    )
    audit_path = LIVE_ROOT / "call_audit.jsonl"
    audit_path.touch(exist_ok=False)

    def transport(body: dict[str, object]) -> dict[str, object]:
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
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError("provider transport failure") from exc
        value = response.json()
        if not isinstance(value, dict):
            raise TypeError("provider response must be an object")
        return value

    try:
        result = execute_with_transport(
            transport=transport,
            exclusion_registry=exclusion,
            audit_sink=lambda event: append_audit_event(audit_path, dict(event)),
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        write_json(
            LIVE_ROOT / "terminal_error.json",
            {"status": "SOURCE_GENERATION_ABORTED_FAIL_CLOSED", "error_type": type(exc).__name__},
        )
        raise
    result.pop("audits")
    proposals = result.pop("proposals")
    write_jsonl(LIVE_ROOT / "proposals_not_truth.jsonl", proposals)
    write_json(LIVE_ROOT / "result.json", result)
    files = []
    for name in (
        "authorization_receipt_snapshot.json",
        "call_audit.jsonl",
        "proposals_not_truth.jsonl",
        "result.json",
    ):
        path = LIVE_ROOT / name
        files.append({"path": name, "sha256": sha256_file(path), "size_bytes": path.stat().st_size})
    write_json(
        LIVE_ROOT / "manifest.json",
        {
            "status": result["status"],
            "preparation_manifest_sha256": sha256_file(preparation_manifest),
            "files": files,
        },
    )
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
