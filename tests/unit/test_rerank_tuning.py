from __future__ import annotations

import httpx

from linkrag_eval.llm.rerank_client import RerankScore, StandardRerankClient
from linkrag_eval.models import Layer, RankedHit, StageOutput
from linkrag_eval.retrieval.rerank_tuning import rerank_fused_candidates


async def test_standard_rerank_client_maps_scores_by_input_index() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rerank"
        assert request.headers["Authorization"] == "Bearer test-key"
        body = __import__("json").loads(request.content)
        assert body["documents"] == ["one", "two"]
        return httpx.Response(200, json={"results": [
            {"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.2}
        ]})

    client = StandardRerankClient(
        base_url="https://rerank.example", api_key="test-key", model="rerank-test",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    scores = await client.rerank("q", ["one", "two"])
    assert {item.index: item.score for item in scores} == {0: 0.2, 1: 0.9}
    await client.aclose()


async def test_standard_rerank_client_preserves_explicit_plural_endpoint() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/compatible-api/v1/reranks"
        return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 1.0}]})

    client = StandardRerankClient(
        base_url="https://workspace.example/compatible-api/v1/reranks",
        api_key="test-key",
        model="qwen3-rerank",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert (await client.rerank("q", ["one"]))[0].score == 1.0
    await client.aclose()


async def test_dashscope_rerank_uses_native_payload_and_nested_results() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content)
        assert body == {
            "model": "qwen3-rerank",
            "input": {"query": "q", "documents": ["one"]},
            "parameters": {"return_documents": False},
        }
        return httpx.Response(200, json={"output": {"results": [{"index": 0, "relevance_score": 0.8}]}})

    client = StandardRerankClient(
        base_url="https://dashscope.example/api/v1/services/rerank/text-rerank/text-rerank",
        api_key="test-key", model="qwen3-rerank", provider="dashscope",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    assert (await client.rerank("q", ["one"]))[0].score == 0.8
    await client.aclose()


async def test_rerank_truncates_documents_before_request() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = __import__("json").loads(request.content)
        assert body["documents"] == ["abc"]
        return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 1.0}]})

    client = StandardRerankClient(
        base_url="https://rerank.example", api_key="test-key", model="test",
        max_document_chars=3,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    await client.rerank("q", ["abcdef"])
    await client.aclose()


def test_rerank_fused_candidates_preserves_metadata_and_order() -> None:
    fused = StageOutput(
        layer=Layer.RETRIEVAL,
        query="q",
        ranked=[
            RankedHit("c1", 1, 1, 0, 0.9, frozenset({"dense"})),
            RankedHit("c2", 2, 1, 1, 0.8, frozenset({"sparse"})),
        ],
    )
    output, missing = rerank_fused_candidates(
        fused,
        contents={"c1": "a", "c2": "b"},
        scores=[
            RerankScore(0, 0.1),
            RerankScore(1, 0.9),
        ],
        final_top_k=10,
    )
    assert missing == 0
    assert output.layer == Layer.RERANK
    assert [hit.chunk_id for hit in output.ranked] == ["c2", "c1"]
    assert output.ranked[0].sources == frozenset({"sparse"})
