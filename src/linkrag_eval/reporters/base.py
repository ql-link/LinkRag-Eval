"""Reporter 抽象 + 基线 diff / 回归判据。

回归判据为**初始占位**（可调）：Recall@k 跌>2pp / NDCG 跌>0.02。正式判据须
超噪声地板 σ_metric 且 n≥30（M1 校准，见 trend_dashboard §5.0/§5.2）。
小样本桶只标"样本不足、仅定性"，不触发回归。不作 PR 自动门禁。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from linkrag_eval.models import EvalResult


@runtime_checkable
class Reporter(Protocol):
    def render(self, result: EvalResult, baseline: EvalResult | None = None) -> str: ...


@dataclass(frozen=True)
class RegressionCriteria:
    recall_drop: float = 0.02       # Recall@k 跌幅 > 2pp 判回归
    ndcg_drop: float = 0.02        # NDCG@k 跌幅 > 0.02 判回归
    min_n: int = 30                 # 低于该样本量不触发回归（仅定性）


@dataclass
class MetricDelta:
    name: str
    k: int | None
    value: float
    baseline_value: float
    delta: float
    n: int
    is_regression: bool


@dataclass
class DiffReport:
    deltas: list[MetricDelta] = field(default_factory=list)
    regressions: list[MetricDelta] = field(default_factory=list)
    # 口径不一致警告（如 provider 不同：三态各留各的基线，不混比）
    incomparable_reasons: list[str] = field(default_factory=list)

    @property
    def comparable(self) -> bool:
        return not self.incomparable_reasons


_COMPARABLE_DIMS = [
    "sparse_vector_provider",
    "top_k",
    "enabled_sources",
    "rrf_k",
    "route_score_thresholds",
    "route_top_ks",
    "fusion_strategy",
    "fusion_weights",
]


def diff_metrics(
    result: EvalResult,
    baseline: EvalResult,
    criteria: RegressionCriteria = RegressionCriteria(),
) -> DiffReport:
    """同口径逐指标对比基线。口径维度不一致则整体判不可比（仍给出差值供参考）。"""
    report = DiffReport()
    for dim in _COMPARABLE_DIMS:
        cur, base = getattr(result.snapshot, dim), getattr(baseline.snapshot, dim)
        if cur != base:
            report.incomparable_reasons.append(f"{dim}: {base!r} → {cur!r}（不同口径不互比）")

    base_by_key = {(m.name, m.k): m for m in baseline.metrics}
    for mr in result.metrics:
        bm = base_by_key.get((mr.name, mr.k))
        if bm is None:
            continue
        delta = mr.mean - bm.mean
        is_regression = False
        if report.comparable and mr.n >= criteria.min_n:
            if mr.name == "recall" and delta < -criteria.recall_drop:
                is_regression = True
            elif mr.name.startswith("ndcg") and delta < -criteria.ndcg_drop:
                is_regression = True
        md = MetricDelta(
            name=mr.name, k=mr.k, value=mr.mean, baseline_value=bm.mean,
            delta=delta, n=mr.n, is_regression=is_regression,
        )
        report.deltas.append(md)
        if is_regression:
            report.regressions.append(md)
    return report
