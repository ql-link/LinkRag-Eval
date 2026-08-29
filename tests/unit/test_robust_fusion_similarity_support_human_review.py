from __future__ import annotations

import csv
from pathlib import Path

import pytest

from linkrag_eval.robust_fusion.similarity_support_finalization import (
    build_final_relation_records,
    require_zero_adjudication,
    support_summary,
    terminal_decision,
)
from scripts.review_robust_fusion_similarity_support_supplement import (
    FINALIZATION_DIR,
    RELATION_FIELDS,
    SIMILARITY_FIELDS,
    finalize_zero_adjudication,
    lock_submissions,
    require_bound_input_hashes,
    validate_relation,
    validate_similarity,
    verify_lock,
)


def _write(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def relation_row() -> dict[str, str]:
    return {
        "relation_audit_id": "R1",
        "target_reference_status": "valid",
        "target_group_status": "unique",
        "target_relation": "factual_conflict",
        "conflict_type": "numeric",
        "evidence_locator": "target reference and candidate fact slot",
        "rationale": "same slot, incompatible value",
        "reviewer_id": "researcher-a",
        "confidence": "high",
        "uncertain": "no",
        "adjudication_status": "single",
    }


def test_relation_submission_contract(tmp_path: Path) -> None:
    path = tmp_path / "submission.csv"
    _write(path, RELATION_FIELDS, [relation_row()])
    assert validate_relation(path, {"R1"})[0]["conflict_type"] == "numeric"

    bad = relation_row()
    bad["target_relation"] = "equivalent"
    _write(path, RELATION_FIELDS, [bad])
    with pytest.raises(RuntimeError, match="non-conflict requires"):
        validate_relation(path, {"R1"})


def test_invalid_reference_stops_downstream_relation(tmp_path: Path) -> None:
    path = tmp_path / "submission.csv"
    bad = relation_row()
    bad["target_reference_status"] = "invalid"
    _write(path, RELATION_FIELDS, [bad])
    with pytest.raises(RuntimeError, match="must stop downstream"):
        validate_relation(path, {"R1"})


def test_similarity_submission_contract(tmp_path: Path) -> None:
    path = tmp_path / "submission.csv"
    row = {
        "similarity_audit_id": "S1",
        "human_similarity_ordinal": "4",
        "confidence": "medium",
        "uncertain": "no",
        "note": "",
    }
    _write(path, SIMILARITY_FIELDS, [row])
    assert validate_similarity(path, {"S1"})[0]["human_similarity_ordinal"] == "4"
    row["uncertain"] = "yes"
    _write(path, SIMILARITY_FIELDS, [row])
    with pytest.raises(RuntimeError, match="requires note"):
        validate_similarity(path, {"S1"})


def similarity_row(audit_id: str, score: str = "4") -> dict[str, str]:
    return {
        "similarity_audit_id": audit_id,
        "human_similarity_ordinal": score,
        "confidence": "high",
        "uncertain": "no",
        "note": "",
    }


def zero_review(relation_rows: int, similarity_rows: int) -> dict[str, object]:
    return {
        "relation_rows_each": relation_rows,
        "similarity_rows_each": similarity_rows,
        "relation_adjudication_ids": [],
        "similarity_mandatory_adjudication_ids": [],
        "similarity_adjudication_ids_for_unique_final_score": [],
    }


def test_zero_adjudication_exact_agreement_succeeds() -> None:
    left_relation = relation_row()
    right_relation = {**left_relation, "reviewer_id": "researcher-b"}
    left_similarity = similarity_row("S1")
    right_similarity = similarity_row("S1")

    require_zero_adjudication(
        zero_review(1, 1),
        [left_relation],
        [right_relation],
        [left_similarity],
        [right_similarity],
        expected_relation_rows=1,
        expected_similarity_rows=1,
    )


@pytest.mark.parametrize("kind", ["relation_disagreement", "relation_uncertain", "similarity_disagreement", "similarity_uncertain"])
def test_zero_adjudication_rejects_any_disagreement_or_uncertainty(kind: str) -> None:
    left_relation = relation_row()
    right_relation = {**left_relation, "reviewer_id": "researcher-b"}
    left_similarity = similarity_row("S1")
    right_similarity = similarity_row("S1")
    if kind == "relation_disagreement":
        right_relation["conflict_type"] = "version_or_time"
    elif kind == "relation_uncertain":
        left_relation["uncertain"] = "yes"
    elif kind == "similarity_disagreement":
        right_similarity["human_similarity_ordinal"] = "5"
    else:
        right_similarity["uncertain"] = "yes"

    with pytest.raises(RuntimeError, match="zero-adjudication"):
        require_zero_adjudication(
            zero_review(1, 1),
            [left_relation],
            [right_relation],
            [left_similarity],
            [right_similarity],
            expected_relation_rows=1,
            expected_similarity_rows=1,
        )


def test_locked_submission_and_pre_review_hash_drift_are_rejected(tmp_path: Path) -> None:
    for task, role in (
        ("human_relation", "annotator_a"),
        ("human_relation", "annotator_b"),
        ("human_similarity", "annotator_a"),
        ("human_similarity", "annotator_b"),
    ):
        directory = tmp_path / task / role
        directory.mkdir(parents=True)
        (directory / "submission.csv").write_text("locked\n", encoding="utf-8")
        (directory / "package_manifest.json").write_text("{}\n", encoding="utf-8")
    lock_submissions(tmp_path)
    verify_lock(tmp_path)
    (tmp_path / "human_similarity/annotator_b/submission.csv").write_text(
        "drift\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="locked submission content drift"):
        verify_lock(tmp_path)

    expected = {"pre_adjudication_review": "before", "submission_lock": "same"}
    current = {"pre_adjudication_review": "after", "submission_lock": "same"}
    with pytest.raises(RuntimeError, match="pre_adjudication_review"):
        require_bound_input_hashes(expected, current)


def _support_rows(equivalent_hits: int) -> list[dict[str, object]]:
    rows = []
    for index in range(100):
        equivalent_valid = index < equivalent_hits
        rows.append(
            {
                "preregistered_denominator_slot": "equivalent",
                "final_relation_truth": {
                    "target_reference_status": "valid" if equivalent_valid else "invalid",
                    "target_group_status": "unique" if equivalent_valid else "unresolved",
                    "target_relation": "equivalent" if equivalent_valid else "unresolved",
                },
                "main_similarity": 0.6 if equivalent_valid else None,
            }
        )
        rows.append(
            {
                "preregistered_denominator_slot": "factual_conflict",
                "final_relation_truth": {
                    "target_reference_status": "valid",
                    "target_group_status": "unique",
                    "target_relation": "factual_conflict",
                },
                "main_similarity": 0.4 if index == 0 else 0.8,
            }
        )
    # Give the equivalent side a non-degenerate observed range while retaining
    # exactly the requested number of fixed-denominator hits.
    if equivalent_hits >= 2:
        rows[0]["main_similarity"] = 0.4
        rows[2]["main_similarity"] = 0.8
    return rows


def test_missing_as_miss_uses_fixed_denominator_and_exact_60_percent_boundary() -> None:
    passing = support_summary(_support_rows(60), denominator_each_relation=100)
    assert passing["hit_count_by_relation"]["equivalent"] == 60
    assert passing["diagnostics"]["equivalent"]["total_miss_count"] == 40
    assert passing["coverage_by_relation"]["equivalent"] == 0.60
    assert passing["automatic_coverage_pass"] is True

    failing = support_summary(_support_rows(59), denominator_each_relation=100)
    assert failing["coverage_by_relation"]["equivalent"] == 0.59
    assert failing["automatic_coverage_pass"] is False


def test_human_validity_failure_in_either_scope_blocks_terminal_pass() -> None:
    assert (
        terminal_decision(
            combined_support_pass=True,
            supplement_human_decision="FAIL",
            combined_human_decision="PASS",
        )
        == "FAIL"
    )
    assert (
        terminal_decision(
            combined_support_pass=True,
            supplement_human_decision="PASS",
            combined_human_decision="FAIL",
        )
        == "FAIL"
    )
    assert (
        terminal_decision(
            combined_support_pass=True,
            supplement_human_decision="PASS",
            combined_human_decision="PASS",
        )
        == "PASS"
    )


def test_construction_role_is_slot_not_relation_truth() -> None:
    left = relation_row()
    left["target_relation"] = "equivalent"
    left["conflict_type"] = "not_applicable"
    right = {**left, "reviewer_id": "researcher-b"}
    registry = [
        {
            "relation_audit_id": "R1",
            "query_family_id": "F1",
            "candidate_id": "C1",
            "construction_role": "factual_conflict",
        }
    ]
    final = build_final_relation_records(
        registry,
        [left],
        [right],
        {"C1": {"main_similarity": 0.7}},
        submission_hashes={"relation_a": "a", "relation_b": "b"},
    )[0]
    assert final["preregistered_denominator_slot"] == "factual_conflict"
    assert final["final_relation_truth"]["target_relation"] == "equivalent"


def test_repeated_finalization_refuses_existing_output(tmp_path: Path) -> None:
    (tmp_path / FINALIZATION_DIR).mkdir(parents=True)
    with pytest.raises(RuntimeError, match="refusing to overwrite finalization"):
        finalize_zero_adjudication(tmp_path, tmp_path / "v1", tmp_path / "repo")
