"""Judge 协议:LLM-as-judge 抽象。

约定:判官 temperature=0,关键指标多次采样取均值(n_samples 记入结果)。
实现(judge/eval_llm)接 eval 自带 llm 模块,本模块只定契约,不引入任何判官依赖。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class JudgeResult:
    score: float
    reasoning: str
    n_samples: int


@runtime_checkable
class Judge(Protocol):
    model_name: str

    async def score(
        self,
        criterion: str,
        *,
        query: str,
        answer: str,
        contexts: list[str],
        golden_answer: str | None = None,
    ) -> JudgeResult: ...
