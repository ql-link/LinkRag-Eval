"""评测编排执行层:dataset × evaluable × metrics → EvalResult。"""

from linkrag_eval.runners.context import RunContext
from linkrag_eval.runners.gen_runner import GenRunReport, run_golden_gen
from linkrag_eval.runners.stage_runner import aggregate, run_stage

__all__ = [
    "GenRunReport",
    "RunContext",
    "aggregate",
    "run_golden_gen",
    "run_stage",
]
