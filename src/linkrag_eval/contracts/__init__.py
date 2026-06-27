"""评估框架抽象端口:全框架唯一的依赖汇聚点。

metrics / adapters / runners 一律只 import contracts 与 models,彼此不直连。
新增环节 = 实现这里的协议,不改动既有模块。

硬约束:本包不依赖任何其他评估模块(models 除外)、不 import src.core。
"""

from linkrag_eval.contracts.dataset import Dataset, Sample
from linkrag_eval.contracts.evaluable import Evaluable
from linkrag_eval.contracts.judge import Judge, JudgeResult
from linkrag_eval.contracts.metric import Metric
from linkrag_eval.contracts.store import AsyncResultStore, ResultStore

__all__ = [
    "AsyncResultStore",
    "Dataset",
    "Evaluable",
    "Judge",
    "JudgeResult",
    "Metric",
    "ResultStore",
    "Sample",
]
