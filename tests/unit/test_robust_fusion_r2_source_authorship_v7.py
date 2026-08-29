from __future__ import annotations

import json
from pathlib import Path

import pytest

from linkrag_eval.robust_fusion.r2_source_authorship_v7 import (
    MODEL_ID,
    SOURCE_PROTOCOL_ID_V7,
    materialize_v7_families,
    validate_authored_proposal,
)
from linkrag_eval.robust_fusion.r2_source_generation import PROPOSAL_FIELDS


def _empty_exclusion() -> dict[str, list[object]]:
    return {"text_sha256": [], "template_sha256": [], "near_duplicate_ngrams": []}


def _fixture(slot_id: str = "FIXTURE-NOT-A-FORMAL-SLOT") -> dict[str, object]:
    reference = (
        "Within the entirely fictional amber district, the relay sends exactly seven quiet "
        "pulses before dawn to guide small survey balloons home."
    )
    return {
        "slot_id": slot_id,
        "dataset_role": "public_general",
        "language": "en",
        "length_stratum": "short",
        "conflict_type": "numeric",
        "edit_level": 1,
        "query": "How many quiet pulses does the entirely fictional amber relay send before dawn?",
        "reference": reference,
        "equivalent_candidate": (
            "Within the entirely fictional amber district, the relay emits exactly seven quiet "
            "pulses before dawn to guide small survey balloons home."
        ),
        "factual_conflict_candidate": (
            "Within the entirely fictional amber district, the relay sends exactly nine quiet "
            "pulses before dawn to guide small survey balloons home."
        ),
    }


def test_validate_is_pass_through_and_adds_only_provenance() -> None:
    raw = _fixture()
    accepted = validate_authored_proposal(
        raw,
        slot={
            key: raw[key]
            for key in (
                "slot_id",
                "dataset_role",
                "language",
                "length_stratum",
                "conflict_type",
                "edit_level",
            )
        },
        exclusion_registry=_empty_exclusion(),
        accepted_proposals=[],
        attempt=1,
    )
    assert {key: accepted[key] for key in PROPOSAL_FIELDS} == raw
    assert accepted["generator_model"] == MODEL_ID
    assert accepted["generator_source_protocol_id"] == SOURCE_PROTOCOL_ID_V7


def test_rejects_text_identity_and_out_of_band_edit() -> None:
    raw = _fixture()
    raw["equivalent_candidate"] = raw["reference"]
    with pytest.raises(ValueError, match="schema"):
        validate_authored_proposal(
            raw,
            slot={
                key: raw[key]
                for key in (
                    "slot_id",
                    "dataset_role",
                    "language",
                    "length_stratum",
                    "conflict_type",
                    "edit_level",
                )
            },
            exclusion_registry=_empty_exclusion(),
            accepted_proposals=[],
            attempt=1,
        )


def test_materializer_requires_fixed_denominator() -> None:
    with pytest.raises(RuntimeError, match="128"):
        materialize_v7_families([], _empty_exclusion())


def test_protocol_has_no_network_dependency() -> None:
    source = Path("src/linkrag_eval/robust_fusion/r2_source_authorship_v7.py").read_text()
    runner = Path("scripts/run_robust_fusion_r2_source_authorship_v7.py").read_text()
    assert "httpx" not in source + runner
    assert "dotenv" not in source + runner
    assert "EVAL_JUDGE" not in source + runner


def test_fixture_is_not_a_formal_authorship_body() -> None:
    assert json.dumps(_fixture(), ensure_ascii=False).find("R2SRC-") == -1
