"""Correctly scoped append-only source-data lock executor for R2 v7.1."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from linkrag_eval.robust_fusion.r2_measurement import (
    character_ngrams,
    jaccard,
    template_signature,
    text_sha256,
)
from linkrag_eval.robust_fusion.r2_source_authorship_v7 import (
    MODEL_ID,
    SOURCE_PROTOCOL_ID_V7,
)
from linkrag_eval.robust_fusion.r2_source_execution_v2 import (
    materialize_and_validate_families as base_materialize_families,
)

SOURCE_LOCK_EXECUTOR_ID = "ROBUST-FUSION-R2-SOURCE-LOCK-2026-08-29-v7.1"
TEXT_FIELDS = ("query", "reference", "equivalent_candidate", "factual_conflict_candidate")


def validate_cross_family_duplicates(families: Sequence[Mapping[str, Any]]) -> None:
    """Reject duplicate/near-duplicate text across families, never within one family."""
    seen_hashes: set[str] = set()
    seen_templates: set[str] = set()
    seen_ngrams: list[set[str]] = []
    for family in families:
        current = [str(family[field]) for field in TEXT_FIELDS]
        current_hashes = [text_sha256(value) for value in current]
        current_templates = [template_signature(value) for value in current]
        current_ngrams = [character_ngrams(value) for value in current]
        if any(digest in seen_hashes for digest in current_hashes):
            raise RuntimeError("cross-family exact duplicate at v7.1 data lock")
        if any(signature in seen_templates for signature in current_templates):
            raise RuntimeError("cross-family template duplicate at v7.1 data lock")
        if any(
            jaccard(grams, prior) >= 0.82
            for grams in current_ngrams
            for prior in seen_ngrams
        ):
            raise RuntimeError("cross-family 5-gram near duplicate at v7.1 data lock")
        seen_hashes.update(current_hashes)
        seen_templates.update(current_templates)
        seen_ngrams.extend(current_ngrams)


def materialize_v7_1_families(
    proposals: Sequence[Mapping[str, Any]], exclusion_registry: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    families, validation = base_materialize_families(proposals, exclusion_registry)
    if len(families) != len(proposals):
        raise RuntimeError("v7.1 materialization denominator drift")
    for family, proposal in zip(families, proposals, strict=True):
        slot = str(proposal["slot_id"])
        if slot == "R2SRC-001":
            model = "deepseek-v4-flash"
            protocol = "ROBUST-FUSION-R2-SOURCE-RECOVERY-2026-08-29-v4"
        elif slot == "R2SRC-002":
            model = "deepseek-v4-pro"
            protocol = "ROBUST-FUSION-R2-SOURCE-RECOVERY-2026-08-29-v6"
        else:
            model = str(proposal.get("generator_model"))
            protocol = str(proposal.get("generator_source_protocol_id"))
            if model != MODEL_ID or protocol != SOURCE_PROTOCOL_ID_V7:
                raise RuntimeError("v7.1 authored provenance drift")
        family["provenance_id"] = f"{model}/{slot}/{proposal['source_attempt_version']}"
        family["generator_model"] = model
        family["generator_source_protocol_id"] = protocol
    validate_cross_family_duplicates(families)
    return families, {
        **validation,
        "mixed_generator_provenance_assignment": "PASS",
        "cross_family_exact_template_5gram_recheck": "PASS",
        "within_family_template_5gram_comparison": "NOT_APPLICABLE_BY_FROZEN_DESIGN",
        "source_lock_executor_id": SOURCE_LOCK_EXECUTOR_ID,
    }

