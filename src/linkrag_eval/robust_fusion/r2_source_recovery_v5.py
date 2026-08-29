"""Conservative v5 recovery with substantive retries and inherited slot 001."""

from __future__ import annotations

import json
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
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
    materialize_and_validate_families,
    usage_and_peak_cost,
)
from linkrag_eval.robust_fusion.r2_source_generation import (
    EXPECTED_MODEL,
    PROPOSAL_FIELDS,
    _language_ok,
    _length_ok,
    build_slot_registry,
    canonical_json,
    normalized_levenshtein,
    sha256_text,
    validate_slot_registry,
)
from linkrag_eval.robust_fusion.r2_source_recovery_v4 import (
    _conflict_instruction,
    _reject_external_or_prior_duplicates,
    changed_character_interval,
    edit_rule,
    length_rule,
    validate_complete_proposal,
)

SOURCE_PROTOCOL_ID_V5 = "ROBUST-FUSION-R2-SOURCE-RECOVERY-2026-08-29-v5"
PROMPT_CONTRACT_ID_V5 = "ROBUST-FUSION-R2-SOURCE-SUBSTANTIVE-RETRY-2026-08-29-v5"
STAGES = ("R", "E", "C")
MAX_COMPLETE_STAGE_RESPONSES_WITHOUT_LOCK = 24
MAX_COMPLETE_ASSEMBLIES_WITHOUT_ACCEPTANCE = 24
MAX_OUTPUT_TOKENS_PER_RESPONSE = 4000
FROZEN_TEMPERATURE = 0.6
FROZEN_TOP_P = 0.9
RECOVERABLE_STAGE_FAILURES = {
    "json_parse",
    "schema",
    "language_length_surface",
    "r1_exclusion",
}
R_STRATEGIES = (
    "interior_length_direct",
    "explicit_unit_self_count",
    "two_clause_structured_fact",
    "compact_exact_schema_restatement",
)
E_STRATEGIES = {
    1: (
        "one_local_synonym",
        "one_local_clause_order_swap",
        "function_word_plus_synonym_pair",
        "local_active_passive_rewrite",
    ),
    2: (
        "phrase_synonym_rewrite",
        "local_clause_reorder",
        "subject_frame_rewrite",
        "two_phrase_substitutions",
    ),
    3: (
        "full_clause_reorder",
        "split_one_clause",
        "merge_adjacent_clauses",
        "predicate_frame_rewrite",
    ),
    4: (
        "multi_clause_lexical_rewrite",
        "split_and_reorder",
        "merge_and_predicate_rewrite",
        "global_syntax_rewrite_all_facts_fixed",
    ),
}


class MechanicalFailure(ValueError):
    """Mechanical failure safe to serialize without response text."""

    def __init__(
        self, category: str, detail: str, metrics: Mapping[str, Any] | None = None
    ) -> None:
        super().__init__(category)
        self.category = category
        self.detail = detail
        self.metrics = dict(metrics or {})

    def receipt(self) -> dict[str, Any]:
        return {"category": self.category, "detail": self.detail, "metrics": self.metrics}


def orchestration_attempt_version(attempt: int) -> str:
    if attempt < 1:
        raise ValueError("orchestration attempt must be positive")
    return f"source-recovery-v5-attempt-{attempt:04d}"


def stage_call_version(stage: str, orchestration_attempt: int, response_attempt: int) -> str:
    if stage not in STAGES or response_attempt < 1:
        raise ValueError("invalid v5 stage call identity")
    return (
        f"{orchestration_attempt_version(orchestration_attempt)}-"
        f"stage-{stage.lower()}-{response_attempt:04d}"
    )


def scheduled_strategy(stage: str, edit_level: int, response_attempt: int) -> str:
    sequence = R_STRATEGIES if stage == "R" else E_STRATEGIES[edit_level]
    return sequence[(response_attempt - 1) % len(sequence)]


def failure_specific_action(previous_failure: Mapping[str, Any] | None) -> str:
    if previous_failure is None:
        return "first_attempt_follow_all_frozen_mechanical_rules"
    detail = str(previous_failure["detail"])
    if str(previous_failure["category"]) == "json_parse":
        return "return_one_valid_json_object_only"
    if detail in {"stage_exact_fields", "empty_stage_text", "query_reference_not_unique"}:
        return "return_exact_stage_keys_and_pairwise_distinct_nonempty_values"
    if detail == "language":
        return "use_only_the_fixed_language"
    if detail.endswith("_length"):
        return "self_count_with_the_frozen_unit_and_target_the_interior_interval"
    if detail.endswith("_not_unique"):
        return "apply_the_scheduled_surface_operation_before_output_and_never_copy"
    if detail.endswith("_edit_below_minimum"):
        return "increase_nonfactual_changes_into_the_explicit_changed_character_interval"
    if detail.endswith("_edit_above_maximum"):
        return "reduce_nonfactual_changes_into_the_explicit_changed_character_interval"
    if str(previous_failure["category"]) == "r1_exclusion":
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
        raise RuntimeError("previous response text is forbidden in v5 recovery payload")


def build_request_v5(
    slot: Mapping[str, Any],
    *,
    stage: str,
    orchestration_attempt: int,
    response_attempt: int,
    locked_fields: Mapping[str, str],
    previous_failure: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if stage not in STAGES:
        raise ValueError("unknown v5 stage")
    expected_locked = {
        "R": set(),
        "E": {"query", "reference"},
        "C": {"query", "reference", "equivalent_candidate"},
    }[stage]
    if set(locked_fields) != expected_locked:
        raise RuntimeError("attempt-scoped stage lock drift")
    _validate_previous_failure(previous_failure)
    strategy = scheduled_strategy(stage, int(slot["edit_level"]), response_attempt)
    prompt: dict[str, Any] = {
        "task": "generate_one_stage_of_a_new_non_sensitive_synthetic_microfact_proposal",
        "prompt_contract_id": PROMPT_CONTRACT_ID_V5,
        "stage": stage,
        "slot": dict(slot),
        "orchestration_attempt": orchestration_attempt,
        "orchestration_attempt_version": orchestration_attempt_version(orchestration_attempt),
        "stage_response_attempt": response_attempt,
        "stage_call": stage_call_version(stage, orchestration_attempt, response_attempt),
        "previous_mechanical_failure": previous_failure,
        "recovery_directive": {
            "scheduled_strategy": strategy,
            "strategy_cycle_index": (response_attempt - 1) % 4,
            "failure_specific_action": failure_specific_action(previous_failure),
            "selection_rule": "fixed_by_stage_edit_level_attempt_and_failure_enum_not_content",
        },
        "language_and_length": length_rule(slot),
        "output_role": "proposal_only_not_truth_pending_independent_human_review",
        "boundaries": [
            "invent all facts and entities; use no real person or organization",
            "do not use R1, Blind, Gate, production, internal, score, or annotation content",
            "do not copy, quote, or receive any previous failed response text",
            "return exactly one JSON object with the stage fields and no prose",
            "do not claim that a construction role is ground truth",
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
                        "write the complete fictional microfact in the fixed language; follow "
                        "the scheduled structural strategy and target the interior length interval"
                    ),
                },
            }
        )
    elif stage == "E":
        reference = locked_fields["reference"]
        prompt.update(
            {
                "exact_output_fields": ["equivalent_candidate"],
                "current_attempt_required_context": {
                    "query": locked_fields["query"],
                    "reference": reference,
                },
                "reference_to_candidate_edit_rule": {
                    **edit_rule(int(slot["edit_level"])),
                    **changed_character_interval(reference, int(slot["edit_level"])),
                },
                "stage_instruction": (
                    "produce one propositionally equivalent candidate in the fixed language. "
                    "MANDATORY: never copy reference; execute the scheduled non-factual surface "
                    "strategy while preserving every entity, number, date, version, polarity, "
                    "applicability condition and logical proposition"
                ),
            }
        )
    else:
        reference = locked_fields["reference"]
        prompt.update(
            {
                "exact_output_fields": ["factual_conflict_candidate"],
                "current_attempt_required_context": dict(locked_fields),
                "fixed_conflict_type": slot["conflict_type"],
                "reference_to_candidate_edit_rule": {
                    **edit_rule(int(slot["edit_level"])),
                    **changed_character_interval(reference, int(slot["edit_level"])),
                },
                "stage_instruction": (
                    f"{_conflict_instruction(str(slot['conflict_type']))}; execute the scheduled "
                    "surface strategy, keep every non-target fact unchanged, and never copy reference"
                ),
            }
        )
    return {
        "model": EXPECTED_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return exactly one JSON object for the requested stage. Apply the explicit "
                    "recovery directive. This is a synthetic proposal, never truth."
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


def _language_metrics(text: str, expected: str) -> dict[str, Any]:
    han = sum("CJK UNIFIED IDEOGRAPH" in unicodedata.name(char, "") for char in text)
    latin = sum(char.isascii() and char.isalpha() for char in text)
    return {"expected_language": expected, "han_characters": han, "latin_letters": latin}


def _length_metrics(text: str, slot: Mapping[str, Any]) -> dict[str, Any]:
    rule = length_rule(slot)
    normalized = normalize_text(text)
    count = len(normalized) if slot["language"] == "zh" else len(normalized.split())
    return {
        "observed": count,
        "unit": rule["unit"],
        "minimum": rule["frozen_minimum"],
        "maximum": rule["frozen_maximum"],
        "interior_target_minimum": rule["interior_prompt_target_minimum"],
        "interior_target_maximum": rule["interior_prompt_target_maximum"],
    }


def validate_stage_response_v5(
    raw: str,
    *,
    slot: Mapping[str, Any],
    stage: str,
    locked_fields: Mapping[str, str],
    exclusion_registry: Mapping[str, Any],
    accepted_proposals: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    fields = {
        "R": {"query", "reference"},
        "E": {"equivalent_candidate"},
        "C": {"factual_conflict_candidate"},
    }[stage]
    value = _parse_exact_object(raw, fields)
    texts = {field: str(value[field]) for field in fields}
    if any(not text.strip() for text in texts.values()):
        raise MechanicalFailure("schema", "empty_stage_text")
    language = str(slot["language"])
    for text in texts.values():
        if not _language_ok(text, language):
            raise MechanicalFailure(
                "language_length_surface", "language", _language_metrics(text, language)
            )
    if stage == "R":
        if normalize_text(texts["query"]) == normalize_text(texts["reference"]):
            raise MechanicalFailure("schema", "query_reference_not_unique")
        if not _length_ok(texts["reference"], language, str(slot["length_stratum"])):
            raise MechanicalFailure(
                "language_length_surface",
                "reference_length",
                _length_metrics(texts["reference"], slot),
            )
    else:
        field = next(iter(fields))
        candidate = texts[field]
        if not _length_ok(candidate, language, str(slot["length_stratum"])):
            raise MechanicalFailure(
                "language_length_surface",
                f"{field}_length",
                _length_metrics(candidate, slot),
            )
        equal_to = [
            name
            for name, text in locked_fields.items()
            if normalize_text(candidate) == normalize_text(text)
        ]
        if equal_to:
            raise MechanicalFailure(
                "schema",
                f"{field}_not_unique",
                {"normalized_equal_to_fields": sorted(equal_to)},
            )
        distance = normalized_levenshtein(locked_fields["reference"], candidate)
        rule = edit_rule(int(slot["edit_level"]))
        metrics = {
            "observed_ratio": distance,
            "minimum_ratio": rule["minimum"],
            "maximum_ratio": rule["maximum"],
            "reference_normalized_characters": len(normalize_text(locked_fields["reference"])),
            "candidate_normalized_characters": len(normalize_text(candidate)),
            **changed_character_interval(locked_fields["reference"], int(slot["edit_level"])),
        }
        if distance < float(rule["minimum"]):
            raise MechanicalFailure(
                "language_length_surface", f"{field}_edit_below_minimum", metrics
            )
        if distance > float(rule["maximum"]):
            raise MechanicalFailure(
                "language_length_surface", f"{field}_edit_above_maximum", metrics
            )
    try:
        _reject_external_or_prior_duplicates(
            list(texts.values()),
            exclusion_registry=exclusion_registry,
            accepted_proposals=accepted_proposals,
        )
    except ValueError as exc:
        raise MechanicalFailure(
            getattr(exc, "category", "r1_exclusion"),
            getattr(exc, "detail", "r1_or_accepted_r2_exclusion"),
        ) from exc
    return texts


def verify_inherited_v4_proposal(
    v4_root: Path, exclusion_registry: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    accepted_lines = (v4_root / "accepted_proposals_not_truth.jsonl").read_bytes().splitlines()
    if len(accepted_lines) != 1:
        raise RuntimeError("v4 inherited accepted ledger must contain exactly one row")
    accepted = json.loads(accepted_lines[0])
    slot = build_slot_registry()[0]
    for key in (
        "slot_id",
        "dataset_role",
        "language",
        "length_stratum",
        "conflict_type",
        "edit_level",
    ):
        if accepted[key] != slot[key]:
            raise RuntimeError("v4 inherited slot identity drift")
    if accepted.get("source_attempt_version") != "source-recovery-v4-attempt-0001":
        raise RuntimeError("v4 inherited source attempt drift")
    assemblies = [
        json.loads(line)
        for line in (v4_root / "complete_assembly_attempts_not_truth.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    if len(assemblies) != 1 or assemblies[0]["status"] != (
        "FIRST_COMPLETE_MECHANICALLY_VALID_OBJECT_PERMANENTLY_ACCEPTED"
    ):
        raise RuntimeError("v4 inherited complete assembly drift")
    assembled = assemblies[0]["assembled_proposal_not_truth"]
    if assembled != {key: accepted[key] for key in PROPOSAL_FIELDS}:
        raise RuntimeError("v4 inherited source object/assembly mismatch")
    if assemblies[0]["proposal_sha256"] != accepted["proposal_sha256"]:
        raise RuntimeError("v4 inherited proposal/assembly hash mismatch")
    stage_locks = [
        json.loads(line)
        for line in (v4_root / "attempt_scoped_stage_locks.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    selected = [row for row in stage_locks if row["slot_id"] == "R2SRC-001"]
    if len(selected) != 3 or {row["stage"] for row in selected} != set(STAGES):
        raise RuntimeError("v4 inherited stage lock set drift")
    locked_fields: dict[str, str] = {}
    for stage in STAGES:
        row = next(item for item in selected if item["stage"] == stage)
        if row["status"] != "ATTEMPT_SCOPED_STAGE_LOCK" or row["permanent_slot_lock"]:
            raise RuntimeError("v4 inherited stage lock status drift")
        locked_fields.update({key: str(value) for key, value in row["locked_fields"].items()})
    if locked_fields != {key: str(accepted[key]) for key in locked_fields}:
        raise RuntimeError("v4 inherited stage lock text drift")
    parsed = validate_complete_proposal(
        slot,
        locked_fields,
        exclusion_registry=exclusion_registry,
        accepted_proposals=[],
    )
    if parsed["proposal_sha256"] != accepted["proposal_sha256"]:
        raise RuntimeError("v4 inherited unchanged-parser replay mismatch")
    responses = [
        json.loads(line)
        for line in (v4_root / "response_archive_synthetic_only.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    archived_hashes = {row["response_sha256"] for row in responses}
    if any(row["response_sha256"] not in archived_hashes for row in selected):
        raise RuntimeError("v4 inherited stage source response missing")
    return accepted, {
        "status": "R2SRC_001_INHERITED_HARD_LOCK_VERIFIED",
        "slot_id": "R2SRC-001",
        "accepted_ledger_line_sha256": hashlib_sha256(accepted_lines[0]),
        "proposal_sha256": accepted["proposal_sha256"],
        "source_attempt_version": accepted["source_attempt_version"],
        "stage_locks_verified": 3,
        "complete_assembly_verified": True,
        "unchanged_parser_and_all_mechanical_gates_pass": True,
        "replaceable": False,
    }


def hashlib_sha256(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()


def _response_content(response: Mapping[str, Any]) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise PermanentProviderError("provider response envelope drift") from exc
    if not isinstance(content, str):
        raise PermanentProviderError("provider response content type drift")
    return content


def _failure_receipt(exc: ValueError) -> dict[str, Any]:
    if isinstance(exc, MechanicalFailure):
        return exc.receipt()
    return {
        "category": getattr(exc, "category", str(exc)),
        "detail": getattr(exc, "detail", "unchanged_final_parser_rejection"),
        "metrics": dict(getattr(exc, "metrics", {})),
    }


def execute_source_v5(
    *,
    transport: Transport,
    exclusion_registry: Mapping[str, Any],
    inherited_proposal: Mapping[str, Any],
    audit_sink: RecordSink,
    response_sink: RecordSink,
    stage_lock_sink: RecordSink,
    attempt_sink: RecordSink,
    proposal_sink: RecordSink,
    slots: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    frame = list(build_slot_registry() if slots is None else slots)
    validate_slot_registry(frame)
    if frame[0]["slot_id"] != "R2SRC-001" or inherited_proposal["slot_id"] != "R2SRC-001":
        raise RuntimeError("v5 inherited slot 001 identity drift")
    accepted: list[dict[str, Any]] = [dict(inherited_proposal)]
    audit_sink(
        {
            "source_protocol_id": SOURCE_PROTOCOL_ID_V5,
            "event": "INHERITED_PROPOSAL_HARD_LOCKED",
            "slot_id": "R2SRC-001",
            "proposal_sha256": inherited_proposal["proposal_sha256"],
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
        for orchestration_attempt in range(1, MAX_COMPLETE_ASSEMBLIES_WITHOUT_ACCEPTANCE + 1):
            attempt_fields: dict[str, str] = {}
            for stage in STAGES:
                complete_responses_without_lock = 0
                response_attempt = 1
                consecutive_transport = 0
                previous_failure: dict[str, Any] | None = None
                while True:
                    body = build_request_v5(
                        slot,
                        stage=stage,
                        orchestration_attempt=orchestration_attempt,
                        response_attempt=response_attempt,
                        locked_fields=attempt_fields,
                        previous_failure=previous_failure,
                    )
                    request_hash = sha256_text(canonical_json(body))
                    if request_hash in request_hashes:
                        raise RuntimeError("request replay detected")
                    request_hashes.add(request_hash)
                    base = {
                        "source_protocol_id": SOURCE_PROTOCOL_ID_V5,
                        "prompt_contract_id": PROMPT_CONTRACT_ID_V5,
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
                        "model": EXPECTED_MODEL,
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
                        previous_failure = None
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
                    consecutive_transport = 0
                    envelope_hash = sha256_text(canonical_json(response))
                    try:
                        usage = usage_and_peak_cost(response)
                        raw = _response_content(response)
                    except PermanentProviderError as exc:
                        response_sink(
                            {
                                **base,
                                "response_sha256": envelope_hash,
                                "response_hash_scope": "provider_envelope",
                                "response_content": None,
                                "mechanical_outcome": {
                                    "category": "provider",
                                    "detail": str(exc),
                                    "metrics": {},
                                },
                            }
                        )
                        audit_sink(
                            {
                                **base,
                                "event": "CALL_COMPLETED",
                                "status": "PERMANENT_PROVIDER_FAILURE",
                                "response_sha256": envelope_hash,
                                "response_hash_scope": "provider_envelope",
                                "mechanical_outcome": {
                                    "category": "provider",
                                    "detail": str(exc),
                                    "metrics": {},
                                },
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
                        stage_values = validate_stage_response_v5(
                            raw,
                            slot=slot,
                            stage=stage,
                            locked_fields=attempt_fields,
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
                        hard_block: str | None = None
                        if response_hash_counts[hash_key] >= MAX_IDENTICAL_RESPONSE_HASHES:
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
                    attempt_fields.update(stage_values)
                    stage_lock_sink(
                        {
                            **base,
                            "status": "ATTEMPT_SCOPED_STAGE_LOCK",
                            "permanent_slot_lock": False,
                            "response_sha256": response_hash,
                            "locked_fields": stage_values,
                        }
                    )
                    break
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
                        "assembled_proposal_not_truth": {
                            **{key: slot[key] for key in PROPOSAL_FIELDS if key in slot},
                            **attempt_fields,
                        },
                    }
                )
                if orchestration_attempt >= MAX_COMPLETE_ASSEMBLIES_WITHOUT_ACCEPTANCE:
                    audit_sink(
                        {
                            "source_protocol_id": SOURCE_PROTOCOL_ID_V5,
                            "event": "HARD_BLOCK",
                            "status": "AGGREGATE_COMPLETE_ASSEMBLY_NO_PROGRESS",
                            "slot_id": slot["slot_id"],
                            "orchestration_attempt": orchestration_attempt,
                            "mechanical_outcome": outcome,
                        }
                    )
                    raise RuntimeError(
                        "non-financial hard block: aggregate complete-assembly no progress"
                    ) from exc
                continue
            proposal = {
                **proposal,
                "source_attempt_version": orchestration_attempt_version(orchestration_attempt),
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
                    "assembled_proposal_not_truth": {key: proposal[key] for key in PROPOSAL_FIELDS},
                }
            )
            proposal_sink(proposal)
            accepted.append(proposal)
            accepted_for_slot = True
            break
        if not accepted_for_slot:
            raise RuntimeError("fixed slot was not permanently accepted")
    return {
        "status": "SOURCE_PROPOSALS_COMPLETE_AWAITING_DATA_LOCK",
        "source_protocol_id": SOURCE_PROTOCOL_ID_V5,
        "inherited_slots": 1,
        "newly_accepted_slots": len(accepted) - 1,
        "accepted_slots": len(accepted),
        "candidate_denominator": len(accepted) * 2,
        "calls": calls,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "peak_estimated_cost_usd": total_cost,
        "proposals": accepted,
    }


__all__ = [
    "FROZEN_TEMPERATURE",
    "FROZEN_TOP_P",
    "PROMPT_CONTRACT_ID_V5",
    "SOURCE_PROTOCOL_ID_V5",
    "build_request_v5",
    "execute_source_v5",
    "failure_specific_action",
    "materialize_and_validate_families",
    "scheduled_strategy",
    "validate_stage_response_v5",
    "verify_inherited_v4_proposal",
]
