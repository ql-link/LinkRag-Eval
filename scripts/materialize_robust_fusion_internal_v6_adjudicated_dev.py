#!/usr/bin/env python3
"""将 Internal Stress v6 人工接纳 family 物化为版本化 Dev 摄取制品。"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.internal_v6_pilot import (
    canonical_json,
    sha256_file,
    sha256_text,
)

RELEASE_VERSION = "ROBUST-FUSION-INTERNAL-V6-DEV-ADJUDICATED-2026-08-29-v1"
INTERNAL_PROTOCOL_VERSION = "ROBUST-FUSION-INTERNAL-STRESS-2026-08-29-v9"
ROOT_MANIFEST_VERSION = "ROBUST-FUSION-INTERNAL-V6-ROOT-MANIFEST-2026-08-29-v9"
FINAL_DECISION_VERSION = "ROBUST-FUSION-INTERNAL-V6-FACILITATOR-DECISION-2026-08-29-v1"
EXPECTED_FINAL_MANIFEST_SHA256 = (
    "654ff9ff1959aeb18895b8a872c34665c9a262510f13d79146aca6183650b99a"
)
EXPECTED_SUBMISSION_LOCK_SHA256 = (
    "72d8b77ca601c925ff3840afc4812ac1395019d1930548cd98836201adefbb00"
)

QUERY_FIELDS = [
    "intake_record_id",
    "source_system",
    "source_query_id",
    "query_text_local",
    "query_sha256",
    "query_origin",
    "collection_date",
    "privacy_review_status",
    "consent_or_authorization",
    "exposure_status",
    "query_family_id",
    "document_family_id",
    "version_family_id",
    "counterfactual_template_family_id",
    "proposed_cohort",
    "curator_id",
    "intake_status",
]
DOCUMENT_FIELDS = [
    "intake_record_id",
    "source_system",
    "source_document_id",
    "source_chunk_id",
    "document_text_local",
    "content_sha256",
    "source_locator_local",
    "license_or_authorization",
    "privacy_review_status",
    "document_family_id",
    "version_id",
    "version_family_id",
    "effective_date",
    "parser_id",
    "chunker_id",
    "chunker_parameters_sha256",
    "source_span_locator",
    "exposure_status",
    "intake_status",
]
EVIDENCE_FIELDS = [
    "source_query_id",
    "source_chunk_id",
    "source_relevance_label",
    "target_equivalence_group_id",
    "target_relation",
    "conflict_type",
    "adjudicability",
    "evidence_locator_local",
    "evidence_span_local",
    "reviewer_a",
    "reviewer_b",
    "adjudicator",
    "review_status",
    "handbook_version",
    "exposure_status",
]
FAMILY_FIELDS = [
    "group_id",
    "query_family_id",
    "document_family_id",
    "version_family_id",
    "counterfactual_template_family_id",
    "assignment_hash",
    "assigned_cohort",
    "assignment_seed_id",
    "overlap_check_status",
    "curator_approval",
]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.write_text("".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8")
    path.chmod(0o600)


def write_tsv(path: Path, fields: list[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    path.chmod(0o600)


def verify_manifest(root: Path, name: str, receipt_name: str) -> str:
    manifest_path = root / name
    digest = sha256_file(manifest_path)
    recorded = (root / receipt_name).read_text(encoding="utf-8").split()[0]
    if digest != recorded:
        raise RuntimeError(f"manifest 回执不匹配：{manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for row in manifest["files"]:
        path = root / row["path"]
        if (
            not path.is_file()
            or path.stat().st_size != row["size_bytes"]
            or sha256_file(path) != row["sha256"]
        ):
            raise RuntimeError(f"manifest 文件不匹配：{path}")
    return digest


def _ensure_single_line(value: str, unit: str) -> None:
    if any(char in value for char in ("\t", "\n", "\r")):
        raise RuntimeError(f"TSV 正文含制表或换行符：{unit}")


def _candidate_source(proposal: dict[str, Any], role: str) -> dict[str, Any]:
    return {
        "equivalent": proposal["equivalent_candidate"],
        "conflict": proposal["conflict_candidate"],
        "surface_control": proposal["surface_control_candidate"],
    }[role]


def build_release(
    *,
    repo_root: Path,
    review_root: Path,
    output_root: Path,
    dataset_root: Path,
) -> dict[str, Any]:
    if output_root.exists():
        raise RuntimeError(f"Dev release 已存在，拒绝覆盖：{output_root}")
    dev_manifest_v9 = dataset_root / "dev" / "cohort_manifest_v9.json"
    root_manifest_v9 = dataset_root / "control" / "root_manifest_v9.json"
    root_receipt_v9 = dataset_root / "control" / "root_manifest_v9.sha256"
    for path in (dev_manifest_v9, root_manifest_v9, root_receipt_v9):
        if path.exists():
            raise RuntimeError(f"v9 sidecar 已存在，拒绝覆盖：{path}")

    final_root = review_root / "final_v1"
    final_manifest_sha256 = verify_manifest(
        final_root, "final_manifest.json", "final_manifest.sha256"
    )
    if final_manifest_sha256 != EXPECTED_FINAL_MANIFEST_SHA256:
        raise RuntimeError("最终裁定 manifest 不是预期冻结版本")
    final_result = json.loads((final_root / "final_result.json").read_text(encoding="utf-8"))
    if final_result["final_version"] != FINAL_DECISION_VERSION:
        raise RuntimeError("最终裁定版本不符")
    if final_result["submission_lock_sha256"] != EXPECTED_SUBMISSION_LOCK_SHA256:
        raise RuntimeError("最终裁定未绑定预期提交锁")
    if final_result["accepted_family_count"] != 28:
        raise RuntimeError("最终接纳 family 数不为 28")

    accepted_rows = [
        row
        for row in read_csv(final_root / "family_acceptance.csv")
        if row["family_status"] == "accepted"
    ]
    rejected_rows = [
        row
        for row in read_csv(final_root / "family_acceptance.csv")
        if row["family_status"] == "rejected"
    ]
    if (len(accepted_rows), len(rejected_rows)) != (28, 2):
        raise RuntimeError("family_acceptance.csv 的接纳/拒绝计数不符")

    cases = {
        row["case_id"]: row
        for row in read_jsonl(review_root / "frozen_inputs/annotator_a/annotation_cases.jsonl")
    }
    mappings = read_jsonl(review_root / "frozen_inputs/facilitator/blind_mapping.jsonl")
    mapping_by_unit = {(row["case_id"], row["candidate_id"]): row for row in mappings}
    selected = read_jsonl(review_root / "frozen_inputs/facilitator/selected_proposals.jsonl")
    final_cases = {
        row["case_id"]: row
        for row in read_csv(final_root / "adjudicated_case_qualification.csv")
    }
    final_candidates = {
        (row["case_id"], row["candidate_id"]): row
        for row in read_csv(final_root / "adjudicated_candidate_annotation.csv")
    }

    chunker_parameters_sha256 = sha256_text(
        canonical_json(
            {
                "mode": "one synthetic passage equals one immutable Dev chunk",
                "normalization": "none",
                "release_version": RELEASE_VERSION,
            }
        )
    )
    source_system = "internal_v6_deepseek_synthetic_dev_double_reviewed"
    source_locator_prefix = (
        "runs/robust_fusion/internal_v6_deepseek_pilot_v2_human_review_v1/"
        "facilitator_review/frozen_inputs/facilitator/selected_proposals.jsonl"
    )
    authorization = "user_authorized_noncommercial_research_synthetic_generation"
    privacy = "PASS_SYNTHETIC_NO_PRIVATE_SOURCE"
    intake_status = "ACCEPTED_DOUBLE_REVIEW_ADJUDICATED_DEV_ONLY"
    handbook_version = final_candidates[next(iter(final_candidates))]["handbook_version"]

    query_rows: list[dict[str, Any]] = []
    document_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    family_rows: list[dict[str, Any]] = []
    mapping_rows: list[dict[str, Any]] = []
    content_ids: set[str] = set()

    accepted_by_generation = {row["generation_id"]: row for row in accepted_rows}
    for selected_row in selected:
        generation_id = selected_row["generation_id"]
        if generation_id not in accepted_by_generation:
            continue
        family_status = accepted_by_generation[generation_id]
        case_id = family_status["case_id"]
        case = cases[case_id]
        proposal = selected_row["proposal"]
        family_ids = proposal["family_ids"]
        case_qualification = final_cases[case_id]
        if (
            case_qualification["target_reference_status"] != "valid"
            or case_qualification["target_group_status"] != "unique"
        ):
            raise RuntimeError(f"接纳 family 的目标资格不合法：{case_id}")
        if case["query_text"] != proposal["query"]["text"]:
            raise RuntimeError(f"Query 文本与提案不一致：{case_id}")
        target_text = case["target_references"][0]["display_text"]
        if target_text != proposal["target_evidence"]["text"]:
            raise RuntimeError(f"目标证据文本与提案不一致：{case_id}")
        for name, value in (
            ("query", case["query_text"]),
            ("target", target_text),
        ):
            _ensure_single_line(value, f"{case_id}:{name}")

        query_id = proposal["query"]["query_id"]
        query_rows.append(
            {
                "intake_record_id": f"{RELEASE_VERSION}:query:{query_id}",
                "source_system": source_system,
                "source_query_id": query_id,
                "query_text_local": case["query_text"],
                "query_sha256": sha256_text(case["query_text"]),
                "query_origin": "synthetic",
                "collection_date": "2026-08-29",
                "privacy_review_status": privacy,
                "consent_or_authorization": authorization,
                "exposure_status": "dev_exposed",
                "query_family_id": family_ids["query_family_id"],
                "document_family_id": family_ids["document_family_id"],
                "version_family_id": family_ids["version_family_id"],
                "counterfactual_template_family_id": family_ids[
                    "counterfactual_template_family_id"
                ],
                "proposed_cohort": "internal-v6-dev",
                "curator_id": "FACILITATOR",
                "intake_status": intake_status,
            }
        )

        target_document_id = proposal["target_evidence"]["document_id"]
        target_chunk_id = f"{target_document_id}-CHUNK-001"
        target_equivalence_group_id = f"{generation_id}-TARGET-EQG"
        document_specs = [
            {
                "candidate_alias": "T1",
                "construction_role": "target_gold",
                "source_document_id": target_document_id,
                "source_chunk_id": target_chunk_id,
                "text": target_text,
                "version_id": f"{generation_id}-VERSION-T1",
            }
        ]
        for candidate in case["candidates"]:
            alias = candidate["candidate_id"]
            mapping = mapping_by_unit[(case_id, alias)]
            source = _candidate_source(proposal, mapping["construction_role"])
            if candidate["display_text"] != source["text"]:
                raise RuntimeError(f"候选正文与构造映射不一致：{case_id}/{alias}")
            _ensure_single_line(candidate["display_text"], f"{case_id}:{alias}")
            document_specs.append(
                {
                    "candidate_alias": alias,
                    "construction_role": mapping["construction_role"],
                    "source_document_id": source["candidate_id"],
                    "source_chunk_id": source["candidate_id"],
                    "text": candidate["display_text"],
                    "version_id": f"{generation_id}-VERSION-{alias}",
                }
            )

        for spec in document_specs:
            chunk_id = spec["source_chunk_id"]
            if chunk_id in content_ids:
                raise RuntimeError(f"source_chunk_id 重复：{chunk_id}")
            content_ids.add(chunk_id)
            document_rows.append(
                {
                    "intake_record_id": f"{RELEASE_VERSION}:document:{chunk_id}",
                    "source_system": source_system,
                    "source_document_id": spec["source_document_id"],
                    "source_chunk_id": chunk_id,
                    "document_text_local": spec["text"],
                    "content_sha256": sha256_text(spec["text"]),
                    "source_locator_local": (
                        f"{source_locator_prefix}#generation_id={generation_id};"
                        f"candidate={spec['candidate_alias']}"
                    ),
                    "license_or_authorization": authorization,
                    "privacy_review_status": privacy,
                    "document_family_id": family_ids["document_family_id"],
                    "version_id": spec["version_id"],
                    "version_family_id": family_ids["version_family_id"],
                    "effective_date": "",
                    "parser_id": "none_synthetic_single_passage_v1",
                    "chunker_id": "identity_single_passage_v1",
                    "chunker_parameters_sha256": chunker_parameters_sha256,
                    "source_span_locator": "whole synthetic passage",
                    "exposure_status": "dev_exposed",
                    "intake_status": intake_status,
                }
            )
            if spec["construction_role"] == "target_gold":
                evidence_rows.append(
                    {
                        "source_query_id": query_id,
                        "source_chunk_id": chunk_id,
                        "source_relevance_label": "relevant_gold",
                        "target_equivalence_group_id": target_equivalence_group_id,
                        "target_relation": "equivalent",
                        "conflict_type": "not_applicable",
                        "adjudicability": "not_applicable",
                        "evidence_locator_local": case_qualification["evidence_locator"],
                        "evidence_span_local": proposal["target_evidence"]["verbatim_anchor"],
                        "reviewer_a": "A",
                        "reviewer_b": "B",
                        "adjudicator": "FACILITATOR",
                        "review_status": "agreed_target_valid_unique",
                        "handbook_version": handbook_version,
                        "exposure_status": "dev_exposed",
                    }
                )
            else:
                final = final_candidates[(case_id, spec["candidate_alias"])]
                evidence_rows.append(
                    {
                        "source_query_id": query_id,
                        "source_chunk_id": chunk_id,
                        "source_relevance_label": final["relevance_status"],
                        "target_equivalence_group_id": target_equivalence_group_id,
                        "target_relation": final["target_relation"],
                        "conflict_type": final["conflict_type"],
                        "adjudicability": final["adjudicability"],
                        "evidence_locator_local": final["evidence_locator"],
                        "evidence_span_local": final["evidence_locator"],
                        "reviewer_a": "A",
                        "reviewer_b": "B",
                        "adjudicator": "FACILITATOR",
                        "review_status": final["adjudication_status"],
                        "handbook_version": final["handbook_version"],
                        "exposure_status": "dev_exposed",
                    }
                )

        assignment_payload = {
            **family_ids,
            "assigned_cohort": "internal-v6-dev",
            "release_version": RELEASE_VERSION,
        }
        family_rows.append(
            {
                "group_id": proposal["synthetic_fact"]["synthetic_fact_id"],
                "query_family_id": family_ids["query_family_id"],
                "document_family_id": family_ids["document_family_id"],
                "version_family_id": family_ids["version_family_id"],
                "counterfactual_template_family_id": family_ids[
                    "counterfactual_template_family_id"
                ],
                "assignment_hash": sha256_text(canonical_json(assignment_payload)),
                "assigned_cohort": "internal-v6-dev",
                "assignment_seed_id": RELEASE_VERSION,
                "overlap_check_status": (
                    "PASS_DEV_IDS_AND_V5_EXACT_TEXT;GATEA_AND_BLIND_EMPTY;"
                    "SEMANTIC_CONFIRMATORY_OVERLAP_PENDING"
                ),
                "curator_approval": "APPROVED_DEV_ONLY_AFTER_DOUBLE_REVIEW",
            }
        )
        mapping_rows.append(
            {
                "case_id": case_id,
                "generation_id": generation_id,
                "source_batch_id": selected_row["source_batch_id"],
                "proposal_sha256": selected_row["proposal_sha256"],
                "source_query_id": query_id,
                "target_chunk_id": target_chunk_id,
                "target_equivalence_group_id": target_equivalence_group_id,
                "family_ids": family_ids,
                "intended_primary_conflict_type": family_status[
                    "intended_primary_conflict_type"
                ],
                "final_primary_conflict_type": family_status[
                    "final_primary_conflict_type"
                ],
                "origin": "synthetic",
                "split_role": "internal-v6-dev",
                "gate_eligible": False,
            }
        )

    if (len(query_rows), len(document_rows), len(evidence_rows), len(family_rows)) != (
        28,
        112,
        112,
        28,
    ):
        raise RuntimeError("物化后的四张摄取表计数不符")
    if len({row["source_query_id"] for row in query_rows}) != 28:
        raise RuntimeError("source_query_id 不唯一")
    if len({row["assignment_hash"] for row in family_rows}) != 28:
        raise RuntimeError("assignment_hash 不唯一")

    output_root.mkdir(parents=True, mode=0o700)
    output_root.chmod(0o700)
    write_tsv(output_root / "query_intake.tsv", QUERY_FIELDS, query_rows)
    write_tsv(output_root / "document_intake.tsv", DOCUMENT_FIELDS, document_rows)
    write_tsv(output_root / "evidence_intake.tsv", EVIDENCE_FIELDS, evidence_rows)
    write_tsv(output_root / "family_assignment.tsv", FAMILY_FIELDS, family_rows)
    write_jsonl(output_root / "case_mapping.jsonl", mapping_rows)
    write_jsonl(output_root / "rejected_family_audit.jsonl", rejected_rows)
    write_json(
        output_root / "review_binding.json",
        {
            "release_version": RELEASE_VERSION,
            "final_decision_version": FINAL_DECISION_VERSION,
            "submission_lock_sha256": EXPECTED_SUBMISSION_LOCK_SHA256,
            "final_manifest_sha256": final_manifest_sha256,
            "source_review_root": str(review_root.relative_to(repo_root)),
        },
    )
    (output_root / "README.md").write_text(
        "# Internal Stress v6 Adjudicated Dev v1\n\n"
        "本目录是 30-family 全合成先导经 A/B 双审和主持人仲裁后的 Dev-only 摄取制品。"
        "接纳 28 个 family、拒绝 2 个。它可用于构念、相似度、冲突代理、三路检索与功效校准，"
        "不得进入 GateA/Blind。当前尚未计算 Dense/Learned Sparse/BM25 证据。\n",
        encoding="utf-8",
    )
    (output_root / "README.md").chmod(0o600)

    content_files = []
    for path in sorted(output_root.iterdir()):
        if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"}:
            content_files.append(
                {
                    "path": path.name,
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    content_root_sha256 = sha256_text(canonical_json(content_files))
    manifest = {
        "release_version": RELEASE_VERSION,
        "generated_at_local": now_iso(),
        "internal_protocol_version": INTERNAL_PROTOCOL_VERSION,
        "final_decision_version": FINAL_DECISION_VERSION,
        "submission_lock_sha256": EXPECTED_SUBMISSION_LOCK_SHA256,
        "final_manifest_sha256": final_manifest_sha256,
        "split_role": "internal-v6-dev",
        "origin": "synthetic",
        "reviewed_family_count": 30,
        "accepted_family_count": 28,
        "rejected_family_count": 2,
        "human_acceptance_rate": 28 / 30,
        "query_count": len(query_rows),
        "document_chunk_count": len(document_rows),
        "evidence_label_count": len(evidence_rows),
        "family_assignment_count": len(family_rows),
        "primary_conflict_type_quota": dict(
            sorted(Counter(row["final_primary_conflict_type"] for row in mapping_rows).items())
        ),
        "primary_conflict_adjudicability": {"detectable_only": 28},
        "c2_three_way_boundary_covered": False,
        "annotation_ready": True,
        "retrieval_route_evidence_ready": False,
        "gate_eligibility": "NOT_ELIGIBLE",
        "gate_a_executed": False,
        "gate_b_executed": False,
        "files": content_files,
        "content_root_sha256": content_root_sha256,
    }
    write_json(output_root / "manifest.json", manifest)
    release_manifest_sha256 = sha256_file(output_root / "manifest.json")
    (output_root / "manifest.sha256").write_text(
        f"{release_manifest_sha256}  manifest.json\n", encoding="utf-8"
    )
    (output_root / "manifest.sha256").chmod(0o400)

    dev_manifest = {
        "package_version": INTERNAL_PROTOCOL_VERSION,
        "cohort_id": "internal-v6-dev",
        "role": "construct_annotation_similarity_proxy_and_power_calibration",
        "population_state": "ADJUDICATED_SYNTHETIC_DEV_ONLY",
        "query_family_count": 28,
        "record_count": 28,
        "count_visibility": "visible",
        "release_path": str(output_root.relative_to(dataset_root)),
        "release_manifest_sha256": release_manifest_sha256,
        "content_root_sha256": content_root_sha256,
        "runtime_access": "development_only",
        "unlocked_at": now_iso(),
        "sealed_at": None,
        "gate_eligibility": "NOT_ELIGIBLE",
        "prohibitions": [
            "no migration into internal-v6-gatea or internal-v6-blind",
            "no historical Blind v4/v5 family",
            "no claim of natural candidate yield or Gate evidence",
            "no use as complete C2 three-way boundary coverage",
        ],
    }
    write_json(dev_manifest_v9, dev_manifest)

    prior_root = dataset_root / "control/root_manifest.json"
    root_manifest = {
        "root_manifest_version": ROOT_MANIFEST_VERSION,
        "generated_at_local": now_iso(),
        "previous_root_manifest_path": "control/root_manifest.json",
        "previous_root_manifest_sha256": sha256_file(prior_root),
        "internal_protocol_version": INTERNAL_PROTOCOL_VERSION,
        "protocol_records": {
            "scientific_protocol": "ROBUST-FUSION-RESEARCH-2026-08-29-v22",
            "engineering_protocol": "ROBUST-FUSION-ENGINEERING-2026-08-29-v13",
            "progress_record": "ROBUST-FUSION-PROGRESS-2026-08-29-v24",
            "final_decision": FINAL_DECISION_VERSION,
        },
        "cohorts": {
            "dev": {
                "manifest": "dev/cohort_manifest_v9.json",
                "sha256": sha256_file(dev_manifest_v9),
            },
            "gatea": {
                "manifest": "gatea/cohort_manifest.json",
                "sha256": sha256_file(dataset_root / "gatea/cohort_manifest.json"),
                "population_state": "EMPTY_LOCKED",
            },
            "blind": {
                "manifest": "blind/cohort_manifest.json",
                "sha256": sha256_file(dataset_root / "blind/cohort_manifest.json"),
                "population_state": "EMPTY_LOCKED",
            },
        },
        "submission_lock_sha256": EXPECTED_SUBMISSION_LOCK_SHA256,
        "final_manifest_sha256": final_manifest_sha256,
        "dev_release_manifest_sha256": release_manifest_sha256,
        "gate_eligibility": "NOT_ELIGIBLE",
        "state": "DEV_SYNTHETIC_ADJUDICATED_CONFIRMATORY_COHORTS_EMPTY",
        "reason_not_eligible": (
            "Dev has 28 adjudicated synthetic families, but GateA/Blind remain empty and lack "
            "independent natural anchors, nonzero natural candidate quotas, power-supported "
            "denominators, extended family isolation, and formal seals."
        ),
    }
    write_json(root_manifest_v9, root_manifest)
    root_manifest_sha256 = sha256_file(root_manifest_v9)
    root_receipt_v9.write_text(
        f"{root_manifest_sha256}  root_manifest_v9.json\n", encoding="utf-8"
    )
    root_receipt_v9.chmod(0o400)
    return {
        "status": "MATERIALIZED_DEV_ONLY",
        "release_version": RELEASE_VERSION,
        "release_path": str(output_root.relative_to(repo_root)),
        "release_manifest_sha256": release_manifest_sha256,
        "content_root_sha256": content_root_sha256,
        "root_manifest_v9_sha256": root_manifest_sha256,
        "query_count": len(query_rows),
        "document_chunk_count": len(document_rows),
        "evidence_label_count": len(evidence_rows),
        "family_assignment_count": len(family_rows),
        "gate_eligibility": "NOT_ELIGIBLE",
    }


def resolve_in_repo(repo_root: Path, path: Path) -> Path:
    resolved = (path if path.is_absolute() else repo_root / path).resolve()
    if not resolved.is_relative_to(repo_root):
        raise RuntimeError(f"路径必须位于仓库内：{resolved}")
    return resolved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--review-root",
        type=Path,
        default=Path(
            "runs/robust_fusion/internal_v6_deepseek_pilot_v2_human_review_v1/"
            "facilitator_review"
        ),
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path("data/robust_fusion/internal_stress_v6"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "data/robust_fusion/internal_stress_v6/dev/releases/"
            "adjudicated_synthetic_v1"
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    result = build_release(
        repo_root=repo_root,
        review_root=resolve_in_repo(repo_root, args.review_root),
        output_root=resolve_in_repo(repo_root, args.output),
        dataset_root=resolve_in_repo(repo_root, args.dataset_root),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
