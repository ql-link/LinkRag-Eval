from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from linkrag_eval.robust_fusion.similarity_dev_calibration import (
    AUDIT_MODEL_ID,
    AUDIT_REVISION,
    MAIN_MODEL_ID,
    MAIN_REVISION,
    assign_length_strata,
    build_reference_sets,
    canonical_json,
    ensure_method_view_safe,
    load_frozen_dev_inputs,
    reject_confirmatory_path,
    score_candidates,
    verify_encoder_roles,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTE_ROOT = REPO_ROOT / (
    "runs/robust_fusion/internal_v6_route_evidence_v1/"
    "internal-v6-dev-route-evidence-v5-20260829"
)


def _minimal() -> tuple[list[dict], list[dict]]:
    chunks = [
        {"chunk_id": "ref", "content": "正确答案", "content_sha256": "r" * 64},
        {"chunk_id": "cand", "content": "候选答案", "content_sha256": "c" * 64},
    ]
    relations = [
        {
            "query_uid": "q1",
            "chunk_id": "ref",
            "source_chunk_id": "OFFICIAL-REF",
            "source_relevance_label": "relevant_gold",
            "target_equivalence_group_id": "g1",
            "target_relation": "equivalent",
            "conflict_type": "not_applicable",
            "review_status": "agreed_target_valid_unique",
        },
        {
            "query_uid": "q1",
            "chunk_id": "cand",
            "source_chunk_id": "OFFICIAL-CAND",
            "source_relevance_label": "relevant_equivalent",
            "target_equivalence_group_id": "g1",
            "target_relation": "equivalent",
            "conflict_type": "not_applicable",
            "review_status": "agreed",
        },
    ]
    return chunks, relations


def test_frozen_v5_reference_membership_and_digest_are_deterministic() -> None:
    dev = load_frozen_dev_inputs(ROUTE_ROOT)
    first, candidates = build_reference_sets(dev["chunks"], dev["relations"])
    second, replay_candidates = build_reference_sets(dev["chunks"], dev["relations"])

    assert canonical_json(first) == canonical_json(second)
    assert canonical_json(candidates) == canonical_json(replay_candidates)
    assert len(first) == 28
    assert sum(len(row["members"]) for row in first) == 28
    assert len(candidates) == 84
    first_row = next(row for row in first if row["members"][0]["official_record_id"] == "RF-V6D-DOC-001-T-CHUNK-001")
    assert first_row["set_membership_sha256"] == hashlib.sha256(
        canonical_json(["RF-V6D-DOC-001-T-CHUNK-001"]).encode()
    ).hexdigest()


def test_method_view_leakage_is_rejected_recursively() -> None:
    ensure_method_view_safe({"safe.jsonl": [{"route": {"rank": 1}}]})
    with pytest.raises(RuntimeError, match="view leakage"):
        ensure_method_view_safe({"bad.jsonl": [{"nested": {"target_relation": "equivalent"}}]})


def test_empty_duplicate_and_missing_references_are_rejected() -> None:
    chunks, relations = _minimal()
    with pytest.raises(RuntimeError, match="empty/missing A_qg"):
        build_reference_sets(chunks, relations[1:])

    with pytest.raises(RuntimeError, match="duplicate evaluation relation"):
        build_reference_sets(chunks, relations + [copy.deepcopy(relations[0])])

    references, candidates = build_reference_sets(chunks, relations)
    with pytest.raises(RuntimeError, match="missing reference vector"):
        score_candidates(references, candidates, {"cand": [1.0, 0.0]}, expected_dim=2)

    empty_reference = copy.deepcopy(references)
    empty_reference[0]["members"] = []
    with pytest.raises(RuntimeError, match="empty reference set"):
        score_candidates(
            empty_reference,
            candidates,
            {"ref": [1.0, 0.0], "cand": [1.0, 0.0]},
            expected_dim=2,
        )


def test_score_replay_uses_target_reference_not_query() -> None:
    chunks, relations = _minimal()
    references, candidates = build_reference_sets(chunks, relations)
    vectors = {"ref": [1.0, 0.0], "cand": [0.6, 0.8]}
    first = score_candidates(references, candidates, vectors, expected_dim=2)
    second = score_candidates(references, candidates, vectors, expected_dim=2)
    assert first == second
    assert first[0]["max_cosine_similarity"] == pytest.approx(0.6)
    assert first[0]["argmax_reference_id"] == "OFFICIAL-REF"


def test_truncation_metadata_can_be_stratified_into_short_and_long() -> None:
    rows = [
        {"candidate_chunk_id": "c1", "argmax_reference_local_chunk_id": "r1"},
        {"candidate_chunk_id": "c2", "argmax_reference_local_chunk_id": "r2"},
        {"candidate_chunk_id": "c3", "argmax_reference_local_chunk_id": "r3"},
        {"candidate_chunk_id": "c4", "argmax_reference_local_chunk_id": "r4"},
    ]
    result = assign_length_strata(
        rows,
        {"c1": 10, "r1": 12, "c2": 20, "r2": 18, "c3": 130, "r3": 100, "c4": 600, "r4": 40},
    )
    assert result["counts"] == {"long": 2, "short": 2}
    assert [row["length_stratum"] for row in rows] == ["short", "short", "long", "long"]
    assert rows[-1]["pair_untruncated_token_count_max"] == 600


def test_encoder_roles_cannot_be_exchanged() -> None:
    main = {
        "role": "main_similarity_encoder",
        "model_id": MAIN_MODEL_ID,
        "revision": MAIN_REVISION,
    }
    audit = {
        "role": "independent_audit_encoder",
        "model_id": AUDIT_MODEL_ID,
        "revision": AUDIT_REVISION,
    }
    verify_encoder_roles(main, audit)
    with pytest.raises(RuntimeError, match="may not be exchanged"):
        verify_encoder_roles(audit, main)


@pytest.mark.parametrize(
    "relative",
    [
        "data/robust_fusion/internal_stress_v6/gatea/input",
        "data/robust_fusion/internal_stress_v6/Gate-A/input",
        "data/robust_fusion/internal_stress_v6/blind/input",
    ],
)
def test_gate_a_and_blind_paths_are_never_read(relative: str) -> None:
    with pytest.raises(RuntimeError, match="refuses GateA/Blind"):
        reject_confirmatory_path(REPO_ROOT / relative)
