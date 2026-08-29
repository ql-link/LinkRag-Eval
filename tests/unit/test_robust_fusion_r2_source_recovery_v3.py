from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import linkrag_eval.robust_fusion.r2_source_generation as source_v1
import linkrag_eval.robust_fusion.r2_source_recovery_v3 as recovery_v3
from linkrag_eval.robust_fusion.r2_source_generation import build_slot_registry
from linkrag_eval.robust_fusion.r2_source_recovery_v3 import (
    build_request_v3,
    execute_source_v3,
    parse_and_validate_proposal,
)
from scripts.prepare_robust_fusion_r2_source_recovery_v3 import (
    EXPECTED_PARSER_SOURCE_SHA,
    REPO_ROOT,
    V2_LIVE,
    V2_LIVE_HASHES,
    _dry_fixture,
    verify_v2_append_only,
)
from scripts.run_robust_fusion_r2_source_recovery_v3 import initialize_live_root


def empty_registry() -> dict[str, list[object]]:
    return {"family_keys": [], "text_sha256": [], "template_sha256": [], "near_duplicate_ngrams": []}


def provider_response(content: str = "{}") -> dict[str, object]:
    return {
        "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        "choices": [{"message": {"content": content}}],
    }


def test_prompt_contract_is_explicit_self_contained_and_contains_no_prior_payload() -> None:
    request = build_request_v3(build_slot_registry()[0], attempt=2, prior_failure="schema")
    serialized = json.dumps(request, ensure_ascii=False)
    assert "pairwise_distinct" in serialized
    assert "never copy reference" in serialized
    assert "syntactic reordering" in serialized
    assert "change exactly one numeric factual slot" in serialized
    assert "normalized_levenshtein" in serialized
    assert "response_archive_synthetic_only" not in serialized
    assert "79e7f2bb1a" not in serialized
    assert request["thinking"] == {"type": "disabled"}
    assert request["response_format"] == {"type": "json_object"}


def test_parser_identity_and_source_hash_are_unchanged() -> None:
    assert parse_and_validate_proposal is source_v1.parse_and_validate_proposal
    parser_source = REPO_ROOT / "src/linkrag_eval/robust_fusion/r2_source_generation.py"
    assert hashlib.sha256(parser_source.read_bytes()).hexdigest() == EXPECTED_PARSER_SOURCE_SHA


def test_parser_still_rejects_reference_copy() -> None:
    slot = build_slot_registry()[0]
    value = {
        "slot_id": slot["slot_id"],
        "dataset_role": slot["dataset_role"],
        "language": slot["language"],
        "length_stratum": slot["length_stratum"],
        "conflict_type": slot["conflict_type"],
        "edit_level": slot["edit_level"],
        "query": "雾桥镇的灯塔维护券何时启用，每户每季能领取几张？",
        "reference": "雾桥镇公共事务所公告，灯塔维护券自二〇二七年五月起启用，登记家庭每季度最多领取两张，并须在月底前在线确认。",
        "equivalent_candidate": "雾桥镇公共事务所公告，灯塔维护券自二〇二七年五月起启用，登记家庭每季度最多领取两张，并须在月底前在线确认。",
        "factual_conflict_candidate": "雾桥镇公共事务所通告，灯塔维护券自二〇二七年五月起启用，登记家庭每季度最多领取五张，并须在月底前在线确认。",
    }
    with pytest.raises(ValueError, match="schema"):
        parse_and_validate_proposal(
            json.dumps(value, ensure_ascii=False),
            slot=slot,
            exclusion_registry=empty_registry(),
        )


def test_new_dry_structural_fixture_passes_frozen_parser() -> None:
    fixture, receipt = _dry_fixture()
    assert len({source_v1.normalize_text(str(fixture[field])) for field in (
        "query", "reference", "equivalent_candidate", "factual_conflict_candidate"
    )}) == 4
    assert receipt["status"] == "DRY_STRUCTURAL_FIXTURE_PASS"
    assert receipt["provider_calls"] == 0


def test_v2_live_root_is_append_only_and_hash_stable() -> None:
    verify_v2_append_only()
    for name, expected in V2_LIVE_HASHES.items():
        assert hashlib.sha256((V2_LIVE / name).read_bytes()).hexdigest() == expected


def test_v3_live_root_replay_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "v3-live"
    initialize_live_root(root)
    with pytest.raises(RuntimeError, match="replay"):
        initialize_live_root(root)


def test_v3_state_machine_locks_first_valid_without_rewriting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    accepted: list[dict[str, object]] = []

    def parser(raw: str, *, slot: object, **_kwargs: object) -> dict[str, object]:
        nonlocal calls
        if calls <= 3:
            raise ValueError("schema")
        row = dict(slot)  # type: ignore[arg-type]
        return {
            **row,
            "query": f"unique-query-{row['slot_id']}",
            "reference": f"unique-reference-{row['slot_id']}",
            "equivalent_candidate": f"unique-equivalent-{row['slot_id']}",
            "factual_conflict_candidate": f"unique-conflict-{row['slot_id']}",
            "proposal_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "truth_status": "PROPOSAL_ONLY_AWAITING_INDEPENDENT_HUMAN_REVIEW",
        }

    monkeypatch.setattr(recovery_v3, "parse_and_validate_proposal", parser)
    monkeypatch.setattr(recovery_v3, "template_signature", lambda text: str(text))

    def transport(_body: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return provider_response(f'{{"raw_call":{calls}}}')

    result = execute_source_v3(
        transport=transport,
        exclusion_registry=empty_registry(),
        audit_sink=lambda _row: None,
        response_sink=lambda _row: None,
        proposal_sink=lambda row: accepted.append(dict(row)),
    )
    assert result["accepted_slots"] == 128
    assert result["calls"] == 131
    assert accepted[0]["source_attempt_version"] == "source-recovery-v3-attempt-0004"
    assert accepted[0]["query"] == "unique-query-R2SRC-001"
