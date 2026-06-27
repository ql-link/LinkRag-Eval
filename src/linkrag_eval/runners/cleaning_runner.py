"""清洗层运行器:照对应关系表清洗回 md → 纯函数比对 → 分桶报告。

搬迁自源仓库 ``runners/cleaning_runner.py``。与检索 ``run_stage`` 分开:清洗的输入是渲染件
引用(RenderedRef)而非黄金集 Sample,产出是 CleaningQcReport(逐 format×backend 分桶)而非
EvalResult。活栈仅在 ``CleaningEvaluable.run`` 处(其余纯函数)。
"""

from __future__ import annotations

from linkrag_eval.cleaning.adapter import CleaningEvaluable, RenderedRef
from linkrag_eval.metrics import cleaning as M
from linkrag_eval.models import CleaningPair, CleaningQcItem, CleaningQcReport


async def run_cleaning(
    rendered_refs: list[RenderedRef],
    evaluable: CleaningEvaluable,
    *,
    run_id: str,
    snapshot: dict | None = None,
) -> tuple[CleaningQcReport, list[CleaningQcItem]]:
    """对每个渲染件清洗 + 比对,返回 (分桶聚合报告, 单文档明细列表)。

    明细 list 供落 cleaning_detail.jsonl(排查用);报告供入结果库与 HTML 渲染。
    """
    items: list[CleaningQcItem] = []
    for ref in rendered_refs:
        out = await evaluable.run(ref)
        pair: CleaningPair = out.raw
        item = M.score_pair(
            pair,
            sample_id=ref.sample_id,
            fmt=ref.fmt,
            pdf_backend=ref.pdf_backend,
            clean_ms=out.elapsed_ms,
            ok=pair.ok,
            stability_runs=[pair.produced, *pair.repeats] if pair.repeats else None,
        )
        items.append(item)

    report = M.aggregate(items, run_id=run_id, snapshot=snapshot or {})
    return report, items
