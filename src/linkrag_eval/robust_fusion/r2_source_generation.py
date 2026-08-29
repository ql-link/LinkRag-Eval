"""Offline-first, fail-closed R2 synthetic source-generation controls."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from linkrag_eval.robust_fusion.r2_measurement import (
    character_ngrams,
    jaccard,
    normalize_text,
    template_signature,
    text_sha256,
)
from linkrag_eval.robust_fusion.r2_measurement_power_v2 import build_frame

SOURCE_PROTOCOL_ID = "ROBUST-FUSION-R2-SOURCE-GENERATION-2026-08-29-v1"
PRICE_SNAPSHOT_ID = "ROBUST-FUSION-R2-DEEPSEEK-PRICE-2026-08-29-v1"
EXPECTED_BASE_URL = "https://api.deepseek.com/chat/completions"
EXPECTED_MODEL = "deepseek-v4-flash"
MAX_ATTEMPTS_PER_SLOT = 3
MAX_CALLS = 384
HARD_FUSE_USD = 5.0
MAX_INPUT_TOKENS = 8000
MAX_OUTPUT_TOKENS = 4000
PRICE_INPUT_CACHE_MISS_PER_MILLION = 0.44
PRICE_OUTPUT_PER_MILLION = 1.32
PROPOSAL_FIELDS = {
    "slot_id",
    "dataset_role",
    "language",
    "length_stratum",
    "conflict_type",
    "edit_level",
    "query",
    "reference",
    "equivalent_candidate",
    "factual_conflict_candidate",
}
RECOVERABLE_FAILURES = {
    "transport",
    "json_parse",
    "schema",
    "language_length_surface",
    "r1_exclusion",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_slot_registry() -> list[dict[str, Any]]:
    families = build_frame()[::2]
    slots = []
    for index, row in enumerate(families, 1):
        length, language = str(row["length_language"]).split("_")
        slots.append(
            {
                "slot_id": f"R2SRC-{index:03d}",
                "dataset_role": row["dataset"],
                "language": language,
                "length_stratum": length,
                "condition_cell": row["condition_cell"],
                "conflict_type": row["conflict_type"],
                "edit_level": row["edit_level"],
                "fixed_candidate_count": 2,
            }
        )
    validate_slot_registry(slots)
    return slots


def validate_slot_registry(slots: Sequence[Mapping[str, Any]]) -> None:
    if len(slots) != 128 or len({row["slot_id"] for row in slots}) != 128:
        raise RuntimeError("source slot denominator/identity drift")
    dataset_counts = Counter(str(row["dataset_role"]) for row in slots)
    if dataset_counts != Counter(
        {"public_general": 44, "public_domain": 42, "internal_control": 42}
    ):
        raise RuntimeError("source dataset quota drift")
    condition_counts = Counter(str(row["condition_cell"]) for row in slots)
    if len(condition_counts) != 12 or set(condition_counts.values()) - {10, 11}:
        raise RuntimeError("source 12-cell quota drift")
    for length_language in ("short_zh", "long_zh", "short_en", "long_en"):
        selected = [
            row for row in slots if f"{row['length_stratum']}_{row['language']}" == length_language
        ]
        if len(selected) != 32:
            raise RuntimeError(f"source length-language denominator drift: {length_language}")
        cross = Counter((row["conflict_type"], int(row["edit_level"])) for row in selected)
        if len(cross) != 16 or set(cross.values()) != {2}:
            raise RuntimeError(f"source conflict-edit mapping drift: {length_language}")


def attempt_version(attempt: int) -> str:
    if attempt not in {1, 2, 3}:
        raise RuntimeError("attempt must be within frozen 1..3")
    return "primary-v1" if attempt == 1 else f"recovery-v1-{attempt}"


def build_request(
    slot: Mapping[str, Any], *, attempt: int, prior_failure: str | None = None
) -> dict[str, Any]:
    if attempt > 1 and prior_failure not in RECOVERABLE_FAILURES:
        raise RuntimeError("retry is allowed only for frozen mechanical/structural failures")
    prompt = {
        "task": "propose_one_new_non_sensitive_synthetic_microfact_family",
        "slot": dict(slot),
        "attempt_version": attempt_version(attempt),
        "prior_failure_category": prior_failure,
        "constraints": {
            "novel": "invent all names, entities, facts, and wording; do not quote or retrieve data",
            "output_role": "proposal_only_not_truth",
            "pair": "one equivalent and one factual-conflict candidate around the same clean reference",
            "privacy": "no real person, production, R1, Blind, Gate, score, or human annotation content",
            "json_exact_fields": sorted(PROPOSAL_FIELDS),
        },
    }
    body = {
        "model": EXPECTED_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Return only one JSON object. The text is a proposal for later independent human review, never ground truth.",
            },
            {"role": "user", "content": canonical_json(prompt)},
        ],
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "stream": False,
        "temperature": 0.2,
        "max_tokens": MAX_OUTPUT_TOKENS,
    }
    input_bytes = len(canonical_json(body).encode("utf-8"))
    if input_bytes > MAX_INPUT_TOKENS:
        raise RuntimeError("conservative input-byte/token ceiling exceeded")
    return body


def worst_case_call_usd() -> float:
    return (
        MAX_INPUT_TOKENS * PRICE_INPUT_CACHE_MISS_PER_MILLION
        + MAX_OUTPUT_TOKENS * PRICE_OUTPUT_PER_MILLION
    ) / 1_000_000


def peak_cost_usd(input_tokens: int, output_tokens: int) -> float:
    if not 0 <= input_tokens <= MAX_INPUT_TOKENS:
        raise RuntimeError("input token usage missing or above frozen maximum")
    if not 0 <= output_tokens <= MAX_OUTPUT_TOKENS:
        raise RuntimeError("output token usage missing or above frozen maximum")
    return (
        input_tokens * PRICE_INPUT_CACHE_MISS_PER_MILLION + output_tokens * PRICE_OUTPUT_PER_MILLION
    ) / 1_000_000


@dataclass
class BudgetLedger:
    spent_usd: float = 0.0
    calls: int = 0

    def reserve_next(self) -> None:
        if self.calls >= MAX_CALLS:
            raise RuntimeError("384-call hard cap reached")
        if self.spent_usd + worst_case_call_usd() > HARD_FUSE_USD:
            raise RuntimeError("5 USD hard fuse would be exceeded")

    def record(self, *, input_tokens: int, output_tokens: int) -> float:
        cost = peak_cost_usd(input_tokens, output_tokens)
        self.calls += 1
        self.spent_usd += cost
        if self.calls > MAX_CALLS or self.spent_usd >= HARD_FUSE_USD:
            raise RuntimeError("generation budget hard fuse reached")
        return cost

    def record_worst_case(self) -> float:
        self.reserve_next()
        self.calls += 1
        cost = worst_case_call_usd()
        self.spent_usd += cost
        return cost


def _language_ok(text: str, language: str) -> bool:
    han = sum("CJK UNIFIED IDEOGRAPH" in __import__("unicodedata").name(char, "") for char in text)
    latin = sum(char.isascii() and char.isalpha() for char in text)
    return han > latin if language == "zh" else latin > 0 and han == 0


def _length_ok(text: str, language: str, length: str) -> bool:
    normalized = normalize_text(text)
    count = len(normalized) if language == "zh" else len(normalized.split())
    ranges = {
        ("zh", "short"): (35, 130),
        ("zh", "long"): (160, 420),
        ("en", "short"): (18, 70),
        ("en", "long"): (90, 220),
    }
    lower, upper = ranges[(language, length)]
    return lower <= count <= upper


def normalized_levenshtein(left: str, right: str) -> float:
    left = normalize_text(left)
    right = normalize_text(right)
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, 1):
        current = [left_index]
        for right_index, right_char in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1] / max(len(left), len(right), 1)


def parse_and_validate_proposal(
    raw: str,
    *,
    slot: Mapping[str, Any],
    exclusion_registry: Mapping[str, Any],
    accepted_proposals: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("json_parse") from exc
    if not isinstance(value, dict) or set(value) != PROPOSAL_FIELDS:
        raise ValueError("schema")
    for key in (
        "slot_id",
        "dataset_role",
        "language",
        "length_stratum",
        "conflict_type",
        "edit_level",
    ):
        if value[key] != slot[key]:
            raise ValueError("schema")
    text_fields = ("query", "reference", "equivalent_candidate", "factual_conflict_candidate")
    texts = [str(value[field]) for field in text_fields]
    if (
        any(not text.strip() for text in texts)
        or len({normalize_text(text) for text in texts}) != 4
    ):
        raise ValueError("schema")
    if any(not _language_ok(text, str(slot["language"])) for text in texts):
        raise ValueError("language_length_surface")
    if any(
        not _length_ok(text, str(slot["language"]), str(slot["length_stratum"]))
        for text in texts[1:]
    ):
        raise ValueError("language_length_surface")
    edit = int(slot["edit_level"])
    bounds = {1: (0.02, 0.18), 2: (0.08, 0.28), 3: (0.15, 0.40), 4: (0.22, 0.58)}[edit]
    distances = [normalized_levenshtein(texts[1], candidate) for candidate in texts[2:]]
    if any(not bounds[0] <= distance <= bounds[1] for distance in distances):
        raise ValueError("language_length_surface")
    excluded_texts = set(exclusion_registry["text_sha256"])
    excluded_templates = set(exclusion_registry["template_sha256"])
    excluded_ngrams = [set(value) for value in exclusion_registry["near_duplicate_ngrams"]]
    accepted_texts = [str(row[field]) for row in accepted_proposals for field in text_fields]
    for text in texts:
        grams = character_ngrams(text)
        if text_sha256(text) in excluded_texts or template_signature(text) in excluded_templates:
            raise ValueError("r1_exclusion")
        if any(jaccard(grams, prior) >= 0.82 for prior in excluded_ngrams):
            raise ValueError("r1_exclusion")
        if any(jaccard(grams, character_ngrams(prior)) >= 0.82 for prior in accepted_texts):
            raise ValueError("r1_exclusion")
    value["proposal_sha256"] = sha256_text(canonical_json(value))
    value["truth_status"] = "PROPOSAL_ONLY_AWAITING_INDEPENDENT_HUMAN_REVIEW"
    return value


def dry_run_summary(price_snapshot: Mapping[str, Any]) -> dict[str, Any]:
    slots = build_slot_registry()
    requests = [
        build_request(slot, attempt=attempt, prior_failure=None if attempt == 1 else "schema")
        for slot in slots
        for attempt in range(1, 4)
    ]
    request_hashes = [sha256_text(canonical_json(request)) for request in requests]
    if len(set(request_hashes)) != MAX_CALLS:
        raise RuntimeError("dry-run request identity collision")
    theoretical = MAX_CALLS * worst_case_call_usd()
    if not math.isclose(theoretical, float(price_snapshot["theoretical_max_usd"])):
        raise RuntimeError("price snapshot/theoretical budget drift")
    if theoretical >= HARD_FUSE_USD:
        raise RuntimeError("dry-run budget is not below hard fuse")
    return {
        "status": "AWAITING_EXPLICIT_PAID_API_AUTHORIZATION",
        "network_calls": 0,
        "api_key_read": False,
        "slots": len(slots),
        "candidate_denominator": len(slots) * 2,
        "planned_request_envelopes": len(requests),
        "maximum_calls": MAX_CALLS,
        "theoretical_peak_usd": theoretical,
        "hard_fuse_usd": HARD_FUSE_USD,
        "request_plan_sha256": sha256_text("\n".join(request_hashes)),
    }


Transport = Callable[[Mapping[str, Any]], Mapping[str, Any]]
AuditSink = Callable[[Mapping[str, Any]], None]


def execute_with_transport(
    *,
    transport: Transport,
    exclusion_registry: Mapping[str, Any],
    slots: Sequence[Mapping[str, Any]] | None = None,
    audit_sink: AuditSink | None = None,
) -> dict[str, Any]:
    """Execute the sealed recovery state machine with an injected transport."""
    frame = list(build_slot_registry() if slots is None else slots)
    validate_slot_registry(frame)
    accepted: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    request_hashes: set[str] = set()
    budget = BudgetLedger()
    for slot in frame:
        prior_failure: str | None = None
        accepted_for_slot = False
        for attempt in range(1, MAX_ATTEMPTS_PER_SLOT + 1):
            body = build_request(slot, attempt=attempt, prior_failure=prior_failure)
            request_hash = sha256_text(canonical_json(body))
            if request_hash in request_hashes:
                raise RuntimeError("request replay detected")
            request_hashes.add(request_hash)
            budget.reserve_next()
            audit: dict[str, Any] = {
                "slot_id": slot["slot_id"],
                "attempt": attempt,
                "attempt_version": attempt_version(attempt),
                "request_sha256": request_hash,
                "model": EXPECTED_MODEL,
                "price_snapshot_id": PRICE_SNAPSHOT_ID,
                "peak_input_cache_miss_usd_per_million": (
                    PRICE_INPUT_CACHE_MISS_PER_MILLION
                ),
                "peak_output_usd_per_million": PRICE_OUTPUT_PER_MILLION,
            }
            if audit_sink is not None:
                audit_sink({**audit, "event": "REQUEST_DISPATCHED"})
            try:
                response = transport(body)
            except (ConnectionError, OSError, RuntimeError, TimeoutError) as exc:
                prior_failure = "transport"
                audit.update(
                    {
                        "status": "RECOVERABLE_FAILURE",
                        "failure_category": prior_failure,
                        "failure_type": type(exc).__name__,
                        "charged_peak_usd": budget.record_worst_case(),
                        "usage_source": "worst_case_due_transport_failure",
                    }
                )
                audits.append(audit)
                if audit_sink is not None:
                    audit_sink({**audit, "event": "CALL_COMPLETED"})
                continue
            usage = response.get("usage")
            if not isinstance(usage, Mapping):
                raise TypeError("provider usage missing; budget cannot be audited")
            input_tokens = usage.get("prompt_tokens")
            output_tokens = usage.get("completion_tokens")
            if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
                raise TypeError("provider token usage schema drift")
            cost = budget.record(input_tokens=input_tokens, output_tokens=output_tokens)
            try:
                raw = str(response["choices"][0]["message"]["content"])
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError("provider response envelope drift") from exc
            response_hash = sha256_text(raw)
            try:
                proposal = parse_and_validate_proposal(
                    raw,
                    slot=slot,
                    exclusion_registry=exclusion_registry,
                    accepted_proposals=accepted,
                )
            except ValueError as exc:
                failure = str(exc)
                if failure not in RECOVERABLE_FAILURES:
                    raise RuntimeError(f"unregistered recovery category: {failure}") from exc
                prior_failure = failure
                audit.update(
                    {
                        "status": "RECOVERABLE_FAILURE",
                        "failure_category": failure,
                        "response_sha256": response_hash,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "charged_peak_usd": cost,
                    }
                )
                audits.append(audit)
                if audit_sink is not None:
                    audit_sink({**audit, "event": "CALL_COMPLETED"})
                continue
            accepted.append(proposal)
            audit.update(
                {
                    "status": "ACCEPTED_PROPOSAL_NOT_TRUTH",
                    "response_sha256": response_hash,
                    "proposal_sha256": proposal["proposal_sha256"],
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "charged_peak_usd": cost,
                }
            )
            audits.append(audit)
            if audit_sink is not None:
                audit_sink({**audit, "event": "CALL_COMPLETED"})
            accepted_for_slot = True
            break
        if not accepted_for_slot:
            return {
                "status": "SOURCE_GENERATION_TERMINAL_MISSING_FIXED_SLOT",
                "failed_slot_id": slot["slot_id"],
                "accepted_slots": len(accepted),
                "fixed_denominator": 128,
                "calls": budget.calls,
                "charged_peak_usd": budget.spent_usd,
                "audits": audits,
                "proposals": accepted,
            }
    return {
        "status": "SOURCE_PROPOSALS_COMPLETE_AWAITING_HUMAN_AND_DATA_LOCK",
        "accepted_slots": len(accepted),
        "candidate_denominator": len(accepted) * 2,
        "calls": budget.calls,
        "charged_peak_usd": budget.spent_usd,
        "audits": audits,
        "proposals": accepted,
    }
