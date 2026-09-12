#!/usr/bin/env python3
"""Describe one human-confirmed Issue 21 submission; never relabel model results."""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from prepare import TYPES, read_rows, unique

HERE = Path(__file__).resolve().parent


def relation(row, source):
    if row["preferred_chunk_id"] is None:
        return row["nondirectional_preference"]
    return "same" if row["preferred_chunk_id"] == source["reference_chunk_id"] else "opposite"


def summarize(rows):
    n = len(rows)
    counts = Counter(r["primary_type"] for r in rows)
    return {
        "queries": n,
        "distinct_pairs": len({(r["role"], r["pair_id"]) for r in rows}),
        "source_groups": len({(r["role"], r["source_group_id"]) for r in rows}),
        "type_counts": {k: counts[k] for k in TYPES},
        "type_percent_of_cohort": {k: 100 * counts[k] / n if n else None for k in TYPES},
        "preference_vs_reference": {
            k: sum(r["preference_vs_reference"] == k for r in rows)
            for k in ("same", "opposite", "tie", "undetermined")
        },
        "status_counts": dict(sorted(Counter(r["status"] for r in rows).items())),
        "preference_unresolved": sum(r["preference_unresolved"] for r in rows),
        "technical_fallback_cases": sum(any(r["technical_fallback"].values()) for r in rows),
    }


def build(received):
    receipt = json.loads((received / "receipt.json").read_text())
    if receipt["human_reviewer_count"] != 1:
        raise ValueError("this analysis accepts one confirmed submission; no automatic consensus")
    source = unique(read_rows(HERE / "private/source-cases.jsonl"), "source_query_id")
    normalized = read_rows(received / "reviewer-labels.jsonl")
    by_qid = unique(normalized, "source_query_id")
    if set(by_qid) != set(source):
        raise ValueError("submission and source populations differ")
    labels, format_notes = [], []
    for qid in sorted(source):
        row, src = by_qid[qid], source[qid]
        if row["role"] != src["role"] or not row["human_confirmed"]:
            raise ValueError("source role or human-confirmation metadata differs")
        if row["preferred_chunk_id"] not in [None, *src["paragraphs"]]:
            raise ValueError("preferred chunk is outside the designated pair")
        label = {
            **row,
            **{k: src[k] for k in (
                "pair_id", "source_group_id", "reference_chunk_id", "reference_basis",
                "official_preferred_chunk_id", "selected_for", "model_outcomes",
                "technical_fallback",
            )},
            "preference_vs_reference": relation(row, src),
            "preference_unresolved": (
                row["status"] == "uncertain" or row["preference"] == "undetermined"
            ),
            "classification_basis": {
                "human_only": "single_human_only_confirmed_submission",
                "model_assisted": "single_model_assisted_human_confirmed_submission",
            }[row["annotation_mode"]],
            "reference_adjudicated": False,
        }
        labels.append(label)
        reason, flags = row["reason"], []
        if '\",' in reason:
            flags.append("quote_comma_fragment")
        if '\"status\":' in reason:
            flags.append("embedded_status_text_not_a_structural_field")
        if '\"reason\":' in reason:
            flags.append("embedded_reason_prefix")
        if reason != reason.rstrip():
            flags.append("trailing_whitespace")
        if flags:
            format_notes.append({"case_id": row["case_id"], "source_query_id": qid,
                                 "flags": flags, "disposition": "preserved_verbatim"})
    cohorts = {
        "all": labels,
        "confirmation_union": [r for r in labels if r["role"] == "confirmation"],
        "E0_development": [r for r in labels if r["role"] == "development"],
        "qwen_first_noncorrect": [r for r in labels if "qwen" in r["selected_for"]],
        "gpt_noncorrect": [r for r in labels if "gpt" in r["selected_for"]],
        "qwen_gpt_shared": [r for r in labels if set(r["selected_for"]) == {"qwen", "gpt"}],
        "qwen_only": [r for r in labels if r["selected_for"] == ["qwen"]],
        "gpt_only": [r for r in labels if r["selected_for"] == ["gpt"]],
    }
    cohorts["qwen_first_noncorrect_without_fallback"] = [
        r for r in cohorts["qwen_first_noncorrect"] if not r["technical_fallback"].get("qwen")
    ]
    cohorts["non_disputed_without_technical_fallback"] = [
        r for r in labels
        if r["primary_type"] != "标签争议" and not any(r["technical_fallback"].values())
    ]
    disputed = [r for r in labels if r["primary_type"] == "标签争议"]
    technical = [r for r in labels if any(r["technical_fallback"].values())]
    summary = {
        "analysis_kind": "descriptive_selected_error_cases",
        "human_reviewer_count": 1,
        "reviewer_slots": sorted({r["reviewer_slot"] for r in labels}),
        "annotation_modes": sorted({r["annotation_mode"] for r in labels}),
        "assistance_notes_verbatim": sorted({r["assistance_notes"] for r in labels}),
        "previous_exposure": sorted({r["previous_exposure"] for r in labels}),
        "cohorts": {k: summarize(v) for k, v in cohorts.items()},
        "reference_dispute_cases": len(disputed),
        "disputed_case_ids": [r["case_id"] for r in disputed],
        "unresolved_case_ids": [r["case_id"] for r in labels if r["preference_unresolved"]],
        "opposite_reference_case_ids": [
            r["case_id"] for r in labels if r["preference_vs_reference"] == "opposite"
        ],
        "technical_fallback_case_ids": [r["case_id"] for r in technical],
        "reference_relation_category_conflicts": [
            r["case_id"] for r in labels
            if (r["preference_vs_reference"] != "same") != (r["primary_type"] == "标签争议")
        ],
        "reason_format_flag_counts": dict(sorted(Counter(
            f for row in format_notes for f in row["flags"]
        ).items())),
        "between_human_agreement": None,
        "reference_adjudication_performed": False,
        "original_research_labels_modified": False,
        "model_results_recomputed": False,
        "official_test_read": False,
        "denominator_note": "query-level selected cases; Qwen/GPT overlap by 50; not population prevalence",
    }
    encode = lambda x: json.dumps(x, ensure_ascii=False, indent=2) + "\n"
    encode_rows = lambda rows: "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    return {
        "labels.jsonl": encode_rows(labels),
        "reference-disputes.jsonl": encode_rows(disputed),
        "technical-fallback.jsonl": encode_rows(technical),
        "reason-format-notes.jsonl": encode_rows(format_notes),
        "summary.json": encode(summary),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--received", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    started = datetime.now(UTC).isoformat()
    start = time.perf_counter()
    outputs = build(args.received)
    for name, content in outputs.items():
        path = args.received / name
        if args.check:
            if not path.exists() or path.read_text() != content:
                raise ValueError(f"analysis output differs: {path}")
        elif path.exists():
            raise ValueError(f"analysis output exists; use --check: {path}")
    if not args.check:
        for name, content in outputs.items():
            (args.received / name).write_text(content)
        (args.received / "analysis-execution.json").write_text(json.dumps({
            "started_at": started, "elapsed_seconds": time.perf_counter() - start,
            "model_requests": 0, "mode": "deterministic_single_submission_description",
        }, ensure_ascii=False, indent=2) + "\n")
    print(f"{'Verified' if args.check else 'Wrote'} {len(outputs)} analysis files")


if __name__ == "__main__":
    main()
