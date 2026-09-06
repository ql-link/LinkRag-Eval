"""OpenAIDenseEmbedder:mock httpx 验证 /embeddings 解析、分批、回序、错误。不触网络。"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from linkrag_eval.config import EvalSettings
from linkrag_eval.llm.dense_client import (
    DenseEncodeError,
    DenseInputLengthError,
    OpenAIDenseEmbedder,
    build_alt_dense_embedder,
    build_dense_embedder,
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


def _length_error(*, status=400, **updates):
    error = {
        "code": "InvalidParameter", "type": "InvalidParameter", "param": None,
        "message": "<400> InternalError.Algo.InvalidParameter: "
        "Range of input length should be [1, 33000]",
        **updates,
    }
    return httpx.Response(status, json={"error": error})


def _success(texts):
    return httpx.Response(200, json={"data": [
        {"index": index, "embedding": [len(text), ord(text[0]) if text else 0]}
        for index, text in reversed(list(enumerate(texts)))
    ]})


async def test_metadata_records_successfully_sent_characters_without_changing_normal_text():
    original = [" 2026年利润 12.3万元\n", "A🦦B", "v2.7 / x<=10 & !allowed"]
    sent = []

    def handler(request):
        texts = json.loads(request.content)["input"]
        sent.append(texts)
        return _success(texts)

    embedder = _emb(handler, input_length_policy="prefix_on_length_error")
    vectors = await embedder.aembed_with_metadata(original)
    assert sent == [original]
    assert [vector.input_chars for vector in vectors] == list(map(len, original))
    assert vectors[1].input_chars == 3  # Unicode 码点，不是 UTF-8 字节数或 tokenizer tokens。
    assert [vector.values[0] for vector in vectors] == list(map(len, original))
    await embedder.aclose()


async def test_default_policy_rejects_a_structured_length_error_without_retry():
    calls = []

    def handler(request):
        calls.append(json.loads(request.content)["input"])
        return _length_error()

    embedder = _emb(handler)
    with pytest.raises(DenseInputLengthError) as error:
        await embedder.aembed(["文" * 17])
    assert error.value.reported_limit == 33000
    assert calls == [["文" * 17]]
    await embedder.aclose()


async def test_single_input_halves_only_after_rejection_and_query_uses_same_policy():
    calls = []
    original = "甲乙丙丁戊己庚辛壬癸0123456"

    def handler(request):
        texts = json.loads(request.content)["input"]
        calls.append(texts)
        return _length_error() if len(texts[0]) > 5 else _success(texts)

    embedder = _emb(handler, input_length_policy="prefix_on_length_error")
    [vector] = await embedder.aembed_with_metadata([original])
    assert calls == [[original], [original[:8]], [original[:4]]]
    assert vector.input_chars == 4
    calls.clear()
    query_vector, usage = await embedder.aembed_query_detailed(original)
    assert query_vector == vector.values
    assert usage is None
    assert calls == [[original], [original[:8]], [original[:4]]]
    await embedder.aclose()


async def test_batch_length_rejection_identifies_each_input_before_shortening():
    original = ["短文本", "L" * 17, "尾部"]
    calls = []

    def handler(request):
        texts = json.loads(request.content)["input"]
        calls.append(texts)
        return _length_error() if any(len(text) > 5 for text in texts) else _success(texts)

    embedder = _emb(handler, input_length_policy="prefix_on_length_error")
    vectors = await embedder.aembed_with_metadata(original)
    assert calls == [
        original, [original[0]], [original[1]], [original[1][:8]], [original[1][:4]], [original[2]],
    ]
    assert [vector.input_chars for vector in vectors] == [3, 4, 2]
    assert [vector.values[1] for vector in vectors] == [ord("短"), ord("L"), ord("尾")]
    assert original == ["短文本", "L" * 17, "尾部"]
    await embedder.aclose()


@pytest.mark.parametrize("response", [
    _length_error(status=401), _length_error(status=429), _length_error(status=500),
    _length_error(code="different_error"), _length_error(type="different_error"),
    _length_error(param="max_tokens"),
    _length_error(message="Range of input length should be [1, 33000]"),
    _length_error(message="<400> InternalError.Algo.InvalidParameter: Range of max_tokens should be [1, 33000]"),
    _length_error(message="<400> InternalError.Algo.InvalidParameter: Range of input length should be [1, 33000] secret echoed"),
    httpx.Response(400, text="InvalidParameter secret non-JSON response"),
    httpx.Response(400, json={"error": "InvalidParameter"}),
])
async def test_other_errors_never_trigger_input_shortening_or_echo_response(response):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content)["input"])
        return response

    embedder = _emb(handler, input_length_policy="prefix_on_length_error", max_retries=0)
    with pytest.raises(DenseEncodeError) as error:
        await embedder.aembed(["abcdefghijk"])
    assert not isinstance(error.value, DenseInputLengthError)
    assert "secret" not in str(error.value)
    assert calls == [["abcdefghijk"]]
    await embedder.aclose()


@pytest.mark.parametrize("text", ["", "甲", "123456789"])
async def test_length_rejection_terminates_at_single_character_without_empty_retry(text):
    calls = []

    def handler(request):
        value = json.loads(request.content)["input"][0]
        calls.append(value)
        return _length_error()

    embedder = _emb(handler, input_length_policy="prefix_on_length_error")
    with pytest.raises(DenseInputLengthError):
        await embedder.aembed([text])
    expected = [text]
    while len(expected[-1]) > 1:
        expected.append(expected[-1][:len(expected[-1]) // 2])
    assert calls == expected
    await embedder.aclose()


async def test_one_failed_batch_cancels_and_awaits_sibling_requests():
    slow_started = asyncio.Event()
    active = set()
    cancelled = set()

    async def handler(request):
        value = json.loads(request.content)["input"][0]
        active.add(value)
        try:
            if value == "fail":
                await slow_started.wait()
                return httpx.Response(401, text="denied")
            if value == "slow":
                slow_started.set()
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.add(value)
            raise
        finally:
            active.remove(value)

    embedder = _emb(handler, batch_size=1, concurrency=2)
    with pytest.raises(DenseEncodeError):
        await embedder.aembed(["fail", "slow", "queued"])
    assert "slow" in cancelled
    assert active == set()
    await embedder.aclose()


async def test_caller_cancellation_awaits_all_active_model_requests():
    all_started = asyncio.Event()
    active = set()
    cancelled = set()

    async def handler(request):
        value = json.loads(request.content)["input"][0]
        active.add(value)
        if len(active) == 2:
            all_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.add(value)
            raise
        finally:
            active.remove(value)

    embedder = _emb(handler, batch_size=1, concurrency=2)
    operation = asyncio.create_task(embedder.aembed_with_metadata(["a", "b"]))
    await asyncio.wait_for(all_started.wait(), timeout=1)
    operation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert cancelled == {"a", "b"}
    assert active == set()
    await embedder.aclose()


async def test_factory_reads_current_input_length_policy():
    calls = []

    def handler(request):
        texts = json.loads(request.content)["input"]
        calls.append(texts)
        return _length_error() if len(texts[0]) > 2 else _success(texts)

    settings = EvalSettings(
        _env_file=None, embed_api_key="k", embed_base_url="https://fixture.invalid/v1",
        embed_input_length_policy="prefix_on_length_error",
    )
    embedder = build_dense_embedder(settings)
    assert embedder.input_length_policy == "prefix_on_length_error"
    embedder._client = _client(handler)
    [vector] = await embedder.aembed_with_metadata(["abcd"])
    assert calls == [["abcd"], ["ab"]]
    assert vector.input_chars == 2
    await embedder.aclose()


@pytest.mark.parametrize("indices", [[0, 0], [1, 2], [0.0, 1], [None, 1]])
async def test_metadata_rejects_ambiguous_response_input_mapping(indices):
    def handler(_):
        return httpx.Response(200, json={"data": [
            {"index": index, "embedding": [0.1]} for index in indices
        ]})

    embedder = _emb(handler)
    with pytest.raises(DenseEncodeError, match="index"):
        await embedder.aembed_with_metadata(["短", "较长文字"])
    await embedder.aclose()
