"""数据清洗适配器(CLEANING 层):照对应关系表取已渲染件 → parser 清洗回 md。

搬迁自源仓库 ``adapters/cleaning_adapter.py``。唯一对 rag 的接缝是
``ParserFactory.get_parser(fmt)``(PDF 再叠 backend)→ ``IFileParser.parse(Path) -> str``,
那正是 CLEANING 层的**被测对象**,故本文件是允许 import rag 的 adapter 之一;rag import
惰性、收在 ``run`` 内。本适配器只测量"清洗(解析)"这一步并归一化成
``StageOutput.raw=CleaningPair``,指标 ``metrics/cleaning.py`` 纯函数比对,不进活栈。

输入不是黄金集 Sample 而是"渲染件引用"(阶段一产物):阶段一已把标准 md 渲染成各格式,
阶段二照引用读。首版用文件后端(本地路径);接对象存储后 object_key→下载临时文件即可,
比对逻辑不变。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from linkrag_eval.models import CleaningPair, Layer, StageOutput


@dataclass(frozen=True)
class RenderedRef:
    """阶段一产出的一个渲染件引用(对应一条渲染记录 + 其 doc 的 md_ref)。

    首版文件后端:rendered_path/md_ref_path 为本地路径;切对象存储后换成下载到临时目录的
    路径即可,其余不变。
    """

    sample_id: str
    fmt: str                       # pdf / docx / html / md
    rendered_path: str             # 渲染件本地路径(或下载后的临时路径)
    md_ref_path: str               # 参考标准 md 路径
    pdf_backend: str | None = None  # 仅 PDF


class CleaningEvaluable:
    """layer=CLEANING。一次 run = 取一个渲染件清洗回 md,计清洗时间。

    stability_runs>1 时对**非确定后端**(mineru/VLM)重复清洗,供
    ``metrics.stability`` 统计多次一致率;确定性后端设 1 即可。
    """

    layer = Layer.CLEANING

    def __init__(self, *, stability_runs: int = 1):
        self.stability_runs = max(1, stability_runs)

    async def run(self, rendered: RenderedRef, *, upstream: StageOutput | None = None) -> StageOutput:
        from src.core.parser import ParserFactory

        md_ref = Path(rendered.md_ref_path).read_text(encoding="utf-8")
        source = Path(rendered.rendered_path)
        kwargs = {"backend": rendered.pdf_backend} if rendered.fmt == "pdf" and rendered.pdf_backend else {}

        produced = ""
        repeats: list[str] = []
        ok = True
        t0 = perf_counter()
        try:
            parser = ParserFactory.get_parser(rendered.fmt, **kwargs)
            produced = parser.parse(source)
            for _ in range(self.stability_runs - 1):
                repeats.append(ParserFactory.get_parser(rendered.fmt, **kwargs).parse(source))
        except Exception:  # 清洗异常 → ok=False,桶内仍计入(不静默丢样本)
            ok = False
        elapsed_ms = int((perf_counter() - t0) * 1000)

        return StageOutput(
            layer=self.layer,
            query=rendered.sample_id,
            ranked=[],
            elapsed_ms=elapsed_ms,
            rerank_applied=None,
            raw=CleaningPair(ref=md_ref, produced=produced, ok=ok, repeats=tuple(repeats)),
        )
