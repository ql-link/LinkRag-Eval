"""eval 自带的 dense 编码客户端(纯 httpx,config 驱动,模型可选)。

实现 :class:`~linkrag_eval.compute.protocol.DenseEncoder`:文本 → 稠密向量。OpenAI 兼容
``/embeddings`` 口径(对齐生产系统 embedder:base + ``/embeddings``,payload ``{model, input:[...]}``,
响应 ``data[i].embedding``),模型/key/端点/维度全走 EVAL_EMBED_* 配置。

写入侧(compute_dense)与召回 query 侧**必须共用本编码器同一实例口径**——否则两侧向量空间
不一致、recall 分数失真(decoupling-plan 风险 C)。零 rag import。
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from typing import Literal

import httpx

from linkrag_eval.compute.protocol import DenseVec


class DenseEncodeError(RuntimeError):
    """dense 编码失败:未配置 key/model、连接/超时/5xx 重试耗尽、响应非法。"""


class DenseInputLengthError(DenseEncodeError):
    """当前端点明确拒绝输入长度；报告范围不作为本地 token 计数契约。"""

    def __init__(self, reported_limit: int) -> None:
        self.reported_limit = reported_limit
        super().__init__(f"embeddings 服务拒绝输入长度，报告范围上限为 {reported_limit}。")


def _reported_length_limit(response: httpx.Response) -> int | None:
    """只识别已经实测的 HTTP 400 / InvalidParameter 长度错误结构。"""
    if response.status_code != 400:
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict) or (
        error.get("code") != "InvalidParameter"
        or error.get("type") != "InvalidParameter"
        or "param" not in error
        or error.get("param") is not None
        or not isinstance(error.get("message"), str)
    ):
        return None
    match = re.fullmatch(
        r"<400> InternalError\.Algo\.InvalidParameter: "
        r"Range of input length should be \[1, ([1-9][0-9]*)\]",
        error["message"],
    )
    return int(match[1]) if match else None


class OpenAIDenseEmbedder:
    """OpenAI 兼容 /embeddings 稠密编码器(对齐生产系统 embedder 口径)。"""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        dim: int = 1024,
        batch_size: int = 10,
        concurrency: int = 4,
        timeout_ms: int = 60000,
        max_retries: int = 3,
        input_length_policy: Literal["reject", "prefix_on_length_error"] = "reject",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not (api_key or "").strip():
            raise DenseEncodeError("EVAL_EMBED_API_KEY 未配置。")
        if not (model or "").strip():
            raise DenseEncodeError("EVAL_EMBED_MODEL 未配置。")
        if not (base_url or "").strip():
            raise DenseEncodeError("EVAL_EMBED_BASE_URL 未配置。")
        if input_length_policy not in {"reject", "prefix_on_length_error"}:
            raise DenseEncodeError("不支持的 Dense 输入长度策略。")
        self._api_key = api_key
        self._model = model
        # base 自动补 /embeddings(已带则不重复)
        b = base_url.rstrip("/")
        self._endpoint = b if b.endswith("/embeddings") else f"{b}/embeddings"
        self._dim = dim
        self._batch_size = max(1, batch_size)
        self._concurrency = max(1, concurrency)
        self._timeout_ms = timeout_ms
        self._max_retries = max_retries
        self._input_length_policy = input_length_policy
        self._client = http_client

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def input_length_policy(self) -> str:
        return self._input_length_policy

    # —— 生产召回 facade 期望的属性形状(被当 resolved embedding_pipeline 用)——
    @property
    def embedding_model(self) -> str:
        """facade.search_dense 读 ``embedding_pipeline.embedding_model`` 上报用量。"""
        return self._model

    @property
    def embedder(self):
        """facade 读 ``embedding_pipeline.embedder.provider_type``(getattr 容错);返回 self 即可。"""
        return self

    async def aembed(self, texts: Sequence[str]) -> list[list[float]]:
        """批量编码；沿用 detailed 入口的同一发送策略，只返回向量值。"""
        return [vector.values for vector in await self.aembed_with_metadata(texts)]

    async def aembed_with_metadata(self, texts: Sequence[str]) -> list[DenseVec]:
        """返回向量及成功发送的字符数；原始输入不变，不推断服务端内部处理。"""
        items = list(texts)
        if not items:
            return []
        batches = [items[start : start + self._batch_size] for start in range(0, len(items), self._batch_size)]
        semaphore = asyncio.Semaphore(self._concurrency)

        async def encode(batch: list[str]) -> list[DenseVec]:
            async with semaphore:
                return await self._embed_batch(batch)

        tasks = [asyncio.create_task(encode(batch)) for batch in batches]
        try:
            encoded = await asyncio.gather(*tasks)
        except BaseException:
            # 单批失败或调用方取消后，不能遗留兄弟任务继续发出模型请求。
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        return [vector for batch in encoded for vector in batch]

    async def aembed_query(self, text: str) -> list[float]:
        """单条 query 编码(召回侧用)。"""
        [vec] = await self.aembed([text])
        return vec

    async def aembed_query_detailed(self, text: str) -> tuple[list[float], None]:
        """召回 facade 期望的 query 编码口径:返回 (向量, usage)。

        生产 ``search_dense_chunks`` 调 ``embedding_pipeline.aembed_query_detailed``;eval 注入
        本编码器当 resolver 结果,故需此方法。usage 不上报,返回 None。
        """
        return await self.aembed_query(text), None

    async def _embed_batch(self, batch: list[str]) -> list[DenseVec]:
        working = batch
        while True:
            try:
                return await self._request_batch(working)
            except DenseInputLengthError:
                if self._input_length_policy == "reject":
                    raise
                if len(working) > 1:
                    # 批错误没有给出超长项位置；每条先原样发送，避免连带截短短文本。
                    vectors = []
                    for text in working:
                        vectors.extend(await self._embed_batch([text]))
                    return vectors
                text = working[0]
                if len(text) <= 1:
                    raise
                # 仅缩短网络传输副本；每次严格减半，到单字符仍拒绝则上抛。
                working = [text[:len(text) // 2]]

    async def _request_batch(self, batch: list[str]) -> list[DenseVec]:
        data = await self._post({"model": self._model, "input": batch})
        rows = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list) or len(rows) != len(batch):
            raise DenseEncodeError(
                f"embeddings 响应 data 数量不符:got {len(rows) if isinstance(rows, list) else 'N/A'}, "
                f"expected {len(batch)}。"
            )
        # 字符数须与同一输入的向量对应；当前 OpenAI 接口要求完整且唯一的 index。
        if not all(isinstance(row, dict) and type(row.get("index")) is int for row in rows):
            raise DenseEncodeError("embeddings 响应缺少有效输入 index。")
        if sorted(row["index"] for row in rows) != list(range(len(batch))):
            raise DenseEncodeError("embeddings 响应 index 重复或与输入不对应。")
        rows_sorted = sorted(rows, key=lambda row: row["index"])
        vecs: list[DenseVec] = []
        for r, text in zip(rows_sorted, batch, strict=True):
            emb = r.get("embedding") if isinstance(r, dict) else None
            if not isinstance(emb, list) or not emb:
                raise DenseEncodeError("embeddings 项缺少有效 embedding。")
            vecs.append(DenseVec(values=[float(x) for x in emb], input_chars=len(text)))
        return vecs

    async def _post(self, payload: dict, attempt: int = 0) -> dict:
        client = await self._get_client()
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = await client.post(self._endpoint, json=payload, headers=headers)
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            if attempt < self._max_retries:
                import asyncio

                await asyncio.sleep(2 * (attempt + 1))
                return await self._post(payload, attempt + 1)
            raise DenseEncodeError(f"embeddings 连接失败:{type(exc).__name__}。") from exc

        if resp.status_code in {408, 429} or resp.status_code >= 500:
            if attempt < self._max_retries:
                import asyncio

                await asyncio.sleep(2 * (attempt + 1))
                return await self._post(payload, attempt + 1)
            raise DenseEncodeError(f"embeddings 服务端错误 {resp.status_code}。")
        if 400 <= resp.status_code < 500:
            reported_limit = _reported_length_limit(resp)
            if reported_limit is not None:
                raise DenseInputLengthError(reported_limit)
            raise DenseEncodeError(f"embeddings 客户端错误 {resp.status_code}。")
        try:
            return resp.json()
        except ValueError as exc:
            raise DenseEncodeError("embeddings 返回非 JSON。") from exc

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(self._timeout_ms / 1000))
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()


def build_dense_embedder(settings=None) -> OpenAIDenseEmbedder:
    """按 EVAL_EMBED_* 配置装配 dense 编码器。"""
    if settings is None:
        from linkrag_eval.config import get_settings

        settings = get_settings()
    return OpenAIDenseEmbedder(
        api_key=settings.embed_api_key,
        model=settings.embed_model,
        base_url=settings.embed_base_url,
        dim=settings.embed_dim,
        batch_size=settings.embed_batch_size,
        concurrency=settings.embed_concurrency,
        timeout_ms=settings.embed_timeout_ms,
        input_length_policy=settings.embed_input_length_policy,
    )


def build_alt_dense_embedder(settings=None):
    """按 EVAL_ALT_EMBED_* 配置装配候选池 alt embedding 编码器。"""
    if settings is None:
        from linkrag_eval.config import get_settings

        settings = get_settings()
    if not (settings.alt_embed_api_key or "").strip():
        raise DenseEncodeError("EVAL_ALT_EMBED_API_KEY 未配置。")
    if not (settings.alt_embed_model or "").strip():
        raise DenseEncodeError("EVAL_ALT_EMBED_MODEL 未配置。")
    if not (settings.alt_embed_base_url or "").strip():
        raise DenseEncodeError("EVAL_ALT_EMBED_BASE_URL 未配置。")
    return OpenAIDenseEmbedder(
        api_key=settings.alt_embed_api_key,
        model=settings.alt_embed_model,
        base_url=settings.alt_embed_base_url,
        dim=settings.alt_embed_dim,
        batch_size=settings.alt_embed_batch_size,
        timeout_ms=settings.alt_embed_timeout_ms,
    )
