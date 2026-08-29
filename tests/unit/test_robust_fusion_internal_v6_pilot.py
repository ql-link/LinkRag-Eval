"""Internal v6 DeepSeek Dev 先导的离线配额、原子性和费用测试。"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

import pytest

from linkrag_eval.robust_fusion.internal_v6_pilot import (
    BATCH_ID,
    CONFLICT_QUOTA,
    SCHEMA_VERSION,
    FamilySpec,
    build_family_specs,
    estimate_cost_rmb,
    extract_usage,
    price_tier,
    validate_frozen_run_config,
    validate_proposal,
)
from linkrag_eval.robust_fusion.internal_v6_review import build_blind_case


def _proposal(spec: FamilySpec) -> dict:
    target_answer = "2032年4月1日"
    target_text = f"{spec.fictional_domain}公告：雾桥计划自{target_answer}起采用新流程。"
    before = target_answer
    after = "2033年4月1日"
    return {
        "schema_version": SCHEMA_VERSION,
        "generation_id": spec.generation_id,
        "batch_id": BATCH_ID,
        "primary_conflict_type": spec.primary_conflict_type,
        "synthetic_fact": {
            "synthetic_fact_id": spec.fact_id,
            "fictional_domain": spec.fictional_domain,
            "entity_name": "雾桥计划",
            "answer_slot": "新流程生效日期",
            "target_answer": target_answer,
            "canonical_fact_statement": f"雾桥计划自{target_answer}起采用新流程。",
        },
        "query": {
            "query_id": spec.query_id,
            "text": "雾桥计划何时开始采用新流程？",
            "origin": "synthetic",
        },
        "target_evidence": {
            "document_id": spec.target_document_id,
            "text": target_text,
            "verbatim_anchor": f"自{target_answer}起采用新流程",
            "origin": "synthetic",
        },
        "equivalent_candidate": {
            "candidate_id": spec.equivalent_candidate_id,
            "text": f"新流程的启用日为{target_answer}，适用于雾桥计划。",
            "relation_proposal": "equivalent",
            "equivalence_rationale": "实体、事实槽和日期一致。",
            "origin": "synthetic",
        },
        "conflict_candidate": {
            "candidate_id": spec.conflict_candidate_id,
            "text": target_text.replace(before, after, 1),
            "relation_proposal": "factual_conflict",
            "conflict_type_proposal": spec.primary_conflict_type,
            "atomic_edit": {"before": before, "after": after},
            "conflict_rationale": "只替换生效日期。",
            "origin": "synthetic",
        },
        "surface_control_candidate": {
            "candidate_id": spec.surface_candidate_id,
            "text": "雾桥计划的新流程培训地点设在东厅，公告未讨论启用日期。",
            "relation_proposal": "other_incorrect",
            "non_conflict_rationale": "主题相同但回答的是培训地点。",
            "same_topic_terms": ["雾桥计划", "新流程"],
            "origin": "synthetic",
        },
        "family_ids": spec.family_ids,
        "uncertainty_flags": [],
    }


def test_frozen_quota_and_ids_are_complete() -> None:
    specs = build_family_specs()
    assert len(specs) == 30
    assert Counter(spec.primary_conflict_type for spec in specs) == Counter(CONFLICT_QUOTA)
    assert len({spec.generation_id for spec in specs}) == 30
    assert len({tuple(spec.family_ids.values()) for spec in specs}) == 30


def test_valid_proposal_passes_atomic_validator() -> None:
    spec = build_family_specs()[0]
    assert validate_proposal(_proposal(spec), spec) == []


def test_non_atomic_conflict_is_rejected() -> None:
    spec = build_family_specs()[0]
    proposal = _proposal(spec)
    proposal["conflict_candidate"]["text"] += "另有一处变化。"
    errors = validate_proposal(proposal, spec)
    assert "conflict_candidate.text 不是目标正文的单次精确原子替换" in errors


def test_usage_falls_back_to_cache_miss_and_costs_peak_rate() -> None:
    usage = extract_usage({"usage": {"prompt_tokens": 1_000_000, "completion_tokens": 100_000}})
    assert usage["cache_miss_input_tokens"] == 1_000_000
    assert usage["cache_partition_inferred"] is True
    assert estimate_cost_rmb(usage, "peak") == "3.900000"


def test_price_tier_uses_beijing_windows() -> None:
    # 01:30 UTC = 09:30 Asia/Shanghai，属于峰时。
    assert price_tier(datetime(2026, 8, 29, 1, 30, tzinfo=UTC)) == "peak"
    assert price_tier(datetime(2026, 8, 29, 5, 0, tzinfo=UTC)) == "off_peak"


def test_frozen_config_rejects_drift() -> None:
    with pytest.raises(RuntimeError, match="运行参数偏离冻结协议"):
        validate_frozen_run_config(
            endpoint="https://api.deepseek.com/chat/completions",
            api_key="configured",
            model="deepseek-v4-flash",
            families=29,
            temperature=0.7,
            max_tokens=8192,
            timeout_seconds=90.0,
            concurrency=6,
            max_retries=6,
        )


def test_blind_case_hides_construction_roles_and_source_ids() -> None:
    spec = build_family_specs()[0]
    case, mapping = build_blind_case(_proposal(spec), spec)
    assert case["case_id"].startswith("RF-V6HR-")
    assert {candidate["candidate_id"] for candidate in case["candidates"]} == {"C1", "C2", "C3"}
    assert {row["construction_role"] for row in mapping} == {
        "equivalent",
        "conflict",
        "surface_control",
    }
    encoded = str(case)
    assert spec.generation_id not in encoded
    assert spec.primary_conflict_type not in encoded
    assert "construction_role" not in encoded
    assert "source_candidate_id" not in encoded
