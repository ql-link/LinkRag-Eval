from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import linkrag_eval.robust_fusion.r2_source_recovery_v5 as recovery_v5
from linkrag_eval.robust_fusion.r2_source_generation import (
    PROPOSAL_FIELDS,
    build_slot_registry,
    canonical_json,
)
from linkrag_eval.robust_fusion.r2_source_recovery_v5 import (
    MechanicalFailure,
    build_request_v5,
    execute_source_v5,
    scheduled_strategy,
    verify_inherited_v4_proposal,
)
from scripts.prepare_robust_fusion_r2_source_recovery_v5 import (
    _dry_request_plan,
    assert_no_v5_live_root_before_seal,
    verify_append_only_inputs,
)
from scripts.run_robust_fusion_r2_source_recovery_v5 import initialize_live_root

ROOT = Path(__file__).resolve().parents[2]
V4_ROOT = ROOT / (
    "runs/robust_fusion/r2_source_recovery_v4/robust-fusion-r2-source-recovery-v4-20260829"
)
EXCLUSION = ROOT / (
    "runs/robust_fusion/r2_measurement_v1/"
    "robust-fusion-r2-measurement-v1-20260829/exclusions/registry.json"
)


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


def inherited_stub(slot: dict[str, Any]) -> dict[str, Any]:
    values = {
        **{key: slot[key] for key in PROPOSAL_FIELDS if key in slot},
        "query": "inherited-query",
        "reference": "inherited-reference",
        "equivalent_candidate": "inherited-equivalent",
        "factual_conflict_candidate": "inherited-conflict",
    }
    return {
        **values,
        "proposal_sha256": hashlib.sha256(canonical_json(values).encode()).hexdigest(),
        "truth_status": "PROPOSAL_ONLY_AWAITING_INDEPENDENT_HUMAN_REVIEW",
        "source_attempt_version": "source-recovery-v4-attempt-0001",
    }


def fake_stage_values(raw: str, **_kwargs: object) -> dict[str, str]:
    return {key: str(value) for key, value in json.loads(raw).items()}


def fake_complete(
    slot: dict[str, Any], locked_fields: dict[str, str], **_kwargs: object
) -> dict[str, Any]:
    value = {
        **{key: slot[key] for key in PROPOSAL_FIELDS if key in slot},
        **locked_fields,
    }
    return {
        **value,
        "proposal_sha256": hashlib.sha256(canonical_json(value).encode()).hexdigest(),
        "truth_status": "PROPOSAL_ONLY_AWAITING_INDEPENDENT_HUMAN_REVIEW",
    }


def patch_two_slots(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    slots = build_slot_registry()[:2]
    monkeypatch.setattr(recovery_v5, "validate_slot_registry", lambda _rows: None)
    return slots


def staged_transport(body: dict[str, Any]) -> dict[str, object]:
    prompt = request_prompt(body)
    stage = prompt["stage"]
    attempt = prompt["orchestration_attempt"]
    content = {
        "R": {"query": f"query-{attempt}", "reference": f"reference-{attempt}"},
        "E": {"equivalent_candidate": f"equivalent-{attempt}"},
        "C": {"factual_conflict_candidate": f"conflict-{attempt}"},
    }[stage]
    return provider_response(json.dumps(content))


def test_inherited_001_is_byte_reverified_and_tamper_is_rejected(tmp_path: Path) -> None:
    registry = json.loads(EXCLUSION.read_text(encoding="utf-8"))
    inherited, receipt = verify_inherited_v4_proposal(V4_ROOT, registry)
    assert inherited["slot_id"] == "R2SRC-001"
    assert receipt["replaceable"] is False
    assert receipt["stage_locks_verified"] == 3

    copied = tmp_path / "v4"
    copied.mkdir()
    for path in V4_ROOT.iterdir():
        if path.is_file():
            (copied / path.name).write_bytes(path.read_bytes())
    accepted_path = copied / "accepted_proposals_not_truth.jsonl"
    accepted_path.write_bytes(accepted_path.read_bytes().replace(b"R2SRC-001", b"R2SRC-999"))
    with pytest.raises(RuntimeError, match="slot identity drift"):
        verify_inherited_v4_proposal(copied, registry)


def test_payload_has_substantive_frozen_recovery_without_failed_text() -> None:
    slot = build_slot_registry()[1]
    locked = {"query": "虚构问题", "reference": "甲" * 60}
    first = build_request_v5(
        slot,
        stage="E",
        orchestration_attempt=1,
        response_attempt=1,
        locked_fields=locked,
        previous_failure=None,
    )
    failure = {
        "category": "language_length_surface",
        "detail": "equivalent_candidate_edit_below_minimum",
        "metrics": {"observed_ratio": 0.0, "minimum_ratio": 0.02},
    }
    second = build_request_v5(
        slot,
        stage="E",
        orchestration_attempt=1,
        response_attempt=2,
        locked_fields=locked,
        previous_failure=failure,
    )
    p1, p2 = request_prompt(first), request_prompt(second)
    assert first["temperature"] == second["temperature"] == 0.6
    assert first["top_p"] == second["top_p"] == 0.9
    assert p2["stage_response_attempt"] == 2
    assert p2["previous_mechanical_failure"] == failure
    assert p1["recovery_directive"] != p2["recovery_directive"]
    assert (
        p2["recovery_directive"]["scheduled_strategy"]
        != p1["recovery_directive"]["scheduled_strategy"]
    )
    assert "secret failed body" not in canonical_json(p2)


def test_edit_strength_strategy_tables_are_fixed_and_finite() -> None:
    for level in range(1, 5):
        first_cycle = [scheduled_strategy("E", level, attempt) for attempt in range(1, 5)]
        second_cycle = [scheduled_strategy("E", level, attempt) for attempt in range(5, 9)]
        assert len(set(first_cycle)) == 4
        assert first_cycle == second_cycle
    assert scheduled_strategy("E", 1, 1) != scheduled_strategy("E", 4, 1)


def test_slot_001_is_never_called_and_002_starts_with_fresh_r(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slots = patch_two_slots(monkeypatch)
    monkeypatch.setattr(recovery_v5, "validate_stage_response_v5", fake_stage_values)
    monkeypatch.setattr(recovery_v5, "validate_complete_proposal", fake_complete)
    requests: list[dict[str, Any]] = []

    def transport(body: dict[str, Any]) -> dict[str, object]:
        requests.append(request_prompt(body))
        return staged_transport(body)

    proposals: list[dict[str, Any]] = []
    result = execute_source_v5(
        transport=transport,
        exclusion_registry=empty_registry(),
        inherited_proposal=inherited_stub(slots[0]),
        audit_sink=lambda _row: None,
        response_sink=lambda _row: None,
        stage_lock_sink=lambda _row: None,
        attempt_sink=lambda _row: None,
        proposal_sink=lambda row: proposals.append(dict(row)),
        slots=slots,
    )
    assert [row["stage"] for row in requests] == ["R", "E", "C"]
    assert {row["slot"]["slot_id"] for row in requests} == {"R2SRC-002"}
    assert requests[0]["orchestration_attempt"] == 1
    assert result["inherited_slots"] == 1
    assert result["newly_accepted_slots"] == 1
    assert len(proposals) == 1


def test_first_complete_pass_is_accepted_without_alternative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slots = patch_two_slots(monkeypatch)
    monkeypatch.setattr(recovery_v5, "validate_stage_response_v5", fake_stage_values)
    monkeypatch.setattr(recovery_v5, "validate_complete_proposal", fake_complete)
    result = execute_source_v5(
        transport=staged_transport,
        exclusion_registry=empty_registry(),
        inherited_proposal=inherited_stub(slots[0]),
        audit_sink=lambda _row: None,
        response_sink=lambda _row: None,
        stage_lock_sink=lambda _row: None,
        attempt_sink=lambda _row: None,
        proposal_sink=lambda _row: None,
        slots=slots,
    )
    assert result["calls"] == 3


def test_sixth_identical_response_is_completed_before_hard_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slots = patch_two_slots(monkeypatch)

    def always_invalid(_raw: str, **_kwargs: object) -> dict[str, str]:
        raise MechanicalFailure("schema", "stage_exact_fields")

    monkeypatch.setattr(recovery_v5, "validate_stage_response_v5", always_invalid)
    audit: list[dict[str, Any]] = []
    with pytest.raises(RuntimeError, match="repeated_identical_response"):
        execute_source_v5(
            transport=lambda _body: provider_response("{}"),
            exclusion_registry=empty_registry(),
            inherited_proposal=inherited_stub(slots[0]),
            audit_sink=lambda row: audit.append(dict(row)),
            response_sink=lambda _row: None,
            stage_lock_sink=lambda _row: None,
            attempt_sink=lambda _row: None,
            proposal_sink=lambda _row: None,
            slots=slots,
        )
    sixth = [row for row in audit if row.get("stage_response_attempt") == 6]
    assert [row["event"] for row in sixth] == [
        "REQUEST_DISPATCHED",
        "CALL_COMPLETED",
        "HARD_BLOCK",
    ]
    assert sixth[1]["response_sha256"] == sixth[2]["response_sha256"]


def test_identical_hash_breaker_is_scoped_to_orchestration_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slots = patch_two_slots(monkeypatch)
    monkeypatch.setattr(recovery_v5, "MAX_IDENTICAL_RESPONSE_HASHES", 2)
    monkeypatch.setattr(recovery_v5, "MAX_COMPLETE_ASSEMBLIES_WITHOUT_ACCEPTANCE", 2)
    monkeypatch.setattr(recovery_v5, "validate_stage_response_v5", fake_stage_values)
    monkeypatch.setattr(
        recovery_v5,
        "validate_complete_proposal",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            MechanicalFailure("r1_exclusion", "assembled_only")
        ),
    )
    with pytest.raises(RuntimeError, match="complete-assembly no progress"):
        execute_source_v5(
            transport=staged_transport,
            exclusion_registry=empty_registry(),
            inherited_proposal=inherited_stub(slots[0]),
            audit_sink=lambda _row: None,
            response_sink=lambda _row: None,
            stage_lock_sink=lambda _row: None,
            attempt_sink=lambda _row: None,
            proposal_sink=lambda _row: None,
            slots=slots,
        )


def test_frozen_parser_prereg_and_v4_ledgers_are_hash_stable() -> None:
    expected = {
        ROOT / "src/linkrag_eval/robust_fusion/r2_source_generation.py": (
            "34ba67706fb5ddb0b7ac7924b153e00c8f26ca34f60914bd31cdf7efd57de65c"
        ),
        ROOT / "runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/"
        "preregistration/manifest.json": (
            "b3c75dee6140c7aa57b865e592054ff5534405872efef4769b9636cccd09c71b"
        ),
        V4_ROOT / "call_audit.jsonl": (
            "3c3cb03dc85eed353d0a2c6c01d5d58c66f67754b12b4faae3955d8f136a3a86"
        ),
        V4_ROOT / "accepted_proposals_not_truth.jsonl": (
            "d1e15f11394ed15e2db8248987ba50310472ce206bb433d835144c7c6c98ee6b"
        ),
    }
    for path, digest in expected.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


def test_v2_v3_v4_and_both_diagnostics_remain_append_only() -> None:
    verify_append_only_inputs()


def test_dry_run_is_zero_network_zero_key_and_skips_001() -> None:
    receipt = _dry_request_plan()
    assert receipt["network_calls"] == 0
    assert receipt["api_key_read"] is False
    assert receipt["inherited_slots_not_called"] == 1
    assert receipt["new_fixed_slots"] == 127
    assert receipt["planned_dry_requests"] == 762


def test_seal_precedes_live_root_and_replay_is_refused(tmp_path: Path) -> None:
    live = tmp_path / "v5-live"
    assert_no_v5_live_root_before_seal(live)
    initialize_live_root(live)
    with pytest.raises(RuntimeError, match="before seal"):
        assert_no_v5_live_root_before_seal(live)
    with pytest.raises(RuntimeError, match="replay"):
        initialize_live_root(live)
