"""DB 结果仓储单测:只用内存 SQLite,不连活栈。"""

from __future__ import annotations

from sqlalchemy import select

from linkrag_eval.models import EvalResult, Layer, MetricResult, QuestionType, Snapshot
from linkrag_eval.store.db_result_store import EvalDbResultStore
from linkrag_eval.store.engine import close_eval_engines, get_eval_sessionmaker, init_eval_schema
from linkrag_eval.store.models import EvalMetricResultDB, EvalRunDB


def _snapshot(run_id: str) -> Snapshot:
    return Snapshot(
        run_id=run_id,
        git_sha="abc1234",
        sparse_vector_provider="ark:bge-m3",
        top_k=10,
        score_threshold=0.0,
        enabled_sources=["dense", "sparse"],
        rrf_k=60,
        rerank_top_n=None,
        chat_model="",
        judge_model="",
        generator_model="",
        token_budget=0,
        prompt_version="v1",
    )


def _result(run_id: str, value: float) -> EvalResult:
    return EvalResult(
        run_id=run_id,
        snapshot=_snapshot(run_id),
        metrics=[
            MetricResult(
                name="recall",
                layer=Layer.RETRIEVAL,
                k=10,
                mean=value,
                n=2,
                by_type={QuestionType.KEYWORD: value},
                by_type_n={QuestionType.KEYWORD: 2},
            )
        ],
    )


async def test_db_result_store_saves_and_loads_baseline() -> None:
    url = "sqlite+aiosqlite:///:memory:"
    await init_eval_schema(url)
    sessionmaker = get_eval_sessionmaker(url)
    store = EvalDbResultStore(sessionmaker)
    try:
        await store.save_result(_result("r1", 0.9), dataset="demo")
        await store.save_result(_result("r1", 0.8), dataset="demo")  # 幂等替换指标行

        async with sessionmaker() as session:
            run = await session.get(EvalRunDB, "r1")
            metrics = (
                await session.execute(
                    select(EvalMetricResultDB).where(EvalMetricResultDB.run_id == "r1")
                )
            ).scalars().all()

        assert run is not None
        assert run.status == "done"
        assert run.top_k == 10
        assert run.sparse_provider == "ark:bge-m3"
        assert len(metrics) == 2
        assert sorted(m.type_bucket for m in metrics) == ["__all__", "keyword"]

        loaded = await store.load_baseline("r1")
        assert loaded is not None
        metric = loaded.metrics[0]
        assert metric.mean == 0.8
        assert metric.by_type[QuestionType.KEYWORD] == 0.8
    finally:
        await close_eval_engines()
