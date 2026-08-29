#!/usr/bin/env python3
"""Prepare and enforce the sealed R2 measurement workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.r2_measurement import (
    RECORD_ID,
    RESEARCH_ID,
    RUN_ID,
    character_ngrams,
    family_key,
    template_signature,
    text_sha256,
)
from linkrag_eval.robust_fusion.similarity_dev_calibration import (
    canonical_json,
    sha256_file,
    write_json,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / "runs/robust_fusion/r2_measurement_v1" / RUN_ID
PREREG_ROOT = OUTPUT_ROOT / "preregistration"
FORMAL_FILES = (
    "docs/plans/robust-fusion-r2-research.md",
    "docs/plans/robust-fusion-r2-similarity-measurement.md",
    "docs/plans/robust-fusion-r1-to-r2-inheritance-matrix.md",
)
CODE_FILES = (
    "src/linkrag_eval/robust_fusion/r2_measurement.py",
    "src/linkrag_eval/robust_fusion/r2_measurement_power.py",
    "src/linkrag_eval/robust_fusion/r2_measurement_power_v2.py",
    "scripts/run_robust_fusion_r2_measurement.py",
    "scripts/run_robust_fusion_similarity_dev_calibration.py",
    "tests/unit/test_robust_fusion_r2_measurement.py",
    "tests/unit/test_robust_fusion_r2_measurement_power.py",
    "tests/unit/test_robust_fusion_r2_measurement_power_v2.py",
)
POWER_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_measurement_power_v2/robust-fusion-r2-measurement-power-v2-20260829"
)
R1_V1_ROOT = REPO_ROOT / (
    "runs/robust_fusion/similarity_dev_calibration_v1/"
    "internal-v6-dev-similarity-calibration-v1-20260829"
)
R1_SUPPLEMENT_ROOT = REPO_ROOT / (
    "runs/robust_fusion/similarity_dev_support_supplement_v1/"
    "internal-v6-dev-similarity-support-supplement-v1-20260829"
)
R1_ROUTE_ROOT = REPO_ROOT / (
    "runs/robust_fusion/internal_v6_route_evidence_v1/internal-v6-dev-route-evidence-v5-20260829"
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_sidecar(path: Path) -> None:
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{sha256_file(path)}  {path.name}\n", encoding="utf-8"
    )


def seal_preregistration() -> dict[str, Any]:
    if OUTPUT_ROOT.exists():
        raise RuntimeError("R2 measurement output root already exists; refusing overwrite")
    PREREG_ROOT.mkdir(parents=True, mode=0o700)
    records = []
    for relative in (*FORMAL_FILES, *CODE_FILES):
        path = REPO_ROOT / relative
        if not path.is_file():
            raise RuntimeError(f"missing R2 preregistration input: {relative}")
        records.append(
            {"path": relative, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}
        )
    power_files = []
    for name in (
        "simulation_setup_lock.json",
        "simulation_results.json",
        "manifest.json",
        "receipt.json",
    ):
        path = POWER_ROOT / name
        if not path.is_file():
            raise RuntimeError(f"missing completed power evidence: {path}")
        power_files.append({"path": str(path.relative_to(REPO_ROOT)), "sha256": sha256_file(path)})
    manifest = {
        "research_id": RESEARCH_ID,
        "record_id": RECORD_ID,
        "run_id": RUN_ID,
        "status": "PREREGISTERED_AWAITING_R2_DEV",
        "sealed_before_r2_text_score_or_human_result": True,
        "r1_terminal_disposition": "PERMANENT_INCONCLUSIVE_HARD_EXCLUDE",
        "human_rows_per_researcher": {"relation": 256, "similarity": 256, "total": 512},
        "files": records,
        "power_evidence": power_files,
    }
    write_json(PREREG_ROOT / "manifest.json", manifest)
    _write_sidecar(PREREG_ROOT / "manifest.json")
    lock = {
        "status": "SEALED_BEFORE_ANY_R2_CANDIDATE_TEXT_ENCODER_SCORE_OR_HUMAN_RESULT",
        "manifest_sha256": sha256_file(PREREG_ROOT / "manifest.json"),
        "sealed_at_unix_ns": time.time_ns(),
        "external_timestamp_claimed": False,
        "result_directories_present": [],
    }
    write_json(PREREG_ROOT / "lock.json", lock)
    _write_sidecar(PREREG_ROOT / "lock.json")
    receipt = {
        "receipt_type": "local_result_before_preregistration_receipt",
        "manifest_sha256": lock["manifest_sha256"],
        "lock_sha256": sha256_file(PREREG_ROOT / "lock.json"),
        "external_timestamp_claimed": False,
    }
    write_json(PREREG_ROOT / "receipt.json", receipt)
    _write_sidecar(PREREG_ROOT / "receipt.json")
    return {**lock, "receipt_sha256": sha256_file(PREREG_ROOT / "receipt.json")}


def verify_preregistration() -> dict[str, Any]:
    manifest = json.loads((PREREG_ROOT / "manifest.json").read_text(encoding="utf-8"))
    for record in manifest["files"]:
        path = REPO_ROOT / record["path"]
        if path.stat().st_size != record["size_bytes"] or sha256_file(path) != record["sha256"]:
            raise RuntimeError(f"sealed R2 preregistration drift: {record['path']}")
    lock = json.loads((PREREG_ROOT / "lock.json").read_text(encoding="utf-8"))
    if lock["manifest_sha256"] != sha256_file(PREREG_ROOT / "manifest.json"):
        raise RuntimeError("R2 preregistration manifest drift")
    return lock


def build_r1_exclusion_registry() -> dict[str, Any]:
    verify_preregistration()
    root = OUTPUT_ROOT / "exclusions"
    if root.exists():
        raise RuntimeError("R1 exclusion registry already exists; refusing overwrite")
    root.mkdir(mode=0o700)
    family_keys: set[str] = set()
    text_hashes: set[str] = set()
    template_hashes: set[str] = set()
    near_duplicate_ngrams: set[tuple[str, ...]] = set()
    v1_rows = _read_jsonl(R1_V1_ROOT / "candidate_similarity.jsonl")
    for row in v1_rows:
        family_keys.add(hashlib.sha256(str(row["query_uid"]).encode()).hexdigest())
        text_hashes.update(
            str(row[key])
            for key in ("candidate_content_sha256", "candidate_raw_content_sha256")
            if row.get(key)
        )
    route_queries = _read_jsonl(R1_ROUTE_ROOT / "method_view/queries.jsonl")
    route_chunks = _read_jsonl(R1_ROUTE_ROOT / "method_view/chunks.jsonl")
    route_families = _read_jsonl(R1_ROUTE_ROOT / "evaluation_view/families.jsonl")
    for row in route_families:
        for field in (
            "query_family_id",
            "document_family_id",
            "version_family_id",
            "counterfactual_template_family_id",
        ):
            family_keys.add(hashlib.sha256(str(row[field]).encode()).hexdigest())
    for value in [
        *(str(row["query_text"]) for row in route_queries),
        *(str(row["content"]) for row in route_chunks),
    ]:
        text_hashes.add(text_sha256(value))
        template_hashes.add(template_signature(value))
        near_duplicate_ngrams.add(tuple(sorted(character_ngrams(value))))
    supplement_rows = _read_jsonl(R1_SUPPLEMENT_ROOT / "data/families.jsonl")
    for row in supplement_rows:
        family_keys.add(
            family_key(
                {
                    "query": row["query"],
                    "reference": row["reference"],
                    "provenance_id": row["query_origin"],
                }
            )
        )
        for field in ("query", "reference", "equivalent_candidate", "factual_conflict_candidate"):
            value = str(row[field])
            text_hashes.add(text_sha256(value))
            template_hashes.add(template_signature(value))
            near_duplicate_ngrams.add(tuple(sorted(character_ngrams(value))))
    registry = {
        "research_id": RESEARCH_ID,
        "status": "R1_HARD_EXCLUSION_REGISTRY_LOCKED",
        "r1_v1_family_rows": len(v1_rows),
        "r1_supplement_families": len(supplement_rows),
        "r1_route_queries": len(route_queries),
        "r1_route_chunks": len(route_chunks),
        "family_keys": sorted(family_keys),
        "text_sha256": sorted(text_hashes),
        "template_sha256": sorted(template_hashes),
        "near_duplicate_ngrams": [list(value) for value in sorted(near_duplicate_ngrams)],
        "near_duplicate_rule": "normalized character 5-gram Jaccard >=0.82 rejects",
        "historical_blind_exclusions": ["blind-v4", "blind-v5"],
        "inputs": [
            {
                "path": str((R1_V1_ROOT / "candidate_similarity.jsonl").relative_to(REPO_ROOT)),
                "sha256": sha256_file(R1_V1_ROOT / "candidate_similarity.jsonl"),
            },
            {
                "path": str((R1_SUPPLEMENT_ROOT / "data/families.jsonl").relative_to(REPO_ROOT)),
                "sha256": sha256_file(R1_SUPPLEMENT_ROOT / "data/families.jsonl"),
            },
            {
                "path": str((R1_ROUTE_ROOT / "method_view/queries.jsonl").relative_to(REPO_ROOT)),
                "sha256": sha256_file(R1_ROUTE_ROOT / "method_view/queries.jsonl"),
            },
            {
                "path": str((R1_ROUTE_ROOT / "method_view/chunks.jsonl").relative_to(REPO_ROOT)),
                "sha256": sha256_file(R1_ROUTE_ROOT / "method_view/chunks.jsonl"),
            },
            {
                "path": str(
                    (R1_ROUTE_ROOT / "evaluation_view/families.jsonl").relative_to(REPO_ROOT)
                ),
                "sha256": sha256_file(R1_ROUTE_ROOT / "evaluation_view/families.jsonl"),
            },
        ],
    }
    write_json(root / "registry.json", registry)
    _write_sidecar(root / "registry.json")
    write_json(root / "manifest.json", {"registry_sha256": sha256_file(root / "registry.json")})
    _write_sidecar(root / "manifest.json")
    return {"registry_sha256": sha256_file(root / "registry.json"), **registry}


def audit_legacy_inventory_metadata_only() -> dict[str, Any]:
    verify_preregistration()
    root = OUTPUT_ROOT / "legacy_inventory_audit"
    if root.exists():
        raise RuntimeError("legacy inventory audit already exists; refusing overwrite")
    root.mkdir(mode=0o700)
    gate_root = REPO_ROOT / "runs/robust_fusion/gate_a"
    files = []
    for path in sorted(gate_root.glob("*")):
        if path.is_file():
            files.append(
                {
                    "path": str(path.relative_to(REPO_ROOT)),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                    "content_parsed": False,
                }
            )
    result = {
        "audit_id": "ROBUST-FUSION-R2-LEGACY-ELIGIBILITY-AUDIT-2026-08-29-v1",
        "status": "NOT_ELIGIBLE_METADATA_INSUFFICIENT",
        "outcome_blind": True,
        "content_or_ranking_results_read": False,
        "allowed_operations": ["file identity", "byte size", "SHA-256"],
        "files_observed_without_parsing": files,
        "reason": "no separately allowlisted family/provenance/strata inventory was present; preflight JSON content was not parsed",
        "historical_blind_v4_v5": "PERMANENTLY_EXCLUDED",
        "gate_authorized": False,
    }
    write_json(root / "audit.json", result)
    _write_sidecar(root / "audit.json")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=("seal-prereg", "verify-prereg", "build-r1-exclusions", "audit-legacy")
    )
    args = parser.parse_args()
    functions = {
        "seal-prereg": seal_preregistration,
        "verify-prereg": verify_preregistration,
        "build-r1-exclusions": build_r1_exclusion_registry,
        "audit-legacy": audit_legacy_inventory_metadata_only,
    }
    print(canonical_json(functions[args.command]()))


if __name__ == "__main__":
    main()
