from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import linkrag_eval.robust_fusion.r2_source_recovery_v6 as recovery_v6
from linkrag_eval.robust_fusion.r2_source_execution_v2 import RecoverableTransportError
from linkrag_eval.robust_fusion.r2_source_generation import (
    PROPOSAL_FIELDS,
    build_slot_registry,
    canonical_json,
)
from linkrag_eval.robust_fusion.r2_source_recovery_v5 import MechanicalFailure
from linkrag_eval.robust_fusion.r2_source_recovery_v6 import (
    EXPECTED_MODEL_V6,
    build_request_v6,
    execute_source_v6,
    validate_ep_plan,
)
from scripts.prepare_robust_fusion_r2_source_recovery_v6 import (
    assert_no_v6_live_root_before_seal,
    dry_request_plan,
    endpoint_model_contract,
    verify_append_only_inputs,
)
from scripts.run_robust_fusion_r2_source_recovery_v6 import initialize_live_root

ROOT = Path(__file__).resolve().parents[2]
V4_ROOT = ROOT / (
    "runs/robust_fusion/r2_source_recovery_v4/robust-fusion-r2-source-recovery-v4-20260829"
)
V5_ROOT = ROOT / (
    "runs/robust_fusion/r2_source_recovery_v5/robust-fusion-r2-source-recovery-v5-20260829"
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


def patch_two_slots(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    slots = build_slot_registry()[:2]
    monkeypatch.setattr(recovery_v6, "validate_slot_registry", lambda _rows: None)
    return slots


def fake_stage_values(raw: str, **_kwargs: object) -> dict[str, str]:
    return {key: str(value) for key, value in json.loads(raw).items()}


def fake_ep(raw: str, **_kwargs: object) -> dict[str, str]:
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


def staged_transport(body: dict[str, Any]) -> dict[str, object]:
    prompt = request_prompt(body)
    stage = prompt["stage"]
    attempt = prompt["orchestration_attempt"]
    content = {
        "R": {"query": f"query-{attempt}", "reference": f"reference-{attempt}"},
        "EP": {
            "operation_type": "lexical_substitution",
            "source_span": "reference",
            "replacement_span": "restatement",
        },
        "E": {"equivalent_candidate": f"equivalent-{attempt}"},
        "C": {"factual_conflict_candidate": f"conflict-{attempt}"},
    }[stage]
    return provider_response(json.dumps(content))


def _run(
    monkeypatch: pytest.MonkeyPatch,
    *,
    transport: Any = staged_transport,
    audit: list[dict[str, Any]] | None = None,
    responses: list[dict[str, Any]] | None = None,
    attempts: list[dict[str, Any]] | None = None,
    proposals: list[dict[str, Any]] | None = None,
    provenance: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    slots = patch_two_slots(monkeypatch)
    monkeypatch.setattr(recovery_v6, "validate_stage_response_v5", fake_stage_values)
    monkeypatch.setattr(recovery_v6, "validate_ep_plan", fake_ep)
    monkeypatch.setattr(recovery_v6, "validate_complete_proposal", fake_complete)
    audit = [] if audit is None else audit
    responses = [] if responses is None else responses
    attempts = [] if attempts is None else attempts
    proposals = [] if proposals is None else proposals
    provenance = [] if provenance is None else provenance
    return execute_source_v6(
        transport=transport,
        exclusion_registry=empty_registry(),
        inherited_proposal=inherited_stub(slots[0]),
        audit_sink=lambda row: audit.append(dict(row)),
        response_sink=lambda row: responses.append(dict(row)),
        stage_lock_sink=lambda _row: None,
        attempt_sink=lambda row: attempts.append(dict(row)),
        proposal_sink=lambda row: proposals.append(dict(row)),
        provenance_sink=lambda row: provenance.append(dict(row)),
        slots=slots,
    )


def test_ep_schema_span_operation_and_no_complete_candidate() -> None:
    slot = build_slot_registry()[0]
    reference = "雾桥镇公共事务所规定灯塔券每季度领取两张并在月底确认。"
    valid = {
        "operation_type": "lexical_substitution",
        "source_span": "领取",
        "replacement_span": "申领",
    }
    assert (
        validate_ep_plan(json.dumps(valid, ensure_ascii=False), slot=slot, reference=reference)
        == valid
    )
    with pytest.raises(MechanicalFailure, match="ep_plan") as missing:
        validate_ep_plan(
            json.dumps({**valid, "source_span": "不存在"}, ensure_ascii=False),
            slot=slot,
            reference=reference,
        )
    assert missing.value.detail == "source_span_missing"
    with pytest.raises(MechanicalFailure) as operation:
        validate_ep_plan(
            json.dumps({**valid, "operation_type": "global_syntax_rewrite"}, ensure_ascii=False),
            slot=slot,
            reference=reference,
        )
    assert operation.value.detail == "operation_not_allowed"
    with pytest.raises(MechanicalFailure) as whole:
        validate_ep_plan(
            json.dumps(
                {**valid, "source_span": reference, "replacement_span": reference + "改"},
                ensure_ascii=False,
            ),
            slot=slot,
            reference=reference,
        )
    assert whole.value.detail in {"plan_contains_complete_candidate", "plan_span_too_large"}


def test_001_is_reverified_from_v4_and_cannot_be_replaced() -> None:
    registry = json.loads(EXCLUSION.read_text(encoding="utf-8"))
    inherited, receipt = recovery_v6.verify_inherited_v4_proposal(V4_ROOT, registry)
    assert inherited["slot_id"] == "R2SRC-001"
    assert receipt["replaceable"] is False
    assert receipt["unchanged_parser_and_all_mechanical_gates_pass"] is True


def test_payload_model_context_sampling_and_failure_are_frozen() -> None:
    slot = build_slot_registry()[1]
    locked_ep = {"query": "虚构问题", "reference": "甲乙丙丁戊己庚辛壬癸" * 5}
    ep = build_request_v6(
        slot,
        stage="EP",
        orchestration_attempt=1,
        response_attempt=1,
        locked_fields=locked_ep,
        previous_failure=None,
    )
    prompt_ep = request_prompt(ep)
    assert ep["model"] == EXPECTED_MODEL_V6 == "deepseek-v4-pro"
    assert ep["thinking"] == {"type": "disabled"}
    assert ep["response_format"] == {"type": "json_object"}
    assert ep["temperature"] == 0.6 and ep["top_p"] == 0.9
    assert set(prompt_ep["current_attempt_required_context"]) == {"query", "reference"}
    assert "equivalent_candidate" not in prompt_ep["current_attempt_required_context"]
    assert prompt_ep["exact_output_fields"] == [
        "operation_type",
        "source_span",
        "replacement_span",
    ]

    plan = {
        "operation_type": "lexical_substitution",
        "source_span": "甲乙",
        "replacement_span": "甲丙",
    }
    failure = {
        "category": "schema",
        "detail": "equivalent_candidate_not_unique",
        "metrics": {"normalized_equal_to_fields": ["reference"]},
    }
    e = build_request_v6(
        slot,
        stage="E",
        orchestration_attempt=1,
        response_attempt=2,
        locked_fields={**locked_ep, "ep_plan": plan},
        previous_failure=failure,
    )
    prompt_e = request_prompt(e)
    assert prompt_e["stage_response_attempt"] == 2
    assert prompt_e["previous_mechanical_failure"] == failure
    assert prompt_e["current_attempt_required_context"]["ep_plan"] == plan
    assert "secret failed response" not in canonical_json(prompt_e)
    with pytest.raises(RuntimeError, match="response text is forbidden"):
        build_request_v6(
            slot,
            stage="E",
            orchestration_attempt=1,
            response_attempt=3,
            locked_fields={**locked_ep, "ep_plan": plan},
            previous_failure={
                "category": "schema",
                "detail": "stage_exact_fields",
                "metrics": {"raw": "secret failed response"},
            },
        )


def test_001_not_called_002_uses_pro_and_mixed_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []

    def transport(body: dict[str, Any]) -> dict[str, object]:
        requests.append(body)
        return staged_transport(body)

    result = _run(monkeypatch, transport=transport, provenance=provenance)
    assert [request_prompt(row)["stage"] for row in requests] == ["R", "EP", "E", "C"]
    assert {request_prompt(row)["slot"]["slot_id"] for row in requests} == {"R2SRC-002"}
    assert {row["model"] for row in requests} == {"deepseek-v4-pro"}
    assert provenance[0]["slot_id"] == "R2SRC-001"
    assert provenance[0]["generator_model"] == "deepseek-v4-flash"
    assert provenance[0]["byte_exact_inherited_accepted_row"] is True
    assert provenance[1]["slot_id"] == "R2SRC-002"
    assert provenance[1]["generator_model"] == "deepseek-v4-pro"
    assert result["inherited_generator_model"] == "deepseek-v4-flash"
    assert result["new_generator_model"] == "deepseek-v4-pro"


def test_materialized_family_provenance_records_flash_and_pro(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposals = [
        {
            "slot_id": "R2SRC-001",
            "source_attempt_version": "source-recovery-v4-attempt-0001",
        },
        {
            "slot_id": "R2SRC-002",
            "source_attempt_version": "source-recovery-v6-attempt-0001",
            "generator_model": "deepseek-v4-pro",
            "generator_source_protocol_id": recovery_v6.SOURCE_PROTOCOL_ID_V6,
        },
    ]
    monkeypatch.setattr(
        recovery_v6,
        "_materialize_and_validate_families",
        lambda _proposals, _registry: ([{"family_id": "1"}, {"family_id": "2"}], {}),
    )
    families, validation = recovery_v6.materialize_and_validate_families(
        proposals, empty_registry()
    )
    assert families[0]["generator_model"] == "deepseek-v4-flash"
    assert families[1]["generator_model"] == "deepseek-v4-pro"
    assert families[0]["provenance_id"].startswith("deepseek-v4-flash/R2SRC-001/")
    assert families[1]["provenance_id"].startswith("deepseek-v4-pro/R2SRC-002/")
    assert validation["mixed_generator_provenance_assignment"] == "PASS"


def test_program_does_not_apply_plan_or_modify_e_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exact_e = "MODEL-E-OUTPUT-BYTE-SEQUENCE"
    proposals: list[dict[str, Any]] = []

    def transport(body: dict[str, Any]) -> dict[str, object]:
        prompt = request_prompt(body)
        if prompt["stage"] == "E":
            return provider_response(json.dumps({"equivalent_candidate": exact_e}))
        return staged_transport(body)

    _run(monkeypatch, transport=transport, proposals=proposals)
    assert proposals[0]["equivalent_candidate"] == exact_e


def test_first_complete_pass_stops_after_four_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(monkeypatch)
    assert result["calls"] == 4
    assert result["accepted_slots"] == 2


def test_six_e_failures_abandon_plan_then_restart_from_new_r(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slots = patch_two_slots(monkeypatch)
    monkeypatch.setattr(recovery_v6, "validate_ep_plan", fake_ep)
    monkeypatch.setattr(recovery_v6, "validate_complete_proposal", fake_complete)
    audit: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    stages: list[tuple[int, str, int]] = []

    def transport(body: dict[str, Any]) -> dict[str, object]:
        prompt = request_prompt(body)
        stages.append(
            (
                int(prompt["orchestration_attempt"]),
                str(prompt["stage"]),
                int(prompt["stage_response_attempt"]),
            )
        )
        return staged_transport(body)

    def stage_validator(raw: str, *, stage: str, **_kwargs: object) -> dict[str, str]:
        if stage == "E" and stages[-1][0] == 1:
            raise MechanicalFailure("schema", "equivalent_candidate_not_unique")
        return fake_stage_values(raw)

    monkeypatch.setattr(recovery_v6, "validate_stage_response_v5", stage_validator)
    result = execute_source_v6(
        transport=transport,
        exclusion_registry=empty_registry(),
        inherited_proposal=inherited_stub(slots[0]),
        audit_sink=lambda row: audit.append(dict(row)),
        response_sink=lambda _row: None,
        stage_lock_sink=lambda _row: None,
        attempt_sink=lambda row: attempts.append(dict(row)),
        proposal_sink=lambda _row: None,
        provenance_sink=lambda _row: None,
        slots=slots,
    )
    assert result["calls"] == 12
    assert stages[:8] == [(1, "R", 1), (1, "EP", 1), *[(1, "E", i) for i in range(1, 7)]]
    assert stages[8:] == [(2, "R", 1), (2, "EP", 1), (2, "E", 1), (2, "C", 1)]
    assert attempts[0]["status"] == "E_PLAN_EXHAUSTED_ATTEMPT_ABANDONED"
    sixth = [
        row
        for row in audit
        if row.get("stage") == "E"
        and row.get("orchestration_attempt") == 1
        and row.get("stage_response_attempt") == 6
    ]
    assert [row["event"] for row in sixth] == [
        "REQUEST_DISPATCHED",
        "CALL_COMPLETED",
        "ORCHESTRATION_ATTEMPT_ABANDONED",
    ]


def test_repeated_r_response_writes_completed_then_hard_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slots = patch_two_slots(monkeypatch)

    def invalid(_raw: str, **_kwargs: object) -> dict[str, str]:
        raise MechanicalFailure("schema", "stage_exact_fields")

    monkeypatch.setattr(recovery_v6, "validate_stage_response_v5", invalid)
    audit: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    with pytest.raises(RuntimeError, match="repeated_identical_response"):
        execute_source_v6(
            transport=lambda _body: provider_response("{}"),
            exclusion_registry=empty_registry(),
            inherited_proposal=inherited_stub(slots[0]),
            audit_sink=lambda row: audit.append(dict(row)),
            response_sink=lambda row: responses.append(dict(row)),
            stage_lock_sink=lambda _row: None,
            attempt_sink=lambda _row: None,
            proposal_sink=lambda _row: None,
            provenance_sink=lambda _row: None,
            slots=slots,
        )
    sixth = [row for row in audit if row.get("stage_response_attempt") == 6]
    assert [row["event"] for row in sixth] == [
        "REQUEST_DISPATCHED",
        "CALL_COMPLETED",
        "HARD_BLOCK",
    ]
    assert len(responses) == 6


def test_aggregate_stage_and_slot_attempt_breakers(monkeypatch: pytest.MonkeyPatch) -> None:
    slots = patch_two_slots(monkeypatch)
    calls = 0

    def unique_transport(_body: dict[str, Any]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return provider_response(json.dumps({"response": calls}))

    def invalid(_raw: str, **_kwargs: object) -> dict[str, str]:
        raise MechanicalFailure("schema", "stage_exact_fields")

    monkeypatch.setattr(recovery_v6, "validate_stage_response_v5", invalid)
    with pytest.raises(RuntimeError, match="aggregate_stage_no_progress"):
        execute_source_v6(
            transport=unique_transport,
            exclusion_registry=empty_registry(),
            inherited_proposal=inherited_stub(slots[0]),
            audit_sink=lambda _row: None,
            response_sink=lambda _row: None,
            stage_lock_sink=lambda _row: None,
            attempt_sink=lambda _row: None,
            proposal_sink=lambda _row: None,
            provenance_sink=lambda _row: None,
            slots=slots,
        )
    assert calls == 24

    monkeypatch.setattr(recovery_v6, "MAX_COMPLETE_ORCHESTRATION_ATTEMPTS_WITHOUT_ACCEPTANCE", 2)
    monkeypatch.setattr(recovery_v6, "validate_stage_response_v5", fake_stage_values)
    monkeypatch.setattr(recovery_v6, "validate_ep_plan", fake_ep)
    monkeypatch.setattr(
        recovery_v6,
        "validate_complete_proposal",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            MechanicalFailure("r1_exclusion", "assembled_only")
        ),
    )
    with pytest.raises(RuntimeError, match="orchestration-attempt no progress"):
        execute_source_v6(
            transport=staged_transport,
            exclusion_registry=empty_registry(),
            inherited_proposal=inherited_stub(slots[0]),
            audit_sink=lambda _row: None,
            response_sink=lambda _row: None,
            stage_lock_sink=lambda _row: None,
            attempt_sink=lambda _row: None,
            proposal_sink=lambda _row: None,
            provenance_sink=lambda _row: None,
            slots=slots,
        )


def test_permanent_model_http_error_is_archived_completed_and_hard_blocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slots = patch_two_slots(monkeypatch)
    audit: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    with pytest.raises(Exception, match="permanent provider HTTP_400"):
        execute_source_v6(
            transport=lambda _body: {
                "_v6_http_error": True,
                "status_code": 400,
                "recoverable": False,
                "response_content": '{"error":"model_not_found"}',
            },
            exclusion_registry=empty_registry(),
            inherited_proposal=inherited_stub(slots[0]),
            audit_sink=lambda row: audit.append(dict(row)),
            response_sink=lambda row: responses.append(dict(row)),
            stage_lock_sink=lambda _row: None,
            attempt_sink=lambda _row: None,
            proposal_sink=lambda _row: None,
            provenance_sink=lambda _row: None,
            slots=slots,
        )
    assert len(responses) == 1
    assert [row["event"] for row in audit[-3:]] == [
        "REQUEST_DISPATCHED",
        "CALL_COMPLETED",
        "HARD_BLOCK",
    ]
    assert audit[-1]["status"] == "PERMANENT_PROVIDER_OR_MODEL_HTTP_ERROR"


def test_eighth_transport_failure_completes_then_hard_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slots = patch_two_slots(monkeypatch)
    audit: list[dict[str, Any]] = []

    def transport(_body: dict[str, Any]) -> dict[str, object]:
        raise RecoverableTransportError("timeout")

    with pytest.raises(RuntimeError, match="consecutive transport failures"):
        execute_source_v6(
            transport=transport,
            exclusion_registry=empty_registry(),
            inherited_proposal=inherited_stub(slots[0]),
            audit_sink=lambda row: audit.append(dict(row)),
            response_sink=lambda _row: None,
            stage_lock_sink=lambda _row: None,
            attempt_sink=lambda _row: None,
            proposal_sink=lambda _row: None,
            provenance_sink=lambda _row: None,
            slots=slots,
        )
    eighth = [row for row in audit if row.get("stage_response_attempt") == 8]
    assert [row["event"] for row in eighth] == [
        "REQUEST_DISPATCHED",
        "CALL_COMPLETED",
        "HARD_BLOCK",
    ]


def test_parser_prereg_v4_and_v5_are_hash_stable() -> None:
    expected = {
        ROOT / "src/linkrag_eval/robust_fusion/r2_source_generation.py": (
            "34ba67706fb5ddb0b7ac7924b153e00c8f26ca34f60914bd31cdf7efd57de65c"
        ),
        ROOT / "runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/"
        "preregistration/manifest.json": (
            "b3c75dee6140c7aa57b865e592054ff5534405872efef4769b9636cccd09c71b"
        ),
        V4_ROOT / "accepted_proposals_not_truth.jsonl": (
            "d1e15f11394ed15e2db8248987ba50310472ce206bb433d835144c7c6c98ee6b"
        ),
        V5_ROOT / "call_audit.jsonl": (
            "39cdbffbd7b79c858c7908d9e479ebdbf838add46a029f5e449d07674157c2ba"
        ),
        V5_ROOT / "response_archive_synthetic_only.jsonl": (
            "686b23926155baff47cc54b21e777e4792cb5e85b50919e4fd7ebee08af6c4d0"
        ),
        V5_ROOT / "terminal_error.json": (
            "5d8e88cbae6f12fb0ebe986415053bed514e0989bb4c0a4d23372e03ae46e3df"
        ),
    }
    for path, digest in expected.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


def test_all_old_evidence_is_append_only() -> None:
    verify_append_only_inputs()


def test_endpoint_contract_and_dry_run_are_zero_network_zero_key() -> None:
    endpoint = endpoint_model_contract()
    assert endpoint["base_url"] == "https://api.deepseek.com/chat/completions"
    assert endpoint["model_field"] == "deepseek-v4-pro"
    assert endpoint["network_calls"] == endpoint["provider_probe_calls"] == 0
    assert endpoint["api_key_read"] is False
    dry = dry_request_plan()
    assert dry["network_calls"] == dry["provider_probe_calls"] == 0
    assert dry["api_key_read"] is False
    assert dry["inherited_slots_not_called"] == 1
    assert dry["planned_dry_requests"] == 1016
    assert dry["programmatic_text_rewriting_performed"] is False


def test_seal_precedes_live_root_and_replay_is_refused(tmp_path: Path) -> None:
    live = tmp_path / "v6-live"
    assert_no_v6_live_root_before_seal(live)
    initialize_live_root(live)
    with pytest.raises(RuntimeError, match="before seal"):
        assert_no_v6_live_root_before_seal(live)
    with pytest.raises(RuntimeError, match="replay"):
        initialize_live_root(live)
