#!/usr/bin/env python3
"""Write per-query candidate coverage for the three retrieval routes."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

from linkrag_eval.config import get_settings
from linkrag_eval.golden.loader import load_golden
from linkrag_eval.retrieval.tuning import (
    TuneConfig,
    cache_route_hits,
    stage_output_for_config,
)


def _first_rank(hits, expected: set[str]) -> int | None:
    for rank, hit in enumerate(hits, start=1):
        if hit.chunk_id in expected:
            return rank
    return None


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--summary-out", required=True)
    parser.add_argument("--concurrency", type=int, default=2)
    args = parser.parse_args()

    samples = load_golden(args.golden)
    cached = await cache_route_hits(
        samples, settings=get_settings(), max_dense_top_k=300,
        max_sparse_top_k=100, max_bm25_top_k=100, concurrency=args.concurrency,
    )
    # The currently selected three-route candidate configuration.
    config = TuneConfig(
        dense_top_k=150, sparse_top_k=50, bm25_top_k=100,
        dense_threshold=0.3, sparse_threshold=0.2, bm25_threshold=0.0,
        final_top_k=10, rrf_k=60,
    )
    weights = {"dense": 0.70, "sparse": 0.15, "bm25": 0.15}
    rows = []
    counts: Counter[str] = Counter()
    failed = 0
    for item in cached:
        expected = set(item.sample.expected_chunk_ids)
        ranks = {
            "dense": _first_rank(item.dense_hits, expected),
            "sparse": _first_rank(item.sparse_hits, expected),
            "bm25": _first_rank(item.bm25_hits, expected),
        }
        output = stage_output_for_config(
            item, config, fusion_strategy="weighted_score", fusion_weights=weights
        )
        final_rank = _first_rank(output.ranked, expected)
        if final_rank is not None:
            diagnosis = "top10_hit"
        elif any(rank is not None for rank in ranks.values()):
            diagnosis = "fusion_miss"
        else:
            diagnosis = "candidate_miss"
        counts[diagnosis] += 1
        failed += bool(item.failed_sources)
        rows.append({
            "query_id": item.sample.id,
            "query": item.sample.query,
            "expected_chunk_ids": sorted(expected),
            "route_first_rank": ranks,
            "union_candidate_hit": any(rank is not None for rank in ranks.values()),
            "final_rank": final_rank,
            "diagnosis": diagnosis,
            "failed_sources": list(item.failed_sources),
        })
    Path(args.out).write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    Path(args.summary_out).write_text(json.dumps({
        "queries": len(rows), "failed_source_queries": failed,
        "diagnosis_counts": dict(sorted(counts.items())),
        "candidate_union_recall": (counts["top10_hit"] + counts["fusion_miss"]) / len(rows) if rows else 0,
        "final_recall_at_10": counts["top10_hit"] / len(rows) if rows else 0,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
