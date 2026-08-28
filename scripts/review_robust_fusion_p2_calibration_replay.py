#!/usr/bin/env python3
"""锁定并机械审查 Robust Fusion P2 双人重放提交。"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import prepare_robust_fusion_p2_calibration_replay as package

LOCK_VERSION = "ROBUST-FUSION-P2-SUBMISSION-LOCK-2026-08-29-v1"
REVIEW_VERSION = "ROBUST-FUSION-P2-MECHANICAL-REVIEW-2026-08-29-v1"
ROLE_DIRS = {"A": "annotator_a", "B": "annotator_b"}
CSV_NAMES = (
    "case_qualification.csv",
    "candidate_annotation.csv",
    "pair_annotation.csv",
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


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def file_meta(path: Path) -> dict[str, Any]:
    stat = path.lstat()
    return {
        "size_bytes": stat.st_size,
        "mtime_local": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
        "sha256": package.sha256_file(path),
        "regular_file": path.is_file(),
        "symlink": path.is_symlink(),
    }


def lock_submissions(
    repo_root: Path,
    master_dir: Path,
    work_root: Path,
    review_root: Path,
) -> dict[str, Any]:
    if review_root.exists():
        raise RuntimeError(
            f"主持人审查目录已存在，拒绝覆盖：{review_root}。请先运行 --verify-lock。"
        )
    manifest_path = master_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["package_version"] != package.PACKAGE_VERSION:
        raise RuntimeError("管理员包版本与重放协议不一致")

    source_rows: list[dict[str, Any]] = []
    for reviewer_id, dirname in ROLE_DIRS.items():
        for name in CSV_NAMES:
            path = work_root / dirname / name
            if not path.exists() or not path.is_file() or path.is_symlink():
                raise RuntimeError(f"提交不是普通文件：{path}")
            source_rows.append(
                {
                    "reviewer_id": reviewer_id,
                    "source_path": str(path.relative_to(repo_root)),
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
                    "snapshot_path": str(snapshot.relative_to(repo_root)),
                    "filename": name,
                    **meta,
                }
            )

    lock = {
        "lock_version": LOCK_VERSION,
        "package_version": package.PACKAGE_VERSION,
        "handbook_version": package.HANDBOOK_VERSION,
        "view_contract_version": package.VIEW_CONTRACT_VERSION,
        "locked_at_local": locked_at,
        "master_manifest_path": str(manifest_path.relative_to(repo_root)),
        "master_manifest_sha256": package.sha256_file(manifest_path),
        "blind_input_sha256": package.sha256_file(master_dir / "annotation_cases.jsonl"),
        "source_submissions": source_rows,
        "locked_snapshots": snapshot_rows,
        "answer_key_read_before_lock": False,
        "review_must_use_snapshots": True,
    }
    write_json(review_root / "submission_lock.json", lock)
    lock_hash = package.sha256_file(review_root / "submission_lock.json")
    (review_root / "submission_lock.sha256").write_text(
        f"{lock_hash}  submission_lock.json\n",
        encoding="utf-8",
    )
    (review_root / "README.md").write_text(
        f"""# P2 重放提交锁定目录

- 锁定版本：`{LOCK_VERSION}`
- 锁定时间：`{locked_at}`
- 包版本：`{package.PACKAGE_VERSION}`
- 规则：后续主持人审查只读取 `locked_submissions/`，不再读取标注员工作目录。
- 答案键：建立本锁定记录前未读取。

`submission_lock.json` 保存六份源提交和六份快照的大小、修改时间与 SHA-256；`submission_lock.sha256` 锁定该回执本身。
""",
        encoding="utf-8",
    )
    return {
        "status": "LOCKED",
        "lock_version": LOCK_VERSION,
        "locked_at_local": locked_at,
        "submission_lock_sha256": lock_hash,
        "submission_count": 6,
        "snapshot_count": 6,
        "answer_key_read_before_lock": False,
        "review_root": str(review_root.relative_to(repo_root)),
        "submissions": [
            {
                "reviewer_id": row["reviewer_id"],
                "filename": row["filename"],
                "sha256": row["sha256"],
            }
            for row in source_rows
        ],
    }


def verify_lock(repo_root: Path, review_root: Path) -> dict[str, Any]:
    lock_path = review_root / "submission_lock.json"
    lock_hash = package.sha256_file(lock_path)
    expected = f"{lock_hash}  submission_lock.json\n"
    if (review_root / "submission_lock.sha256").read_text(encoding="utf-8") != expected:
        raise RuntimeError("submission_lock.sha256 不匹配")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock["lock_version"] != LOCK_VERSION or lock["answer_key_read_before_lock"] is not False:
        raise RuntimeError("锁定回执版本或盲态声明不合法")
    for row in lock["locked_snapshots"]:
        path = repo_root / row["snapshot_path"]
        meta = file_meta(path)
        if meta["sha256"] != row["sha256"] or meta["size_bytes"] != row["size_bytes"]:
            raise RuntimeError(f"锁定快照发生变化：{path}")
    return {
        "status": "PASS",
        "submission_lock_sha256": lock_hash,
        "snapshot_count": len(lock["locked_snapshots"]),
        "locked_at_local": lock["locked_at_local"],
    }


def csv_rows(path: Path, expected_fields: list[str]) -> list[dict[str, str]]:
    fields, rows = package.read_csv(path)
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
            row["candidate_id"]: row
            for row in case["facilitator"]["candidate_keys"]
        }
        for candidate in case["candidates"]:
            unit = (case["case_id"], candidate["candidate_id"])
            candidate_ids.append(unit)
            expected_labels[unit] = key_by_id[candidate["candidate_id"]]["expected"]
            candidate_meta[unit] = {
                "dataset_id": case["dataset_id"],
                "quota_cell": case["quota_cell"],
                "key_conflict_type": expected_labels[unit]["conflict_type"],
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


def validate_role(
    snapshot_dir: Path,
    reviewer_id: str,
    key_rows: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, str]]], list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    case_ids, candidate_ids, pair_ids, _, _ = expected_indexes(key_rows)
    try:
        cases = csv_rows(snapshot_dir / "case_qualification.csv", package.CASE_FIELDS)
        candidates = csv_rows(
            snapshot_dir / "candidate_annotation.csv", package.CANDIDATE_FIELDS
        )
        pairs = csv_rows(snapshot_dir / "pair_annotation.csv", package.PAIR_FIELDS)
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
        (row["case_id"], row["candidate_id_a"], row["candidate_id_b"])
        for row in pairs
    ] != pair_ids:
        add("pair", "all", "候选对行数、顺序、缺失或重复 ID 不符合冻结模板")

    for row in cases:
        unit = row.get("case_id", "?")
        if row.get("reviewer_id") != reviewer_id:
            add("case", unit, "reviewer_id 不符")
        if row.get("adjudication_status") != "single":
            add("case", unit, "初始 adjudication_status 必须为 single")
        if row.get("handbook_version") != package.HANDBOOK_VERSION:
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
        if row.get("handbook_version") != package.HANDBOOK_VERSION:
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
                package.validate_expected(
                    {field: row[field] for field in CANDIDATE_ENUMS}
                )
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
        if row.get("handbook_version") != package.HANDBOOK_VERSION:
            add("pair", unit, "handbook_version 不符")
        if row.get("candidate_pair_relation") not in PAIR_ENUMS["candidate_pair_relation"]:
            add("pair", unit, "candidate_pair_relation 缺失或非法")
        for field in ("evidence_locator", "rationale"):
            if not row.get(field, "").strip():
                add("pair", unit, f"{field} 为空")
        if row.get("confidence") not in CONFIDENCE:
            add("pair", unit, "confidence 缺失或非法")
    return {"case": cases, "candidate": candidates, "pair": pairs}, errors


def macro_f1(left: list[str], right: list[str]) -> float | None:
    if not left or len(left) != len(right):
        return None
    labels = sorted(set(left) | set(right))
    scores = []
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


def review_submissions(
    repo_root: Path,
    master_dir: Path,
    review_root: Path,
) -> dict[str, Any]:
    lock_check = verify_lock(repo_root, review_root)
    output_path = review_root / "mechanical_review.json"
    if output_path.exists():
        raise RuntimeError("mechanical_review.json 已存在，拒绝覆盖历史审查")

    # 锁定完成并验证后，才读取答案键。
    key_rows = read_jsonl(master_dir / "facilitator_key.jsonl")
    package.validate_cases(key_rows)
    case_ids, candidate_ids, pair_ids, expected_labels, candidate_meta = expected_indexes(
        key_rows
    )
    role_data: dict[str, dict[str, list[dict[str, str]]]] = {}
    format_errors: list[dict[str, str]] = []
    for reviewer_id, dirname in ROLE_DIRS.items():
        data, errors = validate_role(
            review_root / "locked_submissions" / dirname,
            reviewer_id,
            key_rows,
        )
        role_data[reviewer_id] = data
        format_errors.extend(errors)

    if any(not role_data[role]["candidate"] for role in ROLE_DIRS):
        report = {
            "review_version": REVIEW_VERSION,
            "reviewed_at_local": now_iso(),
            "lock_check": lock_check,
            "format_errors": format_errors,
            "provisional_gate": "FAIL_FORMAT",
        }
        write_json(output_path, report)
        return report

    by_role_candidate = {
        role: {
            (row["case_id"], row["candidate_id"]): row
            for row in role_data[role]["candidate"]
        }
        for role in ROLE_DIRS
    }
    by_role_case = {
        role: {row["case_id"]: row for row in role_data[role]["case"]}
        for role in ROLE_DIRS
    }
    by_role_pair = {
        role: {
            (row["case_id"], row["candidate_id_a"], row["candidate_id_b"]): row
            for row in role_data[role]["pair"]
        }
        for role in ROLE_DIRS
    }

    metrics: dict[str, Any] = {}
    candidate_fields = [
        "relevance_status",
        "target_relation",
        "conflict_type",
        "adjudicability",
    ]
    for field in candidate_fields:
        a = [by_role_candidate["A"][unit][field] for unit in candidate_ids]
        b = [by_role_candidate["B"][unit][field] for unit in candidate_ids]
        key = [expected_labels[unit][field] for unit in candidate_ids]
        metrics[field] = {
            "a_vs_b": agreement(a, b),
            "a_vs_key": agreement(a, key),
            "b_vs_key": agreement(b, key),
        }

    conflict_units = [
        unit
        for unit in candidate_ids
        if expected_labels[unit]["target_relation"] == "factual_conflict"
    ]
    conflict_gate_metrics: dict[str, Any] = {}
    for field in ("conflict_type", "adjudicability"):
        a = [by_role_candidate["A"][unit][field] for unit in conflict_units]
        b = [by_role_candidate["B"][unit][field] for unit in conflict_units]
        key = [expected_labels[unit][field] for unit in conflict_units]
        conflict_gate_metrics[field] = {
            "a_vs_b": agreement(a, b),
            "a_vs_key": agreement(a, key),
            "b_vs_key": agreement(b, key),
        }

    qualification = {}
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

    pair_metrics = {}
    for pair_id in pair_ids:
        a = by_role_pair["A"][pair_id]["candidate_pair_relation"]
        b = by_role_pair["B"][pair_id]["candidate_pair_relation"]
        pair_metrics["/".join(pair_id)] = {
            "a": a,
            "b": b,
            "key": "same_fact",
            "both_correct": a == b == "same_fact",
        }

    comparison_rows: list[dict[str, Any]] = []
    disagreements: list[dict[str, Any]] = []
    for unit in candidate_ids:
        base = {
            "case_id": unit[0],
            "candidate_id": unit[1],
            **candidate_meta[unit],
        }
        row = dict(base)
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
                        **base,
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

    strata = defaultdict(lambda: {"units": 0, "a_b_disagreements": 0})
    for unit in candidate_ids:
        dataset = candidate_meta[unit]["dataset_id"]
        strata[("dataset", dataset)]["units"] += 1
        if by_role_candidate["A"][unit]["target_relation"] != by_role_candidate["B"][unit]["target_relation"]:
            strata[("dataset", dataset)]["a_b_disagreements"] += 1
        conflict_type = expected_labels[unit]["conflict_type"]
        if conflict_type != "not_applicable":
            strata[("key_conflict_type", conflict_type)]["units"] += 1
            if by_role_candidate["A"][unit]["conflict_type"] != by_role_candidate["B"][unit]["conflict_type"]:
                strata[("key_conflict_type", conflict_type)]["a_b_disagreements"] += 1
    strata_rows = [
        {
            "stratum_type": key[0],
            "stratum": key[1],
            **value,
            "disagreement_rate": value["a_b_disagreements"] / value["units"],
        }
        for key, value in sorted(strata.items())
    ]

    unresolved = {}
    for role in ROLE_DIRS:
        candidate_rows = role_data[role]["candidate"]
        unresolved[role] = {
            "target_relation_unresolved": sum(
                row["target_relation"] == "unresolved" for row in candidate_rows
            ),
            "possible_false_negative": sum(
                row["relevance_status"] == "unresolved_possible_false_negative"
                for row in candidate_rows
            ),
            "qualification_unresolved": sum(
                row["target_reference_status"] == "unresolved"
                or row["target_group_status"] == "unresolved"
                for row in role_data[role]["case"]
            ),
        }

    equivalent_conflict_cross = []
    for unit in candidate_ids:
        a = by_role_candidate["A"][unit]["target_relation"]
        b = by_role_candidate["B"][unit]["target_relation"]
        if {a, b} == {"equivalent", "factual_conflict"}:
            equivalent_conflict_cross.append("/".join(unit))

    false_negative_units = [
        unit for unit in candidate_ids if candidate_meta[unit]["quota_cell"] == "possible_false_negative"
    ]
    false_negative_construct_errors = []
    for unit in false_negative_units:
        for role in ROLE_DIRS:
            row = by_role_candidate[role][unit]
            if row["target_relation"] != "equivalent" or row["relevance_status"] not in {
                "relevant_gold",
                "relevant_equivalent",
            }:
                false_negative_construct_errors.append(
                    {"unit": "/".join(unit), "reviewer_id": role, "labels": row}
                )

    evidence_only_admin_signal = []
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

    relation_gate = metrics["target_relation"]
    conflict_gate = conflict_gate_metrics["conflict_type"]
    adjudicability_gate = conflict_gate_metrics["adjudicability"]
    gate_checks = {
        "format_errors_zero": len(format_errors) == 0,
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
        "equivalent_vs_factual_conflict_cross_zero": len(equivalent_conflict_cross) == 0,
        "false_negative_construct_errors_zero": len(false_negative_construct_errors) == 0,
        "evidence_only_admin_signal_zero": len(evidence_only_admin_signal) == 0,
    }
    provisional_gate = "PASS_PENDING_FACILITATOR_ADJUDICATION" if all(
        gate_checks.values()
    ) else "FAIL_REQUIRES_FACILITATOR_DIAGNOSIS"
    if all(gate_checks.values()) and not disagreements:
        provisional_gate = "PASS_NO_DISAGREEMENT"

    review = {
        "review_version": REVIEW_VERSION,
        "reviewed_at_local": now_iso(),
        "package_version": package.PACKAGE_VERSION,
        "handbook_version": package.HANDBOOK_VERSION,
        "view_contract_version": package.VIEW_CONTRACT_VERSION,
        "submission_lock_sha256": lock_check["submission_lock_sha256"],
        "review_script_sha256": package.sha256_file(Path(__file__).resolve()),
        "format_errors": format_errors,
        "qualification": qualification,
        "candidate_metrics_all_13": metrics,
        "conflict_gate_metrics_key_9": conflict_gate_metrics,
        "pair_metrics": pair_metrics,
        "unresolved_counts": unresolved,
        "stratified_disagreement": strata_rows,
        "similarity_band_stratification": "not_available_in_P2_calibration_package",
        "zero_tolerance_audit": {
            "equivalent_conflict_cross": equivalent_conflict_cross,
            "false_negative_construct_errors": false_negative_construct_errors,
            "evidence_only_admin_signal": evidence_only_admin_signal,
        },
        "gate_checks": gate_checks,
        "disagreement_count": len(disagreements),
        "disagreements": disagreements,
        "provisional_gate": provisional_gate,
        "gate_scope": "P2 calibration only; not Gate A/B evidence",
    }
    write_json(output_path, review)

    if comparison_rows:
        fields = list(comparison_rows[0])
        with (review_root / "comparison_rows.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(comparison_rows)
    if disagreements:
        fields = list(disagreements[0])
        with (review_root / "disagreements.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(disagreements)
    else:
        (review_root / "disagreements.csv").write_text(
            "case_id,candidate_id,field,a,b,key\n", encoding="utf-8"
        )
    return review


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=("lock", "verify-lock", "review"),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--master-dir",
        type=Path,
        default=Path("data/robust_fusion/derived/p2_calibration_v2"),
    )
    parser.add_argument(
        "--work-root",
        type=Path,
        default=Path("runs/robust_fusion/p2_human_calibration_v2"),
    )
    parser.add_argument(
        "--review-root",
        type=Path,
        default=Path("runs/robust_fusion/p2_human_calibration_v2/facilitator_review"),
    )
    return parser.parse_args()


def resolve(repo_root: Path, path: Path) -> Path:
    return (path if path.is_absolute() else repo_root / path).resolve()


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
