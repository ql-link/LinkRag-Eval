from __future__ import annotations

import copy

import pytest

from linkrag_eval.robust_fusion.r2_measurement import (
    build_blind_package_rows,
    build_candidate_rows,
    finalize_measurement,
    score_candidate_vectors,
    similarity_agreement,
    validate_family_frame,
)
from linkrag_eval.robust_fusion.r2_measurement_power_v2 import build_frame


def empty_registry() -> dict[str, list[object]]:
    return {
        "family_keys": [],
        "text_sha256": [],
        "template_sha256": [],
        "near_duplicate_ngrams": [],
    }


def family_rows() -> list[dict[str, object]]:
    rows = []
    for ordinal, frame in enumerate(build_frame()[::2]):
        length, language = str(frame["length_language"]).split("_")
        rows.append(
            {
                "family_id": f"R2F{ordinal:03d}",
                "dataset_role": frame["dataset"],
                "language": language,
                "length_stratum": length,
                "conflict_type": frame["conflict_type"],
                "edit_level": frame["edit_level"],
                "query": f"query {ordinal} {language}",
                "reference": f"reference {ordinal} {language}",
                "equivalent_candidate": f"equivalent {ordinal} {language}",
                "factual_conflict_candidate": f"conflict {ordinal} {language}",
                "provenance_id": f"source-{ordinal}",
                "source_record_sha256": f"{ordinal:064x}",
            }
        )
    return rows


def test_family_frame_enforces_fixed_denominator_and_quota() -> None:
    rows = family_rows()
    assert validate_family_frame(rows, empty_registry())["families"] == 128
    with pytest.raises(RuntimeError, match="exactly 128"):
        validate_family_frame(rows[:-1], empty_registry())


def test_exclusion_and_near_duplicate_fail_closed() -> None:
    rows = family_rows()
    registry = empty_registry()
    from linkrag_eval.robust_fusion.r2_measurement import text_sha256

    registry["text_sha256"] = [text_sha256(str(rows[0]["query"]))]
    with pytest.raises(RuntimeError, match="collision"):
        validate_family_frame(rows, registry)


def test_blind_packages_are_complete_distinct_and_similarity_has_no_truth() -> None:
    candidates = build_candidate_rows(family_rows())
    relation_a = build_blind_package_rows(candidates, reviewer="A", task="relation")
    relation_b = build_blind_package_rows(candidates, reviewer="B", task="relation")
    similarity_a = build_blind_package_rows(candidates, reviewer="A", task="similarity")
    assert len(relation_a) == len(relation_b) == len(similarity_a) == 256
    assert [row["candidate_id"] for row in relation_a] != [
        row["candidate_id"] for row in relation_b
    ]
    assert all("target_relation" not in row for row in similarity_a)
    assert all("e5" not in row and "construction_role" not in row for row in similarity_a)


def test_score_is_candidate_to_max_clean_reference_not_query() -> None:
    candidates = build_candidate_rows(family_rows())[:1]
    candidate_id = candidates[0]["candidate_id"]
    family_id = candidates[0]["family_id"]
    result = score_candidate_vectors(
        candidates,
        candidate_vectors={candidate_id: [1.0, 0.0]},
        reference_vectors={family_id: [[0.0, 1.0], [1.0, 0.0]]},
    )
    assert result == [{"candidate_id": candidate_id, "similarity": 1.0}]


def test_similarity_agreement_enforces_qwk_and_within_one() -> None:
    left = [1, 2, 3, 4, 5, 6, 7] * 36 + [1, 2, 3, 4]
    assert len(left) == 256
    result = similarity_agreement(left, list(left))
    assert result["quadratic_weighted_kappa"] == pytest.approx(1.0)
    assert result["within_one_fraction"] == pytest.approx(1.0)
    assert result["pass"] == 1.0


def test_finalizer_missing_is_terminal_fail() -> None:
    rows = []
    for row in build_frame():
        rows.append(
            {
                **row,
                "dataset": row["dataset"],
                "human_score": 5,
                "e5": 0.5,
                "relation_valid": True,
                "similarity_valid": True,
            }
        )
    rows[0]["similarity_valid"] = False
    result = finalize_measurement(rows, bootstrap_iterations=19)
    assert result["status"] == "R2_MEASUREMENT_FAIL_TERMINAL"
    assert result["invalid_rows"] == 1


def test_construction_role_cannot_change_finalizer_truth() -> None:
    rows = []
    for index, row in enumerate(build_frame()):
        score = 8 - int(row["edit_level"])
        if row["relation"] == "factual_conflict":
            score = max(4, score - 1)
        rows.append(
            {
                **row,
                "human_score": score,
                "e5": score + index / 10000,
                "relation_valid": True,
                "similarity_valid": True,
                "construction_role_preview": "wrong",
            }
        )
    changed = copy.deepcopy(rows)
    for row in changed:
        row["construction_role_preview"] = "opposite"
    assert finalize_measurement(rows, bootstrap_iterations=19) == finalize_measurement(
        changed, bootstrap_iterations=19
    )
