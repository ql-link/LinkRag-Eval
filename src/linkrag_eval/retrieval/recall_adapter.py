"""召回适配器:复用生产 RecallPipeline,把 RecallResponse 归一化为 StageOutput。

搬迁自源仓库 ``adapters/recall_adapter.py``。RecallRequest/RecallResponse 是 rag(被测对象)
类型,故本文件是允许 import rag 的 adapter 之一;rag import 惰性、收在本文件。

装配(指向 eval 前缀)见 ``recall_factory.build_eval_recall_pipeline``。``_to_stage_output``
为纯 marshalling,可注入 fake response 单测。
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from linkrag_eval.contracts.dataset import Sample
from linkrag_eval.models import Layer, RankedHit, StageOutput

if TYPE_CHECKING:
    from src.core.pipeline.recall.models import RecallResponse
    from src.core.pipeline.recall.pipeline import RecallPipeline


class RecallEvaluable:
    layer = Layer.RETRIEVAL

    def __init__(self, pipeline: "RecallPipeline", top_k: int, *, retries: int = 5):
        self.pipeline = pipeline
        self.top_k = top_k
        # per-query 重试:远端 Qdrant/embedding 网关偶发 502,某条 query 两路同时挂会抛
        # RecallError;召回只读、幂等,退避重试即可,避免一条抖动毁掉整轮评测。
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
        )
        started = time.monotonic()
        for attempt in range(1, self.retries + 1):
            try:
                resp = await self.pipeline.execute(req)
                break
            except Exception:
                if attempt == self.retries:
                    raise
                await asyncio.sleep(2 * attempt)
        wall_ms = int((time.monotonic() - started) * 1000)
        return self._to_stage_output(sample.query, resp, wall_ms)

    def _to_stage_output(
        self, query: str, resp: "RecallResponse", wall_ms: int
    ) -> StageOutput:
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
