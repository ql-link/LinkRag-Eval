from __future__ import annotations

from linkrag_eval.robust_fusion.r2_automatic_execution import (
    build_blind_packages,
    build_encoder_inputs,
    build_scored_candidate_frame,
)


def _families() -> list[dict[str, object]]:
    rows = []
    for index in range(128):
        rows.append(
            {
                "family_id": f"R2DEV-{index + 1:03d}",
                "dataset_role": ("public_general", "public_domain", "internal_control")[index % 3],
                "language": "zh" if index % 2 == 0 else "en",
                "length_stratum": "short" if index % 4 < 2 else "long",
                "conflict_type": ("numeric", "version_time", "negation_direction", "applicability_condition")[index % 4],
                "edit_level": index % 4 + 1,
                "query": f"question {index}",
                "reference": f"reference proposition {index}",
                "equivalent_candidate": f"equivalent proposition {index}",
                "factual_conflict_candidate": f"conflict proposition {index}",
            }
        )
    return rows


def test_encoder_inputs_have_fixed_denominator_and_no_scores() -> None:
    rows = build_encoder_inputs(_families())
    assert len(rows) == 384
    assert all("score" not in key for row in rows for key in row)


def test_four_blind_packages_are_opaque_and_complete() -> None:
    registry, packages = build_blind_packages(_families())
    assert len(registry) == 1024
    assert set(packages) == {("A", "relation"), ("B", "relation"), ("A", "similarity"), ("B", "similarity")}
    assert all(len(rows) == 256 for rows in packages.values())
    forbidden = {"candidate_id", "generator_model", "construction_role", "main_similarity", "audit_similarity", "target_relation"}
    assert all(not (set(row) & forbidden) for rows in packages.values() for row in rows)
    assert {row["audit_id"] for row in packages[("A", "relation")]} != {row["audit_id"] for row in packages[("B", "relation")]}


def test_scored_frame_keeps_fixed_denominator() -> None:
    families = _families()
    ids = [f"R2DEV-{index + 1:03d}::CAND-{candidate}" for index in range(128) for candidate in (1, 2)]
    scores = {identifier: 0.5 for identifier in ids}
    rows = build_scored_candidate_frame(families, main_scores=scores, audit_scores=scores)
    assert len(rows) == 256
    assert all(row["main_similarity"] == 0.5 for row in rows)
