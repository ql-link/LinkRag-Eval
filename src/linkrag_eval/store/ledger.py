"""EvalResult → tidy 长表行(ledger)。纯函数,零 IO/零 rag。

搬迁自源仓库 ``storage/filesystem.py:ledger_rows``。每行 = 一个指标在一个 type/domain 桶上
的取值,联合主键 (run_id, layer, metric, k, relevance_scale, type_bucket, domain_bucket)。
JSON 报告与(后续)DB 结果库纯下游消费同一份长表,口径一致、零返工。
"""

from __future__ import annotations

from typing import Any

from linkrag_eval.models import EvalResult

ALL_BUCKET = "__all__"


def _scale_of(metric_name: str) -> str:
    base = metric_name.removesuffix("_chunk").removesuffix("_doc")
    return "graded" if base.endswith("_graded") else "binary"


def ledger_rows(result: EvalResult, *, dataset: str, ts: str) -> list[dict[str, Any]]:
    """EvalResult → tidy 长表行(每行 = 一个指标在一个 type/domain 桶上的取值)。"""
    snap = result.snapshot
    config_dims = {
        "sparse_provider": snap.sparse_vector_provider,
        "top_k": snap.top_k,
        "score_threshold": snap.score_threshold,
        "enabled_sources": ",".join(sorted(snap.enabled_sources)),
        "rrf_k": snap.rrf_k,
        "route_top_ks": snap.route_top_ks,
        "fusion_strategy": snap.fusion_strategy,
        "fusion_weights": snap.fusion_weights,
        "rerank_top_n": snap.rerank_top_n,
        "chat_model": snap.chat_model,
        "judge_model": snap.judge_model,
        "generator_model": snap.generator_model,
    }
    rows: list[dict[str, Any]] = []
    for mr in result.metrics:
        base = {
            "run_id": result.run_id,
            "ts": ts,
            "git_sha": snap.git_sha,
            "dataset": dataset,
            "layer": mr.layer.value,
            "metric": mr.name,
            "k": mr.k,
            "relevance_scale": _scale_of(mr.name),
            **config_dims,
        }
        rows.append({**base, "type_bucket": ALL_BUCKET, "domain_bucket": ALL_BUCKET,
                     "value": mr.mean, "n": mr.n})
        for qtype, value in mr.by_type.items():
            rows.append(
                {
                    **base,
                    "type_bucket": qtype.value,
                    "domain_bucket": ALL_BUCKET,
                    "value": value,
                    "n": mr.by_type_n.get(qtype, 0),
                }
            )
        for domain, value in mr.by_domain.items():
            rows.append(
                {
                    **base,
                    "type_bucket": ALL_BUCKET,
                    "domain_bucket": domain,
                    "value": value,
                    "n": mr.by_domain_n.get(domain, 0),
                }
            )
    return rows
