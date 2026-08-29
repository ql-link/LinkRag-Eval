#!/usr/bin/env python3
"""Lock and validate the four human submissions for the Dev supplement."""

from __future__ import annotations

import argparse
import csv
import json
import platform
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.similarity_dev_calibration import (
    canonical_json,
    sha256_file,
    write_json,
)
from linkrag_eval.robust_fusion.similarity_dev_calibration import (
    validate_submission as validate_v1_similarity_submission,
)
from linkrag_eval.robust_fusion.similarity_support_finalization import (
    build_final_relation_records,
    build_final_similarity_records,
    human_validity_summary,
    numeric_summary,
    require_zero_adjudication,
    support_summary,
    terminal_decision,
)

try:
    from scripts.run_robust_fusion_similarity_support_supplement import (
        DEFAULT_OUTPUT_ROOT,
        DEFAULT_V1_ROOT,
        read_jsonl,
        resolve_in_repo,
        verify_materialized,
        verify_preregistration,
        verify_v1_read_only,
    )
except ModuleNotFoundError:  # Direct ``python scripts/...py`` execution.
    from run_robust_fusion_similarity_support_supplement import (  # type: ignore[no-redef]
        DEFAULT_OUTPUT_ROOT,
        DEFAULT_V1_ROOT,
        read_jsonl,
        resolve_in_repo,
        verify_materialized,
        verify_preregistration,
        verify_v1_read_only,
    )

POST_LOCK_IMPLEMENTATION_DIR = Path(
    "human_review/facilitator/post_lock_finalizer_implementation_v1"
)
FINALIZATION_DIR = Path("human_review/facilitator/finalization_v1")
EXPECTED_RELATION_ROWS = 144
EXPECTED_SIMILARITY_ROWS = 48

RELATION_FIELDS = [
    "relation_audit_id",
    "target_reference_status",
    "target_group_status",
    "target_relation",
    "conflict_type",
    "evidence_locator",
    "rationale",
    "reviewer_id",
    "confidence",
    "uncertain",
    "adjudication_status",
]
SIMILARITY_FIELDS = [
    "similarity_audit_id",
    "human_similarity_ordinal",
    "confidence",
    "uncertain",
    "note",
]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_csv(path: Path, fields: list[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != fields:
            raise RuntimeError(f"submission header mismatch: {path}")
        return list(reader)


def submission_paths(root: Path) -> dict[str, Path]:
    return {
        "relation_a": root / "human_relation/annotator_a/submission.csv",
        "relation_b": root / "human_relation/annotator_b/submission.csv",
        "similarity_a": root / "human_similarity/annotator_a/submission.csv",
        "similarity_b": root / "human_similarity/annotator_b/submission.csv",
    }


def lock_submissions(root: Path) -> dict[str, Any]:
    facilitator = root / "human_review/facilitator"
    lock_path = facilitator / "submission_lock.json"
    if lock_path.exists():
        raise RuntimeError("refusing to overwrite human submission lock")
    paths = submission_paths(root)
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise RuntimeError(f"all four physical submissions are required before lock: {missing}")
    facilitator.mkdir(parents=True, mode=0o700)
    files = {}
    for name, path in paths.items():
        package_manifest = path.parent / "package_manifest.json"
        files[name] = {
            "relative_path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "package_manifest_sha256": sha256_file(package_manifest),
        }
    lock = {
        "status": "LOCKED_BEFORE_CONTENT_VALIDATION_OR_COMPARISON",
        "locked_at_local": now_iso(),
        "submissions": files,
    }
    write_json(lock_path, lock)
    lock_sha = sha256_file(lock_path)
    (facilitator / "submission_lock.sha256").write_text(
        f"{lock_sha}  submission_lock.json\n", encoding="utf-8"
    )
    return {"status": lock["status"], "submission_lock_sha256": lock_sha}


def verify_lock(root: Path) -> dict[str, Any]:
    facilitator = root / "human_review/facilitator"
    lock_path = facilitator / "submission_lock.json"
    lock_sha = sha256_file(lock_path)
    if (facilitator / "submission_lock.sha256").read_text(encoding="utf-8").split()[0] != lock_sha:
        raise RuntimeError("human submission lock receipt drift")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    for name, record in lock["submissions"].items():
        path = root / record["relative_path"]
        if path != submission_paths(root)[name]:
            raise RuntimeError(f"locked submission path drift: {name}")
        if path.stat().st_size != record["size_bytes"] or sha256_file(path) != record["sha256"]:
            raise RuntimeError(f"locked submission content drift: {name}")
        if sha256_file(path.parent / "package_manifest.json") != record["package_manifest_sha256"]:
            raise RuntimeError(f"locked package manifest drift: {name}")
    return {"submission_lock_sha256": lock_sha, **lock}


def _receipt_sha(path: Path, expected_name: str) -> str:
    parts = path.read_text(encoding="utf-8").split()
    if len(parts) != 2 or parts[1] != expected_name:
        raise RuntimeError(f"invalid receipt format: {path}")
    return parts[0]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8"
    )
    path.chmod(0o600)


def _manifest_files(directory: Path, names: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "path": name,
            "size_bytes": (directory / name).stat().st_size,
            "sha256": sha256_file(directory / name),
        }
        for name in names
    ]


def _write_manifest_and_receipt(
    directory: Path,
    *,
    schema_version: str,
    status: str,
    names: list[str],
    receipt_type: str,
    extra: dict[str, Any],
) -> dict[str, str]:
    manifest = {
        "schema_version": schema_version,
        "status": status,
        "files": _manifest_files(directory, names),
        **extra,
    }
    manifest_path = directory / "manifest.json"
    write_json(manifest_path, manifest)
    manifest_sha = sha256_file(manifest_path)
    (directory / "manifest.sha256").write_text(
        f"{manifest_sha}  manifest.json\n", encoding="utf-8"
    )
    receipt = {
        "receipt_type": receipt_type,
        "status": status,
        "manifest_sha256": manifest_sha,
        "issued_at_local": now_iso(),
        "issued_at_unix_ns": time.time_ns(),
    }
    receipt_path = directory / "receipt.json"
    write_json(receipt_path, receipt)
    receipt_sha = sha256_file(receipt_path)
    (directory / "receipt.sha256").write_text(
        f"{receipt_sha}  receipt.json\n", encoding="utf-8"
    )
    for path in directory.iterdir():
        if path.is_file():
            path.chmod(0o600)
    return {"manifest_sha256": manifest_sha, "receipt_sha256": receipt_sha}


def _verify_manifest_and_receipt(
    directory: Path, *, expected_schema: str
) -> dict[str, Any]:
    manifest_path = directory / "manifest.json"
    manifest_sha = sha256_file(manifest_path)
    if _receipt_sha(directory / "manifest.sha256", "manifest.json") != manifest_sha:
        raise RuntimeError(f"manifest receipt drift: {directory}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != expected_schema:
        raise RuntimeError(f"manifest schema drift: {directory}")
    for row in manifest["files"]:
        path = directory / row["path"]
        if (
            not path.is_file()
            or path.stat().st_size != row["size_bytes"]
            or sha256_file(path) != row["sha256"]
        ):
            raise RuntimeError(f"sealed file drift: {directory}:{row['path']}")
    receipt_path = directory / "receipt.json"
    receipt_sha = sha256_file(receipt_path)
    if _receipt_sha(directory / "receipt.sha256", "receipt.json") != receipt_sha:
        raise RuntimeError(f"receipt drift: {directory}")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("manifest_sha256") != manifest_sha:
        raise RuntimeError(f"receipt does not bind manifest: {directory}")
    return {
        **manifest,
        "manifest_sha256": manifest_sha,
        "receipt_sha256": receipt_sha,
    }


def validate_relation(path: Path, expected_ids: set[str]) -> list[dict[str, str]]:
    rows = read_csv(path, RELATION_FIELDS)
    ids = [row["relation_audit_id"] for row in rows]
    if len(ids) != len(set(ids)) or set(ids) != expected_ids:
        raise RuntimeError(f"relation IDs incomplete, extra, or duplicated: {path}")
    reference_values = {"valid", "invalid", "unresolved"}
    group_values = {"unique", "non_unique", "unresolved"}
    relation_values = {"equivalent", "factual_conflict", "other_incorrect", "unresolved"}
    conflict_values = {
        "not_applicable",
        "version_or_time",
        "numeric",
        "negation_or_direction",
        "applicability_or_condition",
        "unresolved",
    }
    reviewer_ids = set()
    for row in rows:
        audit_id = row["relation_audit_id"]
        if row["target_reference_status"] not in reference_values:
            raise RuntimeError(f"invalid target_reference_status: {audit_id}")
        if row["target_group_status"] not in group_values:
            raise RuntimeError(f"invalid target_group_status: {audit_id}")
        if row["target_relation"] not in relation_values or row["conflict_type"] not in conflict_values:
            raise RuntimeError(f"invalid relation/conflict enum: {audit_id}")
        if row["target_reference_status"] != "valid" or row["target_group_status"] != "unique":
            if row["target_relation"] != "unresolved" or row["conflict_type"] != "unresolved":
                raise RuntimeError(f"invalid reference/group must stop downstream labeling: {audit_id}")
        elif row["target_relation"] == "factual_conflict":
            if row["conflict_type"] not in {
                "version_or_time",
                "numeric",
                "negation_or_direction",
                "applicability_or_condition",
            }:
                raise RuntimeError(f"factual conflict requires one frozen conflict type: {audit_id}")
        elif row["target_relation"] in {"equivalent", "other_incorrect"}:
            if row["conflict_type"] != "not_applicable":
                raise RuntimeError(f"non-conflict requires not_applicable: {audit_id}")
        elif row["conflict_type"] != "unresolved":
            raise RuntimeError(f"unresolved relation requires unresolved conflict type: {audit_id}")
        if not row["evidence_locator"].strip() or not row["rationale"].strip():
            raise RuntimeError(f"relation evidence/rationale missing: {audit_id}")
        if row["confidence"] not in {"high", "medium", "low"}:
            raise RuntimeError(f"invalid relation confidence: {audit_id}")
        if row["uncertain"] not in {"yes", "no"}:
            raise RuntimeError(f"invalid relation uncertainty: {audit_id}")
        if row["adjudication_status"] != "single":
            raise RuntimeError(f"initial relation adjudication_status must be single: {audit_id}")
        if not row["reviewer_id"].strip():
            raise RuntimeError(f"relation reviewer_id missing: {audit_id}")
        reviewer_ids.add(row["reviewer_id"].strip())
    if len(reviewer_ids) != 1:
        raise RuntimeError(f"one consistent relation reviewer identity required: {path}")
    return rows


def validate_similarity(path: Path, expected_ids: set[str]) -> list[dict[str, str]]:
    rows = read_csv(path, SIMILARITY_FIELDS)
    ids = [row["similarity_audit_id"] for row in rows]
    if len(ids) != len(set(ids)) or set(ids) != expected_ids:
        raise RuntimeError(f"similarity IDs incomplete, extra, or duplicated: {path}")
    for row in rows:
        audit_id = row["similarity_audit_id"]
        if row["human_similarity_ordinal"] not in {"1", "2", "3", "4", "5"}:
            raise RuntimeError(f"invalid similarity score: {audit_id}")
        if row["confidence"] not in {"high", "medium", "low"}:
            raise RuntimeError(f"invalid similarity confidence: {audit_id}")
        if row["uncertain"] not in {"yes", "no"}:
            raise RuntimeError(f"invalid similarity uncertainty: {audit_id}")
        if row["uncertain"] == "yes" and not row["note"].strip():
            raise RuntimeError(f"similarity uncertainty requires note: {audit_id}")
    return rows


def collect_validated_submissions(root: Path) -> dict[str, Any]:
    lock = verify_lock(root)
    relation_expected = {
        row["relation_audit_id"]
        for row in read_csv(
            root / "human_relation/annotator_a/submission_template.csv", RELATION_FIELDS
        )
    }
    similarity_expected = {
        row["similarity_audit_id"]
        for row in read_csv(
            root / "human_similarity/annotator_a/submission_template.csv", SIMILARITY_FIELDS
        )
    }
    relation_a = validate_relation(submission_paths(root)["relation_a"], relation_expected)
    relation_b = validate_relation(submission_paths(root)["relation_b"], relation_expected)
    similarity_a = validate_similarity(submission_paths(root)["similarity_a"], similarity_expected)
    similarity_b = validate_similarity(submission_paths(root)["similarity_b"], similarity_expected)
    if relation_a[0]["reviewer_id"] == relation_b[0]["reviewer_id"]:
        raise RuntimeError("relation A/B must use different real reviewer identities")
    relation_disagreements = []
    relation_b_by_id = {row["relation_audit_id"]: row for row in relation_b}
    compare_fields = (
        "target_reference_status",
        "target_group_status",
        "target_relation",
        "conflict_type",
    )
    for row in relation_a:
        other = relation_b_by_id[row["relation_audit_id"]]
        if any(row[field] != other[field] for field in compare_fields) or "yes" in {
            row["uncertain"],
            other["uncertain"],
        }:
            relation_disagreements.append(row["relation_audit_id"])
    similarity_b_by_id = {row["similarity_audit_id"]: row for row in similarity_b}
    mandatory_similarity = []
    all_nonexact_similarity = []
    for row in similarity_a:
        other = similarity_b_by_id[row["similarity_audit_id"]]
        delta = abs(int(row["human_similarity_ordinal"]) - int(other["human_similarity_ordinal"]))
        if delta:
            all_nonexact_similarity.append(row["similarity_audit_id"])
        if delta >= 2 or "yes" in {row["uncertain"], other["uncertain"]}:
            mandatory_similarity.append(row["similarity_audit_id"])
    review: dict[str, Any] = {
        "status": "VALIDATED_LOCKED_SUBMISSIONS_AWAITING_ADJUDICATION",
        "submission_lock_sha256": lock["submission_lock_sha256"],
        "relation_rows_each": len(relation_a),
        "similarity_rows_each": len(similarity_a),
        "relation_adjudication_ids": sorted(relation_disagreements),
        "similarity_mandatory_adjudication_ids": sorted(mandatory_similarity),
        "similarity_adjudication_ids_for_unique_final_score": sorted(all_nonexact_similarity),
    }
    return {
        "lock": lock,
        "relation_a": relation_a,
        "relation_b": relation_b,
        "similarity_a": similarity_a,
        "similarity_b": similarity_b,
        "review": review,
    }


def validate_locked_submissions(root: Path) -> dict[str, Any]:
    bundle = collect_validated_submissions(root)
    review = bundle["review"]
    output = root / "human_review/facilitator/pre_adjudication_review.json"
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if canonical_json(existing) != canonical_json(review):
            raise RuntimeError("refusing to overwrite drifted pre-adjudication review")
    else:
        write_json(output, review)
    return review


def implementation_code_snapshot(repo_root: Path) -> dict[str, Any]:
    paths = [
        Path(__file__).resolve(),
        repo_root
        / "src/linkrag_eval/robust_fusion/similarity_support_finalization.py",
        repo_root / "src/linkrag_eval/robust_fusion/similarity_dev_calibration.py",
        repo_root / "src/linkrag_eval/robust_fusion/similarity_support_supplement.py",
        repo_root / "scripts/run_robust_fusion_similarity_support_supplement.py",
        repo_root / "tests/unit/test_robust_fusion_similarity_support_human_review.py",
    ]
    return {
        "python": platform.python_version(),
        "files": [
            {
                "path": path.relative_to(repo_root).as_posix(),
                "sha256": sha256_file(path),
            }
            for path in paths
        ],
    }


def _post_lock_bound_inputs(root: Path, v1_root: Path) -> dict[str, str]:
    paths = {
        "supplement_preregistration_protocol": root / "preregistration/protocol.json",
        "supplement_preregistration_lock": root / "preregistration/lock.json",
        "supplement_data_manifest": root / "data/manifest.json",
        "supplement_automatic_manifest": root / "automatic/manifest.json",
        "supplement_relation_registry": root / "human_relation/facilitator/registry.jsonl",
        "supplement_similarity_registry": root / "human_similarity/facilitator/registry.jsonl",
        "submission_lock": root / "human_review/facilitator/submission_lock.json",
        "pre_adjudication_review": root
        / "human_review/facilitator/pre_adjudication_review.json",
        "v1_candidate_similarity": v1_root / "candidate_similarity.jsonl",
        "v1_submission_lock": v1_root / "human_audit/facilitator/submission_lock.json",
        "v1_submission_a": v1_root / "human_audit/annotator_a/submission.csv",
        "v1_submission_b": v1_root / "human_audit/annotator_b/submission.csv",
        "v1_final_manifest": v1_root
        / "human_audit/facilitator/adjudication_v1/final_manifest.json",
        "v1_final_scores": v1_root
        / "human_audit/facilitator/adjudication_v1/final_scores.jsonl",
    }
    return {name: sha256_file(path) for name, path in paths.items()}


def require_bound_input_hashes(
    expected: dict[str, str], current: dict[str, str]
) -> None:
    if expected != current:
        changed = sorted(
            name
            for name in set(expected) | set(current)
            if expected.get(name) != current.get(name)
        )
        raise RuntimeError(f"post-lock finalizer bound input drift: {changed}")


def seal_zero_finalizer_implementation(
    root: Path, v1_root: Path, repo_root: Path
) -> dict[str, Any]:
    output_dir = root / POST_LOCK_IMPLEMENTATION_DIR
    if output_dir.exists():
        raise RuntimeError(f"refusing to overwrite post-lock implementation seal: {output_dir}")
    if (root / FINALIZATION_DIR).exists():
        raise RuntimeError("cannot seal implementation after finalization output exists")
    preregistration = verify_preregistration(root, repo_root)
    verify_materialized(root, preregistration)
    verify_v1_read_only(v1_root)
    lock = verify_lock(root)
    pre_review_path = root / "human_review/facilitator/pre_adjudication_review.json"
    pre_review = json.loads(pre_review_path.read_text(encoding="utf-8"))
    if pre_review.get("submission_lock_sha256") != lock["submission_lock_sha256"]:
        raise RuntimeError("pre-adjudication review does not bind current submission lock")
    output_dir.mkdir(parents=True, mode=0o700)
    spec = {
        "schema_version": "robust-fusion-similarity-support-post-lock-finalizer-spec-v1",
        "status": "SEALED_POST_LOCK_BEFORE_REAL_FINALIZER_EXECUTION",
        "nature": (
            "missing executor for the already-frozen protocol; not a protocol, estimand, "
            "threshold, denominator, model, or evidence-definition change"
        ),
        "input_state": {
            "submission_lock_sha256": lock["submission_lock_sha256"],
            "pre_adjudication_review_sha256": sha256_file(pre_review_path),
            "relation_adjudication_count": len(pre_review["relation_adjudication_ids"]),
            "similarity_mandatory_adjudication_count": len(
                pre_review["similarity_mandatory_adjudication_ids"]
            ),
            "similarity_unique_score_adjudication_count": len(
                pre_review["similarity_adjudication_ids_for_unique_final_score"]
            ),
        },
        "zero_adjudication_rule": {
            "relation_truth": "use only the A/B exact common value for the four frozen fields",
            "similarity_score": "use only the A/B exact common ordinal",
            "fail_closed_on": [
                "any relation disagreement",
                "any similarity disagreement",
                "any uncertain=yes",
                "submission lock or package-manifest drift",
                "pre-adjudication review drift",
                "expected ID or row-count drift",
                "non-empty adjudication set",
            ],
            "automatic_adjudication_allowed": False,
        },
        "frozen_scientific_invariants": {
            "v1_disposition": "PERMANENT_FORMAL_INCONCLUSIVE_READ_ONLY",
            "supplement_family_count": 72,
            "combined_denominator_each_relation": 100,
            "missing_or_invalid": "miss_in_fixed_denominator",
            "encoders_unchanged": True,
            "estimand": "S_qg(c)=max_h_in_A_qg cosine(z(c),z(h))",
            "ddof": 1,
            "common_support": "intersection_of_relation_specific_observed_min_max_ranges",
            "minimum_coverage_each_relation": 0.60,
            "human_validity_thresholds": "unchanged_v1_six_thresholds",
            "unique_stop_rule_unchanged": True,
        },
        "construction_role_boundary": (
            "the preregistered role may identify a fixed denominator slot only; it is never "
            "relation truth. automatic/construction_role_preview.json is not parsed or used "
            "to decide truth, validity, PASS, or the numeric freeze"
        ),
        "bound_input_hashes": _post_lock_bound_inputs(root, v1_root),
        "forbidden_execution": [
            "Blind read",
            "readiness",
            "Gate A",
            "Gate B",
            "Reranker effect",
            "D1-D3",
            "A0",
            "M1",
        ],
        "sealed_at_local": now_iso(),
        "sealed_at_unix_ns": time.time_ns(),
    }
    code = implementation_code_snapshot(repo_root)
    write_json(output_dir / "implementation_spec.json", spec)
    write_json(output_dir / "code_snapshot.json", code)
    hashes = _write_manifest_and_receipt(
        output_dir,
        schema_version="robust-fusion-similarity-support-post-lock-implementation-v1",
        status=spec["status"],
        names=["implementation_spec.json", "code_snapshot.json"],
        receipt_type="post_lock_pre_execution_implementation_receipt",
        extra={
            "submission_lock_sha256": lock["submission_lock_sha256"],
            "pre_adjudication_review_sha256": sha256_file(pre_review_path),
            "real_finalizer_executed": False,
            "gate_a_executed": False,
            "gate_b_executed": False,
        },
    )
    return {"status": spec["status"], **hashes}


def verify_zero_finalizer_implementation(
    root: Path, v1_root: Path, repo_root: Path
) -> dict[str, Any]:
    output_dir = root / POST_LOCK_IMPLEMENTATION_DIR
    seal = _verify_manifest_and_receipt(
        output_dir,
        expected_schema="robust-fusion-similarity-support-post-lock-implementation-v1",
    )
    spec = json.loads((output_dir / "implementation_spec.json").read_text(encoding="utf-8"))
    code = json.loads((output_dir / "code_snapshot.json").read_text(encoding="utf-8"))
    if code != implementation_code_snapshot(repo_root):
        raise RuntimeError("post-lock finalizer code snapshot drift")
    current_inputs = _post_lock_bound_inputs(root, v1_root)
    require_bound_input_hashes(spec.get("bound_input_hashes", {}), current_inputs)
    if spec.get("status") != "SEALED_POST_LOCK_BEFORE_REAL_FINALIZER_EXECUTION":
        raise RuntimeError("post-lock finalizer spec status drift")
    return {**seal, "spec": spec, "code_snapshot": code}


def _load_automatic_scores(root: Path) -> tuple[list[dict[str, Any]], str]:
    automatic = root / "automatic"
    manifest_path = automatic / "manifest.json"
    manifest_sha = sha256_file(manifest_path)
    if _receipt_sha(automatic / "manifest.sha256", "manifest.json") != manifest_sha:
        raise RuntimeError("automatic manifest receipt drift")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for row in manifest["files"]:
        path = automatic / row["path"]
        if (
            not path.is_file()
            or path.stat().st_size != row["size_bytes"]
            or sha256_file(path) != row["sha256"]
        ):
            raise RuntimeError(f"automatic file drift: {row['path']}")
    rows = read_jsonl(automatic / "candidate_similarity.jsonl")
    if len(rows) != EXPECTED_RELATION_ROWS or len(
        {row["candidate_id"] for row in rows}
    ) != EXPECTED_RELATION_ROWS:
        raise RuntimeError("automatic candidate score ID/row-count drift")
    return rows, manifest_sha


def _read_untyped_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _load_v1_human_and_scores(v1_root: Path) -> dict[str, Any]:
    verify_v1_read_only(v1_root)
    lock_path = v1_root / "human_audit/facilitator/submission_lock.json"
    lock_sha = sha256_file(lock_path)
    if _receipt_sha(lock_path.with_suffix(".sha256"), "submission_lock.json") != lock_sha:
        raise RuntimeError("v1 human submission lock receipt drift")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("content_read_before_lock") is not False:
        raise RuntimeError("v1 human submissions were not locked before comparison")
    submissions = {}
    for record in lock["submissions"]:
        role = record["role"].lower()
        submission_path = v1_root / f"human_audit/annotator_{role}/submission.csv"
        package_manifest = submission_path.parent / "package_manifest.json"
        if (
            submission_path.stat().st_size != record["bytes"]
            or sha256_file(submission_path) != record["sha256"]
            or sha256_file(package_manifest) != record["package_manifest_sha256"]
        ):
            raise RuntimeError(f"v1 locked submission/package drift: {role}")
        expected = {
            row["audit_id"]
            for row in _read_untyped_csv(submission_path.parent / "pairs.csv")
        }
        rows = validate_v1_similarity_submission(submission_path, expected)
        submissions[role] = {row["audit_id"]: row for row in rows}
    if set(submissions) != {"a", "b"} or set(submissions["a"]) != set(
        submissions["b"]
    ):
        raise RuntimeError("v1 human A/B identity or ID-set drift")

    final_dir = v1_root / "human_audit/facilitator/adjudication_v1"
    final_manifest_path = final_dir / "final_manifest.json"
    final_manifest_sha = sha256_file(final_manifest_path)
    if _receipt_sha(final_dir / "final_manifest.sha256", "final_manifest.json") != final_manifest_sha:
        raise RuntimeError("v1 final manifest receipt drift")
    final_manifest = json.loads(final_manifest_path.read_text(encoding="utf-8"))
    for row in final_manifest["files"]:
        path = final_dir / row["path"]
        if (
            path.stat().st_size != row["size_bytes"]
            or sha256_file(path) != row["sha256"]
        ):
            raise RuntimeError(f"v1 final file drift: {row['path']}")
    final_rows = read_jsonl(final_dir / "final_scores.jsonl")
    if len(final_rows) != 24 or len({row["audit_id"] for row in final_rows}) != 24:
        raise RuntimeError("v1 final human score ID/row-count drift")
    candidates = [
        row
        for row in read_jsonl(v1_root / "candidate_similarity.jsonl")
        if row["target_relation"] in {"equivalent", "factual_conflict"}
    ]
    if len(candidates) != 56:
        raise RuntimeError("v1 eligible candidate count drift")
    return {
        "submission_lock_sha256": lock_sha,
        "submission_a": submissions["a"],
        "submission_b": submissions["b"],
        "final_rows": final_rows,
        "candidate_rows": candidates,
        "final_manifest_sha256": final_manifest_sha,
    }


def _v1_relation_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "relation_audit_id": None,
            "query_family_id": row["query_uid"],
            "candidate_id": row["candidate_chunk_id"],
            "preregistered_denominator_slot": row["target_relation"],
            "final_relation_truth": {
                "target_reference_status": "valid",
                "target_group_status": "unique",
                "target_relation": row["target_relation"],
                "conflict_type": row["conflict_type"],
            },
            "main_similarity": float(row["main_similarity"]),
            "final_truth_source": "v1_read_only_final_relation",
        }
        for row in rows
    ]


def _normalized_v1_human_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "similarity_audit_id": row["audit_id"],
            "candidate_id": row["candidate_chunk_id"],
            "main_similarity": float(row["main_similarity"]),
            "audit_similarity": float(row["audit_similarity"]),
            "length_stratum": row["length_stratum"],
            "final_human_similarity_ordinal": int(
                row["final_human_similarity_ordinal"]
            ),
            "final_score_source": row["final_score_source"],
        }
        for row in rows
    ]


def finalize_zero_adjudication(
    root: Path, v1_root: Path, repo_root: Path
) -> dict[str, Any]:
    output_dir = root / FINALIZATION_DIR
    if output_dir.exists():
        raise RuntimeError(f"refusing to overwrite finalization: {output_dir}")
    implementation = verify_zero_finalizer_implementation(root, v1_root, repo_root)
    preregistration = verify_preregistration(root, repo_root)
    families = verify_materialized(root, preregistration)
    if len(families) != 72:
        raise RuntimeError("supplement family count drift")
    bundle = collect_validated_submissions(root)
    pre_review_path = root / "human_review/facilitator/pre_adjudication_review.json"
    stored_review = json.loads(pre_review_path.read_text(encoding="utf-8"))
    if canonical_json(stored_review) != canonical_json(bundle["review"]):
        raise RuntimeError("pre-adjudication review content/recomputation drift")
    expected_pre_review_sha = implementation["spec"]["input_state"][
        "pre_adjudication_review_sha256"
    ]
    if sha256_file(pre_review_path) != expected_pre_review_sha:
        raise RuntimeError("pre-adjudication review hash drift")
    require_zero_adjudication(
        stored_review,
        bundle["relation_a"],
        bundle["relation_b"],
        bundle["similarity_a"],
        bundle["similarity_b"],
        expected_relation_rows=EXPECTED_RELATION_ROWS,
        expected_similarity_rows=EXPECTED_SIMILARITY_ROWS,
    )

    automatic_rows, automatic_manifest_sha = _load_automatic_scores(root)
    scores_by_candidate = {row["candidate_id"]: row for row in automatic_rows}
    relation_registry = read_jsonl(root / "human_relation/facilitator/registry.jsonl")
    similarity_registry = read_jsonl(root / "human_similarity/facilitator/registry.jsonl")
    if len(relation_registry) != EXPECTED_RELATION_ROWS or len(
        {row["relation_audit_id"] for row in relation_registry}
    ) != EXPECTED_RELATION_ROWS:
        raise RuntimeError("relation facilitator registry ID/row-count drift")
    if len(similarity_registry) != EXPECTED_SIMILARITY_ROWS or len(
        {row["similarity_audit_id"] for row in similarity_registry}
    ) != EXPECTED_SIMILARITY_ROWS:
        raise RuntimeError("similarity facilitator registry ID/row-count drift")
    submission_hashes = {
        name: record["sha256"] for name, record in bundle["lock"]["submissions"].items()
    }
    final_relation = build_final_relation_records(
        relation_registry,
        bundle["relation_a"],
        bundle["relation_b"],
        scores_by_candidate,
        submission_hashes=submission_hashes,
    )
    final_similarity = build_final_similarity_records(
        similarity_registry,
        bundle["similarity_a"],
        bundle["similarity_b"],
        scores_by_candidate,
        submission_hashes=submission_hashes,
    )

    v1 = _load_v1_human_and_scores(v1_root)
    v1_relation = _v1_relation_records(v1["candidate_rows"])
    combined_relation = [*v1_relation, *final_relation]
    support = {
        "v1": support_summary(v1_relation, denominator_each_relation=28),
        "supplement_only": support_summary(
            final_relation, denominator_each_relation=72
        ),
        "combined": support_summary(
            combined_relation, denominator_each_relation=100
        ),
    }
    if support["v1"]["hit_count_by_relation"] != {
        "equivalent": 5,
        "factual_conflict": 16,
    }:
        raise RuntimeError("v1 permanent common-support counts drift")

    supplement_numeric = numeric_summary(final_relation)
    combined_numeric = numeric_summary(combined_relation)
    supplement_a = {
        row["similarity_audit_id"]: row for row in bundle["similarity_a"]
    }
    supplement_b = {
        row["similarity_audit_id"]: row for row in bundle["similarity_b"]
    }
    v1_human = _normalized_v1_human_rows(v1["final_rows"])
    if set(v1["submission_a"]) & set(supplement_a):
        raise RuntimeError("v1/supplement human audit ID overlap")
    combined_a = {**v1["submission_a"], **supplement_a}
    combined_b = {**v1["submission_b"], **supplement_b}
    human_validity = {
        "supplement_only": human_validity_summary(
            final_similarity,
            supplement_a,
            supplement_b,
            high_min_inclusive=supplement_numeric["bands"]["high_min_inclusive"],
            scope="supplement_only_frozen_48_pair_audit_frame",
        ),
        "combined": human_validity_summary(
            [*v1_human, *final_similarity],
            combined_a,
            combined_b,
            high_min_inclusive=combined_numeric["bands"]["high_min_inclusive"],
            scope="v1_plus_supplement_frozen_72_pair_audit_frame",
        ),
    }
    decision = terminal_decision(
        combined_support_pass=support["combined"]["automatic_coverage_pass"],
        supplement_human_decision=human_validity["supplement_only"][
            "human_measurement_decision"
        ],
        combined_human_decision=human_validity["combined"][
            "human_measurement_decision"
        ],
    )
    passed = decision == "PASS"
    status = (
        "FORMAL_NUMERIC_FREEZE_COMPLETE_AWAITING_READINESS"
        if passed
        else f"P2_TERMINAL_{decision}_GATE_A_UNAUTHORIZED"
    )
    final_decision = {
        "status": status,
        "formal_combined_decision": decision,
        "required_components": {
            "combined_common_support": (
                "PASS" if support["combined"]["automatic_coverage_pass"] else "FAIL"
            ),
            "supplement_only_human_validity": human_validity["supplement_only"][
                "human_measurement_decision"
            ],
            "combined_human_validity": human_validity["combined"][
                "human_measurement_decision"
            ],
        },
        "formal_numeric_freeze_complete": passed,
        "p2_01_complete": passed,
        "p2_04_complete": passed,
        "additional_p2_supplement_allowed": False,
        "readiness_executed": False,
        "gate_a_authorized": False,
        "gate_a_executed": False,
        "gate_b_executed": False,
        "v1_permanent_decision": "INCONCLUSIVE",
        "construction_role_used_as_truth": False,
        "implementation_nature": (
            "post-lock missing executor for frozen protocol; no scientific definition changed"
        ),
    }

    output_dir.mkdir(parents=True, mode=0o700)
    _write_jsonl(output_dir / "final_relation_records.jsonl", final_relation)
    _write_jsonl(output_dir / "final_similarity_records.jsonl", final_similarity)
    write_json(output_dir / "human_validity.json", human_validity)
    write_json(output_dir / "common_support.json", support)
    write_json(output_dir / "final_decision.json", final_decision)
    write_json(
        output_dir / "status.json",
        {
            "status": status,
            "formal_numeric_freeze_complete": passed,
            "p2_01_complete": passed,
            "p2_04_complete": passed,
            "gate_a_authorized": False,
            "gate_a_executed": False,
            "gate_b_executed": False,
        },
    )
    names = [
        "final_relation_records.jsonl",
        "final_similarity_records.jsonl",
        "human_validity.json",
        "common_support.json",
        "final_decision.json",
        "status.json",
    ]
    if passed:
        formal_numeric = {
            "status": "FORMALLY_FROZEN_ON_COMBINED_PASS",
            **combined_numeric,
            "common_support": support["combined"],
            "source_population": "v1_read_only_plus_all_72_preregistered_supplement_families",
            "missing_as_miss": True,
            "construction_role_used_as_truth": False,
        }
        write_json(output_dir / "formal_numeric_freeze.json", formal_numeric)
        names.append("formal_numeric_freeze.json")
    hashes = _write_manifest_and_receipt(
        output_dir,
        schema_version="robust-fusion-similarity-support-finalization-v1",
        status=status,
        names=names,
        receipt_type="single_real_zero_adjudication_finalization_receipt",
        extra={
            "submission_lock_sha256": bundle["lock"]["submission_lock_sha256"],
            "pre_adjudication_review_sha256": sha256_file(pre_review_path),
            "post_lock_implementation_manifest_sha256": implementation[
                "manifest_sha256"
            ],
            "automatic_manifest_sha256": automatic_manifest_sha,
            "v1_final_manifest_sha256": v1["final_manifest_sha256"],
            "formal_combined_decision": decision,
            "readiness_executed": False,
            "gate_a_executed": False,
            "gate_b_executed": False,
        },
    )
    return {
        **final_decision,
        **hashes,
        "support": support,
        "human_validity": human_validity,
        "formal_numeric": combined_numeric if passed else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command",
        choices=(
            "lock-submissions",
            "validate",
            "seal-zero-finalizer-implementation",
            "finalize-zero-adjudication",
        ),
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--v1-root", type=Path, default=DEFAULT_V1_ROOT)
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    root = resolve_in_repo(repo_root, args.root)
    v1_root = resolve_in_repo(repo_root, args.v1_root)
    result = {
        "lock-submissions": lambda: lock_submissions(root),
        "validate": lambda: validate_locked_submissions(root),
        "seal-zero-finalizer-implementation": lambda: seal_zero_finalizer_implementation(
            root, v1_root, repo_root
        ),
        "finalize-zero-adjudication": lambda: finalize_zero_adjudication(
            root, v1_root, repo_root
        ),
    }[args.command]()
    print(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
