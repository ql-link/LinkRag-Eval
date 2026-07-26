"""Track B · LLM 合成语料:真实格式文档 + 埋点回定位,覆盖 parser+chunker 全链路。

流程:spec → facts → compose → render → ingest → locate → qa → gate → jsonl。
ground truth 由构造决定(fact 锚点 + 归一化回定位),零人工;换分块策略后
relocate 用锚点自动重建 expected_chunk_ids(B11 闭环)。

``ingest_and_locate``(渲染→解析→分块→灌库→回定位)走注入的 eval indexer/computer/parser。
"""

from linkrag_eval.golden.synth.ingest import SynthDocResult, ingest_and_locate

from linkrag_eval.golden.synth.compose import (
    ComposeResult,
    DocumentComposer,
    check_anchors,
)
from linkrag_eval.golden.synth.facts import (
    FactPlanner,
    FactUnit,
    deterministic_facts,
    load_facts,
    save_facts,
    validate_facts,
)
from linkrag_eval.golden.synth.locate import (
    LocateReport,
    LocateResult,
    locate_facts,
    match_anchor,
    normalize,
)
from linkrag_eval.golden.synth.qa import QAGenerator, QAStats, anchor_leaked
from linkrag_eval.golden.synth.relocate import RelocateReport, relocate_samples
from linkrag_eval.golden.synth.render import render
from linkrag_eval.golden.synth.spec import DocSpec, SpecMatrix, default_matrix

__all__ = [
    "ComposeResult",
    "DocSpec",
    "DocumentComposer",
    "FactPlanner",
    "FactUnit",
    "LocateReport",
    "LocateResult",
    "QAGenerator",
    "QAStats",
    "RelocateReport",
    "SpecMatrix",
    "SynthDocResult",
    "anchor_leaked",
    "check_anchors",
    "default_matrix",
    "deterministic_facts",
    "ingest_and_locate",
    "load_facts",
    "locate_facts",
    "match_anchor",
    "normalize",
    "relocate_samples",
    "render",
    "save_facts",
    "validate_facts",
]
