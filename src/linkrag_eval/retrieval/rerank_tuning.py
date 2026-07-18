"""融合候选截断后的 rerank 与候选 K 调优。

召回层先按既定 weighted-score/RRF 产出一个有序候选池；本模块只把该顺序的前 ``K``
条正文送入 rerank。K 是 rerank 输入预算，不是最终输出 Top10。所有分数基于 chunk
粒度 golden，调参集与 blind 集由调用方严格分开。
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Any, Sequence

from linkrag_eval.llm.rerank_client import RerankScore
from linkrag_eval.models import Layer, RankedHit, StageOutput
from linkrag_eval.retrieval.tuning import (
    CachedSample,
    TuneConfig,
    _metric_values,
    stage_output_for_config,
)


@dataclass(frozen=True)
class RerankTuneResult:
    candidate_top_k: int
    final_top_k: int
    recall_at_10: float
    hit_rate_at_10: float
    map: float
    mrr: float
    n: int
    missing_content_candidates: int
    failed_samples: int

    @property
    def score_key(self) -> tuple[float, float, float, float, int]:
        # 同等效果优先更小 K，降低模型延迟与成本。
        return (self.recall_at_10, self.hit_rate_at_10, self.mrr, self.map, -self.candidate_top_k)


def rerank_fused_candidates(
    fused: StageOutput,
    *,
    contents: dict[str, str],
    scores: Sequence[RerankScore],
    final_top_k: int,
) -> tuple[StageOutput, int]:
    """将 rerank 返回分数映射回融合候选，并保持 chunk/doc 元数据。"""
    eligible = [hit for hit in fused.ranked if contents.get(hit.chunk_id)]
    missing = len(fused.ranked) - len(eligible)
    if len(scores) != len(eligible):
        raise ValueError(f"rerank score 数量不符:got {len(scores)}, expected {len(eligible)}")
    score_by_index = {item.index: item.score for item in scores}
    if set(score_by_index) != set(range(len(eligible))):
        raise ValueError("rerank score index 未覆盖全部候选")
    ordered = sorted(
        enumerate(eligible),
        key=lambda pair: (-score_by_index[pair[0]], pair[0]),
    )
    ranked = [
        RankedHit(
            chunk_id=hit.chunk_id,
            doc_id=hit.doc_id,
            dataset_id=hit.dataset_id,
            rank=rank,
            score=score_by_index[index],
            sources=hit.sources,
        )
        for rank, (index, hit) in enumerate(ordered[:final_top_k])
    ]
    return (
        StageOutput(
            layer=Layer.RERANK,
            query=fused.query,
            ranked=ranked,
            comparisons={"fusion": list(fused.ranked)},
            per_source_counts=dict(fused.per_source_counts),
            rerank_applied=True,
        ),
        missing,
    )


async def evaluate_rerank_candidate_ks(
    cached: list[CachedSample],
    *,
    fusion_config: TuneConfig,
    fusion_strategy: str,
    fusion_weights: dict[str, float],
    candidate_top_ks: Sequence[int],
    content_fetcher: Any,
    reranker: Any,
    concurrency: int = 4,
    progress: Any | None = None,
) -> list[RerankTuneResult]:
    """对每个候选 K 作**独立模型调用**并计算指标，不假设不同 K 的模型分数可互用。"""
    ks = sorted(set(int(k) for k in candidate_top_ks))
    if not ks or any(k <= 0 for k in ks):
        raise ValueError("candidate_top_ks 必须为正整数")
    max_k = max(ks)
    if fusion_config.final_top_k < max_k:
        raise ValueError("fusion_config.final_top_k 必须不小于最大 candidate_top_k")
    sem = asyncio.Semaphore(max(1, concurrency))
    accum: dict[int, dict[str, float]] = {
        k: {"recall": 0.0, "hit_rate": 0.0, "map": 0.0, "mrr": 0.0, "missing": 0.0, "failed": 0.0}
        for k in ks
    }
    done = 0

    async def fetch_contents(chunk_ids: list[str]) -> dict[str, str]:
        """MySQL 短暂断连只重试当前 query 的正文回填，不让全轮 rerank 中止。"""
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                return await content_fetcher(chunk_ids)
            except Exception as exc:  # remote eval DB intermittent failure
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(0.5 * (attempt + 1))
        assert last_error is not None
        raise last_error

    async def one(item: CachedSample) -> dict[int, tuple[dict[str, float], int, bool]]:
        fused = stage_output_for_config(
            item,
            fusion_config,
            fusion_strategy=fusion_strategy,
            fusion_weights=fusion_weights,
        )
        try:
            all_contents = await fetch_contents([hit.chunk_id for hit in fused.ranked])
        except Exception:
            # 当前 query 的所有 K 都无法得到正文，记为非 clean，但保留其它 query 的结果。
            return {
                candidate_k: ({"recall": 0.0, "hit_rate": 0.0, "map": 0.0, "mrr": 0.0}, 0, True)
                for candidate_k in ks
            }
        result: dict[int, tuple[dict[str, float], int, bool]] = {}
        for candidate_k in ks:
            candidates = fused.ranked[:candidate_k]
            candidate_fused = StageOutput(
                layer=Layer.RETRIEVAL,
                query=fused.query,
                ranked=candidates,
                per_source_counts=fused.per_source_counts,
            )
            eligible = [hit for hit in candidates if all_contents.get(hit.chunk_id)]
            missing = len(candidates) - len(eligible)
            if not eligible:
                result[candidate_k] = ({"recall": 0.0, "hit_rate": 0.0, "map": 0.0, "mrr": 0.0}, missing, True)
                continue
            try:
                scores = await reranker.rerank(
                    item.sample.query, [all_contents[hit.chunk_id] for hit in eligible]
                )
                reranked, _ = rerank_fused_candidates(
                    candidate_fused,
                    contents=all_contents,
                    scores=scores,
                    final_top_k=10,
                )
                result[candidate_k] = (_metric_values(item.sample, reranked, k=10), missing, False)
            except Exception:
                result[candidate_k] = ({"recall": 0.0, "hit_rate": 0.0, "map": 0.0, "mrr": 0.0}, missing, True)
        return result

    async def guarded(item: CachedSample) -> None:
        nonlocal done
        async with sem:
            values = await one(item)
        for candidate_k, (metrics, missing, failed) in values.items():
            for name, value in metrics.items():
                accum[candidate_k][name] += value
            accum[candidate_k]["missing"] += missing
            accum[candidate_k]["failed"] += int(failed)
        done += 1
        if progress and (done % 10 == 0 or done == len(cached)):
            progress(f"rerank evaluated {done}/{len(cached)}")

    await asyncio.gather(*(guarded(item) for item in cached))
    n = len(cached)
    results = [
        RerankTuneResult(
            candidate_top_k=k,
            final_top_k=10,
            recall_at_10=values["recall"] / n if n else 0.0,
            hit_rate_at_10=values["hit_rate"] / n if n else 0.0,
            map=values["map"] / n if n else 0.0,
            mrr=values["mrr"] / n if n else 0.0,
            n=n,
            missing_content_candidates=int(values["missing"]),
            failed_samples=int(values["failed"]),
        )
        for k, values in accum.items()
    ]
    return sorted(results, key=lambda item: item.score_key, reverse=True)


def results_payload(results: Sequence[RerankTuneResult], *, args: dict[str, Any]) -> dict[str, Any]:
    """输出稳定 JSON，供报告渲染与 blind 固化读取。"""
    return {"args": args, "best": asdict(results[0]) if results else None, "results": [asdict(item) for item in results]}
