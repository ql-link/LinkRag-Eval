"""指标注册表:按 Layer 注册/取用,让加指标无需改 runner。"""

from __future__ import annotations

from linkrag_eval.contracts.metric import Metric
from linkrag_eval.models import Layer

_REGISTRY: dict[Layer, list[Metric]] = {layer: [] for layer in Layer}


def register(metric: Metric) -> None:
    bucket = _REGISTRY[metric.layer]
    if any(m.name == metric.name and type(m) is type(metric) for m in bucket):
        return  # 幂等:同型同名不重复注册
    bucket.append(metric)


def metrics_for(layer: Layer) -> list[Metric]:
    return list(_REGISTRY[layer])


def register_defaults() -> None:
    """注册各层默认指标组(当前仅检索层;后续在此追加)。"""
    from linkrag_eval.metrics.retrieval import default_retrieval_metrics

    for metric in default_retrieval_metrics():
        register(metric)
