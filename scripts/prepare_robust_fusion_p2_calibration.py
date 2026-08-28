#!/usr/bin/env python3
"""Build the 12-case P2 desktop calibration package for Robust Fusion.

This script only reads pinned public Dev data.  Its outputs are calibration-only,
must stay outside Gate A/Blind families, and deliberately keep the annotator view
separate from provenance and the facilitator key.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

T2_REVISION = "2a369a430a70979223f1b9a41b1919774d46b432"
DRUID_REVISION = "4b37ea52c1e1ad5af63a4feee9ce1cfb7348078b"
HANDBOOK_VERSION = "ROBUST-FUSION-ANNOTATION-HANDBOOK-2026-08-28-v1"
PACKAGE_VERSION = "ROBUST-FUSION-P2-CALIBRATION-2026-08-28-v1"

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

QUOTA = {
    "version_or_time": 2,
    "numeric": 2,
    "negation_or_direction": 2,
    "applicability_or_condition": 2,
    "equivalent": 1,
    "other_incorrect": 1,
    "possible_false_negative": 1,
    "wrong_consensus": 1,
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


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.write_text(
        "".join(canonical_json(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def display_text(raw: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    text = re.sub(r"(?is)<img\b[^>]*>", "", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def read_queries(path: Path, wanted: set[str]) -> dict[str, str]:
    queries: dict[str, str] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t", 1)
            if len(parts) == 2 and parts[0] in wanted:
                queries[parts[0]] = parts[1]
    if set(queries) != wanted:
        raise RuntimeError(f"missing T2 queries: {sorted(wanted - set(queries))}")
    return queries


def read_qrels(path: Path, wanted_qids: set[str]) -> dict[tuple[str, str], int]:
    qrels: dict[tuple[str, str], int] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if not parts or parts[0] not in wanted_qids:
                continue
            try:
                rel = int(parts[-1])
            except (IndexError, ValueError):
                continue
            qrels[(parts[0], parts[-2])] = rel
    return qrels


def read_passages(path: Path, wanted: set[str]) -> dict[str, str]:
    passages: dict[str, str] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t", 1)
            if len(parts) == 2 and parts[0] in wanted:
                passages[parts[0]] = parts[1]
                if len(passages) == len(wanted):
                    break
    if set(passages) != wanted:
        raise RuntimeError(f"missing T2 passages: {sorted(wanted - set(passages))}")
    return passages


def read_druid_case(path: Path, claim_id: str) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("claim_id") == claim_id:
                return row
    raise RuntimeError(f"missing DRUID claim: {claim_id}")


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


def validate_expected(labels: dict[str, str]) -> None:
    relevance = labels["relevance_status"]
    relation = labels["target_relation"]
    conflict = labels["conflict_type"]
    adjudicability = labels["adjudicability"]
    if relation == "equivalent" and relevance not in {
        "relevant_gold",
        "relevant_equivalent",
    }:
        raise RuntimeError(f"illegal equivalent labels: {labels}")
    if relation in {"factual_conflict", "other_incorrect"} and relevance != "verified_incorrect_distractor":
        raise RuntimeError(f"illegal incorrect labels: {labels}")
    if relation == "factual_conflict":
        if conflict not in {
            "version_or_time",
            "numeric",
            "negation_or_direction",
            "applicability_or_condition",
        }:
            raise RuntimeError(f"missing factual conflict type: {labels}")
        if adjudicability not in {
            "detectable_only",
            "conditionally_adjudicable",
            "unidentifiable",
        }:
            raise RuntimeError(f"missing adjudicability: {labels}")
    elif conflict != "not_applicable" or adjudicability != "not_applicable":
        raise RuntimeError(f"non-conflict has conflict-only labels: {labels}")


def build_cases(t2_dir: Path, druid_path: Path) -> list[dict[str, Any]]:
    wanted_qids = {"22", "50", "84", "85", "1708", "2341", "2965", "3320", "14948"}
    wanted_pids = {
        "33",
        "4929",
        "10204",
        "4380",
        "52941",
        "56107",
        "66863",
        "277171",
        "435952",
        "539147",
        "519215",
        "596717",
        "681265",
        "68648",
        "711440",
    }
    queries = read_queries(t2_dir / "queries.dev.tsv", wanted_qids)
    qrels = read_qrels(t2_dir / "qrels.dev.tsv", wanted_qids)
    passages = read_passages(t2_dir / "collection.tsv", wanted_pids)
    druid = read_druid_case(druid_path, "checkyourfact_1280")

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
            "provenance": {
                "origin": "natural",
                "official_record_id": pid,
                "source_qrel": qrels.get((qid, pid), "unjudged"),
                "raw_content_sha256": sha256_bytes(raw.encode("utf-8")),
            },
        }

    def t2_synthetic(
        candidate_id: str,
        qid: str,
        base_pid: str,
        text: str,
        edit: str,
    ) -> dict[str, Any]:
        return {
            "candidate_id": candidate_id,
            "display_text": text,
            "provenance": {
                "origin": "synthetic",
                "base_official_record_id": base_pid,
                "base_source_qrel": qrels.get((qid, base_pid), "unjudged"),
                "base_raw_content_sha256": sha256_bytes(passages[base_pid].encode("utf-8")),
                "transformation": edit,
                "synthetic_content_sha256": sha256_bytes(text.encode("utf-8")),
                "atomic_edit_count": 1,
            },
        }

    def t2_case(
        case_id: str,
        quota_cell: str,
        qid: str,
        target_group: str,
        target_pids: list[str],
        candidates: list[dict[str, Any]],
        keys: list[dict[str, Any]],
        calibration_focus: str,
        pair_key: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "case_id": case_id,
            "quota_cell": quota_cell,
            "dataset_id": "THUIR/T2Ranking",
            "dataset_revision": T2_REVISION,
            "split_role": "P2_DESKTOP_CALIBRATION_ONLY",
            "query_id": qid,
            "query_text": queries[qid],
            "target_equivalence_group_id": target_group,
            "target_references": [t2_ref(pid) for pid in target_pids],
            "candidates": candidates,
            "facilitator": {
                "calibration_focus": calibration_focus,
                "case_qualification_key": {
                    "target_reference_status": "valid",
                    "target_group_status": "unique",
                },
                "target_source_qrels": {
                    pid: qrels.get((qid, pid), "unjudged") for pid in target_pids
                },
                "candidate_keys": keys,
                "pair_key": pair_key,
            },
        }

    cases: list[dict[str, Any]] = []
    cases.append(
        t2_case(
            "RF-CAL-01",
            "version_or_time",
            "14948",
            "t2:14948:2021-final-inner-road-rule",
            ["56107"],
            [t2_natural("C1", "14948", "68648")],
            [
                {
                    "candidate_id": "C1",
                    "expected": expected(
                        "verified_incorrect_distractor",
                        "factual_conflict",
                        "version_or_time",
                        "conditionally_adjudicable",
                    ),
                    "evidence_locator": "Target states the final 6 May notice; C1 says a later notice is still pending and retains the earlier time window.",
                    "rationale": "同一 2021 最新限行事实槽使用草案与已发布终版；正文中的发布状态允许按冻结版本规则选择终版。",
                }
            ],
            "区分旧版/草案与已发布终版；同时检验公开正 qrel 不自动等价。",
        )
    )
    cases.append(
        t2_case(
            "RF-CAL-02",
            "version_or_time",
            "1708",
            "t2:1708:jiangsu-2021-exam-june-7-9",
            ["52941"],
            [t2_natural("C1", "1708", "681265")],
            [
                {
                    "candidate_id": "C1",
                    "expected": expected(
                        "verified_incorrect_distractor",
                        "factual_conflict",
                        "version_or_time",
                        "detectable_only",
                    ),
                    "evidence_locator": "Target says 7–9 June; C1 says 7–8 June for the same 2021 Jiangsu exam.",
                    "rationale": "同一考试年份和事实槽给出不相容日期；仅凭两个候选可检测冲突，但 Query 本身没有给出正确日期。",
                }
            ],
            "检验同为公开正 qrel 的自然候选仍可能发生日期冲突。",
        )
    )
    cases.append(
        t2_case(
            "RF-CAL-03",
            "numeric",
            "2965",
            "t2:2965:route-distance-176.14km",
            ["4380"],
            [
                t2_synthetic(
                    "C1",
                    "2965",
                    "4380",
                    "常州市辖区到上海的该路线总距离为176,140米。",
                    "Only convert 176.14 kilometres to the exactly equivalent value 176,140 metres.",
                )
            ],
            [
                {
                    "candidate_id": "C1",
                    "expected": expected("relevant_equivalent", "equivalent"),
                    "evidence_locator": "176.14 km × 1,000 = 176,140 m.",
                    "rationale": "单位换算后数值完全相同，不得因表面数字不同标为冲突。",
                }
            ],
            "数字边界：单位换算等价，不是 numeric conflict。",
        )
    )
    cases.append(
        t2_case(
            "RF-CAL-04",
            "numeric",
            "2965",
            "t2:2965:route-distance-176.14km",
            ["4380"],
            [
                t2_synthetic(
                    "C1",
                    "2965",
                    "4380",
                    "常州市辖区到上海的该路线总距离为167.14公里。",
                    "Replace the route distance 176.14 km with the incompatible value 167.14 km; leave the fact slot unchanged.",
                )
            ],
            [
                {
                    "candidate_id": "C1",
                    "expected": expected(
                        "verified_incorrect_distractor",
                        "factual_conflict",
                        "numeric",
                        "detectable_only",
                    ),
                    "evidence_locator": "Target gives 176.14 km; C1 gives 167.14 km for the same route.",
                    "rationale": "同一单位、路线和口径下数值不相容。",
                }
            ],
            "数字边界：真正不相容的同口径数字。",
        )
    )
    cases.append(
        t2_case(
            "RF-CAL-05",
            "negation_or_direction",
            "50",
            "t2:50:flower-seeds-leaked-on-road",
            ["66863"],
            [
                t2_synthetic(
                    "C1",
                    "50",
                    "66863",
                    "主要内容：长颈鹿给鼹鼠先生寄了花籽；包裹在路上没有破，花籽没有漏出去；第二年小路开满了鲜花。",
                    "Negate only the event that the package broke and the seeds leaked; retain the remaining story summary.",
                )
            ],
            [
                {
                    "candidate_id": "C1",
                    "expected": expected(
                        "verified_incorrect_distractor",
                        "factual_conflict",
                        "negation_or_direction",
                        "detectable_only",
                    ),
                    "evidence_locator": "Target says the package had a hole and its contents leaked; C1 explicitly negates that event.",
                    "rationale": "同一故事事件被显式否定；保留的结果句不会把否定变成普通漏信息。",
                }
            ],
            "显式否定，而不是仅凭是否出现否定词进行机械分类。",
        )
    )
    cases.append(
        t2_case(
            "RF-CAL-06",
            "negation_or_direction",
            "3320",
            "t2:3320:ps5-ps4-account-coexist",
            ["4929"],
            [
                t2_synthetic(
                    "C1",
                    "3320",
                    "4929",
                    "在PS5登录同一个PSN账号后，PS4上的该账号会被强制下线，两台主机不能保持同时登录。",
                    "Reverse only the account coexistence outcome from coexistence to forced logout.",
                )
            ],
            [
                {
                    "candidate_id": "C1",
                    "expected": expected(
                        "verified_incorrect_distractor",
                        "factual_conflict",
                        "negation_or_direction",
                        "detectable_only",
                    ),
                    "evidence_locator": "Target says the PS5 and PS4 accounts can coexist; C1 says PS5 login forces PS4 logout.",
                    "rationale": "两句表面重合高，但对能否共存给出相反方向。",
                }
            ],
            "语义方向反转。",
        )
    )
    cases.append(
        t2_case(
            "RF-CAL-07",
            "applicability_or_condition",
            "85",
            "t2:85:meal-depends-on-airline-and-fare",
            ["277171"],
            [
                t2_synthetic(
                    "C1",
                    "85",
                    "277171",
                    "所有短途航班都免费提供餐饮，无需区分航空公司或票价类型。",
                    "Remove the airline/fare applicability condition and turn the conditional statement into a universal one.",
                )
            ],
            [
                {
                    "candidate_id": "C1",
                    "expected": expected(
                        "verified_incorrect_distractor",
                        "factual_conflict",
                        "applicability_or_condition",
                        "detectable_only",
                    ),
                    "evidence_locator": "Target explicitly distinguishes full-service and low-cost airlines; C1 removes that condition.",
                    "rationale": "决定答案成立范围的航空公司/票价条件被删除并泛化为全部航班。",
                }
            ],
            "适用条件缺失。",
        )
    )
    cases.append(
        t2_case(
            "RF-CAL-08",
            "applicability_or_condition",
            "2341",
            "t2:2341:nm-card-supported-models",
            ["519215"],
            [
                t2_synthetic(
                    "C1",
                    "2341",
                    "519215",
                    "NM存储卡适用于三星Galaxy S21系列和苹果iPhone 12系列。",
                    "Replace the supported Huawei/Honor device family with unrelated Samsung and Apple device families.",
                )
            ],
            [
                {
                    "candidate_id": "C1",
                    "expected": expected(
                        "verified_incorrect_distractor",
                        "factual_conflict",
                        "applicability_or_condition",
                        "detectable_only",
                    ),
                    "evidence_locator": "Target limits support to specified Huawei/Honor families; C1 substitutes Samsung/Apple families.",
                    "rationale": "同一兼容性事实槽把适用设备家族替换成另一组设备。",
                }
            ],
            "适用对象替换。",
        )
    )
    cases.append(
        t2_case(
            "RF-CAL-09",
            "equivalent",
            "84",
            "t2:84:moon-phases-metaphor",
            ["435952"],
            [t2_natural("C1", "84", "539147")],
            [
                {
                    "candidate_id": "C1",
                    "expected": expected("relevant_equivalent", "equivalent"),
                    "evidence_locator": "Both texts explain literal moon states and the metaphor of life's imperfection/uncertainty.",
                    "rationale": "表述与展开程度不同，但对 Query 的核心含义可相互替代。",
                }
            ],
            "自然事实等价。",
        )
    )
    cases.append(
        t2_case(
            "RF-CAL-10",
            "other_incorrect",
            "84",
            "t2:84:moon-phases-metaphor",
            ["435952"],
            [t2_natural("C1", "84", "711440")],
            [
                {
                    "candidate_id": "C1",
                    "expected": expected("verified_incorrect_distractor", "other_incorrect"),
                    "evidence_locator": "C1 identifies the quotation and author but does not explain the requested meaning.",
                    "rationale": "主题和词句高度相关但没有回答事实槽，不是与目标含义互斥。",
                }
            ],
            "普通错误：主题相关但未回答，不应强标事实冲突。",
        )
    )
    cases.append(
        t2_case(
            "RF-CAL-11",
            "possible_false_negative",
            "22",
            "t2:22:chongqing-named-1189",
            ["33"],
            [t2_natural("C1", "22", "10204")],
            [
                {
                    "candidate_id": "C1",
                    "expected": expected("relevant_equivalent", "equivalent"),
                    "evidence_locator": "Both texts state that Chongqing received its name in 1189 under Song Guangzong.",
                    "rationale": "C1 未出现在该 Query 的公开 qrels 中，但正文直接回答；qrel 缺席不能作为负例。目标种子本身为低等级 qrel，也须保留人工层而不覆盖源值。",
                }
            ],
            "疑似 false negative：公开 qrel 缺席/低等级与正文可回答之间的冲突。",
        )
    )

    id_to_ix = {record_id: ix for ix, record_id in enumerate(druid["ids"])}
    target_id = "checkyourfact_1280"
    candidate_source_id = "checkyourfact_1280_ret_bn_g12"
    target_ix = id_to_ix[target_id]
    candidate_ix = id_to_ix[candidate_source_id]
    target_raw = druid["chunks"][target_ix]
    candidate_raw = druid["chunks"][candidate_ix]
    synthetic_wrong = (
        'Warren Buffett said, "You will continue to suffer if you have an emotional '
        'reaction to everything that is said to you," and described restraint as true power.'
    )
    cases.append(
        {
            "case_id": "RF-CAL-12",
            "quota_cell": "wrong_consensus",
            "dataset_id": "Lo/rerankers-and-lexical-similarities:DRUID",
            "dataset_revision": DRUID_REVISION,
            "split_role": "P2_DESKTOP_CALIBRATION_ONLY",
            "query_id": druid["claim_id"],
            "query_text": druid["question"],
            "target_equivalence_group_id": "druid:checkyourfact_1280:refutation",
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
                    "display_text": candidate_raw,
                    "provenance": {
                        "origin": "natural",
                        "official_record_id": candidate_source_id,
                        "source_stance": druid["chunk_stances"][candidate_ix],
                        "source_helpful": druid["is_helpful_chunk"][candidate_ix],
                        "raw_content_sha256": sha256_bytes(candidate_raw.encode("utf-8")),
                    },
                },
                {
                    "candidate_id": "C2",
                    "display_text": synthetic_wrong,
                    "provenance": {
                        "origin": "synthetic",
                        "base_official_record_id": candidate_source_id,
                        "base_raw_content_sha256": sha256_bytes(candidate_raw.encode("utf-8")),
                        "transformation": "Paraphrase the same false attribution without changing its factual value.",
                        "synthetic_content_sha256": sha256_bytes(synthetic_wrong.encode("utf-8")),
                        "atomic_edit_count": 0,
                    },
                },
            ],
            "facilitator": {
                "calibration_focus": "错误共识：两个候选相互同意不代表它们与目标事实等价。",
                "case_qualification_key": {
                    "target_reference_status": "valid",
                    "target_group_status": "unique",
                },
                "target_source_stance": druid["chunk_stances"][target_ix],
                "target_source_helpful": druid["is_helpful_chunk"][target_ix],
                "candidate_keys": [
                    {
                        "candidate_id": candidate_id,
                        "expected": expected(
                            "verified_incorrect_distractor",
                            "factual_conflict",
                            "negation_or_direction",
                            "detectable_only",
                        ),
                        "evidence_locator": "Target reports no evidence and traces the attribution to a parody account; the candidate attributes the quote to Buffett.",
                        "rationale": "候选与目标对同一归属事实给出相反结论；两个错误候选彼此一致不能把错误共识变成正确证据。",
                    }
                    for candidate_id in ("C1", "C2")
                ],
                "pair_key": {
                    "candidate_ids": ["C1", "C2"],
                    "candidate_pair_relation": "same_fact",
                    "rationale": "两条候选都把同一句话归给 Buffett，事实值相同，即使该共同事实值是错的。",
                },
            },
        }
    )
    return cases


def validate_cases(cases: list[dict[str, Any]]) -> None:
    if len(cases) != 12:
        raise RuntimeError(f"expected 12 cases, got {len(cases)}")
    ids = [case["case_id"] for case in cases]
    if len(set(ids)) != len(ids):
        raise RuntimeError("duplicate case IDs")
    quota = Counter(case["quota_cell"] for case in cases)
    if dict(quota) != QUOTA:
        raise RuntimeError(f"quota mismatch: {dict(quota)} != {QUOTA}")
    for case in cases:
        if case["split_role"] != "P2_DESKTOP_CALIBRATION_ONLY":
            raise RuntimeError(f"illegal split role: {case['case_id']}")
        if not case["target_equivalence_group_id"] or not case["target_references"]:
            raise RuntimeError(f"missing target group: {case['case_id']}")
        candidate_ids = [candidate["candidate_id"] for candidate in case["candidates"]]
        if len(set(candidate_ids)) != len(candidate_ids):
            raise RuntimeError(f"duplicate candidate IDs: {case['case_id']}")
        keys = case["facilitator"]["candidate_keys"]
        if {key["candidate_id"] for key in keys} != set(candidate_ids):
            raise RuntimeError(f"key mismatch: {case['case_id']}")
        qualification = case["facilitator"].get("case_qualification_key", {})
        if qualification != {
            "target_reference_status": "valid",
            "target_group_status": "unique",
        }:
            raise RuntimeError(f"case qualification key mismatch: {case['case_id']}")
        for key in keys:
            validate_expected(key["expected"])


def annotator_case(case: dict[str, Any]) -> dict[str, Any]:
    # Do not leak construction origin, source qrels/stances, or expected labels.
    return {
        "case_id": case["case_id"],
        "quota_cell": case["quota_cell"],
        "dataset_id": case["dataset_id"],
        "dataset_revision": case["dataset_revision"],
        "split_role": case["split_role"],
        "query_id": case["query_id"],
        "query_text": case["query_text"],
        "target_equivalence_group_id": case["target_equivalence_group_id"],
        "target_references": [
            {
                "reference_id": f"T{ix}",
                "display_text": ref["display_text"],
            }
            for ix, ref in enumerate(case["target_references"], start=1)
        ],
        "candidates": [
            {
                "candidate_id": candidate["candidate_id"],
                "display_text": candidate["display_text"],
            }
            for candidate in case["candidates"]
        ],
    }


def write_templates(output_dir: Path, cases: list[dict[str, Any]]) -> None:
    case_fields = [
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
    with (output_dir / "case_qualification_template.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=case_fields)
        writer.writeheader()
        for case in cases:
            writer.writerow(
                {
                    "case_id": case["case_id"],
                    "adjudication_status": "single",
                    "handbook_version": HANDBOOK_VERSION,
                }
            )

    candidate_fields = [
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
    with (output_dir / "candidate_annotation_template.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=candidate_fields)
        writer.writeheader()
        for case in cases:
            for candidate in case["candidates"]:
                writer.writerow(
                    {
                        "case_id": case["case_id"],
                        "candidate_id": candidate["candidate_id"],
                        "adjudication_status": "single",
                        "handbook_version": HANDBOOK_VERSION,
                    }
                )

    pair_fields = [
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
    with (output_dir / "pair_annotation_template.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=pair_fields)
        writer.writeheader()
        for case in cases:
            pair_key = case["facilitator"].get("pair_key")
            if pair_key:
                writer.writerow(
                    {
                        "case_id": case["case_id"],
                        "candidate_id_a": pair_key["candidate_ids"][0],
                        "candidate_id_b": pair_key["candidate_ids"][1],
                        "adjudication_status": "single",
                        "handbook_version": HANDBOOK_VERSION,
                    }
                )


def verify_input(path: Path, expected_meta: dict[str, Any], full: bool) -> dict[str, Any]:
    actual_size = path.stat().st_size
    if actual_size != expected_meta["size_bytes"]:
        raise RuntimeError(f"size mismatch for {path}: {actual_size}")
    verification = "size_checked_sha256_inherited_from_data_audit_v4"
    if full:
        actual_hash = sha256_file(path)
        if actual_hash != expected_meta["sha256"]:
            raise RuntimeError(f"SHA-256 mismatch for {path}: {actual_hash}")
        verification = "sha256_recomputed"
    return {
        "path": str(path),
        "size_bytes": actual_size,
        "sha256": expected_meta["sha256"],
        "verification": verification,
    }


def build_package(repo_root: Path, output_dir: Path, verify_full_inputs: bool) -> None:
    t2_dir = (
        repo_root
        / "data/robust_fusion/public/THUIR_T2Ranking"
        / T2_REVISION
        / "data"
    )
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
    for source_file in source_files:
        source_file["path"] = str(Path(source_file["path"]).relative_to(repo_root))

    cases = build_cases(t2_dir, druid_path)
    validate_cases(cases)
    output_dir.mkdir(parents=True, exist_ok=True)

    blind_cases = [annotator_case(case) for case in cases]
    if any(
        forbidden in canonical_json(blind_cases)
        for forbidden in ('"origin"', '"source_qrel"', '"expected"', '"transformation"')
    ):
        raise RuntimeError("annotator view leaks provenance or answer-key fields")

    write_jsonl(output_dir / "annotation_cases.jsonl", blind_cases)
    write_jsonl(output_dir / "facilitator_key.jsonl", cases)
    write_templates(output_dir, cases)
    readme = f"""# Robust Fusion P2 desktop calibration package

- Package: `{PACKAGE_VERSION}`
- Handbook: `{HANDBOOK_VERSION}`
- Role: P2 desktop calibration only; never Gate A, Gate B, or Blind.
- Cases: 12; candidate-level rows: {sum(len(case['candidates']) for case in cases)}; pair rows: 1.
- Review: make one independent copy of all three CSV templates for annotator A and B. Complete case qualification before candidate/pair labels. Do not show `facilitator_key.jsonl` until both initial submissions are locked.
- Blinding: `annotation_cases.jsonl` omits natural/synthetic origin, source qrels/stances, transformations, and expected labels.
- Provenance: `facilitator_key.jsonl` is evaluation/admin view and preserves source labels without overwriting them.
- Medical data are excluded because the license is not yet closed.
- Historical Blind v4/v5 assets are excluded.

The package calibrates the handbook; agreement on these cases is not Gate A evidence and must not be pooled with later confirmatory samples.
"""
    (output_dir / "README.md").write_text(readme, encoding="utf-8")

    output_names = [
        "README.md",
        "annotation_cases.jsonl",
        "case_qualification_template.csv",
        "candidate_annotation_template.csv",
        "facilitator_key.jsonl",
        "pair_annotation_template.csv",
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
        "split_role": "P2_DESKTOP_CALIBRATION_ONLY",
        "gate_a_authorized": False,
        "gate_b_authorized": False,
        "case_count": len(cases),
        "case_qualification_row_count": len(cases),
        "candidate_annotation_row_count": sum(len(case["candidates"]) for case in cases),
        "pair_annotation_row_count": sum(
            1 for case in cases if case["facilitator"].get("pair_key")
        ),
        "quota": QUOTA,
        "source_files": source_files,
        "builder": {
            "path": str(Path(__file__).resolve().relative_to(repo_root)),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "outputs": outputs,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "manifest.sha256").write_text(
        f"{sha256_file(manifest_path)}  manifest.json\n", encoding="utf-8"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/robust_fusion/derived/p2_calibration_v1"),
    )
    parser.add_argument(
        "--verify-full-inputs",
        action="store_true",
        help="Recompute SHA-256 for the 3.6 GB T2 corpus and all other inputs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    build_package(repo_root, output_dir.resolve(), args.verify_full_inputs)


if __name__ == "__main__":
    main()
