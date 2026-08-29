from __future__ import annotations

import copy

import pytest

from linkrag_eval.robust_fusion.r2_human_review import (
    RELATION_FIELDS,
    SIMILARITY_FIELDS,
    build_zero_adjudication_rows,
    compare_submissions,
    parse_csv_bytes,
    validate_registry,
    validate_relation_rows,
    validate_similarity_rows,
)


def registry() -> list[dict[str, object]]:
    rows = []
    for ordinal in range(1, 257):
        candidate = f"F{ordinal:03d}::CAND-1"
        for reviewer in ("A", "B"):
            for task in ("relation", "similarity"):
                rows.append(
                    {
                        "audit_id": f"{reviewer}-{task}-{ordinal}",
                        "reviewer": reviewer,
                        "task": task,
                        "candidate_id": candidate,
                        "family_id": f"F{ordinal:03d}",
                        "package_ordinal": ordinal,
                    }
                )
    return rows


def relation_rows(reviewer: str) -> list[dict[str, str]]:
    return [
        {
            "audit_id": f"{reviewer}-relation-{ordinal}",
            "valid_reference": "yes",
            "unique_target_group": "yes",
            "target_relation": "equivalent",
            "conflict_type": "",
            "uncertain": "no",
            "notes": "",
        }
        for ordinal in range(1, 257)
    ]


def similarity_rows(reviewer: str) -> list[dict[str, str]]:
    return [
        {
            "audit_id": f"{reviewer}-similarity-{ordinal}",
            "similarity_1_to_7": str(1 + ordinal % 7),
            "uncertain": "no",
            "notes": "",
        }
        for ordinal in range(1, 257)
    ]


def strata() -> dict[str, dict[str, object]]:
    return {
        f"F{ordinal:03d}": {
            "dataset_role": "public_general",
            "length_language": "short_en",
            "conflict_type_design_stratum_not_truth": "numeric",
            "edit_level": 1,
        }
        for ordinal in range(1, 257)
    }


def comparison() -> dict[str, object]:
    packages = validate_registry(registry())
    return compare_submissions(
        registry_packages=packages,
        relation_a=relation_rows("A"),
        relation_b=relation_rows("B"),
        similarity_a=similarity_rows("A"),
        similarity_b=similarity_rows("B"),
        family_strata=strata(),
    )


def test_strict_csv_schema_and_denominators() -> None:
    body = ",".join(RELATION_FIELDS) + "\n"
    assert parse_csv_bytes(body.encode(), RELATION_FIELDS) == []
    with pytest.raises(RuntimeError, match="header mismatch"):
        parse_csv_bytes((",".join(reversed(RELATION_FIELDS)) + "\n").encode(), RELATION_FIELDS)
    with pytest.raises(RuntimeError, match="fixed denominator"):
        validate_relation_rows([], set())
    with pytest.raises(RuntimeError, match="fixed denominator"):
        validate_similarity_rows([], set())


def test_enum_conditional_and_uncertain_constraints_fail_closed() -> None:
    relation = relation_rows("A")
    relation[0]["conflict_type"] = "numeric"
    with pytest.raises(RuntimeError, match="blank conflict_type"):
        validate_relation_rows(relation, {row["audit_id"] for row in relation})
    similarity = similarity_rows("A")
    similarity[0]["uncertain"] = "yes"
    with pytest.raises(RuntimeError, match="requires notes"):
        validate_similarity_rows(similarity, {row["audit_id"] for row in similarity})


def test_registry_requires_physical_identity_isolation() -> None:
    rows = registry()
    rows[1]["audit_id"] = rows[0]["audit_id"]
    with pytest.raises(RuntimeError, match="physically isolated"):
        validate_registry(rows)


def test_zero_adjudication_requires_exact_common_values() -> None:
    result = comparison()
    assert result["status"] == "VALIDATED_ZERO_ADJUDICATION_READY_FOR_FINALIZER"
    assert result["relation"]["adjudication_count"] == 0
    assert result["similarity"]["adjudication_count"] == 0
    assert result["similarity"]["quadratic_weighted_kappa"] == pytest.approx(1.0)


def test_any_difference_or_uncertain_requires_human_adjudication() -> None:
    packages = validate_registry(registry())
    relation_b = relation_rows("B")
    relation_b[0]["target_relation"] = "factual_conflict"
    relation_b[0]["conflict_type"] = "numeric"
    similarity_b = similarity_rows("B")
    similarity_b[1]["similarity_1_to_7"] = "7"
    similarity_b[2]["uncertain"] = "yes"
    similarity_b[2]["notes"] = "human uncertainty"
    result = compare_submissions(
        registry_packages=packages,
        relation_a=relation_rows("A"),
        relation_b=relation_b,
        similarity_a=similarity_rows("A"),
        similarity_b=similarity_b,
        family_strata=strata(),
    )
    assert result["status"] == "AWAITING_HUMAN_ADJUDICATION"
    assert result["relation"]["adjudication_count"] == 1
    assert result["similarity"]["adjudication_count"] == 2


def test_final_rows_use_only_exact_human_values_not_construction_role() -> None:
    result = comparison()
    automatic = [
        {
            "candidate_id": f"F{ordinal:03d}::CAND-1",
            "dataset_role": "public_general",
            "length_language": "short_en",
            "condition_cell": "public_general__short_en",
            "main_similarity": ordinal / 1000,
            "audit_similarity": ordinal / 1001,
            "construction_role_preview": "wrong",
        }
        for ordinal in range(1, 257)
    ]
    changed = copy.deepcopy(automatic)
    for row in changed:
        row["construction_role_preview"] = "opposite"
    left = build_zero_adjudication_rows(result, automatic)
    right = build_zero_adjudication_rows(result, changed)
    assert left == right
    assert all("construction_role_preview" not in row for row in left)


def test_zero_finalizer_rejects_disagreement() -> None:
    result = comparison()
    result["status"] = "AWAITING_HUMAN_ADJUDICATION"
    with pytest.raises(RuntimeError, match="requires empty adjudication"):
        build_zero_adjudication_rows(result, [])


def test_similarity_schema_is_frozen() -> None:
    assert SIMILARITY_FIELDS == ("audit_id", "similarity_1_to_7", "uncertain", "notes")
