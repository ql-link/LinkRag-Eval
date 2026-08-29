"""Pure assembly helpers for the sealed R2 automatic execution and blind packages."""

from __future__ import annotations

import hashlib
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from linkrag_eval.robust_fusion.r2_measurement import build_candidate_rows, text_sha256

AUTOMATIC_EXECUTOR_ID = "ROBUST-FUSION-R2-AUTOMATIC-EXECUTION-2026-08-29-v1"


def build_encoder_inputs(families: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if len(families) != 128:
        raise RuntimeError("R2 encoder input family denominator must be 128")
    rows: list[dict[str, Any]] = []
    for family in families:
        family_id = str(family["family_id"])
        for suffix, field in (
            ("REF", "reference"),
            ("CAND-1", "equivalent_candidate"),
            ("CAND-2", "factual_conflict_candidate"),
        ):
            content = str(family[field])
            rows.append(
                {
                    "chunk_id": f"{family_id}::{suffix}",
                    "family_id": family_id,
                    "content": content,
                    "content_sha256": text_sha256(content),
                }
            )
    rows.sort(key=lambda row: str(row["chunk_id"]).encode("utf-8"))
    if len(rows) != 384 or len({row["chunk_id"] for row in rows}) != 384:
        raise RuntimeError("R2 encoder input denominator/identity drift")
    return rows


def build_scored_candidate_frame(
    families: Sequence[Mapping[str, Any]],
    *,
    main_scores: Mapping[str, float],
    audit_scores: Mapping[str, float],
) -> list[dict[str, Any]]:
    candidates = build_candidate_rows(families)
    output = []
    for row in candidates:
        family_id = str(row["family_id"])
        source_suffix = "CAND-1" if str(row["candidate_id"]).endswith("::A") else "CAND-2"
        opaque_candidate_id = f"{family_id}::{source_suffix}"
        if opaque_candidate_id not in main_scores or opaque_candidate_id not in audit_scores:
            raise RuntimeError(f"missing frozen encoder score: {opaque_candidate_id}")
        output.append(
            {
                "candidate_id": opaque_candidate_id,
                "family_id": family_id,
                "dataset_role": row["dataset"],
                "length_language": row["length_language"],
                "condition_cell": row["condition_cell"],
                "main_similarity": float(main_scores[opaque_candidate_id]),
                "audit_similarity": float(audit_scores[opaque_candidate_id]),
            }
        )
    if len(output) != 256:
        raise RuntimeError("R2 scored candidate denominator drift")
    return output


def build_blind_packages(
    families: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], list[dict[str, Any]]]]:
    candidates = build_candidate_rows(families)
    if len(candidates) != 256:
        raise RuntimeError("R2 blind-package candidate denominator drift")
    by_opaque_id: dict[str, dict[str, Any]] = {}
    for row in candidates:
        family_id = str(row["family_id"])
        suffix = "CAND-1" if str(row["candidate_id"]).endswith("::A") else "CAND-2"
        by_opaque_id[f"{family_id}::{suffix}"] = dict(row)
    registry: list[dict[str, Any]] = []
    packages: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for reviewer in ("A", "B"):
        for task in ("relation", "similarity"):
            ids = sorted(by_opaque_id)
            seed = int.from_bytes(
                hashlib.sha256(f"R2::{reviewer}::{task}".encode()).digest()[:8]
            )
            random.Random(seed).shuffle(ids)
            rows: list[dict[str, Any]] = []
            for ordinal, candidate_id in enumerate(ids, 1):
                source = by_opaque_id[candidate_id]
                audit_id = "R2-" + hashlib.sha256(
                    f"{reviewer}::{task}::{candidate_id}".encode()
                ).hexdigest()[:16].upper()
                registry.append(
                    {
                        "audit_id": audit_id,
                        "reviewer": reviewer,
                        "task": task,
                        "candidate_id": candidate_id,
                        "family_id": source["family_id"],
                        "package_ordinal": ordinal,
                    }
                )
                rows.append(
                    {
                        "audit_id": audit_id,
                        "query": source["query"],
                        "reference": source["reference"],
                        "candidate": source["candidate"],
                    }
                )
            packages[(reviewer, task)] = rows
    if len(registry) != 1024 or any(len(rows) != 256 for rows in packages.values()):
        raise RuntimeError("R2 blind-package registry denominator drift")
    return registry, packages


def truncation_summary(
    families: Sequence[Mapping[str, Any]],
    metadata: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    family_stratum = {
        str(row["family_id"]): f"{row['length_stratum']}_{row['language']}"
        for row in families
    }
    counts = Counter()
    maximum = Counter()
    for row in metadata:
        family_id = str(row["chunk_id"]).split("::", 1)[0]
        stratum = family_stratum[family_id]
        counts[(stratum, bool(row["was_truncated"]))] += 1
        maximum[stratum] = max(maximum[stratum], int(row["untruncated_token_count"]))
    return {
        stratum: {
            "inputs": counts[(stratum, False)] + counts[(stratum, True)],
            "truncated": counts[(stratum, True)],
            "maximum_untruncated_tokens": maximum[stratum],
        }
        for stratum in sorted(family_stratum.values())
    }

