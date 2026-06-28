"""报告落盘收口:把 EvalResult / CleaningQcReport 渲染成文件(HTML 人读 + JSON 机读)。

纯 IO + reporter 渲染,零 rag、零活栈,故可直接单测。``run`` 与 ``cleaning`` 两条命令
共用本模块写出报告;JSON 台账行同时充当后续基线/趋势看板的输入。
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from linkrag_eval.models import CleaningQcItem, CleaningQcReport, EvalResult
from linkrag_eval.reporters.cleaning_reporter import CleaningHtmlReporter
from linkrag_eval.reporters.html_reporter import HtmlReporter
from linkrag_eval.reporters.json_reporter import JsonReporter


def write_retrieval_reports(
    result: EvalResult,
    out_dir: str | Path,
    *,
    run_id: str,
    dataset: str = "default",
    baseline: EvalResult | None = None,
) -> dict[str, str]:
    """检索评测 → ``<run_id>.html``(人读)+ ``<run_id>.json``(台账,基线/看板消费)。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    html_path = out / f"{run_id}.html"
    json_path = out / f"{run_id}.json"
    html_path.write_text(
        HtmlReporter(dataset=dataset).render(result, baseline), encoding="utf-8"
    )
    json_path.write_text(
        JsonReporter(dataset=dataset).render(result, baseline), encoding="utf-8"
    )
    return {"html": str(html_path), "json": str(json_path)}


def _detail_row(item: CleaningQcItem) -> dict[str, Any]:
    return dataclasses.asdict(item)


def write_cleaning_reports(
    report: CleaningQcReport,
    items: list[CleaningQcItem],
    out_dir: str | Path,
    *,
    run_id: str,
    dataset: str = "default",
) -> dict[str, str]:
    """清洗质检 → ``<run_id>.cleaning.html``(分桶人读)+ ``<run_id>.cleaning.jsonl``(逐文档明细)。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    html_path = out / f"{run_id}.cleaning.html"
    detail_path = out / f"{run_id}.cleaning.jsonl"
    html_path.write_text(
        CleaningHtmlReporter(dataset=dataset).render(report), encoding="utf-8"
    )
    with open(detail_path, "w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(_detail_row(item), ensure_ascii=False, default=str) + "\n")
    return {"html": str(html_path), "detail": str(detail_path)}
