"""DB 结果仓储:把 EvalResult 写入 eval_run / eval_metric_result。

文件结果仍是可审计原始产物;DB 台账用于趋势查询与跨 run 汇总。实现只使用 eval 自持
``EvalBase`` 模型和 ``EVAL_DB_*`` 连接,不触碰生产库。
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from linkrag_eval.models import EvalResult, Layer, MetricResult, QuestionType, Snapshot
from linkrag_eval.store.engine import get_eval_sessionmaker
from linkrag_eval.store.ledger import ALL_BUCKET
from linkrag_eval.store.models import EvalMetricResultDB, EvalRunDB


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _scale_of(metric_name: str) -> str:
    base = metric_name.removesuffix("_chunk").removesuffix("_doc")
    return "graded" if base.endswith("_graded") else "binary"


def _run_record(
    result: EvalResult,
    *,
    dataset: str | None,
    baseline_run_id: str | None,
    status: str,
) -> EvalRunDB:
    snap = result.snapshot
    layers = sorted({m.layer.value for m in result.metrics})
    quality = _run_quality(result) if status in {"done", "failed"} else {}
    return EvalRunDB(
        run_id=result.run_id,
        git_sha=snap.git_sha or None,
        dataset_ids_json=_json_dumps({"dataset": dataset}) if dataset else None,
        layers_json=_json_dumps(layers),
        baseline_run_id=baseline_run_id,
        status=status,
        snapshot_json=_json_dumps(asdict(snap)),
        sparse_provider=snap.sparse_vector_provider or None,
        top_k=snap.top_k,
        enabled_sources=",".join(sorted(snap.enabled_sources)) if snap.enabled_sources else None,
        rrf_k=snap.rrf_k,
        rerank_top_n=snap.rerank_top_n,
        chat_model=snap.chat_model or None,
        judge_model=snap.judge_model or None,
        generator_model=snap.generator_model or None,
        computer_fingerprint=None,
        run_quality=quality.get("run_quality"),
        failed_samples=quality.get("failed_samples"),
        failed_sources_json=(
            _json_dumps(quality["failed_sources"]) if "failed_sources" in quality else None
        ),
        zero_ranked=quality.get("zero_ranked"),
        finished_at=datetime.now() if status in {"done", "failed"} else None,
    )


def _run_quality(result: EvalResult) -> dict[str, Any]:
    """从逐样本明细汇总运行质量,便于 DB 直接筛 clean run。"""
    failed_counter: Counter[str] = Counter()
    failed_samples = 0
    zero_ranked = 0
    for row in result.per_sample:
        failed = list(row.get("failed_sources") or [])
        if failed:
            failed_samples += 1
            failed_counter.update(failed)
        if row.get("n_ranked") == 0:
            zero_ranked += 1
    return {
        "run_quality": "clean" if failed_samples == 0 and zero_ranked == 0 else "non-clean",
        "failed_samples": failed_samples,
        "failed_sources": dict(failed_counter),
        "zero_ranked": zero_ranked,
    }


def _metric_records(result: EvalResult) -> list[EvalMetricResultDB]:
    rows: list[EvalMetricResultDB] = []
    for metric in result.metrics:
        rows.append(
            EvalMetricResultDB(
                run_id=result.run_id,
                layer=metric.layer.value,
                metric=metric.name,
                k=metric.k,
                relevance_scale=_scale_of(metric.name),
                type_bucket=ALL_BUCKET,
                value=metric.mean,
                n=metric.n,
                n_samples=1,
            )
        )
        for qtype, value in metric.by_type.items():
            rows.append(
                EvalMetricResultDB(
                    run_id=result.run_id,
                    layer=metric.layer.value,
                    metric=metric.name,
                    k=metric.k,
                    relevance_scale=_scale_of(metric.name),
                    type_bucket=qtype.value,
                    value=value,
                    n=metric.by_type_n.get(qtype, 0),
                    n_samples=1,
                )
            )
    return rows


async def _assign_sqlite_metric_ids(
    session: AsyncSession,
    rows: list[EvalMetricResultDB],
) -> None:
    """SQLite 不会对 BigInteger PK 自动递增;单测后端显式补 id,MySQL 不走此分支。"""
    bind = session.get_bind()
    if bind.dialect.name != "sqlite" or not rows:
        return
    max_id = (
        await session.execute(select(func.max(EvalMetricResultDB.id)))
    ).scalar_one_or_none()
    next_id = int(max_id or 0) + 1
    for row in rows:
        row.id = next_id
        next_id += 1


class EvalDbResultStore:
    """异步 DB 后端,写 ``eval_run`` 与 ``eval_metric_result`` 两张表。"""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._sessionmaker = sessionmaker or get_eval_sessionmaker()

    async def save_snapshot(self, snapshot: Snapshot) -> None:
        result = EvalResult(run_id=snapshot.run_id, snapshot=snapshot, metrics=[])
        async with self._sessionmaker() as session:
            await session.merge(
                _run_record(result, dataset=None, baseline_run_id=None, status="running")
            )
            await session.commit()

    async def save_result(
        self,
        result: EvalResult,
        *,
        dataset: str | None = None,
        baseline_run_id: str | None = None,
        status: str = "done",
    ) -> None:
        """幂等写入一次结果:run 行 upsert,metric 行按 run_id 全量替换。"""
        async with self._sessionmaker() as session:
            await session.merge(
                _run_record(
                    result,
                    dataset=dataset,
                    baseline_run_id=baseline_run_id,
                    status=status,
                )
            )
            await session.execute(
                delete(EvalMetricResultDB).where(EvalMetricResultDB.run_id == result.run_id)
            )
            metrics = _metric_records(result)
            await _assign_sqlite_metric_ids(session, metrics)
            session.add_all(metrics)
            await session.commit()

    async def save_report(self, run_id: str, content: str) -> None:
        """报告 HTML 仍走文件后端;DB 只保存可查询结构化台账。"""
        return None

    async def load_baseline(self, run_id: str) -> EvalResult | None:
        async with self._sessionmaker() as session:
            run = await session.get(EvalRunDB, run_id)
            if run is None or not run.snapshot_json:
                return None
            metric_rows = (
                await session.execute(
                    select(EvalMetricResultDB).where(EvalMetricResultDB.run_id == run_id)
                )
            ).scalars().all()

        snapshot = Snapshot(**json.loads(run.snapshot_json))
        grouped: dict[tuple[str, str, int | None], MetricResult] = {}
        for row in metric_rows:
            key = (row.metric, row.layer, row.k)
            metric = grouped.get(key)
            if metric is None:
                metric = MetricResult(
                    name=row.metric,
                    layer=Layer(row.layer),
                    k=row.k,
                    mean=0.0,
                    n=0,
                )
                grouped[key] = metric
            if row.type_bucket == ALL_BUCKET:
                metric.mean = row.value
                metric.n = row.n
            else:
                qtype = QuestionType(row.type_bucket)
                metric.by_type[qtype] = row.value
                metric.by_type_n[qtype] = row.n

        return EvalResult(
            run_id=run_id,
            snapshot=snapshot,
            metrics=sorted(
                grouped.values(),
                key=lambda m: (m.name, m.k if m.k is not None else -1, m.layer.value),
            ),
        )
