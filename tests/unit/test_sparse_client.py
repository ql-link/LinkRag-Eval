"""ArkSparseEncoder:用 mock httpx 验证请求/响应解析,不触网络。"""

from __future__ import annotations

import httpx
import pytest

from linkrag_eval.llm.sparse_client import ArkSparseEncoder, SparseEncodeError


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
