"""评测编排执行层:dataset × evaluable × metrics → EvalResult。"""

from linkrag_eval.runners.context import RunContext
from linkrag_eval.runners.stage_runner import aggregate, run_stage

__all__ = ["RunContext", "aggregate", "run_stage"]
