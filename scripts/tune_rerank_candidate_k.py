#!/usr/bin/env python3
"""在 tune 或 blind golden 上评测融合截断后的 rerank 候选 K。

调参时只传 tune golden；固定 K 后才允许以 ``--mode blind`` 跑一次 blind。该脚本每个 K
都独立请求 rerank，不会把三路原始候选直接送模型，也不假定不同候选集的分数可复用。
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from linkrag_eval.config import get_settings
from linkrag_eval.golden.loader import load_golden, require_chunk_references
from linkrag_eval.llm.rerank_client import build_rerank_client
from linkrag_eval.retrieval.rerank_tuning import evaluate_rerank_candidate_ks, results_payload
from linkrag_eval.retrieval.tuning import (
    TuneConfig,
    cache_route_hits,
    evaluate_config,
    parse_number_list,
)
from linkrag_eval.store.corpus_repo import EvalCorpusRepo


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", required=True)
    parser.add_argument("--mode", choices=("tune", "blind"), required=True)
    parser.add_argument("--out", required=True, help="结果 JSON 输出路径")
    parser.add_argument("--candidate-top-ks", default="20,40,60,80")
    parser.add_argument("--dense-top-k", type=int, default=150)
    parser.add_argument("--sparse-top-k", type=int, default=50)
    parser.add_argument("--bm25-top-k", type=int, default=100)
    parser.add_argument("--dense-threshold", type=float, default=0.30)
    parser.add_argument("--sparse-threshold", type=float, default=0.20)
    parser.add_argument("--bm25-threshold", type=float, default=0.0)
    parser.add_argument("--dense-weight", type=float, default=0.70)
    parser.add_argument("--sparse-weight", type=float, default=0.15)
    parser.add_argument("--bm25-weight", type=float, default=0.15)
    parser.add_argument("--retrieval-concurrency", type=int, default=6,
                        help="三路候选缓存并发")
    parser.add_argument("--rerank-concurrency", type=int, default=3,
                        help="正文回填和 rerank 并发；MySQL 较保守")
    parser.add_argument("--route-retry-rounds", type=int, default=3,
                        help="只对召回失败 Query 重新获取三路候选的轮数")
    return parser.parse_args()


async def main_async(args: argparse.Namespace) -> int:
    settings = get_settings()
    reranker = build_rerank_client(settings)
    samples = load_golden(args.golden)
    require_chunk_references(samples)
    candidate_ks = parse_number_list(args.candidate_top_ks, cast=int)
    max_k = max(candidate_ks)
    print(f"mode={args.mode} samples={len(samples)} rerank_candidate_ks={candidate_ks}")
    print("缓存三路候选；随后仅按融合顺序截断的 TopK 送 rerank。")
    cached = await cache_route_hits(
        samples,
        settings=settings,
        max_dense_top_k=args.dense_top_k,
        max_sparse_top_k=args.sparse_top_k,
        max_bm25_top_k=args.bm25_top_k,
        concurrency=args.retrieval_concurrency,
        progress=print,
    )
    by_id = {item.sample.id: item for item in cached}
    for retry_round in range(1, max(0, args.route_retry_rounds) + 1):
        failed = [item.sample for item in by_id.values() if item.failed_sources]
        if not failed:
            break
        print(f"route retry round={retry_round} samples={len(failed)}")
        retried = await cache_route_hits(
            failed,
            settings=settings,
            max_dense_top_k=args.dense_top_k,
            max_sparse_top_k=args.sparse_top_k,
            max_bm25_top_k=args.bm25_top_k,
            concurrency=max(1, min(args.retrieval_concurrency, 2)),
            progress=print,
        )
        by_id.update({item.sample.id: item for item in retried})
    cached = [by_id[sample.id] for sample in samples]
    failed_routes = [item for item in cached if item.failed_sources]
    if failed_routes:
        details = ", ".join(
            f"{item.sample.id}:{'/'.join(item.failed_sources)}" for item in failed_routes[:10]
        )
        print(f"NON_CLEAN: {len(failed_routes)}/{len(samples)} Query 仍有召回分路失败：{details}")
        await reranker.aclose()
        return 2
    fusion = TuneConfig(
        dense_top_k=args.dense_top_k,
        sparse_top_k=args.sparse_top_k,
        bm25_top_k=args.bm25_top_k,
        dense_threshold=args.dense_threshold,
        sparse_threshold=args.sparse_threshold,
        bm25_threshold=args.bm25_threshold,
        final_top_k=max_k,
        rrf_k=60,
    )
    weights = {"dense": args.dense_weight, "sparse": args.sparse_weight, "bm25": args.bm25_weight}
    baseline = evaluate_config(
        cached,
        TuneConfig(
            dense_top_k=args.dense_top_k,
            sparse_top_k=args.sparse_top_k,
            bm25_top_k=args.bm25_top_k,
            dense_threshold=args.dense_threshold,
            sparse_threshold=args.sparse_threshold,
            bm25_threshold=args.bm25_threshold,
            final_top_k=10,
            rrf_k=60,
        ),
        fusion_strategy="weighted_score",
        fusion_weights=weights,
    )
    repo = EvalCorpusRepo()
    try:
        results = await evaluate_rerank_candidate_ks(
            cached,
            fusion_config=fusion,
            fusion_strategy="weighted_score",
            fusion_weights=weights,
            candidate_top_ks=candidate_ks,
            content_fetcher=repo.fetch_contents_by_ids,
            reranker=reranker,
            concurrency=args.rerank_concurrency,
            progress=print,
        )
    finally:
        await reranker.aclose()
    payload = results_payload(
        results,
        args={
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mode": args.mode,
            "golden": args.golden,
            "model": reranker.model_name,
            "candidate_top_ks": candidate_ks,
            "fusion": asdict(fusion),
            "fusion_strategy": "weighted_score",
            "fusion_weights": weights,
            "route_retry_rounds": args.route_retry_rounds,
        },
    )
    payload["baseline_same_candidates"] = asdict(baseline)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["best"], ensure_ascii=False, indent=2))
    print(f"结果: {path}")
    failed = int((payload["best"] or {}).get("failed_samples", 0))
    if failed:
        print(f"NON_CLEAN: {failed}/{len(samples)} 条 query 的正文回填或 rerank 调用失败；禁止用此结果选 K 或跑 blind。")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async(parse_args())))
