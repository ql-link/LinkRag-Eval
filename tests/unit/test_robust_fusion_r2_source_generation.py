from __future__ import annotations

import json
from pathlib import Path

import pytest

import linkrag_eval.robust_fusion.r2_source_generation as source_generation
from linkrag_eval.robust_fusion.r2_source_generation import (
    BudgetLedger,
    build_request,
    build_slot_registry,
    character_ngrams,
    dry_run_summary,
    execute_with_transport,
    parse_and_validate_proposal,
    text_sha256,
    validate_slot_registry,
    worst_case_call_usd,
)
from scripts.run_robust_fusion_r2_source_generation import (
    initialize_live_root,
    validate_authorization,
)


def empty_registry() -> dict[str, list[object]]:
    return {
        "text_sha256": [],
        "template_sha256": [],
        "near_duplicate_ngrams": [],
    }


def test_128_slots_match_all_frozen_quotas() -> None:
    slots = build_slot_registry()
    validate_slot_registry(slots)
    assert len(slots) == 128
    assert sum(row["fixed_candidate_count"] for row in slots) == 256


def test_request_is_nonthinking_json_and_contains_no_research_payload() -> None:
    request = build_request(build_slot_registry()[0], attempt=1)
    assert request["model"] == "deepseek-v4-flash"
    assert request["thinking"] == {"type": "disabled"}
    assert request["response_format"] == {"type": "json_object"}
    serialized = json.dumps(request)
    assert "main_similarity" not in serialized and "human_score" not in serialized
    assert "candidate_similarity.jsonl" not in serialized


def test_retry_only_accepts_mechanical_failure_and_stops_after_three() -> None:
    slot = build_slot_registry()[0]
    build_request(slot, attempt=2, prior_failure="schema")
    with pytest.raises(RuntimeError, match="mechanical"):
        build_request(slot, attempt=2, prior_failure="content_preference")
    with pytest.raises(RuntimeError, match="1..3"):
        build_request(slot, attempt=4, prior_failure="schema")


def test_budget_is_below_five_and_fuse_rejects_next_call() -> None:
    assert 384 * worst_case_call_usd() == pytest.approx(3.3792)
    ledger = BudgetLedger(spent_usd=4.999, calls=10)
    with pytest.raises(RuntimeError, match="5 USD"):
        ledger.reserve_next()


def test_parser_rejects_schema_and_r1_exact_collision() -> None:
    slot = build_slot_registry()[0]
    with pytest.raises(ValueError, match="schema"):
        parse_and_validate_proposal("{}", slot=slot, exclusion_registry=empty_registry())
    proposal = {
        "slot_id": slot["slot_id"],
        "dataset_role": slot["dataset_role"],
        "language": slot["language"],
        "length_stratum": slot["length_stratum"],
        "conflict_type": slot["conflict_type"],
        "edit_level": slot["edit_level"],
        "query": "青岚市社区雨水回收补贴从什么时候开始执行？",
        "reference": "青岚市公共服务中心在年度公告中确认，社区雨水回收补贴自二〇二六年三月起执行，居民每户每年可申请一次。",
        "equivalent_candidate": "青岚市公共服务中心在年度通知中说明，社区雨水回收补贴从二〇二六年三月开始执行，居民每户每年限申请一次。",
        "factual_conflict_candidate": "青岚市公共服务中心在年度公告中确认，社区雨水回收补贴自二〇二六年四月起执行，居民每户每年可申请一次。",
    }
    raw = json.dumps(proposal, ensure_ascii=False)
    parsed = parse_and_validate_proposal(
        raw, slot=slot, exclusion_registry=empty_registry()
    )
    assert parsed["truth_status"] == "PROPOSAL_ONLY_AWAITING_INDEPENDENT_HUMAN_REVIEW"
    registry = empty_registry()
    registry["text_sha256"] = [text_sha256(proposal["query"])]
    with pytest.raises(ValueError, match="r1_exclusion"):
        parse_and_validate_proposal(raw, slot=slot, exclusion_registry=registry)
    registry = empty_registry()
    registry["near_duplicate_ngrams"] = [list(character_ngrams(proposal["query"]))]
    with pytest.raises(ValueError, match="r1_exclusion"):
        parse_and_validate_proposal(raw, slot=slot, exclusion_registry=registry)


def test_dry_run_has_zero_network_and_384_unique_envelopes() -> None:
    snapshot = {
        "theoretical_max_usd": 3.3792,
    }
    result = dry_run_summary(snapshot)
    assert result["network_calls"] == 0
    assert result["api_key_read"] is False
    assert result["planned_request_envelopes"] == 384


def test_paid_runner_requires_explicit_matching_receipt(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="--allow-paid-api"):
        validate_authorization(tmp_path / "missing.json", allow_paid_api=False)


def test_live_root_is_append_only_and_refuses_replay(tmp_path: Path) -> None:
    root = tmp_path / "live"
    initialize_live_root(root)
    with pytest.raises(RuntimeError, match="replay"):
        initialize_live_root(root)


def test_transport_state_machine_stops_after_three_mechanical_failures() -> None:
    slots = build_slot_registry()
    events: list[dict[str, object]] = []

    def invalid_transport(_body: object) -> dict[str, object]:
        return {
            "usage": {"prompt_tokens": 100, "completion_tokens": 10},
            "choices": [{"message": {"content": "{}"}}],
        }

    result = execute_with_transport(
        transport=invalid_transport,
        exclusion_registry=empty_registry(),
        slots=slots,
        audit_sink=lambda event: events.append(dict(event)),
    )
    assert result["status"] == "SOURCE_GENERATION_TERMINAL_MISSING_FIXED_SLOT"
    assert result["failed_slot_id"] == "R2SRC-001"
    assert result["calls"] == 3
    assert [event["event"] for event in events] == [
        "REQUEST_DISPATCHED",
        "CALL_COMPLETED",
    ] * 3
    assert {event["request_sha256"] for event in events} == {
        row["request_sha256"] for row in result["audits"]
    }


def test_complete_state_machine_locks_exactly_128_without_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    slots = build_slot_registry()

    def accepted_parser(_raw: str, *, slot: object, **_kwargs: object) -> dict[str, object]:
        row = dict(slot)  # type: ignore[arg-type]
        return {
            **row,
            "query": f"q-{row['slot_id']}",
            "reference": f"r-{row['slot_id']}",
            "equivalent_candidate": f"e-{row['slot_id']}",
            "factual_conflict_candidate": f"c-{row['slot_id']}",
            "proposal_sha256": f"hash-{row['slot_id']}",
            "truth_status": "PROPOSAL_ONLY_AWAITING_INDEPENDENT_HUMAN_REVIEW",
        }

    monkeypatch.setattr(source_generation, "parse_and_validate_proposal", accepted_parser)

    def valid_transport(_body: object) -> dict[str, object]:
        return {
            "usage": {"prompt_tokens": 100, "completion_tokens": 200},
            "choices": [{"message": {"content": "{}"}}],
        }

    result = execute_with_transport(
        transport=valid_transport,
        exclusion_registry=empty_registry(),
        slots=slots,
    )
    assert result["status"] == "SOURCE_PROPOSALS_COMPLETE_AWAITING_HUMAN_AND_DATA_LOCK"
    assert result["accepted_slots"] == 128
    assert result["candidate_denominator"] == 256
    assert result["calls"] == 128
