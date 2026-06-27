"""Metric 协议:指标计算。

compute 统一为 async:生成层须 await judge,而一个 Protocol 不能既同步又
异步;检索/重排层声明 async 但内部是纯函数(不读 judge、不碰 IO)。
requires_judge / requires_golden_answer 仅用于 runner 校验前置
(判官就绪、黄金集带答案),不用于分派同步/异步。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from linkrag_eval.contracts.dataset import Sample
from linkrag_eval.contracts.judge import Judge
from linkrag_eval.models import Layer, MetricValue, StageOutput


@runtime_checkable
class Metric(Protocol):
    name: str
    layer: Layer
    requires_judge: bool            # 生成层为 True
    requires_golden_answer: bool    # CORRECTNESS 层为 True

    async def compute(
        self, sample: Sample, output: StageOutput, *, judge: Judge | None = None
    ) -> list[MetricValue]: ...
