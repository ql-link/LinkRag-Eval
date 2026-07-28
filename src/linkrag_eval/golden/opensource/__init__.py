"""Track A · 开源数据集(主力来源):文档灌评测租户 + 标注转 GoldenSample(doc 粒度)。

选型(授权已核):DuReader_retrieval(检索,Apache-2.0,二值)、T2Ranking(重排辅证,
Apache-2.0,4 级分级)。两套口径与自有语料分开汇报。

灌库 ``ingest_passages`` 走 eval ``EvalVectorIndexer``(段落=一个 chunk,doc 粒度)。
"""

from linkrag_eval.golden.opensource.convert import (
    ConvertReport,
    convert_to_golden,
    write_golden_jsonl,
)
from linkrag_eval.golden.opensource.datasets import (
    PassageCorpus,
    QueryJudgment,
    load_dureader_retrieval,
    load_t2ranking,
)
from linkrag_eval.golden.opensource.ingest import ingest_passages

__all__ = [
    "ConvertReport",
    "PassageCorpus",
    "QueryJudgment",
    "convert_to_golden",
    "ingest_passages",
    "load_dureader_retrieval",
    "load_t2ranking",
    "write_golden_jsonl",
]
