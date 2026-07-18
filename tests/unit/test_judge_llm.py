"""EvalChatClient + parse_llm_json:mock httpx 验证生成/JSON解析/重试/硬失败。不触网络。"""

from __future__ import annotations

import httpx
import pytest

from linkrag_eval.judge.eval_llm import (
    EvalChatClient,
    EvalLLMConfigError,
    ProviderUnavailable,
)
from linkrag_eval.judge.json_parse import parse_llm_json


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _chat(handler, **kw) -> EvalChatClient:
    return EvalChatClient(
        base_url="https://x/v1/chat/completions", api_key="k", model="deepseek-chat",
        http_client=_client(handler), **kw,
    )


def _ok(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


async def test_generate_parses_content() -> None:
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        import json
        seen["model"] = json.loads(req.content)["model"]
        return _ok("hello")

    res = await _chat(handler).generate(prompt="hi", system_prompt="sys")
    assert res.content == "hello"
    assert seen["url"] == "https://x/v1/chat/completions"  # base_url 即完整端点,不拼后缀
    assert seen["model"] == "deepseek-chat"


async def test_generate_json_strips_fence() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return _ok('```json\n{"score": 0.8}\n```')

    assert await _chat(handler).generate_json(prompt="q") == {"score": 0.8}


async def test_generate_json_returns_none_on_garbage() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return _ok("no json here")

    assert await _chat(handler).generate_json(prompt="q") is None


async def test_generate_json_returns_none_on_provider_unavailable() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    import linkrag_eval.judge.eval_llm as mod
    orig_sleep = mod.asyncio.sleep

    async def _no_sleep(_):
        return None

    mod.asyncio.sleep = _no_sleep
    try:
        assert await _chat(handler, max_retries=1).generate_json(prompt="q") is None
    finally:
        mod.asyncio.sleep = orig_sleep


async def test_5xx_retries_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="overloaded")
        return _ok("recovered")

    # max_retries=1 + 退避 sleep 打桩为瞬时,避免真等
    import linkrag_eval.judge.eval_llm as mod
    orig_sleep = mod.asyncio.sleep

    async def _no_sleep(_):
        return None

    mod.asyncio.sleep = _no_sleep
    try:
        res = await _chat(handler, max_retries=1).generate(prompt="q")
    finally:
        mod.asyncio.sleep = orig_sleep
    assert res.content == "recovered"
    assert calls["n"] == 2


async def test_5xx_exhausts_raises_provider_unavailable() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    import linkrag_eval.judge.eval_llm as mod
    orig_sleep = mod.asyncio.sleep

    async def _no_sleep(_):
        return None

    mod.asyncio.sleep = _no_sleep
    try:
        with pytest.raises(ProviderUnavailable):
            await _chat(handler, max_retries=1).generate(prompt="q")
    finally:
        mod.asyncio.sleep = orig_sleep


async def test_4xx_hard_fails_no_retry() -> None:
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401, text="unauthorized")

    with pytest.raises(httpx.HTTPStatusError):
        await _chat(handler, max_retries=3).generate(prompt="q")
    assert calls["n"] == 1  # 4xx 不重试


def test_missing_config_rejected() -> None:
    with pytest.raises(EvalLLMConfigError):
        EvalChatClient(base_url="", api_key="k", model="m")
    with pytest.raises(EvalLLMConfigError):
        EvalChatClient(base_url="https://x", api_key="k", model="")


def test_parse_llm_json_balances_braces() -> None:
    # 尾随多余文本应被截掉
    assert parse_llm_json('{"a": 1} trailing junk') == {"a": 1}
    # 嵌套对象
    assert parse_llm_json('prefix {"a": {"b": 2}} x') == {"a": {"b": 2}}
    # 非对象
    assert parse_llm_json("[]") is None
    assert parse_llm_json("") is None
