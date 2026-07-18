#!/usr/bin/env python3
"""Inject hidden grounded targets into an independently retrieved validation pool."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=Path, required=True)
    parser.add_argument("--candidate-pool", type=Path, required=True)
    parser.add_argument("--chunks", action="append", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report-out", type=Path, required=True)
    parser.add_argument("--route-candidates", type=int, default=23)
    parser.add_argument("--random-candidates", type=int, default=2)
    args = parser.parse_args()

    seeds = {row["query_id"]: row for row in _read_jsonl(args.seeds)}
    chunks = {
        row["chunk_id"]: row
        for path in args.chunks
        for row in _read_jsonl(path)
    }
    rows = []
    retrieved_targets = 0
    injected_targets = 0
    target_positions = []
    for pool in _read_jsonl(args.candidate_pool):
        query_id = pool["query_id"]
        seed = seeds[query_id]
        target_id = seed["target_chunk_id"]
        route = [
            candidate
            for candidate in pool["candidates"]
            if set(candidate.get("sources") or []) != {"random_neighbor"}
        ][: args.route_candidates]
        random_candidates = [
            candidate
            for candidate in pool["candidates"]
            if set(candidate.get("sources") or []) == {"random_neighbor"}
        ][: args.random_candidates]
        by_id = {candidate["chunk_id"]: candidate for candidate in route + random_candidates}
        if target_id in by_id:
            retrieved_targets += 1
        else:
            target = chunks[target_id]
            by_id[target_id] = {
                "chunk_id": target_id,
                "doc_id": target["doc_id"],
                "dataset_id": target["dataset_id"],
                "content": target["content"],
                "sources": ["audit_injected"],
                "rank_by_source": {"audit_injected": 1},
                "score_by_source": {"audit_injected": 0.0},
            }
            injected_targets += 1
        # Candidate provenance and the generated target ID must remain hidden from
        # the judge. Otherwise ``audit_injected`` or ``target_chunk_id`` reveals
        # which candidate was used to construct the query.
        selected = [
            {
                key: candidate[key]
                for key in ("chunk_id", "doc_id", "dataset_id", "content")
                if key in candidate
            }
            for candidate in by_id.values()
        ]
        rng_seed = int(hashlib.sha256(query_id.encode("utf-8")).hexdigest()[:16], 16)
        random.Random(rng_seed).shuffle(selected)
        target_positions.append(
            next(index for index, candidate in enumerate(selected, start=1) if candidate["chunk_id"] == target_id)
        )
        rows.append({**pool, "candidates": selected})

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    report = {
        "queries": len(rows),
        "retrieved_targets": retrieved_targets,
        "injected_targets": injected_targets,
        "retrieval_target_coverage": retrieved_targets / len(rows) if rows else 0.0,
        "candidate_count_min": min((len(row["candidates"]) for row in rows), default=0),
        "candidate_count_max": max((len(row["candidates"]) for row in rows), default=0),
        "target_position_min": min(target_positions, default=0),
        "target_position_max": max(target_positions, default=0),
        "output": str(args.out),
    }
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
