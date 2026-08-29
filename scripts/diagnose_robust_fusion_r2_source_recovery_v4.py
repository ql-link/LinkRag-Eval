#!/usr/bin/env python3
"""Read-only, non-semantic structural diagnosis of the sealed v4 live failure."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.r2_measurement import (
    character_ngrams,
    jaccard,
    normalize_text,
    template_signature,
    text_sha256,
)
from linkrag_eval.robust_fusion.r2_source_generation import (
    _language_ok,
    _length_ok,
    build_slot_registry,
    canonical_json,
    normalized_levenshtein,
)
from linkrag_eval.robust_fusion.r2_source_recovery_v4 import (
    build_request_v4,
    edit_rule,
)
from linkrag_eval.robust_fusion.similarity_dev_calibration import (
    sha256_file,
    write_json,
    write_jsonl,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
LIVE_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_v4/"
    "robust-fusion-r2-source-recovery-v4-20260829"
)
PREPARATION_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_preparation_v4/"
    "robust-fusion-r2-source-recovery-preparation-v4-20260829"
)
OUTPUT_ROOT = REPO_ROOT / (
    "runs/robust_fusion/r2_source_recovery_v4_diagnostic_v1/"
    "robust-fusion-r2-source-recovery-v4-diagnostic-v1-20260829"
)
EXCLUSION = REPO_ROOT / (
    "runs/robust_fusion/r2_measurement_v1/robust-fusion-r2-measurement-v1-20260829/"
    "exclusions/registry.json"
)
EXPECTED_INPUTS = {
    PREPARATION_ROOT / "manifest.json": (
        "01b32fc16758418cb6dc2659bc61560786fd7018d307cff5ef81198401dd99cf"
    ),
    LIVE_ROOT / "authorization_receipt_snapshot.json": (
        "f1ddcef8e4e9770d9d6f968b6e75068e60abb6a0776646963d25dceb2cc3f635"
    ),
    LIVE_ROOT / "call_audit.jsonl": (
        "3c3cb03dc85eed353d0a2c6c01d5d58c66f67754b12b4faae3955d8f136a3a86"
    ),
    LIVE_ROOT / "response_archive_synthetic_only.jsonl": (
        "8f0d2cea12e97587d3d54728d3ab0323a9a515d0653d34b934be0c70ae1b6111"
    ),
    LIVE_ROOT / "attempt_scoped_stage_locks.jsonl": (
        "a06f09597055819540ea72ced30bdd986e3640a6f58be0d2dc9a1270fbe52842"
    ),
    LIVE_ROOT / "complete_assembly_attempts_not_truth.jsonl": (
        "1f9964fe8ffc473bac85b0333c552c4e06f562c18f4aa9b9b9bff4292d93a43e"
    ),
    LIVE_ROOT / "accepted_proposals_not_truth.jsonl": (
        "d1e15f11394ed15e2db8248987ba50310472ce206bb433d835144c7c6c98ee6b"
    ),
    LIVE_ROOT / "terminal_error.json": (
        "c192fc455f0e8d26a48717ab1ff5150e3e032eb0fe239e21dcb75934561acae0"
    ),
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _sidecar(path: Path) -> None:
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{sha256_file(path)}  {path.name}\n", encoding="utf-8"
    )


def verify_inputs() -> None:
    for path, expected in EXPECTED_INPUTS.items():
        if sha256_file(path) != expected:
            raise RuntimeError(f"v4 diagnostic input drift: {path.relative_to(REPO_ROOT)}")
    preparation = json.loads((PREPARATION_ROOT / "manifest.json").read_text(encoding="utf-8"))
    for row in preparation["files"]:
        path = REPO_ROOT / row["path"]
        if path.stat().st_size != row["size_bytes"] or sha256_file(path) != row["sha256"]:
            raise RuntimeError(f"v4 preparation input drift: {row['path']}")


def _locked_r_fields(stage_locks: list[dict[str, Any]]) -> dict[str, str]:
    selected = [
        row
        for row in stage_locks
        if row["slot_id"] == "R2SRC-002"
        and row["stage"] == "R"
        and row["orchestration_attempt"] == 1
    ]
    if len(selected) != 1:
        raise RuntimeError("expected exactly one R2SRC-002/R attempt-scoped lock")
    fields = selected[0]["locked_fields"]
    if set(fields) != {"query", "reference"}:
        raise RuntimeError("R2SRC-002/R stage lock schema drift")
    return {key: str(value) for key, value in fields.items()}


def reconstruct_requests(
    response_rows: list[dict[str, Any]], locked_fields: dict[str, str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    slot = next(row for row in build_slot_registry() if row["slot_id"] == "R2SRC-002")
    output = []
    hashes_without_stage_call = []
    for archive in sorted(response_rows, key=lambda row: int(row["stage_response_attempt"])):
        response_attempt = int(archive["stage_response_attempt"])
        body = build_request_v4(
            slot,
            stage="E",
            orchestration_attempt=1,
            response_attempt=response_attempt,
            locked_fields=locked_fields,
        )
        payload_hash = _digest(body)
        if payload_hash != archive["request_sha256"]:
            raise RuntimeError(f"reconstructed request mismatch at E attempt {response_attempt}")
        prompt = json.loads(body["messages"][1]["content"])
        without_stage_call = copy.deepcopy(body)
        stripped_prompt = json.loads(without_stage_call["messages"][1]["content"])
        stripped_prompt.pop("stage_call")
        without_stage_call["messages"][1]["content"] = canonical_json(stripped_prompt)
        hashes_without_stage_call.append(_digest(without_stage_call))
        output.append(
            {
                "slot_id": archive["slot_id"],
                "stage": archive["stage"],
                "orchestration_attempt": archive["orchestration_attempt"],
                "stage_response_attempt": response_attempt,
                "payload_sha256": payload_hash,
                "payload_matches_live_request_sha256": True,
                "messages_sha256": _digest(body["messages"]),
                "payload_without_stage_call_sha256": hashes_without_stage_call[-1],
                "temperature": body.get("temperature"),
                "top_p_present": "top_p" in body,
                "top_p": body.get("top_p"),
                "thinking": body.get("thinking"),
                "response_format": body.get("response_format"),
                "stream": body.get("stream"),
                "orchestration_attempt_metadata_in_payload": (
                    prompt.get("orchestration_attempt")
                ),
                "stage_call_metadata_in_payload": prompt.get("stage_call"),
                "numeric_stage_response_attempt_field_in_payload": (
                    "stage_response_attempt" in prompt
                ),
                "prior_failure_category_in_payload": any(
                    key in prompt
                    for key in (
                        "prior_failure",
                        "prior_failure_category",
                        "prior_mechanical_failure_category",
                    )
                ),
                "deterministic_diversification_instruction_in_payload": False,
            }
        )
    return output, {
        "request_payloads": len(output),
        "unique_payload_sha256": len({row["payload_sha256"] for row in output}),
        "unique_messages_sha256": len({row["messages_sha256"] for row in output}),
        "unique_payload_without_stage_call_sha256": len(set(hashes_without_stage_call)),
        "full_payloads_exactly_identical": len({row["payload_sha256"] for row in output}) == 1,
        "payloads_identical_after_removing_stage_call": len(set(hashes_without_stage_call)) == 1,
        "only_payload_difference": "stage_call_metadata",
    }


def _mechanical_row(
    archive: dict[str, Any],
    *,
    locked_fields: dict[str, str],
    exclusion: dict[str, Any],
    accepted: list[dict[str, Any]],
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "slot_id": archive["slot_id"],
        "stage": archive["stage"],
        "orchestration_attempt": archive["orchestration_attempt"],
        "stage_response_attempt": archive["stage_response_attempt"],
        "request_sha256": archive["request_sha256"],
        "response_sha256": archive["response_sha256"],
        "prompt_tokens": archive["prompt_tokens"],
        "completion_tokens": archive["completion_tokens"],
        "prompt_cache_hit_tokens": archive["prompt_cache_hit_tokens"],
        "prompt_cache_miss_tokens": archive["prompt_cache_miss_tokens"],
        "expected_response_identity_fields": [],
        "request_bound_identity_matches": (
            archive["slot_id"] == "R2SRC-002"
            and archive["stage"] == "E"
            and archive["orchestration_attempt"] == 1
        ),
    }
    try:
        value = json.loads(str(archive["response_content"]))
    except json.JSONDecodeError:
        record.update(
            {
                "json_object": False,
                "exact_keys": False,
                "first_mechanical_failure": "json_parse",
            }
        )
        return record
    record["json_object"] = isinstance(value, dict)
    keys = set(value) if isinstance(value, dict) else set()
    record["response_keys"] = sorted(keys)
    record["exact_keys"] = keys == {"equivalent_candidate"}
    if not isinstance(value, dict) or keys != {"equivalent_candidate"}:
        record["first_mechanical_failure"] = "schema_exact_keys"
        return record
    candidate = str(value["equivalent_candidate"])
    normalized_candidate = normalize_text(candidate)
    reference = locked_fields["reference"]
    language = "zh"
    length = "short"
    record["nonempty"] = bool(candidate.strip())
    record["language_ok"] = _language_ok(candidate, language)
    record["normalized_length_unit"] = "normalized_characters"
    record["normalized_length"] = len(normalized_candidate)
    record["frozen_length_minimum"] = 35
    record["frozen_length_maximum"] = 130
    record["length_ok"] = _length_ok(candidate, language, length)
    record["normalized_unique_from_query"] = (
        normalized_candidate != normalize_text(locked_fields["query"])
    )
    record["normalized_unique_from_reference"] = (
        normalized_candidate != normalize_text(reference)
    )
    distance = normalized_levenshtein(reference, candidate)
    bounds = edit_rule(1)
    record["normalized_levenshtein_from_reference"] = distance
    record["edit_band_minimum"] = bounds["minimum"]
    record["edit_band_maximum"] = bounds["maximum"]
    record["edit_band_ok"] = float(bounds["minimum"]) <= distance <= float(bounds["maximum"])
    digest = text_sha256(candidate)
    template = template_signature(candidate)
    grams = character_ngrams(candidate)
    record["r1_exact_hit"] = digest in set(exclusion["text_sha256"])
    record["r1_template_hit"] = template in set(exclusion["template_sha256"])
    record["r1_5gram_near_duplicate_hit"] = any(
        jaccard(grams, set(prior)) >= 0.82 for prior in exclusion["near_duplicate_ngrams"]
    )
    prior_texts = [
        str(row[field])
        for row in accepted
        for field in ("query", "reference", "equivalent_candidate", "factual_conflict_candidate")
    ]
    record["accepted_r2_cross_slot_exact_template_or_5gram_hit"] = any(
        digest == text_sha256(prior)
        or template == template_signature(prior)
        or jaccard(grams, character_ngrams(prior)) >= 0.82
        for prior in prior_texts
    )
    if not record["nonempty"]:
        failure = "schema_empty"
    elif not record["language_ok"]:
        failure = "language"
    elif not record["length_ok"]:
        failure = "equivalent_candidate_length"
    elif not record["normalized_unique_from_query"]:
        failure = "equivalent_candidate_equals_query"
    elif not record["normalized_unique_from_reference"]:
        failure = "equivalent_candidate_equals_reference"
    elif not record["edit_band_ok"]:
        failure = "equivalent_candidate_edit_band"
    elif any(
        record[key]
        for key in (
            "r1_exact_hit",
            "r1_template_hit",
            "r1_5gram_near_duplicate_hit",
            "accepted_r2_cross_slot_exact_template_or_5gram_hit",
        )
    ):
        failure = "r1_or_accepted_r2_exclusion"
    else:
        failure = "mechanically_valid_stage_value"
    record["first_mechanical_failure"] = failure
    return record


def run(output_root: Path = OUTPUT_ROOT) -> dict[str, Any]:
    if output_root.exists():
        raise RuntimeError("v4 diagnostic output exists; refusing overwrite")
    verify_inputs()
    responses = _read_jsonl(LIVE_ROOT / "response_archive_synthetic_only.jsonl")
    selected = [
        row for row in responses if row["slot_id"] == "R2SRC-002" and row["stage"] == "E"
    ]
    if len(selected) != 6:
        raise RuntimeError("expected exactly six R2SRC-002/E responses")
    stage_locks = _read_jsonl(LIVE_ROOT / "attempt_scoped_stage_locks.jsonl")
    locked_fields = _locked_r_fields(stage_locks)
    exclusion = json.loads(EXCLUSION.read_text(encoding="utf-8"))
    accepted = _read_jsonl(LIVE_ROOT / "accepted_proposals_not_truth.jsonl")
    requests, request_summary = reconstruct_requests(selected, locked_fields)
    mechanical = [
        _mechanical_row(
            row,
            locked_fields=locked_fields,
            exclusion=exclusion,
            accepted=accepted,
        )
        for row in sorted(selected, key=lambda row: int(row["stage_response_attempt"]))
    ]
    failure_counts = Counter(str(row["first_mechanical_failure"]) for row in mechanical)
    audits = _read_jsonl(LIVE_ROOT / "call_audit.jsonl")
    last = audits[-1]
    summary = {
        "status": "FAIL_CLOSED_NON_SEMANTIC_SOURCE_IMPLEMENTATION_DIAGNOSTIC",
        "semantic_evaluation_performed": False,
        "response_text_emitted": False,
        "provider_calls": 0,
        "request_comparison": request_summary,
        "response_hashes": [row["response_sha256"] for row in mechanical],
        "unique_response_hashes": len({row["response_sha256"] for row in mechanical}),
        "mechanical_first_failure_counts": dict(failure_counts),
        "retry_contract": {
            "previous_failure_category_carried": False,
            "numeric_stage_response_attempt_field_carried": False,
            "attempt_index_encoded_only_in_stage_call_string": True,
            "deterministic_diversification_instruction_carried": False,
            "temperature": 0.2,
            "top_p": "ABSENT_PROVIDER_DEFAULT_UNKNOWN",
        },
        "provider_cache_and_context": {
            "saved_prompt_cache_hit_tokens": [
                row["prompt_cache_hit_tokens"] for row in mechanical
            ],
            "saved_prompt_cache_miss_tokens": [
                row["prompt_cache_miss_tokens"] for row in mechanical
            ],
            "response_headers_persisted": False,
            "conversation_history_sent": False,
            "provider_internal_output_reuse_or_cache_causation": "UNKNOWN",
        },
        "repeated_response_breaker": {
            "actual_counter_key": ["slot_id", "stage", "response_sha256"],
            "orchestration_attempt_in_counter_key": False,
            "observed_responses_same_orchestration_attempt": True,
            "threshold": 6,
        },
        "audit_order": {
            "response_archive_written_before_breaker_check": True,
            "call_completed_written_after_breaker_and_stage_validation": True,
            "last_event": {
                key: last.get(key)
                for key in (
                    "event",
                    "slot_id",
                    "stage",
                    "orchestration_attempt",
                    "stage_response_attempt",
                    "request_sha256",
                )
            },
            "crash_consistent_terminal_call_record": False,
            "future_version_fix_needed": True,
        },
        "v5_options": {
            "conservative_recommendation": (
                "inherit R2SRC-001 by locked hash as the only permanently accepted predecessor; "
                "discard R2SRC-002 attempt-scoped R lock; restart R2SRC-002 R-E-C in a new sealed "
                "root; do not call until separately approved"
            ),
            "replay_all_128_under_same_r2": (
                "NOT_RECOMMENDED because v4 declared the first complete mechanically valid "
                "R2SRC-001 object permanently accepted; querying a replacement would reopen "
                "selection after observing a valid object"
            ),
            "formal_128_family_source_data_lock_formed": False,
            "v5_authorized": False,
        },
    }
    output_root.mkdir(parents=True, mode=0o700)
    write_jsonl(output_root / "reconstructed_request_metadata.jsonl", requests)
    write_jsonl(output_root / "response_mechanical_diagnostic.jsonl", mechanical)
    write_json(output_root / "summary.json", summary)
    for path in (
        output_root / "reconstructed_request_metadata.jsonl",
        output_root / "response_mechanical_diagnostic.jsonl",
        output_root / "summary.json",
    ):
        _sidecar(path)
    manifest = {
        "status": summary["status"],
        "inputs": [
            {"path": str(path.relative_to(REPO_ROOT)), "sha256": digest}
            for path, digest in EXPECTED_INPUTS.items()
        ],
        "outputs": [
            {
                "path": path.name,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
            for path in (
                output_root / "reconstructed_request_metadata.jsonl",
                output_root / "response_mechanical_diagnostic.jsonl",
                output_root / "summary.json",
            )
        ],
    }
    write_json(output_root / "manifest.json", manifest)
    _sidecar(output_root / "manifest.json")
    return {
        **summary,
        "manifest_sha256": sha256_file(output_root / "manifest.json"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("run",))
    parser.parse_args()
    print(canonical_json(run()))


if __name__ == "__main__":
    main()
