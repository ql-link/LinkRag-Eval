"""文档规格矩阵：格式 × PDF后端 × 结构 × 长度 × 事实分布。

矩阵驱动让"哪种格式/结构下召回掉点"可归因到具体条件。覆盖项对准项目
实际 parser：docx（WordParser）、pdf（mineru/opendataloader/naive 三后端）、
html（HtmlParser）、markdown（入库源即 md）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

FORMATS = ["md", "html", "docx", "pdf"]
PDF_BACKENDS = ["mineru", "opendataloader", "naive"]
STRUCTURES = ["headings", "table_heavy", "list_heavy", "long_paragraph", "code_block"]
LENGTHS = ["short", "medium", "long"]          # 短=单 chunk / 中 / 长=跨多 chunk
FACT_DISTRIBUTIONS = ["concentrated", "scattered", "cross_section"]

# 长度 → 目标事实单元数与编织篇幅提示
LENGTH_PROFILE = {
    "short": {"n_facts": 3, "words": "300字左右"},
    "medium": {"n_facts": 6, "words": "1200字左右"},
    "long": {"n_facts": 10, "words": "3000字以上"},
}


@dataclass(frozen=True)
class DocSpec:
    fmt: str                          # md / html / docx / pdf
    structure: str
    length: str
    fact_distribution: str
    pdf_backend: str | None = None    # 仅 fmt=pdf 有意义
    n_docs: int = 1

    @property
    def key(self) -> str:
        backend = f"x{self.pdf_backend}" if self.pdf_backend else ""
        return f"{self.fmt}{backend}-{self.structure}-{self.length}-{self.fact_distribution}"

    @property
    def n_facts(self) -> int:
        return LENGTH_PROFILE[self.length]["n_facts"]


@dataclass
class SpecMatrix:
    specs: list[DocSpec] = field(default_factory=list)

    def __iter__(self) -> Iterator[DocSpec]:
        return iter(self.specs)

    def __len__(self) -> int:
        return len(self.specs)


def default_matrix(*, docs_per_cell: int = 1) -> SpecMatrix:
    """默认覆盖矩阵：分层覆盖而非全笛卡尔积（宁可窄而全，不要宽而稀）。

    - 每种格式至少覆盖：多级标题×中、表格密集×中；
    - pdf 三后端各跑一份（headings×medium）；
    - 长文/跨段事实仅 md 与 pdf×mineru（压测分块边界与 cross-chunk 问题）。
    """
    specs: list[DocSpec] = []
    for fmt in FORMATS:
        backends = PDF_BACKENDS if fmt == "pdf" else [None]
        for backend in backends:
            specs.append(
                DocSpec(fmt, "headings", "medium", "scattered", backend, docs_per_cell)
            )
        first_backend = PDF_BACKENDS[0] if fmt == "pdf" else None
        specs.append(
            DocSpec(fmt, "table_heavy", "medium", "concentrated", first_backend, docs_per_cell)
        )
    for fmt, backend in [("md", None), ("pdf", "mineru")]:
        specs.append(
            DocSpec(fmt, "long_paragraph", "long", "cross_section", backend, docs_per_cell)
        )
    specs.append(DocSpec("md", "code_block", "medium", "scattered", None, docs_per_cell))
    specs.append(DocSpec("html", "list_heavy", "short", "concentrated", None, docs_per_cell))
    return SpecMatrix(specs)
