from __future__ import annotations

import json

from scripts.diagnose_robust_fusion_r2_source_recovery_v4 import (
    LIVE_ROOT,
    OUTPUT_ROOT,
    _locked_r_fields,
    _mechanical_row,
    _read_jsonl,
    reconstruct_requests,
    verify_inputs,
)


def test_v4_diagnostic_inputs_and_reconstructed_payloads_match() -> None:
    verify_inputs()
    responses = [
        row
        for row in _read_jsonl(LIVE_ROOT / "response_archive_synthetic_only.jsonl")
        if row["slot_id"] == "R2SRC-002" and row["stage"] == "E"
    ]
    locked = _locked_r_fields(_read_jsonl(LIVE_ROOT / "attempt_scoped_stage_locks.jsonl"))
    rows, summary = reconstruct_requests(responses, locked)
    assert len(rows) == 6
    assert summary["unique_payload_sha256"] == 6
    assert summary["unique_messages_sha256"] == 6
    assert summary["unique_payload_without_stage_call_sha256"] == 1
    assert all(row["payload_matches_live_request_sha256"] for row in rows)
    assert not any(row["prior_failure_category_in_payload"] for row in rows)
    assert not any(row["deterministic_diversification_instruction_in_payload"] for row in rows)


def test_v4_response_diagnostic_contains_no_response_text_and_is_mechanical() -> None:
    rows = _read_jsonl(OUTPUT_ROOT / "response_mechanical_diagnostic.jsonl")
    assert len(rows) == 6
    assert len({row["response_sha256"] for row in rows}) == 1
    assert {row["first_mechanical_failure"] for row in rows} == {
        "equivalent_candidate_equals_reference"
    }
    assert all(row["json_object"] and row["exact_keys"] for row in rows)
    assert all(row["language_ok"] and row["length_ok"] for row in rows)
    assert all(row["normalized_length"] == 45 for row in rows)
    assert all(row["normalized_levenshtein_from_reference"] == 0.0 for row in rows)
    assert all(not row["edit_band_ok"] for row in rows)
    assert all(not row["r1_exact_hit"] for row in rows)
    assert all(not row["r1_template_hit"] for row in rows)
    assert all(not row["r1_5gram_near_duplicate_hit"] for row in rows)
    assert all("response_content" not in row for row in rows)


def test_v4_summary_records_actual_breaker_scope_and_audit_gap() -> None:
    summary = json.loads((OUTPUT_ROOT / "summary.json").read_text(encoding="utf-8"))
    assert summary["repeated_response_breaker"]["actual_counter_key"] == [
        "slot_id",
        "stage",
        "response_sha256",
    ]
    assert summary["repeated_response_breaker"]["orchestration_attempt_in_counter_key"] is False
    assert summary["audit_order"]["response_archive_written_before_breaker_check"] is True
    assert summary["audit_order"]["crash_consistent_terminal_call_record"] is False


def test_mechanical_helper_does_not_need_or_return_semantic_judgment() -> None:
    responses = [
        row
        for row in _read_jsonl(LIVE_ROOT / "response_archive_synthetic_only.jsonl")
        if row["slot_id"] == "R2SRC-002" and row["stage"] == "E"
    ]
    locked = _locked_r_fields(_read_jsonl(LIVE_ROOT / "attempt_scoped_stage_locks.jsonl"))
    row = _mechanical_row(
        responses[0],
        locked_fields=locked,
        exclusion={"text_sha256": [], "template_sha256": [], "near_duplicate_ngrams": []},
        accepted=[],
    )
    assert "semantic" not in row
    assert "response_content" not in row
