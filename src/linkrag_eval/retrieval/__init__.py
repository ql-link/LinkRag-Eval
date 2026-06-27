"""召回装配:复用生产 RecallPipeline 测真链路,指向 eval 前缀 + 注入 eval 编码器。"""

from linkrag_eval.retrieval.recall_adapter import RecallEvaluable
from linkrag_eval.retrieval.recall_factory import (
    build_eval_recall_evaluable,
    build_eval_recall_pipeline,
)

__all__ = ["RecallEvaluable", "build_eval_recall_evaluable", "build_eval_recall_pipeline"]
