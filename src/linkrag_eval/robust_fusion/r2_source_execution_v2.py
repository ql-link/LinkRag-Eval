"""Authorized, unbudgeted R2 source execution with non-financial circuit breakers."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from linkrag_eval.robust_fusion.r2_measurement import (
    character_ngrams,
    jaccard,
    template_signature,
    text_sha256,
    validate_family_frame,
)
from linkrag_eval.robust_fusion.r2_source_generation import (
    EXPECTED_MODEL,
    PRICE_INPUT_CACHE_MISS_PER_MILLION,
    PRICE_OUTPUT_PER_MILLION,
    PROPOSAL_FIELDS,
    build_slot_registry,
    canonical_json,
    parse_and_validate_proposal,
    sha256_text,
    validate_slot_registry,
)

SOURCE_PROTOCOL_ID_V2 = "ROBUST-FUSION-R2-SOURCE-EXECUTION-2026-08-29-v2"
AUTHORIZATION_ID = "ROBUST-FUSION-R2-SOURCE-AUTH-20260829-v2-RESEARCH-LEAD-USER"
PRICE_INPUT_CACHE_HIT_PER_MILLION = 0.014
MAX_OUTPUT_TOKENS_PER_RESPONSE = 4000
MAX_CONSECUTIVE_TRANSPORT_FAILURES = 8
MAX_CONSECUTIVE_SAME_MECHANICAL_FAILURE = 24
MAX_IDENTICAL_RESPONSE_HASHES = 6
RECOVERABLE_FAILURES = {
    "transport",
    "json_parse",
    "schema",
    "language_length_surface",
    "r1_exclusion",
}


class RecoverableTransportError(RuntimeError):
    """A transient provider/network failure eligible for same-command recovery."""


class PermanentProviderError(RuntimeError):
    """A provider failure that must terminate without command-level retry."""


Transport = Callable[[Mapping[str, Any]], Mapping[str, Any]]
RecordSink = Callable[[Mapping[str, Any]], None]


def attempt_version(attempt: int) -> str:
    if attempt < 1:
        raise ValueError("attempt must be positive")
    return f"source-execution-v2-attempt-{attempt:04d}"


def _surface_constraints(slot: Mapping[str, Any]) -> dict[str, Any]:
    language = str(slot["language"])
    length = str(slot["length_stratum"])
    ranges = {
        ("zh", "short"): {"unit": "normalized_characters", "minimum": 35, "maximum": 130},
        ("zh", "long"): {"unit": "normalized_characters", "minimum": 160, "maximum": 420},
        ("en", "short"): {"unit": "words", "minimum": 18, "maximum": 70},
        ("en", "long"): {"unit": "words", "minimum": 90, "maximum": 220},
    }
    edit_bounds = {
        1: {"minimum": 0.02, "maximum": 0.18},
        2: {"minimum": 0.08, "maximum": 0.28},
        3: {"minimum": 0.15, "maximum": 0.40},
        4: {"minimum": 0.22, "maximum": 0.58},
    }
    return {
        "reference_and_both_candidates_length": ranges[(language, length)],
        "normalized_levenshtein_from_reference_for_each_candidate": edit_bounds[
            int(slot["edit_level"])
        ],
        "language": language,
    }


def build_request_v2(
    slot: Mapping[str, Any], *, attempt: int, prior_failure: str | None
) -> dict[str, Any]:
    if attempt > 1 and prior_failure not in RECOVERABLE_FAILURES:
        raise RuntimeError("recovery requires a registered mechanical failure")
    recovery_instruction = {
        None: "follow every mechanical constraint on the first proposal",
        "transport": "repeat the same fixed slot without changing its identity",
        "json_parse": "return one syntactically valid JSON object and nothing else",
        "schema": "use exactly the required keys and copy all six slot identity values exactly",
        "language_length_surface": (
            "correct the requested language, length range, and both edit-distance ranges"
        ),
        "r1_exclusion": (
            "invent different fictional entities, facts, wording, and sentence structure"
        ),
    }[prior_failure]
    prompt = {
        "task": "propose_one_new_non_sensitive_synthetic_microfact_family",
        "slot": dict(slot),
        "attempt_version": attempt_version(attempt),
        "prior_mechanical_failure_category": prior_failure,
        "recovery_instruction": recovery_instruction,
        "required_exact_json_fields": sorted(PROPOSAL_FIELDS),
        "surface_constraints": _surface_constraints(slot),
        "semantic_construction_request_for_later_human_review": {
            "query": "ask about the invented microfact in the requested language",
            "reference": "state one fully invented microfact; use no real person or organization",
            "equivalent_candidate": "preserve every factual condition while paraphrasing",
            "factual_conflict_candidate": (
                f"change exactly one {slot['conflict_type']} fact while matching surface structure"
            ),
        },
        "prohibitions": [
            "no real person, organization, production, internal, R1, Blind, or Gate content",
            "no model score, human annotation, answer key, or construction-role truth claim",
            "no markdown fence or prose outside the single JSON object",
        ],
        "output_role": "proposal_only_not_truth",
    }
    return {
        "model": EXPECTED_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return exactly one JSON object. It is only a synthetic proposal for later "
                    "independent human review and is never ground truth."
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


def usage_and_peak_cost(response: Mapping[str, Any]) -> dict[str, Any]:
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        raise PermanentProviderError("provider usage missing")
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    if not isinstance(prompt_tokens, int) or not isinstance(completion_tokens, int):
        raise PermanentProviderError("provider usage schema drift")
    hit = usage.get("prompt_cache_hit_tokens", 0)
    miss = usage.get("prompt_cache_miss_tokens")
    if not isinstance(hit, int):
        hit = 0
    if not isinstance(miss, int):
        miss = max(prompt_tokens - hit, 0)
    if min(prompt_tokens, completion_tokens, hit, miss) < 0:
        raise PermanentProviderError("negative provider token usage")
    cost = (
        hit * PRICE_INPUT_CACHE_HIT_PER_MILLION
        + miss * PRICE_INPUT_CACHE_MISS_PER_MILLION
        + completion_tokens * PRICE_OUTPUT_PER_MILLION
    ) / 1_000_000
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "prompt_cache_hit_tokens": hit,
        "prompt_cache_miss_tokens": miss,
        "peak_estimated_cost_usd": cost,
    }


def _response_content(response: Mapping[str, Any]) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise PermanentProviderError("provider response envelope drift") from exc
    if not isinstance(content, str):
        raise PermanentProviderError("provider response content type drift")
    return content


def execute_source_v2(
    *,
    transport: Transport,
    exclusion_registry: Mapping[str, Any],
    audit_sink: RecordSink,
    response_sink: RecordSink,
    proposal_sink: RecordSink,
    slots: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run fixed slots until accepted or a non-financial hard blocker is reached."""
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
            body = build_request_v2(slot, attempt=attempt, prior_failure=prior_failure)
            request_hash = sha256_text(canonical_json(body))
            if request_hash in request_hashes:
                raise RuntimeError("request replay detected")
            request_hashes.add(request_hash)
            base_audit = {
                "source_protocol_id": SOURCE_PROTOCOL_ID_V2,
                "authorization_id": AUTHORIZATION_ID,
                "slot_id": slot["slot_id"],
                "attempt": attempt,
                "attempt_version": attempt_version(attempt),
                "request_sha256": request_hash,
                "model": EXPECTED_MODEL,
            }
            audit_sink({**base_audit, "event": "REQUEST_DISPATCHED"})
            calls += 1
            try:
                response = transport(body)
            except RecoverableTransportError as exc:
                consecutive_transport += 1
                failure = "transport"
                audit_sink(
                    {
                        **base_audit,
                        "event": "CALL_COMPLETED",
                        "status": "RECOVERABLE_FAILURE",
                        "failure_category": failure,
                        "failure_type": type(exc).__name__,
                        "failure_detail": str(exc)[:240],
                    }
                )
                if consecutive_transport >= MAX_CONSECUTIVE_TRANSPORT_FAILURES:
                    raise RuntimeError("non-financial hard block: consecutive transport failures")
                prior_failure = failure
                attempt += 1
                continue
            except PermanentProviderError:
                raise
            consecutive_transport = 0
            usage = usage_and_peak_cost(response)
            total_cost += float(usage["peak_estimated_cost_usd"])
            total_prompt_tokens += int(usage["prompt_tokens"])
            total_completion_tokens += int(usage["completion_tokens"])
            raw = _response_content(response)
            response_hash = sha256_text(raw)
            response_hash_counts[response_hash] += 1
            response_sink(
                {
                    **base_audit,
                    "response_sha256": response_hash,
                    "response_content": raw,
                    **usage,
                }
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
                        **base_audit,
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
            audit_sink(
                {
                    **base_audit,
                    "event": "CALL_COMPLETED",
                    "status": "ACCEPTED_PROPOSAL_NOT_TRUTH",
                    "response_sha256": response_hash,
                    "proposal_sha256": proposal["proposal_sha256"],
                    **usage,
                }
            )
            proposal = {**proposal, "source_attempt_version": attempt_version(attempt)}
            proposal_sink(proposal)
            accepted.append(proposal)
            break
    return {
        "status": "SOURCE_PROPOSALS_COMPLETE_AWAITING_DATA_LOCK",
        "source_protocol_id": SOURCE_PROTOCOL_ID_V2,
        "accepted_slots": len(accepted),
        "candidate_denominator": len(accepted) * 2,
        "calls": calls,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "peak_estimated_cost_usd": total_cost,
        "proposals": accepted,
    }


def materialize_and_validate_families(
    proposals: Sequence[Mapping[str, Any]], exclusion_registry: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if len(proposals) != 128:
        raise RuntimeError("source proposals must fill the fixed 128-family denominator")
    families = []
    for index, proposal in enumerate(proposals, 1):
        expected_slot = f"R2SRC-{index:03d}"
        if proposal["slot_id"] != expected_slot:
            raise RuntimeError("accepted proposal slot ordering/identity drift")
        families.append(
            {
                "family_id": f"R2DEV-{index:03d}",
                "dataset_role": proposal["dataset_role"],
                "language": proposal["language"],
                "length_stratum": proposal["length_stratum"],
                "conflict_type": proposal["conflict_type"],
                "edit_level": proposal["edit_level"],
                "query": proposal["query"],
                "reference": proposal["reference"],
                "equivalent_candidate": proposal["equivalent_candidate"],
                "factual_conflict_candidate": proposal["factual_conflict_candidate"],
                "provenance_id": (
                    f"deepseek-v4-flash/{proposal['slot_id']}/"
                    f"{proposal['source_attempt_version']}"
                ),
                "source_record_sha256": proposal["proposal_sha256"],
            }
        )
    summary = validate_family_frame(families, exclusion_registry)
    seen_text_hashes: set[str] = set()
    seen_templates: set[str] = set()
    seen_ngrams: list[set[str]] = []
    for row in families:
        family_text_hashes: set[str] = set()
        family_templates: set[str] = set()
        family_ngrams: list[set[str]] = []
        for field in ("query", "reference", "equivalent_candidate", "factual_conflict_candidate"):
            value = str(row[field])
            digest = text_sha256(value)
            template = template_signature(value)
            grams = character_ngrams(value)
            if digest in seen_text_hashes or template in seen_templates:
                raise RuntimeError("within-R2 exact/template duplicate at data lock")
            if any(jaccard(grams, prior) >= 0.82 for prior in seen_ngrams):
                raise RuntimeError("within-R2 5-gram near duplicate at data lock")
            family_text_hashes.add(digest)
            family_templates.add(template)
            family_ngrams.append(grams)
        seen_text_hashes.update(family_text_hashes)
        seen_templates.update(family_templates)
        seen_ngrams.extend(family_ngrams)
    return families, {
        **summary,
        "r1_exact_template_5gram_exclusion": "PASS",
        "within_r2_exact_template_5gram_exclusion": "PASS",
        "fixed_denominator": "PASS",
        "quota_validation": "PASS",
    }


def dry_run_v2() -> dict[str, Any]:
    slots = build_slot_registry()
    requests = [
        build_request_v2(slot, attempt=attempt, prior_failure=None if attempt == 1 else "schema")
        for slot in slots
        for attempt in (1, 4, 25)
    ]
    hashes = [hashlib.sha256(canonical_json(row).encode()).hexdigest() for row in requests]
    if len(hashes) != 384 or len(set(hashes)) != 384:
        raise RuntimeError("v2 unbounded-version request identity drift")
    return {
        "status": "AUTHORIZED_ZERO_NETWORK_DRY_RUN_COMPLETE",
        "network_calls": 0,
        "api_key_read": False,
        "slots": 128,
        "candidate_denominator": 256,
        "sampled_attempt_versions": [1, 4, 25],
        "budget_or_total_call_limit": None,
        "request_plan_sha256": hashlib.sha256("\n".join(hashes).encode()).hexdigest(),
    }
