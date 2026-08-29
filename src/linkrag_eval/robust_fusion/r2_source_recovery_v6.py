"""Outcome-aware engineering recovery v6 with an EP rewrite-plan stage."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from linkrag_eval.robust_fusion.r2_measurement import normalize_text
from linkrag_eval.robust_fusion.r2_source_execution_v2 import (
    AUTHORIZATION_ID,
    MAX_CONSECUTIVE_TRANSPORT_FAILURES,
    MAX_IDENTICAL_RESPONSE_HASHES,
    PermanentProviderError,
    RecordSink,
    RecoverableTransportError,
    Transport,
    usage_and_peak_cost,
)
from linkrag_eval.robust_fusion.r2_source_execution_v2 import (
    materialize_and_validate_families as _materialize_and_validate_families,
)
from linkrag_eval.robust_fusion.r2_source_generation import (
    PROPOSAL_FIELDS,
    _language_ok,
    build_slot_registry,
    canonical_json,
    sha256_text,
    validate_slot_registry,
)
from linkrag_eval.robust_fusion.r2_source_recovery_v4 import (
    _conflict_instruction,
    changed_character_interval,
    edit_rule,
    length_rule,
    validate_complete_proposal,
)
from linkrag_eval.robust_fusion.r2_source_recovery_v5 import (
    E_STRATEGIES,
    R_STRATEGIES,
    MechanicalFailure,
    validate_stage_response_v5,
    verify_inherited_v4_proposal,
)

SOURCE_PROTOCOL_ID_V6 = "ROBUST-FUSION-R2-SOURCE-RECOVERY-2026-08-29-v6"
PROMPT_CONTRACT_ID_V6 = "ROBUST-FUSION-R2-SOURCE-EP-PLAN-2026-08-29-v6"
EXPECTED_MODEL_V6 = "deepseek-v4-pro"
INHERITED_MODEL = "deepseek-v4-flash"
INHERITED_PROTOCOL = "ROBUST-FUSION-R2-SOURCE-RECOVERY-2026-08-29-v4"
STAGES = ("R", "EP", "E", "C")
MAX_E_RESPONSES_PER_PLAN = 6
MAX_COMPLETE_STAGE_RESPONSES_WITHOUT_LOCK = 24
MAX_COMPLETE_ORCHESTRATION_ATTEMPTS_WITHOUT_ACCEPTANCE = 24
MAX_OUTPUT_TOKENS_PER_RESPONSE = 4000
FROZEN_TEMPERATURE = 0.6
FROZEN_TOP_P = 0.9
MAX_PLAN_SPAN_REFERENCE_FRACTION = 0.75
RECOVERABLE_STAGE_FAILURES = {
    "json_parse",
    "schema",
    "ep_plan",
    "language_length_surface",
    "r1_exclusion",
}
EP_OPERATION_WHITELIST = {
    1: ("lexical_substitution", "local_phrase_reorder"),
    2: ("phrase_substitution", "local_clause_reorder"),
    3: ("clause_reorder", "clause_split", "clause_merge"),
    4: ("multi_clause_rewrite", "global_syntax_rewrite"),
}
E_APPLY_STRATEGIES = (
    "apply_plan_exactly",
    "apply_plan_with_minimal_grammar_adjustment",
    "apply_plan_then_local_reorder",
    "apply_plan_with_preservation_self_check",
)


def orchestration_attempt_version(attempt: int) -> str:
    if attempt < 1:
        raise ValueError("orchestration attempt must be positive")
    return f"source-recovery-v6-attempt-{attempt:04d}"


def stage_call_version(stage: str, orchestration_attempt: int, response_attempt: int) -> str:
    if stage not in STAGES or response_attempt < 1:
        raise ValueError("invalid v6 stage call identity")
    return (
        f"{orchestration_attempt_version(orchestration_attempt)}-"
        f"stage-{stage.lower()}-{response_attempt:04d}"
    )


def scheduled_strategy(stage: str, edit_level: int, response_attempt: int) -> str:
    if stage == "R":
        sequence = R_STRATEGIES
    elif stage == "EP":
        sequence = EP_OPERATION_WHITELIST[edit_level]
    elif stage == "E":
        sequence = E_APPLY_STRATEGIES
    elif stage == "C":
        sequence = E_STRATEGIES[edit_level]
    else:
        raise ValueError("unknown v6 stage")
    return sequence[(response_attempt - 1) % len(sequence)]


def failure_specific_action(previous_failure: Mapping[str, Any] | None) -> str:
    if previous_failure is None:
        return "first_attempt_follow_all_frozen_mechanical_rules"
    category = str(previous_failure["category"])
    detail = str(previous_failure["detail"])
    if category == "json_parse":
        return "return_one_valid_json_object_only"
    if detail in {"stage_exact_fields", "empty_stage_text", "query_reference_not_unique"}:
        return "return_exact_stage_keys_and_pairwise_distinct_nonempty_values"
    if detail == "operation_not_allowed":
        return "use_the_scheduled_operation_type_from_the_frozen_edit_level_whitelist"
    if detail in {"source_span_missing", "source_span_ambiguous"}:
        return "select_one_exact_uniquely_occurring_proper_substring_of_reference"
    if detail in {"plan_span_too_large", "plan_contains_complete_candidate"}:
        return "return_only_local_source_and_replacement_spans_not_a_complete_candidate"
    if detail in {"replacement_not_unique", "replacement_language"}:
        return "make_replacement_nonempty_distinct_and_in_the_fixed_language"
    if detail == "language":
        return "use_only_the_fixed_language"
    if detail.endswith("_length"):
        return "self_count_with_the_frozen_unit_and_target_the_interior_interval"
    if detail.endswith("_not_unique"):
        return "apply_the_locked_plan_before_output_and_never_copy_reference"
    if detail.endswith("_edit_below_minimum"):
        return "increase_nonfactual_changes_into_the_explicit_changed_character_interval"
    if detail.endswith("_edit_above_maximum"):
        return "reduce_nonfactual_changes_into_the_explicit_changed_character_interval"
    if category == "r1_exclusion":
        return "invent_new_fictional_entities_and_a_new_surface_pattern_for_this_fixed_slot"
    return "follow_the_scheduled_strategy_and_all_frozen_mechanical_rules"


def _validate_previous_failure(value: Mapping[str, Any] | None) -> None:
    if value is None:
        return
    if set(value) != {"category", "detail", "metrics"}:
        raise RuntimeError("previous mechanical failure receipt schema drift")
    if value["category"] not in RECOVERABLE_STAGE_FAILURES or not isinstance(
        value["metrics"], Mapping
    ):
        raise RuntimeError("previous mechanical failure receipt value drift")
    serialized = canonical_json(value)
    if any(key in serialized for key in ("response_content", "raw", "text_excerpt")):
        raise RuntimeError("previous response text is forbidden in v6 recovery payload")


def _expected_locked_keys(stage: str) -> set[str]:
    return {
        "R": set(),
        "EP": {"query", "reference"},
        "E": {"query", "reference", "ep_plan"},
        "C": {"query", "reference", "equivalent_candidate"},
    }[stage]


def build_request_v6(
    slot: Mapping[str, Any],
    *,
    stage: str,
    orchestration_attempt: int,
    response_attempt: int,
    locked_fields: Mapping[str, Any],
    previous_failure: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if stage not in STAGES:
        raise ValueError("unknown v6 stage")
    if set(locked_fields) != _expected_locked_keys(stage):
        raise RuntimeError("attempt-scoped stage lock drift")
    _validate_previous_failure(previous_failure)
    edit_level = int(slot["edit_level"])
    strategy = scheduled_strategy(stage, edit_level, response_attempt)
    prompt: dict[str, Any] = {
        "task": "generate_one_stage_of_a_new_non_sensitive_synthetic_microfact_proposal",
        "prompt_contract_id": PROMPT_CONTRACT_ID_V6,
        "stage": stage,
        "slot": dict(slot),
        "orchestration_attempt": orchestration_attempt,
        "orchestration_attempt_version": orchestration_attempt_version(orchestration_attempt),
        "stage_response_attempt": response_attempt,
        "stage_call": stage_call_version(stage, orchestration_attempt, response_attempt),
        "previous_mechanical_failure": previous_failure,
        "recovery_directive": {
            "scheduled_strategy": strategy,
            "failure_specific_action": failure_specific_action(previous_failure),
            "selection_rule": "fixed_by_stage_edit_level_attempt_and_failure_enum_not_content",
        },
        "language_and_length": length_rule(slot),
        "output_role": "proposal_or_plan_only_not_truth_pending_independent_human_review",
        "boundaries": [
            "invent all facts and entities; use no real person or organization",
            "do not use R1, Blind, Gate, production, internal, score, or annotation content",
            "do not copy, quote, or receive any previous failed response text",
            "return exactly one JSON object with the stage fields and no prose",
            "construction roles, rewrite plans, and model outputs are never truth",
        ],
    }
    if stage == "R":
        prompt.update(
            {
                "exact_output_fields": ["query", "reference"],
                "stage_instruction": {
                    "query": (
                        "write a question in the fixed language about one entirely fictional "
                        "microfact; normalized text must differ from reference"
                    ),
                    "reference": (
                        "write the complete fictional microfact in the fixed language and target "
                        "the interior length interval"
                    ),
                },
            }
        )
    elif stage == "EP":
        prompt.update(
            {
                "exact_output_fields": [
                    "operation_type",
                    "source_span",
                    "replacement_span",
                ],
                "current_attempt_required_context": dict(locked_fields),
                "allowed_operation_types": list(EP_OPERATION_WHITELIST[edit_level]),
                "stage_instruction": (
                    "return a local rewrite plan only. source_span must be one exact uniquely "
                    "occurring proper substring of reference. replacement_span must be nonempty, "
                    "different after normalization, use the fixed language, and preserve the full "
                    "proposition. Never return a complete candidate or an equivalent_candidate field"
                ),
                "plan_span_limits": {
                    "source_and_replacement_each_strictly_less_than_reference_fraction": (
                        MAX_PLAN_SPAN_REFERENCE_FRACTION
                    )
                },
            }
        )
    elif stage == "E":
        reference = str(locked_fields["reference"])
        prompt.update(
            {
                "exact_output_fields": ["equivalent_candidate"],
                "current_attempt_required_context": dict(locked_fields),
                "reference_to_candidate_edit_rule": {
                    **edit_rule(edit_level),
                    **changed_character_interval(reference, edit_level),
                },
                "same_plan_response_limit": MAX_E_RESPONSES_PER_PLAN,
                "stage_instruction": (
                    "apply the locked EP plan yourself and return one propositionally equivalent "
                    "candidate. Never copy reference. Preserve every entity, number, date, version, "
                    "polarity, applicability condition and logical proposition"
                ),
            }
        )
    else:
        reference = str(locked_fields["reference"])
        prompt.update(
            {
                "exact_output_fields": ["factual_conflict_candidate"],
                "current_attempt_required_context": dict(locked_fields),
                "fixed_conflict_type": slot["conflict_type"],
                "reference_to_candidate_edit_rule": {
                    **edit_rule(edit_level),
                    **changed_character_interval(reference, edit_level),
                },
                "stage_instruction": (
                    f"{_conflict_instruction(str(slot['conflict_type']))}; execute the scheduled "
                    "surface strategy, keep every non-target fact unchanged, and never copy reference"
                ),
            }
        )
    return {
        "model": EXPECTED_MODEL_V6,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return exactly one JSON object for the requested stage. Apply the explicit "
                    "recovery directive. This is synthetic planning or proposal generation, never truth."
                ),
            },
            {"role": "user", "content": canonical_json(prompt)},
        ],
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "stream": False,
        "temperature": FROZEN_TEMPERATURE,
        "top_p": FROZEN_TOP_P,
        "max_tokens": MAX_OUTPUT_TOKENS_PER_RESPONSE,
    }


def _parse_exact_object(raw: str, expected_fields: set[str]) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MechanicalFailure("json_parse", "invalid_json") from exc
    if not isinstance(value, dict) or set(value) != expected_fields:
        raise MechanicalFailure("schema", "stage_exact_fields")
    return value


def validate_ep_plan(raw: str, *, slot: Mapping[str, Any], reference: str) -> dict[str, str]:
    value = _parse_exact_object(raw, {"operation_type", "source_span", "replacement_span"})
    if any(not isinstance(value[key], str) or not value[key].strip() for key in value):
        raise MechanicalFailure("schema", "empty_or_nonstring_plan_field")
    operation_type = str(value["operation_type"])
    source_span = str(value["source_span"])
    replacement_span = str(value["replacement_span"])
    allowed = EP_OPERATION_WHITELIST[int(slot["edit_level"])]
    if operation_type not in allowed:
        raise MechanicalFailure(
            "ep_plan",
            "operation_not_allowed",
            {"allowed_operation_types": list(allowed)},
        )
    occurrences = reference.count(source_span)
    if occurrences == 0:
        raise MechanicalFailure("ep_plan", "source_span_missing", {"occurrences": 0})
    if occurrences != 1:
        raise MechanicalFailure("ep_plan", "source_span_ambiguous", {"occurrences": occurrences})
    normalized_reference = normalize_text(reference)
    normalized_source = normalize_text(source_span)
    normalized_replacement = normalize_text(replacement_span)
    if normalized_replacement in {normalized_source, normalized_reference}:
        raise MechanicalFailure("ep_plan", "replacement_not_unique")
    if not _language_ok(replacement_span, str(slot["language"])):
        raise MechanicalFailure("ep_plan", "replacement_language")
    reference_length = len(normalized_reference)
    metrics = {
        "reference_normalized_characters": reference_length,
        "source_normalized_characters": len(normalized_source),
        "replacement_normalized_characters": len(normalized_replacement),
        "maximum_fraction_exclusive": MAX_PLAN_SPAN_REFERENCE_FRACTION,
    }
    if not normalized_source or normalized_source == normalized_reference:
        raise MechanicalFailure("ep_plan", "plan_contains_complete_candidate", metrics)
    if max(len(normalized_source), len(normalized_replacement)) >= (
        reference_length * MAX_PLAN_SPAN_REFERENCE_FRACTION
    ):
        raise MechanicalFailure("ep_plan", "plan_span_too_large", metrics)
    return {
        "operation_type": operation_type,
        "source_span": source_span,
        "replacement_span": replacement_span,
    }


def _response_content(response: Mapping[str, Any]) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise PermanentProviderError("provider response envelope drift") from exc
    if not isinstance(content, str):
        raise PermanentProviderError("provider response content type drift")
    return content


def _failure_receipt(exc: ValueError) -> dict[str, Any]:
    return {
        "category": getattr(exc, "category", str(exc)),
        "detail": getattr(exc, "detail", "unchanged_final_parser_rejection"),
        "metrics": dict(getattr(exc, "metrics", {})),
    }


def _stage_locked_context(
    stage: str, attempt_fields: Mapping[str, str], ep_plan: Mapping[str, str] | None
) -> dict[str, Any]:
    if stage == "R":
        return {}
    if stage == "EP":
        return {key: attempt_fields[key] for key in ("query", "reference")}
    if stage == "E":
        if ep_plan is None:
            raise RuntimeError("E stage requires an attempt-scoped EP plan")
        return {
            "query": attempt_fields["query"],
            "reference": attempt_fields["reference"],
            "ep_plan": dict(ep_plan),
        }
    return {
        "query": attempt_fields["query"],
        "reference": attempt_fields["reference"],
        "equivalent_candidate": attempt_fields["equivalent_candidate"],
    }


def materialize_and_validate_families(
    proposals: Sequence[Mapping[str, Any]], exclusion_registry: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run the frozen validator, then correct only generator provenance metadata."""
    families, validation = _materialize_and_validate_families(proposals, exclusion_registry)
    if len(families) != len(proposals):
        raise RuntimeError("materialized family/proposal count drift")
    for family, proposal in zip(families, proposals, strict=True):
        if proposal["slot_id"] == "R2SRC-001":
            model = INHERITED_MODEL
            protocol = INHERITED_PROTOCOL
        else:
            model = str(proposal.get("generator_model") or "")
            protocol = str(proposal.get("generator_source_protocol_id") or "")
            if model != EXPECTED_MODEL_V6 or protocol != SOURCE_PROTOCOL_ID_V6:
                raise RuntimeError("v6 accepted proposal generator provenance drift")
        family["provenance_id"] = (
            f"{model}/{proposal['slot_id']}/{proposal['source_attempt_version']}"
        )
        family["generator_model"] = model
        family["generator_source_protocol_id"] = protocol
    return families, {**validation, "mixed_generator_provenance_assignment": "PASS"}


def execute_source_v6(
    *,
    transport: Transport,
    exclusion_registry: Mapping[str, Any],
    inherited_proposal: Mapping[str, Any],
    audit_sink: RecordSink,
    response_sink: RecordSink,
    stage_lock_sink: RecordSink,
    attempt_sink: RecordSink,
    proposal_sink: RecordSink,
    provenance_sink: RecordSink,
    slots: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    frame = list(build_slot_registry() if slots is None else slots)
    validate_slot_registry(frame)
    if frame[0]["slot_id"] != "R2SRC-001" or inherited_proposal["slot_id"] != "R2SRC-001":
        raise RuntimeError("v6 inherited slot 001 identity drift")
    accepted: list[dict[str, Any]] = [dict(inherited_proposal)]
    inherited_provenance = {
        "slot_id": "R2SRC-001",
        "proposal_sha256": inherited_proposal["proposal_sha256"],
        "generator_model": INHERITED_MODEL,
        "generator_source_protocol_id": INHERITED_PROTOCOL,
        "imported_into_source_protocol_id": SOURCE_PROTOCOL_ID_V6,
        "byte_exact_inherited_accepted_row": True,
    }
    provenance_sink(inherited_provenance)
    audit_sink(
        {
            "source_protocol_id": SOURCE_PROTOCOL_ID_V6,
            "event": "INHERITED_PROPOSAL_HARD_LOCKED",
            **inherited_provenance,
            "replaceable": False,
            "provider_call_performed": False,
        }
    )
    request_hashes: set[str] = set()
    response_hash_counts: Counter[tuple[str, str, int, str]] = Counter()
    calls = 0
    total_cost = 0.0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    for slot in frame[1:]:
        accepted_for_slot = False
        for orchestration_attempt in range(
            1, MAX_COMPLETE_ORCHESTRATION_ATTEMPTS_WITHOUT_ACCEPTANCE + 1
        ):
            attempt_fields: dict[str, str] = {}
            ep_plan: dict[str, str] | None = None
            abandon_attempt = False
            for stage in STAGES:
                complete_responses_without_lock = 0
                response_attempt = 1
                consecutive_transport = 0
                previous_failure: dict[str, Any] | None = None
                while True:
                    locked_context = _stage_locked_context(stage, attempt_fields, ep_plan)
                    body = build_request_v6(
                        slot,
                        stage=stage,
                        orchestration_attempt=orchestration_attempt,
                        response_attempt=response_attempt,
                        locked_fields=locked_context,
                        previous_failure=previous_failure,
                    )
                    request_hash = sha256_text(canonical_json(body))
                    if request_hash in request_hashes:
                        raise RuntimeError("request replay detected")
                    request_hashes.add(request_hash)
                    base = {
                        "source_protocol_id": SOURCE_PROTOCOL_ID_V6,
                        "prompt_contract_id": PROMPT_CONTRACT_ID_V6,
                        "authorization_id": AUTHORIZATION_ID,
                        "slot_id": slot["slot_id"],
                        "orchestration_attempt": orchestration_attempt,
                        "orchestration_attempt_version": orchestration_attempt_version(
                            orchestration_attempt
                        ),
                        "stage": stage,
                        "stage_response_attempt": response_attempt,
                        "stage_call_version": stage_call_version(
                            stage, orchestration_attempt, response_attempt
                        ),
                        "request_sha256": request_hash,
                        "model": EXPECTED_MODEL_V6,
                    }
                    audit_sink({**base, "event": "REQUEST_DISPATCHED"})
                    calls += 1
                    try:
                        response = transport(body)
                    except RecoverableTransportError as exc:
                        consecutive_transport += 1
                        outcome = {
                            "category": "transport",
                            "detail": type(exc).__name__,
                            "metrics": {},
                        }
                        audit_sink(
                            {
                                **base,
                                "event": "CALL_COMPLETED",
                                "status": "RECOVERABLE_FAILURE",
                                "mechanical_outcome": outcome,
                            }
                        )
                        if consecutive_transport >= MAX_CONSECUTIVE_TRANSPORT_FAILURES:
                            audit_sink(
                                {
                                    **base,
                                    "event": "HARD_BLOCK",
                                    "status": "CONSECUTIVE_TRANSPORT_FAILURES",
                                }
                            )
                            raise RuntimeError(
                                "non-financial hard block: consecutive transport failures"
                            )
                        response_attempt += 1
                        continue
                    except PermanentProviderError as exc:
                        audit_sink(
                            {
                                **base,
                                "event": "CALL_COMPLETED",
                                "status": "PERMANENT_PROVIDER_FAILURE",
                                "mechanical_outcome": {
                                    "category": "provider",
                                    "detail": type(exc).__name__,
                                    "metrics": {},
                                },
                            }
                        )
                        audit_sink({**base, "event": "HARD_BLOCK", "status": "PROVIDER"})
                        raise
                    if response.get("_v6_http_error") is True:
                        status_code = int(response["status_code"])
                        raw_http = str(response.get("response_content") or "")
                        response_hash = sha256_text(raw_http)
                        outcome = {
                            "category": "transport"
                            if bool(response["recoverable"])
                            else "provider",
                            "detail": f"HTTP_{status_code}",
                            "metrics": {"status_code": status_code},
                        }
                        response_sink(
                            {
                                **base,
                                "response_sha256": response_hash,
                                "response_hash_scope": "http_error_body",
                                "response_content": raw_http,
                                "http_status_code": status_code,
                                "mechanical_outcome": outcome,
                            }
                        )
                        audit_sink(
                            {
                                **base,
                                "event": "CALL_COMPLETED",
                                "status": (
                                    "RECOVERABLE_FAILURE"
                                    if bool(response["recoverable"])
                                    else "PERMANENT_PROVIDER_FAILURE"
                                ),
                                "response_sha256": response_hash,
                                "response_hash_scope": "http_error_body",
                                "mechanical_outcome": outcome,
                            }
                        )
                        if not bool(response["recoverable"]):
                            audit_sink(
                                {
                                    **base,
                                    "event": "HARD_BLOCK",
                                    "status": "PERMANENT_PROVIDER_OR_MODEL_HTTP_ERROR",
                                    "response_sha256": response_hash,
                                    "mechanical_outcome": outcome,
                                }
                            )
                            raise PermanentProviderError(f"permanent provider HTTP_{status_code}")
                        consecutive_transport += 1
                        if consecutive_transport >= MAX_CONSECUTIVE_TRANSPORT_FAILURES:
                            audit_sink(
                                {
                                    **base,
                                    "event": "HARD_BLOCK",
                                    "status": "CONSECUTIVE_TRANSPORT_FAILURES",
                                    "response_sha256": response_hash,
                                    "mechanical_outcome": outcome,
                                }
                            )
                            raise RuntimeError(
                                "non-financial hard block: consecutive transport failures"
                            )
                        response_attempt += 1
                        continue
                    consecutive_transport = 0
                    envelope_hash = sha256_text(canonical_json(response))
                    try:
                        usage = usage_and_peak_cost(response)
                        raw = _response_content(response)
                    except PermanentProviderError as exc:
                        outcome = {
                            "category": "provider",
                            "detail": str(exc),
                            "metrics": {},
                        }
                        response_sink(
                            {
                                **base,
                                "response_sha256": envelope_hash,
                                "response_hash_scope": "provider_envelope",
                                "response_content": None,
                                "mechanical_outcome": outcome,
                            }
                        )
                        audit_sink(
                            {
                                **base,
                                "event": "CALL_COMPLETED",
                                "status": "PERMANENT_PROVIDER_FAILURE",
                                "response_sha256": envelope_hash,
                                "response_hash_scope": "provider_envelope",
                                "mechanical_outcome": outcome,
                            }
                        )
                        audit_sink(
                            {
                                **base,
                                "event": "HARD_BLOCK",
                                "status": "PROVIDER_ENVELOPE",
                                "response_sha256": envelope_hash,
                            }
                        )
                        raise
                    total_cost += float(usage["peak_estimated_cost_usd"])
                    total_prompt_tokens += int(usage["prompt_tokens"])
                    total_completion_tokens += int(usage["completion_tokens"])
                    response_hash = sha256_text(raw)
                    response_sink(
                        {
                            **base,
                            "response_sha256": response_hash,
                            "response_content": raw,
                            **usage,
                        }
                    )
                    hash_key = (
                        str(slot["slot_id"]),
                        stage,
                        orchestration_attempt,
                        response_hash,
                    )
                    response_hash_counts[hash_key] += 1
                    try:
                        if stage == "EP":
                            stage_value: dict[str, Any] = validate_ep_plan(
                                raw,
                                slot=slot,
                                reference=attempt_fields["reference"],
                            )
                        else:
                            v5_locked = {
                                key: str(value)
                                for key, value in locked_context.items()
                                if key != "ep_plan"
                            }
                            stage_value = validate_stage_response_v5(
                                raw,
                                slot=slot,
                                stage=stage,
                                locked_fields=v5_locked,
                                exclusion_registry=exclusion_registry,
                                accepted_proposals=accepted,
                            )
                    except ValueError as exc:
                        outcome = _failure_receipt(exc)
                        if outcome["category"] not in RECOVERABLE_STAGE_FAILURES:
                            raise RuntimeError(
                                f"unregistered stage recovery category: {outcome['category']}"
                            ) from exc
                        complete_responses_without_lock += 1
                        audit_sink(
                            {
                                **base,
                                "event": "CALL_COMPLETED",
                                "status": "RECOVERABLE_FAILURE",
                                "response_sha256": response_hash,
                                "mechanical_outcome": outcome,
                                "complete_stage_responses_without_lock": (
                                    complete_responses_without_lock
                                ),
                                **usage,
                            }
                        )
                        if (
                            stage == "E"
                            and complete_responses_without_lock >= MAX_E_RESPONSES_PER_PLAN
                        ):
                            attempt_sink(
                                {
                                    "slot_id": slot["slot_id"],
                                    "orchestration_attempt": orchestration_attempt,
                                    "orchestration_attempt_version": (
                                        orchestration_attempt_version(orchestration_attempt)
                                    ),
                                    "status": "E_PLAN_EXHAUSTED_ATTEMPT_ABANDONED",
                                    "e_complete_responses": complete_responses_without_lock,
                                    "last_mechanical_outcome": outcome,
                                    "ep_plan": ep_plan,
                                    "permanent_slot_lock": False,
                                }
                            )
                            audit_sink(
                                {
                                    **base,
                                    "event": "ORCHESTRATION_ATTEMPT_ABANDONED",
                                    "status": "E_PLAN_EXHAUSTED_AFTER_SIX_RESPONSES",
                                    "response_sha256": response_hash,
                                    "mechanical_outcome": outcome,
                                }
                            )
                            abandon_attempt = True
                            break
                        hard_block: str | None = None
                        if (
                            stage != "E"
                            and response_hash_counts[hash_key] >= MAX_IDENTICAL_RESPONSE_HASHES
                        ):
                            hard_block = "REPEATED_IDENTICAL_RESPONSE"
                        elif (
                            complete_responses_without_lock
                            >= MAX_COMPLETE_STAGE_RESPONSES_WITHOUT_LOCK
                        ):
                            hard_block = "AGGREGATE_STAGE_NO_PROGRESS"
                        if hard_block is not None:
                            audit_sink(
                                {
                                    **base,
                                    "event": "HARD_BLOCK",
                                    "status": hard_block,
                                    "response_sha256": response_hash,
                                    "mechanical_outcome": outcome,
                                    **usage,
                                }
                            )
                            raise RuntimeError(f"non-financial hard block: {hard_block.lower()}")
                        previous_failure = outcome
                        response_attempt += 1
                        continue
                    audit_sink(
                        {
                            **base,
                            "event": "CALL_COMPLETED",
                            "status": "ATTEMPT_SCOPED_STAGE_LOCK",
                            "response_sha256": response_hash,
                            "mechanical_outcome": {
                                "category": "PASS",
                                "detail": "PASS",
                                "metrics": {},
                            },
                            **usage,
                        }
                    )
                    stage_lock_sink(
                        {
                            **base,
                            "status": "ATTEMPT_SCOPED_STAGE_LOCK",
                            "permanent_slot_lock": False,
                            "response_sha256": response_hash,
                            "locked_fields": stage_value,
                        }
                    )
                    if stage == "EP":
                        ep_plan = {key: str(value) for key, value in stage_value.items()}
                    else:
                        attempt_fields.update(
                            {key: str(value) for key, value in stage_value.items()}
                        )
                    break
                if abandon_attempt:
                    break
            if abandon_attempt:
                if orchestration_attempt >= MAX_COMPLETE_ORCHESTRATION_ATTEMPTS_WITHOUT_ACCEPTANCE:
                    audit_sink(
                        {
                            "source_protocol_id": SOURCE_PROTOCOL_ID_V6,
                            "event": "HARD_BLOCK",
                            "status": "AGGREGATE_ORCHESTRATION_ATTEMPT_NO_PROGRESS",
                            "slot_id": slot["slot_id"],
                            "orchestration_attempt": orchestration_attempt,
                        }
                    )
                    raise RuntimeError(
                        "non-financial hard block: aggregate orchestration-attempt no progress"
                    )
                continue
            try:
                proposal = validate_complete_proposal(
                    slot,
                    attempt_fields,
                    exclusion_registry=exclusion_registry,
                    accepted_proposals=accepted,
                )
            except ValueError as exc:
                outcome = _failure_receipt(exc)
                attempt_sink(
                    {
                        "slot_id": slot["slot_id"],
                        "orchestration_attempt": orchestration_attempt,
                        "orchestration_attempt_version": orchestration_attempt_version(
                            orchestration_attempt
                        ),
                        "status": "COMPLETE_OBJECT_REJECTED_MECHANICALLY",
                        "mechanical_outcome": outcome,
                        "ep_plan": ep_plan,
                        "assembled_proposal_not_truth": {
                            **{key: slot[key] for key in PROPOSAL_FIELDS if key in slot},
                            **attempt_fields,
                        },
                    }
                )
                if orchestration_attempt >= MAX_COMPLETE_ORCHESTRATION_ATTEMPTS_WITHOUT_ACCEPTANCE:
                    audit_sink(
                        {
                            "source_protocol_id": SOURCE_PROTOCOL_ID_V6,
                            "event": "HARD_BLOCK",
                            "status": "AGGREGATE_ORCHESTRATION_ATTEMPT_NO_PROGRESS",
                            "slot_id": slot["slot_id"],
                            "orchestration_attempt": orchestration_attempt,
                            "mechanical_outcome": outcome,
                        }
                    )
                    raise RuntimeError(
                        "non-financial hard block: aggregate orchestration-attempt no progress"
                    ) from exc
                continue
            proposal = {
                **proposal,
                "source_attempt_version": orchestration_attempt_version(orchestration_attempt),
                "generator_model": EXPECTED_MODEL_V6,
                "generator_source_protocol_id": SOURCE_PROTOCOL_ID_V6,
            }
            attempt_sink(
                {
                    "slot_id": slot["slot_id"],
                    "orchestration_attempt": orchestration_attempt,
                    "orchestration_attempt_version": orchestration_attempt_version(
                        orchestration_attempt
                    ),
                    "status": "FIRST_COMPLETE_MECHANICALLY_VALID_OBJECT_PERMANENTLY_ACCEPTED",
                    "proposal_sha256": proposal["proposal_sha256"],
                    "generator_model": EXPECTED_MODEL_V6,
                    "ep_plan": ep_plan,
                    "assembled_proposal_not_truth": {key: proposal[key] for key in PROPOSAL_FIELDS},
                }
            )
            proposal_sink(proposal)
            provenance_sink(
                {
                    "slot_id": slot["slot_id"],
                    "proposal_sha256": proposal["proposal_sha256"],
                    "generator_model": EXPECTED_MODEL_V6,
                    "generator_source_protocol_id": SOURCE_PROTOCOL_ID_V6,
                    "source_attempt_version": proposal["source_attempt_version"],
                    "byte_exact_inherited_accepted_row": False,
                }
            )
            accepted.append(proposal)
            accepted_for_slot = True
            break
        if not accepted_for_slot:
            raise RuntimeError("fixed slot was not permanently accepted")
    return {
        "status": "SOURCE_PROPOSALS_COMPLETE_AWAITING_DATA_LOCK",
        "source_protocol_id": SOURCE_PROTOCOL_ID_V6,
        "inherited_slots": 1,
        "inherited_generator_model": INHERITED_MODEL,
        "newly_accepted_slots": len(accepted) - 1,
        "new_generator_model": EXPECTED_MODEL_V6,
        "accepted_slots": len(accepted),
        "candidate_denominator": len(accepted) * 2,
        "calls": calls,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "peak_estimated_cost_usd": total_cost,
        "proposals": accepted,
    }


__all__ = [
    "EXPECTED_MODEL_V6",
    "FROZEN_TEMPERATURE",
    "FROZEN_TOP_P",
    "PROMPT_CONTRACT_ID_V6",
    "SOURCE_PROTOCOL_ID_V6",
    "build_request_v6",
    "execute_source_v6",
    "failure_specific_action",
    "materialize_and_validate_families",
    "scheduled_strategy",
    "validate_ep_plan",
    "verify_inherited_v4_proposal",
]
