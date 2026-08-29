#!/usr/bin/env python3
"""初始化 C2 三分边界 Dev-only 空白管理员包。"""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.internal_v6_route_evidence import (
    canonical_json,
    now_iso,
    sha256_file,
    sha256_text,
)

PACKAGE_VERSION = "ROBUST-FUSION-C2-BOUNDARY-SUPPLEMENT-2026-08-29-v1"
HANDBOOK_VERSION = "ROBUST-FUSION-ANNOTATION-HANDBOOK-2026-08-29-v2"

QUOTA_FIELDS = [
    "slot_id",
    "matched_chain_id",
    "primary_conflict_type",
    "target_adjudicability",
    "candidate_design",
    "method_view_signal",
    "required_pair_relation",
    "status",
]
CASE_FIELDS = [
    "case_id",
    "slot_id",
    "query_text",
    "target_reference_text",
    "target_reference_sha256",
    "generator_record_id",
    "proposal_sha256",
    "structure_review_status",
]
CANDIDATE_FIELDS = [
    "case_id",
    "candidate_id",
    "display_text",
    "content_sha256",
    "method_view_metadata_json",
    "construction_role_admin_only",
    "verbatim_anchor",
]
PAIR_FIELDS = ["case_id", "candidate_id_a", "candidate_id_b", "required_for_review"]
ANNOTATOR_CASE_FIELDS = [
    "case_id",
    "reviewer_id",
    "target_reference_status",
    "target_group_status",
    "evidence_locator",
    "rationale",
    "confidence",
    "adjudication_status",
    "handbook_version",
]
ANNOTATOR_CANDIDATE_FIELDS = [
    "case_id",
    "candidate_id",
    "reviewer_id",
    "relevance_status",
    "target_relation",
    "conflict_type",
    "adjudicability",
    "evidence_locator",
    "rationale",
    "confidence",
    "adjudication_status",
    "handbook_version",
]
ANNOTATOR_PAIR_FIELDS = [
    "case_id",
    "candidate_id_a",
    "candidate_id_b",
    "reviewer_id",
    "candidate_pair_relation",
    "evidence_locator",
    "rationale",
    "confidence",
    "adjudication_status",
    "handbook_version",
]

QUOTA_ROWS = [
    {
        "slot_id": "C2S-N-COND",
        "matched_chain_id": "numeric",
        "primary_conflict_type": "numeric",
        "target_adjudicability": "conditionally_adjudicable",
        "candidate_design": "one equivalent + one factual conflict",
        "method_view_signal": "explicit arithmetic or unit conversion rule",
        "required_pair_relation": "factual_conflict",
        "status": "PLANNED_EMPTY",
    },
    {
        "slot_id": "C2S-N-DETECT",
        "matched_chain_id": "numeric",
        "primary_conflict_type": "numeric",
        "target_adjudicability": "detectable_only",
        "candidate_design": "one equivalent + one factual conflict",
        "method_view_signal": "same-slot disagreement; no deciding formula or baseline",
        "required_pair_relation": "factual_conflict",
        "status": "PLANNED_EMPTY",
    },
    {
        "slot_id": "C2S-N-UNID",
        "matched_chain_id": "numeric",
        "primary_conflict_type": "numeric",
        "target_adjudicability": "unidentifiable",
        "candidate_design": "two candidates repeat the same wrong value",
        "method_view_signal": "none; empty metadata",
        "required_pair_relation": "same_fact",
        "status": "PLANNED_EMPTY",
    },
    {
        "slot_id": "C2S-V-COND",
        "matched_chain_id": "version",
        "primary_conflict_type": "version_or_time",
        "target_adjudicability": "conditionally_adjudicable",
        "candidate_design": "one equivalent + one factual conflict",
        "method_view_signal": "query cutoff plus explicit effective intervals",
        "required_pair_relation": "factual_conflict",
        "status": "PLANNED_EMPTY",
    },
    {
        "slot_id": "C2S-V-DETECT",
        "matched_chain_id": "version",
        "primary_conflict_type": "version_or_time",
        "target_adjudicability": "detectable_only",
        "candidate_design": "one equivalent + one factual conflict",
        "method_view_signal": "version disagreement; no deciding cutoff or interval",
        "required_pair_relation": "factual_conflict",
        "status": "PLANNED_EMPTY",
    },
    {
        "slot_id": "C2S-V-UNID",
        "matched_chain_id": "version",
        "primary_conflict_type": "version_or_time",
        "target_adjudicability": "unidentifiable",
        "candidate_design": "two candidates repeat the same wrong version",
        "method_view_signal": "none; empty metadata",
        "required_pair_relation": "same_fact",
        "status": "PLANNED_EMPTY",
    },
    {
        "slot_id": "C2S-D-COND",
        "matched_chain_id": "direction",
        "primary_conflict_type": "negation_or_direction",
        "target_adjudicability": "conditionally_adjudicable",
        "candidate_design": "one equivalent + one factual conflict",
        "method_view_signal": "explicit trigger and deterministic Boolean rule",
        "required_pair_relation": "factual_conflict",
        "status": "PLANNED_EMPTY",
    },
    {
        "slot_id": "C2S-A-COND",
        "matched_chain_id": "applicability",
        "primary_conflict_type": "applicability_or_condition",
        "target_adjudicability": "conditionally_adjudicable",
        "candidate_design": "one equivalent + one factual conflict",
        "method_view_signal": "explicit query scope and candidate applicability scope",
        "required_pair_relation": "factual_conflict",
        "status": "PLANNED_EMPTY",
    },
]


def write_tsv(path: Path, fields: list[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    path.chmod(0o600)


def write_csv(path: Path, fields: list[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    path.chmod(0o600)


def initialize(output_root: Path) -> dict[str, Any]:
    if output_root.exists():
        raise RuntimeError(f"C2 补充目录已存在，拒绝覆盖：{output_root}")
    output_root.mkdir(parents=True, mode=0o700)
    output_root.chmod(0o700)
    write_tsv(output_root / "quota_plan.tsv", QUOTA_FIELDS, QUOTA_ROWS)
    write_tsv(output_root / "case_intake.tsv", CASE_FIELDS, [])
    write_tsv(output_root / "candidate_intake.tsv", CANDIDATE_FIELDS, [])
    write_tsv(output_root / "pair_intake.tsv", PAIR_FIELDS, [])
    write_csv(output_root / "annotator_case_template.csv", ANNOTATOR_CASE_FIELDS, [])
    write_csv(
        output_root / "annotator_candidate_template.csv", ANNOTATOR_CANDIDATE_FIELDS, []
    )
    write_csv(output_root / "annotator_pair_template.csv", ANNOTATOR_PAIR_FIELDS, [])
    view_contract = {
        "version": PACKAGE_VERSION,
        "method_view": [
            "query_text",
            "candidates[].display_text",
            "candidates[].method_view_metadata",
        ],
        "evaluation_view": ["target_references", "facilitator_key", "provenance"],
        "administrator_only": [
            "quota_plan",
            "target_adjudicability",
            "construction_role_admin_only",
            "matched_chain_id",
        ],
        "annotator_package_forbidden": [
            "quota_cell",
            "target_adjudicability",
            "construction_role",
            "origin",
            "facilitator_key",
        ],
    }
    (output_root / "view_contract.json").write_text(
        json.dumps(view_contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_root / "view_contract.json").chmod(0o600)
    (output_root / "README.md").write_text(
        "# C2 三分边界补充 v1\n\n"
        "这是 Dev-only 空白管理员包：8 个 slot 已冻结，但案例正文、答案键和人工标签均为空。"
        "在生成、结构复核、盲化发包、A/B 提交锁和主持人仲裁完成前，不得标为可用数据，"
        "不得进入 Gate A/B。\n",
        encoding="utf-8",
    )
    (output_root / "README.md").chmod(0o600)

    files = []
    for path in sorted(output_root.iterdir()):
        if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"}:
            files.append(
                {
                    "path": path.name,
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    manifest = {
        "package_version": PACKAGE_VERSION,
        "generated_at_local": now_iso(),
        "handbook_version": HANDBOOK_VERSION,
        "split_role": "internal-v6-dev",
        "population_state": "PLANNED_EMPTY",
        "planned_case_count": len(QUOTA_ROWS),
        "materialized_case_count": 0,
        "materialized_candidate_count": 0,
        "materialized_pair_count": 0,
        "human_annotation_started": False,
        "retrieval_route_evidence_ready": False,
        "gate_eligibility": "NOT_ELIGIBLE",
        "gate_a_executed": False,
        "gate_b_executed": False,
        "quota_sha256": sha256_text(canonical_json(QUOTA_ROWS)),
        "files": files,
        "content_root_sha256": sha256_text(canonical_json(files)),
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_root / "manifest.json").chmod(0o600)
    manifest_sha256 = sha256_file(output_root / "manifest.json")
    (output_root / "manifest.sha256").write_text(
        f"{manifest_sha256}  manifest.json\n", encoding="utf-8"
    )
    (output_root / "manifest.sha256").chmod(0o400)
    return {
        "status": "INITIALIZED_PLANNED_EMPTY_DEV_ONLY",
        "package_version": PACKAGE_VERSION,
        "output": str(output_root),
        "planned_case_count": len(QUOTA_ROWS),
        "manifest_sha256": manifest_sha256,
        "gate_eligibility": "NOT_ELIGIBLE",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/robust_fusion/internal_stress_v6/dev/supplements/"
            "c2_boundary_calibration_v1"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output = (args.output if args.output.is_absolute() else repo_root / args.output).resolve()
    if not output.is_relative_to(repo_root):
        raise RuntimeError("输出路径必须位于仓库内")
    print(json.dumps(initialize(output), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
