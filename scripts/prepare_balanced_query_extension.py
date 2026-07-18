#!/usr/bin/env python3
"""Prepare additional candidate batches for unresolved balanced queries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _is_positive(row: dict[str, Any]) -> bool:
    return bool(row.get("relevant")) and int(row.get("grade", 0) or 0) > 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-pool", type=Path, required=True)
    parser.add_argument("--judgments", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--additional-candidates", type=int, required=True)
    parser.add_argument("--batch-size", type=int, default=5)
    args = parser.parse_args()

    judgments = _read_jsonl(args.judgments)
    judged_by_query: dict[str, list[dict[str, Any]]] = {}
    for row in judgments:
        judged_by_query.setdefault(str(row["query_id"]), []).append(row)
    unresolved = {
        query_id
        for query_id, rows in judged_by_query.items()
        if not any(_is_positive(row) for row in rows)
    }

    selected_rows: list[dict[str, Any]] = []
    candidate_counts: list[int] = []
    for pool_row in _read_jsonl(args.candidate_pool):
        query_id = str(pool_row["query_id"])
        if query_id not in unresolved:
            continue
        judged_ids = {
            str(row.get("candidate", {}).get("chunk_id") or row.get("chunk_id"))
            for row in judged_by_query[query_id]
        }
        remaining = [
            candidate
            for candidate in pool_row["candidates"]
            if set(candidate.get("sources") or []) != {"random_neighbor"}
            and str(candidate["chunk_id"]) not in judged_ids
        ][: args.additional_candidates]
        if not remaining:
            continue
        selected_rows.append({**pool_row, "candidates": remaining})
        candidate_counts.append(len(remaining))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for old in args.out_dir.glob("pool_*.jsonl"):
        old.unlink()
    for index, offset in enumerate(range(0, len(selected_rows), args.batch_size), start=1):
        batch = selected_rows[offset : offset + args.batch_size]
        path = args.out_dir / f"pool_{index:03d}.jsonl"
        path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in batch),
            encoding="utf-8",
        )

    report = {
        "candidate_pool": str(args.candidate_pool),
        "base_judgments": str(args.judgments),
        "total_base_queries": len(judged_by_query),
        "unresolved_queries": len(unresolved),
        "prepared_queries": len(selected_rows),
        "batches": (len(selected_rows) + args.batch_size - 1) // args.batch_size,
        "additional_candidates": args.additional_candidates,
        "candidate_count_min": min(candidate_counts, default=0),
        "candidate_count_max": max(candidate_counts, default=0),
    }
    (args.out_dir / "prepare_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
