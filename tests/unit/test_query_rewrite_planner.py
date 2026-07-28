from __future__ import annotations

from linkrag_eval.golden.schema import GoldenSample
from linkrag_eval.models import QuestionType
from linkrag_eval.query_rewrite.planner import QueryRewritePlanner


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.prompt = None

    async def generate_json(self, **kwargs):
        self.prompt = kwargs
        return self.response


def sample() -> GoldenSample:
    return GoldenSample(
        id="q1",
        query="订单ABC-7为什么不能退款",
        user_id=990001,
        dataset_ids=[992000],
        expected_chunk_ids=["secret-target"],
        expected_doc_ids=[1],
        type=QuestionType.PARAPHRASE,
    )


async def test_planner_prompt_does_not_include_qrels() -> None:
    client = FakeClient(
        {
            "query_type": "exact_identifier",
            "queries": {
                "dense": "订单ABC-7的退款限制是什么",
                "sparse": "订单 ABC-7 退款限制",
                "bm25": "ABC-7 不能退款",
            },
            "weights": {"dense": 0.3, "sparse": 0.35, "bm25": 0.35},
            "protected_candidates": {"dense": 2, "sparse": 3, "bm25": 3},
            "confidence": 0.9,
        }
    )
    planner = QueryRewritePlanner(client, model="rewrite-model")

    plan = await planner.plan(sample())

    assert not plan.fallback
    assert "secret-target" not in client.prompt["prompt"]
    assert "expected_chunk_ids" not in client.prompt["prompt"]


async def test_planner_falls_back_on_invalid_response() -> None:
    planner = QueryRewritePlanner(FakeClient(None), model="rewrite-model")

    plan = await planner.plan(sample())

    assert plan.fallback
    assert plan.dense_query == sample().query
