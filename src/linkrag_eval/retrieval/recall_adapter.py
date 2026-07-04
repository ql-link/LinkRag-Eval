"""召回适配器:复用生产 RecallPipeline,把 RecallResponse 归一化为 StageOutput。

搬迁自源仓库 ``adapters/recall_adapter.py``。RecallRequest/RecallResponse 是 rag(被测对象)
类型,故本文件是允许 import rag 的 adapter 之一;rag import 惰性、收在本文件。

装配(指向 eval 前缀)见 ``recall_factory.build_eval_recall_pipeline``。``_to_stage_output``
为纯 marshalling,可注入 fake response 单测。
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from linkrag_eval.contracts.dataset import Sample
from linkrag_eval.models import Layer, RankedHit, StageOutput

if TYPE_CHECKING:
    from src.core.pipeline.recall.models import RecallResponse
    from src.core.pipeline.recall.pipeline import RecallPipeline


class RecallEvaluable:
    layer = Layer.RETRIEVAL

    def __init__(
        self,
        pipeline: "RecallPipeline",
        top_k: int,
        *,
        bm25_top_k: int | None = None,
        dense_top_k: int | None = None,
        sparse_top_k: int | None = None,
        dense_score_threshold: float | None = None,
        sparse_score_threshold: float | None = None,
        fusion_strategy: str = "rrf",
        fusion_weights: dict[str, float] | None = None,
        retries: int = 5,
    ):
        self.pipeline = pipeline
        self.top_k = top_k
        self.bm25_top_k = bm25_top_k or top_k
        self.dense_top_k = dense_top_k or top_k
        self.sparse_top_k = sparse_top_k or top_k
        self.dense_score_threshold = dense_score_threshold
        self.sparse_score_threshold = sparse_score_threshold
        self.fusion_strategy = fusion_strategy
        self.fusion_weights = dict(fusion_weights or {})
        # per-query 重试:远端 Qdrant/embedding 网关偶发 502,严格模式下会抛 RecallError;
        # 宽松模式下单路失败会进入 failed_sources。召回只读、幂等,退避重试即可,
        # 避免一条抖动污染整轮 clean run。
        self.retries = retries

    async def run(
        self, sample: Sample, *, upstream: StageOutput | None = None
    ) -> StageOutput:
        from src.core.pipeline.recall.models import RecallRequest

        req = RecallRequest(
            query=sample.query,
            user_id=sample.user_id,
            dataset_ids=sample.dataset_ids,
            top_k=self.top_k,
            bm25_top_k=self.bm25_top_k,
            dense_top_k=self.dense_top_k,
            sparse_top_k=self.sparse_top_k,
            dense_score_threshold_override=self.dense_score_threshold,
            sparse_score_threshold_override=self.sparse_score_threshold,
            fusion_strategy_override=self.fusion_strategy,
            fusion_dense_weight_override=self.fusion_weights.get("dense"),
            fusion_sparse_weight_override=self.fusion_weights.get("sparse"),
            fusion_bm25_weight_override=self.fusion_weights.get("bm25"),
        )
        started = time.monotonic()
        resp = None
        for attempt in range(1, self.retries + 1):
            try:
                resp = await self.pipeline.execute(req)
                if not self._needs_retry(resp) or attempt == self.retries:
                    break
            except Exception:
                if attempt == self.retries:
                    raise
            await asyncio.sleep(2 * attempt)
        wall_ms = int((time.monotonic() - started) * 1000)
        assert resp is not None
        return self._to_stage_output(sample.query, resp, wall_ms)

    @staticmethod
    def _needs_retry(resp: "RecallResponse") -> bool:
        """宽松模式下 failed_sources/零结果不抛错,这里把它们视为可重试的不完整响应。"""
        return bool(resp.failed_sources) or not bool(resp.hits)

    def _to_stage_output(self, query: str, resp: "RecallResponse", wall_ms: int) -> StageOutput:
        ordered = sorted(resp.hits, key=lambda h: h.fused_score, reverse=True)
        ranked = [
            RankedHit(
                chunk_id=h.chunk_id,
                doc_id=h.doc_id,
                dataset_id=h.dataset_id,
                rank=i,
                score=h.fused_score,
                # 非 None 的路即命中路 → 归一化来源集合(三路重叠率只读它)
                sources=frozenset(s for s, v in h.scores.items() if v is not None),
            )
            for i, h in enumerate(ordered)
        ]
        return StageOutput(
            layer=self.layer,
            query=query,
            ranked=ranked,
            elapsed_ms=resp.elapsed_ms or wall_ms,
            per_source_counts=dict(resp.per_source_counts),
            failed_sources=list(resp.failed_sources),
            raw=resp,
        )

    def config_snapshot(self) -> dict[str, Any]:
        """返回正式 run 使用的召回参数,供 snapshot/report 记录。"""
        return {
            "top_k": self.top_k,
            "route_top_ks": {
                "bm25": self.bm25_top_k,
                "dense": self.dense_top_k,
                "sparse": self.sparse_top_k,
            },
            "route_score_thresholds": {
                "dense": self.dense_score_threshold,
                "sparse": self.sparse_score_threshold,
            },
            "fusion_strategy": self.fusion_strategy,
            "fusion_weights": dict(self.fusion_weights),
        }
