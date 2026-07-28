#!/usr/bin/env python3
"""Repair known unsupported Blind queries and invalid exact-identifier labels."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from linkrag_eval.retrieval.candidate_routing import (
    classify_candidate_query,
    has_exact_identifier,
)


BLIND_QUERY_REWRITES = {
    "blind-v2-20260718-number-time-0033": (
        "仓内滞留回流到派送时，如何保留滞留原因链条和每次回流记录？"
    ),
    "blind-v2-20260718-number-time-0031": (
        "包裹滞留转人工介入时，自动重派应核对滞留原因还是目的地类型？"
    ),
    "blind-v2-20260718-number-time-0042": "多次滞留后重打面单，应保留哪些回流记录？",
    "blind-v2-20260718-number-time-0011": (
        "滞留中改状态需要二次用户确认时，如何记录每次回流时间？"
    ),
}
ROUTING_TO_SCENARIO = {
    "short_keyword": "short_keyword",
    "exact_identifier": "exact_identifier",
    "number_time": "number_time",
    "long_multi": "multi_constraint",
    "natural_default": "dense_paraphrase",
}
QUESTION_TYPES = {
    "short_keyword": "keyword",
    "exact_identifier": "keyword",
    "number_time": "keyword",
    "multi_constraint": "longtail",
    "dense_paraphrase": "paraphrase",
}
_TYPE_HINT_RE = re.compile(r"(?<=type_hint=)[^;]+")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _note_type_hint(note: str) -> str | None:
    match = _TYPE_HINT_RE.search(note)
    return match.group(0) if match else None


def repair_rows(
    rows: list[dict[str, Any]],
    *,
    rewrite_known_blind_queries: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    repaired = []
    rewrites = []
    relabeled = []
    for original in rows:
        row = dict(original)
        sample_id = str(row["id"])
        old_query = str(row["query"])
        if rewrite_known_blind_queries and sample_id in BLIND_QUERY_REWRITES:
            row["query"] = BLIND_QUERY_REWRITES[sample_id]
            rewrites.append(
                {"sample_id": sample_id, "old_query": old_query, "new_query": row["query"]}
            )

        old_hint = _note_type_hint(str(row.get("note") or ""))
        invalid_exact = old_hint == "exact_identifier" and not has_exact_identifier(
            str(row["query"])
        )
        rewritten_blind = sample_id in BLIND_QUERY_REWRITES and row["query"] != old_query
        if invalid_exact or rewritten_blind:
            routing_bucket = classify_candidate_query(str(row["query"]))
            new_hint = ROUTING_TO_SCENARIO[routing_bucket]
            if old_hint:
                row["note"] = _TYPE_HINT_RE.sub(new_hint, str(row["note"]), count=1)
            else:
                row["note"] = f"{row.get('note', '')}; type_hint={new_hint}".strip("; ")
            row["type"] = QUESTION_TYPES[new_hint]
            if old_hint != new_hint:
                relabeled.append(
                    {
                        "sample_id": sample_id,
                        "old_type_hint": old_hint,
                        "new_type_hint": new_hint,
                        "reason": "invalid_exact_identifier"
                        if invalid_exact
                        else "unsupported_condition_rewrite",
                    }
                )
        repaired.append(row)

    remaining_invalid = [
        row["id"]
        for row in repaired
        if _note_type_hint(str(row.get("note") or "")) == "exact_identifier"
        and not has_exact_identifier(str(row["query"]))
    ]
    if remaining_invalid:
        raise RuntimeError(f"invalid exact_identifier rows remain: {remaining_invalid[:5]}")
    report = {
        "samples": len(repaired),
        "query_rewrites": len(rewrites),
        "scenario_relabels": len(relabeled),
        "rewrite_rows": rewrites,
        "relabel_rows": relabeled,
        "scenario_counts": dict(
            Counter(_note_type_hint(str(row.get("note") or "")) for row in repaired)
        ),
        "remaining_invalid_exact_identifier": 0,
    }
    return repaired, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--rewrite-known-blind-queries", action="store_true")
    args = parser.parse_args()

    rows, report = repair_rows(
        _read_jsonl(args.input),
        rewrite_known_blind_queries=args.rewrite_known_blind_queries,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    report["input"] = str(args.input)
    report["output"] = str(args.out)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
