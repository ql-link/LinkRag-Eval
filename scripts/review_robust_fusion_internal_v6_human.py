#!/usr/bin/env python3
"""锁定并审查 Internal Stress v6 Dev 的 A/B 双人盲标提交。"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.internal_v6_pilot import HANDBOOK_VERSION, sha256_file
from linkrag_eval.robust_fusion.internal_v6_review import (
    CANDIDATE_FIELDS,
    CASE_FIELDS,
    PAIR_FIELDS,
    REVIEW_PACKAGE_VERSION,
    VIEW_CONTRACT_VERSION,
)

LOCK_VERSION = "ROBUST-FUSION-INTERNAL-V6-SUBMISSION-LOCK-2026-08-29-v1"
REVIEW_VERSION = "ROBUST-FUSION-INTERNAL-V6-DOUBLE-REVIEW-2026-08-29-v2"
FINAL_VERSION = "ROBUST-FUSION-INTERNAL-V6-FACILITATOR-DECISION-2026-08-29-v1"
ROLE_DIRS = {"A": "annotator_a", "B": "annotator_b"}
ANSWER_FILES = (
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
        "unresolved",
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
        "not_annotated",
        "same_fact",
        "factual_conflict",
        "insufficient_context",
        "unresolved",
    }
}
CONFIDENCE = {"high", "medium", "low"}
CLASSIFICATION_FIELDS = {
    "case": ("target_reference_status", "target_group_status"),
    "candidate": (
        "relevance_status",
        "target_relation",
        "conflict_type",
        "adjudicability",
    ),
    "pair": ("candidate_pair_relation",),
}
PAIR_ADJUDICATIONS = {
    ("RF-V6HR-2A5D398D4D", "C1", "C3"): {
        "candidate_pair_relation": "factual_conflict",
        "evidence_locator": (
            "C1“样品入库时的温度条件为零下四十摄氏度”；"
            "C3“所有待入库的样品必须在零下四十摄氏度的环境中完成预冷与转移，"
            "但该规定仅适用于常规样品，特殊样品需单独审批”"
        ),
        "rationale": (
            "C1 无条件陈述样品入库温度为零下四十摄氏度；C3 同时声称适用于“所有”"
            "样品，又把适用范围限为常规样品，并对特殊样品改为单独审批。按手册第 5 节，"
            "决定答案成立范围的条件不相容，候选对最终判 factual_conflict。"
        ),
        "confidence": "medium",
        "handbook_clause": "标注手册第 5 节候选对关系；第 9.2/全量指南第 14.2 节仲裁顺序",
    }
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    path.chmod(0o600)


def file_meta(path: Path) -> dict[str, Any]:
    stat = path.lstat()
    return {
        "size_bytes": stat.st_size,
        "mtime_local": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
        "sha256": sha256_file(path),
        "regular_file": path.is_file(),
        "symlink": path.is_symlink(),
    }


def repo_relative(repo_root: Path, path: Path) -> str:
    return path.resolve().relative_to(repo_root).as_posix()


def resolve_in_repo(repo_root: Path, path: Path) -> Path:
    resolved = (path if path.is_absolute() else repo_root / path).resolve()
    if not resolved.is_relative_to(repo_root):
        raise RuntimeError(f"路径必须位于仓库内：{resolved}")
    return resolved


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def read_csv(path: Path, expected_fields: list[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        rows = list(reader)
    if fields != expected_fields:
        raise ValueError(f"表头不符：{path}；实际={fields}")
    return rows


def verify_delivery_inputs(work_root: Path) -> dict[str, Any]:
    manifest_path = work_root / "delivery_manifest.json"
    manifest_hash = sha256_file(manifest_path)
    recorded = (work_root / "delivery_manifest.sha256").read_text(encoding="utf-8").strip()
    if recorded.split()[0] != manifest_hash:
        raise RuntimeError("空白交付 manifest 的 SHA-256 回执不匹配")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("package_version") != REVIEW_PACKAGE_VERSION:
        raise RuntimeError("人工包版本不符")

    answer_paths = {
        f"{dirname}/{filename}"
        for dirname in ROLE_DIRS.values()
        for filename in ANSWER_FILES
    }
    static_rows: list[dict[str, Any]] = []
    answer_rows: list[dict[str, Any]] = []
    for expected in manifest["files"]:
        relative = expected["path"]
        path = work_root / relative
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"交付文件缺失或不是普通文件：{relative}")
        actual = file_meta(path)
        row = {"path": relative, "delivery": expected, "current": actual}
        if relative in answer_paths:
            row["changed_from_blank_delivery"] = (
                actual["sha256"] != expected["sha256"]
                or actual["size_bytes"] != expected["size_bytes"]
            )
            answer_rows.append(row)
        else:
            if (
                actual["sha256"] != expected["sha256"]
                or actual["size_bytes"] != expected["size_bytes"]
            ):
                raise RuntimeError(f"冻结的非答案输入发生变化：{relative}")
            static_rows.append(row)
    if len(answer_rows) != 6:
        raise RuntimeError("交付 manifest 中的答案文件数量不为六")
    if not all(row["changed_from_blank_delivery"] for row in answer_rows):
        unchanged = [row["path"] for row in answer_rows if not row["changed_from_blank_delivery"]]
        raise RuntimeError(f"仍有空白答案文件：{unchanged}")
    return {
        "delivery_manifest_sha256": manifest_hash,
        "static_file_count": len(static_rows),
        "static_files_unchanged": True,
        "answer_files_changed_from_blank_count": sum(
            row["changed_from_blank_delivery"] for row in answer_rows
        ),
        "answer_files": answer_rows,
    }


def _copy_locked(source: Path, destination: Path) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.parent.chmod(0o700)
    shutil.copyfile(source, destination)
    destination.chmod(0o400)
    source_meta = file_meta(source)
    destination_meta = file_meta(destination)
    if (
        source_meta["sha256"] != destination_meta["sha256"]
        or source_meta["size_bytes"] != destination_meta["size_bytes"]
    ):
        raise RuntimeError(f"锁定副本与源文件不一致：{source}")
    return {"source": source_meta, "snapshot": destination_meta}


def lock_submissions(repo_root: Path, work_root: Path, review_root: Path) -> dict[str, Any]:
    if review_root.exists():
        raise RuntimeError(f"主持人审查目录已存在，拒绝覆盖：{review_root}")
    binding = verify_delivery_inputs(work_root)
    review_root.mkdir(parents=True, mode=0o700)
    review_root.chmod(0o700)

    answer_rows: list[dict[str, Any]] = []
    for reviewer_id, dirname in ROLE_DIRS.items():
        for filename in ANSWER_FILES:
            source = work_root / dirname / filename
            if not source.is_file() or source.is_symlink():
                raise RuntimeError(f"提交不是普通文件：{source}")
            destination = review_root / "locked_submissions" / dirname / filename
            copied = _copy_locked(source, destination)
            answer_rows.append(
                {
                    "reviewer_id": reviewer_id,
                    "filename": filename,
                    "source_path": repo_relative(repo_root, source),
                    "snapshot_path": repo_relative(repo_root, destination),
                    **copied,
                }
            )

    frozen_paths = [
        "delivery_manifest.json",
        "delivery_manifest.sha256",
        "package_report.json",
        "README.md",
        "annotator_a/annotation_cases.jsonl",
        "annotator_a/标注说明.md",
        "annotator_b/annotation_cases.jsonl",
        "annotator_b/标注说明.md",
        "facilitator/blind_mapping.jsonl",
        "facilitator/selected_proposals.jsonl",
        "facilitator/exposure_audit.json",
        "facilitator/run_chain_audit.json",
    ]
    frozen_rows: list[dict[str, Any]] = []
    for relative in frozen_paths:
        source = work_root / relative
        destination = review_root / "frozen_inputs" / relative
        copied = _copy_locked(source, destination)
        frozen_rows.append(
            {
                "source_path": repo_relative(repo_root, source),
                "snapshot_path": repo_relative(repo_root, destination),
                **copied,
            }
        )

    locked_at = now_iso()
    lock = {
        "lock_version": LOCK_VERSION,
        "package_version": REVIEW_PACKAGE_VERSION,
        "handbook_version": HANDBOOK_VERSION,
        "view_contract_version": VIEW_CONTRACT_VERSION,
        "locked_at_local": locked_at,
        "delivery_binding": binding,
        "answer_snapshots": answer_rows,
        "frozen_input_snapshots": frozen_rows,
        "review_must_use_snapshots": True,
        "submission_content_parsed_before_lock_by_this_review": False,
        "submissions_compared_before_lock_by_this_review": False,
        "facilitator_mapping_parsed_before_lock_by_this_review": False,
        "facilitator_created_package_and_mapping_before_lock": True,
        "facilitator_blindness_claimed": False,
        "annotator_independence_claim": (
            "A/B 使用相互隔离、无构造角色与答案键的盲化目录；本锁只证明先锁后比，"
            "不把主持人描述为盲态。"
        ),
    }
    write_json(review_root / "submission_lock.json", lock)
    lock_hash = sha256_file(review_root / "submission_lock.json")
    (review_root / "submission_lock.sha256").write_text(
        f"{lock_hash}  submission_lock.json\n", encoding="utf-8"
    )
    (review_root / "submission_lock.sha256").chmod(0o400)
    (review_root / "README.md").write_text(
        "# Internal Stress v6 Dev 主持人审查\n\n"
        f"- 提交锁版本：`{LOCK_VERSION}`\n"
        f"- 锁定时间：`{locked_at}`\n"
        "- 后续机械校验、比较和仲裁只能读取 `locked_submissions/` 与 `frozen_inputs/`。\n"
        "- 空白交付 manifest 保持不变；人工填写后的六份 CSV 由本目录另行锁定。\n"
        "- 本记录只主张 A/B 独立盲标与先锁后比，不主张主持人盲态。\n",
        encoding="utf-8",
    )
    (review_root / "README.md").chmod(0o600)
    return {
        "status": "LOCKED",
        "lock_version": LOCK_VERSION,
        "locked_at_local": locked_at,
        "submission_lock_sha256": lock_hash,
        "answer_snapshot_count": len(answer_rows),
        "frozen_input_snapshot_count": len(frozen_rows),
        "static_files_unchanged": binding["static_files_unchanged"],
        "review_root": repo_relative(repo_root, review_root),
    }


def verify_lock(repo_root: Path, review_root: Path) -> dict[str, Any]:
    lock_path = review_root / "submission_lock.json"
    digest = sha256_file(lock_path)
    expected = f"{digest}  submission_lock.json\n"
    if (review_root / "submission_lock.sha256").read_text(encoding="utf-8") != expected:
        raise RuntimeError("submission_lock.sha256 不匹配")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("lock_version") != LOCK_VERSION:
        raise RuntimeError("提交锁版本不符")
    if lock.get("submission_content_parsed_before_lock_by_this_review") is not False:
        raise RuntimeError("提交锁中的先锁后读声明不合法")
    if lock.get("submissions_compared_before_lock_by_this_review") is not False:
        raise RuntimeError("提交锁中的先锁后比声明不合法")
    snapshots = lock["answer_snapshots"] + lock["frozen_input_snapshots"]
    for row in snapshots:
        path = repo_root / row["snapshot_path"]
        current = file_meta(path)
        expected_meta = row["snapshot"]
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"锁定副本不是普通文件：{path}")
        if (
            current["sha256"] != expected_meta["sha256"]
            or current["size_bytes"] != expected_meta["size_bytes"]
        ):
            raise RuntimeError(f"锁定副本发生变化：{path}")
    return {
        "status": "PASS",
        "submission_lock_sha256": digest,
        "answer_snapshot_count": len(lock["answer_snapshots"]),
        "frozen_input_snapshot_count": len(lock["frozen_input_snapshots"]),
        "locked_at_local": lock["locked_at_local"],
    }


def expected_orders(cases: list[dict[str, Any]]) -> dict[str, list[Any]]:
    case_ids: list[str] = []
    candidate_ids: list[tuple[str, str]] = []
    pair_ids: list[tuple[str, str, str]] = []
    for case in cases:
        case_id = case["case_id"]
        case_ids.append(case_id)
        aliases = sorted(candidate["candidate_id"] for candidate in case["candidates"])
        candidate_ids.extend((case_id, alias) for alias in aliases)
        pair_ids.extend(
            (case_id, aliases[left], aliases[right])
            for left in range(len(aliases))
            for right in range(left + 1, len(aliases))
        )
    return {"case": case_ids, "candidate": candidate_ids, "pair": pair_ids}


def validate_candidate_combination(row: dict[str, str]) -> str | None:
    relation = row["target_relation"]
    relevance = row["relevance_status"]
    conflict = row["conflict_type"]
    adjudicability = row["adjudicability"]
    if relation == "equivalent":
        legal = (
            relevance in {"relevant_gold", "relevant_equivalent"}
            and conflict == "not_applicable"
            and adjudicability == "not_applicable"
        )
    elif relation == "factual_conflict":
        legal = (
            relevance == "verified_incorrect_distractor"
            and conflict
            in {
                "version_or_time",
                "numeric",
                "negation_or_direction",
                "applicability_or_condition",
            }
            and adjudicability
            in {"detectable_only", "conditionally_adjudicable", "unidentifiable"}
        )
    elif relation == "other_incorrect":
        legal = (
            relevance == "verified_incorrect_distractor"
            and conflict == "not_applicable"
            and adjudicability == "not_applicable"
        )
    else:
        legal = (
            relevance == "unresolved_possible_false_negative"
            and conflict == "not_applicable"
            and adjudicability == "not_applicable"
        )
    return None if legal else "候选四字段组合不符合手册第 8 节"


def _quoted_spans(value: str) -> list[str]:
    spans = re.findall(r"“([^”]+)”|\"([^\"]+)\"|'([^']+)'", value)
    return [next(item for item in group if item).strip() for group in spans]


def validate_evidence_locator(
    locator: str, allowed_texts: list[str]
) -> tuple[list[str], list[str]]:
    if not locator.strip():
        return ["evidence_locator 为空"], []
    spans = [span for span in _quoted_spans(locator) if len(span) >= 2]
    if not spans:
        return ["evidence_locator 未提供可逐字核对的引号片段"], []
    missing: list[str] = []
    for span in spans:
        # 允许用省略号连接同一原文中的多个逐字片段；省略号本身不是正文。
        fragments = [
            fragment.strip(" ，；：、")
            for fragment in re.split(r"(?:…{2,}|\.{3,})", span)
            if len(fragment.strip(" ，；：、")) >= 2
        ]
        if not fragments or any(
            not any(fragment in text for text in allowed_texts) for fragment in fragments
        ):
            missing.append(span)
    warnings = [
        f"evidence_locator 可定位但引号片段不是完全逐字引用，需主持人规范化：{span}"
        for span in missing
    ]
    return [], warnings


def validate_role(
    snapshot_dir: Path,
    cases: list[dict[str, Any]],
    reviewer_id: str,
) -> tuple[
    dict[str, list[dict[str, str]]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    orders = expected_orders(cases)
    case_by_id = {case["case_id"]: case for case in cases}

    try:
        data = {
            "case": read_csv(snapshot_dir / ANSWER_FILES[0], CASE_FIELDS),
            "candidate": read_csv(snapshot_dir / ANSWER_FILES[1], CANDIDATE_FIELDS),
            "pair": read_csv(snapshot_dir / ANSWER_FILES[2], PAIR_FIELDS),
        }
    except ValueError as exc:
        return (
            {"case": [], "candidate": [], "pair": []},
            [
                {
                    "reviewer_id": reviewer_id,
                    "scope": "file",
                    "unit": "all",
                    "error": str(exc),
                }
            ],
            [],
        )

    def add(scope: str, unit: str, error: str) -> None:
        errors.append(
            {"reviewer_id": reviewer_id, "scope": scope, "unit": unit, "error": error}
        )

    def warn(scope: str, unit: str, warning: str) -> None:
        warnings.append(
            {
                "reviewer_id": reviewer_id,
                "scope": scope,
                "unit": unit,
                "warning": warning,
            }
        )

    observed_orders = {
        "case": [row["case_id"] for row in data["case"]],
        "candidate": [
            (row["case_id"], row["candidate_id"]) for row in data["candidate"]
        ],
        "pair": [
            (row["case_id"], row["candidate_id_a"], row["candidate_id_b"])
            for row in data["pair"]
        ],
    }
    for scope in ("case", "candidate", "pair"):
        if observed_orders[scope] != orders[scope]:
            add(scope, "all", "行数、ID、顺序、缺失或重复项不符合冻结模板")

    for row in data["case"]:
        unit = row.get("case_id", "?")
        case = case_by_id.get(unit)
        if row.get("reviewer_id") != reviewer_id:
            add("case", unit, "reviewer_id 不符")
        if row.get("adjudication_status") != "single":
            add("case", unit, "初始 adjudication_status 必须为 single")
        if row.get("handbook_version") != HANDBOOK_VERSION:
            add("case", unit, "handbook_version 不符")
        for field, legal in QUALIFICATION_ENUMS.items():
            if row.get(field) not in legal:
                add("case", unit, f"{field} 缺失或非法：{row.get(field)!r}")
        if not row.get("rationale", "").strip():
            add("case", unit, "rationale 为空")
        if row.get("confidence") not in CONFIDENCE:
            add("case", unit, "confidence 缺失或非法")
        if case:
            allowed = [case["query_text"]] + [
                item["display_text"] for item in case["target_references"]
            ]
            evidence_errors, evidence_warnings = validate_evidence_locator(
                row.get("evidence_locator", ""), allowed
            )
            for error in evidence_errors:
                add("case", unit, error)
            for warning in evidence_warnings:
                warn("case", unit, warning)

    for row in data["candidate"]:
        case_id = row.get("case_id", "?")
        candidate_id = row.get("candidate_id", "?")
        unit = f"{case_id}/{candidate_id}"
        case = case_by_id.get(case_id)
        if row.get("reviewer_id") != reviewer_id:
            add("candidate", unit, "reviewer_id 不符")
        if row.get("adjudication_status") != "single":
            add("candidate", unit, "初始 adjudication_status 必须为 single")
        if row.get("handbook_version") != HANDBOOK_VERSION:
            add("candidate", unit, "handbook_version 不符")
        enums_ok = True
        for field, legal in CANDIDATE_ENUMS.items():
            if row.get(field) not in legal:
                add("candidate", unit, f"{field} 缺失或非法：{row.get(field)!r}")
                enums_ok = False
        if enums_ok:
            combination_error = validate_candidate_combination(row)
            if combination_error:
                add("candidate", unit, combination_error)
        if not row.get("rationale", "").strip():
            add("candidate", unit, "rationale 为空")
        if row.get("confidence") not in CONFIDENCE:
            add("candidate", unit, "confidence 缺失或非法")
        if case:
            candidates = {item["candidate_id"]: item for item in case["candidates"]}
            candidate = candidates.get(candidate_id)
            if candidate:
                allowed = [case["query_text"], candidate["display_text"]] + [
                    item["display_text"] for item in case["target_references"]
                ]
                evidence_errors, evidence_warnings = validate_evidence_locator(
                    row.get("evidence_locator", ""), allowed
                )
                for error in evidence_errors:
                    add("candidate", unit, error)
                for warning in evidence_warnings:
                    warn("candidate", unit, warning)

    for row in data["pair"]:
        case_id = row.get("case_id", "?")
        candidate_a = row.get("candidate_id_a", "?")
        candidate_b = row.get("candidate_id_b", "?")
        unit = f"{case_id}/{candidate_a}-{candidate_b}"
        case = case_by_id.get(case_id)
        if row.get("reviewer_id") != reviewer_id:
            add("pair", unit, "reviewer_id 不符")
        if row.get("adjudication_status") != "single":
            add("pair", unit, "初始 adjudication_status 必须为 single")
        if row.get("handbook_version") != HANDBOOK_VERSION:
            add("pair", unit, "handbook_version 不符")
        if row.get("candidate_pair_relation") not in PAIR_ENUMS["candidate_pair_relation"]:
            add("pair", unit, "candidate_pair_relation 缺失或非法")
        if not row.get("rationale", "").strip():
            add("pair", unit, "rationale 为空")
        if row.get("confidence") not in CONFIDENCE:
            add("pair", unit, "confidence 缺失或非法")
        if case:
            candidates = {item["candidate_id"]: item for item in case["candidates"]}
            if candidate_a in candidates and candidate_b in candidates:
                allowed = [
                    case["query_text"],
                    candidates[candidate_a]["display_text"],
                    candidates[candidate_b]["display_text"],
                ]
                evidence_errors, evidence_warnings = validate_evidence_locator(
                    row.get("evidence_locator", ""), allowed
                )
                for error in evidence_errors:
                    add("pair", unit, error)
                for warning in evidence_warnings:
                    warn("pair", unit, warning)
    return data, errors, warnings


def macro_f1(left: list[str], right: list[str]) -> float | None:
    if not left or len(left) != len(right):
        return None
    scores: list[float] = []
    for label in sorted(set(left) | set(right)):
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
    expected = 1 - sum(count * (count - 1) for count in counts.values()) / (
        total * (total - 1)
    )
    if math.isclose(expected, 0.0):
        return 1.0 if math.isclose(observed, 0.0) else None
    return 1 - observed / expected


def cohens_kappa(left: list[str], right: list[str]) -> float | None:
    if not left or len(left) != len(right):
        return None
    observed = sum(a == b for a, b in zip(left, right, strict=True)) / len(left)
    left_counts = Counter(left)
    right_counts = Counter(right)
    expected = sum(
        left_counts[label] / len(left) * right_counts[label] / len(right)
        for label in set(left_counts) | set(right_counts)
    )
    if math.isclose(expected, 1.0):
        return 1.0 if math.isclose(observed, 1.0) else None
    return (observed - expected) / (1 - expected)


def agreement(left: list[str], right: list[str]) -> dict[str, Any]:
    matches = sum(a == b for a, b in zip(left, right, strict=True))
    return {
        "matches": matches,
        "total": len(left),
        "rate": matches / len(left) if left else None,
        "macro_f1": macro_f1(left, right),
        "krippendorff_alpha_nominal": krippendorff_alpha_nominal(left, right),
        "cohens_kappa": cohens_kappa(left, right),
    }


def index_rows(data: dict[str, list[dict[str, str]]]) -> dict[str, dict[Any, dict[str, str]]]:
    return {
        "case": {row["case_id"]: row for row in data["case"]},
        "candidate": {
            (row["case_id"], row["candidate_id"]): row for row in data["candidate"]
        },
        "pair": {
            (row["case_id"], row["candidate_id_a"], row["candidate_id_b"]): row
            for row in data["pair"]
        },
    }


def construction_index(mapping_rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for row in mapping_rows:
        unit = (row["case_id"], row["candidate_id"])
        role = row["construction_role"]
        if role == "equivalent":
            intended = {
                "relevance_status": "relevant_equivalent",
                "target_relation": "equivalent",
                "conflict_type": "not_applicable",
            }
        elif role == "conflict":
            intended = {
                "relevance_status": "verified_incorrect_distractor",
                "target_relation": "factual_conflict",
                "conflict_type": row["primary_conflict_type_proposal"],
            }
        elif role == "surface_control":
            intended = {
                "relevance_status": "verified_incorrect_distractor",
                "target_relation": "other_incorrect",
                "conflict_type": "not_applicable",
            }
        else:
            raise RuntimeError(f"未知 construction_role：{role}")
        index[unit] = {**row, "intended": intended}
    return index


def review_submissions(
    repo_root: Path,
    review_root: Path,
    analysis_root: Path,
) -> dict[str, Any]:
    lock_check = verify_lock(repo_root, review_root)
    if analysis_root.exists():
        raise RuntimeError(f"分析目录已存在，拒绝覆盖历史审查：{analysis_root}")
    analysis_root.mkdir(parents=True, mode=0o700)
    analysis_root.chmod(0o700)
    summary_path = analysis_root / "review_summary.json"

    role_data: dict[str, dict[str, list[dict[str, str]]]] = {}
    cases_by_role: dict[str, list[dict[str, Any]]] = {}
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    for reviewer_id, dirname in ROLE_DIRS.items():
        cases = read_jsonl(review_root / "frozen_inputs" / dirname / "annotation_cases.jsonl")
        cases_by_role[reviewer_id] = cases
        data, role_errors, role_warnings = validate_role(
            review_root / "locked_submissions" / dirname,
            cases,
            reviewer_id,
        )
        role_data[reviewer_id] = data
        errors.extend(role_errors)
        warnings.extend(role_warnings)

    mechanical = {
        "review_version": REVIEW_VERSION,
        "reviewed_at_local": now_iso(),
        "submission_lock_sha256": lock_check["submission_lock_sha256"],
        "review_script_sha256": sha256_file(Path(__file__).resolve()),
        "errors": errors,
        "error_count": len(errors),
        "warnings": warnings,
        "warning_count": len(warnings),
        "status": "PASS" if not errors else "FAIL",
    }
    write_json(analysis_root / "mechanical_validation.json", mechanical)
    if errors:
        summary = {
            "review_version": REVIEW_VERSION,
            "status": "BLOCKED_MECHANICAL_VALIDATION",
            "submission_lock_sha256": lock_check["submission_lock_sha256"],
            "mechanical_error_count": len(errors),
            "mechanical_warning_count": len(warnings),
            "gate_eligibility": "NOT_ELIGIBLE",
        }
        write_json(summary_path, summary)
        return summary

    indexes = {role: index_rows(data) for role, data in role_data.items()}
    a_orders = expected_orders(cases_by_role["A"])
    b_orders = expected_orders(cases_by_role["B"])
    if set(a_orders["case"]) != set(b_orders["case"]):
        raise RuntimeError("A/B case ID 集合不一致")
    if set(a_orders["candidate"]) != set(b_orders["candidate"]):
        raise RuntimeError("A/B candidate ID 集合不一致")
    if set(a_orders["pair"]) != set(b_orders["pair"]):
        raise RuntimeError("A/B pair ID 集合不一致")

    mapping_rows = read_jsonl(
        review_root / "frozen_inputs" / "facilitator" / "blind_mapping.jsonl"
    )
    construction = construction_index(mapping_rows)
    if set(construction) != set(a_orders["candidate"]):
        raise RuntimeError("构造映射与候选 ID 集合不一致")

    units = {
        "case": sorted(a_orders["case"]),
        "candidate": sorted(a_orders["candidate"]),
        "pair": sorted(a_orders["pair"]),
    }
    metrics: dict[str, Any] = {}
    disagreements: list[dict[str, Any]] = []
    for scope, fields in CLASSIFICATION_FIELDS.items():
        metrics[scope] = {}
        for field in fields:
            left = [indexes["A"][scope][unit][field] for unit in units[scope]]
            right = [indexes["B"][scope][unit][field] for unit in units[scope]]
            metrics[scope][field] = agreement(left, right)
            for unit, a_value, b_value in zip(units[scope], left, right, strict=True):
                if a_value == b_value:
                    continue
                unit_text = unit if isinstance(unit, str) else "/".join(unit)
                row: dict[str, Any] = {
                    "scope": scope,
                    "unit": unit_text,
                    "field": field,
                    "a": a_value,
                    "b": b_value,
                    "a_evidence_locator": indexes["A"][scope][unit]["evidence_locator"],
                    "b_evidence_locator": indexes["B"][scope][unit]["evidence_locator"],
                    "a_rationale": indexes["A"][scope][unit]["rationale"],
                    "b_rationale": indexes["B"][scope][unit]["rationale"],
                }
                if scope == "candidate":
                    row["construction_role"] = construction[unit]["construction_role"]
                    row["proposal_conflict_type"] = construction[unit][
                        "primary_conflict_type_proposal"
                    ]
                disagreements.append(row)

    construction_rows: list[dict[str, Any]] = []
    deviations: list[dict[str, Any]] = []
    for unit in units["candidate"]:
        meta = construction[unit]
        row: dict[str, Any] = {
            "case_id": unit[0],
            "candidate_id": unit[1],
            "construction_role": meta["construction_role"],
            "proposal_conflict_type": meta["primary_conflict_type_proposal"],
        }
        for field, intended in meta["intended"].items():
            row[f"intended_{field}"] = intended
            for role in ROLE_DIRS:
                actual = indexes[role]["candidate"][unit][field]
                row[f"{role.lower()}_{field}"] = actual
                row[f"{role.lower()}_{field}_aligned"] = actual == intended
                if actual != intended:
                    deviations.append(
                        {
                            "case_id": unit[0],
                            "candidate_id": unit[1],
                            "reviewer_id": role,
                            "construction_role": meta["construction_role"],
                            "field": field,
                            "intended": intended,
                            "actual": actual,
                            "evidence_locator": indexes[role]["candidate"][unit][
                                "evidence_locator"
                            ],
                            "rationale": indexes[role]["candidate"][unit]["rationale"],
                        }
                    )
        construction_rows.append(row)

    unresolved_counts: dict[str, Any] = {}
    for role in ROLE_DIRS:
        unresolved_counts[role] = {
            "case_reference": sum(
                row["target_reference_status"] == "unresolved"
                for row in role_data[role]["case"]
            ),
            "case_group": sum(
                row["target_group_status"] == "unresolved"
                for row in role_data[role]["case"]
            ),
            "candidate_relation": sum(
                row["target_relation"] == "unresolved"
                for row in role_data[role]["candidate"]
            ),
            "pair_relation": sum(
                row["candidate_pair_relation"] == "unresolved"
                for row in role_data[role]["pair"]
            ),
        }

    agreement_report = {
        "review_version": REVIEW_VERSION,
        "metrics": metrics,
        "disagreement_count": len(disagreements),
        "construction_deviation_count": len(deviations),
        "unresolved_counts": unresolved_counts,
        "construction_alignment_is_not_human_truth": True,
        "gate_scope": "Internal Stress v6 Dev 构造率先导；不是 Gate A/B 证据",
    }
    write_json(analysis_root / "agreement_report.json", agreement_report)

    disagreement_fields = [
        "scope",
        "unit",
        "field",
        "a",
        "b",
        "construction_role",
        "proposal_conflict_type",
        "a_evidence_locator",
        "b_evidence_locator",
        "a_rationale",
        "b_rationale",
    ]
    write_csv(analysis_root / "disagreements.csv", disagreements, disagreement_fields)
    construction_fields = list(construction_rows[0])
    write_csv(
        analysis_root / "construction_alignment.csv",
        construction_rows,
        construction_fields,
    )
    deviation_fields = [
        "case_id",
        "candidate_id",
        "reviewer_id",
        "construction_role",
        "field",
        "intended",
        "actual",
        "evidence_locator",
        "rationale",
    ]
    write_csv(analysis_root / "construction_deviations.csv", deviations, deviation_fields)

    status = (
        "PENDING_FACILITATOR_ADJUDICATION"
        if disagreements or deviations
        else "READY_FOR_FINAL_ACCEPTANCE_REVIEW"
    )
    summary = {
        "review_version": REVIEW_VERSION,
        "status": status,
        "reviewed_at_local": now_iso(),
        "submission_lock_sha256": lock_check["submission_lock_sha256"],
        "mechanical_validation": "PASS",
        "mechanical_error_count": 0,
        "mechanical_warning_count": len(warnings),
        "case_count": len(units["case"]),
        "candidate_count": len(units["candidate"]),
        "pair_count": len(units["pair"]),
        "disagreement_count": len(disagreements),
        "construction_deviation_count": len(deviations),
        "unresolved_counts": unresolved_counts,
        "human_truth_status": "PENDING_FACILITATOR_ADJUDICATION",
        "accepted_family_count": None,
        "gate_eligibility": "NOT_ELIGIBLE",
        "gate_a_executed": False,
        "gate_b_executed": False,
    }
    write_json(summary_path, summary)
    return summary


def conservative_confidence(left: str, right: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    return left if order[left] <= order[right] else right


def _final_agreed_row(
    left: dict[str, str],
    right: dict[str, str],
    fields: tuple[str, ...],
) -> dict[str, str]:
    disagreements = [field for field in fields if left[field] != right[field]]
    if disagreements:
        raise RuntimeError(f"存在未声明的 A/B 分歧：{disagreements}")
    return {
        **left,
        "reviewer_id": "FACILITATOR",
        "rationale": f"A/B 独立同标签；主持人复核：{left['rationale']}",
        "confidence": conservative_confidence(left["confidence"], right["confidence"]),
        "adjudication_status": "agreed",
    }


def _load_finalization_inputs(
    review_root: Path,
) -> tuple[
    dict[str, list[dict[str, Any]]],
    dict[str, dict[str, list[dict[str, str]]]],
    list[dict[str, Any]],
]:
    cases_by_role: dict[str, list[dict[str, Any]]] = {}
    role_data: dict[str, dict[str, list[dict[str, str]]]] = {}
    for reviewer_id, dirname in ROLE_DIRS.items():
        cases = read_jsonl(review_root / "frozen_inputs" / dirname / "annotation_cases.jsonl")
        data, errors, _warnings = validate_role(
            review_root / "locked_submissions" / dirname,
            cases,
            reviewer_id,
        )
        if errors:
            raise RuntimeError(f"{reviewer_id} 仍有机械错误，不能最终化：{errors}")
        cases_by_role[reviewer_id] = cases
        role_data[reviewer_id] = data
    mapping_rows = read_jsonl(
        review_root / "frozen_inputs" / "facilitator" / "blind_mapping.jsonl"
    )
    return cases_by_role, role_data, mapping_rows


def _validate_final_rows(
    cases: list[dict[str, Any]],
    final_data: dict[str, list[dict[str, str]]],
) -> list[str]:
    errors: list[str] = []
    orders = expected_orders(cases)
    observed = {
        "case": [row["case_id"] for row in final_data["case"]],
        "candidate": [
            (row["case_id"], row["candidate_id"]) for row in final_data["candidate"]
        ],
        "pair": [
            (row["case_id"], row["candidate_id_a"], row["candidate_id_b"])
            for row in final_data["pair"]
        ],
    }
    case_by_id = {case["case_id"]: case for case in cases}
    for scope, observed_units in observed.items():
        if observed_units != orders[scope]:
            errors.append(f"{scope} 最终行顺序或 ID 不符")
    for scope, rows in final_data.items():
        for row in rows:
            if row["reviewer_id"] != "FACILITATOR":
                errors.append(f"{scope} reviewer_id 不是 FACILITATOR")
            if row["adjudication_status"] not in {"agreed", "adjudicated"}:
                errors.append(f"{scope} adjudication_status 非最终状态")
            if row["handbook_version"] != HANDBOOK_VERSION:
                errors.append(f"{scope} handbook_version 不符")
    for row in final_data["candidate"]:
        if validate_candidate_combination(row):
            errors.append(f"{row['case_id']}/{row['candidate_id']} 最终候选组合非法")

    for row in final_data["case"]:
        case = case_by_id[row["case_id"]]
        allowed = [case["query_text"]] + [
            item["display_text"] for item in case["target_references"]
        ]
        locator_errors, locator_warnings = validate_evidence_locator(
            row["evidence_locator"], allowed
        )
        errors.extend(locator_errors + locator_warnings)
    for row in final_data["candidate"]:
        case = case_by_id[row["case_id"]]
        candidate = {
            item["candidate_id"]: item for item in case["candidates"]
        }[row["candidate_id"]]
        allowed = [case["query_text"], candidate["display_text"]] + [
            item["display_text"] for item in case["target_references"]
        ]
        locator_errors, locator_warnings = validate_evidence_locator(
            row["evidence_locator"], allowed
        )
        errors.extend(locator_errors + locator_warnings)
    for row in final_data["pair"]:
        case = case_by_id[row["case_id"]]
        candidates = {item["candidate_id"]: item for item in case["candidates"]}
        allowed = [
            case["query_text"],
            candidates[row["candidate_id_a"]]["display_text"],
            candidates[row["candidate_id_b"]]["display_text"],
        ]
        locator_errors, locator_warnings = validate_evidence_locator(
            row["evidence_locator"], allowed
        )
        errors.extend(locator_errors + locator_warnings)
    return errors


def finalize_submissions(
    repo_root: Path,
    review_root: Path,
    analysis_root: Path,
    final_root: Path,
) -> dict[str, Any]:
    lock_check = verify_lock(repo_root, review_root)
    if final_root.exists():
        raise RuntimeError(f"最终裁定目录已存在，拒绝覆盖：{final_root}")
    analysis = json.loads((analysis_root / "review_summary.json").read_text(encoding="utf-8"))
    if analysis.get("review_version") != REVIEW_VERSION:
        raise RuntimeError("分析版本不是当前冻结版本")
    if analysis.get("mechanical_validation") != "PASS":
        raise RuntimeError("机械校验未通过，不能最终化")

    cases_by_role, role_data, mapping_rows = _load_finalization_inputs(review_root)
    indexes = {role: index_rows(data) for role, data in role_data.items()}
    orders = expected_orders(cases_by_role["A"])
    final_data: dict[str, list[dict[str, str]]] = {"case": [], "candidate": [], "pair": []}
    adjudication_ledger: list[dict[str, Any]] = []

    for case_id in orders["case"]:
        final_data["case"].append(
            _final_agreed_row(
                indexes["A"]["case"][case_id],
                indexes["B"]["case"][case_id],
                CLASSIFICATION_FIELDS["case"],
            )
        )
    for unit in orders["candidate"]:
        final_data["candidate"].append(
            _final_agreed_row(
                indexes["A"]["candidate"][unit],
                indexes["B"]["candidate"][unit],
                CLASSIFICATION_FIELDS["candidate"],
            )
        )
    for unit in orders["pair"]:
        left = indexes["A"]["pair"][unit]
        right = indexes["B"]["pair"][unit]
        if unit in PAIR_ADJUDICATIONS:
            decision = PAIR_ADJUDICATIONS[unit]
            final = {
                **left,
                "reviewer_id": "FACILITATOR",
                "candidate_pair_relation": decision["candidate_pair_relation"],
                "evidence_locator": decision["evidence_locator"],
                "rationale": decision["rationale"],
                "confidence": decision["confidence"],
                "adjudication_status": "adjudicated",
            }
            adjudication_ledger.append(
                {
                    "scope": "pair",
                    "unit": "/".join(unit),
                    "field": "candidate_pair_relation",
                    "a": left["candidate_pair_relation"],
                    "b": right["candidate_pair_relation"],
                    "final": decision["candidate_pair_relation"],
                    "status": "adjudicated",
                    "handbook_clause": decision["handbook_clause"],
                    "rationale": decision["rationale"],
                }
            )
        else:
            final = _final_agreed_row(left, right, CLASSIFICATION_FIELDS["pair"])
        final_data["pair"].append(final)

    final_errors = _validate_final_rows(cases_by_role["A"], final_data)
    if final_errors:
        raise RuntimeError(f"最终行机器复核失败：{final_errors}")

    construction = construction_index(mapping_rows)
    final_candidates = {
        (row["case_id"], row["candidate_id"]): row for row in final_data["candidate"]
    }
    mappings_by_case: dict[str, list[dict[str, Any]]] = {}
    for row in mapping_rows:
        mappings_by_case.setdefault(row["case_id"], []).append(row)

    family_rows: list[dict[str, Any]] = []
    construction_ledger: list[dict[str, Any]] = []
    for case_id in sorted(orders["case"]):
        mappings = mappings_by_case[case_id]
        failures: list[str] = []
        final_primary_type = ""
        intended_primary_type = next(
            row["primary_conflict_type_proposal"]
            for row in mappings
            if row["construction_role"] == "conflict"
        )
        for mapping in mappings:
            unit = (case_id, mapping["candidate_id"])
            final = final_candidates[unit]
            intended = construction[unit]["intended"]
            differences = [
                field for field, value in intended.items() if final[field] != value
            ]
            if mapping["construction_role"] == "conflict":
                final_primary_type = final["conflict_type"]
            if differences:
                decision = "human_label_overrides_model_proposal"
                if mapping["construction_role"] == "surface_control":
                    failures.append(
                        f"{mapping['candidate_id']} 的表面控制实际为 factual_conflict"
                    )
                    decision = "reject_family_surface_control_failed"
                construction_ledger.append(
                    {
                        "case_id": case_id,
                        "candidate_id": mapping["candidate_id"],
                        "construction_role": mapping["construction_role"],
                        "differing_fields": ";".join(differences),
                        "intended_values": json.dumps(
                            {field: intended[field] for field in differences},
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        "final_values": json.dumps(
                            {field: final[field] for field in differences},
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        "decision": decision,
                        "handbook_clause": (
                            "标注手册第 4 节 target_relation、冲突类型与原子性规则；"
                            "模型构造角色不是真值"
                        ),
                    }
                )
        accepted = not failures
        source = mappings[0]
        family_rows.append(
            {
                "case_id": case_id,
                "generation_id": source["generation_id"],
                "source_batch_id": source["source_batch_id"],
                "intended_primary_conflict_type": intended_primary_type,
                "final_primary_conflict_type": final_primary_type,
                "primary_type_fidelity": intended_primary_type == final_primary_type,
                "family_status": "accepted" if accepted else "rejected",
                "rejection_reason": "；".join(failures),
                "split_role": "internal-v6-dev",
                "origin": "synthetic",
                "gate_eligible": False,
            }
        )

    accepted_rows = [row for row in family_rows if row["family_status"] == "accepted"]
    rejected_rows = [row for row in family_rows if row["family_status"] == "rejected"]
    accepted_ids = {row["case_id"] for row in accepted_rows}
    accepted_primary_units = [
        (row["case_id"], row["candidate_id"])
        for row in mapping_rows
        if row["case_id"] in accepted_ids and row["construction_role"] == "conflict"
    ]
    final_primary_rows = [final_candidates[unit] for unit in accepted_primary_units]
    final_type_quota = Counter(row["conflict_type"] for row in final_primary_rows)
    adjudicability_distribution = Counter(
        row["adjudicability"] for row in final_primary_rows
    )
    source_batch_counts = Counter(row["source_batch_id"] for row in accepted_rows)

    final_root.mkdir(parents=True, mode=0o700)
    final_root.chmod(0o700)
    write_csv(final_root / "adjudicated_case_qualification.csv", final_data["case"], CASE_FIELDS)
    write_csv(
        final_root / "adjudicated_candidate_annotation.csv",
        final_data["candidate"],
        CANDIDATE_FIELDS,
    )
    write_csv(final_root / "adjudicated_pair_annotation.csv", final_data["pair"], PAIR_FIELDS)
    write_csv(
        final_root / "adjudication_ledger.csv",
        adjudication_ledger,
        [
            "scope",
            "unit",
            "field",
            "a",
            "b",
            "final",
            "status",
            "handbook_clause",
            "rationale",
        ],
    )
    write_csv(
        final_root / "construction_adjudication.csv",
        construction_ledger,
        [
            "case_id",
            "candidate_id",
            "construction_role",
            "differing_fields",
            "intended_values",
            "final_values",
            "decision",
            "handbook_clause",
        ],
    )
    write_csv(
        final_root / "family_acceptance.csv",
        family_rows,
        [
            "case_id",
            "generation_id",
            "source_batch_id",
            "intended_primary_conflict_type",
            "final_primary_conflict_type",
            "primary_type_fidelity",
            "family_status",
            "rejection_reason",
            "split_role",
            "origin",
            "gate_eligible",
        ],
    )

    result = {
        "final_version": FINAL_VERSION,
        "finalized_at_local": now_iso(),
        "submission_lock_sha256": lock_check["submission_lock_sha256"],
        "analysis_review_version": REVIEW_VERSION,
        "analysis_summary_sha256": sha256_file(analysis_root / "review_summary.json"),
        "finalization_script_sha256": sha256_file(Path(__file__).resolve()),
        "mechanical_validation": "PASS",
        "mechanical_error_count": 0,
        "raw_evidence_locator_format_warning_count": analysis[
            "mechanical_warning_count"
        ],
        "final_evidence_locator_error_or_warning_count": 0,
        "a_b_disagreement_count": analysis["disagreement_count"],
        "adjudicated_disagreement_count": len(adjudication_ledger),
        "unresolved_disagreement_count": 0,
        "reviewed_family_count": len(family_rows),
        "accepted_family_count": len(accepted_rows),
        "rejected_family_count": len(rejected_rows),
        "human_acceptance_rate": len(accepted_rows) / len(family_rows),
        "rejected_case_ids": [row["case_id"] for row in rejected_rows],
        "final_primary_conflict_type_quota": dict(sorted(final_type_quota.items())),
        "primary_conflict_adjudicability_distribution": dict(
            sorted(adjudicability_distribution.items())
        ),
        "accepted_source_batch_counts": dict(sorted(source_batch_counts.items())),
        "primary_type_fidelity_count": sum(
            row["primary_type_fidelity"] for row in family_rows
        ),
        "primary_type_fidelity_rate": sum(
            row["primary_type_fidelity"] for row in family_rows
        )
        / len(family_rows),
        "human_truth_status": "ADJUDICATED_DEV_ONLY",
        "model_output_is_truth": False,
        "split_role": "internal-v6-dev controlled synthetic construction-yield pilot only",
        "gate_eligibility": "NOT_ELIGIBLE",
        "gate_a_executed": False,
        "gate_b_executed": False,
        "c2_boundary_coverage": {
            "detectable_only": adjudicability_distribution.get("detectable_only", 0),
            "conditionally_adjudicable": adjudicability_distribution.get(
                "conditionally_adjudicable", 0
            ),
            "unidentifiable": adjudicability_distribution.get("unidentifiable", 0),
            "sufficient_for_three_way_c2": False,
        },
    }
    write_json(final_root / "final_result.json", result)

    report = f"""# Internal Stress v6 Dev 双人盲审与主持人裁定报告

> 记录：`{FINAL_VERSION}`

## 结论

- A/B 原始提交已先锁后比；提交锁 SHA-256：`{lock_check['submission_lock_sha256']}`。
- 两人均完成 30 条资格、90 条候选、90 条候选对；机械错误为 0，unresolved 为 0。
- 候选级四个标签与两个资格字段全部一致；候选对 89/90 一致，唯一分歧已按手册裁定为 `factual_conflict`。
- 30 个结构合格提案中，28 个 family 人工接纳，2 个因“表面非冲突控制实际构成同槽事实冲突”被拒绝；人工接纳率为 {len(accepted_rows) / len(family_rows):.2%}。
- 接纳后的主冲突类型为：`numeric={final_type_quota.get('numeric', 0)}`、`version_or_time={final_type_quota.get('version_or_time', 0)}`、`negation_or_direction={final_type_quota.get('negation_or_direction', 0)}`、`applicability_or_condition={final_type_quota.get('applicability_or_condition', 0)}`。

## 证据定位与独立性

B 的原始提交有 {analysis['mechanical_warning_count']} 条定位采用省略/缩写式引用：都能凭 case/candidate ID 回到唯一包内正文，但不是完全逐字引文。它们作为格式警告原样保留；最终表使用 A 的逐字定位或主持人逐字定位，最终定位错误/警告为 0。此项没有修改任何 B 原始标签。

主持人创建过本轮包与构造映射，因此不声称主持人盲态。可成立的独立性主张仅为：A/B 角色目录隔离、输入不含构造角色或答案键、两份提交在内容比较前已锁定。

## 主持人裁定

1. `RF-V6HR-2A5D398D4D/C1-C3`：A=`same_fact`、B=`factual_conflict`。C3 把适用范围收窄到常规样品，并对特殊样品改为单独审批；按候选对关系与适用条件规则，最终为 `factual_conflict`。
2. `RF-V6HR-0E6E7C8889/C2`：预设 `applicability_or_condition`，人工一致判 `numeric`。Query 直接询问年龄，6–12 与 6–14 是同一数值范围上限冲突；接纳人工标签。
3. `RF-V6HR-2A5D398D4D/C2`：预设 `applicability_or_condition`，人工一致判 `numeric`。零下四十与零下二十是同单位温度值冲突；接纳人工标签，但该 family 因 C3 控制失败而整体拒绝。
4. `RF-V6HR-2A5D398D4D/C3` 与 `RF-V6HR-E7058C1EB3/C2`：模型预设为 `surface_control/other_incorrect`，A/B 均判同槽 `factual_conflict + applicability_or_condition`；人工判断覆盖模型角色，两 family 拒绝。

## 研究边界

本轮是 `internal-v6-dev` 的全合成构造率先导，不进入 Gate A/B。接纳的 28 个主冲突全部为 `detectable_only`，因此可用于 Dev 层的冲突检测与压力构造校准，但不能单独覆盖 C2 的“可条件裁决—仅可检测—不可识别”三分边界。GateA/Blind 仍须建立独立自然来源锚点、非零自然候选配额、family 零重合和功效支持的人口。
"""
    (final_root / "facilitator_report.md").write_text(report, encoding="utf-8")
    (final_root / "facilitator_report.md").chmod(0o600)

    manifest_files = []
    for path in sorted(final_root.iterdir()):
        if path.is_file() and path.name not in {"final_manifest.json", "final_manifest.sha256"}:
            manifest_files.append(
                {
                    "path": path.name,
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    manifest = {
        "final_version": FINAL_VERSION,
        "generated_at_local": now_iso(),
        "submission_lock_sha256": lock_check["submission_lock_sha256"],
        "analysis_summary_sha256": result["analysis_summary_sha256"],
        "files": manifest_files,
    }
    write_json(final_root / "final_manifest.json", manifest)
    manifest_hash = sha256_file(final_root / "final_manifest.json")
    (final_root / "final_manifest.sha256").write_text(
        f"{manifest_hash}  final_manifest.json\n", encoding="utf-8"
    )
    (final_root / "final_manifest.sha256").chmod(0o400)
    return {
        "status": "FINALIZED_DEV_ONLY",
        "final_version": FINAL_VERSION,
        "submission_lock_sha256": lock_check["submission_lock_sha256"],
        "final_manifest_sha256": manifest_hash,
        "accepted_family_count": len(accepted_rows),
        "rejected_family_count": len(rejected_rows),
        "human_acceptance_rate": len(accepted_rows) / len(family_rows),
        "a_b_disagreement_count": analysis["disagreement_count"],
        "unresolved_disagreement_count": 0,
        "gate_eligibility": "NOT_ELIGIBLE",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("lock", "verify-lock", "review", "finalize"))
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--work-root",
        type=Path,
        default=Path(
            "runs/robust_fusion/"
            "internal_v6_deepseek_pilot_v2_human_review_v1"
        ),
    )
    parser.add_argument(
        "--review-root",
        type=Path,
        default=Path(
            "runs/robust_fusion/"
            "internal_v6_deepseek_pilot_v2_human_review_v1/facilitator_review"
        ),
    )
    parser.add_argument(
        "--analysis-root",
        type=Path,
        default=Path(
            "runs/robust_fusion/"
            "internal_v6_deepseek_pilot_v2_human_review_v1/"
            "facilitator_review/analysis_v3"
        ),
    )
    parser.add_argument(
        "--final-root",
        type=Path,
        default=Path(
            "runs/robust_fusion/"
            "internal_v6_deepseek_pilot_v2_human_review_v1/"
            "facilitator_review/final_v1"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    work_root = resolve_in_repo(repo_root, args.work_root)
    review_root = resolve_in_repo(repo_root, args.review_root)
    analysis_root = resolve_in_repo(repo_root, args.analysis_root)
    final_root = resolve_in_repo(repo_root, args.final_root)
    if args.mode == "lock":
        result = lock_submissions(repo_root, work_root, review_root)
    elif args.mode == "verify-lock":
        result = verify_lock(repo_root, review_root)
    elif args.mode == "review":
        result = review_submissions(repo_root, review_root, analysis_root)
    else:
        result = finalize_submissions(repo_root, review_root, analysis_root, final_root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
