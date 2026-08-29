from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import linkrag_eval.robust_fusion.r2_source_recovery_v4 as recovery_v4
from linkrag_eval.robust_fusion.r2_source_generation import (
    build_slot_registry,
    canonical_json,
    text_sha256,
)
from linkrag_eval.robust_fusion.r2_source_recovery_v4 import (
    MechanicalFailure,
    build_request_v4,
    changed_character_interval,
    execute_source_v4,
    length_rule,
    validate_stage_response,
)
from scripts.prepare_robust_fusion_r2_source_recovery_v4 import (
    assert_no_v4_live_root_before_seal,
    verify_v3_append_only,
)
from scripts.run_robust_fusion_r2_source_recovery_v4 import initialize_live_root


def empty_registry() -> dict[str, list[object]]:
    return {
        "family_keys": [],
        "text_sha256": [],
        "template_sha256": [],
        "near_duplicate_ngrams": [],
    }


def provider_response(content: str) -> dict[str, object]:
    return {
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "prompt_cache_hit_tokens": 0,
            "prompt_cache_miss_tokens": 100,
        },
        "choices": [{"message": {"content": content}}],
    }


def request_prompt(body: dict[str, Any]) -> dict[str, Any]:
    return json.loads(body["messages"][1]["content"])


def patch_single_slot(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setattr(recovery_v4, "validate_slot_registry", lambda _rows: None)
    return build_slot_registry()[0]


def fake_stage_values(raw: str, *, stage: str, **_kwargs: object) -> dict[str, str]:
    return {key: str(value) for key, value in json.loads(raw).items()}


def fake_complete(
    slot: dict[str, Any], locked_fields: dict[str, str], **_kwargs: object
) -> dict[str, Any]:
    value = {
        **{key: slot[key] for key in (
            "slot_id",
            "dataset_role",
            "language",
            "length_stratum",
            "conflict_type",
            "edit_level",
        )},
        **locked_fields,
    }
    return {
        **value,
        "proposal_sha256": hashlib.sha256(canonical_json(value).encode()).hexdigest(),
        "truth_status": "PROPOSAL_ONLY_AWAITING_INDEPENDENT_HUMAN_REVIEW",
    }


def staged_transport(body: dict[str, Any]) -> dict[str, object]:
    prompt = request_prompt(body)
    attempt = int(str(prompt["orchestration_attempt"]).rsplit("-", 1)[1])
    stage = prompt["stage"]
    content = {
        "R": {
            "query": f"query-{attempt}",
            "reference": f"reference-{attempt}",
        },
        "E": {"equivalent_candidate": f"equivalent-{attempt}"},
        "C": {"factual_conflict_candidate": f"conflict-{attempt}"},
    }[stage]
    return provider_response(json.dumps(content))


def test_stage_prompts_are_scoped_and_keep_frozen_units_and_edit_interval() -> None:
    slot = build_slot_registry()[0]
    request_r = build_request_v4(
        slot,
        stage="R",
        orchestration_attempt=1,
        response_attempt=1,
        locked_fields={},
    )
    prompt_r = request_prompt(request_r)
    assert prompt_r["exact_output_fields"] == ["query", "reference"]
    assert prompt_r["language_and_length"]["unit"] == "normalized_characters"
    assert prompt_r["language_and_length"]["frozen_minimum"] == 35
    assert request_r["thinking"] == {"type": "disabled"}
    assert request_r["response_format"] == {"type": "json_object"}

    locked = {"query": "q", "reference": "甲" * 50}
    request_e = build_request_v4(
        slot,
        stage="E",
        orchestration_attempt=1,
        response_attempt=1,
        locked_fields=locked,
    )
    prompt_e = request_prompt(request_e)
    interval = prompt_e["reference_to_candidate_edit_rule"]
    assert prompt_e["current_attempt_deepseek_generated_reference"] == "甲" * 50
    assert interval["equal_normalized_length_minimum_changed_characters"] == 1
    assert interval["equal_normalized_length_maximum_changed_characters"] == 9
    assert "query" not in canonical_json(prompt_e)


def test_chinese_english_length_units_and_all_edit_intervals_are_explicit() -> None:
    slots = build_slot_registry()
    assert length_rule(next(row for row in slots if row["condition_cell"].endswith("short_zh")))[
        "unit"
    ] == "normalized_characters"
    assert length_rule(next(row for row in slots if row["condition_cell"].endswith("short_en")))[
        "unit"
    ] == "normalized_words"
    intervals = [changed_character_interval("甲" * 100, level) for level in range(1, 5)]
    assert [(row["equal_normalized_length_minimum_changed_characters"], row[
        "equal_normalized_length_maximum_changed_characters"
    ]) for row in intervals] == [(2, 18), (8, 28), (15, 40), (22, 58)]


def test_stage_validator_rejects_r1_and_accepted_cross_slot_duplicates() -> None:
    slot = build_slot_registry()[0]
    query = "雾桥镇的灯塔维护券何时启用，每户每季能领取几张？"
    reference = (
        "雾桥镇公共事务所公告，灯塔维护券自二〇二七年五月起启用，"
        "登记家庭每季度最多领取两张，并须在月底前在线确认。"
    )
    raw = json.dumps({"query": query, "reference": reference}, ensure_ascii=False)
    registry = empty_registry()
    registry["text_sha256"] = [text_sha256(reference)]
    with pytest.raises(MechanicalFailure, match="r1_exclusion"):
        validate_stage_response(
            raw,
            slot=slot,
            stage="R",
            locked_fields={},
            exclusion_registry=registry,
            accepted_proposals=[],
        )
    prior = {
        "query": query,
        "reference": "先前参照文本",
        "equivalent_candidate": "先前等价文本",
        "factual_conflict_candidate": "先前冲突文本",
    }
    with pytest.raises(MechanicalFailure) as caught:
        validate_stage_response(
            raw,
            slot=slot,
            stage="R",
            locked_fields={},
            exclusion_registry=empty_registry(),
            accepted_proposals=[prior],
        )
    assert caught.value.detail == "accepted_r2_cross_slot_duplicate"


def test_attempt_scoped_locks_are_discarded_after_final_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slot = patch_single_slot(monkeypatch)
    monkeypatch.setattr(recovery_v4, "validate_stage_response", fake_stage_values)
    complete_calls = 0

    def fail_first_complete(
        slot: dict[str, Any], locked_fields: dict[str, str], **kwargs: object
    ) -> dict[str, Any]:
        nonlocal complete_calls
        complete_calls += 1
        if complete_calls == 1:
            raise MechanicalFailure("r1_exclusion", "assembled_only_constraint")
        return fake_complete(slot, locked_fields, **kwargs)

    monkeypatch.setattr(recovery_v4, "validate_complete_proposal", fail_first_complete)
    attempts: list[dict[str, Any]] = []
    proposals: list[dict[str, Any]] = []
    result = execute_source_v4(
        transport=staged_transport,
        exclusion_registry=empty_registry(),
        audit_sink=lambda _row: None,
        response_sink=lambda _row: None,
        stage_lock_sink=lambda _row: None,
        attempt_sink=lambda row: attempts.append(dict(row)),
        proposal_sink=lambda row: proposals.append(dict(row)),
        slots=[slot],
    )
    assert result["calls"] == 6
    assert attempts[0]["status"] == "COMPLETE_OBJECT_REJECTED_MECHANICALLY"
    assert attempts[0]["assembled_proposal_not_truth"]["reference"] == "reference-1"
    assert proposals[0]["reference"] == "reference-2"
    assert proposals[0]["source_attempt_version"].endswith("0002")


def test_first_complete_valid_object_locks_without_requesting_alternatives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slot = patch_single_slot(monkeypatch)
    monkeypatch.setattr(recovery_v4, "validate_stage_response", fake_stage_values)
    monkeypatch.setattr(recovery_v4, "validate_complete_proposal", fake_complete)
    proposals: list[dict[str, Any]] = []
    result = execute_source_v4(
        transport=staged_transport,
        exclusion_registry=empty_registry(),
        audit_sink=lambda _row: None,
        response_sink=lambda _row: None,
        stage_lock_sink=lambda _row: None,
        attempt_sink=lambda _row: None,
        proposal_sink=lambda row: proposals.append(dict(row)),
        slots=[slot],
    )
    assert result["calls"] == 3
    assert result["accepted_slots"] == 1
    assert len(proposals) == 1


def test_aggregate_stage_breaker_counts_alternating_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slot = patch_single_slot(monkeypatch)
    calls = 0

    def unique_transport(_body: dict[str, Any]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return provider_response(json.dumps({"response": calls}))

    def alternating_failure(_raw: str, **_kwargs: object) -> dict[str, str]:
        category = "schema" if calls % 2 else "language_length_surface"
        raise MechanicalFailure(category, f"alternating-{calls}")

    monkeypatch.setattr(recovery_v4, "validate_stage_response", alternating_failure)
    with pytest.raises(RuntimeError, match="aggregate stage no progress"):
        execute_source_v4(
            transport=unique_transport,
            exclusion_registry=empty_registry(),
            audit_sink=lambda _row: None,
            response_sink=lambda _row: None,
            stage_lock_sink=lambda _row: None,
            attempt_sink=lambda _row: None,
            proposal_sink=lambda _row: None,
            slots=[slot],
        )
    assert calls == 24


def test_aggregate_complete_assembly_breaker_is_exactly_24_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slot = patch_single_slot(monkeypatch)
    monkeypatch.setattr(recovery_v4, "validate_stage_response", fake_stage_values)
    monkeypatch.setattr(
        recovery_v4,
        "validate_complete_proposal",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            MechanicalFailure("r1_exclusion", "assembled-only")
        ),
    )
    attempts: list[dict[str, Any]] = []
    with pytest.raises(RuntimeError, match="aggregate complete-assembly no progress"):
        execute_source_v4(
            transport=staged_transport,
            exclusion_registry=empty_registry(),
            audit_sink=lambda _row: None,
            response_sink=lambda _row: None,
            stage_lock_sink=lambda _row: None,
            attempt_sink=lambda row: attempts.append(dict(row)),
            proposal_sink=lambda _row: None,
            slots=[slot],
        )
    assert len(attempts) == 24


def test_frozen_parser_hash_is_unchanged() -> None:
    root = Path(__file__).resolve().parents[2]
    parser = root / "src/linkrag_eval/robust_fusion/r2_source_generation.py"
    assert hashlib.sha256(parser.read_bytes()).hexdigest() == (
        "34ba67706fb5ddb0b7ac7924b153e00c8f26ca34f60914bd31cdf7efd57de65c"
    )


def test_v2_v3_evidence_is_append_only_and_hash_stable() -> None:
    verify_v3_append_only()


def test_seal_must_precede_live_root_and_replay_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "v4-live"
    assert_no_v4_live_root_before_seal(root)
    initialize_live_root(root)
    with pytest.raises(RuntimeError, match="before seal"):
        assert_no_v4_live_root_before_seal(root)
    with pytest.raises(RuntimeError, match="replay"):
        initialize_live_root(root)
