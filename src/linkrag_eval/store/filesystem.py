"""文件后端 ResultStore 完整体:结构化结果/快照/报告落本地目录,支持基线往返。

目录布局::
    <base>/snapshots/<run-id>.json   配置快照
    <base>/results/<run-id>.json     EvalResult(嵌套结构 + tidy 台账行)
    <base>/reports/<run-id>.html     HTML 报告

``save_result`` 把整个 EvalResult 序列化(含 by_type/by_domain 分桶),``load_baseline``
按 run_id 读回同构对象——这是跨 run 回归对比(``diff_metrics``)的前提。``JsonResultStore``
是只写快照/报告的简版;需要基线对比时用本实现。

相对源仓库的改进:metrics 序列化补齐 ``by_domain``/``by_domain_n``,多域评测的分桶在
往返后不丢。``results json`` 内嵌 ``ledger`` 长表行,趋势看板/DB 后端纯下游消费同一份。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from linkrag_eval.models import (
    EvalResult,
    Layer,
    MetricResult,
    QuestionType,
    Snapshot,
)
from linkrag_eval.store.ledger import ledger_rows


def _metric_to_dict(mr: MetricResult) -> dict[str, Any]:
    return {
        "name": mr.name,
        "layer": mr.layer.value,
        "k": mr.k,
        "mean": mr.mean,
        "n": mr.n,
        "by_type": {k.value: v for k, v in mr.by_type.items()},
        "by_type_n": {k.value: v for k, v in mr.by_type_n.items()},
        "by_domain": dict(mr.by_domain),
        "by_domain_n": dict(mr.by_domain_n),
    }


def _metric_from_dict(m: dict[str, Any]) -> MetricResult:
    return MetricResult(
        name=m["name"],
        layer=Layer(m["layer"]),
        k=m["k"],
        mean=m["mean"],
        n=m["n"],
        by_type={QuestionType(k): v for k, v in m.get("by_type", {}).items()},
        by_type_n={QuestionType(k): v for k, v in m.get("by_type_n", {}).items()},
        by_domain=dict(m.get("by_domain", {})),
        by_domain_n=dict(m.get("by_domain_n", {})),
    )


def result_to_dict(result: EvalResult, *, dataset: str, ts: str) -> dict[str, Any]:
    """EvalResult → 可往返 dict(嵌套 metrics + per_sample + tidy ledger 长表)。"""
    return {
        "run_id": result.run_id,
        "dataset": dataset,
        "ts": ts,
        "snapshot": asdict(result.snapshot),
        "metrics": [_metric_to_dict(mr) for mr in result.metrics],
        "per_sample": result.per_sample,
        "ledger": ledger_rows(result, dataset=dataset, ts=ts),
    }


def dict_to_result(data: dict[str, Any]) -> EvalResult:
    """``result_to_dict`` 的逆:读回 EvalResult(ledger 是派生冗余,不参与重建)。"""
    return EvalResult(
        run_id=data["run_id"],
        snapshot=Snapshot(**data["snapshot"]),
        metrics=[_metric_from_dict(m) for m in data["metrics"]],
        per_sample=data.get("per_sample", []),
    )


class FilesystemResultStore:
    """实现 ``contracts.ResultStore``;另提供 ``save_result``(结构化结果落盘 + 基线往返)。"""

    def __init__(self, base_dir: str | Path, *, dataset: str = "default"):
        self.base = Path(base_dir)
        self.dataset = dataset
        for sub in ("snapshots", "results", "reports"):
            (self.base / sub).mkdir(parents=True, exist_ok=True)

    def save_snapshot(self, snapshot: Snapshot) -> None:
        path = self.base / "snapshots" / f"{snapshot.run_id}.json"
        path.write_text(
            json.dumps(asdict(snapshot), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def save_result(self, result: EvalResult, *, ts: str | None = None) -> Path:
        ts = ts or datetime.now().isoformat(timespec="seconds")
        path = self.base / "results" / f"{result.run_id}.json"
        path.write_text(
            json.dumps(
                result_to_dict(result, dataset=self.dataset, ts=ts),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    def save_report(self, run_id: str, content: str) -> None:
        (self.base / "reports" / f"{run_id}.html").write_text(content, encoding="utf-8")

    def load_baseline(self, run_id: str) -> EvalResult | None:
        path = self.base / "results" / f"{run_id}.json"
        if not path.exists():
            return None
        return dict_to_result(json.loads(path.read_text(encoding="utf-8")))
