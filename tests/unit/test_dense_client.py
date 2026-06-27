"""OpenAIDenseEmbedder:mock httpx 验证 /embeddings 解析、分批、回序、错误。不触网络。"""

from __future__ import annotations

import httpx
import pytest

from linkrag_eval.llm.dense_client import DenseEncodeError, OpenAIDenseEmbedder


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _emb(handler, **kw) -> OpenAIDenseEmbedder:
    return OpenAIDenseEmbedder(
        api_key="k", model="text-embedding-v4", base_url="https://x/v1",
        http_client=_client(handler), **kw,
    )


async def test_endpoint_and_parse() -> None:
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        import json
        body = json.loads(req.content)
        # 按乱序 index 返回,验证回序
        data = [{"index": i, "embedding": [float(i), 0.5]} for i in range(len(body["input"]))]
        return httpx.Response(200, json={"data": list(reversed(data))})

    emb = _emb(handler)
    vecs = await emb.aembed(["a", "b", "c"])
    assert seen["url"] == "https://x/v1/embeddings"  # 自动补 /embeddings
    assert vecs == [[0.0, 0.5], [1.0, 0.5], [2.0, 0.5]]  # 已按 index 回序


async def test_batching() -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        import json
        calls["n"] += 1
        n = len(json.loads(req.content)["input"])
        return httpx.Response(200, json={"data": [{"index": i, "embedding": [0.1]} for i in range(n)]})

    emb = _emb(handler, batch_size=2)
    vecs = await emb.aembed(["a", "b", "c", "d", "e"])
    assert len(vecs) == 5
    assert calls["n"] == 3  # 2+2+1


async def test_query_helper() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [9.0]}]})

    assert await _emb(handler).aembed_query("q") == [9.0]


async def test_4xx_raises() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    with pytest.raises(DenseEncodeError):
        await _emb(handler).aembed(["a"])


def test_missing_config_rejected() -> None:
    with pytest.raises(DenseEncodeError):
        OpenAIDenseEmbedder(api_key="", model="m", base_url="https://x")
    with pytest.raises(DenseEncodeError):
        OpenAIDenseEmbedder(api_key="k", model="m", base_url="")
