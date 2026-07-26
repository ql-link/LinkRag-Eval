"""黄金集:schema(GoldenSample)+ 加载/前置自检(load_golden / precheck)。"""

from linkrag_eval.golden.loader import PrecheckReport, load_golden, precheck
from linkrag_eval.golden.schema import GoldenSample

__all__ = ["GoldenSample", "PrecheckReport", "load_golden", "precheck"]
