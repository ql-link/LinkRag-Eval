"""Fail-closed direct authorship controls for R2 source proposals v7."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from linkrag_eval.robust_fusion.r2_measurement import (
    character_ngrams,
    jaccard,
    template_signature,
    text_sha256,
)
from linkrag_eval.robust_fusion.r2_source_execution_v2 import (
    materialize_and_validate_families as base_materialize_families,
)
from linkrag_eval.robust_fusion.r2_source_generation import (
    PROPOSAL_FIELDS,
    build_slot_registry,
    canonical_json,
    parse_and_validate_proposal,
    sha256_text,
)
from linkrag_eval.robust_fusion.r2_source_recovery_v5 import verify_inherited_v4_proposal
from linkrag_eval.robust_fusion.similarity_dev_calibration import sha256_file

SOURCE_PROTOCOL_ID_V7 = "ROBUST-FUSION-R2-SOURCE-CODEX-AUTHORED-2026-08-29-v7"
AUTHORSHIP_ROLE = "codex_direct_authorship"
MODEL_ID = "unavailable_not_inferred"
SOURCE_THREAD_ID = "01a046dd-168d-7151-abb2-d88697fdaadd"
TASK_THREAD_ID = "01a04c5a-d07c-7db3-8641-3bc092ecad51"
AUTHORIZATION_QUOTE = (
    "如果你反复尝试DeepSeek还是觉得不够好，就由你自己替代完成某些任务，"
    "现在你不要管这个要求，先继续至V6结束"
)
V6_ACCEPTED_LEDGER_SHA256 = "58a8c76007ea59429ba69e4b125432921cae99a0772651ed094f3b668724ff37"
V6_PROVENANCE_LEDGER_SHA256 = "a14793ad427bdf50f5620096a3f6cbe113e69dcaef0a79c5b99a36ba5d0a7e93"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def verify_inherited_v6_proposals(
    v4_root: Path,
    v6_root: Path,
    exclusion_registry: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Verify both inherited rows without reading any failed-response archive."""
    if sha256_file(v6_root / "accepted_proposals_not_truth.jsonl") != V6_ACCEPTED_LEDGER_SHA256:
        raise RuntimeError("v6 accepted proposal ledger drift")
    if sha256_file(v6_root / "generator_provenance.jsonl") != V6_PROVENANCE_LEDGER_SHA256:
        raise RuntimeError("v6 generator provenance ledger drift")
    rows = _read_jsonl(v6_root / "accepted_proposals_not_truth.jsonl")
    provenance = _read_jsonl(v6_root / "generator_provenance.jsonl")
    if len(rows) != 2 or [row["slot_id"] for row in rows] != ["R2SRC-001", "R2SRC-002"]:
        raise RuntimeError("v6 inherited accepted denominator/order drift")
    if len(provenance) != 2 or [row["slot_id"] for row in provenance] != [
        "R2SRC-001",
        "R2SRC-002",
    ]:
        raise RuntimeError("v6 inherited provenance identity drift")

    inherited_001, receipt_001 = verify_inherited_v4_proposal(v4_root, exclusion_registry)
    if rows[0] != inherited_001:
        raise RuntimeError("R2SRC-001 byte-level parsed row drift across v4/v6")

    slot_002 = build_slot_registry()[1]
    replay_002 = parse_and_validate_proposal(
        canonical_json({key: rows[1][key] for key in PROPOSAL_FIELDS}),
        slot=slot_002,
        exclusion_registry=exclusion_registry,
        accepted_proposals=[rows[0]],
    )
    if replay_002["proposal_sha256"] != rows[1]["proposal_sha256"]:
        raise RuntimeError("R2SRC-002 unchanged-parser replay hash drift")
    if (
        rows[1].get("generator_model") != "deepseek-v4-pro"
        or rows[1].get("generator_source_protocol_id")
        != "ROBUST-FUSION-R2-SOURCE-RECOVERY-2026-08-29-v6"
    ):
        raise RuntimeError("R2SRC-002 generator provenance drift")
    if rows[1].get("source_attempt_version") != "source-recovery-v6-attempt-0001":
        raise RuntimeError("R2SRC-002 source attempt drift")
    expected_provenance = {
        "R2SRC-001": ("deepseek-v4-flash", receipt_001["proposal_sha256"]),
        "R2SRC-002": ("deepseek-v4-pro", rows[1]["proposal_sha256"]),
    }
    for row in provenance:
        expected_model, expected_hash = expected_provenance[row["slot_id"]]
        if row["generator_model"] != expected_model or row["proposal_sha256"] != expected_hash:
            raise RuntimeError("inherited generator provenance value drift")
    return rows, {
        "status": "R2SRC_001_002_INHERITED_HARD_LOCK_VERIFIED",
        "accepted_ledger_sha256": V6_ACCEPTED_LEDGER_SHA256,
        "provenance_ledger_sha256": V6_PROVENANCE_LEDGER_SHA256,
        "slot_ids": ["R2SRC-001", "R2SRC-002"],
        "proposal_sha256": [rows[0]["proposal_sha256"], rows[1]["proposal_sha256"]],
        "unchanged_parser_and_all_mechanical_gates_pass": True,
        "replaceable": False,
        "failed_response_bodies_read": False,
    }


def validate_authored_proposal(
    raw_proposal: Mapping[str, Any],
    *,
    slot: Mapping[str, Any],
    exclusion_registry: Mapping[str, Any],
    accepted_proposals: Sequence[Mapping[str, Any]],
    attempt: int,
) -> dict[str, Any]:
    """Validate one already-authored object; this function never edits text."""
    if set(raw_proposal) != PROPOSAL_FIELDS:
        raise ValueError("schema")
    parsed = parse_and_validate_proposal(
        canonical_json(raw_proposal),
        slot=slot,
        exclusion_registry=exclusion_registry,
        accepted_proposals=accepted_proposals,
    )
    return {
        **parsed,
        "source_attempt_version": f"codex-authored-v7-attempt-{attempt:04d}",
        "generator_model": MODEL_ID,
        "generator_source_protocol_id": SOURCE_PROTOCOL_ID_V7,
    }


def validate_no_cross_r2_duplicates(families: Sequence[Mapping[str, Any]]) -> None:
    seen_hashes: set[str] = set()
    seen_templates: set[str] = set()
    seen_ngrams: list[set[str]] = []
    for row in families:
        for field in ("query", "reference", "equivalent_candidate", "factual_conflict_candidate"):
            value = str(row[field])
            digest = text_sha256(value)
            template = template_signature(value)
            grams = character_ngrams(value)
            if digest in seen_hashes or template in seen_templates:
                raise RuntimeError("within-R2 exact/template duplicate at v7 data lock")
            if any(jaccard(grams, prior) >= 0.82 for prior in seen_ngrams):
                raise RuntimeError("within-R2 5-gram near duplicate at v7 data lock")
            seen_hashes.add(digest)
            seen_templates.add(template)
            seen_ngrams.append(grams)


def materialize_v7_families(
    proposals: Sequence[Mapping[str, Any]], exclusion_registry: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    families, validation = base_materialize_families(proposals, exclusion_registry)
    if len(families) != len(proposals):
        raise RuntimeError("v7 materialization denominator drift")
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
                raise RuntimeError("v7 authored provenance drift")
        family["provenance_id"] = f"{model}/{slot}/{proposal['source_attempt_version']}"
        family["generator_model"] = model
        family["generator_source_protocol_id"] = protocol
    validate_no_cross_r2_duplicates(families)
    return families, {**validation, "mixed_generator_provenance_assignment": "PASS"}


def proposal_attempt_sha256(value: Mapping[str, Any]) -> str:
    return sha256_text(canonical_json(value))


def byte_line_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
