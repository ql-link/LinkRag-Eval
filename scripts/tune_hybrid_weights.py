#!/usr/bin/env python3
"""Grid-search three-route weighted-score fusion on a tune-only golden set."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from linkrag_eval.config import get_settings
from linkrag_eval.golden.loader import load_golden
from linkrag_eval.retrieval.tuning import cache_route_hits, iter_configs, run_grid


def _numbers(raw: str, cast):
    return [cast(part.strip()) for part in raw.split(",") if part.strip()]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()
    samples = load_golden(args.golden)
    cached = await cache_route_hits(
        samples, settings=get_settings(), max_dense_top_k=150,
        max_sparse_top_k=100, max_bm25_top_k=100, concurrency=args.concurrency,
    )
    configs = list(iter_configs(
        dense_top_ks=(100, 150), sparse_top_ks=(50, 75, 100), bm25_top_ks=(20, 50, 100),
        dense_thresholds=(0.2, 0.3), sparse_thresholds=(0.1, 0.2),
        bm25_thresholds=(0.0, 0.1), final_top_k=10, rrf_k=60,
    ))
    rows = []
    # Keep dense dominant, while explicitly testing whether BM25 adds useful exact-match signal.
    for dense_weight, sparse_weight, bm25_weight in (
        (0.90, 0.10, 0.00), (0.85, 0.10, 0.05), (0.80, 0.10, 0.10),
        (0.75, 0.15, 0.10), (0.75, 0.10, 0.15), (0.70, 0.15, 0.15),
    ):
        for result in run_grid(
            cached, configs, fusion_strategy="weighted_score",
            fusion_weights={"dense": dense_weight, "sparse": sparse_weight, "bm25": bm25_weight},
        ):
            row = asdict(result)
            row["dense_weight"] = dense_weight
            row["sparse_weight"] = sparse_weight
            row["bm25_weight"] = bm25_weight
            rows.append(row)
    rows.sort(key=lambda row: (
        row["recall_at_10"], row["hit_rate_at_10"], row["mrr"], row["map"],
        -row["bm25_top_k"], -row["sparse_top_k"],
    ), reverse=True)
    payload = {
        "golden": args.golden,
        "n_samples": len(samples),
        "failed_source_samples": sum(bool(item.failed_sources) for item in cached),
        "configs": len(rows),
        "best": rows[0] if rows else None,
        "top20": rows[:20],
    }
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["best"], ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
