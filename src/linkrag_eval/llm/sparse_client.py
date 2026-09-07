"""eval 自带的稀疏编码客户端(纯 httpx,config 驱动,模型可选)。

实现 :class:`~linkrag_eval.compute.protocol.SparseEncoder`:文本 → :class:`SparseVec`。
当前内置 ``ark`` provider(火山方舟 doubao-vision / 多模态端点),请求/响应口径对齐生产
``DoubaoVisionProvider``:逐条 POST ``input=[{type:text,text}]`` + ``sparse_embedding={type:enabled}``,
响应取 ``data.sparse_embedding=[{index,value},...]``,再经 :func:`normalize_lexical_weights`
清洗(同生产口径)。模型 / key / 端点全走 EVAL_SPARSE_* 配置,换模型即改配置。

零 rag import，运行配置只接受当前 Ark 接口。
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from dataclasses import replace
from typing import Literal

import httpx

from linkrag_eval.compute.protocol import SparseVec
from linkrag_eval.llm.normalize import SparseCleaningError, normalize_lexical_weights

SAFE_SPARSE_FAILURE_REASONS = frozenset({
    "configuration",
    "account_overdue",
    "http_error",
    "http_retry_exhausted",
    "transport_retry_exhausted",
    "input_length_exceeded",
    "invalid_json",
    "invalid_response_schema",
    "invalid_sparse_item",
})


class SparseEncodeError(RuntimeError):
    """稀疏编码失败:未配置 key、连接/超时/5xx 重试耗尽、响应非法。"""

    def __init__(
        self, message: str, *, reason: str, status_code: int | None = None
    ) -> None:
        if reason not in SAFE_SPARSE_FAILURE_REASONS:
            raise ValueError("未知的 Sparse 失败分类。")
        if status_code is not None and type(status_code) is not int:
            raise ValueError("Sparse HTTP 状态必须为整数或 None。")
        self.reason = reason
        self.status_code = status_code
        super().__init__(message)


class SparseInputLengthError(SparseEncodeError):
    """当前服务明确报告输入 token 总长超限；不携带原始响应或输入。"""


_INPUT_LENGTH_MESSAGE = re.compile(
    r"total tokens of image and text exceed max message tokens\."
    r"(?:\s+request id:[^\r\n]*)?",
    flags=re.IGNORECASE,
)


def _is_input_length_error(data: object) -> bool:
    """只识别已实测的结构化长度错误，不能把普通 InvalidParameter 当成超长。"""
    error = data.get("error") if isinstance(data, dict) else None
    if not isinstance(error, dict) or error.get("code") != "InvalidParameter":
        return False
    message = error.get("message")
    return isinstance(message, str) and _INPUT_LENGTH_MESSAGE.fullmatch(message.strip()) is not None


class ArkSparseEncoder:
    """火山方舟多模态端点稀疏编码器(对齐生产 doubao_vision 口径)。"""

    DEFAULT_ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/embeddings/multimodal"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "",
        top_k: int = 256,
        min_weight: float = 0.0,
        timeout_ms: int = 60000,
        max_retries: int = 3,
        concurrency: int = 8,
        input_length_policy: Literal["reject", "prefix_on_length_error"] = "reject",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not (api_key or "").strip():
            raise SparseEncodeError("EVAL_SPARSE_API_KEY 未配置。", reason="configuration")
        if not (model or "").strip():
            raise SparseEncodeError("EVAL_SPARSE_MODEL 未配置。", reason="configuration")
        self._api_key = api_key
        self._model = model
        self._endpoint = (base_url or self.DEFAULT_ENDPOINT).rstrip("/")
        self._top_k = top_k
        self._min_weight = min_weight
        self._timeout_ms = timeout_ms
        self._max_retries = max_retries
        if input_length_policy not in {"reject", "prefix_on_length_error"}:
            raise SparseEncodeError("未知的 Sparse input_length_policy。", reason="configuration")
        self._input_length_policy = input_length_policy
        if concurrency < 1:
            raise SparseEncodeError("Ark concurrency 必须大于 0。", reason="configuration")
        self._concurrency = concurrency
        self._client = http_client

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def input_length_policy(self) -> str:
        return self._input_length_policy

    async def aencode(self, texts: Sequence[str]) -> list[SparseVec]:
        """逐条编码(多模态端点一次融合成单向量),返回与输入同序、等长的 SparseVec。"""
        if not texts:
            return []
        semaphore = asyncio.Semaphore(self._concurrency)

        async def encode(text: str) -> SparseVec:
            async with semaphore:
                return await self._encode_one(text)

        tasks = [asyncio.create_task(encode(text)) for text in texts]
        try:
            return list(await asyncio.gather(*tasks))
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    async def _encode_one(self, text: str) -> SparseVec:
        request_text = text
        while True:
            payload = {
                "model": self._model,
                "input": [{"type": "text", "text": request_text}],
                "sparse_embedding": {"type": "enabled"},
            }
            try:
                data, status_code = await self._post(payload)
                break
            except SparseInputLengthError:
                if self._input_length_policy != "prefix_on_length_error" or len(request_text) <= 1:
                    raise
                # 仅缩短本条请求副本；Unicode 码点数不是 token 上限，不改变其他文本。
                request_text = request_text[: len(request_text) // 2]
        obj = data.get("data") if isinstance(data, dict) else None
        if not isinstance(obj, dict):
            raise SparseEncodeError(
                "Ark 响应缺少 data 对象。",
                reason="invalid_response_schema", status_code=status_code,
            )
        sparse = obj.get("sparse_embedding")
        if not isinstance(sparse, list):
            raise SparseEncodeError(
                "Ark 响应缺少 sparse_embedding 列表。",
                reason="invalid_response_schema", status_code=status_code,
            )
        weights: dict[int, float] = {}
        for item in sparse:
            if not isinstance(item, dict) or "index" not in item or "value" not in item:
                raise SparseEncodeError(
                    "Ark sparse 项格式异常。",
                    reason="invalid_sparse_item", status_code=status_code,
                )
            try:
                weights[int(item["index"])] = float(item["value"])
            except (TypeError, ValueError) as exc:
                raise SparseEncodeError(
                    "Ark sparse 权重非法。",
                    reason="invalid_sparse_item", status_code=status_code,
                ) from exc
        try:
            vector = normalize_lexical_weights(
                weights, top_k=self._top_k, min_weight=self._min_weight
            )
        except SparseCleaningError as exc:
            raise SparseEncodeError(
                "Ark sparse 权重无法生成合法向量。",
                reason="invalid_sparse_item", status_code=status_code,
            ) from exc
        return replace(vector, input_chars=len(request_text))

    async def _post(self, payload: dict, attempt: int = 0) -> tuple[object, int]:
        client = await self._get_client()
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = await client.post(self._endpoint, json=payload, headers=headers)
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            if attempt < self._max_retries:
                await asyncio.sleep(2 * (attempt + 1))
                return await self._post(payload, attempt + 1)
            raise SparseEncodeError(
                "Ark 连接失败，重试耗尽。", reason="transport_retry_exhausted"
            ) from exc

        if resp.status_code in {408, 429} or resp.status_code >= 500:
            if attempt < self._max_retries:
                await asyncio.sleep(2 * (attempt + 1))
                return await self._post(payload, attempt + 1)
            raise SparseEncodeError(
                f"Ark 服务端错误 {resp.status_code}。",
                reason="http_retry_exhausted", status_code=resp.status_code,
            )
        if 400 <= resp.status_code < 500:
            try:
                error_data = resp.json()
            except ValueError:
                error_data = None
            if resp.status_code == 400 and _is_input_length_error(error_data):
                raise SparseInputLengthError(
                    "Ark 明确报告输入 token 总长超限。",
                    reason="input_length_exceeded", status_code=resp.status_code,
                )
            error = error_data.get("error") if isinstance(error_data, dict) else None
            if (
                resp.status_code == 403
                and isinstance(error, dict)
                and error.get("code") == "AccountOverdueError"
            ):
                raise SparseEncodeError(
                    "Ark 账户欠费。", reason="account_overdue", status_code=resp.status_code
                )
            raise SparseEncodeError(
                f"Ark 客户端错误 {resp.status_code}。",
                reason="http_error", status_code=resp.status_code,
            )
        try:
            return resp.json(), resp.status_code
        except ValueError as exc:
            raise SparseEncodeError(
                "Ark 返回非 JSON。", reason="invalid_json", status_code=resp.status_code
            ) from exc

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(self._timeout_ms / 1000))
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()


def build_sparse_encoder(settings=None):
    """按 EVAL_SPARSE_* 配置装配 Ark 稀疏编码器。模型/端点/key 全走配置。"""
    if settings is None:
        from linkrag_eval.config import get_settings

        settings = get_settings()
    return ArkSparseEncoder(
        api_key=settings.sparse_api_key,
        model=settings.sparse_model,
        base_url=settings.sparse_base_url,
        top_k=settings.sparse_top_k,
        min_weight=settings.sparse_min_weight,
        timeout_ms=settings.sparse_timeout_ms,
        concurrency=settings.sparse_concurrency,
        input_length_policy=settings.sparse_input_length_policy,
    )
