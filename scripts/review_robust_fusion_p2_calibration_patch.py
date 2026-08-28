#!/usr/bin/env python3
"""锁定并审查 Robust Fusion P2 五例补标及其与 v2 保留部分的合并结果。"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import prepare_robust_fusion_p2_calibration_patch as patch
import prepare_robust_fusion_p2_calibration_replay as base

LOCK_VERSION = "ROBUST-FUSION-P2-PATCH-SUBMISSION-LOCK-2026-08-29-v1"
REVIEW_VERSION = "ROBUST-FUSION-P2-PATCH-COMBINED-REVIEW-2026-08-29-v1"
ROLE_DIRS = {"A": "annotator_a", "B": "annotator_b"}
CSV_NAMES = (
    "case_qualification.csv",
    "candidate_annotation.csv",
    "pair_annotation.csv",
)
STATIC_INPUT_NAMES = (
    "INSTRUCTIONS.md",
    "标注操作手册.md",
    "view_contract.json",
    "annotation_cases.jsonl",
)

QUALIFICATION_ENUMS = {
    "target_reference_status": {"valid", "invalid", "unresolved"},
    "target_group_status": {"unique", "non_unique", "unresolved"},
}
CANDIDATE_ENUMS = {
    "relevance_status": {
        "relevant_gold",
        "relevant_equivalent",
        "verified_incorrect_distractor",
        "unresolved_possible_false_negative",
    },
    "target_relation": {"equivalent", "factual_conflict", "other_incorrect", "unresolved"},
    "conflict_type": {
        "not_applicable",
        "version_or_time",
        "numeric",
        "negation_or_direction",
        "applicability_or_condition",
    },
    "adjudicability": {
        "not_applicable",
        "detectable_only",
        "conditionally_adjudicable",
        "unidentifiable",
    },
}
PAIR_ENUMS = {
    "candidate_pair_relation": {
        "same_fact",
        "factual_conflict",
        "insufficient_context",
        "unresolved",
    }
}
CONFIDENCE = {"high", "medium", "low"}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def file_meta(path: Path) -> dict[str, Any]:
    stat = path.lstat()
    return {
        "size_bytes": stat.st_size,
        "mtime_local": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
        "sha256": patch.sha256_file(path),
        "regular_file": path.is_file(),
        "symlink": path.is_symlink(),
    }


def relative(repo_root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(repo_root))


def verify_master_and_static_inputs(
    repo_root: Path,
    master_dir: Path,
    work_root: Path,
) -> dict[str, Any]:
    manifest_path = master_dir / "manifest.json"
    manifest_hash = patch.sha256_file(manifest_path)
    expected_line = f"{manifest_hash}  manifest.json\n"
    if (master_dir / "manifest.sha256").read_text(encoding="utf-8") != expected_line:
        raise RuntimeError("补包 manifest.sha256 不匹配")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("package_version") != patch.PACKAGE_VERSION:
        raise RuntimeError("补包版本不符")
    for name, meta in manifest["outputs"].items():
        path = master_dir / name
        if path.stat().st_size != meta["size_bytes"] or patch.sha256_file(path) != meta["sha256"]:
            raise RuntimeError(f"管理员补包输出发生变化：{name}")

    for reviewer_id, dirname in ROLE_DIRS.items():
        role_dir = work_root / dirname
        receipt = json.loads((role_dir / "package_receipt.json").read_text(encoding="utf-8"))
        if receipt.get("reviewer_id") != reviewer_id or receipt.get("answer_key_included") is not False:
            raise RuntimeError(f"{dirname} 回执角色或盲化声明不符")
        if receipt.get("master_manifest_sha256") != manifest_hash:
            raise RuntimeError(f"{dirname} 未绑定当前管理员补包")
        for name in STATIC_INPUT_NAMES:
            expected = receipt["files"][name]
            path = role_dir / name
            if path.stat().st_size != expected["size_bytes"] or patch.sha256_file(path) != expected["sha256"]:
                raise RuntimeError(f"{dirname} 的冻结输入发生变化：{name}")
    return {
        "master_manifest_path": relative(repo_root, manifest_path),
        "master_manifest_sha256": manifest_hash,
        "blind_input_sha256": patch.sha256_file(master_dir / "annotation_cases.jsonl"),
    }


def lock_submissions(
    repo_root: Path,
    master_dir: Path,
    work_root: Path,
    review_root: Path,
) -> dict[str, Any]:
    if review_root.exists():
        raise RuntimeError(f"主持人审查目录已存在，拒绝覆盖：{review_root}")
    package_binding = verify_master_and_static_inputs(repo_root, master_dir, work_root)

    source_rows: list[dict[str, Any]] = []
    for reviewer_id, dirname in ROLE_DIRS.items():
        for name in CSV_NAMES:
            path = work_root / dirname / name
            if not path.exists() or not path.is_file() or path.is_symlink():
                raise RuntimeError(f"提交不是普通文件：{path}")
            source_rows.append(
                {
                    "reviewer_id": reviewer_id,
                    "source_path": relative(repo_root, path),
                    "filename": name,
                    **file_meta(path),
                }
            )

    locked_at = now_iso()
    snapshot_root = review_root / "locked_submissions"
    for reviewer_id, dirname in ROLE_DIRS.items():
        destination = snapshot_root / dirname
        destination.mkdir(parents=True, exist_ok=False)
        for name in CSV_NAMES:
            shutil.copyfile(work_root / dirname / name, destination / name)

    snapshot_rows: list[dict[str, Any]] = []
    for reviewer_id, dirname in ROLE_DIRS.items():
        for name in CSV_NAMES:
            source = next(
                row
                for row in source_rows
                if row["reviewer_id"] == reviewer_id and row["filename"] == name
            )
            snapshot = snapshot_root / dirname / name
            meta = file_meta(snapshot)
            if meta["sha256"] != source["sha256"] or meta["size_bytes"] != source["size_bytes"]:
                raise RuntimeError(f"快照与提交不一致：{snapshot}")
            snapshot_rows.append(
                {
                    "reviewer_id": reviewer_id,
                    "snapshot_path": relative(repo_root, snapshot),
                    "filename": name,
                    **meta,
                }
            )

    lock = {
        "lock_version": LOCK_VERSION,
        "package_version": patch.PACKAGE_VERSION,
        "handbook_version": patch.HANDBOOK_VERSION,
        "view_contract_version": patch.VIEW_CONTRACT_VERSION,
        "locked_at_local": locked_at,
        **package_binding,
        "source_submissions": source_rows,
        "locked_snapshots": snapshot_rows,
        "review_must_use_snapshots": True,
        "submission_content_read_before_lock": False,
        "submissions_compared_to_key_before_lock": False,
        "facilitator_key_known_before_lock": True,
        "facilitator_key_knowledge_reason": "当前主持人创建了 v3 补包及答案键；因此不声称主持人盲态，只声称两位标注员独立盲标且提交在比较前锁定。",
        "annotator_independence_claim": "A/B 目录隔离、盲化输入哈希相同，角色目录不含答案键。",
    }
    write_json(review_root / "submission_lock.json", lock)
    lock_hash = patch.sha256_file(review_root / "submission_lock.json")
    (review_root / "submission_lock.sha256").write_text(
        f"{lock_hash}  submission_lock.json\n",
        encoding="utf-8",
    )
    (review_root / "README.md").write_text(
        f"""# P2 五例补标提交锁定目录

- 锁定版本：`{LOCK_VERSION}`
- 锁定时间：`{locked_at}`
- 补包版本：`{patch.PACKAGE_VERSION}`
- 后续审查只读取 `locked_submissions/`，不再读取标注员工作目录。
- 六份提交在内容读取和答案比较前完成哈希锁定。
- 主持人是 v3 补包与 key 的创建者，因此预先知道 key；本记录不虚构主持人盲态。
- 两位标注员的角色目录相互隔离、输入相同且不含答案键。
""",
        encoding="utf-8",
    )
    return {
        "status": "LOCKED",
        "lock_version": LOCK_VERSION,
        "locked_at_local": locked_at,
        "submission_lock_sha256": lock_hash,
        "submission_count": len(source_rows),
        "snapshot_count": len(snapshot_rows),
        "facilitator_key_known_before_lock": True,
        "submissions_compared_to_key_before_lock": False,
        "review_root": relative(repo_root, review_root),
    }


def verify_lock(repo_root: Path, review_root: Path) -> dict[str, Any]:
    lock_path = review_root / "submission_lock.json"
    lock_hash = patch.sha256_file(lock_path)
    expected = f"{lock_hash}  submission_lock.json\n"
    if (review_root / "submission_lock.sha256").read_text(encoding="utf-8") != expected:
        raise RuntimeError("submission_lock.sha256 不匹配")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("lock_version") != LOCK_VERSION:
        raise RuntimeError("提交锁版本不符")
    if lock.get("submission_content_read_before_lock") is not False:
        raise RuntimeError("提交锁的内容读取声明不合法")
    if lock.get("submissions_compared_to_key_before_lock") is not False:
        raise RuntimeError("提交锁的答案比较声明不合法")
    if lock.get("facilitator_key_known_before_lock") is not True:
        raise RuntimeError("提交锁未披露主持人预知 key")
    for row in lock.get("locked_snapshots", []):
        path = repo_root / row["snapshot_path"]
        meta = file_meta(path)
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"锁定快照不是普通文件：{path}")
        if meta["sha256"] != row["sha256"] or meta["size_bytes"] != row["size_bytes"]:
            raise RuntimeError(f"锁定快照发生变化：{path}")
    if len(lock.get("locked_snapshots", [])) != 6:
        raise RuntimeError("锁定快照数量不为六")
    return {
        "status": "PASS",
        "submission_lock_sha256": lock_hash,
        "snapshot_count": 6,
        "locked_at_local": lock["locked_at_local"],
        "facilitator_key_known_before_lock": True,
    }


def csv_rows(path: Path, expected_fields: list[str]) -> list[dict[str, str]]:
    fields, rows = patch.read_csv(path)
    if fields != expected_fields:
        raise ValueError(f"表头不符：{path}")
    return rows


def expected_indexes(
    key_rows: list[dict[str, Any]],
) -> tuple[
    list[str],
    list[tuple[str, str]],
    list[tuple[str, str, str]],
    dict[tuple[str, str], dict[str, str]],
    dict[tuple[str, str], dict[str, Any]],
]:
    case_ids = [row["case_id"] for row in key_rows]
    candidate_ids: list[tuple[str, str]] = []
    pair_ids: list[tuple[str, str, str]] = []
    expected_labels: dict[tuple[str, str], dict[str, str]] = {}
    candidate_meta: dict[tuple[str, str], dict[str, Any]] = {}
    for case in key_rows:
        key_by_id = {
            row["candidate_id"]: row for row in case["facilitator"]["candidate_keys"]
        }
        for candidate in case["candidates"]:
            unit = (case["case_id"], candidate["candidate_id"])
            candidate_ids.append(unit)
            expected_labels[unit] = key_by_id[candidate["candidate_id"]]["expected"]
            candidate_meta[unit] = {
                "dataset_id": case["dataset_id"],
                "quota_cell": case["quota_cell"],
                "key_conflict_type": expected_labels[unit]["conflict_type"],
                "source_partition": (
                    "retained_v2" if case["case_id"] in patch.RETAINED_CASE_IDS else "patch_v3"
                ),
            }
        pair_key = case["facilitator"].get("pair_key")
        if pair_key:
            pair_ids.append(
                (
                    case["case_id"],
                    pair_key["candidate_ids"][0],
                    pair_key["candidate_ids"][1],
                )
            )
    return case_ids, candidate_ids, pair_ids, expected_labels, candidate_meta


def validate_patch_role(
    snapshot_dir: Path,
    reviewer_id: str,
    key_rows: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, str]]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    case_ids, candidate_ids, pair_ids, _, _ = expected_indexes(key_rows)
    try:
        cases = csv_rows(snapshot_dir / "case_qualification.csv", patch.CASE_FIELDS)
        candidates = csv_rows(
            snapshot_dir / "candidate_annotation.csv", patch.CANDIDATE_FIELDS
        )
        pairs = csv_rows(snapshot_dir / "pair_annotation.csv", patch.PAIR_FIELDS)
    except ValueError as exc:
        return {"case": [], "candidate": [], "pair": []}, [
            {"reviewer_id": reviewer_id, "scope": "file", "error": str(exc)}
        ]

    def add(scope: str, unit: str, error: str) -> None:
        errors.append(
            {
                "reviewer_id": reviewer_id,
                "scope": scope,
                "unit": unit,
                "error": error,
            }
        )

    if [row["case_id"] for row in cases] != case_ids:
        add("case", "all", "案例行数、顺序、缺失或重复 ID 不符合冻结模板")
    if [(row["case_id"], row["candidate_id"]) for row in candidates] != candidate_ids:
        add("candidate", "all", "候选行数、顺序、缺失或重复 ID 不符合冻结模板")
    if [
        (row["case_id"], row["candidate_id_a"], row["candidate_id_b"]) for row in pairs
    ] != pair_ids:
        add("pair", "all", "候选对行数、顺序、缺失或重复 ID 不符合冻结模板")

    for row in cases:
        unit = row.get("case_id", "?")
        if row.get("reviewer_id") != reviewer_id:
            add("case", unit, "reviewer_id 不符")
        if row.get("adjudication_status") != "single":
            add("case", unit, "初始 adjudication_status 必须为 single")
        if row.get("handbook_version") != patch.HANDBOOK_VERSION:
            add("case", unit, "handbook_version 不符")
        for field, legal in QUALIFICATION_ENUMS.items():
            if row.get(field) not in legal:
                add("case", unit, f"{field} 缺失或非法：{row.get(field)!r}")
        for field in ("evidence_locator", "rationale"):
            if not row.get(field, "").strip():
                add("case", unit, f"{field} 为空")
        if row.get("confidence") not in CONFIDENCE:
            add("case", unit, "confidence 缺失或非法")

    for row in candidates:
        unit = f"{row.get('case_id','?')}/{row.get('candidate_id','?')}"
        if row.get("reviewer_id") != reviewer_id:
            add("candidate", unit, "reviewer_id 不符")
        if row.get("adjudication_status") != "single":
            add("candidate", unit, "初始 adjudication_status 必须为 single")
        if row.get("handbook_version") != patch.HANDBOOK_VERSION:
            add("candidate", unit, "handbook_version 不符")
        for field, legal in CANDIDATE_ENUMS.items():
            if row.get(field) not in legal:
                add("candidate", unit, f"{field} 缺失或非法：{row.get(field)!r}")
        for field in ("evidence_locator", "rationale"):
            if not row.get(field, "").strip():
                add("candidate", unit, f"{field} 为空")
        if row.get("confidence") not in CONFIDENCE:
            add("candidate", unit, "confidence 缺失或非法")
        if all(row.get(field) in legal for field, legal in CANDIDATE_ENUMS.items()):
            try:
                patch.validate_expected({field: row[field] for field in CANDIDATE_ENUMS})
            except RuntimeError as exc:
                add("candidate", unit, f"非法字段组合：{exc}")

    for row in pairs:
        unit = (
            f"{row.get('case_id','?')}/"
            f"{row.get('candidate_id_a','?')}-{row.get('candidate_id_b','?')}"
        )
        if row.get("reviewer_id") != reviewer_id:
            add("pair", unit, "reviewer_id 不符")
        if row.get("adjudication_status") != "single":
            add("pair", unit, "初始 adjudication_status 必须为 single")
        if row.get("candidate_pair_relation") not in PAIR_ENUMS["candidate_pair_relation"]:
            add("pair", unit, "candidate_pair_relation 缺失或非法")
        for field in ("evidence_locator", "rationale"):
            if not row.get(field, "").strip():
                add("pair", unit, f"{field} 为空")
        if row.get("confidence") not in CONFIDENCE:
            add("pair", unit, "confidence 缺失或非法")
    return {"case": cases, "candidate": candidates, "pair": pairs}, errors


def base_retained_role_rows(
    repo_root: Path,
    reviewer_id: str,
) -> dict[str, list[dict[str, str]]]:
    dirname = ROLE_DIRS[reviewer_id]
    root = repo_root / patch.BASE_LOCK_PATH.parent / "locked_submissions" / dirname
    case_rows = [
        row
        for row in csv_rows(root / "case_qualification.csv", base.CASE_FIELDS)
        if row["case_id"] in patch.RETAINED_CASE_IDS
    ]
    candidate_rows = [
        row
        for row in csv_rows(root / "candidate_annotation.csv", base.CANDIDATE_FIELDS)
        if row["case_id"] in patch.RETAINED_CASE_IDS
    ]
    pair_rows = [
        row
        for row in csv_rows(root / "pair_annotation.csv", base.PAIR_FIELDS)
        if row["case_id"] in patch.RETAINED_CASE_IDS
    ]
    if (len(case_rows), len(candidate_rows), len(pair_rows)) != (7, 8, 1):
        raise RuntimeError(f"v2 保留提交行数异常：{reviewer_id}")
    return {"case": case_rows, "candidate": candidate_rows, "pair": pair_rows}


def macro_f1(left: list[str], right: list[str]) -> float | None:
    if not left or len(left) != len(right):
        return None
    labels = sorted(set(left) | set(right))
    scores: list[float] = []
    for label in labels:
        tp = sum(a == label and b == label for a, b in zip(left, right, strict=True))
        fp = sum(a == label and b != label for a, b in zip(left, right, strict=True))
        fn = sum(a != label and b == label for a, b in zip(left, right, strict=True))
        denominator = 2 * tp + fp + fn
        scores.append(0.0 if denominator == 0 else 2 * tp / denominator)
    return sum(scores) / len(scores)


def krippendorff_alpha_nominal(left: list[str], right: list[str]) -> float | None:
    if not left or len(left) != len(right):
        return None
    observed = sum(a != b for a, b in zip(left, right, strict=True)) / len(left)
    counts = Counter(left + right)
    total = sum(counts.values())
    if total < 2:
        return None
    expected = 1 - sum(count * (count - 1) for count in counts.values()) / (
        total * (total - 1)
    )
    if math.isclose(expected, 0.0):
        return 1.0 if math.isclose(observed, 0.0) else None
    return 1 - observed / expected


def agreement(left: list[str], right: list[str]) -> dict[str, Any]:
    if len(left) != len(right):
        raise RuntimeError("agreement 输入长度不一致")
    matches = sum(a == b for a, b in zip(left, right, strict=True))
    return {
        "matches": matches,
        "total": len(left),
        "rate": matches / len(left) if left else None,
        "macro_f1": macro_f1(left, right),
        "krippendorff_alpha_nominal": krippendorff_alpha_nominal(left, right),
    }


def metric_bundle(
    units: list[tuple[str, str]],
    by_role: dict[str, dict[tuple[str, str], dict[str, str]]],
    expected_labels: dict[tuple[str, str], dict[str, str]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field in ("relevance_status", "target_relation", "conflict_type", "adjudicability"):
        a = [by_role["A"][unit][field] for unit in units]
        b = [by_role["B"][unit][field] for unit in units]
        key = [expected_labels[unit][field] for unit in units]
        result[field] = {
            "a_vs_b": agreement(a, b),
            "a_vs_key": agreement(a, key),
            "b_vs_key": agreement(b, key),
        }
    return result


def review_submissions(
    repo_root: Path,
    master_dir: Path,
    review_root: Path,
) -> dict[str, Any]:
    lock_check = verify_lock(repo_root, review_root)
    output_path = review_root / "mechanical_review.json"
    if output_path.exists():
        raise RuntimeError("mechanical_review.json 已存在，拒绝覆盖历史审查")

    retained, base_binding = patch.verify_base(repo_root)
    patch_cases = patch.read_jsonl(master_dir / "facilitator_key.jsonl")
    patch.validate_patch_cases(patch_cases)
    combined_design = patch.validate_combined(retained, patch_cases)
    combined_key = retained + patch_cases
    (
        case_ids,
        candidate_ids,
        pair_ids,
        expected_labels,
        candidate_meta,
    ) = expected_indexes(combined_key)
    patch_case_ids, patch_candidate_ids, _, _, _ = expected_indexes(patch_cases)

    patch_role_data: dict[str, dict[str, list[dict[str, str]]]] = {}
    format_errors: list[dict[str, str]] = []
    for reviewer_id, dirname in ROLE_DIRS.items():
        data, errors = validate_patch_role(
            review_root / "locked_submissions" / dirname,
            reviewer_id,
            patch_cases,
        )
        patch_role_data[reviewer_id] = data
        format_errors.extend(errors)

    combined_role_data: dict[str, dict[str, list[dict[str, str]]]] = {}
    for reviewer_id in ROLE_DIRS:
        retained_rows = base_retained_role_rows(repo_root, reviewer_id)
        combined_role_data[reviewer_id] = {
            scope: retained_rows[scope] + patch_role_data[reviewer_id][scope]
            for scope in ("case", "candidate", "pair")
        }

    if format_errors:
        report = {
            "review_version": REVIEW_VERSION,
            "reviewed_at_local": now_iso(),
            "lock_check": lock_check,
            "format_errors": format_errors,
            "provisional_gate": "FAIL_FORMAT",
            "gate_scope": "P2 构念校准；不是 Gate A/B 证据",
        }
        write_json(output_path, report)
        return report

    for reviewer_id in ROLE_DIRS:
        if [row["case_id"] for row in combined_role_data[reviewer_id]["case"]] != case_ids:
            raise RuntimeError(f"合并案例顺序异常：{reviewer_id}")
        if [
            (row["case_id"], row["candidate_id"])
            for row in combined_role_data[reviewer_id]["candidate"]
        ] != candidate_ids:
            raise RuntimeError(f"合并候选顺序异常：{reviewer_id}")
        if [
            (row["case_id"], row["candidate_id_a"], row["candidate_id_b"])
            for row in combined_role_data[reviewer_id]["pair"]
        ] != pair_ids:
            raise RuntimeError(f"合并候选对顺序异常：{reviewer_id}")

    by_role_candidate = {
        role: {
            (row["case_id"], row["candidate_id"]): row
            for row in combined_role_data[role]["candidate"]
        }
        for role in ROLE_DIRS
    }
    by_role_case = {
        role: {row["case_id"]: row for row in combined_role_data[role]["case"]}
        for role in ROLE_DIRS
    }
    by_role_pair = {
        role: {
            (row["case_id"], row["candidate_id_a"], row["candidate_id_b"]): row
            for row in combined_role_data[role]["pair"]
        }
        for role in ROLE_DIRS
    }

    combined_metrics = metric_bundle(candidate_ids, by_role_candidate, expected_labels)
    patch_metrics = metric_bundle(patch_candidate_ids, by_role_candidate, expected_labels)
    conflict_units = [
        unit
        for unit in candidate_ids
        if expected_labels[unit]["target_relation"] == "factual_conflict"
    ]
    conflict_metrics: dict[str, Any] = {}
    for field in ("conflict_type", "adjudicability"):
        a = [by_role_candidate["A"][unit][field] for unit in conflict_units]
        b = [by_role_candidate["B"][unit][field] for unit in conflict_units]
        key = [expected_labels[unit][field] for unit in conflict_units]
        conflict_metrics[field] = {
            "a_vs_b": agreement(a, b),
            "a_vs_key": agreement(a, key),
            "b_vs_key": agreement(b, key),
        }

    qualification: dict[str, Any] = {}
    for field, key_value in (
        ("target_reference_status", "valid"),
        ("target_group_status", "unique"),
    ):
        a = [by_role_case["A"][case_id][field] for case_id in case_ids]
        b = [by_role_case["B"][case_id][field] for case_id in case_ids]
        key = [key_value] * len(case_ids)
        qualification[field] = {
            "a_vs_b": agreement(a, b),
            "a_vs_key": agreement(a, key),
            "b_vs_key": agreement(b, key),
        }

    patch_qualification: dict[str, Any] = {}
    for field, key_value in (
        ("target_reference_status", "valid"),
        ("target_group_status", "unique"),
    ):
        a = [by_role_case["A"][case_id][field] for case_id in patch_case_ids]
        b = [by_role_case["B"][case_id][field] for case_id in patch_case_ids]
        key = [key_value] * len(patch_case_ids)
        patch_qualification[field] = {
            "a_vs_b": agreement(a, b),
            "a_vs_key": agreement(a, key),
            "b_vs_key": agreement(b, key),
        }

    pair_metrics: dict[str, Any] = {}
    for pair_id in pair_ids:
        a = by_role_pair["A"][pair_id]["candidate_pair_relation"]
        b = by_role_pair["B"][pair_id]["candidate_pair_relation"]
        pair_metrics["/".join(pair_id)] = {
            "a": a,
            "b": b,
            "key": "same_fact",
            "both_correct": a == b == "same_fact",
        }

    candidate_fields = (
        "relevance_status",
        "target_relation",
        "conflict_type",
        "adjudicability",
    )
    comparison_rows: list[dict[str, Any]] = []
    disagreements: list[dict[str, Any]] = []
    for unit in candidate_ids:
        meta = candidate_meta[unit]
        row: dict[str, Any] = {
            "case_id": unit[0],
            "candidate_id": unit[1],
            **meta,
        }
        for field in candidate_fields:
            row[f"a_{field}"] = by_role_candidate["A"][unit][field]
            row[f"b_{field}"] = by_role_candidate["B"][unit][field]
            row[f"key_{field}"] = expected_labels[unit][field]
        row["a_evidence_locator"] = by_role_candidate["A"][unit]["evidence_locator"]
        row["b_evidence_locator"] = by_role_candidate["B"][unit]["evidence_locator"]
        row["a_rationale"] = by_role_candidate["A"][unit]["rationale"]
        row["b_rationale"] = by_role_candidate["B"][unit]["rationale"]
        comparison_rows.append(row)
        for field in candidate_fields:
            a_value = row[f"a_{field}"]
            b_value = row[f"b_{field}"]
            key_value = row[f"key_{field}"]
            if a_value != b_value or a_value != key_value or b_value != key_value:
                disagreements.append(
                    {
                        "case_id": unit[0],
                        "candidate_id": unit[1],
                        **meta,
                        "field": field,
                        "a": a_value,
                        "b": b_value,
                        "key": key_value,
                        "a_evidence_locator": row["a_evidence_locator"],
                        "b_evidence_locator": row["b_evidence_locator"],
                        "a_rationale": row["a_rationale"],
                        "b_rationale": row["b_rationale"],
                    }
                )

    equivalent_conflict_cross = [
        "/".join(unit)
        for unit in candidate_ids
        if {
            by_role_candidate["A"][unit]["target_relation"],
            by_role_candidate["B"][unit]["target_relation"],
        }
        == {"equivalent", "factual_conflict"}
    ]
    evidence_only_admin_signal: list[dict[str, Any]] = []
    admin_terms = ("qrel", "相似度", "排名", "reranker", "ltr", "score")
    evidence_terms = ("t1", "c1", "c2", "query", "目标", "候选", "正文", "“", '"')
    for role in ROLE_DIRS:
        for unit, row in by_role_candidate[role].items():
            text = row["evidence_locator"].lower()
            if any(term in text for term in admin_terms) and not any(
                term in text for term in evidence_terms
            ):
                evidence_only_admin_signal.append(
                    {"unit": "/".join(unit), "reviewer_id": role, "evidence_locator": text}
                )

    relation_gate = combined_metrics["target_relation"]
    conflict_gate = conflict_metrics["conflict_type"]
    adjudicability_gate = conflict_metrics["adjudicability"]
    gate_checks = {
        "format_errors_zero": not format_errors,
        "qualification_all_valid_unique": all(
            qualification[field][comparison]["matches"] == 12
            for field in qualification
            for comparison in ("a_vs_key", "b_vs_key")
        ),
        "target_relation_a_b_at_least_12_of_13": relation_gate["a_vs_b"]["matches"] >= 12,
        "target_relation_each_vs_key_at_least_12_of_13": (
            relation_gate["a_vs_key"]["matches"] >= 12
            and relation_gate["b_vs_key"]["matches"] >= 12
        ),
        "conflict_type_a_b_at_least_8_of_9": conflict_gate["a_vs_b"]["matches"] >= 8,
        "conflict_type_each_vs_key_at_least_8_of_9": (
            conflict_gate["a_vs_key"]["matches"] >= 8
            and conflict_gate["b_vs_key"]["matches"] >= 8
        ),
        "adjudicability_a_b_at_least_7_of_9": adjudicability_gate["a_vs_b"]["matches"] >= 7,
        "adjudicability_each_vs_key_at_least_7_of_9": (
            adjudicability_gate["a_vs_key"]["matches"] >= 7
            and adjudicability_gate["b_vs_key"]["matches"] >= 7
        ),
        "pair_both_same_fact": all(row["both_correct"] for row in pair_metrics.values()),
        "equivalent_vs_factual_conflict_cross_zero": not equivalent_conflict_cross,
        "evidence_only_admin_signal_zero": not evidence_only_admin_signal,
    }
    provisional_gate = (
        "PASS_PENDING_FACILITATOR_ADJUDICATION"
        if all(gate_checks.values())
        else "FAIL_REQUIRES_FACILITATOR_DIAGNOSIS"
    )
    if all(gate_checks.values()) and not disagreements:
        provisional_gate = "PASS_NO_DISAGREEMENT"

    review = {
        "review_version": REVIEW_VERSION,
        "reviewed_at_local": now_iso(),
        "package_version": patch.PACKAGE_VERSION,
        "handbook_version": patch.HANDBOOK_VERSION,
        "view_contract_version": patch.VIEW_CONTRACT_VERSION,
        "submission_lock_sha256": lock_check["submission_lock_sha256"],
        "review_script_sha256": patch.sha256_file(Path(__file__).resolve()),
        "facilitator_key_known_before_lock": True,
        "format_errors": format_errors,
        "base_v2_binding": base_binding,
        "combined_design": combined_design,
        "patch_qualification_5": patch_qualification,
        "patch_candidate_metrics_5": patch_metrics,
        "combined_qualification_12": qualification,
        "combined_candidate_metrics_13": combined_metrics,
        "combined_conflict_gate_metrics_9": conflict_metrics,
        "pair_metrics": pair_metrics,
        "zero_tolerance_audit": {
            "equivalent_conflict_cross": equivalent_conflict_cross,
            "evidence_only_admin_signal": evidence_only_admin_signal,
        },
        "gate_checks": gate_checks,
        "disagreement_count": len(disagreements),
        "patch_disagreement_count": sum(
            row["source_partition"] == "patch_v3" for row in disagreements
        ),
        "retained_v2_disagreement_count": sum(
            row["source_partition"] == "retained_v2" for row in disagreements
        ),
        "disagreements": disagreements,
        "provisional_gate": provisional_gate,
        "gate_scope": "P2 构念校准；不是 Gate A/B 证据",
    }
    write_json(output_path, review)

    with (review_root / "comparison_rows.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(comparison_rows[0]))
        writer.writeheader()
        writer.writerows(comparison_rows)
    if disagreements:
        with (review_root / "disagreements.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=list(disagreements[0]))
            writer.writeheader()
            writer.writerows(disagreements)
    else:
        (review_root / "disagreements.csv").write_text(
            "case_id,candidate_id,field,a,b,key\n",
            encoding="utf-8",
        )
    return review


def resolve(repo_root: Path, path: Path) -> Path:
    resolved = (path if path.is_absolute() else repo_root / path).resolve()
    if not resolved.is_relative_to(repo_root):
        raise RuntimeError(f"路径必须位于仓库内：{resolved}")
    return resolved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("lock", "verify-lock", "review"))
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--master-dir",
        type=Path,
        default=Path("data/robust_fusion/derived/p2_calibration_patch_v3"),
    )
    parser.add_argument(
        "--work-root",
        type=Path,
        default=Path(
            "runs/robust_fusion/internal_v6_deepseek_pilot_v1/"
            "human_calibration_patch_v3"
        ),
    )
    parser.add_argument(
        "--review-root",
        type=Path,
        default=Path(
            "runs/robust_fusion/internal_v6_deepseek_pilot_v1/"
            "human_calibration_patch_v3/facilitator_review"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    master_dir = resolve(repo_root, args.master_dir)
    work_root = resolve(repo_root, args.work_root)
    review_root = resolve(repo_root, args.review_root)
    if args.mode == "lock":
        result = lock_submissions(repo_root, master_dir, work_root, review_root)
    elif args.mode == "verify-lock":
        result = verify_lock(repo_root, review_root)
    else:
        result = review_submissions(repo_root, master_dir, review_root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
