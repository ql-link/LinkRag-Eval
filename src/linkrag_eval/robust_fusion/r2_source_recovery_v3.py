"""Prompt-only v3 recovery for the fixed R2 source-generation frame."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from linkrag_eval.robust_fusion.r2_measurement import template_signature, text_sha256
from linkrag_eval.robust_fusion.r2_source_execution_v2 import (
    AUTHORIZATION_ID,
    MAX_CONSECUTIVE_SAME_MECHANICAL_FAILURE,
    MAX_CONSECUTIVE_TRANSPORT_FAILURES,
    MAX_IDENTICAL_RESPONSE_HASHES,
    RECOVERABLE_FAILURES,
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
    build_slot_registry,
    canonical_json,
    parse_and_validate_proposal,
    sha256_text,
    validate_slot_registry,
)

SOURCE_PROTOCOL_ID_V3 = "ROBUST-FUSION-R2-SOURCE-RECOVERY-2026-08-29-v3"
PROMPT_CONTRACT_ID_V3 = "ROBUST-FUSION-R2-SOURCE-PROMPT-CONTRACT-2026-08-29-v3"
MAX_OUTPUT_TOKENS_PER_RESPONSE = 4000


def attempt_version_v3(attempt: int) -> str:
    if attempt < 1:
        raise ValueError("attempt must be positive")
    return f"source-recovery-v3-attempt-{attempt:04d}"


def _length_rule(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        ("zh", "short"): {"unit": "normalized_characters", "minimum": 35, "maximum": 130},
        ("zh", "long"): {"unit": "normalized_characters", "minimum": 160, "maximum": 420},
        ("en", "short"): {"unit": "words", "minimum": 18, "maximum": 70},
        ("en", "long"): {"unit": "words", "minimum": 90, "maximum": 220},
    }[(str(slot["language"]), str(slot["length_stratum"]))]


def _edit_rule(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        1: {
            "minimum": 0.02,
            "maximum": 0.18,
            "instruction": "local synonym replacement or a small syntax adjustment",
        },
        2: {
            "minimum": 0.08,
            "maximum": 0.28,
            "instruction": "phrase-level paraphrase without factual changes",
        },
        3: {
            "minimum": 0.15,
            "maximum": 0.40,
            "instruction": "clear syntactic reordering while preserving facts",
        },
        4: {
            "minimum": 0.22,
            "maximum": 0.58,
            "instruction": "multiple non-factual lexical and syntactic rewrites",
        },
    }[int(slot["edit_level"])]


def build_request_v3(
    slot: Mapping[str, Any], *, attempt: int, prior_failure: str | None
) -> dict[str, Any]:
    if attempt > 1 and prior_failure not in RECOVERABLE_FAILURES:
        raise RuntimeError("recovery requires a registered mechanical failure")
    recovery_instruction = {
        None: "satisfy every rule on the first response",
        "transport": "repeat the same fixed slot under this self-contained contract",
        "json_parse": "emit one syntactically valid JSON object and no surrounding text",
        "schema": (
            "use the exact fields and identities; critically, do not copy reference into any "
            "candidate and make all four normalized text values pairwise different"
        ),
        "language_length_surface": (
            "correct language, length, and each candidate's normalized edit-distance band"
        ),
        "r1_exclusion": "invent new fictional entities, facts, vocabulary, and sentence structure",
    }[prior_failure]
    prompt = {
        "task": "create_one_new_non_sensitive_synthetic_microfact_proposal",
        "prompt_contract_id": PROMPT_CONTRACT_ID_V3,
        "slot": dict(slot),
        "attempt_version": attempt_version_v3(attempt),
        "prior_mechanical_failure_category_only": prior_failure,
        "recovery_instruction": recovery_instruction,
        "exact_output_fields": sorted(PROPOSAL_FIELDS),
        "mechanical_contract": {
            "language": slot["language"],
            "reference_and_candidates_length": _length_rule(slot),
            "reference_to_each_candidate_normalized_levenshtein": _edit_rule(slot),
            "four_texts_pairwise_distinct_after_nfkc_casefold_whitespace_normalization": True,
        },
        "field_contract": {
            "query": (
                "a question about the invented microfact; it must not copy any statement field"
            ),
            "reference": "a complete statement of one entirely fictional microfact",
            "equivalent_candidate": (
                "MANDATORY: never copy reference. Perform non-factual synonym substitution or "
                "syntactic reordering so normalized text differs, while every entity, number, "
                "date, version, polarity, applicability condition, and proposition remains equal"
            ),
            "factual_conflict_candidate": (
                f"change exactly one {slot['conflict_type']} factual slot and no other fact; "
                "also make normalized text distinct using only non-factual surface rewriting"
            ),
        },
        "pre_output_self_check": [
            "all six slot identity values copied exactly",
            "query, reference, equivalent_candidate, factual_conflict_candidate are pairwise distinct",
            "reference and equivalent_candidate express exactly the same proposition",
            "conflict changes only the requested factual slot",
            "both candidates fall within the requested edit-distance band",
            "output contains exactly one JSON object and no extra keys or prose",
        ],
        "privacy_and_research_boundaries": [
            "invent all entities and facts; use no real person or organization",
            "no R1, prior response, Blind, Gate, production, internal, score, or annotation content",
            "this output is a proposal for independent human review and is never truth",
        ],
    }
    return {
        "model": EXPECTED_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return exactly one JSON object. Follow the pairwise-distinct non-copy rule. "
                    "The output is only a synthetic proposal for later independent human review."
                ),
            },
            {"role": "user", "content": canonical_json(prompt)},
        ],
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "stream": False,
        "temperature": 0.2,
        "max_tokens": MAX_OUTPUT_TOKENS_PER_RESPONSE,
    }


def _response_content(response: Mapping[str, Any]) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise PermanentProviderError("provider response envelope drift") from exc
    if not isinstance(content, str):
        raise PermanentProviderError("provider response content type drift")
    return content


def execute_source_v3(
    *,
    transport: Transport,
    exclusion_registry: Mapping[str, Any],
    audit_sink: RecordSink,
    response_sink: RecordSink,
    proposal_sink: RecordSink,
    slots: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    frame = list(build_slot_registry() if slots is None else slots)
    validate_slot_registry(frame)
    accepted: list[dict[str, Any]] = []
    request_hashes: set[str] = set()
    calls = 0
    total_cost = 0.0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    for slot in frame:
        attempt = 1
        prior_failure: str | None = None
        consecutive_transport = 0
        consecutive_failure_category = 0
        response_hash_counts: Counter[str] = Counter()
        while True:
            body = build_request_v3(slot, attempt=attempt, prior_failure=prior_failure)
            request_hash = sha256_text(canonical_json(body))
            if request_hash in request_hashes:
                raise RuntimeError("request replay detected")
            request_hashes.add(request_hash)
            base = {
                "source_protocol_id": SOURCE_PROTOCOL_ID_V3,
                "prompt_contract_id": PROMPT_CONTRACT_ID_V3,
                "authorization_id": AUTHORIZATION_ID,
                "slot_id": slot["slot_id"],
                "attempt": attempt,
                "attempt_version": attempt_version_v3(attempt),
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
                    raise RuntimeError("non-financial hard block: consecutive transport failures")
                prior_failure = "transport"
                attempt += 1
                continue
            consecutive_transport = 0
            usage = usage_and_peak_cost(response)
            total_cost += float(usage["peak_estimated_cost_usd"])
            total_prompt_tokens += int(usage["prompt_tokens"])
            total_completion_tokens += int(usage["completion_tokens"])
            raw = _response_content(response)
            response_hash = sha256_text(raw)
            response_hash_counts[response_hash] += 1
            response_sink(
                {**base, "response_sha256": response_hash, "response_content": raw, **usage}
            )
            if response_hash_counts[response_hash] >= MAX_IDENTICAL_RESPONSE_HASHES:
                raise RuntimeError("non-financial hard block: repeated identical response")
            try:
                proposal = parse_and_validate_proposal(
                    raw,
                    slot=slot,
                    exclusion_registry=exclusion_registry,
                    accepted_proposals=accepted,
                )
                prior_texts = [
                    str(row[field])
                    for row in accepted
                    for field in (
                        "query",
                        "reference",
                        "equivalent_candidate",
                        "factual_conflict_candidate",
                    )
                ]
                for field in (
                    "query",
                    "reference",
                    "equivalent_candidate",
                    "factual_conflict_candidate",
                ):
                    current = str(proposal[field])
                    if any(
                        text_sha256(current) == text_sha256(prior)
                        or template_signature(current) == template_signature(prior)
                        for prior in prior_texts
                    ):
                        raise ValueError("r1_exclusion")
            except ValueError as exc:
                failure = str(exc)
                if failure not in RECOVERABLE_FAILURES:
                    raise RuntimeError(f"unregistered recovery category: {failure}") from exc
                consecutive_failure_category = (
                    consecutive_failure_category + 1 if failure == prior_failure else 1
                )
                audit_sink(
                    {
                        **base,
                        "event": "CALL_COMPLETED",
                        "status": "RECOVERABLE_FAILURE",
                        "failure_category": failure,
                        "response_sha256": response_hash,
                        **usage,
                    }
                )
                if consecutive_failure_category >= MAX_CONSECUTIVE_SAME_MECHANICAL_FAILURE:
                    raise RuntimeError(
                        "non-financial hard block: repeated same mechanical failure"
                    )
                prior_failure = failure
                attempt += 1
                continue
            proposal = {**proposal, "source_attempt_version": attempt_version_v3(attempt)}
            proposal_sink(proposal)
            audit_sink(
                {
                    **base,
                    "event": "CALL_COMPLETED",
                    "status": "ACCEPTED_PROPOSAL_NOT_TRUTH",
                    "response_sha256": response_hash,
                    "proposal_sha256": proposal["proposal_sha256"],
                    **usage,
                }
            )
            accepted.append(proposal)
            break
    return {
        "status": "SOURCE_PROPOSALS_COMPLETE_AWAITING_DATA_LOCK",
        "source_protocol_id": SOURCE_PROTOCOL_ID_V3,
        "accepted_slots": len(accepted),
        "candidate_denominator": len(accepted) * 2,
        "calls": calls,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "peak_estimated_cost_usd": total_cost,
        "proposals": accepted,
    }


__all__ = [
    "PROMPT_CONTRACT_ID_V3",
    "SOURCE_PROTOCOL_ID_V3",
    "attempt_version_v3",
    "build_request_v3",
    "execute_source_v3",
    "materialize_and_validate_families",
    "parse_and_validate_proposal",
]
