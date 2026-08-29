from __future__ import annotations

import json
from pathlib import Path

import pytest

import linkrag_eval.robust_fusion.r2_source_execution_v2 as execution_v2
from linkrag_eval.robust_fusion.r2_measurement import REQUIRED_FAMILY_FIELDS
from linkrag_eval.robust_fusion.r2_source_execution_v2 import (
    RecoverableTransportError,
    attempt_version,
    build_request_v2,
    execute_source_v2,
    materialize_and_validate_families,
    usage_and_peak_cost,
)
from linkrag_eval.robust_fusion.r2_source_generation import build_slot_registry
from scripts.run_robust_fusion_r2_source_execution_v2 import validate_authorization


def empty_registry() -> dict[str, list[object]]:
    return {"family_keys": [], "text_sha256": [], "template_sha256": [], "near_duplicate_ngrams": []}


def provider_response(content: str = "{}") -> dict[str, object]:
    return {
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "prompt_cache_hit_tokens": 25,
            "prompt_cache_miss_tokens": 75,
        },
        "choices": [{"message": {"content": content}}],
    }


def test_attempt_versions_have_no_budget_or_three_attempt_ceiling() -> None:
    assert attempt_version(1) == "source-execution-v2-attempt-0001"
    assert attempt_version(25) == "source-execution-v2-attempt-0025"
    request = build_request_v2(
        build_slot_registry()[0], attempt=25, prior_failure="language_length_surface"
    )
    assert request["thinking"] == {"type": "disabled"}
    assert request["response_format"] == {"type": "json_object"}
    assert request["model"] == "deepseek-v4-flash"
    serialized = json.dumps(request, ensure_ascii=False)
    assert "normalized_levenshtein" in serialized
    assert "human_score" not in serialized and "candidate_similarity.jsonl" not in serialized


def test_usage_cost_is_recorded_without_token_or_budget_rejection() -> None:
    value = usage_and_peak_cost(
        {
            "usage": {
                "prompt_tokens": 200_000,
                "completion_tokens": 100_000,
                "prompt_cache_hit_tokens": 50_000,
                "prompt_cache_miss_tokens": 150_000,
            }
        }
    )
    assert value["prompt_tokens"] == 200_000
    assert value["peak_estimated_cost_usd"] > 0


def test_state_machine_recovers_beyond_three_and_locks_first_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slots = build_slot_registry()
    calls = 0
    audits: list[dict[str, object]] = []
    responses: list[dict[str, object]] = []
    proposals: list[dict[str, object]] = []

    def parser(_raw: str, *, slot: object, **_kwargs: object) -> dict[str, object]:
        nonlocal calls
        row = dict(slot)  # type: ignore[arg-type]
        if row["slot_id"] == "R2SRC-001" and calls <= 3:
            raise ValueError("schema")
        return {
            **row,
            "query": f"q-{row['slot_id']}",
            "reference": f"r-{row['slot_id']}",
            "equivalent_candidate": f"e-{row['slot_id']}",
            "factual_conflict_candidate": f"c-{row['slot_id']}",
            "proposal_sha256": f"hash-{row['slot_id']}",
            "truth_status": "PROPOSAL_ONLY_AWAITING_INDEPENDENT_HUMAN_REVIEW",
        }

    monkeypatch.setattr(execution_v2, "parse_and_validate_proposal", parser)
    monkeypatch.setattr(execution_v2, "template_signature", lambda text: str(text))

    def transport(_body: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return provider_response(f'{{"call":{calls}}}')

    result = execute_source_v2(
        transport=transport,
        exclusion_registry=empty_registry(),
        audit_sink=lambda row: audits.append(dict(row)),
        response_sink=lambda row: responses.append(dict(row)),
        proposal_sink=lambda row: proposals.append(dict(row)),
        slots=slots,
    )
    assert result["accepted_slots"] == 128
    assert result["calls"] == 131
    assert proposals[0]["source_attempt_version"] == "source-execution-v2-attempt-0004"
    assert len(responses) == 131
    assert len(audits) == 262


def test_identical_response_loop_is_a_nonfinancial_hard_block() -> None:
    with pytest.raises(RuntimeError, match="repeated identical response"):
        execute_source_v2(
            transport=lambda _body: provider_response("{}"),
            exclusion_registry=empty_registry(),
            audit_sink=lambda _row: None,
            response_sink=lambda _row: None,
            proposal_sink=lambda _row: None,
        )


def test_consecutive_transport_errors_are_a_nonfinancial_hard_block() -> None:
    def broken(_body: object) -> dict[str, object]:
        raise RecoverableTransportError("HTTP_503")

    with pytest.raises(RuntimeError, match="consecutive transport"):
        execute_source_v2(
            transport=broken,
            exclusion_registry=empty_registry(),
            audit_sink=lambda _row: None,
            response_sink=lambda _row: None,
            proposal_sink=lambda _row: None,
        )


def test_materialization_retains_fixed_slot_identity_and_no_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposals = []
    for index, slot in enumerate(build_slot_registry(), 1):
        proposals.append(
            {
                **slot,
                "query": f"query-{index}",
                "reference": f"reference-{index}",
                "equivalent_candidate": f"equivalent-{index}",
                "factual_conflict_candidate": f"conflict-{index}",
                "proposal_sha256": f"proposal-{index}",
                "truth_status": "PROPOSAL_ONLY_AWAITING_INDEPENDENT_HUMAN_REVIEW",
                "source_attempt_version": attempt_version(index),
            }
        )
    monkeypatch.setattr(
        execution_v2,
        "validate_family_frame",
        lambda rows, _registry: {"families": len(rows), "candidates": len(rows) * 2},
    )
    monkeypatch.setattr(execution_v2, "jaccard", lambda _left, _right: 0.0)
    monkeypatch.setattr(execution_v2, "template_signature", lambda text: str(text))
    families, summary = materialize_and_validate_families(proposals, empty_registry())
    assert len(families) == 128
    assert families[0]["family_id"] == "R2DEV-001"
    assert set(families[0]) == REQUIRED_FAMILY_FIELDS
    assert "truth_status" not in families[0]
    assert summary["fixed_denominator"] == "PASS"


def test_authorization_requires_exact_sealed_amendment(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="--allow-paid-api"):
        validate_authorization(tmp_path / "none.json", allow_paid_api=False)
    with pytest.raises(RuntimeError, match="only the sealed"):
        validate_authorization(tmp_path / "other.json", allow_paid_api=True)
