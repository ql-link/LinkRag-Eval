#!/usr/bin/env python3
"""Run the sole preregistered pre-Gate Dev common-support supplement."""

from __future__ import annotations

import argparse
import csv
import json
import platform
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from linkrag_eval.robust_fusion.similarity import cosine_float64
from linkrag_eval.robust_fusion.similarity_dev_calibration import (
    canonical_json,
    sha256_file,
    sha256_text,
    write_json,
    write_jsonl,
)
from linkrag_eval.robust_fusion.similarity_support_supplement import (
    COMBINED_FAMILY_COUNT,
    SUPPLEMENT_FAMILY_COUNT,
    SUPPLEMENT_RUN_ID,
    SUPPLEMENT_VERSION,
    V1_CONFLICT_HITS,
    V1_EQUIVALENT_HITS,
    V1_FAMILY_COUNT,
    fixed_sample_size_design,
    generate_paired_families,
    preregistration_protocol,
    select_similarity_audit_sample,
    validate_paired_families,
)

try:
    from scripts.run_robust_fusion_similarity_dev_calibration import (
        encode_model,
        encoder_provenance,
        load_qualification,
    )
except ModuleNotFoundError:  # Direct ``python scripts/...py`` execution.
    from run_robust_fusion_similarity_dev_calibration import (  # type: ignore[no-redef]
        encode_model,
        encoder_provenance,
        load_qualification,
    )

DEFAULT_OUTPUT_ROOT = Path(
    "runs/robust_fusion/similarity_dev_support_supplement_v1/"
    "internal-v6-dev-similarity-support-supplement-v1-20260829"
)
DEFAULT_V1_ROOT = Path(
    "runs/robust_fusion/similarity_dev_calibration_v1/"
    "internal-v6-dev-similarity-calibration-v1-20260829"
)
DEFAULT_QUALIFICATION_ROOT = Path(
    "runs/robust_fusion/contracts/similarity-encoder-qualification-v3"
)
DEFAULT_MODEL_CACHE = Path("data/robust_fusion/models/huggingface")

V1_HASHES = {
    "manifest.json": "b44d13f5a5e4f6bea2225ec8c29588db10a37ad1da124eb2d8ff7fb09f08454c",
    "provisional_calibration.json": "01ae8c0f141221ebd45d21332e357f197ec0b15e5d3d5c5616d60ac544c4b371",
    "candidate_similarity.jsonl": "0a0962970a28724d48dad83619adb3b6252916361568e8f62e0d3621c435fb5e",
    "human_audit/facilitator/adjudication_v1/final_manifest.json": "463c31cbf0dbf112b8be087a42ce20239ea46b4729d9863498ca9a484a41647d",
    "human_audit/facilitator/adjudication_v1/final_review.json": "90ed2c7e930b3628f87529dfa876603aacf94a2eb292105a5f586d12f1433a71",
    "human_audit/facilitator/adjudication_v1/final_scores.jsonl": "899f610cfe1edf42079078186f71edefe611891b476dd33d937580db6fb4cb67",
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def resolve_in_repo(repo_root: Path, path: Path) -> Path:
    resolved = (path if path.is_absolute() else repo_root / path).resolve()
    if not resolved.is_relative_to(repo_root):
        raise RuntimeError(f"path must remain inside repository: {resolved}")
    tokens = {part.lower().replace("_", "-") for part in resolved.parts}
    if any("gatea" in token or "gate-a" in token or "blind" in token for token in tokens):
        raise RuntimeError(f"supplement refuses GateA/Blind path: {resolved}")
    return resolved


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    path.chmod(0o600)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def verify_v1_read_only(v1_root: Path) -> None:
    for relative, expected in V1_HASHES.items():
        path = v1_root / relative
        if not path.is_file() or sha256_file(path) != expected:
            raise RuntimeError(f"immutable v1 drift: {relative}")
    review = json.loads(
        (v1_root / "human_audit/facilitator/adjudication_v1/final_review.json").read_text(
            encoding="utf-8"
        )
    )
    if (
        review.get("combined_similarity_freeze_decision") != "INCONCLUSIVE"
        or review.get("formal_numeric_freeze_complete") is not False
    ):
        raise RuntimeError("v1 disposition is no longer the permanent INCONCLUSIVE record")


def code_snapshot(repo_root: Path) -> dict[str, Any]:
    paths = [
        Path(__file__).resolve(),
        repo_root / "src/linkrag_eval/robust_fusion/similarity_support_supplement.py",
        repo_root / "src/linkrag_eval/robust_fusion/similarity_dev_calibration.py",
        repo_root / "src/linkrag_eval/robust_fusion/similarity.py",
        repo_root / "scripts/run_robust_fusion_similarity_dev_calibration.py",
    ]
    return {
        "python": platform.python_version(),
        "files": [
            {"path": path.relative_to(repo_root).as_posix(), "sha256": sha256_file(path)}
            for path in paths
        ],
    }


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    output_root = resolve_in_repo(repo_root, args.output_root)
    v1_root = resolve_in_repo(repo_root, args.v1_root)
    if output_root.exists():
        raise RuntimeError(f"refusing to overwrite supplement root: {output_root}")
    verify_v1_read_only(v1_root)
    output_root.mkdir(parents=True, mode=0o700)
    prereg = output_root / "preregistration"
    prereg.mkdir(mode=0o700)
    protocol = preregistration_protocol()
    sample_size = fixed_sample_size_design()
    workload = {
        "new_query_families": SUPPLEMENT_FAMILY_COUNT,
        "new_candidates": SUPPLEMENT_FAMILY_COUNT * 2,
        "relation_rows_per_researcher": SUPPLEMENT_FAMILY_COUNT * 2,
        "similarity_rows_per_researcher": 48,
        "total_rows_per_researcher_before_adjudication": SUPPLEMENT_FAMILY_COUNT * 2 + 48,
        "adjudication_rows": "determined mechanically after all four submissions are locked",
        "external_paid_calls_required": False,
        "local_encoder_vectors": SUPPLEMENT_FAMILY_COUNT * 3,
    }
    code = code_snapshot(repo_root)
    write_json(prereg / "protocol.json", protocol)
    write_json(prereg / "sample_size.json", sample_size)
    write_json(prereg / "workload.json", workload)
    write_json(prereg / "code_snapshot.json", code)
    manifest_files = []
    for name in ("protocol.json", "sample_size.json", "workload.json", "code_snapshot.json"):
        path = prereg / name
        manifest_files.append(
            {"path": name, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}
        )
    manifest = {
        "protocol_version": SUPPLEMENT_VERSION,
        "run_id": SUPPLEMENT_RUN_ID,
        "status": "PREREGISTERED_NO_NEW_RESULTS_READ",
        "v1_read_only_hashes": V1_HASHES,
        "result_files_present_at_manifest": [],
        "files": manifest_files,
    }
    write_json(prereg / "manifest.json", manifest)
    manifest_sha = sha256_file(prereg / "manifest.json")
    (prereg / "manifest.sha256").write_text(
        f"{manifest_sha}  manifest.json\n", encoding="utf-8"
    )
    locked_at_ns = time.time_ns()
    lock = {
        "protocol_version": SUPPLEMENT_VERSION,
        "run_id": SUPPLEMENT_RUN_ID,
        "status": "LOCKED_BEFORE_ANY_SUPPLEMENT_DATA_SCORE_OR_HUMAN_RESULT",
        "manifest_sha256": manifest_sha,
        "locked_at_local": now_iso(),
        "locked_at_unix_ns": locked_at_ns,
        "result_directories_present_at_lock": [],
        "v1_verified_read_only": True,
    }
    write_json(prereg / "lock.json", lock)
    lock_sha = sha256_file(prereg / "lock.json")
    (prereg / "lock.sha256").write_text(f"{lock_sha}  lock.json\n", encoding="utf-8")
    receipt = {
        "receipt_type": "local_pre_result_preregistration_lock_receipt",
        "run_id": SUPPLEMENT_RUN_ID,
        "lock_sha256": lock_sha,
        "manifest_sha256": manifest_sha,
        "issued_at_local": now_iso(),
        "issued_at_unix_ns": time.time_ns(),
        "external_timestamp_claimed": False,
    }
    write_json(prereg / "receipt.json", receipt)
    (prereg / "receipt.sha256").write_text(
        f"{sha256_file(prereg / 'receipt.json')}  receipt.json\n", encoding="utf-8"
    )
    return {
        "status": lock["status"],
        "output_root": str(output_root),
        "manifest_sha256": manifest_sha,
        "lock_sha256": lock_sha,
        "fixed_new_families": SUPPLEMENT_FAMILY_COUNT,
        "rows_per_researcher": workload["total_rows_per_researcher_before_adjudication"],
    }


def verify_preregistration(output_root: Path, repo_root: Path) -> dict[str, Any]:
    prereg = output_root / "preregistration"
    manifest_path = prereg / "manifest.json"
    manifest_sha = sha256_file(manifest_path)
    if (prereg / "manifest.sha256").read_text(encoding="utf-8").split()[0] != manifest_sha:
        raise RuntimeError("preregistration manifest receipt drift")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for row in manifest["files"]:
        path = prereg / row["path"]
        if (
            not path.is_file()
            or path.stat().st_size != row["size_bytes"]
            or sha256_file(path) != row["sha256"]
        ):
            raise RuntimeError(f"preregistration file drift: {row['path']}")
    lock_path = prereg / "lock.json"
    lock_sha = sha256_file(lock_path)
    if (prereg / "lock.sha256").read_text(encoding="utf-8").split()[0] != lock_sha:
        raise RuntimeError("preregistration lock receipt drift")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    receipt = json.loads((prereg / "receipt.json").read_text(encoding="utf-8"))
    if (
        lock["manifest_sha256"] != manifest_sha
        or receipt["lock_sha256"] != lock_sha
        or receipt["manifest_sha256"] != manifest_sha
        or lock["result_directories_present_at_lock"]
    ):
        raise RuntimeError("preregistration lock chain invalid")
    current_code = code_snapshot(repo_root)
    frozen_code = json.loads((prereg / "code_snapshot.json").read_text(encoding="utf-8"))
    if current_code != frozen_code:
        raise RuntimeError("supplement code changed after preregistration lock")
    return {"manifest_sha256": manifest_sha, "lock_sha256": lock_sha, **lock}


def _materialize_relation_packages(output_root: Path, families: list[dict[str, Any]]) -> list[dict[str, Any]]:
    root = output_root / "human_relation"
    facilitator = root / "facilitator"
    facilitator.mkdir(parents=True, mode=0o700)
    registry: list[dict[str, Any]] = []
    for family in families:
        for role, field, candidate_id in (
            ("equivalent", "equivalent_candidate", family["equivalent_candidate_id"]),
            ("factual_conflict", "factual_conflict_candidate", family["conflict_candidate_id"]),
        ):
            audit_id = "RF-SUP-REL-" + sha256_text(
                f"{SUPPLEMENT_VERSION}:{candidate_id}"
            )[:12].upper()
            registry.append(
                {
                    "relation_audit_id": audit_id,
                    "query_family_id": family["query_family_id"],
                    "candidate_id": candidate_id,
                    "construction_role": role,
                    "conflict_type_preregistered": family["conflict_type_preregistered"],
                    "length_stratum_preregistered": family["length_stratum_preregistered"],
                    "query": family["query"],
                    "reference": family["reference"],
                    "candidate": family[field],
                }
            )
    write_jsonl(facilitator / "registry.jsonl", registry)
    fields = [
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
    packages = []
    instruction = (
        "请依据标注手册 v2 独立完成全部 144 行关系判断。只判断目标参照有效性、目标组唯一性、"
        "候选与目标事实的关系及冲突类型；不要评价两段文本有多相似。不得查看模型分数、分带、"
        "构造角色或另一位研究员答案。adjudication_status 初始固定为 single；uncertain=yes 时理由必填。"
    )
    for role in ("A", "B"):
        role_root = root / f"annotator_{role.lower()}"
        role_root.mkdir(mode=0o700)
        ordered = sorted(
            registry,
            key=lambda row: sha256_text(f"relation:{role}:{row['relation_audit_id']}"),
        )
        cases = [
            {
                "relation_audit_id": row["relation_audit_id"],
                "query": row["query"],
                "target_reference": row["reference"],
                "candidate": row["candidate"],
            }
            for row in ordered
        ]
        template = [
            {
                "relation_audit_id": row["relation_audit_id"],
                "target_reference_status": "",
                "target_group_status": "",
                "target_relation": "",
                "conflict_type": "",
                "evidence_locator": "",
                "rationale": "",
                "reviewer_id": "",
                "confidence": "",
                "uncertain": "",
                "adjudication_status": "single",
            }
            for row in ordered
        ]
        write_csv(role_root / "cases.csv", cases, list(cases[0]))
        write_csv(role_root / "submission_template.csv", template, fields)
        (role_root / "README.txt").write_text(instruction + "\n", encoding="utf-8")
        manifest = {
            "protocol_version": SUPPLEMENT_VERSION,
            "role": role,
            "task": "formal_relation_labeling",
            "row_count": len(cases),
            "contains_model_scores": False,
            "contains_similarity_bands": False,
            "contains_construction_role": False,
            "contains_answer_key": False,
            "files": [
                {"path": name, "sha256": sha256_file(role_root / name)}
                for name in ("README.txt", "cases.csv", "submission_template.csv")
            ],
        }
        write_json(role_root / "package_manifest.json", manifest)
        (role_root / "package_manifest.sha256").write_text(
            f"{sha256_file(role_root / 'package_manifest.json')}  package_manifest.json\n",
            encoding="utf-8",
        )
        packages.append(
            {
                "role": role,
                "rows": len(cases),
                "manifest_sha256": sha256_file(role_root / "package_manifest.json"),
            }
        )
    return packages


def materialize(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    output_root = resolve_in_repo(repo_root, args.output_root)
    v1_root = resolve_in_repo(repo_root, args.v1_root)
    lock = verify_preregistration(output_root, repo_root)
    verify_v1_read_only(v1_root)
    if (output_root / "data").exists() or (output_root / "human_relation").exists():
        raise RuntimeError("refusing to overwrite materialized supplement data")
    families = generate_paired_families()
    data_root = output_root / "data"
    data_root.mkdir(mode=0o700)
    write_jsonl(data_root / "families.jsonl", families)
    relation_packages = _materialize_relation_packages(output_root, families)
    manifest = {
        "protocol_version": SUPPLEMENT_VERSION,
        "run_id": SUPPLEMENT_RUN_ID,
        "status": "MATERIALIZED_BEFORE_ENCODER_SCORING",
        "generated_at_local": now_iso(),
        "generated_at_unix_ns": time.time_ns(),
        "preregistration_lock_sha256": lock["lock_sha256"],
        "lock_precedes_materialization": time.time_ns() > lock["locked_at_unix_ns"],
        "family_count": len(families),
        "candidate_count": len(families) * 2,
        "strata": {
            "length": dict(sorted(Counter(row["length_stratum_preregistered"] for row in families).items())),
            "language": dict(sorted(Counter(row["language"] for row in families).items())),
            "conflict_type": dict(sorted(Counter(row["conflict_type_preregistered"] for row in families).items())),
        },
        "relation_packages": relation_packages,
        "files": [
            {
                "path": "families.jsonl",
                "size_bytes": (data_root / "families.jsonl").stat().st_size,
                "sha256": sha256_file(data_root / "families.jsonl"),
            }
        ],
    }
    write_json(data_root / "manifest.json", manifest)
    (data_root / "manifest.sha256").write_text(
        f"{sha256_file(data_root / 'manifest.json')}  manifest.json\n", encoding="utf-8"
    )
    return {
        "status": manifest["status"],
        "family_count": len(families),
        "data_manifest_sha256": sha256_file(data_root / "manifest.json"),
        "relation_rows_per_researcher": len(families) * 2,
    }


def verify_materialized(output_root: Path, prereg_lock: dict[str, Any]) -> list[dict[str, Any]]:
    data_root = output_root / "data"
    manifest_path = data_root / "manifest.json"
    manifest_sha = sha256_file(manifest_path)
    if (data_root / "manifest.sha256").read_text(encoding="utf-8").split()[0] != manifest_sha:
        raise RuntimeError("materialized data manifest receipt drift")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest["preregistration_lock_sha256"] != prereg_lock["lock_sha256"]
        or manifest["generated_at_unix_ns"] <= prereg_lock["locked_at_unix_ns"]
    ):
        raise RuntimeError("materialization did not follow the preregistration lock")
    families_path = data_root / "families.jsonl"
    if sha256_file(families_path) != manifest["files"][0]["sha256"]:
        raise RuntimeError("materialized family file drift")
    families = read_jsonl(families_path)
    validate_paired_families(families)
    return families


def _percentile_ranks(values: list[float]) -> list[float]:
    ordered = sorted(range(len(values)), key=lambda index: (values[index], index))
    ranks = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and values[ordered[end]] == values[ordered[start]]:
            end += 1
        average = ((start + end - 1) / 2) / max(1, len(values) - 1)
        for position in range(start, end):
            ranks[ordered[position]] = average
        start = end
    return ranks


def _score_rows(
    families: list[dict[str, Any]],
    main_vectors: np.ndarray,
    audit_vectors: np.ndarray,
    index: dict[str, int],
    main_meta: dict[str, dict[str, Any]],
    audit_meta: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for family in families:
        reference_id = family["reference_id"]
        for construction_role, candidate_id in (
            ("equivalent", family["equivalent_candidate_id"]),
            ("factual_conflict", family["conflict_candidate_id"]),
        ):
            rows.append(
                {
                    "query_family_id": family["query_family_id"],
                    "query_id": family["query_id"],
                    "target_equivalence_group_id": family["target_equivalence_group_id"],
                    "reference_id": reference_id,
                    "candidate_id": candidate_id,
                    "construction_role": construction_role,
                    "conflict_type_preregistered": family["conflict_type_preregistered"],
                    "length_stratum_preregistered": family["length_stratum_preregistered"],
                    "language": family["language"],
                    "main_similarity": cosine_float64(
                        main_vectors[index[candidate_id]], main_vectors[index[reference_id]]
                    ),
                    "audit_similarity": cosine_float64(
                        audit_vectors[index[candidate_id]], audit_vectors[index[reference_id]]
                    ),
                    "main_untruncated_token_count_max": max(
                        main_meta[candidate_id]["untruncated_token_count"],
                        main_meta[reference_id]["untruncated_token_count"],
                    ),
                    "audit_untruncated_token_count_max": max(
                        audit_meta[candidate_id]["untruncated_token_count"],
                        audit_meta[reference_id]["untruncated_token_count"],
                    ),
                    "main_was_truncated": bool(
                        main_meta[candidate_id]["was_truncated"]
                        or main_meta[reference_id]["was_truncated"]
                    ),
                    "audit_was_truncated": bool(
                        audit_meta[candidate_id]["was_truncated"]
                        or audit_meta[reference_id]["was_truncated"]
                    ),
                }
            )
    main_ranks = _percentile_ranks([float(row["main_similarity"]) for row in rows])
    audit_ranks = _percentile_ranks([float(row["audit_similarity"]) for row in rows])
    for row, left, right in zip(rows, main_ranks, audit_ranks):
        row["main_percentile_rank"] = left
        row["audit_percentile_rank"] = right
        row["encoder_percentile_gap"] = abs(left - right)
    return rows


def _validate_length_contract(rows: list[dict[str, Any]]) -> dict[str, Any]:
    errors = []
    for row in rows:
        if row["length_stratum_preregistered"] == "short":
            if row["audit_untruncated_token_count_max"] > 128:
                errors.append(f"short_truncated:{row['candidate_id']}")
        else:
            if not row["audit_was_truncated"] or row["main_was_truncated"]:
                errors.append(f"long_contract:{row['candidate_id']}")
    if errors:
        raise RuntimeError(f"preregistered length contract failed without replacement: {errors[:5]}")
    return {
        "short_rows": sum(row["length_stratum_preregistered"] == "short" for row in rows),
        "long_rows": sum(row["length_stratum_preregistered"] == "long" for row in rows),
        "main_truncated_rows": sum(row["main_was_truncated"] for row in rows),
        "audit_truncated_rows": sum(row["audit_was_truncated"] for row in rows),
    }


def _construction_role_preview(
    v1_root: Path, supplement_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    v1_rows = [
        row
        for row in read_jsonl(v1_root / "candidate_similarity.jsonl")
        if row["target_relation"] in {"equivalent", "factual_conflict"}
    ]
    by_relation = {
        relation: [
            float(row["main_similarity"])
            for row in v1_rows
            if row["target_relation"] == relation
        ]
        + [
            float(row["main_similarity"])
            for row in supplement_rows
            if row["construction_role"] == relation
        ]
        for relation in ("equivalent", "factual_conflict")
    }
    low = max(min(values) for values in by_relation.values())
    high = min(max(values) for values in by_relation.values())
    coverage = {
        relation: sum(low <= value <= high for value in values) / COMBINED_FAMILY_COUNT
        for relation, values in by_relation.items()
    }
    supplement_only = {
        relation: sum(
            low <= float(row["main_similarity"]) <= high
            for row in supplement_rows
            if row["construction_role"] == relation
        )
        / SUPPLEMENT_FAMILY_COUNT
        for relation in ("equivalent", "factual_conflict")
    }
    return {
        "status": "NONFORMAL_CONSTRUCTION_ROLE_PREVIEW_AWAITING_HUMAN_RELATION_TRUTH",
        "may_freeze_numbers": False,
        "v1": {
            "denominator_each_relation": V1_FAMILY_COUNT,
            "equivalent_hits_in_v1_interval": V1_EQUIVALENT_HITS,
            "factual_conflict_hits_in_v1_interval": V1_CONFLICT_HITS,
            "permanent_decision": "INCONCLUSIVE",
        },
        "combined_preview_interval_inclusive": [low, high],
        "supplement_only_preview_coverage": supplement_only,
        "combined_preview_coverage": coverage,
        "warning": "construction roles are not formal relation labels; this preview cannot determine PASS",
    }


def _materialize_similarity_packages(
    output_root: Path,
    sample: list[dict[str, Any]],
    family_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    root = output_root / "human_similarity"
    facilitator = root / "facilitator"
    facilitator.mkdir(parents=True, mode=0o700)
    registry = []
    for row in sample:
        audit_id = "RF-SUP-SIM-" + sha256_text(
            f"{SUPPLEMENT_VERSION}:{row['candidate_id']}"
        )[:12].upper()
        registry.append({"similarity_audit_id": audit_id, **row})
    write_jsonl(facilitator / "registry.jsonl", registry)
    packages = []
    instruction = (
        "请独立完成全部 48 对文本，只判断两段文本的语义接近程度，不判断哪段正确，也不要填写关系标签。"
        "不得查看模型分数、分带、构造目标、关系包答案或另一位研究员答案。量表与 v1 相同："
        "1=不同主题/实体/事实槽；2=同领域但实体或事实槽不同；3=同实体/主题且部分事实槽或条件重合；"
        "4=同一事实槽且语义高度接近（允许关键事实/条件不同）；5=近乎等价或紧密改写。"
        "uncertain=yes 时 note 必填。"
    )
    fields = ["similarity_audit_id", "human_similarity_ordinal", "confidence", "uncertain", "note"]
    for role in ("A", "B"):
        role_root = root / f"annotator_{role.lower()}"
        role_root.mkdir(mode=0o700)
        ordered = sorted(
            registry,
            key=lambda row: sha256_text(f"similarity:{role}:{row['similarity_audit_id']}"),
        )
        pairs = []
        template = []
        for row in ordered:
            family = family_by_id[row["query_family_id"]]
            candidate = (
                family["equivalent_candidate"]
                if row["construction_role"] == "equivalent"
                else family["factual_conflict_candidate"]
            )
            swap = int(sha256_text(f"swap:{role}:{row['similarity_audit_id']}")[-1], 16) % 2
            pairs.append(
                {
                    "similarity_audit_id": row["similarity_audit_id"],
                    "text_1": candidate if swap else family["reference"],
                    "text_2": family["reference"] if swap else candidate,
                }
            )
            template.append(
                {
                    "similarity_audit_id": row["similarity_audit_id"],
                    "human_similarity_ordinal": "",
                    "confidence": "",
                    "uncertain": "",
                    "note": "",
                }
            )
        write_csv(role_root / "pairs.csv", pairs, list(pairs[0]))
        write_csv(role_root / "submission_template.csv", template, fields)
        (role_root / "README.txt").write_text(instruction + "\n", encoding="utf-8")
        manifest = {
            "protocol_version": SUPPLEMENT_VERSION,
            "role": role,
            "task": "blind_similarity_rating",
            "row_count": len(pairs),
            "contains_model_scores": False,
            "contains_similarity_bands": False,
            "contains_relation_labels": False,
            "contains_construction_goal": False,
            "contains_answer_key": False,
            "files": [
                {"path": name, "sha256": sha256_file(role_root / name)}
                for name in ("README.txt", "pairs.csv", "submission_template.csv")
            ],
        }
        write_json(role_root / "package_manifest.json", manifest)
        (role_root / "package_manifest.sha256").write_text(
            f"{sha256_file(role_root / 'package_manifest.json')}  package_manifest.json\n",
            encoding="utf-8",
        )
        packages.append(
            {
                "role": role,
                "rows": len(pairs),
                "manifest_sha256": sha256_file(role_root / "package_manifest.json"),
            }
        )
    return packages


def score(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    output_root = resolve_in_repo(repo_root, args.output_root)
    v1_root = resolve_in_repo(repo_root, args.v1_root)
    qualification_root = resolve_in_repo(repo_root, args.qualification_root)
    cache_root = resolve_in_repo(repo_root, args.model_cache)
    lock = verify_preregistration(output_root, repo_root)
    verify_v1_read_only(v1_root)
    families = verify_materialized(output_root, lock)
    automatic = output_root / "automatic"
    if automatic.exists() or (output_root / "human_similarity").exists():
        raise RuntimeError("refusing to overwrite supplement scores or similarity packages")
    _qualification, main_spec, audit_spec = load_qualification(qualification_root)
    chunks = []
    for family in families:
        chunks.extend(
            [
                {"chunk_id": family["reference_id"], "content": family["reference"], "content_sha256": family["reference_sha256"]},
                {"chunk_id": family["equivalent_candidate_id"], "content": family["equivalent_candidate"], "content_sha256": family["equivalent_candidate_sha256"]},
                {"chunk_id": family["conflict_candidate_id"], "content": family["factual_conflict_candidate"], "content_sha256": family["factual_conflict_candidate_sha256"]},
            ]
        )
    ordered_chunks = sorted(chunks, key=lambda row: row["chunk_id"])
    main_vectors, main_metadata = encode_model(main_spec, cache_root, ordered_chunks)
    audit_vectors, audit_metadata = encode_model(audit_spec, cache_root, ordered_chunks)
    index = {row["chunk_id"]: position for position, row in enumerate(ordered_chunks)}
    main_meta = {row["chunk_id"]: row for row in main_metadata}
    audit_meta = {row["chunk_id"]: row for row in audit_metadata}
    rows = _score_rows(families, main_vectors, audit_vectors, index, main_meta, audit_meta)
    length_summary = _validate_length_contract(rows)
    sample = select_similarity_audit_sample(rows)
    automatic.mkdir(mode=0o700)
    vectors_root = automatic / "vectors"
    vectors_root.mkdir(mode=0o700)
    np.save(vectors_root / "main.float32.npy", main_vectors, allow_pickle=False)
    np.save(vectors_root / "audit.float32.npy", audit_vectors, allow_pickle=False)
    write_jsonl(
        vectors_root / "index.jsonl",
        [{"vector_row": index[row["chunk_id"]], "chunk_id": row["chunk_id"]} for row in ordered_chunks],
    )
    write_jsonl(automatic / "main_input_vectors.jsonl", main_metadata)
    write_jsonl(automatic / "audit_input_vectors.jsonl", audit_metadata)
    write_jsonl(automatic / "candidate_similarity.jsonl", rows)
    write_json(automatic / "length_summary.json", length_summary)
    preview = _construction_role_preview(v1_root, rows)
    write_json(automatic / "construction_role_preview.json", preview)
    packages = _materialize_similarity_packages(
        output_root, sample, {row["query_family_id"]: row for row in families}
    )
    config = {
        "protocol_version": SUPPLEMENT_VERSION,
        "estimand": "S_qg(c)=max_h_in_A_qg cosine(z(c),z(h)); one frozen reference per family",
        "main_encoder": encoder_provenance(main_spec),
        "audit_encoder": encoder_provenance(audit_spec),
        "cosine": "float32 vectors; float64 accumulation; no rounding",
        "human_similarity_sampling": "12 per construction-role x preregistered-length cell; six lowest and six highest E5/DistilUSE percentile-rank gaps",
        "formal_relation_labels_available": False,
    }
    write_json(automatic / "computation_config.json", config)
    generated_ns = time.time_ns()
    managed = sorted(
        path for path in automatic.rglob("*") if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"}
    )
    manifest = {
        "protocol_version": SUPPLEMENT_VERSION,
        "run_id": SUPPLEMENT_RUN_ID,
        "status": "AUTOMATIC_COMPLETE_AWAITING_FOUR_HUMAN_SUBMISSIONS",
        "generated_at_local": now_iso(),
        "generated_at_unix_ns": generated_ns,
        "preregistration_lock_sha256": lock["lock_sha256"],
        "lock_precedes_scores": generated_ns > lock["locked_at_unix_ns"],
        "v1_hashes_reverified": V1_HASHES,
        "reference_count": SUPPLEMENT_FAMILY_COUNT,
        "candidate_score_count": SUPPLEMENT_FAMILY_COUNT * 2,
        "main_vector_shape": list(main_vectors.shape),
        "audit_vector_shape": list(audit_vectors.shape),
        "length_summary": length_summary,
        "similarity_packages": packages,
        "formal_combined_decision": "AWAITING_HUMAN_SUBMISSIONS",
        "gate_a_authorized": False,
        "gate_a_executed": False,
        "gate_b_executed": False,
        "files": [
            {"path": path.relative_to(automatic).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in managed
        ],
    }
    write_json(automatic / "manifest.json", manifest)
    (automatic / "manifest.sha256").write_text(
        f"{sha256_file(automatic / 'manifest.json')}  manifest.json\n", encoding="utf-8"
    )
    status = {
        "protocol_version": SUPPLEMENT_VERSION,
        "status": "AWAITING_HUMAN_SUBMISSIONS",
        "v1_permanent_decision": "INCONCLUSIVE",
        "supplement_cycle_number": 1,
        "additional_p2_supplement_allowed": False,
        "automatic_part_complete": True,
        "formal_numeric_freeze_complete": False,
        "p2_01_complete": False,
        "p2_04_complete": False,
        "gate_a_authorized": False,
        "relation_rows_per_researcher": 144,
        "similarity_rows_per_researcher": 48,
        "total_rows_per_researcher": 192,
    }
    write_json(output_root / "status.json", status)
    return {
        "status": status["status"],
        "automatic_manifest_sha256": sha256_file(automatic / "manifest.json"),
        "scored_candidates": len(rows),
        "relation_rows_per_researcher": 144,
        "similarity_rows_per_researcher": 48,
    }


def verify(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    output_root = resolve_in_repo(repo_root, args.output_root)
    v1_root = resolve_in_repo(repo_root, args.v1_root)
    lock = verify_preregistration(output_root, repo_root)
    verify_v1_read_only(v1_root)
    families = verify_materialized(output_root, lock)
    automatic = output_root / "automatic"
    if not automatic.exists():
        return {
            "status": "VERIFIED_PREREGISTERED_MATERIALIZED_NOT_SCORED",
            "family_count": len(families),
            "lock_sha256": lock["lock_sha256"],
        }
    manifest_path = automatic / "manifest.json"
    manifest_sha = sha256_file(manifest_path)
    if (automatic / "manifest.sha256").read_text(encoding="utf-8").split()[0] != manifest_sha:
        raise RuntimeError("automatic manifest receipt drift")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest["preregistration_lock_sha256"] != lock["lock_sha256"]
        or manifest["generated_at_unix_ns"] <= lock["locked_at_unix_ns"]
        or manifest["gate_a_authorized"]
    ):
        raise RuntimeError("automatic result crossed its locked Dev-only boundary")
    for row in manifest["files"]:
        path = automatic / row["path"]
        if not path.is_file() or path.stat().st_size != row["size_bytes"] or sha256_file(path) != row["sha256"]:
            raise RuntimeError(f"automatic file drift: {row['path']}")
    scores = read_jsonl(automatic / "candidate_similarity.jsonl")
    if len(scores) != 144 or len({row["candidate_id"] for row in scores}) != 144:
        raise RuntimeError("automatic score set is incomplete or duplicated")
    for task, expected_rows in (("human_relation", 144), ("human_similarity", 48)):
        for role in ("a", "b"):
            package = output_root / task / f"annotator_{role}"
            package_manifest = json.loads((package / "package_manifest.json").read_text(encoding="utf-8"))
            if package_manifest["row_count"] != expected_rows or package_manifest["contains_model_scores"]:
                raise RuntimeError(f"human package contract drift: {task}:{role}")
            text = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.csv"))
            forbidden = (
                "main_similarity",
                "audit_similarity",
                "construction_role",
                "similarity_band",
                "conflict_type_preregistered",
            )
            if any(token in text for token in forbidden):
                raise RuntimeError(f"human package leaks facilitator/model fields: {task}:{role}")
    status = json.loads((output_root / "status.json").read_text(encoding="utf-8"))
    if status["status"] != "AWAITING_HUMAN_SUBMISSIONS" or status["gate_a_authorized"]:
        raise RuntimeError("supplement status boundary drift")
    return {
        "status": "VERIFIED_AWAITING_HUMAN_SUBMISSIONS",
        "preregistration_lock_sha256": lock["lock_sha256"],
        "automatic_manifest_sha256": manifest_sha,
        "family_count": len(families),
        "scored_candidate_count": len(scores),
        "relation_rows_per_researcher": 144,
        "similarity_rows_per_researcher": 48,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "materialize", "score", "verify"))
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--v1-root", type=Path, default=DEFAULT_V1_ROOT)
    parser.add_argument("--qualification-root", type=Path, default=DEFAULT_QUALIFICATION_ROOT)
    parser.add_argument("--model-cache", type=Path, default=DEFAULT_MODEL_CACHE)
    args = parser.parse_args()
    result = {
        "prepare": prepare,
        "materialize": materialize,
        "score": score,
        "verify": verify,
    }[args.command](args)
    print(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
