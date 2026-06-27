"""Ark / BgeM3Http SparseEncoder:用 mock httpx 验证请求/响应解析,不触网络。"""

from __future__ import annotations

import httpx
import pytest

from linkrag_eval.llm.sparse_client import (
    ArkSparseEncoder,
    BgeM3HttpSparseEncoder,
    SparseEncodeError,
)


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_aencode_parses_and_sorts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # 乱序 + 一个低于 min_weight 的维度(应被过滤)
        return httpx.Response(
            200,
            json={"data": {"sparse_embedding": [
                {"index": 5, "value": 0.9},
                {"index": 1, "value": 0.4},
                {"index": 3, "value": 0.05},
            ]}},
        )

    enc = ArkSparseEncoder(
        api_key="k", model="m", min_weight=0.1, http_client=_mock_client(handler)
    )
    [vec] = await enc.aencode(["hello"])
    assert vec.indices == [1, 5]  # 升序,index=3 被 min_weight 过滤
    assert vec.values == [0.4, 0.9]


async def test_empty_input_returns_empty() -> None:
    enc = ArkSparseEncoder(api_key="k", model="m")
    assert await enc.aencode([]) == []


async def test_4xx_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad")

    enc = ArkSparseEncoder(api_key="k", model="m", http_client=_mock_client(handler))
    with pytest.raises(SparseEncodeError):
        await enc.aencode(["x"])


def test_missing_key_or_model_rejected() -> None:
    with pytest.raises(SparseEncodeError):
        ArkSparseEncoder(api_key="", model="m")
    with pytest.raises(SparseEncodeError):
        ArkSparseEncoder(api_key="k", model="")


async def test_bge_m3_http_batch_parse() -> None:
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        import json
        seen["body"] = json.loads(req.content)
        # 每条一个 {token_id: weight};含低权重(被 min_weight 过滤)
        return httpx.Response(200, json={"sparse": [
            {"5": 0.9, "1": 0.4, "3": 0.05},
            {"2": 0.8},
        ]})

    enc = BgeM3HttpSparseEncoder(
        base_url="http://x:37997", min_weight=0.1, http_client=_mock_client(handler)
    )
    vecs = await enc.aencode(["a", "b"])
    assert seen["body"] == {"texts": ["a", "b"], "return_dense": False, "return_sparse": True}
    assert vecs[0].indices == [1, 5] and vecs[0].values == [0.4, 0.9]  # 升序,3 被过滤
    assert vecs[1].indices == [2]


async def test_bge_m3_http_count_mismatch_raises() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"sparse": [{"1": 0.5}]})  # 只回 1 条

    enc = BgeM3HttpSparseEncoder(base_url="http://x", http_client=_mock_client(handler))
    with pytest.raises(SparseEncodeError, match="数量不符"):
        await enc.aencode(["a", "b"])


def test_bge_m3_http_missing_base_url_rejected() -> None:
    with pytest.raises(SparseEncodeError):
        BgeM3HttpSparseEncoder(base_url="")
