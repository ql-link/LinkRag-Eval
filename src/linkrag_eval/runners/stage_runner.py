"""单环节驱动:dataset × evaluable × metrics → EvalResult。

precheck 已在入口完成(失效则不进此处)。聚合按 (name, k) 求 mean,
并按 sample.type 分桶(每桶标样本量,小样本桶只作定性参考)。检索层 reference
粒度(chunk/doc)必须分开聚合,避免把严格 chunk 指标与宽松 doc 指标混成一个 headline。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable

from linkrag_eval.contracts.evaluable import Evaluable
from linkrag_eval.contracts.judge import Judge
from linkrag_eval.contracts.metric import Metric
from linkrag_eval.golden.schema import GoldenSample
from linkrag_eval.models import (
    EvalResult,
    MetricResult,
    MetricValue,
    QuestionType,
)
from linkrag_eval.runners.context import RunContext


def _metric_group_name(value: MetricValue) -> str:
    """聚合指标名:检索 reference 粒度单独分名,例如 recall_chunk / recall_doc。"""
    granularity = value.detail.get("granularity")
    if value.layer.value == "retrieval" and granularity in {"chunk", "doc"}:
        return f"{value.name}_{granularity}"
    return value.name


def aggregate(
    per_sample_values: list[tuple[GoldenSample, list[MetricValue]]],
    *,
    domain_of: "Callable[[GoldenSample], str | None] | None" = None,
) -> list[MetricResult]:
    """跨样本聚合:按 (name, layer, k) 求 mean + 按 QuestionType 分桶。

    ``domain_of`` 给定时(sample → 语料垂域,取自 ``eval_dataset.domain`` 编目),
    额外按 domain 分桶填 ``by_domain``;返回 None 的样本归入 ``"未编目"`` 桶。
    """
    groups: dict[tuple, list[tuple[QuestionType, str | None, float]]] = defaultdict(list)
    for sample, values in per_sample_values:
        domain = (domain_of(sample) or "未编目") if domain_of else None
        for v in values:
            groups[(_metric_group_name(v), v.layer, v.k)].append(
                (sample.type, domain, v.value)
            )

    results: list[MetricResult] = []
    for (name, layer, k), entries in sorted(
        groups.items(), key=lambda kv: (kv[0][0], kv[0][2] if kv[0][2] is not None else -1)
    ):
        all_values = [val for _, _, val in entries]
        by_type_values: dict[QuestionType, list[float]] = defaultdict(list)
        by_domain_values: dict[str, list[float]] = defaultdict(list)
        for qtype, domain, val in entries:
            by_type_values[qtype].append(val)
            if domain is not None:  # domain_of 未给时不分桶
                by_domain_values[domain].append(val)
        results.append(
            MetricResult(
                name=name,
                layer=layer,
                k=k,
                mean=sum(all_values) / len(all_values),
                n=len(all_values),
                by_type={t: sum(vs) / len(vs) for t, vs in by_type_values.items()},
                by_type_n={t: len(vs) for t, vs in by_type_values.items()},
                by_domain={d: sum(vs) / len(vs) for d, vs in by_domain_values.items()},
                by_domain_n={d: len(vs) for d, vs in by_domain_values.items()},
            )
        )
    return results


async def run_stage(
    dataset: list[GoldenSample],
    evaluable: Evaluable,
    metrics: list[Metric],
    ctx: RunContext,
    *,
    judge: Judge | None = None,
    domain_of: Callable[[GoldenSample], str | None] | None = None,
) -> EvalResult:
    # 前置校验:指标声明的依赖须就绪(requires_judge / requires_golden_answer)
    for m in metrics:
        if m.requires_judge and judge is None:
            raise ValueError(f"指标 {m.name} 需要 judge,但未提供")
    if any(m.requires_golden_answer for m in metrics):
        lacking = [s.id for s in dataset if not s.golden_answer]
        if lacking:
            raise ValueError(
                f"指标需要 golden_answer,但 {len(lacking)} 条样本缺失(如 {lacking[:5]})"
            )

    per_sample_values: list[tuple[GoldenSample, list[MetricValue]]] = []
    per_sample_diag: list[dict] = []
    for sample in dataset:
        output = await evaluable.run(sample)
        values: list[MetricValue] = []
        for metric in metrics:
            values.extend(await metric.compute(sample, output, judge=judge))
        per_sample_values.append((sample, values))
        per_sample_diag.append(
            {
                "sample_id": sample.id,
                "type": sample.type.value,
                "elapsed_ms": output.elapsed_ms,
                "per_source_counts": output.per_source_counts,
                "failed_sources": output.failed_sources,
                "rerank_applied": output.rerank_applied,
                "n_ranked": len(output.ranked),
                "values": [
                    {
                        "name": _metric_group_name(v),
                        "raw_name": v.name,
                        "k": v.k,
                        "value": v.value,
                        "detail": dict(v.detail),
                    }
                    for v in values
                ],
            }
        )

    return EvalResult(
        run_id=ctx.run_id,
        snapshot=ctx.snapshot,
        metrics=aggregate(per_sample_values, domain_of=domain_of),
        per_sample=per_sample_diag,
    )
