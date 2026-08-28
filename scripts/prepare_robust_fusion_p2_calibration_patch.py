#!/usr/bin/env python3
"""生成并校验 Robust Fusion P2 五例最小替换校准包。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import shutil
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

T2_REVISION = "2a369a430a70979223f1b9a41b1919774d46b432"
DRUID_REVISION = "4b37ea52c1e1ad5af63a4feee9ce1cfb7348078b"
PACKAGE_VERSION = "ROBUST-FUSION-P2-CALIBRATION-PATCH-2026-08-29-v3"
HANDBOOK_VERSION = "ROBUST-FUSION-P2-PATCH-HANDBOOK-2026-08-29-v1"
VIEW_CONTRACT_VERSION = "ROBUST-FUSION-P2-PATCH-VIEW-CONTRACT-2026-08-29-v2"
SPLIT_ROLE = "P2_DESKTOP_CALIBRATION_PATCH_ONLY"

BASE_PACKAGE_VERSION = "ROBUST-FUSION-P2-CALIBRATION-REPLAY-2026-08-29-v2"
BASE_MANIFEST_PATH = Path("data/robust_fusion/derived/p2_calibration_v2/manifest.json")
BASE_KEY_PATH = Path("data/robust_fusion/derived/p2_calibration_v2/facilitator_key.jsonl")
BASE_LOCK_PATH = Path(
    "runs/robust_fusion/internal_v6_deepseek_pilot_v1/"
    "human_calibration_replay_v2/facilitator_review/submission_lock.json"
)
BASE_MANIFEST_SHA256 = "a8eee3dba3e0a7fa5822039ce1f39b7a6b917dec0025d2b83e854ec3a4cb0df2"
BASE_KEY_SHA256 = "2baa076cf43ac512aa5650532e0ed7964e814aa3848108419610b6bccaa3fd38"
BASE_LOCK_SHA256 = "98cce4a8136d1026aed96dcb3f20e3f442fba58b159d458a9d3d131bc7c5be1f"

T2_INPUTS = {
    "collection.tsv": {
        "size_bytes": 3_659_243_528,
        "sha256": "07b84e543e9ba696124a727c00629d5bce586631648c436c98dd6e9b146da212",
    },
    "queries.dev.tsv": {
        "size_bytes": 939_767,
        "sha256": "1df544dd04bf9b6d0de0dd77e0f3a84a0d74fc4bb9a1ff67b7306de8169135ba",
    },
    "qrels.dev.tsv": {
        "size_bytes": 6_537_957,
        "sha256": "a0356bd3c6d72c532ca17a4d88d7765554857f321346cf0f9cb4ad480738b25a",
    },
}
DRUID_INPUT = {
    "size_bytes": 3_327_953,
    "sha256": "679850fd833ca6b84f1751927c7048758be6dd1645bfd4932b8af90a57d5f79a",
}

BASE_CASE_IDS = {f"RF-P2R2-{index:02d}" for index in range(1, 13)}
REPLACED_CASE_IDS = {
    "RF-P2R2-03",
    "RF-P2R2-06",
    "RF-P2R2-09",
    "RF-P2R2-10",
    "RF-P2R2-11",
}
RETAINED_CASE_IDS = BASE_CASE_IDS - REPLACED_CASE_IDS
REPLACEMENT_MAP = {
    "RF-P2P3-4C9A": "RF-P2R2-03",
    "RF-P2P3-7F21": "RF-P2R2-06",
    "RF-P2P3-A6D4": "RF-P2R2-09",
    "RF-P2P3-C318": "RF-P2R2-10",
    "RF-P2P3-E05B": "RF-P2R2-11",
}

COMBINED_QUOTA = {
    "version_or_time": 2,
    "numeric": 2,
    "negation_or_direction": 2,
    "applicability_or_condition": 2,
    "equivalent": 1,
    "other_incorrect": 1,
    "possible_false_negative": 1,
    "wrong_consensus": 1,
}
PATCH_QUOTA = {
    "version_or_time": 2,
    "applicability_or_condition": 2,
    "other_incorrect": 1,
}

# v1 与 v2 均已被标注员接触；补包不得复用其中任何 Query。
V1_T2_QUERY_IDS = {"22", "50", "84", "85", "1708", "2341", "2965", "3320", "14948"}
V1_DRUID_QUERY_IDS = {"checkyourfact_1280"}
V2_T2_QUERY_IDS = {"598", "967", "2022", "2359", "2441", "3542", "4400", "4487", "5457"}
V2_DRUID_QUERY_IDS = {"checkyourfact_1294"}

CASE_FIELDS = [
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
CANDIDATE_FIELDS = [
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
PAIR_FIELDS = [
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

BLIND_FORBIDDEN_FIELDS = {
    "quota_cell",
    "dataset_id",
    "dataset_revision",
    "split_role",
    "query_id",
    "target_equivalence_group_id",
    "official_record_id",
    "source_qrel",
    "origin",
    "source_stance",
    "source_helpful",
    "transformation",
    "expected",
    "facilitator",
    "replaces_case_id",
}
ROLE_STATIC_FILES = {
    "INSTRUCTIONS.md",
    "标注操作手册.md",
    "view_contract.json",
    "annotation_cases.jsonl",
    "case_qualification.csv",
    "candidate_annotation.csv",
    "pair_annotation.csv",
    "package_receipt.json",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.write_text(
        "".join(canonical_json(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def display_text(raw: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    text = re.sub(r"(?is)<img\b[^>]*>", "", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def read_queries(path: Path, wanted: set[str]) -> dict[str, str]:
    rows: dict[str, str] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t", 1)
            if len(parts) == 2 and parts[0] in wanted:
                rows[parts[0]] = parts[1]
    if set(rows) != wanted:
        raise RuntimeError(f"缺少 T2 Query：{sorted(wanted - set(rows))}")
    return rows


def read_qrels(path: Path, wanted_qids: set[str]) -> dict[tuple[str, str], int]:
    rows: dict[tuple[str, str], int] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if not parts or parts[0] not in wanted_qids:
                continue
            try:
                rows[(parts[0], parts[-2])] = int(parts[-1])
            except (IndexError, ValueError):
                continue
    return rows


def read_passages(path: Path, wanted: set[str]) -> dict[str, str]:
    rows: dict[str, str] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t", 1)
            if len(parts) == 2 and parts[0] in wanted:
                rows[parts[0]] = parts[1]
                if len(rows) == len(wanted):
                    break
    if set(rows) != wanted:
        raise RuntimeError(f"缺少 T2 passage：{sorted(wanted - set(rows))}")
    return rows


def read_druid_case(path: Path, claim_id: str) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("claim_id") == claim_id:
                return row
    raise RuntimeError(f"缺少 DRUID claim：{claim_id}")


def expected(
    relevance_status: str,
    target_relation: str,
    conflict_type: str = "not_applicable",
    adjudicability: str = "not_applicable",
) -> dict[str, str]:
    return {
        "relevance_status": relevance_status,
        "target_relation": target_relation,
        "conflict_type": conflict_type,
        "adjudicability": adjudicability,
    }


def view_contract() -> dict[str, Any]:
    return {
        "view_contract_version": VIEW_CONTRACT_VERSION,
        "field_roles": {
            "query_text": "method_view",
            "candidates[].display_text": "method_view",
            "candidates[].method_view_metadata": "method_view；仅使用包内明示字段，可为空",
            "target_references[].display_text": "evaluation_view",
            "case_id/reference_id/candidate_id": "仅用于定位记录，不提供事实判断信号",
        },
        "target_policy": {
            "external_verification": "禁止",
            "rule": "本包 target 是冻结 Gold；只检查正文能否回答 Query 及目标组是否唯一，不联网核实。",
        },
        "adjudicability_policy": {
            "allowed_fields": [
                "query_text",
                "candidates[].display_text",
                "candidates[].method_view_metadata",
            ],
            "forbidden_signals": [
                "target_references（包括 T1/Gold 正文和身份）",
                "外部知识或联网核证结果",
                "qrel、来源、构造方式、配额、split、数据集身份和管理员字段",
            ],
            "conditionally_adjudicable": "method view 加冻结确定性规则能推出正确值，或能唯一选择正确成员。",
            "detectable_only": "method view 只能稳定发现冲突或不可靠风险，不能推出正确值。",
            "unidentifiable": "method view 连稳定风险信号也没有；只有 evaluation view 才知道候选错误。",
            "deterministic_rule_boundary": "对 Query 明示输入做确定性算术或日历计算不算外部核证；仅凭常识猜答案仍禁止。",
        },
        "single_fact_policy": {
            "rule": "每个事实冲突只比较一个主事实槽；若冲突核心是资格、地域、人群、型号、阶段或所需材料组合，主类为 applicability_or_condition。",
            "negation_boundary": "只有在实体、时间、范围和前提均相同而命题真值直接反转时，才优先选 negation_or_direction。",
        },
    }


def build_patch_cases(t2_dir: Path, druid_path: Path) -> list[dict[str, Any]]:
    wanted_qids = {"2440", "12791", "12945", "20432"}
    wanted_pids = {"695777", "695779", "401014", "493137", "98185"}
    queries = read_queries(t2_dir / "queries.dev.tsv", wanted_qids)
    qrels = read_qrels(t2_dir / "qrels.dev.tsv", wanted_qids)
    passages = read_passages(t2_dir / "collection.tsv", wanted_pids)
    druid = read_druid_case(druid_path, "checkyourfact_1378")

    required_qrels = {
        ("2440", "695777"): 1,
        ("2440", "695779"): 2,
        ("12791", "401014"): 3,
        ("12945", "98185"): 2,
        ("20432", "493137"): 2,
    }
    actual_qrels = {unit: qrels.get(unit) for unit in required_qrels}
    if actual_qrels != required_qrels:
        raise RuntimeError(f"选定 T2 qrel 与冻结值不符：{actual_qrels}")

    def t2_ref(pid: str) -> dict[str, Any]:
        raw = passages[pid]
        return {
            "official_record_id": pid,
            "display_text": display_text(raw),
            "raw_content_sha256": sha256_bytes(raw.encode("utf-8")),
        }

    def t2_natural(candidate_id: str, qid: str, pid: str) -> dict[str, Any]:
        raw = passages[pid]
        return {
            "candidate_id": candidate_id,
            "display_text": display_text(raw),
            "method_view_metadata": {},
            "provenance": {
                "origin": "natural",
                "official_record_id": pid,
                "source_qrel": qrels[(qid, pid)],
                "raw_content_sha256": sha256_bytes(raw.encode("utf-8")),
            },
        }

    def t2_synthetic(
        candidate_id: str,
        text: str,
        base_pid: str,
        transformation: str,
        method_view_metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        base_raw = passages[base_pid]
        metadata = method_view_metadata or {}
        return {
            "candidate_id": candidate_id,
            "display_text": text,
            "method_view_metadata": metadata,
            "provenance": {
                "origin": "synthetic",
                "base_official_record_id": base_pid,
                "base_raw_content_sha256": sha256_bytes(base_raw.encode("utf-8")),
                "transformation": transformation,
                "atomic_fact_edit_count": 1,
                "method_signal_addition_count": int(bool(metadata)),
                "synthetic_content_sha256": sha256_bytes(text.encode("utf-8")),
                "method_view_metadata_sha256": sha256_bytes(canonical_json(metadata).encode("utf-8")),
            },
        }

    def t2_case(
        case_id: str,
        quota_cell: str,
        qid: str,
        target_group_id: str,
        target_pids: list[str],
        candidate: dict[str, Any],
        candidate_key: dict[str, Any],
        calibration_focus: str,
    ) -> dict[str, Any]:
        return {
            "case_id": case_id,
            "replaces_case_id": REPLACEMENT_MAP[case_id],
            "quota_cell": quota_cell,
            "dataset_id": "THUIR/T2Ranking",
            "dataset_revision": T2_REVISION,
            "split_role": SPLIT_ROLE,
            "query_id": qid,
            "query_text": queries[qid],
            "target_equivalence_group_id": target_group_id,
            "target_references": [t2_ref(pid) for pid in target_pids],
            "candidates": [candidate],
            "facilitator": {
                "calibration_focus": calibration_focus,
                "case_qualification_key": {
                    "target_reference_status": "valid",
                    "target_group_status": "unique",
                },
                "candidate_keys": [candidate_key],
            },
        }

    cases: list[dict[str, Any]] = []

    cases.append(
        t2_case(
            "RF-P2P3-4C9A",
            "other_incorrect",
            "2440",
            "t2:2440:fubao-station-opened-2020-10-28",
            ["695777"],
            t2_natural("C1", "2440", "695779"),
            {
                "candidate_id": "C1",
                "expected": expected(
                    "verified_incorrect_distractor",
                    "other_incorrect",
                ),
                "evidence_locator": "T1 明示福保站随延长线于10月28日开通；C1 只描述车站位置、工程进展及‘即将’运营，没有给出开通日期。",
                "rationale": "C1 与主题相关，但缺失 Query 所问的开通时间事实槽；它没有对同一日期给出相反值，因此不是事实冲突。",
            },
            "主题相关且公开 qrel 为正，但正文未回答所问时间槽。",
        )
    )

    cases.append(
        t2_case(
            "RF-P2P3-7F21",
            "version_or_time",
            "12791",
            "t2:12791:coco-founded-1997",
            ["401014"],
            t2_synthetic(
                "C1",
                "CoCo 都可奶茶成立于1998年。",
                "401014",
                "只替换成立年份 1997→1998；另把未定稿与年份未核验状态作为方法侧元数据明示。",
                {
                    "document_status": "未定稿",
                    "year_verification": "未完成",
                },
            ),
            {
                "candidate_id": "C1",
                "expected": expected(
                    "verified_incorrect_distractor",
                    "factual_conflict",
                    "version_or_time",
                    "detectable_only",
                ),
                "evidence_locator": "T1 写明品牌诞生于1997年；C1 写为1998年；C1 的 method_view_metadata 明示‘未定稿、年份未核验’。",
                "rationale": "同一品牌成立年份不相容。方法侧元数据能稳定标记该候选的年份风险，但不能推出正确年份1997，因此只能检测，不能裁决正确值。",
            },
            "纯年份冲突，并明确区分风险可检测与正确值可推出。",
        )
    )

    cases.append(
        t2_case(
            "RF-P2P3-A6D4",
            "applicability_or_condition",
            "20432",
            "t2:20432:foshang-high-skill-entry-requires-local-six-month-social-security",
            ["493137"],
            t2_synthetic(
                "C1",
                "高技能人才申请入户佛山时，社保条件为在广东省内任一城市连续缴纳满6个月。",
                "493137",
                "只把社保参保地域从佛山市替换为广东省内任一城市；时长保持6个月。",
            ),
            {
                "candidate_id": "C1",
                "expected": expected(
                    "verified_incorrect_distractor",
                    "factual_conflict",
                    "applicability_or_condition",
                    "unidentifiable",
                ),
                "evidence_locator": "T1 的高技能入户条件是‘缴纳佛山社保满6个月’；C1 把地域扩大为‘广东省内任一城市’，时长同为6个月。",
                "rationale": "冲突只落在参保地域这一适用范围，核心不是一般允许/禁止反转。Query+C1 没有正确地域值或风险标记，方法侧无法识别该候选错误。",
            },
            "仅替换资格条件中的地域范围，避免与时长或资格证条件混合。",
        )
    )

    target_id = "checkyourfact_1378"
    target_ix = druid["ids"].index(target_id)
    target_raw = druid["chunks"][target_ix]
    candidate_text = "Ford created this pride-themed commercial in 2023."
    cases.append(
        {
            "case_id": "RF-P2P3-C318",
            "replaces_case_id": REPLACEMENT_MAP["RF-P2P3-C318"],
            "quota_cell": "version_or_time",
            "dataset_id": "Lo/rerankers-and-lexical-similarities:DRUID",
            "dataset_revision": DRUID_REVISION,
            "split_role": SPLIT_ROLE,
            "query_id": druid["claim_id"],
            "query_text": druid["question"],
            "target_equivalence_group_id": "druid:checkyourfact_1378:commercial-created-2022",
            "target_references": [
                {
                    "official_record_id": target_id,
                    "display_text": target_raw,
                    "raw_content_sha256": sha256_bytes(target_raw.encode("utf-8")),
                }
            ],
            "candidates": [
                {
                    "candidate_id": "C1",
                    "display_text": candidate_text,
                    "method_view_metadata": {},
                    "provenance": {
                        "origin": "synthetic",
                        "base_official_record_id": target_id,
                        "base_raw_content_sha256": sha256_bytes(target_raw.encode("utf-8")),
                        "transformation": "只把广告制作年份 2022 替换为 2023。",
                        "atomic_fact_edit_count": 1,
                        "synthetic_content_sha256": sha256_bytes(candidate_text.encode("utf-8")),
                    },
                }
            ],
            "facilitator": {
                "calibration_focus": "单一制作年份冲突；Query 与候选同意错误年份时仍不得把 Gold 当成方法信号。",
                "case_qualification_key": {
                    "target_reference_status": "valid",
                    "target_group_status": "unique",
                },
                "target_source_stance": druid["chunk_stances"][target_ix],
                "target_source_helpful": druid["is_helpful_chunk"][target_ix],
                "candidate_keys": [
                    {
                        "candidate_id": "C1",
                        "expected": expected(
                            "verified_incorrect_distractor",
                            "factual_conflict",
                            "version_or_time",
                            "unidentifiable",
                        ),
                        "evidence_locator": "T1 写明广告实际制作于2022年；C1 写为2023年。",
                        "rationale": "同一广告制作年份不相容；Query 与 C1 只重复2023这一侧，metadata 为空，也没有风险标记，方法侧不能知道2022才是正确值。",
                    }
                ],
            },
        }
    )

    cases.append(
        t2_case(
            "RF-P2P3-E05B",
            "applicability_or_condition",
            "12945",
            "t2:12945:postal-veteran-card-id-document-combination",
            ["98185"],
            t2_synthetic(
                "C1",
                "办理邮政退役军人专属服务卡时，退役证属于有效实名证件，可单独满足开户身份核验条件。",
                "98185",
                "只把退役证从辅助证件替换为可单独满足开户核验的有效实名证件。",
            ),
            {
                "candidate_id": "C1",
                "expected": expected(
                    "verified_incorrect_distractor",
                    "factual_conflict",
                    "applicability_or_condition",
                    "unidentifiable",
                ),
                "evidence_locator": "T1 写明退役证、优待证属于辅助证件，办理时仍需有效实名证件；C1 写成退役证可单独完成身份核验。",
                "rationale": "冲突只涉及所需证件组合与单证充分性，属于办理触发条件替换。Query+C1 没有正确证件组合或风险信号，方法侧无法识别错误。",
            },
            "仅替换办理材料组合中的单证充分性，不混入发卡对象或服务权益。",
        )
    )
    return cases


def validate_expected(labels: dict[str, str]) -> None:
    relevance = labels["relevance_status"]
    relation = labels["target_relation"]
    conflict = labels["conflict_type"]
    adjudicability = labels["adjudicability"]
    if relation == "equivalent":
        if relevance not in {"relevant_gold", "relevant_equivalent"}:
            raise RuntimeError(f"非法 equivalent 组合：{labels}")
        if conflict != "not_applicable" or adjudicability != "not_applicable":
            raise RuntimeError(f"非冲突行含冲突字段：{labels}")
    elif relation in {"factual_conflict", "other_incorrect"}:
        if relevance != "verified_incorrect_distractor":
            raise RuntimeError(f"错误候选的 relevance 非法：{labels}")
        if relation == "factual_conflict":
            if conflict not in {
                "version_or_time",
                "numeric",
                "negation_or_direction",
                "applicability_or_condition",
            }:
                raise RuntimeError(f"事实冲突缺少主类型：{labels}")
            if adjudicability not in {
                "detectable_only",
                "conditionally_adjudicable",
                "unidentifiable",
            }:
                raise RuntimeError(f"事实冲突缺少 adjudicability：{labels}")
        elif conflict != "not_applicable" or adjudicability != "not_applicable":
            raise RuntimeError(f"other_incorrect 含冲突字段：{labels}")
    elif relation == "unresolved":
        if relevance != "unresolved_possible_false_negative":
            raise RuntimeError(f"unresolved 组合非法：{labels}")
        if conflict != "not_applicable" or adjudicability != "not_applicable":
            raise RuntimeError(f"unresolved 含冲突字段：{labels}")
    else:
        raise RuntimeError(f"未知 target_relation：{labels}")


def candidate_stats(cases: list[dict[str, Any]]) -> tuple[int, int, int]:
    candidate_count = 0
    conflict_count = 0
    pair_count = 0
    for case in cases:
        candidate_count += len(case["candidates"])
        keys = case["facilitator"]["candidate_keys"]
        conflict_count += sum(
            row["expected"]["target_relation"] == "factual_conflict" for row in keys
        )
        pair_count += int(bool(case["facilitator"].get("pair_key")))
    return candidate_count, conflict_count, pair_count


def validate_case_structure(cases: list[dict[str, Any]]) -> None:
    case_ids = [case["case_id"] for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise RuntimeError("case_id 重复")
    for case in cases:
        if not case["target_equivalence_group_id"] or not case["target_references"]:
            raise RuntimeError(f"目标组缺失：{case['case_id']}")
        candidate_ids = [row["candidate_id"] for row in case["candidates"]]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise RuntimeError(f"candidate_id 重复：{case['case_id']}")
        qualification = case["facilitator"].get("case_qualification_key")
        if qualification != {
            "target_reference_status": "valid",
            "target_group_status": "unique",
        }:
            raise RuntimeError(f"资格 key 非法：{case['case_id']}")
        keys = case["facilitator"]["candidate_keys"]
        if {row["candidate_id"] for row in keys} != set(candidate_ids):
            raise RuntimeError(f"候选与 key 不一致：{case['case_id']}")
        for row in keys:
            validate_expected(row["expected"])
        pair_key = case["facilitator"].get("pair_key")
        if pair_key:
            if pair_key["candidate_ids"] != sorted(pair_key["candidate_ids"]):
                raise RuntimeError(f"候选对 ID 顺序不确定：{case['case_id']}")
            if set(pair_key["candidate_ids"]) - set(candidate_ids):
                raise RuntimeError(f"候选对引用不存在：{case['case_id']}")


def validate_patch_cases(cases: list[dict[str, Any]]) -> None:
    validate_case_structure(cases)
    if len(cases) != 5 or {case["case_id"] for case in cases} != set(REPLACEMENT_MAP):
        raise RuntimeError("补包必须恰好包含五个冻结替换案例")
    if Counter(case["quota_cell"] for case in cases) != Counter(PATCH_QUOTA):
        raise RuntimeError("补包配额不符合冻结设计")
    if any(case["split_role"] != SPLIT_ROLE for case in cases):
        raise RuntimeError("补包存在非法 split_role")
    if {case["replaces_case_id"] for case in cases} != REPLACED_CASE_IDS:
        raise RuntimeError("替换映射不完整")
    if any(REPLACEMENT_MAP[case["case_id"]] != case["replaces_case_id"] for case in cases):
        raise RuntimeError("替换映射错位")
    query_units = [(case["dataset_id"], case["query_id"]) for case in cases]
    if len(query_units) != len(set(query_units)):
        raise RuntimeError("补包内部复用了 Query")
    reused = {
        case["query_id"]
        for case in cases
        if (
            case["dataset_id"] == "THUIR/T2Ranking"
            and case["query_id"] in V1_T2_QUERY_IDS | V2_T2_QUERY_IDS
        )
        or (
            "DRUID" in case["dataset_id"]
            and case["query_id"] in V1_DRUID_QUERY_IDS | V2_DRUID_QUERY_IDS
        )
    }
    if reused:
        raise RuntimeError(f"补包复用了 v1/v2 Query：{sorted(reused)}")
    if candidate_stats(cases) != (5, 4, 0):
        raise RuntimeError(f"补包冻结行数不符：{candidate_stats(cases)}")
    for case in cases:
        if len(case["candidates"]) != 1:
            raise RuntimeError(f"替换案例必须只有一个候选：{case['case_id']}")
        candidate = case["candidates"][0]
        if (
            candidate["provenance"].get("origin") == "synthetic"
            and candidate["provenance"].get("atomic_fact_edit_count") != 1
        ):
            raise RuntimeError(f"合成候选不是单事实编辑：{case['case_id']}")


def verify_base(repo_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    manifest_path = repo_root / BASE_MANIFEST_PATH
    key_path = repo_root / BASE_KEY_PATH
    lock_path = repo_root / BASE_LOCK_PATH
    observed = {
        "base_manifest_sha256": sha256_file(manifest_path),
        "base_key_sha256": sha256_file(key_path),
        "base_submission_lock_sha256": sha256_file(lock_path),
    }
    expected_hashes = {
        "base_manifest_sha256": BASE_MANIFEST_SHA256,
        "base_key_sha256": BASE_KEY_SHA256,
        "base_submission_lock_sha256": BASE_LOCK_SHA256,
    }
    if observed != expected_hashes:
        raise RuntimeError(f"v2 基础包或锁定提交发生变化：{observed}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("package_version") != BASE_PACKAGE_VERSION:
        raise RuntimeError("v2 基础包版本不符")
    if manifest["outputs"]["facilitator_key.jsonl"]["sha256"] != BASE_KEY_SHA256:
        raise RuntimeError("v2 manifest 未绑定冻结 facilitator key")

    lock_hash_line = f"{BASE_LOCK_SHA256}  submission_lock.json\n"
    if lock_path.with_name("submission_lock.sha256").read_text(encoding="utf-8") != lock_hash_line:
        raise RuntimeError("v2 submission_lock.sha256 不匹配")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("answer_key_read_before_lock") is not False:
        raise RuntimeError("v2 提交未在答案键打开前锁定")
    if lock.get("master_manifest_sha256") != BASE_MANIFEST_SHA256:
        raise RuntimeError("v2 提交锁未绑定冻结管理员包")
    for row in lock.get("locked_snapshots", []):
        path = repo_root / row["snapshot_path"]
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"v2 锁定快照不是普通文件：{path}")
        if path.stat().st_size != row["size_bytes"] or sha256_file(path) != row["sha256"]:
            raise RuntimeError(f"v2 锁定快照发生变化：{path}")
    if len(lock.get("locked_snapshots", [])) != 6:
        raise RuntimeError("v2 锁定快照数量不为六")

    base_cases = read_jsonl(key_path)
    validate_case_structure(base_cases)
    if {case["case_id"] for case in base_cases} != BASE_CASE_IDS:
        raise RuntimeError("v2 基础案例集合发生变化")
    retained = [case for case in base_cases if case["case_id"] in RETAINED_CASE_IDS]
    if len(retained) != 7 or candidate_stats(retained) != (8, 5, 1):
        raise RuntimeError("v2 保留部分行数不符合 7/8/5/1 冻结设计")
    binding = {
        **observed,
        "base_manifest_path": str(BASE_MANIFEST_PATH),
        "base_key_path": str(BASE_KEY_PATH),
        "base_submission_lock_path": str(BASE_LOCK_PATH),
        "retained_case_ids": sorted(RETAINED_CASE_IDS),
        "replaced_case_ids": sorted(REPLACED_CASE_IDS),
        "locked_snapshot_count": 6,
    }
    return retained, binding


def validate_combined(
    retained: list[dict[str, Any]],
    patch_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    combined = retained + patch_cases
    validate_case_structure(combined)
    if len(combined) != 12:
        raise RuntimeError("合并后案例数不为12")
    if Counter(case["quota_cell"] for case in combined) != Counter(COMBINED_QUOTA):
        raise RuntimeError("合并后配额不符合 v2 冻结设计")
    if candidate_stats(combined) != (13, 9, 1):
        raise RuntimeError(f"合并后行数不符合 13/9/1：{candidate_stats(combined)}")
    return {
        "status": "PASS",
        "case_qualification_row_count": 12,
        "candidate_annotation_row_count": 13,
        "factual_conflict_row_count": 9,
        "pair_annotation_row_count": 1,
        "retained_base_case_count": 7,
        "patch_case_count": 5,
        "quota": COMBINED_QUOTA,
        "replacement_map": REPLACEMENT_MAP,
        "eligibility_scope": "P2 构念校准；不授权 Gate A、Gate B 或 Blind 统计",
    }


def annotator_case(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "package_version": PACKAGE_VERSION,
        "case_id": case["case_id"],
        "query_text": case["query_text"],
        "view_contract": {
            "version": VIEW_CONTRACT_VERSION,
            "target_references": "evaluation_view；可用于资格与事实关系，不得用于 adjudicability",
            "query_text": "method_view",
            "candidates[].display_text": "method_view",
            "candidates[].method_view_metadata": "method_view；仅限包内明示字段",
            "external_verification": "禁止",
        },
        "target_references": [
            {
                "reference_id": f"T{index}",
                "display_text": row["display_text"],
                "view": "evaluation_only",
            }
            for index, row in enumerate(case["target_references"], start=1)
        ],
        "candidates": [
            {
                "candidate_id": row["candidate_id"],
                "display_text": row["display_text"],
                "method_view_metadata": row.get("method_view_metadata", {}),
                "view": "method_view",
            }
            for row in case["candidates"]
        ],
    }


def find_forbidden_keys(value: Any, path: str = "$") -> list[str]:
    leaks: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in BLIND_FORBIDDEN_FIELDS:
                leaks.append(f"{path}.{key}")
            leaks.extend(find_forbidden_keys(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            leaks.extend(find_forbidden_keys(child, f"{path}[{index}]"))
    return leaks


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def template_rows(cases: list[dict[str, Any]], reviewer_id: str = "") -> dict[str, Any]:
    case_rows = [
        {
            "case_id": case["case_id"],
            "reviewer_id": reviewer_id,
            "adjudication_status": "single",
            "handbook_version": HANDBOOK_VERSION,
        }
        for case in cases
    ]
    candidate_rows = [
        {
            "case_id": case["case_id"],
            "candidate_id": candidate["candidate_id"],
            "reviewer_id": reviewer_id,
            "adjudication_status": "single",
            "handbook_version": HANDBOOK_VERSION,
        }
        for case in cases
        for candidate in case["candidates"]
    ]
    return {"case": case_rows, "candidate": candidate_rows, "pair": []}


def write_templates(output_dir: Path, cases: list[dict[str, Any]], reviewer_id: str = "") -> None:
    rows = template_rows(cases, reviewer_id)
    suffix = "_template" if not reviewer_id else ""
    write_csv(output_dir / f"case_qualification{suffix}.csv", CASE_FIELDS, rows["case"])
    write_csv(output_dir / f"candidate_annotation{suffix}.csv", CANDIDATE_FIELDS, rows["candidate"])
    write_csv(output_dir / f"pair_annotation{suffix}.csv", PAIR_FIELDS, rows["pair"])


def annotator_guide() -> str:
    return f"""# Robust Fusion P2 五例最小替换标注操作手册

- 手册版本：`{HANDBOOK_VERSION}`
- 视图契约：`{VIEW_CONTRACT_VERSION}`
- 包版本：`{PACKAGE_VERSION}`
- 用途：只补标五个替换案例；不得重做或改写 v2 的七个保留案例。

## 1. 盲标边界

只读取当前分配目录。不得读取旧标注、另一位标注员目录、管理员答案键或主持人审查材料；不得联网核证。

- `query_text`、候选 `display_text` 和候选 `method_view_metadata` 属于 method view。
- T1/Gold 正文属于 evaluation view，只能用于案例资格、相关性、事实关系和冲突类型。
- 判断 `adjudicability` 时必须完全忽略 T1/Gold；也不得使用外部常识替代包内信号。

## 2. 填写顺序与行数

1. 先完成 `case_qualification.csv` 的 5 行。
2. 只有资格为 `valid + unique` 时，才完成相应候选行。
3. 再完成 `candidate_annotation.csv` 的 5 行。
4. `pair_annotation.csv` 本轮没有数据行，只保留表头，不得新增候选对。
5. 不增删、换序或重命名行列；保持既有 ID、`reviewer_id`、`single` 与手册版本。

## 3. 案例资格

`target_reference_status`：

- `valid`：T1 正文完整回答 Query，可承担目标参照；
- `invalid`：T1 答非所问、文本损坏或不能承担目标参照；
- `unresolved`：仅凭包内材料无法确认。

`target_group_status`：

- `unique`：实体、事实槽、时间、版本和条件边界唯一；
- `non_unique`：存在两个以上不能合并的合理目标组；
- `unresolved`：包内无法稳定确定。

任一资格字段不是 `valid + unique` 时，停止该案例的候选填写。

## 4. 候选关系

`relevance_status`：

- `relevant_gold`；
- `relevant_equivalent`；
- `verified_incorrect_distractor`；
- `unresolved_possible_false_negative`。

`target_relation`：

- `equivalent`：同一事实槽、时间和条件下答案相同或相容；
- `factual_conflict`：同一可比事实给出互不相容的值、版本、方向或条件；
- `other_incorrect`：主题相近但没回答所问槽、信息不足、实体错配或普通无关；
- `unresolved`：包内证据不足。

公开 qrel 不在盲包中，也不决定人工语义标签。主题相关但没有回答 Query 的候选不能因此升级为等价证据。

## 5. 主冲突类型

每条事实冲突只能选择一个主类：

- `version_or_time`：错误年份、日期、版本、生效期或历史/当前状态；
- `numeric`：同单位、口径和范围下的错误数字；
- `negation_or_direction`：实体、时间、范围、条件均相同，仅命题真值或方向反转；
- `applicability_or_condition`：决定答案的地域、人群、型号、阶段、资格、材料组合或触发条件被替换；
- `not_applicable`：非事实冲突。

若差异是“谁适用、在哪适用、满足哪些条件或需要哪些材料”，即使句子含“可以/无需”等词，仍优先按 `applicability_or_condition`；不能只看表面否定词。

## 6. 可裁决性

只对事实冲突填写：

- `conditionally_adjudicable`：Query+候选正文+候选元数据加冻结确定性规则，能推出正确值或唯一选择正确成员；
- `detectable_only`：method view 能稳定发现冲突或不可靠风险，但不能推出正确值；
- `unidentifiable`：method view 连稳定风险信号也没有，只有 T1 才揭示错误；
- `not_applicable`：非事实冲突。

关键边界：

- “未定稿”“年份未核验”等信号只能说明风险；如果 method view 没给正确年份，不能判 `conditionally_adjudicable`。
- Query 与候选重复同一个值，不等于独立证据，也不能用于挑出正确侧。
- 对 Query 明示输入做确定性算术或日历计算不算外部核证；凭常识猜测则不允许。

合法组合：

| `target_relation` | `relevance_status` | `conflict_type` | `adjudicability` |
| --- | --- | --- | --- |
| `equivalent` | `relevant_gold` / `relevant_equivalent` | `not_applicable` | `not_applicable` |
| `factual_conflict` | `verified_incorrect_distractor` | 四类之一 | 三类之一 |
| `other_incorrect` | `verified_incorrect_distractor` | `not_applicable` | `not_applicable` |
| `unresolved` | `unresolved_possible_false_negative` | `not_applicable` | `not_applicable` |

## 7. 人工说明字段

- `evidence_locator`：同时定位 T1 与 C1 的具体片段；若判断可裁决性，也定位候选元数据。
- `rationale`：说明比较的唯一事实槽、所用规则，以及 method view 能或不能提供什么。
- `confidence`：`high` / `medium` / `low`。
- `adjudication_status`：保留 `single`。
- `reviewer_id`：保留目录预填的 `A` 或 `B`。

## 8. 提交前检查

- 两张需填写 CSV 分别保持 5 行；候选对表保持 0 行；
- 标签、定位、理由和置信度均完整；
- 非事实冲突的 `conflict_type/adjudicability` 均为 `not_applicable`；
- 没有读取目录外材料，也没有与另一位标注员讨论；
- 只向主持人交回三张 CSV。
"""


def role_instructions(reviewer_id: str, role_dir_name: str) -> str:
    return f"""# P2 五例替换标注分配说明（标注员 {reviewer_id}）

你被分配到独立目录 `{role_dir_name}/`，`reviewer_id` 已固定为 `{reviewer_id}`。该目录是本轮唯一允许读取和写入的工作目录。

1. 阅读 `标注操作手册.md` 与 `view_contract.json`；
2. 阅读 `annotation_cases.jsonl`；
3. 填写 `case_qualification.csv` 的 5 行和 `candidate_annotation.csv` 的 5 行；
4. `pair_annotation.csv` 只保留表头，不新增行；
5. 不查看目录外旧答案、管理员材料或另一位标注员目录，不联网核证；
6. 完成后只把三张 CSV 交给主持人。

本轮只补五个替换案例，不重做 v2 已锁定的七个保留案例。

- 校准包：`{PACKAGE_VERSION}`
- 标签手册：`{HANDBOOK_VERSION}`
- 视图契约：`{VIEW_CONTRACT_VERSION}`

`package_receipt.json` 仅用于完整性核对，不含答案。
"""


def master_readme() -> str:
    return f"""# Robust Fusion P2 五例最小替换校准包

- 包版本：`{PACKAGE_VERSION}`
- 用途：替换 v2 中五个经主持人认定存在构造缺陷的案例。
- 规模：5 个案例、5 条资格记录、5 条候选记录、0 条候选对记录。
- 合并口径：与 v2 的 7 个保留案例合并后，恢复为 12 条资格、13 条候选、9 条事实冲突、1 条候选对。
- 新鲜性：五个 Query 均未在 v1/v2 出现，补包内部也不复用 Query。
- 原子性：四条合成冲突均只编辑一个主事实轴；另一个案例为自然候选。
- 盲化：标注输入不含替换位、配额、数据集、revision、官方 ID、qrel、来源、构造方式、split、目标组 ID 或答案键。
- 视图：T1/Gold 属于 evaluation view；`adjudicability` 只允许使用 Query、候选正文和候选方法侧元数据。
- 授权：只用于 P2 构念校准，不得进入 Gate A、Gate B 或 Blind 确证统计。

主持人保留 `facilitator_key.jsonl`。两名标注员只能接触各自独立目录；两份补标结果应先锁定，再打开答案键审查。v2 原提交和审查目录不得修改。
"""


def facilitator_readme(master_dir: Path) -> str:
    return f"""# P2 五例替换人工交付说明

管理员包：`{master_dir}`

1. 将 `annotator_a/` 与 `annotator_b/` 分别交给两位相互独立的标注员；每人只查看自己的目录。
2. 每人完成 5 条案例资格和 5 条候选；候选对表保持空表头。
3. 两份提交在答案键打开前另行锁定；不要覆盖本目录，也不要修改 v2 的锁定快照。
4. 最终 P2 复核使用：v2 锁定的 7 个保留案例 + 本补包的 5 个替换案例。
5. `combined_eligibility.json` 只证明设计与行数可合并，不代表补标已经通过。

本轮不是 Gate A/B 数据或结果。
"""


def verify_input(path: Path, expected_meta: dict[str, Any], full: bool) -> dict[str, Any]:
    actual_size = path.stat().st_size
    if actual_size != expected_meta["size_bytes"]:
        raise RuntimeError(f"输入大小不符：{path}（{actual_size}）")
    verification = "size_checked_sha256_inherited_from_data_audit_v4"
    if full:
        actual_hash = sha256_file(path)
        if actual_hash != expected_meta["sha256"]:
            raise RuntimeError(f"输入 SHA-256 不符：{path}（{actual_hash}）")
        verification = "sha256_recomputed"
    return {
        "path": str(path),
        "size_bytes": actual_size,
        "sha256": expected_meta["sha256"],
        "verification": verification,
    }


def write_master_package(
    repo_root: Path,
    output_dir: Path,
    cases: list[dict[str, Any]],
    source_files: list[dict[str, Any]],
    base_binding: dict[str, Any],
    combined: dict[str, Any],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=False)
    blind_cases = [annotator_case(case) for case in cases]
    leaks = [leak for row in blind_cases for leak in find_forbidden_keys(row)]
    if leaks:
        raise RuntimeError(f"盲化输入存在管理员字段：{leaks}")

    write_jsonl(output_dir / "annotation_cases.jsonl", blind_cases)
    write_jsonl(output_dir / "facilitator_key.jsonl", cases)
    write_json(output_dir / "view_contract.json", view_contract())
    write_json(output_dir / "base_v2_binding.json", base_binding)
    write_json(output_dir / "combined_eligibility.json", combined)
    (output_dir / "标注操作手册.md").write_text(annotator_guide(), encoding="utf-8")
    (output_dir / "README.md").write_text(master_readme(), encoding="utf-8")
    write_templates(output_dir, cases)

    output_names = [
        "README.md",
        "标注操作手册.md",
        "view_contract.json",
        "annotation_cases.jsonl",
        "case_qualification_template.csv",
        "candidate_annotation_template.csv",
        "pair_annotation_template.csv",
        "facilitator_key.jsonl",
        "base_v2_binding.json",
        "combined_eligibility.json",
    ]
    outputs = {
        name: {
            "size_bytes": (output_dir / name).stat().st_size,
            "sha256": sha256_file(output_dir / name),
        }
        for name in output_names
    }
    manifest = {
        "package_version": PACKAGE_VERSION,
        "handbook_version": HANDBOOK_VERSION,
        "view_contract_version": VIEW_CONTRACT_VERSION,
        "split_role": SPLIT_ROLE,
        "gate_a_authorized": False,
        "gate_b_authorized": False,
        "fresh_against_v1_and_v2": True,
        "patch_case_count": 5,
        "case_qualification_row_count": 5,
        "candidate_annotation_row_count": 5,
        "factual_conflict_row_count": 4,
        "pair_annotation_row_count": 0,
        "patch_quota": PATCH_QUOTA,
        "combined_design": combined,
        "base_v2_binding": base_binding,
        "source_files": source_files,
        "builder": {
            "path": str(Path(__file__).resolve().relative_to(repo_root)),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "outputs": outputs,
    }
    write_json(output_dir / "manifest.json", manifest)
    manifest_hash = sha256_file(output_dir / "manifest.json")
    (output_dir / "manifest.sha256").write_text(
        f"{manifest_hash}  manifest.json\n",
        encoding="utf-8",
    )
    return manifest


def write_role_package(
    master_dir: Path,
    role_dir: Path,
    cases: list[dict[str, Any]],
    reviewer_id: str,
) -> None:
    role_dir.mkdir(parents=True, exist_ok=False)
    for name in ("annotation_cases.jsonl", "标注操作手册.md", "view_contract.json"):
        shutil.copyfile(master_dir / name, role_dir / name)
    (role_dir / "INSTRUCTIONS.md").write_text(
        role_instructions(reviewer_id, role_dir.name),
        encoding="utf-8",
    )
    write_templates(role_dir, cases, reviewer_id)
    files = {
        path.name: {
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(role_dir.iterdir())
        if path.name != "package_receipt.json"
    }
    receipt = {
        "package_version": PACKAGE_VERSION,
        "handbook_version": HANDBOOK_VERSION,
        "view_contract_version": VIEW_CONTRACT_VERSION,
        "reviewer_id": reviewer_id,
        "answer_key_included": False,
        "blind_input_sha256": sha256_file(role_dir / "annotation_cases.jsonl"),
        "master_manifest_sha256": sha256_file(master_dir / "manifest.json"),
        "files": files,
    }
    write_json(role_dir / "package_receipt.json", receipt)


def validate_blank_csv(
    path: Path,
    expected_fields: list[str],
    expected_rows: list[dict[str, Any]],
) -> None:
    fields, actual_rows = read_csv(path)
    if fields != expected_fields:
        raise RuntimeError(f"CSV 表头不符：{path}")
    normalized_expected = [
        {field: str(row.get(field, "")) for field in expected_fields}
        for row in expected_rows
    ]
    if actual_rows != normalized_expected:
        raise RuntimeError(f"CSV 不再是冻结空表或预填值被修改：{path}")


def validate_existing(repo_root: Path, master_dir: Path, work_root: Path) -> dict[str, Any]:
    retained, current_binding = verify_base(repo_root)
    manifest_path = master_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_hash = sha256_file(manifest_path)
    expected_manifest_line = f"{manifest_hash}  manifest.json\n"
    if (master_dir / "manifest.sha256").read_text(encoding="utf-8") != expected_manifest_line:
        raise RuntimeError("manifest.sha256 不匹配")
    if manifest["package_version"] != PACKAGE_VERSION:
        raise RuntimeError("补包版本不匹配")
    if manifest["base_v2_binding"] != current_binding:
        raise RuntimeError("补包未绑定当前冻结 v2 基础记录")
    for name, meta in manifest["outputs"].items():
        path = master_dir / name
        if path.stat().st_size != meta["size_bytes"] or sha256_file(path) != meta["sha256"]:
            raise RuntimeError(f"管理员补包输出哈希不匹配：{name}")

    blind_rows = read_jsonl(master_dir / "annotation_cases.jsonl")
    leaks = [leak for row in blind_rows for leak in find_forbidden_keys(row)]
    if leaks:
        raise RuntimeError(f"盲化输入泄漏：{leaks}")
    if len(blind_rows) != 5 or len({row["case_id"] for row in blind_rows}) != 5:
        raise RuntimeError("盲化案例行数或 ID 不符")
    if any(row.get("view_contract", {}).get("version") != VIEW_CONTRACT_VERSION for row in blind_rows):
        raise RuntimeError("案例内视图契约缺失或版本不符")

    key_rows = read_jsonl(master_dir / "facilitator_key.jsonl")
    validate_patch_cases(key_rows)
    combined = validate_combined(retained, key_rows)
    if manifest["combined_design"] != combined:
        raise RuntimeError("manifest 的合并资格记录与实时复算不一致")
    if json.loads((master_dir / "combined_eligibility.json").read_text(encoding="utf-8")) != combined:
        raise RuntimeError("combined_eligibility.json 与实时复算不一致")

    templates = template_rows(key_rows)
    validate_blank_csv(
        master_dir / "case_qualification_template.csv",
        CASE_FIELDS,
        templates["case"],
    )
    validate_blank_csv(
        master_dir / "candidate_annotation_template.csv",
        CANDIDATE_FIELDS,
        templates["candidate"],
    )
    validate_blank_csv(
        master_dir / "pair_annotation_template.csv",
        PAIR_FIELDS,
        templates["pair"],
    )

    role_blind_hashes: dict[str, str] = {}
    for reviewer_id, dirname in (("A", "annotator_a"), ("B", "annotator_b")):
        role_dir = work_root / dirname
        actual_files = {path.name for path in role_dir.iterdir() if path.is_file()}
        if actual_files != ROLE_STATIC_FILES:
            raise RuntimeError(
                f"{dirname} 文件集合不符：缺少 {sorted(ROLE_STATIC_FILES - actual_files)}；"
                f"多出 {sorted(actual_files - ROLE_STATIC_FILES)}"
            )
        receipt = json.loads((role_dir / "package_receipt.json").read_text(encoding="utf-8"))
        if receipt["reviewer_id"] != reviewer_id or receipt["answer_key_included"] is not False:
            raise RuntimeError(f"{dirname} 回执角色或盲化状态不符")
        if receipt["master_manifest_sha256"] != manifest_hash:
            raise RuntimeError(f"{dirname} 未绑定当前管理员 manifest")
        for name, meta in receipt["files"].items():
            path = role_dir / name
            if path.stat().st_size != meta["size_bytes"] or sha256_file(path) != meta["sha256"]:
                raise RuntimeError(f"{dirname} 文件哈希不符：{name}")
        blind_hash = sha256_file(role_dir / "annotation_cases.jsonl")
        if blind_hash != sha256_file(master_dir / "annotation_cases.jsonl"):
            raise RuntimeError(f"{dirname} 的盲化输入与管理员包不一致")
        role_blind_hashes[reviewer_id] = blind_hash
        expected_rows = template_rows(key_rows, reviewer_id)
        validate_blank_csv(role_dir / "case_qualification.csv", CASE_FIELDS, expected_rows["case"])
        validate_blank_csv(
            role_dir / "candidate_annotation.csv",
            CANDIDATE_FIELDS,
            expected_rows["candidate"],
        )
        validate_blank_csv(role_dir / "pair_annotation.csv", PAIR_FIELDS, expected_rows["pair"])
    if len(set(role_blind_hashes.values())) != 1:
        raise RuntimeError("A/B 盲化输入不一致")

    delivery = json.loads((work_root / "delivery_manifest.json").read_text(encoding="utf-8"))
    delivery_hash = sha256_file(work_root / "delivery_manifest.json")
    if (work_root / "delivery_manifest.sha256").read_text(encoding="utf-8") != (
        f"{delivery_hash}  delivery_manifest.json\n"
    ):
        raise RuntimeError("delivery_manifest.sha256 不匹配")
    if delivery["master_manifest_sha256"] != manifest_hash:
        raise RuntimeError("人工交付清单未绑定管理员补包")

    return {
        "status": "PASS",
        "package_version": PACKAGE_VERSION,
        "manifest_sha256": manifest_hash,
        "delivery_manifest_sha256": delivery_hash,
        "blind_input_sha256": next(iter(role_blind_hashes.values())),
        "patch_case_count": 5,
        "patch_candidate_row_count": 5,
        "patch_factual_conflict_row_count": 4,
        "patch_pair_row_count": 0,
        "combined_case_count": 12,
        "combined_candidate_row_count": 13,
        "combined_factual_conflict_row_count": 9,
        "combined_pair_row_count": 1,
        "roles": ["A", "B"],
        "blind_forbidden_fields_absent": True,
        "fresh_against_v1_and_v2": True,
        "base_v2_lock_verified": True,
        "gate_a_authorized": False,
        "gate_b_authorized": False,
        "master_dir": str(master_dir.relative_to(repo_root)),
        "work_root": str(work_root.relative_to(repo_root)),
    }


def build_package(
    repo_root: Path,
    master_dir: Path,
    work_root: Path,
    verify_full_inputs: bool,
) -> dict[str, Any]:
    if master_dir.exists() or work_root.exists():
        raise RuntimeError(
            "目标目录已存在；为保护历史记录，本脚本拒绝覆盖。请使用新目录或运行 --validate-only。"
        )
    retained, base_binding = verify_base(repo_root)
    t2_dir = repo_root / "data/robust_fusion/public/THUIR_T2Ranking" / T2_REVISION / "data"
    druid_path = (
        repo_root
        / "data/robust_fusion/public/Lo_rerankers-and-lexical-similarities"
        / DRUID_REVISION
        / "DRUID/chunks.jsonl"
    )
    source_files = [
        verify_input(t2_dir / name, meta, verify_full_inputs)
        for name, meta in T2_INPUTS.items()
    ]
    source_files.append(verify_input(druid_path, DRUID_INPUT, verify_full_inputs))
    for row in source_files:
        row["path"] = str(Path(row["path"]).resolve().relative_to(repo_root))

    cases = build_patch_cases(t2_dir, druid_path)
    validate_patch_cases(cases)
    combined = validate_combined(retained, cases)
    write_master_package(
        repo_root,
        master_dir,
        cases,
        source_files,
        base_binding,
        combined,
    )
    work_root.mkdir(parents=True, exist_ok=False)
    write_role_package(master_dir, work_root / "annotator_a", cases, "A")
    write_role_package(master_dir, work_root / "annotator_b", cases, "B")
    (work_root / "FACILITATOR_README.md").write_text(
        facilitator_readme(master_dir.relative_to(repo_root)),
        encoding="utf-8",
    )
    delivery = {
        "delivery_version": "ROBUST-FUSION-P2-PATCH-HUMAN-DELIVERY-2026-08-29-v1",
        "package_version": PACKAGE_VERSION,
        "formal_human_entry": True,
        "facilitator_key_included_in_role_directories": False,
        "master_manifest_sha256": sha256_file(master_dir / "manifest.json"),
        "blind_input_sha256": sha256_file(master_dir / "annotation_cases.jsonl"),
        "roles": ["A", "B"],
        "patch_rows": {"case": 5, "candidate": 5, "pair": 0},
        "combined_design_rows": {"case": 12, "candidate": 13, "factual_conflict": 9, "pair": 1},
        "base_v2_submission_lock_sha256": BASE_LOCK_SHA256,
        "gate_a_authorized": False,
        "gate_b_authorized": False,
    }
    write_json(work_root / "delivery_manifest.json", delivery)
    delivery_hash = sha256_file(work_root / "delivery_manifest.json")
    (work_root / "delivery_manifest.sha256").write_text(
        f"{delivery_hash}  delivery_manifest.json\n",
        encoding="utf-8",
    )
    return validate_existing(repo_root, master_dir, work_root)


def resolve_under_repo(repo_root: Path, path: Path) -> Path:
    resolved = path if path.is_absolute() else repo_root / path
    resolved = resolved.resolve()
    if not resolved.is_relative_to(repo_root):
        raise RuntimeError(f"输出必须位于仓库内：{resolved}")
    return resolved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
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
        "--verify-full-inputs",
        action="store_true",
        help="重新计算 3.6 GB T2 corpus 及其他公开输入的 SHA-256。",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="只读校验已生成补包，不写入任何文件。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    master_dir = resolve_under_repo(repo_root, args.master_dir)
    work_root = resolve_under_repo(repo_root, args.work_root)
    if args.validate_only:
        result = validate_existing(repo_root, master_dir, work_root)
    else:
        result = build_package(
            repo_root,
            master_dir,
            work_root,
            args.verify_full_inputs,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
