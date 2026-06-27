"""JSON 报告：机器可读结构化结果（tidy 台账行），供基线加载与趋势看板消费。

字段对齐 trend_dashboard §三 / eval_metric_result：每行含
run_id/ts/git_sha/dataset/layer/metric/k/relevance_scale/type_bucket/value/n
+ 全部 config 维度。
"""

from __future__ import annotations

import json
from datetime import datetime

from linkrag_eval.models import EvalResult
from linkrag_eval.reporters.base import diff_metrics
from linkrag_eval.store.ledger import ledger_rows


class JsonReporter:
    def __init__(self, *, dataset: str = "default"):
        self.dataset = dataset

    def render(self, result: EvalResult, baseline: EvalResult | None = None) -> str:
        ts = datetime.now().isoformat(timespec="seconds")
        payload: dict = {
            "run_id": result.run_id,
            "dataset": self.dataset,
            "ts": ts,
            "rows": ledger_rows(result, dataset=self.dataset, ts=ts),
        }
        if baseline is not None:
            diff = diff_metrics(result, baseline)
            payload["baseline_run_id"] = baseline.run_id
            payload["comparable"] = diff.comparable
            payload["incomparable_reasons"] = diff.incomparable_reasons
            payload["deltas"] = [
                {
                    "metric": d.name,
                    "k": d.k,
                    "value": d.value,
                    "baseline_value": d.baseline_value,
                    "delta": d.delta,
                    "n": d.n,
                    "is_regression": d.is_regression,
                }
                for d in diff.deltas
            ]
        return json.dumps(payload, ensure_ascii=False, indent=2)
