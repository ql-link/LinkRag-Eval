#!/usr/bin/env python3
"""Seal, validate, adjudicate, and finalize locked R2 human submissions."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.r2_human_review import (
    EXECUTOR_ID,
    RELATION_FIELDS,
    SIMILARITY_FIELDS,
    build_zero_adjudication_rows,
    compare_submissions,
    final_measurement_summary,
    parse_csv_bytes,
    validate_registry,
    validate_relation_rows,
    validate_similarity_rows,
)
from linkrag_eval.robust_fusion.similarity_dev_calibration import (
    canonical_json,
    sha256_file,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_measurement_v1/"
    "robust-fusion-r2-measurement-v1-20260829"
)
SOURCE_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_authorship_v7_codex/"
    "robust-fusion-r2-source-authorship-v7-codex-20260829/data_lock"
)
PREPARATION_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_human_review_preparation_v1/"
    "robust-fusion-r2-human-review-preparation-v1-20260829"
)
SPEC = REPO_ROOT / "docs/plans/robust-fusion-r2-human-review-finalization-v1.md"
CODE_FILES = (
    "src/linkrag_eval/robust_fusion/r2_human_review.py",
    "scripts/review_robust_fusion_r2_human.py",
    "tests/unit/test_robust_fusion_r2_human_review.py",
)
LOCK_DIR = RUN_ROOT / "human_review/submission_lock_v1"
PRE_REVIEW_DIR = RUN_ROOT / "human_review/pre_adjudication_review_v1"
ADJUDICATION_DIR = RUN_ROOT / "human_review/adjudication_v1"
FINALIZATION_DIR = RUN_ROOT / "human_review/finalization_v1"
PACKAGE_KEYS = (
    ("relation", "annotator_a"),
    ("relation", "annotator_b"),
    ("similarity", "annotator_a"),
    ("similarity", "annotator_b"),
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_bytes_exclusive(path: Path, value: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)


def _write_json_exclusive(path: Path, value: MappingLike) -> None:
    _write_bytes_exclusive(path, (canonical_json(value) + "\n").encode("utf-8"))


MappingLike = dict[str, Any]


def _entry(path: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(REPO_ROOT).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _verify_submission_lock() -> dict[str, Any]:
    lock_path = LOCK_DIR / "lock.json"
    receipt = _read_json(LOCK_DIR / "receipt.json")
    if receipt.get("lock_sha256") != sha256_file(lock_path):
        raise RuntimeError("submission lock receipt drift")
    lock = _read_json(lock_path)
    if lock.get("status") != "R2_FOUR_SUBMISSIONS_LOCKED_BEFORE_CONTENT_PARSE":
        raise RuntimeError("submission lock status drift")
    if lock.get("answers_parsed_before_lock") is not False:
        raise RuntimeError("submission lock lacks pre-parse assertion")
    expected_paths = {
        (task, reviewer): RUN_ROOT / "human_packages" / task / reviewer / "submission.csv"
        for task, reviewer in PACKAGE_KEYS
    }
    seen = set()
    for record in lock["submissions"]:
        key = (str(record["task"]), str(record["annotator"]))
        if key not in expected_paths or key in seen:
            raise RuntimeError("submission lock identity drift")
        seen.add(key)
        path = REPO_ROOT / str(record["submission_path"])
        if path != expected_paths[key]:
            raise RuntimeError("submission lock path drift")
        if path.stat().st_size != record["submission_size_bytes"]:
            raise RuntimeError("locked submission size drift")
        if sha256_file(path) != record["submission_sha256"]:
            raise RuntimeError("locked submission content drift")
        manifest = path.parent / "package_manifest.json"
        if sha256_file(manifest) != record["package_manifest_sha256"]:
            raise RuntimeError("locked package manifest drift")
    if seen != set(PACKAGE_KEYS):
        raise RuntimeError("submission lock denominator drift")
    return {**lock, "lock_sha256": sha256_file(lock_path)}


def _verify_package(task: str, annotator: str) -> dict[str, Any]:
    root = RUN_ROOT / "human_packages" / task / annotator
    manifest = _read_json(root / "package_manifest.json")
    reviewer = "A" if annotator == "annotator_a" else "B"
    if (
        manifest.get("reviewer") != reviewer
        or manifest.get("task") != task
        or manifest.get("rows") != 256
        or manifest.get("contains_answer_key") is not False
        or manifest.get("contains_model_scores") is not False
        or manifest.get("contains_generator_or_construction_role") is not False
    ):
        raise RuntimeError(f"blind package identity/safety drift: {task}/{annotator}")
    expected_names = {"README.txt", "pairs.csv", "submission_template.csv"}
    if {str(row["name"]) for row in manifest["files"]} != expected_names:
        raise RuntimeError(f"blind package file set drift: {task}/{annotator}")
    for row in manifest["files"]:
        path = root / str(row["name"])
        if sha256_file(path) != row["sha256"]:
            raise RuntimeError(f"blind package file drift: {task}/{annotator}/{path.name}")
    return manifest


def seal() -> dict[str, Any]:
    if PREPARATION_ROOT.exists():
        raise RuntimeError("R2 human-review preparation exists; replay refused")
    if PRE_REVIEW_DIR.exists() or ADJUDICATION_DIR.exists() or FINALIZATION_DIR.exists():
        raise RuntimeError("retrospective R2 human-review seal refused")
    lock = _verify_submission_lock()
    package_manifests = []
    for task, annotator in PACKAGE_KEYS:
        _verify_package(task, annotator)
        package_manifests.append(
            _entry(RUN_ROOT / "human_packages" / task / annotator / "package_manifest.json")
        )
    bound = [
        _entry(RUN_ROOT / "preregistration/manifest.json"),
        _entry(RUN_ROOT / "preregistration/lock.json"),
        _entry(SOURCE_ROOT / "manifest.json"),
        _entry(SOURCE_ROOT / "lock.json"),
        _entry(SOURCE_ROOT / "families.jsonl"),
        _entry(RUN_ROOT / "automatic/manifest.json"),
        _entry(RUN_ROOT / "automatic/candidate_similarity.jsonl"),
        _entry(RUN_ROOT / "human_packages/facilitator/blind_registry_not_truth.jsonl"),
        _entry(LOCK_DIR / "lock.json"),
        _entry(LOCK_DIR / "receipt.json"),
        *package_manifests,
    ]
    PREPARATION_ROOT.mkdir(parents=True, mode=0o700)
    snapshot = PREPARATION_ROOT / "code_snapshot"
    snapshot.mkdir(mode=0o700)
    snapshot_paths = (str(SPEC.relative_to(REPO_ROOT)), *CODE_FILES)
    for relative in snapshot_paths:
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative, target)
    manifest = {
        "status": "R2_HUMAN_REVIEW_EXECUTOR_SEALED_POST_SUBMISSION_LOCK_BEFORE_PARSE",
        "executor_id": EXECUTOR_ID,
        "sealed_at_unix_ns": time.time_ns(),
        "scientific_protocol_changed": False,
        "submission_lock_sha256": lock["lock_sha256"],
        "bound_inputs": bound,
        "snapshot_files": [_entry(snapshot / relative) for relative in snapshot_paths],
        "forbidden": ["Blind", "readiness", "Gate A/B", "Reranker", "D1-D3", "A0", "M1"],
    }
    _write_json_exclusive(PREPARATION_ROOT / "manifest.json", manifest)
    receipt = {
        "status": "LOCKED_BEFORE_SUBMISSION_PARSE",
        "executor_id": EXECUTOR_ID,
        "manifest_sha256": sha256_file(PREPARATION_ROOT / "manifest.json"),
        "submission_answers_parsed_by_seal": False,
    }
    _write_json_exclusive(PREPARATION_ROOT / "receipt.json", receipt)
    return {**receipt, "receipt_sha256": sha256_file(PREPARATION_ROOT / "receipt.json")}


def _verify_preparation() -> dict[str, Any]:
    receipt = _read_json(PREPARATION_ROOT / "receipt.json")
    manifest_path = PREPARATION_ROOT / "manifest.json"
    if receipt.get("manifest_sha256") != sha256_file(manifest_path):
        raise RuntimeError("R2 human-review preparation manifest drift")
    manifest = _read_json(manifest_path)
    for record in manifest["bound_inputs"]:
        path = REPO_ROOT / str(record["path"])
        if path.stat().st_size != record["size_bytes"] or sha256_file(path) != record["sha256"]:
            raise RuntimeError(f"R2 human-review bound input drift: {record['path']}")
    for record in manifest["snapshot_files"]:
        path = REPO_ROOT / str(record["path"]).removeprefix(
            PREPARATION_ROOT.relative_to(REPO_ROOT).as_posix() + "/code_snapshot/"
        )
        if sha256_file(path) != record["sha256"]:
            raise RuntimeError(f"R2 human-review implementation drift: {path}")
    _verify_submission_lock()
    return {**manifest, "manifest_sha256": sha256_file(manifest_path)}


def _read_pairs(path: Path) -> list[dict[str, str]]:
    return parse_csv_bytes(path.read_bytes(), ("audit_id", "query", "reference", "candidate"))


def _family_strata() -> dict[str, dict[str, Any]]:
    output = {}
    for row in _read_jsonl(SOURCE_ROOT / "families.jsonl"):
        output[str(row["family_id"])] = {
            "dataset_role": str(row["dataset_role"]),
            "length_language": f"{row['length_stratum']}_{row['language']}",
            "conflict_type_design_stratum_not_truth": str(row["conflict_type"]),
            "edit_level": int(row["edit_level"]),
        }
    if len(output) != 128:
        raise RuntimeError("R2 family strata denominator drift")
    return output


def _validated_bundle() -> dict[str, Any]:
    preparation = _verify_preparation()
    registry_rows = _read_jsonl(
        RUN_ROOT / "human_packages/facilitator/blind_registry_not_truth.jsonl"
    )
    registry = validate_registry(registry_rows)
    submissions = {}
    pair_by_package = {}
    for task, annotator in PACKAGE_KEYS:
        reviewer = "A" if annotator == "annotator_a" else "B"
        _verify_package(task, annotator)
        package_root = RUN_ROOT / "human_packages" / task / annotator
        pairs = _read_pairs(package_root / "pairs.csv")
        pair_ids = [row["audit_id"] for row in pairs]
        if len(pair_ids) != 256 or len(set(pair_ids)) != 256:
            raise RuntimeError(f"pairs denominator/ID drift: {task}/{annotator}")
        expected = registry[(reviewer, task)]
        if set(pair_ids) != set(expected):
            raise RuntimeError(f"pairs/registry ID drift: {task}/{annotator}")
        for ordinal, row in enumerate(pairs, 1):
            record = expected[row["audit_id"]]
            if int(record["package_ordinal"]) != ordinal:
                raise RuntimeError(f"package ordinal drift: {task}/{annotator}")
        pair_by_package[(reviewer, task)] = {
            expected[row["audit_id"]]["candidate_id"]: row for row in pairs
        }
        raw = (package_root / "submission.csv").read_bytes()
        parsed = parse_csv_bytes(
            raw, RELATION_FIELDS if task == "relation" else SIMILARITY_FIELDS
        )
        submissions[(reviewer, task)] = (
            validate_relation_rows(parsed, set(expected))
            if task == "relation"
            else validate_similarity_rows(parsed, set(expected))
        )
    for task in ("relation", "similarity"):
        if set(pair_by_package[("A", task)]) != set(pair_by_package[("B", task)]):
            raise RuntimeError(f"A/B package candidate identity drift: {task}")
        for candidate_id in pair_by_package[("A", task)]:
            left = pair_by_package[("A", task)][candidate_id]
            right = pair_by_package[("B", task)][candidate_id]
            if any(left[field] != right[field] for field in ("query", "reference", "candidate")):
                raise RuntimeError(f"A/B package text drift: {task}/{candidate_id}")
    comparison = compare_submissions(
        registry_packages=registry,
        relation_a=submissions[("A", "relation")],
        relation_b=submissions[("B", "relation")],
        similarity_a=submissions[("A", "similarity")],
        similarity_b=submissions[("B", "similarity")],
        family_strata=_family_strata(),
    )
    return {
        "preparation": preparation,
        "registry": registry,
        "pairs": pair_by_package,
        "submissions": submissions,
        "comparison": comparison,
    }


def _manifest_receipt(directory: Path, names: list[str], status: str) -> dict[str, Any]:
    manifest = {
        "status": status,
        "executor_id": EXECUTOR_ID,
        "files": [_entry(directory / name) for name in names],
        "preparation_manifest_sha256": sha256_file(PREPARATION_ROOT / "manifest.json"),
        "submission_lock_sha256": sha256_file(LOCK_DIR / "lock.json"),
    }
    _write_json_exclusive(directory / "manifest.json", manifest)
    receipt = {
        "status": status,
        "manifest_sha256": sha256_file(directory / "manifest.json"),
        "issued_at_unix_ns": time.time_ns(),
    }
    _write_json_exclusive(directory / "receipt.json", receipt)
    return {**receipt, "receipt_sha256": sha256_file(directory / "receipt.json")}


def _write_csv_exclusive(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(0o600)


def _write_adjudication(bundle: dict[str, Any]) -> None:
    comparison = bundle["comparison"]
    ADJUDICATION_DIR.mkdir(parents=True, mode=0o700)
    for task, case_key in (("relation", "relation_cases"), ("similarity", "similarity_cases")):
        cases = comparison[case_key]
        if not cases:
            continue
        root = ADJUDICATION_DIR / task
        root.mkdir(mode=0o700)
        package_rows = []
        template_rows = []
        for ordinal, case in enumerate(cases, 1):
            candidate_id = case["candidate_id"]
            pair = bundle["pairs"][("A", task)][candidate_id]
            adjudication_id = f"R2-ADJ-{task.upper()}-{ordinal:03d}"
            common = {
                "adjudication_id": adjudication_id,
                "query": pair["query"],
                "reference": pair["reference"],
                "candidate": pair["candidate"],
                "reviewer_a_value": canonical_json(
                    case["reviewer_a"] if task == "relation" else {"score": case["score_a"]}
                ),
                "reviewer_b_value": canonical_json(
                    case["reviewer_b"] if task == "relation" else {"score": case["score_b"]}
                ),
                "reviewer_a_uncertain": case["uncertain_a"],
                "reviewer_b_uncertain": case["uncertain_b"],
            }
            package_rows.append(common)
            if task == "relation":
                template_rows.append(
                    {
                        "adjudication_id": adjudication_id,
                        "valid_reference": "",
                        "unique_target_group": "",
                        "target_relation": "",
                        "conflict_type": "",
                        "uncertain": "",
                        "notes": "",
                    }
                )
            else:
                template_rows.append(
                    {
                        "adjudication_id": adjudication_id,
                        "similarity_1_to_7": "",
                        "uncertain": "",
                        "notes": "",
                    }
                )
        package_fields = [
            "adjudication_id",
            "query",
            "reference",
            "candidate",
            "reviewer_a_value",
            "reviewer_b_value",
            "reviewer_a_uncertain",
            "reviewer_b_uncertain",
        ]
        template_fields = (
            ["adjudication_id", *RELATION_FIELDS[1:]]
            if task == "relation"
            else ["adjudication_id", *SIMILARITY_FIELDS[1:]]
        )
        _write_csv_exclusive(root / "cases.csv", package_rows, package_fields)
        _write_csv_exclusive(root / "submission_template.csv", template_rows, template_fields)
        instruction = (
            "真实人类仲裁员只处理本目录。复制 submission_template.csv 为 submission.csv，逐项独立终审；"
            "不得查看 facilitator registry、自动分数、生成来源或 construction role。模型输出不是答案键。"
        )
        _write_bytes_exclusive(root / "README.txt", (instruction + "\n").encode("utf-8"))
        package_manifest = {
            "status": "AWAITING_REAL_HUMAN_ADJUDICATOR",
            "task": task,
            "rows": len(cases),
            "contains_model_scores": False,
            "contains_generator_or_construction_role": False,
            "contains_answer_key": False,
            "files": [_entry(root / name) for name in ("README.txt", "cases.csv", "submission_template.csv")],
        }
        _write_json_exclusive(root / "package_manifest.json", package_manifest)
    names = [
        path.relative_to(ADJUDICATION_DIR).as_posix()
        for path in sorted(ADJUDICATION_DIR.rglob("*"))
        if path.is_file()
    ]
    _manifest_receipt(ADJUDICATION_DIR, names, "AWAITING_REAL_HUMAN_ADJUDICATION")


def validate() -> dict[str, Any]:
    if PRE_REVIEW_DIR.exists() or ADJUDICATION_DIR.exists() or FINALIZATION_DIR.exists():
        raise RuntimeError("R2 human validation output exists; replay refused")
    bundle = _validated_bundle()
    comparison = bundle["comparison"]
    PRE_REVIEW_DIR.mkdir(parents=True, mode=0o700)
    machine = {key: value for key, value in comparison.items() if key != "final_human"}
    _write_json_exclusive(PRE_REVIEW_DIR / "review.json", machine)
    _write_json_exclusive(
        PRE_REVIEW_DIR / "bound_hashes.json",
        {
            "submission_lock_sha256": sha256_file(LOCK_DIR / "lock.json"),
            "preparation_manifest_sha256": sha256_file(PREPARATION_ROOT / "manifest.json"),
            "automatic_manifest_sha256": sha256_file(RUN_ROOT / "automatic/manifest.json"),
            "blind_registry_sha256": sha256_file(
                RUN_ROOT / "human_packages/facilitator/blind_registry_not_truth.jsonl"
            ),
        },
    )
    receipt = _manifest_receipt(
        PRE_REVIEW_DIR,
        ["review.json", "bound_hashes.json"],
        str(comparison["status"]),
    )
    if comparison["status"] == "AWAITING_HUMAN_ADJUDICATION":
        _write_adjudication(bundle)
    return {**machine, **receipt}


def finalize_zero() -> dict[str, Any]:
    if FINALIZATION_DIR.exists():
        raise RuntimeError("R2 finalization output exists; replay refused")
    if ADJUDICATION_DIR.exists():
        raise RuntimeError("zero-adjudication finalizer refuses existing adjudication package")
    bundle = _validated_bundle()
    comparison = bundle["comparison"]
    review_receipt = _read_json(PRE_REVIEW_DIR / "receipt.json")
    if review_receipt.get("manifest_sha256") != sha256_file(PRE_REVIEW_DIR / "manifest.json"):
        raise RuntimeError("pre-adjudication review receipt drift")
    review = _read_json(PRE_REVIEW_DIR / "review.json")
    current_machine = {key: value for key, value in comparison.items() if key != "final_human"}
    if canonical_json(review) != canonical_json(current_machine):
        raise RuntimeError("pre-adjudication review drift")
    automatic = _read_jsonl(RUN_ROOT / "automatic/candidate_similarity.jsonl")
    final_rows = build_zero_adjudication_rows(comparison, automatic)
    result = final_measurement_summary(final_rows)
    FINALIZATION_DIR.mkdir(parents=True, mode=0o700)
    for row in final_rows:
        row.pop("distiluse")
    _write_bytes_exclusive(
        FINALIZATION_DIR / "final_human_records.jsonl",
        "".join(canonical_json(row) + "\n" for row in final_rows).encode("utf-8"),
    )
    _write_json_exclusive(FINALIZATION_DIR / "measurement_result.json", result)
    receipt = _manifest_receipt(
        FINALIZATION_DIR,
        ["final_human_records.jsonl", "measurement_result.json"],
        str(result["formal"]["status"]),
    )
    return {**result, **receipt}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("seal", "validate", "finalize-zero"))
    args = parser.parse_args()
    functions = {"seal": seal, "validate": validate, "finalize-zero": finalize_zero}
    print(canonical_json(functions[args.command]()))


if __name__ == "__main__":
    main()
