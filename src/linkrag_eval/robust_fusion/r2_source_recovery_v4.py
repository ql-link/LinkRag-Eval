"""Three-stage v4 recovery for the fixed R2 synthetic source frame."""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from linkrag_eval.robust_fusion.r2_measurement import (
    character_ngrams,
    jaccard,
    normalize_text,
    template_signature,
    text_sha256,
)
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
    parse_and_validate_proposal,
    sha256_text,
    validate_slot_registry,
)

SOURCE_PROTOCOL_ID_V4 = "ROBUST-FUSION-R2-SOURCE-RECOVERY-2026-08-29-v4"
PROMPT_CONTRACT_ID_V4 = "ROBUST-FUSION-R2-SOURCE-STAGED-CONTRACT-2026-08-29-v4"
STAGES = ("R", "E", "C")
MAX_COMPLETE_STAGE_RESPONSES_WITHOUT_LOCK = 24
MAX_COMPLETE_ASSEMBLIES_WITHOUT_ACCEPTANCE = 24
MAX_OUTPUT_TOKENS_PER_RESPONSE = 4000
RECOVERABLE_STAGE_FAILURES = {
    "json_parse",
    "schema",
    "language_length_surface",
    "r1_exclusion",
}


class MechanicalFailure(ValueError):
    """A registered mechanical rejection with a non-semantic diagnostic detail."""

    def __init__(self, category: str, detail: str) -> None:
        super().__init__(category)
        self.category = category
        self.detail = detail


def orchestration_attempt_version(attempt: int) -> str:
    if attempt < 1:
        raise ValueError("orchestration attempt must be positive")
    return f"source-recovery-v4-attempt-{attempt:04d}"


def stage_call_version(stage: str, orchestration_attempt: int, response_attempt: int) -> str:
    if stage not in STAGES or response_attempt < 1:
        raise ValueError("invalid v4 stage call identity")
    return (
        f"{orchestration_attempt_version(orchestration_attempt)}-"
        f"stage-{stage.lower()}-{response_attempt:04d}"
    )


def length_rule(slot: Mapping[str, Any]) -> dict[str, Any]:
    rules = {
        ("zh", "short"): ("normalized_characters", 35, 130, 60, 90),
        ("zh", "long"): ("normalized_characters", 160, 420, 220, 300),
        ("en", "short"): ("normalized_words", 18, 70, 30, 45),
        ("en", "long"): ("normalized_words", 90, 220, 120, 160),
    }
    unit, minimum, maximum, target_minimum, target_maximum = rules[
        (str(slot["language"]), str(slot["length_stratum"]))
    ]
    return {
        "unit": unit,
        "frozen_minimum": minimum,
        "frozen_maximum": maximum,
        "interior_prompt_target_minimum": target_minimum,
        "interior_prompt_target_maximum": target_maximum,
    }


def edit_rule(edit_level: int) -> dict[str, Any]:
    minimum, maximum, instruction = {
        1: (0.02, 0.18, "small non-factual synonym replacement or syntax adjustment"),
        2: (0.08, 0.28, "phrase-level non-factual paraphrase"),
        3: (0.15, 0.40, "clear non-factual syntactic reordering"),
        4: (0.22, 0.58, "multiple non-factual lexical and syntactic rewrites"),
    }[edit_level]
    return {"minimum": minimum, "maximum": maximum, "instruction": instruction}


def changed_character_interval(reference: str, edit_level: int) -> dict[str, Any]:
    normalized_length = len(normalize_text(reference))
    rule = edit_rule(edit_level)
    minimum = math.ceil(Decimal(str(rule["minimum"])) * normalized_length)
    maximum = math.floor(Decimal(str(rule["maximum"])) * normalized_length)
    return {
        "reference_normalized_character_length": normalized_length,
        "equal_normalized_length_minimum_changed_characters": minimum,
        "equal_normalized_length_maximum_changed_characters": maximum,
        "authoritative_acceptance_formula": (
            "minimum_ratio <= levenshtein_edit_operations / "
            "max(reference_normalized_characters,candidate_normalized_characters) <= "
            "maximum_ratio"
        ),
        "minimum_ratio": rule["minimum"],
        "maximum_ratio": rule["maximum"],
    }


def _conflict_instruction(conflict_type: str) -> str:
    return {
        "numeric": "change exactly one numeric quantity and preserve every other fact",
        "version_time": "change exactly one version or time value and preserve every other fact",
        "negation_direction": (
            "reverse exactly one frozen polarity or direction fact and preserve every other fact"
        ),
        "applicability_condition": (
            "change exactly one applicability condition and preserve every other fact"
        ),
    }[conflict_type]


def build_request_v4(
    slot: Mapping[str, Any],
    *,
    stage: str,
    orchestration_attempt: int,
    response_attempt: int,
    locked_fields: Mapping[str, str],
) -> dict[str, Any]:
    if stage not in STAGES:
        raise ValueError("unknown v4 stage")
    expected_locked = {
        "R": set(),
        "E": {"query", "reference"},
        "C": {"query", "reference", "equivalent_candidate"},
    }[stage]
    if set(locked_fields) != expected_locked:
        raise RuntimeError("attempt-scoped stage lock drift")
    common = {
        "task": "generate_one_stage_of_a_new_non_sensitive_synthetic_microfact_proposal",
        "prompt_contract_id": PROMPT_CONTRACT_ID_V4,
        "stage": stage,
        "slot": dict(slot),
        "orchestration_attempt": orchestration_attempt_version(orchestration_attempt),
        "stage_call": stage_call_version(stage, orchestration_attempt, response_attempt),
        "language_and_length": length_rule(slot),
        "output_role": "proposal_only_not_truth_pending_independent_human_review",
        "boundaries": [
            "invent all facts and entities; use no real person or organization",
            "do not use R1, Blind, Gate, production, internal, score, or annotation content",
            "return exactly one JSON object with the stage fields and no prose",
            "do not claim that a construction role is ground truth",
        ],
    }
    if stage == "R":
        common.update(
            {
                "exact_output_fields": ["query", "reference"],
                "stage_instruction": {
                    "query": (
                        "write a question in the fixed language about one entirely fictional "
                        "microfact; normalized text must differ from reference"
                    ),
                    "reference": (
                        "write the complete fictional microfact in the fixed language; target "
                        "the interior length interval, while the frozen outer interval remains "
                        "the acceptance rule"
                    ),
                },
            }
        )
    elif stage == "E":
        reference = locked_fields["reference"]
        common.update(
            {
                "exact_output_fields": ["equivalent_candidate"],
                "current_attempt_deepseek_generated_reference": reference,
                "reference_to_candidate_edit_rule": {
                    **edit_rule(int(slot["edit_level"])),
                    **changed_character_interval(reference, int(slot["edit_level"])),
                },
                "stage_instruction": (
                    "produce one propositionally equivalent candidate in the fixed language. "
                    "It must be character-normalized different from reference, must preserve "
                    "every entity, number, date, version, polarity, applicability condition and "
                    "logical proposition, and must use only non-factual synonym or syntax changes"
                ),
            }
        )
    else:
        reference = locked_fields["reference"]
        common.update(
            {
                "exact_output_fields": ["factual_conflict_candidate"],
                "current_attempt_deepseek_generated_reference": reference,
                "fixed_conflict_type": slot["conflict_type"],
                "reference_to_candidate_edit_rule": {
                    **edit_rule(int(slot["edit_level"])),
                    **changed_character_interval(reference, int(slot["edit_level"])),
                },
                "stage_instruction": (
                    f"{_conflict_instruction(str(slot['conflict_type']))}; the output must be "
                    "normalized different from reference, and any surface rewriting must be "
                    "non-factual"
                ),
            }
        )
    return {
        "model": EXPECTED_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return exactly one JSON object for the requested stage. Never copy a "
                    "candidate from the reference. This is a proposal, not truth."
                ),
            },
            {"role": "user", "content": canonical_json(common)},
        ],
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "stream": False,
        "temperature": 0.2,
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


def _reject_external_or_prior_duplicates(
    texts: Sequence[str],
    *,
    exclusion_registry: Mapping[str, Any],
    accepted_proposals: Sequence[Mapping[str, Any]],
) -> None:
    excluded_texts = set(exclusion_registry["text_sha256"])
    excluded_templates = set(exclusion_registry["template_sha256"])
    excluded_ngrams = [set(value) for value in exclusion_registry["near_duplicate_ngrams"]]
    prior_texts = [
        str(row[field])
        for row in accepted_proposals
        for field in ("query", "reference", "equivalent_candidate", "factual_conflict_candidate")
    ]
    for text in texts:
        digest = text_sha256(text)
        template = template_signature(text)
        grams = character_ngrams(text)
        if digest in excluded_texts or template in excluded_templates:
            raise MechanicalFailure("r1_exclusion", "r1_exact_or_template")
        if any(jaccard(grams, prior) >= 0.82 for prior in excluded_ngrams):
            raise MechanicalFailure("r1_exclusion", "r1_5gram_near_duplicate")
        if any(
            digest == text_sha256(prior)
            or template == template_signature(prior)
            or jaccard(grams, character_ngrams(prior)) >= 0.82
            for prior in prior_texts
        ):
            raise MechanicalFailure("r1_exclusion", "accepted_r2_cross_slot_duplicate")


def validate_stage_response(
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
    length = str(slot["length_stratum"])
    if any(not _language_ok(text, language) for text in texts.values()):
        raise MechanicalFailure("language_length_surface", "language")
    if stage == "R":
        if normalize_text(texts["query"]) == normalize_text(texts["reference"]):
            raise MechanicalFailure("schema", "query_reference_not_unique")
        if not _length_ok(texts["reference"], language, length):
            raise MechanicalFailure("language_length_surface", "reference_length")
    else:
        field = next(iter(fields))
        candidate = texts[field]
        if not _length_ok(candidate, language, length):
            raise MechanicalFailure("language_length_surface", f"{field}_length")
        if normalize_text(candidate) in {
            normalize_text(text) for text in locked_fields.values()
        }:
            raise MechanicalFailure("schema", f"{field}_not_unique")
        minimum = float(edit_rule(int(slot["edit_level"]))["minimum"])
        maximum = float(edit_rule(int(slot["edit_level"]))["maximum"])
        distance = normalized_levenshtein(locked_fields["reference"], candidate)
        if not minimum <= distance <= maximum:
            raise MechanicalFailure("language_length_surface", f"{field}_edit_band")
    _reject_external_or_prior_duplicates(
        list(texts.values()),
        exclusion_registry=exclusion_registry,
        accepted_proposals=accepted_proposals,
    )
    return texts


def validate_complete_proposal(
    slot: Mapping[str, Any],
    locked_fields: Mapping[str, str],
    *,
    exclusion_registry: Mapping[str, Any],
    accepted_proposals: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    value = {
        key: slot[key]
        for key in (
            "slot_id",
            "dataset_role",
            "language",
            "length_stratum",
            "conflict_type",
            "edit_level",
        )
    }
    value.update(locked_fields)
    if set(value) != PROPOSAL_FIELDS:
        raise MechanicalFailure("schema", "complete_object_fields")
    try:
        proposal = parse_and_validate_proposal(
            canonical_json(value),
            slot=slot,
            exclusion_registry=exclusion_registry,
            accepted_proposals=accepted_proposals,
        )
    except ValueError as exc:
        category = str(exc)
        if category not in RECOVERABLE_STAGE_FAILURES:
            raise RuntimeError(f"unregistered final parser category: {category}") from exc
        raise MechanicalFailure(category, "unchanged_final_parser_rejection") from exc
    _reject_external_or_prior_duplicates(
        [str(proposal[field]) for field in locked_fields],
        exclusion_registry=exclusion_registry,
        accepted_proposals=accepted_proposals,
    )
    return proposal


def _response_content(response: Mapping[str, Any]) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise PermanentProviderError("provider response envelope drift") from exc
    if not isinstance(content, str):
        raise PermanentProviderError("provider response content type drift")
    return content


def execute_source_v4(
    *,
    transport: Transport,
    exclusion_registry: Mapping[str, Any],
    audit_sink: RecordSink,
    response_sink: RecordSink,
    stage_lock_sink: RecordSink,
    attempt_sink: RecordSink,
    proposal_sink: RecordSink,
    slots: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run R→E→C; only the first fully valid assembly permanently accepts a slot."""
    frame = list(build_slot_registry() if slots is None else slots)
    validate_slot_registry(frame)
    accepted: list[dict[str, Any]] = []
    request_hashes: set[str] = set()
    response_hash_counts: Counter[tuple[str, str, str]] = Counter()
    calls = 0
    total_cost = 0.0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    for slot in frame:
        accepted_for_slot = False
        for orchestration_attempt in range(1, MAX_COMPLETE_ASSEMBLIES_WITHOUT_ACCEPTANCE + 1):
            attempt_fields: dict[str, str] = {}
            for stage in STAGES:
                complete_responses_without_lock = 0
                response_attempt = 1
                consecutive_transport = 0
                while True:
                    body = build_request_v4(
                        slot,
                        stage=stage,
                        orchestration_attempt=orchestration_attempt,
                        response_attempt=response_attempt,
                        locked_fields=attempt_fields,
                    )
                    request_hash = sha256_text(canonical_json(body))
                    if request_hash in request_hashes:
                        raise RuntimeError("request replay detected")
                    request_hashes.add(request_hash)
                    base = {
                        "source_protocol_id": SOURCE_PROTOCOL_ID_V4,
                        "prompt_contract_id": PROMPT_CONTRACT_ID_V4,
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
                        audit_sink(
                            {
                                **base,
                                "event": "CALL_COMPLETED",
                                "status": "RECOVERABLE_FAILURE",
                                "failure_category": "transport",
                                "failure_type": type(exc).__name__,
                                "failure_detail": str(exc)[:240],
                            }
                        )
                        if consecutive_transport >= MAX_CONSECUTIVE_TRANSPORT_FAILURES:
                            raise RuntimeError(
                                "non-financial hard block: consecutive transport failures"
                            )
                        response_attempt += 1
                        continue
                    consecutive_transport = 0
                    usage = usage_and_peak_cost(response)
                    total_cost += float(usage["peak_estimated_cost_usd"])
                    total_prompt_tokens += int(usage["prompt_tokens"])
                    total_completion_tokens += int(usage["completion_tokens"])
                    raw = _response_content(response)
                    response_hash = sha256_text(raw)
                    hash_key = (str(slot["slot_id"]), stage, response_hash)
                    response_hash_counts[hash_key] += 1
                    response_sink(
                        {
                            **base,
                            "response_sha256": response_hash,
                            "response_content": raw,
                            **usage,
                        }
                    )
                    if response_hash_counts[hash_key] >= MAX_IDENTICAL_RESPONSE_HASHES:
                        raise RuntimeError("non-financial hard block: repeated identical response")
                    try:
                        stage_values = validate_stage_response(
                            raw,
                            slot=slot,
                            stage=stage,
                            locked_fields=attempt_fields,
                            exclusion_registry=exclusion_registry,
                            accepted_proposals=accepted,
                        )
                    except ValueError as exc:
                        category = getattr(exc, "category", str(exc))
                        detail = getattr(exc, "detail", str(exc))
                        if category not in RECOVERABLE_STAGE_FAILURES:
                            raise RuntimeError(
                                f"unregistered stage recovery category: {category}"
                            ) from exc
                        complete_responses_without_lock += 1
                        audit_sink(
                            {
                                **base,
                                "event": "CALL_COMPLETED",
                                "status": "RECOVERABLE_FAILURE",
                                "failure_category": category,
                                "failure_detail": detail,
                                "response_sha256": response_hash,
                                "complete_stage_responses_without_lock": (
                                    complete_responses_without_lock
                                ),
                                **usage,
                            }
                        )
                        if (
                            complete_responses_without_lock
                            >= MAX_COMPLETE_STAGE_RESPONSES_WITHOUT_LOCK
                        ):
                            raise RuntimeError(
                                "non-financial hard block: aggregate stage no progress"
                            )
                        response_attempt += 1
                        continue
                    attempt_fields.update(stage_values)
                    stage_lock = {
                        **base,
                        "status": "ATTEMPT_SCOPED_STAGE_LOCK",
                        "permanent_slot_lock": False,
                        "response_sha256": response_hash,
                        "locked_fields": stage_values,
                    }
                    stage_lock_sink(stage_lock)
                    audit_sink(
                        {
                            **base,
                            "event": "CALL_COMPLETED",
                            "status": "ATTEMPT_SCOPED_STAGE_LOCK",
                            "permanent_slot_lock": False,
                            "response_sha256": response_hash,
                            **usage,
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
                category = getattr(exc, "category", str(exc))
                detail = getattr(exc, "detail", str(exc))
                attempt_sink(
                    {
                        "slot_id": slot["slot_id"],
                        "orchestration_attempt": orchestration_attempt,
                        "orchestration_attempt_version": orchestration_attempt_version(
                            orchestration_attempt
                        ),
                        "status": "COMPLETE_OBJECT_REJECTED_MECHANICALLY",
                        "failure_category": category,
                        "failure_detail": detail,
                        "assembled_proposal_not_truth": {
                            **{key: slot[key] for key in PROPOSAL_FIELDS if key in slot},
                            **attempt_fields,
                        },
                    }
                )
                if orchestration_attempt >= MAX_COMPLETE_ASSEMBLIES_WITHOUT_ACCEPTANCE:
                    raise RuntimeError(
                        "non-financial hard block: aggregate complete-assembly no progress"
                    ) from exc
                continue
            proposal = {
                **proposal,
                "source_attempt_version": orchestration_attempt_version(
                    orchestration_attempt
                ),
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
                    "assembled_proposal_not_truth": {
                        key: proposal[key] for key in PROPOSAL_FIELDS
                    },
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
        "source_protocol_id": SOURCE_PROTOCOL_ID_V4,
        "accepted_slots": len(accepted),
        "candidate_denominator": len(accepted) * 2,
        "calls": calls,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "peak_estimated_cost_usd": total_cost,
        "proposals": accepted,
    }


__all__ = [
    "MAX_COMPLETE_ASSEMBLIES_WITHOUT_ACCEPTANCE",
    "MAX_COMPLETE_STAGE_RESPONSES_WITHOUT_LOCK",
    "PROMPT_CONTRACT_ID_V4",
    "SOURCE_PROTOCOL_ID_V4",
    "build_request_v4",
    "changed_character_interval",
    "execute_source_v4",
    "materialize_and_validate_families",
    "orchestration_attempt_version",
    "stage_call_version",
    "validate_complete_proposal",
    "validate_stage_response",
]
