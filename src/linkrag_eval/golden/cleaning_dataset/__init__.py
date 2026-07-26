"""数据清洗评测数据集准备(阶段一):标准 md → 渲染件 + 对应关系表。"""

from linkrag_eval.golden.cleaning_dataset.prepare import normalize_reference_md
from linkrag_eval.golden.cleaning_dataset.registry import (
    CleaningDoc,
    CleaningRegistry,
    RenderedDoc,
)
from linkrag_eval.golden.cleaning_dataset.render import build_corpus

__all__ = [
    "CleaningDoc",
    "CleaningRegistry",
    "RenderedDoc",
    "build_corpus",
    "normalize_reference_md",
]
