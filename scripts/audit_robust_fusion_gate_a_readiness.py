#!/usr/bin/env python3
"""Audit every prerequisite that must close before Robust Fusion Gate A.

The audit is deliberately outcome-blind.  It reads protocol text, control
manifests, checksums, git state and artifact presence only.  It never reads a
Gate A/Blind candidate pool, ranking score or research outcome, and it cannot
unlock either cohort.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

ARTIFACT_VERSION = "ROBUST-FUSION-GATE-A-READINESS-PREFLIGHT-2026-08-29-v4"
SCIENTIFIC_PROTOCOL = "ROBUST-FUSION-RESEARCH-2026-08-29-v26"
ENGINEERING_PROTOCOL = "ROBUST-FUSION-ENGINEERING-2026-08-29-v17"
PROGRESS_RECORD = "ROBUST-FUSION-PROGRESS-2026-08-29-v28"
RERANKER_SELECTION_PROGRESS_RECORD = "ROBUST-FUSION-PROGRESS-2026-08-28-v19"
DATA_AUDIT_RECORD = "ROBUST-FUSION-GATE-A-DATA-AUDIT-2026-08-28-v10"
SIMILARITY_MANIFEST_RECORD = "ROBUST-FUSION-SIMILARITY-MANIFEST-2026-08-28-v5"
SIMILARITY_QUALIFICATION_RECORD = (
    "ROBUST-FUSION-SIMILARITY-ENCODER-QUALIFICATION-2026-08-28-v3"
)
RERANKER_QUALIFICATION_RECORD = "ROBUST-FUSION-RERANKER-QUALIFICATION-2026-08-28-v2"
PROVIDER_ROUTE_POLICY_ID = (
    "ROBUST-FUSION-PROVIDER-ROUTE-SNAPSHOT-POLICY-2026-08-29-v2"
)
HISTORICAL_ROUTE_MANIFEST_SHA256 = (
    "640e3d52a2f7cfc6f991cefe4d111ae18d09ba3260626a2e927988b5cd17a38a"
)
HISTORICAL_ROUTE_GENERATOR_SHA256 = (
    "01ba5f6b0b729adaa556755750974692722e47e69ada1caaac0fd0ced3371814"
)
HISTORICAL_REPLAY_CONTRACT_SHA256 = (
    "c2d12f961a18a1fbe9d5b4da857a51c6983e0c2502ed55b11c59e0a59dcc48c0"
)
HISTORICAL_DENSE_DIAGNOSTIC_MANIFEST_SHA256 = (
    "3606a60aca87d41f959214c121b402a1c0ea303d228629cfac622d5648ec9081"
)

REQUIRED_PRE_GATE_TASKS = (
    "P0-03",
    "P2-01",
    "P2-04",
    "P2-05",
    "P2-06",
    "P3-02",
    "P3-03",
    "P3-04",
    "P3-05",
    "P3-06",
    "P4-00",
    "P4-01",
    "P4-02",
    "P4-03",
    "P4-04",
    "P4-05",
    "P4-06",
    "P5-01",
    "P5-02",
    "P5-03",
    "P5-04",
    "P5-05",
    "P5-06",
    "P5-07",
    "P5-08",
)

HUMAN_REQUIRED_TASKS = {"P2-05", "P2-06", "P3-04"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def verify_checksum_manifest(root: Path) -> tuple[bool, list[str]]:
    checksum_path = root / "manifest.sha256"
    if not checksum_path.is_file():
        return False, ["manifest.sha256 missing"]
    errors: list[str] = []
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            errors.append(f"invalid checksum row: {line[:80]}")
            continue
        expected, relative = match.groups()
        target = root / relative
        if not target.is_file():
            errors.append(f"missing: {relative}")
        elif sha256_file(target) != expected:
            errors.append(f"checksum mismatch: {relative}")
    return not errors, errors


def git_snapshot(root: Path) -> dict[str, Any]:
    if not (root / ".git").exists():
        return {"available": False, "root": str(root), "clean": False}

    def run(*args: str) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()

    status = run("status", "--porcelain=v1", "--untracked-files=all")
    return {
        "available": True,
        "root": str(root),
        "head": run("rev-parse", "HEAD"),
        "clean": not bool(status),
        "dirty_entry_count": len(status.splitlines()) if status else 0,
    }


def parse_task_statuses(todo_text: str) -> dict[str, str]:
    pattern = re.compile(r"^- \[([x -])\] \*\*(P\d+-\d+[A-Z]?)\b", re.MULTILINE)
    marker_to_status = {"x": "COMPLETE", "-": "IN_PROGRESS", " ": "INCOMPLETE"}
    return {task: marker_to_status[marker] for marker, task in pattern.findall(todo_text)}


def make_check(
    check_id: str,
    stage: str,
    passed: bool,
    *,
    blocked_kind: str,
    evidence: dict[str, Any],
    next_action: str,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "stage": stage,
        "status": "PASS" if passed else blocked_kind,
        "blocking": not passed,
        "evidence": evidence,
        "next_action": None if passed else next_action,
    }


def build_report(repository_root: Path, linkrag_root: Path) -> dict[str, Any]:
    docs = {
        "scientific": repository_root / "docs/plans/robust-fusion-research.md",
        "engineering": repository_root / "docs/plans/robust-fusion-engineering.md",
        "progress": repository_root / "docs/plans/robust-fusion-todo.md",
        "data_audit": repository_root
        / "docs/reports/robust_fusion_gate_a_data_coverage_audit_2026_08_28.md",
        "similarity": repository_root / "docs/plans/robust-fusion-similarity-manifest.md",
        "handbook": repository_root / "docs/plans/robust-fusion-annotation-handbook.md",
    }
    missing_docs = [str(path) for path in docs.values() if not path.is_file()]
    if missing_docs:
        raise FileNotFoundError(f"missing authoritative documents: {missing_docs}")

    doc_text = {name: path.read_text(encoding="utf-8") for name, path in docs.items()}
    required_records = {
        "scientific": SCIENTIFIC_PROTOCOL,
        "engineering": ENGINEERING_PROTOCOL,
        "progress": PROGRESS_RECORD,
        "data_audit": DATA_AUDIT_RECORD,
    }
    protocol_pass = all(record in doc_text[name] for name, record in required_records.items())
    checks: list[dict[str, Any]] = [
        make_check(
            "protocol_version_alignment",
            "P0",
            protocol_pass,
            blocked_kind="BLOCKED_GOVERNANCE",
            evidence={
                name: {"record": record, "sha256": sha256_file(docs[name])}
                for name, record in required_records.items()
            },
            next_action="Align all current authority records before generating any formal snapshot.",
        )
    ]

    route_root = repository_root / "runs/robust_fusion/contracts/route-contract-preflight-v2"
    route_manifest_path = route_root / "manifest.json"
    route_manifest = load_json(route_manifest_path) if route_manifest_path.is_file() else {}
    route_checksums_ok, route_checksum_errors = verify_checksum_manifest(route_root)
    routes = route_manifest.get("routes", {})
    dense = routes.get("dense", {}) if isinstance(routes, dict) else {}
    sparse = routes.get("learned_sparse", {}) if isinstance(routes, dict) else {}
    bm25 = routes.get("bm25", {}) if isinstance(routes, dict) else {}
    route_generator = route_manifest.get("generator", {})
    route_script = repository_root / "scripts/probe_robust_fusion_route_contract.py"
    replay_contract_script = (
        repository_root / "src/linkrag_eval/robust_fusion/replay_contract.py"
    )
    route_refresh_failure_path = (
        repository_root
        / "runs/robust_fusion/contracts/route-contract-preflight-v1-refresh-v19/failure.json"
    )
    route_refresh_failure = (
        load_json(route_refresh_failure_path) if route_refresh_failure_path.is_file() else {}
    )
    route_blob = canonical_json(routes).lower()
    route_manifest_sha256 = (
        sha256_file(route_manifest_path) if route_manifest_path.is_file() else None
    )
    historical_route_evidence_ok = all(
        (
            route_manifest.get("status")
            == "LOCAL_CONFIG_AND_LIVE_DENSE_TOLERANCE_SPARSE_EXACT_REPLAY_PASS",
            route_manifest.get("scientific_protocol")
            == "ROBUST-FUSION-RESEARCH-2026-08-28-v19",
            route_manifest.get("engineering_protocol")
            == "ROBUST-FUSION-ENGINEERING-2026-08-29-v10",
            dense.get("model") == "text-embedding-v4",
            dense.get("dimension") == 1024,
            len(dense.get("probe_vectors", [])) == 4,
            sparse.get("provider") == "ark",
            sparse.get("model") == "doubao-embedding-vision-251215",
            len(sparse.get("probe_vectors", [])) == 4,
            bm25.get("mode") == "sqlite_fts5",
            "bge" not in route_blob,
            route_checksums_ok,
            route_manifest_sha256 == HISTORICAL_ROUTE_MANIFEST_SHA256,
            route_generator.get("sha256") == HISTORICAL_ROUTE_GENERATOR_SHA256,
            route_generator.get("replay_contract_sha256")
            == HISTORICAL_REPLAY_CONTRACT_SHA256,
            route_manifest.get("gate_a_executed") is False,
            route_manifest.get("outcome_data_read") is False,
        )
    )
    replay_contract_text = replay_contract_script.read_text(encoding="utf-8")
    route_script_text = route_script.read_text(encoding="utf-8")
    current_provider_policy_ok = all(
        (
            PROVIDER_ROUTE_POLICY_ID in doc_text["scientific"],
            PROVIDER_ROUTE_POLICY_ID in doc_text["engineering"],
            PROVIDER_ROUTE_POLICY_ID in replay_contract_text,
            "PROVIDER_ROUTE_POLICY_ID" in route_script_text,
            "DENSE_REPLAY_TOLERANCE" not in replay_contract_text,
            "within_frozen_numeric_tolerance" not in replay_contract_text,
            '"numeric_gate_applied": False' in replay_contract_text,
            '"numeric_acceptance_threshold": None' in route_script_text,
            '"numeric_replay_gate": "NONE"' in route_script_text,
        )
    )
    route_pass = historical_route_evidence_ok and current_provider_policy_ok
    checks.append(
        make_check(
            "actual_three_route_preflight",
            "P4-00",
            route_pass,
            blocked_kind="BLOCKED_AUTOMATIC",
            evidence={
                "artifact": str(route_manifest_path.relative_to(repository_root)),
                "manifest_sha256": route_manifest_sha256,
                "artifact_role": "HISTORICAL_ROUTE_AND_SCHEMA_EVIDENCE",
                "historical_route_evidence_ok": historical_route_evidence_ok,
                "historical_generator_hashes_preserved": route_generator.get("sha256")
                == HISTORICAL_ROUTE_GENERATOR_SHA256
                and route_generator.get("replay_contract_sha256")
                == HISTORICAL_REPLAY_CONTRACT_SHA256,
                "dense_model": dense.get("model"),
                "sparse_provider": sparse.get("provider"),
                "sparse_model": sparse.get("model"),
                "bm25_mode": bm25.get("mode"),
                "checksum_errors": route_checksum_errors,
                "current_policy_id": PROVIDER_ROUTE_POLICY_ID,
                "current_provider_policy_ok": current_provider_policy_ok,
                "numeric_replay_gate": "NONE",
                "numeric_comparison_role": "DESCRIPTIVE_ONLY",
                "snapshot_policy": "ONE_AUTHORIZED_GENERATION_THEN_HASH_SEAL",
                "historical_dense_diagnostic_manifest_sha256": (
                    HISTORICAL_DENSE_DIAGNOSTIC_MANIFEST_SHA256
                ),
                "latest_refresh_failure": route_refresh_failure or None,
            },
            next_action=(
                "Restore the immutable historical v2 route/schema evidence or align the current "
                "no-numeric-gate provider snapshot policy. Do not rerun or select a run because "
                "provider scores differ; BGE-M3 remains forbidden."
            ),
        )
    )

    eligibility_root = repository_root / "data/robust_fusion/derived/gate_a_eligibility_v1"
    eligibility_path = eligibility_root / "manifest.json"
    eligibility = load_json(eligibility_path) if eligibility_path.is_file() else {}
    eligibility_checksums_ok, eligibility_checksum_errors = verify_checksum_manifest(
        eligibility_root
    )
    datasets = eligibility.get("datasets", {})
    t2 = datasets.get("t2ranking", {}) if isinstance(datasets, dict) else {}
    cmed = datasets.get("cmedqa2", {}) if isinstance(datasets, dict) else {}
    du = datasets.get("duretrieval", {}) if isinstance(datasets, dict) else {}
    eligibility_generator = eligibility.get("generator", {})
    eligibility_script = repository_root / "scripts/prepare_robust_fusion_gate_a_eligibility.py"
    eligibility_pass = all(
        (
            eligibility.get("scientific_protocol") == SCIENTIFIC_PROTOCOL,
            eligibility.get("status")
            == "ELIGIBILITY_UPPER_BOUNDS_ONLY_NOT_A_FINAL_GATE_DENOMINATOR",
            t2.get("train_query_count") == 258_042,
            t2.get("dev_query_count") == 24_831,
            t2.get("cross_split_family_count") == 0,
            cmed.get("gatea_eligible_upper_bound") == 99_894,
            cmed.get("gateb_eligible_upper_bound") == 3_954,
            cmed.get("domain_specific_endpoint") is False,
            du.get("corpus_count") == 100_001,
            du.get("query_count") == 2_000,
            du.get("qrel_count") == 9_839,
            du.get("all_rows_preserved") is True,
            eligibility_checksums_ok,
            eligibility_generator.get("sha256") == sha256_file(eligibility_script),
        )
    )
    checks.append(
        make_check(
            "public_data_first_layer_eligibility",
            "P3-02",
            eligibility_pass,
            blocked_kind="BLOCKED_AUTOMATIC",
            evidence={
                "artifact": str(eligibility_path.relative_to(repository_root)),
                "manifest_sha256": sha256_file(eligibility_path)
                if eligibility_path.is_file()
                else None,
                "t2_train_upper_bound": t2.get("eligible_upper_bound"),
                "cmedqa2_gatea_upper_bound": cmed.get("gatea_eligible_upper_bound"),
                "cmedqa2_gateb_upper_bound": cmed.get("gateb_eligible_upper_bound"),
                "duretrieval_role": du.get("role"),
                "checksum_errors": eligibility_checksum_errors,
            },
            next_action="Rebuild the ID/hash-only eligibility artifact from pinned public inputs.",
        )
    )

    internal_root = repository_root / "data/robust_fusion/internal_stress_v6"
    internal_manifest_path = internal_root / "control/root_manifest.json"
    internal_manifest = load_json(internal_manifest_path) if internal_manifest_path.is_file() else {}
    internal_checksums_ok, internal_checksum_errors = verify_checksum_manifest(internal_root)
    internal_protocols = internal_manifest.get("protocol_records", {})
    expected_internal_protocols = {
        "scientific_protocol": SCIENTIFIC_PROTOCOL,
        "engineering_protocol": ENGINEERING_PROTOCOL,
        "progress_record": PROGRESS_RECORD,
        "data_audit_record": DATA_AUDIT_RECORD,
    }
    internal_authoritative_paths = {
        "scientific_protocol": docs["scientific"],
        "engineering_protocol": docs["engineering"],
        "progress_record": docs["progress"],
        "data_audit": docs["data_audit"],
        "asset_reconciliation": repository_root
        / "docs/reports/sqlite_share_restore_and_asset_reconciliation_2026_08_28.md",
        "internal_v6_protocol": repository_root
        / "docs/plans/robust-fusion-internal-stress-v6.md",
    }
    internal_authoritative_hashes = internal_manifest.get("authoritative_document_sha256", {})
    current_internal_authoritative_hashes = {
        name: sha256_file(path) for name, path in internal_authoritative_paths.items()
    }
    internal_authoritative_hashes_match = all(
        internal_authoritative_hashes.get(name) == digest
        for name, digest in current_internal_authoritative_hashes.items()
    )
    internal_skeleton_pass = all(
        (
            internal_manifest.get("package_version")
            == "ROBUST-FUSION-INTERNAL-STRESS-2026-08-28-v6",
            internal_manifest.get("state")
            == "FORMALLY_ESTABLISHED_AWAITING_NEW_REAL_QUERY_INTAKE",
            internal_manifest.get("gate_eligibility") == "NOT_ELIGIBLE",
            all(
                internal_protocols.get(key) == value
                for key, value in expected_internal_protocols.items()
            ),
            internal_authoritative_hashes_match,
            internal_checksums_ok,
            (internal_root / "gatea/METHOD_ACCESS_LOCK.json").is_file(),
            (internal_root / "blind/METHOD_ACCESS_LOCK.json").is_file(),
        )
    )
    checks.append(
        make_check(
            "internal_v6_governance_skeleton",
            "P3-04",
            internal_skeleton_pass,
            blocked_kind="BLOCKED_GOVERNANCE",
            evidence={
                "artifact": str(internal_manifest_path.relative_to(repository_root)),
                "state": internal_manifest.get("state"),
                "gate_eligibility": internal_manifest.get("gate_eligibility"),
                "checksum_errors": internal_checksum_errors,
                "authoritative_document_hashes_match": internal_authoritative_hashes_match,
            },
            next_action="Rebuild the empty governed v6 package before any intake.",
        )
    )
    internal_population_pass = internal_manifest.get("gate_eligibility") == "ELIGIBLE"
    checks.append(
        make_check(
            "internal_v6_real_population_and_adjudication",
            "P3-04",
            internal_population_pass,
            blocked_kind="BLOCKED_HUMAN",
            evidence={
                "state": internal_manifest.get("state"),
                "gate_eligibility": internal_manifest.get("gate_eligibility"),
                "reason": internal_manifest.get("reason_not_eligible"),
            },
            next_action=(
                "Intake new authorized real query/evidence families, then complete independent review, "
                "family-overlap rejection and the population seal."
            ),
        )
    )

    calibration_root = repository_root / "data/robust_fusion/derived/p2_calibration_v2"
    calibration_path = calibration_root / "manifest.json"
    calibration = load_json(calibration_path) if calibration_path.is_file() else {}
    calibration_checksums_ok, calibration_checksum_errors = verify_checksum_manifest(
        calibration_root
    )
    calibration_builder_path = (
        repository_root / "scripts/prepare_robust_fusion_p2_calibration_replay.py"
    )
    delivery_root = repository_root / "runs/robust_fusion/p2_human_calibration_v2"
    delivery_path = delivery_root / "delivery_manifest.json"
    delivery = load_json(delivery_path) if delivery_path.is_file() else {}
    delivery_checksum_path = delivery_root / "delivery_manifest.sha256"
    delivery_manifest_sha256 = sha256_file(delivery_path) if delivery_path.is_file() else None
    delivery_checksum_ok = (
        delivery_manifest_sha256 is not None
        and delivery_checksum_path.is_file()
        and delivery_checksum_path.read_text(encoding="utf-8")
        == f"{delivery_manifest_sha256}  delivery_manifest.json\n"
    )
    delivery_generator_path = (
        repository_root / "scripts/materialize_robust_fusion_p2_human_delivery.py"
    )
    role_receipts: dict[str, dict[str, Any]] = {}
    role_packages_ok = True
    for reviewer_id, dirname in (("A", "annotator_a"), ("B", "annotator_b")):
        receipt_path = delivery_root / dirname / "package_receipt.json"
        receipt = load_json(receipt_path) if receipt_path.is_file() else {}
        role_receipts[reviewer_id] = receipt
        role_packages_ok = role_packages_ok and all(
            (
                receipt.get("reviewer_id") == reviewer_id,
                receipt.get("answer_key_included") is False,
                receipt.get("master_manifest_sha256")
                == delivery.get("manifest_sha256"),
            )
        )
    calibration_package_pass = all(
        (
            calibration.get("package_version")
            == "ROBUST-FUSION-P2-CALIBRATION-REPLAY-2026-08-29-v2",
            calibration.get("case_count") == 12,
            calibration.get("case_qualification_row_count") == 12,
            calibration.get("candidate_annotation_row_count") == 13,
            calibration.get("pair_annotation_row_count") == 1,
            calibration.get("gate_a_authorized") is False,
            calibration.get("gate_b_authorized") is False,
            calibration_checksums_ok,
            calibration.get("builder", {}).get("sha256")
            == sha256_file(calibration_builder_path),
            delivery.get("delivery_version")
            == "ROBUST-FUSION-P2-HUMAN-DELIVERY-2026-08-29-v1",
            delivery.get("formal_human_entry") is True,
            delivery.get("prior_model_or_tool_fills_eligible") is False,
            delivery.get("facilitator_key_included") is False,
            delivery.get("manifest_sha256") == sha256_file(calibration_path),
            delivery.get("generator", {}).get("sha256")
            == sha256_file(delivery_generator_path),
            delivery_checksum_ok,
            role_packages_ok,
            not any(delivery_root.rglob("facilitator_key.jsonl")),
        )
    )
    checks.append(
        make_check(
            "p2_calibration_input_package",
            "P2-05",
            calibration_package_pass,
            blocked_kind="BLOCKED_AUTOMATIC",
            evidence={
                "artifact": str(calibration_path.relative_to(repository_root)),
                "package_version": calibration.get("package_version"),
                "case_count": calibration.get("case_count"),
                "checksum_errors": calibration_checksum_errors,
                "delivery_artifact": str(delivery_path.relative_to(repository_root)),
                "delivery_version": delivery.get("delivery_version"),
                "delivery_manifest_sha256": delivery_manifest_sha256,
                "formal_human_entry": delivery.get("formal_human_entry"),
                "prior_model_or_tool_fills_eligible": delivery.get(
                    "prior_model_or_tool_fills_eligible"
                ),
                "facilitator_key_included": delivery.get("facilitator_key_included"),
                "role_receipts": {
                    role: {
                        "reviewer_id": receipt.get("reviewer_id"),
                        "answer_key_included": receipt.get("answer_key_included"),
                    }
                    for role, receipt in role_receipts.items()
                },
            },
            next_action="Rebuild the clean v2 human delivery from the pinned administrator package.",
        )
    )
    calibration_result_path = (
        delivery_root / "facilitator_review/calibration_result.json"
    )
    calibration_result = (
        load_json(calibration_result_path) if calibration_result_path.is_file() else {}
    )
    calibration_result_pass = all(
        (
            calibration_result.get("status") == "PASS",
            calibration_result.get("package_version")
            == "ROBUST-FUSION-P2-CALIBRATION-REPLAY-2026-08-29-v2",
            calibration_result.get("human_annotator_count") == 2,
            calibration_result.get("model_or_tool_generated_submission_used") is False,
            calibration_result.get("all_disagreements_adjudicated") is True,
            calibration_result.get("machine_validation_error_count") == 0,
            isinstance(calibration_result.get("submission_lock_sha256"), str),
            len(calibration_result.get("submission_lock_sha256", "")) == 64,
        )
    )
    checks.append(
        make_check(
            "p2_double_annotation_adjudication",
            "P2-05",
            calibration_result_pass,
            blocked_kind="BLOCKED_HUMAN",
            evidence={
                "result_present": calibration_result_path.is_file(),
                "result_status": calibration_result.get("status"),
                "formal_result_path": str(
                    calibration_result_path.relative_to(repository_root)
                ),
                "human_annotator_count": calibration_result.get(
                    "human_annotator_count"
                ),
                "model_or_tool_generated_submission_used": calibration_result.get(
                    "model_or_tool_generated_submission_used"
                ),
                "required_rows_per_annotator": {
                    "case_qualification": 12,
                    "candidate": 13,
                    "candidate_pair": 1,
                },
            },
            next_action=(
                "Two annotators complete independent copies, the facilitator locks both submissions, "
                "adjudicates every disagreement and writes a validated PASS result."
            ),
        )
    )

    qualification_root = (
        repository_root
        / "runs/robust_fusion/contracts/similarity-encoder-qualification-v3"
    )
    qualification_path = qualification_root / "manifest.json"
    qualification = load_json(qualification_path) if qualification_path.is_file() else {}
    qualification_checksums_ok, qualification_checksum_errors = verify_checksum_manifest(
        qualification_root
    )
    qualification_models = qualification.get("models", [])
    by_role = {
        model.get("role"): model
        for model in qualification_models
        if isinstance(model, dict) and isinstance(model.get("role"), str)
    }
    main_encoder = by_role.get("main_similarity_encoder", {})
    audit_encoder = by_role.get("independent_audit_encoder", {})
    qualification_generator = qualification.get("generator", {})
    qualification_primitive = qualification.get("measurement_primitive", {})
    qualification_script = (
        repository_root / "scripts/qualify_robust_fusion_similarity_encoders.py"
    )
    similarity_primitive = repository_root / "src/linkrag_eval/robust_fusion/similarity.py"
    qualified_model_ids = [
        str(model.get("model_id", "")).lower()
        for model in qualification_models
        if isinstance(model, dict)
    ]
    qualification_pass = all(
        (
            qualification.get("artifact_version") == SIMILARITY_QUALIFICATION_RECORD,
            qualification.get("scientific_protocol") == SCIENTIFIC_PROTOCOL,
            qualification.get("similarity_manifest") == SIMILARITY_MANIFEST_RECORD,
            qualification.get("status")
            == "QUALIFIED_PRESELECTED_PENDING_DEV_CALIBRATION",
            qualification.get("selection_fixed_before_probe") is True,
            qualification.get("outcome_data_read") is False,
            qualification.get("gate_a_executed") is False,
            qualification.get("bge_m3") == "RETIRED_FORBIDDEN",
            main_encoder.get("model_id") == "intfloat/multilingual-e5-base",
            main_encoder.get("revision")
            == "d128750597153bb5987e10b1c3493a34e5a4502a",
            main_encoder.get("qualification_status") == "PASS",
            main_encoder.get("dimension") == 768,
            main_encoder.get("max_tokens") == 512,
            audit_encoder.get("model_id")
            == "sentence-transformers/distiluse-base-multilingual-cased-v2",
            audit_encoder.get("revision")
            == "bfe45d0732ca50787611c0fe107ba278c7f3f889",
            audit_encoder.get("qualification_status") == "PASS",
            audit_encoder.get("dimension") == 512,
            audit_encoder.get("max_tokens") == 128,
            main_encoder.get("architecture_family")
            != audit_encoder.get("architecture_family"),
            all("bge" not in model_id for model_id in qualified_model_ids),
            qualification.get("implementation", {}).get("sentence_transformers") == "5.7.0",
            qualification_checksums_ok,
            qualification_generator.get("sha256") == sha256_file(qualification_script),
            qualification_primitive.get("sha256") == sha256_file(similarity_primitive),
        )
    )
    checks.append(
        make_check(
            "non_bge_similarity_encoder_qualification",
            "P2-01",
            qualification_pass,
            blocked_kind="BLOCKED_AUTOMATIC",
            evidence={
                "artifact": str(qualification_path.relative_to(repository_root)),
                "manifest_sha256": sha256_file(qualification_path)
                if qualification_path.is_file()
                else None,
                "main_encoder": main_encoder.get("model_id"),
                "main_revision": main_encoder.get("revision"),
                "audit_encoder": audit_encoder.get("model_id"),
                "audit_revision": audit_encoder.get("revision"),
                "outcome_data_read": qualification.get("outcome_data_read"),
                "checksum_errors": qualification_checksum_errors,
            },
            next_action=(
                "Re-run the pinned outcome-free v3 qualification; do not substitute BGE-M3 or "
                "read Dev/Gate outcomes."
            ),
        )
    )

    reranker_root = repository_root / "runs/robust_fusion/contracts/reranker-qualification-v2"
    reranker_path = reranker_root / "manifest.json"
    reranker = load_json(reranker_path) if reranker_path.is_file() else {}
    reranker_checksums_ok, reranker_checksum_errors = verify_checksum_manifest(reranker_root)
    reranker_models = reranker.get("models", [])
    reranker_by_role = {
        model.get("role"): model
        for model in reranker_models
        if isinstance(model, dict) and isinstance(model.get("role"), str)
    }
    qwen_reranker = reranker_by_role.get("generative_instruction_reranker", {})
    jina_reranker = reranker_by_role.get("discriminative_cross_encoder", {})
    reranker_independence = reranker.get("family_independence", {})
    reranker_confirmation = reranker.get("research_lead_confirmation", {})
    reranker_generator = reranker.get("generator", {})
    reranker_script = repository_root / "scripts/qualify_robust_fusion_rerankers.py"
    reranker_selection_pass = all(
        (
            reranker.get("artifact_version") == RERANKER_QUALIFICATION_RECORD,
            reranker.get("scientific_protocol") == SCIENTIFIC_PROTOCOL,
            reranker.get("progress_record") == RERANKER_SELECTION_PROGRESS_RECORD,
            reranker.get("status")
            == "QUALIFIED_SELECTION_FROZEN_PENDING_RESOURCE_AND_DEV_CONTRACT",
            reranker.get("selection_fixed_before_probe") is True,
            reranker.get("selection_frozen_before_dev_and_gate_outcomes") is True,
            reranker.get("outcome_data_read") is False,
            reranker.get("gate_a_executed") is False,
            reranker.get("p3_05_complete") is False,
            reranker_confirmation.get("confirmed") is True,
            reranker_confirmation.get("non_commercial_jina_use_confirmed") is True,
            qwen_reranker.get("model_id") == "Qwen/Qwen3-Reranker-0.6B",
            qwen_reranker.get("revision")
            == "e61197ed45024b0ed8a2d74b80b4d909f1255473",
            qwen_reranker.get("qualification_status") == "PASS",
            jina_reranker.get("model_id")
            == "jinaai/jina-reranker-v2-base-multilingual",
            jina_reranker.get("revision")
            == "9cfeff2df7d40d1b78e75e5e9cebec92a99813c9",
            jina_reranker.get("qualification_status") == "PASS",
            reranker_independence.get("different_architecture") is True,
            reranker_independence.get("different_producer") is True,
            reranker_independence.get("different_scoring_head") is True,
            reranker_independence.get("shares_similarity_encoder_artifact") is False,
            reranker_checksums_ok,
            reranker_generator.get("sha256") == sha256_file(reranker_script),
        )
    )
    checks.append(
        make_check(
            "two_reranker_family_selection",
            "P3-05",
            reranker_selection_pass,
            blocked_kind="BLOCKED_AUTOMATIC",
            evidence={
                "artifact": str(reranker_path.relative_to(repository_root)),
                "manifest_sha256": sha256_file(reranker_path)
                if reranker_path.is_file()
                else None,
                "status": reranker.get("status"),
                "qwen_revision": qwen_reranker.get("revision"),
                "jina_revision": jina_reranker.get("revision"),
                "research_lead_confirmed": reranker_confirmation.get("confirmed"),
                "p3_05_complete": reranker.get("p3_05_complete"),
                "outcome_data_read": reranker.get("outcome_data_read"),
                "checksum_errors": reranker_checksum_errors,
            },
            next_action=(
                "Freeze the exact two-family selection before reading Dev or Gate outcomes; do not "
                "replace either family based on observed performance."
            ),
        )
    )

    similarity_pass = all(
        (
            SIMILARITY_MANIFEST_RECORD in doc_text["similarity"],
            "GATE_A_AUTHORIZATION: false" not in doc_text["similarity"],
        )
    )
    checks.append(
        make_check(
            "non_bge_similarity_measurement_freeze",
            "P2-01/P5-02",
            similarity_pass,
            blocked_kind="BLOCKED_AUTOMATIC",
            evidence={
                "manifest_record": SIMILARITY_MANIFEST_RECORD,
                "encoder_qualification": qualification.get("status"),
                "gate_a_authorization": "DENIED_PENDING_DEV"
                if "GATE_A_AUTHORIZATION: false" in doc_text["similarity"]
                else "FROZEN",
                "bge_forbidden": "BGE-M3 淘汰记录" in doc_text["similarity"],
            },
            next_action=(
                "Run the length-stratified independent-encoder/blinded-human audit and calibrate "
                "common support/bands on Dev only; do not change the frozen Qwen/Jina families."
            ),
        )
    )

    eval_git = git_snapshot(repository_root)
    linkrag_git = git_snapshot(linkrag_root)
    contract_lock = repository_root / "runs/robust_fusion/contracts/contract-lock.json"
    ci_green = repository_root / "runs/robust_fusion/contracts/ci-green.json"
    clean_contract_pass = all(
        (
            eval_git.get("clean") is True,
            linkrag_git.get("clean") is True,
            linkrag_git.get("head") == "861f24810c3482ec0d86768a24f952b1e08ae675",
            contract_lock.is_file(),
            ci_green.is_file(),
        )
    )
    checks.append(
        make_check(
            "clean_dual_repo_contract_lock_and_ci",
            "P4-00",
            clean_contract_pass,
            blocked_kind="BLOCKED_GOVERNANCE",
            evidence={
                "linkrag_eval_git": eval_git,
                "linkrag_git": linkrag_git,
                "contract_lock_present": contract_lock.is_file(),
                "remote_ci_evidence_present": ci_green.is_file(),
            },
            next_action=(
                "After preserving and committing the intended work, obtain a green remote CI run with both "
                "repositories clean and generate the formal contract-lock.json."
            ),
        )
    )

    task_statuses = parse_task_statuses(doc_text["progress"])
    task_rows = []
    for task in REQUIRED_PRE_GATE_TASKS:
        status = task_statuses.get(task, "MISSING_FROM_LEDGER")
        task_rows.append(
            {
                "task": task,
                "status": status,
                "human_required": task in HUMAN_REQUIRED_TASKS,
            }
        )
    pre_gate_tasks_pass = all(row["status"] == "COMPLETE" for row in task_rows)
    checks.append(
        make_check(
            "complete_pre_gate_task_ledger",
            "P0/P2/P3/P4/P5",
            pre_gate_tasks_pass,
            blocked_kind="BLOCKED_AUTOMATIC",
            evidence={
                "required_task_count": len(task_rows),
                "complete_task_count": sum(row["status"] == "COMPLETE" for row in task_rows),
                "tasks": task_rows,
            },
            next_action="Close every required P0/P2/P3/P4/P5 item with evidence before P6-01.",
        )
    )

    seal_path = repository_root / "runs/robust_fusion/gate_a/root-manifest.json"
    receipt_path = repository_root / "runs/robust_fusion/gate_a/timestamp-receipt.json"
    seal_pass = seal_path.is_file() and receipt_path.is_file()
    checks.append(
        make_check(
            "gate_a_snapshot_preregistration_and_external_timestamp",
            "P5-05/P5-07/P5-08",
            seal_pass,
            blocked_kind="BLOCKED_GOVERNANCE",
            evidence={
                "root_manifest_present": seal_path.is_file(),
                "timestamp_receipt_present": receipt_path.is_file(),
            },
            next_action=(
                "Only after P2-P4 completion: freeze estimands/thresholds/denominator, build the immutable "
                "snapshot, create the clean root hash and preserve its external timestamp receipt."
            ),
        )
    )

    blocking = [check for check in checks if check["blocking"]]
    return {
        "artifact_version": ARTIFACT_VERSION,
        "generated_on": "2026-08-29",
        "outcome_data_read": False,
        "gate_a_executed": False,
        "gate_a_unlocked": False,
        "overall_status": "READY_FOR_GATE_A" if not blocking else "NOT_READY_FOR_GATE_A",
        "summary": {
            "check_count": len(checks),
            "pass_count": len(checks) - len(blocking),
            "blocking_count": len(blocking),
            "blocked_by_kind": {
                kind: sum(check["status"] == kind for check in blocking)
                for kind in ("BLOCKED_AUTOMATIC", "BLOCKED_HUMAN", "BLOCKED_GOVERNANCE")
            },
        },
        "actual_route_contract": {
            "dense": "text-embedding-v4",
            "provider_route_policy": PROVIDER_ROUTE_POLICY_ID,
            "numeric_replay_gate": "NONE",
            "learned_sparse": "ark/doubao-embedding-vision-251215",
            "bm25": "sqlite_fts5",
            "bge_m3": "RETIRED_FORBIDDEN",
        },
        "critical_path": [
            "complete_dev_validity_and_freeze_non_bge_similarity_measurement",
            "complete_two_annotator_P2_calibration_and_resource_freeze",
            "complete_frozen_reranker_resource_and_dev_contract",
            "populate_internal_v6_with_new_real_query_evidence_families",
            "run_three_dataset_30_family_constructability_pilot_and_power_analysis",
            "complete_P4_snapshot_metric_and_leakage_instruments",
            "freeze_preregistration_denominator_snapshot_and_external_timestamp",
        ],
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repository-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--linkrag-root", type=Path, default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("runs/robust_fusion/gate_a/readiness-preflight-v4.json"),
    )
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    repository_root = args.repository_root.resolve()
    linkrag_root = (
        args.linkrag_root.resolve()
        if args.linkrag_root is not None
        else repository_root.parent / "LinkRag"
    )
    output = args.output if args.output.is_absolute() else repository_root / args.output
    if output.exists() and not args.replace:
        raise RuntimeError(f"refusing to overwrite existing readiness report: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = build_report(repository_root, linkrag_root)
    output.write_text(canonical_json(report) + "\n", encoding="utf-8")
    print(
        canonical_json(
            {
                "artifact_version": report["artifact_version"],
                "overall_status": report["overall_status"],
                "pass_count": report["summary"]["pass_count"],
                "blocking_count": report["summary"]["blocking_count"],
                "output": str(output),
                "sha256": sha256_file(output),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
