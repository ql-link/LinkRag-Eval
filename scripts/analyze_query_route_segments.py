#!/usr/bin/env python3
"""按 query 特征分桶，对比单路与三路融合的严格 chunk Recall@10。"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import defaultdict
from pathlib import Path

from linkrag_eval.config import get_settings
from linkrag_eval.golden.loader import load_golden
from linkrag_eval.retrieval.tuning import TuneConfig, cache_route_hits, stage_output_for_config


def buckets(query: str) -> list[str]:
    text = query.strip()
    result = ["all"]
    length = len(text)
    result.append("short_le_15" if length <= 15 else "medium_16_35" if length <= 35 else "long_gt_35")
    if re.search(r"\d|[A-Z]{2,}|v\d", text, flags=re.I):
        result.append("exact_number_or_identifier")
    if any(word in text for word in ("条件", "日期", "时间", "版本", "范围", "多少", "是否", "要求")):
        result.append("constraint_or_fact")
    if length > 20 and not re.search(r"\d", text):
        result.append("natural_language_semantic")
    return result


def hit_at_10(output, expected: set[str]) -> float:
    return float(any(hit.chunk_id in expected for hit in output.ranked[:10]))


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--concurrency", type=int, default=6)
    args = parser.parse_args()
    samples = load_golden(args.golden)
    cached = await cache_route_hits(
        samples, settings=get_settings(), max_dense_top_k=150, max_sparse_top_k=50,
        max_bm25_top_k=100, concurrency=args.concurrency, progress=print,
    )
    configs = {
        "dense_only": (TuneConfig(150, 0, 0.3, 0.0, 10, 60, 0, 0.0), {"dense": 1.0}),
        "sparse_only": (TuneConfig(0, 50, 0.0, 0.2, 10, 60, 0, 0.0), {"sparse": 1.0}),
        "bm25_only": (TuneConfig(0, 0, 0.0, 0.0, 10, 60, 100, 0.0), {"bm25": 1.0}),
        "hybrid_070_015_015": (TuneConfig(150, 50, 0.3, 0.2, 10, 60, 100, 0.0), {"dense": .70, "sparse": .15, "bm25": .15}),
    }
    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    rows = []
    for item in cached:
        expected = set(item.sample.expected_chunk_ids)
        values = {}
        for name, (config, weights) in configs.items():
            values[name] = hit_at_10(stage_output_for_config(item, config, fusion_strategy="weighted_score", fusion_weights=weights), expected)
        for bucket in buckets(item.sample.query):
            totals[bucket]["n"] += 1
            for name, value in values.items():
                totals[bucket][name] += value
        rows.append({"id": item.sample.id, "query": item.sample.query, "buckets": buckets(item.sample.query), "hit_at_10": values, "failed_sources": list(item.failed_sources)})
    summary = {bucket: {key: (value / counts["n"] if key != "n" else int(value)) for key, value in counts.items()} for bucket, counts in sorted(totals.items())}
    Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for bucket, values in summary.items():
        print(bucket, values)


if __name__ == "__main__":
    asyncio.run(main())
