"""OpenAIDenseEmbedder:mock httpx 验证 /embeddings 解析、分批、回序、错误。不触网络。"""

from __future__ import annotations

import httpx
import pytest

from linkrag_eval.config import EvalSettings
from linkrag_eval.llm.dense_client import (
    DenseEncodeError,
    OpenAIDenseEmbedder,
    build_alt_dense_embedder,
)


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


async def test_batches_use_bounded_concurrency_and_keep_order() -> None:
    active = 0
    maximum = 0

    async def handler(req: httpx.Request) -> httpx.Response:
        nonlocal active, maximum
        import asyncio
        import json

        active += 1
        maximum = max(maximum, active)
        values = json.loads(req.content)["input"]
        await asyncio.sleep(0.01)
        active -= 1
        return httpx.Response(
            200,
            json={"data": [{"index": i, "embedding": [float(value)]} for i, value in enumerate(values)]},
        )

    emb = _emb(handler, batch_size=1, concurrency=2)
    vectors = await emb.aembed(["1", "2", "3", "4"])

    assert maximum == 2
    assert vectors == [[1.0], [2.0], [3.0], [4.0]]


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


def test_build_alt_dense_embedder_uses_alt_settings() -> None:
    settings = EvalSettings(
        _env_file=None,
        alt_embed_api_key="k",
        alt_embed_model="alt-model",
        alt_embed_base_url="https://alt/v1",
        alt_embed_dim=768,
        alt_embed_batch_size=3,
    )

    embedder = build_alt_dense_embedder(settings)

    assert embedder.model_name == "alt-model"
    assert embedder.dim == 768


def test_build_alt_dense_embedder_reports_alt_missing_config() -> None:
    with pytest.raises(DenseEncodeError, match="EVAL_ALT_EMBED_API_KEY"):
        build_alt_dense_embedder(EvalSettings(_env_file=None))
