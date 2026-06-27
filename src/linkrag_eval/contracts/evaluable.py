"""Evaluable 协议:被评测环节的统一调用面。

run 拿一个样本(重排/生成层还需上游 StageOutput,如重排吃召回结果),
调用对应生产模块并归一化成 StageOutput。所有对 rag 的调用都收敛在
Evaluable 的实现(retrieval/adapters)里——这是框架对生产代码的接缝。
async 因生产入口(RecallPipeline.execute 等)均为协程。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from linkrag_eval.contracts.dataset import Sample
from linkrag_eval.models import Layer, StageOutput


@runtime_checkable
class Evaluable(Protocol):
    layer: Layer

    async def run(
        self, sample: Sample, *, upstream: StageOutput | None = None
    ) -> StageOutput: ...
