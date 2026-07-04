"""run_stage 端到端编排:golden × fake evaluable × 真实 RecallAtK × aggregate。不需 rag/活栈。"""

from __future__ import annotations

import pytest

from linkrag_eval.golden.schema import GoldenSample
from linkrag_eval.app import format_retrieval_summary
from linkrag_eval.metrics.retrieval import RecallAtK
from linkrag_eval.models import Layer, QuestionType, RankedHit, Snapshot, StageOutput
from linkrag_eval.runners import RunContext, run_stage


def _snapshot() -> Snapshot:
    return Snapshot(
        run_id="r1", git_sha="abc", sparse_vector_provider="ark", top_k=10,
        score_threshold=0.0, enabled_sources=["dense", "sparse"], rrf_k=60,
        rerank_top_n=None, chat_model="", judge_model="", generator_model="",
        token_budget=0, prompt_version="v1",
    )


class _FakeRecall:
    """按 sample.id 返回预设 doc 排序的召回。"""

    layer = Layer.RETRIEVAL

    def __init__(self, ranked_docs_by_id: dict[str, list[int]]):
        self._m = ranked_docs_by_id

    async def run(self, sample, *, upstream=None) -> StageOutput:
        docs = self._m[sample.id]
        ranked = [RankedHit(f"c{d}", d, 990131, i, 1.0 - i * 0.1) for i, d in enumerate(docs)]
        return StageOutput(layer=self.layer, query=sample.query, ranked=ranked, elapsed_ms=5)


def _ctx() -> RunContext:
    return RunContext(run_id="r1", snapshot=_snapshot(), store=None, top_k=10)


async def test_run_stage_aggregates_recall() -> None:
    golden = [
        GoldenSample(id="q1", query="问1", user_id=1, dataset_ids=[990131], expected_doc_ids=[1, 2],
                     type=QuestionType.KEYWORD),
        GoldenSample(id="q2", query="问2", user_id=1, dataset_ids=[990131], expected_doc_ids=[3],
                     type=QuestionType.PARAPHRASE),
    ]
    ev = _FakeRecall({"q1": [1, 9, 2], "q2": [3, 8]})  # q1 recall@1=.5 @3=1; q2 recall@1=1
    result = await run_stage(golden, ev, [RecallAtK([1, 3])], _ctx())

    recall = {(r.name, r.k): r for r in result.metrics if r.name == "recall"}
    assert recall[("recall", 1)].mean == pytest.approx(0.75)  # (.5 + 1)/2
    assert recall[("recall", 3)].mean == pytest.approx(1.0)
    assert recall[("recall", 1)].n == 2
    # 按 QuestionType 分桶
    assert recall[("recall", 1)].by_type[QuestionType.KEYWORD] == pytest.approx(0.5)
    assert recall[("recall", 1)].by_type[QuestionType.PARAPHRASE] == pytest.approx(1.0)
    # per_sample 诊断
    assert len(result.per_sample) == 2
    assert result.run_id == "r1"
    assert "run_quality = clean" in format_retrieval_summary(result)


async def test_domain_bucketing() -> None:
    golden = [
        GoldenSample(id="q1", query="q", user_id=1, dataset_ids=[1], expected_doc_ids=[1]),
        GoldenSample(id="q2", query="q", user_id=1, dataset_ids=[2], expected_doc_ids=[1]),
    ]
    ev = _FakeRecall({"q1": [1], "q2": [9]})  # q1 命中,q2 不中
    result = await run_stage(
        golden, ev, [RecallAtK([1])], _ctx(),
        domain_of=lambda s: "tech" if s.id == "q1" else "med",
    )
    r = next(r for r in result.metrics if r.name == "recall" and r.k == 1)
    assert r.by_domain["tech"] == pytest.approx(1.0)
    assert r.by_domain["med"] == pytest.approx(0.0)


async def test_requires_judge_guard() -> None:
    class _NeedsJudge:
        name = "x"
        layer = Layer.GENERATION
        requires_judge = True
        requires_golden_answer = False

        async def compute(self, sample, output, *, judge=None):
            return []

    golden = [GoldenSample(id="q1", query="q", user_id=1, dataset_ids=[1], expected_doc_ids=[1])]
    with pytest.raises(ValueError, match="judge"):
        await run_stage(golden, _FakeRecall({"q1": [1]}), [_NeedsJudge()], _ctx())
