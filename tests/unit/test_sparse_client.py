"""Ark SparseEncoder:用 mock httpx 验证请求/响应解析,不触网络。"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from linkrag_eval.llm.sparse_client import (
    SAFE_SPARSE_FAILURE_REASONS,
    ArkSparseEncoder,
    SparseEncodeError,
    SparseInputLengthError,
    build_sparse_encoder,
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
    assert vec.input_chars == len("hello")


async def test_empty_input_returns_empty() -> None:
    enc = ArkSparseEncoder(api_key="k", model="m")
    assert await enc.aencode([]) == []


async def test_ark_batch_runs_with_bounded_concurrency_and_keeps_order() -> None:
    active = 0
    maximum = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, maximum
        import asyncio
        import json

        active += 1
        maximum = max(maximum, active)
        payload = json.loads(request.content)
        value = int(payload["input"][0]["text"])
        await asyncio.sleep(0.01)
        active -= 1
        return httpx.Response(
            200, json={"data": {"sparse_embedding": [{"index": value, "value": 1.0}]}}
        )

    enc = ArkSparseEncoder(
        api_key="k", model="m", concurrency=2, http_client=_mock_client(handler)
    )
    vectors = await enc.aencode(["1", "2", "3", "4"])

    assert maximum == 2
    assert [vector.indices for vector in vectors] == [[1], [2], [3], [4]]


async def test_4xx_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad")

    enc = ArkSparseEncoder(api_key="k", model="m", http_client=_mock_client(handler))
    with pytest.raises(SparseEncodeError):
        await enc.aencode(["x"])


@pytest.mark.parametrize("kwargs", [
    {"api_key": "", "model": "m"},
    {"api_key": "k", "model": ""},
    {"api_key": "k", "model": "m", "concurrency": 0},
])
def test_invalid_configuration_has_no_http_status(kwargs) -> None:
    with pytest.raises(SparseEncodeError) as error:
        ArkSparseEncoder(**kwargs)
    assert error.value.reason == "configuration"
    assert error.value.status_code is None


# 当前模型真实 HTTP400 主体，request id 使用本地 fixture，不保存服务响应标识。
LENGTH_ERROR = {"error": {
    "code": "InvalidParameter",
    "message": "Total tokens of image and text exceed max message tokens. Request id: fixture",
    "param": "",
}}


def _ok(length=1):
    return httpx.Response(200, json={
        "data": {"sparse_embedding": [{"index": length, "value": 1.0}]},
    })


def _text(request):
    return json.loads(request.content)["input"][0]["text"]


def _encoder(handler, **kwargs):
    return ArkSparseEncoder(
        api_key="fixture", model="fixture", input_length_policy="prefix_on_length_error",
        http_client=_mock_client(handler), **kwargs,
    )


async def test_prefix_reduction_changes_only_this_request_and_records_success_length():
    sent = []

    def handler(request):
        text = _text(request)
        sent.append(text)
        # 这里只模拟长度错误发生时序，不把 fake 字符阈值当作模型 token 上限。
        return httpx.Response(400, json=LENGTH_ERROR) if len(text) > 2 else _ok(len(text))

    texts = ["甲🐾乙丙丁", "短", "AlphaBeta!"]
    original = texts[:]
    enc = _encoder(handler, concurrency=1)
    vectors = await enc.aencode(texts)
    assert enc.input_length_policy == "prefix_on_length_error"
    assert sent == ["甲🐾乙丙丁", "甲🐾", "短", "AlphaBeta!", "Alpha", "Al"]
    assert [vec.input_chars for vec in vectors] == [2, 1, 2]
    assert [vec.indices for vec in vectors] == [[2], [1], [2]]
    assert texts == original


async def test_default_policy_rejects_explicit_length_error_without_shortening():
    sent = []

    def handler(request):
        sent.append(_text(request))
        return httpx.Response(400, json=LENGTH_ERROR)

    enc = ArkSparseEncoder(api_key="fixture", model="fixture", http_client=_mock_client(handler))
    assert enc.input_length_policy == "reject"
    with pytest.raises(SparseInputLengthError) as error:
        await enc.aencode(["完整原文"])
    assert sent == ["完整原文"]
    assert error.value.reason == "input_length_exceeded"
    assert error.value.status_code == 400


@pytest.mark.parametrize("status,body", [
    (400, {"error": {"code": "InvalidParameter", "message": "invalid vector length"}}),
    (400, {"error": {"code": "InvalidParameter", "message": "input is too long"}}),
    (400, {"error": {"code": "Other", "message": LENGTH_ERROR["error"]["message"]}}),
    (400, {"message": LENGTH_ERROR["error"]["message"]}),
    (400, {"error": "InvalidParameter"}),
    (401, LENGTH_ERROR),
    (403, LENGTH_ERROR),
])
async def test_other_structured_errors_never_trigger_prefix_reduction(status, body):
    sent = []

    def handler(request):
        sent.append(_text(request))
        return httpx.Response(status, json=body)

    with pytest.raises(SparseEncodeError) as error:
        await _encoder(handler).aencode(["完整原文"])
    assert not isinstance(error.value, SparseInputLengthError)
    assert error.value.reason == "http_error"
    assert error.value.status_code == status
    assert sent == ["完整原文"]


async def test_non_json_length_text_is_not_a_structured_length_error():
    sent = []

    def handler(request):
        sent.append(_text(request))
        return httpx.Response(400, text=LENGTH_ERROR["error"]["message"])

    with pytest.raises(SparseEncodeError) as error:
        await _encoder(handler).aencode(["完整原文"])
    assert not isinstance(error.value, SparseInputLengthError)
    assert error.value.reason == "http_error"
    assert error.value.status_code == 400
    assert "fixture" not in str(error.value)
    assert sent == ["完整原文"]


@pytest.mark.parametrize("kind", [408, 429, 500, 503, "connect", "timeout"])
async def test_transient_failures_retry_same_text_and_never_shorten(kind, monkeypatch):
    sent = []
    delays = []

    async def no_delay(delay):
        delays.append(delay)

    monkeypatch.setattr("linkrag_eval.llm.sparse_client.asyncio.sleep", no_delay)

    def handler(request):
        sent.append(_text(request))
        if kind == "connect":
            raise httpx.ConnectError("private endpoint", request=request)
        if kind == "timeout":
            raise httpx.ReadTimeout("private endpoint", request=request)
        return httpx.Response(kind, json=LENGTH_ERROR)

    with pytest.raises(SparseEncodeError) as error:
        await _encoder(handler, max_retries=1).aencode(["完整原文"])
    assert not isinstance(error.value, SparseInputLengthError)
    assert sent == ["完整原文", "完整原文"]
    assert delays == [2]
    if isinstance(kind, int):
        assert error.value.reason == "http_retry_exhausted"
        assert error.value.status_code == kind
        assert error.value.__cause__ is None
    else:
        assert error.value.reason == "transport_retry_exhausted"
        assert error.value.status_code is None
        assert isinstance(error.value.__cause__, httpx.RequestError)
    assert "private endpoint" not in str(error.value)


async def test_transient_retry_after_length_error_keeps_current_prefix(monkeypatch):
    sent = []

    async def no_delay(_):
        pass

    monkeypatch.setattr("linkrag_eval.llm.sparse_client.asyncio.sleep", no_delay)

    def handler(request):
        text = _text(request)
        sent.append(text)
        if len(sent) == 1:
            return httpx.Response(400, json=LENGTH_ERROR)
        if len(sent) == 2:
            return httpx.Response(429, json=LENGTH_ERROR)
        return _ok(len(text))

    [vec] = await _encoder(handler, max_retries=1).aencode(["abcdefgh"])
    assert sent == ["abcdefgh", "abcd", "abcd"]
    assert vec.input_chars == 4


async def test_single_character_length_failure_stops_without_an_empty_request():
    sent = []

    def handler(request):
        sent.append(_text(request))
        return httpx.Response(400, json=LENGTH_ERROR)

    with pytest.raises(SparseInputLengthError):
        await _encoder(handler).aencode(["甲🐾乙"])
    assert sent == ["甲🐾乙", "甲"]


async def test_zero_chars_are_known_when_an_empty_request_succeeds():
    [vec] = await _encoder(lambda _request: _ok()).aencode([""])
    assert vec.input_chars == 0


async def test_invalid_success_payload_is_not_retried_with_shorter_text():
    sent = []

    def handler(request):
        sent.append(_text(request))
        return httpx.Response(200, json={"data": {"embedding": [1.0]}})

    with pytest.raises(SparseEncodeError):
        await _encoder(handler).aencode(["完整原文"])
    assert sent == ["完整原文"]


async def test_failed_item_cancels_and_awaits_siblings_before_returning():
    slow_started = asyncio.Event()
    slow_stopped = asyncio.Event()
    sent = []

    async def handler(request):
        text = _text(request)
        sent.append(text)
        if text == "bad":
            await slow_started.wait()
            return httpx.Response(400, json={"error": {"code": "InvalidParameter", "message": "bad"}})
        slow_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            slow_stopped.set()

    with pytest.raises(SparseEncodeError):
        await _encoder(handler, concurrency=2).aencode(["bad", "slow"])
    assert slow_stopped.is_set()
    assert sent == ["bad", "slow"]


async def test_caller_cancellation_also_drains_running_requests():
    started = asyncio.Event()
    stopped = []

    async def handler(request):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.append(_text(request))

    task = asyncio.create_task(_encoder(handler, concurrency=1).aencode(["first", "queued"]))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped == ["first"]


async def test_sibling_failure_cancels_retry_backoff_before_another_post(monkeypatch):
    backoff_started = asyncio.Event()
    backoff_stopped = asyncio.Event()
    sent = []
    active = 0

    async def wait_in_backoff(_):
        backoff_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            backoff_stopped.set()

    monkeypatch.setattr("linkrag_eval.llm.sparse_client.asyncio.sleep", wait_in_backoff)

    async def handler(request):
        nonlocal active
        text = _text(request)
        sent.append(text)
        active += 1
        try:
            if text == "retry":
                return httpx.Response(429)
            if text == "fatal":
                await backoff_started.wait()
                return httpx.Response(400, json={"error": {"code": "InvalidParameter"}})
            await asyncio.Event().wait()
        finally:
            active -= 1

    with pytest.raises(SparseEncodeError):
        await _encoder(handler, concurrency=2).aencode(["retry", "fatal", "queued"])
    assert backoff_stopped.is_set()
    assert sent.count("retry") == 1
    assert active == 0


def test_factory_reads_explicit_policy_and_rejects_unknown_constructor_policy():
    from linkrag_eval.config import EvalSettings

    settings = EvalSettings(
        _env_file=None, sparse_api_key="fixture", sparse_model="fixture",
        sparse_input_length_policy="prefix_on_length_error",
    )
    assert build_sparse_encoder(settings).input_length_policy == "prefix_on_length_error"
    with pytest.raises(SparseEncodeError, match="input_length_policy") as error:
        ArkSparseEncoder(api_key="fixture", model="fixture", input_length_policy="truncate")
    assert error.value.reason == "configuration"
    assert error.value.status_code is None


@pytest.mark.parametrize("status", [200, 201])
async def test_non_json_response_keeps_status_without_exposing_response(status):
    sent = []

    def handler(request):
        sent.append(_text(request))
        return httpx.Response(status, text="private-response-canary")

    with pytest.raises(SparseEncodeError) as error:
        await _encoder(handler).aencode(["private-input-canary"])
    assert error.value.reason == "invalid_json"
    assert error.value.status_code == status
    assert isinstance(error.value.__cause__, ValueError)
    assert sent == ["private-input-canary"]
    assert "canary" not in str(error.value)


@pytest.mark.parametrize("body,reason,cause_type", [
    (["private-response-canary"], "invalid_response_schema", None),
    ({"data": "private-response-canary"}, "invalid_response_schema", None),
    ({"data": {"sparse_embedding": "private-response-canary"}}, "invalid_response_schema", None),
    ({"data": {"sparse_embedding": ["private-response-canary"]}}, "invalid_sparse_item", None),
    ({"data": {"sparse_embedding": [{"index": "private-response-canary"}]}},
     "invalid_sparse_item", None),
    ({"data": {"sparse_embedding": [{"index": "private-response-canary", "value": 1}]}},
     "invalid_sparse_item", "ValueError"),
    ({"data": {"sparse_embedding": [{"index": 1, "value": "private-response-canary"}]}},
     "invalid_sparse_item", "ValueError"),
    ({"data": {"sparse_embedding": [{"index": -1, "value": 1}]}},
     "invalid_sparse_item", "SparseCleaningError"),
    ({"data": {"sparse_embedding": [{"index": 1, "value": "nan"}]}},
     "invalid_sparse_item", "SparseCleaningError"),
    ({"data": {"sparse_embedding": []}}, "invalid_sparse_item", "SparseCleaningError"),
])
async def test_invalid_response_keeps_status_and_safe_reason_without_retry(body, reason, cause_type):
    sent = []

    def handler(request):
        sent.append(_text(request))
        return httpx.Response(200, json=body)

    with pytest.raises(SparseEncodeError) as error:
        await _encoder(handler).aencode(["private-input-canary"])
    assert error.value.reason == reason
    assert error.value.reason in SAFE_SPARSE_FAILURE_REASONS
    assert error.value.status_code == 200
    if cause_type is None:
        assert error.value.__cause__ is None
    else:
        assert type(error.value.__cause__).__name__ == cause_type
    assert sent == ["private-input-canary"]
    assert "canary" not in str(error.value)


@pytest.mark.parametrize("status", [400, 403])
async def test_http_rejection_keeps_only_safe_metadata_without_retry_or_shortening(status):
    sent = []

    def handler(request):
        sent.append(_text(request))
        return httpx.Response(status, json={"error": {
            "code": "private-provider-code-canary",
            "message": "private-response-canary",
        }})

    encoder = ArkSparseEncoder(
        api_key="private-key-canary", model="private-model-canary",
        base_url="https://private-endpoint-canary.invalid/embeddings",
        input_length_policy="prefix_on_length_error", http_client=_mock_client(handler),
    )
    try:
        with pytest.raises(SparseEncodeError) as error:
            await encoder.aencode(["private-input-canary"])
    finally:
        await encoder.aclose()
    assert error.value.reason == "http_error"
    assert error.value.status_code == status
    assert sent == ["private-input-canary"]
    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    assert "canary" not in str(error.value)
    assert "canary" not in json.dumps(vars(error.value))


@pytest.mark.parametrize("status,code,reason", [
    (403, "AccountOverdueError", "account_overdue"),
    (400, "AccountOverdueError", "http_error"),
    (403, "accountoverdueerror", "http_error"),
])
async def test_only_exact_403_account_overdue_code_has_specific_reason(status, code, reason):
    sent = []

    def handler(request):
        sent.append(_text(request))
        return httpx.Response(status, json={"error": {
            "code": code, "message": "private-response-canary",
        }})

    with pytest.raises(SparseEncodeError) as error:
        await _encoder(handler).aencode(["private-input-canary"])
    assert error.value.reason == reason
    assert error.value.status_code == status
    assert sent == ["private-input-canary"]
    assert "canary" not in str(error.value)
    assert "canary" not in json.dumps(vars(error.value))
    assert code not in json.dumps(vars(error.value))


async def test_concurrent_requests_keep_their_own_http_status(monkeypatch):
    response_received = asyncio.Event()
    rejection_finished = asyncio.Event()
    sent = []

    def handler(request):
        text = _text(request)
        sent.append(text)
        return httpx.Response(200 if text == "schema" else 403, json={})

    encoder = _encoder(handler)
    original_post = encoder._post

    async def interleaved_post(payload, attempt=0):
        if payload["input"][0]["text"] == "schema":
            result = await original_post(payload, attempt)
            response_received.set()
            # 让另一请求先报 403，再解析这一请求的成功 HTTP 响应。
            await rejection_finished.wait()
            return result
        await response_received.wait()
        try:
            return await original_post(payload, attempt)
        finally:
            rejection_finished.set()

    monkeypatch.setattr(encoder, "_post", interleaved_post)
    try:
        schema_error, http_error = await asyncio.wait_for(asyncio.gather(
            encoder.aencode(["schema"]), encoder.aencode(["forbidden"]), return_exceptions=True
        ), timeout=1)
    finally:
        await encoder.aclose()
    assert isinstance(schema_error, SparseEncodeError)
    assert (schema_error.status_code, schema_error.reason) == (200, "invalid_response_schema")
    assert isinstance(http_error, SparseEncodeError)
    assert (http_error.status_code, http_error.reason) == (403, "http_error")
    assert sent == ["schema", "forbidden"]


def test_failure_reason_rejects_arbitrary_provider_text():
    assert isinstance(SAFE_SPARSE_FAILURE_REASONS, frozenset)
    with pytest.raises(ValueError) as error:
        SparseEncodeError("固定消息", reason="private-provider-code-canary", status_code=403)
    assert "canary" not in str(error.value)
