#!/usr/bin/env python3
"""Build a 2000-query Tune set from independently validated generated queries."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


FINAL_QUOTAS = {
    "similar_docs": 600,
    "multi_constraint": 300,
    "number_time": 200,
    "alias": 160,
    "dense_paraphrase": 140,
    "short_keyword": 100,
    "exact_identifier": 80,
}
QUESTION_TYPES = {
    "similar_docs": "paraphrase",
    "multi_constraint": "longtail",
    "number_time": "keyword",
    "alias": "paraphrase",
    "dense_paraphrase": "paraphrase",
    "short_keyword": "keyword",
    "exact_identifier": "keyword",
}
DATASET_IDS = [992000, 992001, 992002, 992003]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _stable(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-golden", type=Path, required=True)
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--pools", type=Path, required=True)
    parser.add_argument("--decisions-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()

    base = _read_jsonl(args.base_golden)
    targets = {row["query_id"]: row for row in _read_jsonl(args.targets)}
    queries = {row["query_id"]: row for row in _read_jsonl(args.queries)}
    pools = {row["query_id"]: row for row in _read_jsonl(args.pools)}
    decisions = {
        row["query_id"]: row
        for path in sorted(args.decisions_dir.glob("pool_*.jsonl"))
        for row in _read_jsonl(path)
    }
    if set(targets) != set(queries) or set(targets) != set(pools):
        raise SystemExit("generation/validation coverage mismatch")
    if args.allow_partial:
        if not set(decisions).issubset(targets):
            raise SystemExit("partial decisions contain unknown query IDs")
    elif set(targets) != set(decisions):
        raise SystemExit("generation/validation coverage mismatch")

    existing_queries = {str(row["query"]).strip() for row in base}
    existing_chunks = {
        str(chunk_id) for row in base for chunk_id in row.get("expected_chunk_ids", [])
    }
    accepted_by_type: dict[str, list[dict[str, Any]]] = {
        type_hint: [] for type_hint in FINAL_QUOTAS
    }
    rejected = Counter()
    used_queries = set(existing_queries)
    used_chunks = set(existing_chunks)
    judge_models = Counter()
    generator_models = Counter(str(row.get("generator_model") or "unknown") for row in queries.values())

    for query_id in sorted(decisions, key=_stable):
        decision = decisions[query_id]
        judge_models[str(decision.get("judge_model") or "unknown")] += 1
        selected = decision.get("relevant_chunk_id")
        if selected is None:
            rejected["judge_null"] += 1
            continue
        candidate = next(
            (
                row
                for row in pools[query_id]["candidates"]
                if str(row["chunk_id"]) == str(selected)
            ),
            None,
        )
        if candidate is None:
            raise SystemExit(f"selected candidate missing: {query_id}")
        query = str(queries[query_id]["query"]).strip()
        chunk_id = str(candidate["chunk_id"])
        type_hint = str(targets[query_id]["type_hint"])
        if query in used_queries:
            rejected["duplicate_query"] += 1
            continue
        if chunk_id in used_chunks:
            rejected["duplicate_positive_chunk"] += 1
            continue
        used_queries.add(query)
        used_chunks.add(chunk_id)
        accepted_by_type[type_hint].append(
            {
                "id": query_id,
                "query": query,
                "user_id": 990001,
                "dataset_ids": DATASET_IDS,
                "expected_chunk_ids": [chunk_id],
                "expected_doc_ids": [int(candidate["doc_id"])],
                "golden_answer": None,
                "type": QUESTION_TYPES[type_hint],
                "note": (
                    f"role=hard; source={queries[query_id].get('generator_model')}-ltr2k; "
                    f"type_hint={type_hint}; hard_reason={targets[query_id]['hard_reason']}; "
                    f"independently_validated=true; judge_model={decision.get('judge_model')}"
                ),
                "relevance_grades": {chunk_id: 3},
            }
        )

    selected_new = []
    available = {}
    for type_hint, quota in FINAL_QUOTAS.items():
        rows = sorted(accepted_by_type[type_hint], key=lambda row: _stable(row["id"]))
        available[type_hint] = len(rows)
        if len(rows) < quota and not args.allow_partial:
            raise SystemExit(
                f"insufficient validated {type_hint}: available={len(rows)} required={quota}"
            )
        selected_new.extend(rows[:quota])

    expanded = [*base, *selected_new]
    if len(base) != 420:
        raise SystemExit(f"invalid base total: {len(base)}")
    if not args.allow_partial and (len(selected_new) != 1580 or len(expanded) != 2000):
        raise SystemExit(
            f"invalid totals: base={len(base)} new={len(selected_new)} total={len(expanded)}"
        )
    if len({row["id"] for row in expanded}) != len(expanded):
        raise SystemExit("duplicate sample IDs")
    if len({row["query"] for row in expanded}) != len(expanded):
        raise SystemExit("duplicate queries")

    base_positive_chunks = [
        str(chunk_id) for row in base for chunk_id in row.get("expected_chunk_ids", [])
    ]
    new_positive_chunks = [
        str(chunk_id) for row in selected_new for chunk_id in row.get("expected_chunk_ids", [])
    ]
    full_positive_chunks = [*base_positive_chunks, *new_positive_chunks]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    new_name = "validated_new_partial.jsonl" if args.allow_partial else "validated_new_1580.jsonl"
    expanded_name = (
        "expanded_tune_partial.jsonl" if args.allow_partial else "expanded_tune_2000.jsonl"
    )
    (args.out_dir / new_name).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in selected_new),
        encoding="utf-8",
    )
    (args.out_dir / expanded_name).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in expanded),
        encoding="utf-8",
    )
    report = {
        "base_samples": len(base),
        "new_samples": len(selected_new),
        "total_samples": len(expanded),
        "requested_new_quotas": FINAL_QUOTAS,
        "validated_available": available,
        "rejected": dict(rejected),
        "generator_models": dict(generator_models),
        "judge_models": dict(judge_models),
        "reference_granularity": "chunk_only",
        "positive_chunk_unique": len(full_positive_chunks) == len(set(full_positive_chunks)),
        "new_positive_chunk_unique": len(new_positive_chunks) == len(set(new_positive_chunks)),
        "new_positive_chunk_disjoint_from_base": not (
            set(new_positive_chunks) & set(base_positive_chunks)
        ),
        "query_unique": True,
        "partial": args.allow_partial,
        "validated_query_coverage": len(decisions),
    }
    report_name = "build_report_partial.json" if args.allow_partial else "build_report.json"
    (args.out_dir / report_name).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
