"""eval 自带的稀疏编码客户端(纯 httpx,config 驱动,模型可选)。

实现 :class:`~linkrag_eval.compute.protocol.SparseEncoder`:文本 → :class:`SparseVec`。
当前内置 ``ark`` provider(火山方舟 doubao-vision / 多模态端点),请求/响应口径对齐生产
``DoubaoVisionProvider``:逐条 POST ``input=[{type:text,text}]`` + ``sparse_embedding={type:enabled}``,
响应取 ``data.sparse_embedding=[{index,value},...]``,再经 :func:`normalize_lexical_weights`
清洗(同生产口径)。模型 / key / 端点全走 EVAL_SPARSE_* 配置,换模型即改配置。

零 rag import:保持本层独立。换 provider 在 :func:`build_sparse_encoder` 加分支。
"""

from __future__ import annotations

import asyncio
from typing import Sequence

import httpx

from linkrag_eval.compute.protocol import SparseVec
from linkrag_eval.llm.normalize import normalize_lexical_weights


class SparseEncodeError(RuntimeError):
    """稀疏编码失败:未配置 key、连接/超时/5xx 重试耗尽、响应非法。"""


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
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not (api_key or "").strip():
            raise SparseEncodeError("EVAL_SPARSE_API_KEY 未配置。")
        if not (model or "").strip():
            raise SparseEncodeError("EVAL_SPARSE_MODEL 未配置。")
        self._api_key = api_key
        self._model = model
        self._endpoint = (base_url or self.DEFAULT_ENDPOINT).rstrip("/")
        self._top_k = top_k
        self._min_weight = min_weight
        self._timeout_ms = timeout_ms
        self._max_retries = max_retries
        self._client = http_client

    @property
    def model_name(self) -> str:
        return self._model

    async def aencode(self, texts: Sequence[str]) -> list[SparseVec]:
        """逐条编码(多模态端点一次融合成单向量),返回与输入同序、等长的 SparseVec。"""
        if not texts:
            return []
        return [await self._encode_one(t) for t in texts]

    async def _encode_one(self, text: str) -> SparseVec:
        payload = {
            "model": self._model,
            "input": [{"type": "text", "text": text}],
            "sparse_embedding": {"type": "enabled"},
        }
        data = await self._post(payload)
        obj = data.get("data") if isinstance(data, dict) else None
        if not isinstance(obj, dict):
            raise SparseEncodeError("Ark 响应缺少 data 对象。")
        sparse = obj.get("sparse_embedding")
        if not isinstance(sparse, list):
            raise SparseEncodeError(
                "Ark 响应缺少 sparse_embedding(是否漏传 sparse_embedding={'type':'enabled'}?)。"
            )
        weights: dict[int, float] = {}
        for item in sparse:
            if not isinstance(item, dict) or "index" not in item or "value" not in item:
                raise SparseEncodeError(f"Ark sparse 项格式异常:{item!r}。")
            try:
                weights[int(item["index"])] = float(item["value"])
            except (TypeError, ValueError) as exc:
                raise SparseEncodeError(f"Ark sparse 权重非法:{item!r}。") from exc
        return normalize_lexical_weights(
            weights, top_k=self._top_k, min_weight=self._min_weight
        )

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
                await asyncio.sleep(2 * (attempt + 1))
                return await self._post(payload, attempt + 1)
            raise SparseEncodeError(f"Ark 连接失败:{type(exc).__name__}。") from exc

        if resp.status_code >= 500:
            if attempt < self._max_retries:
                await asyncio.sleep(2 * (attempt + 1))
                return await self._post(payload, attempt + 1)
            raise SparseEncodeError(f"Ark 服务端错误 {resp.status_code}。")
        if 400 <= resp.status_code < 500:
            raise SparseEncodeError(f"Ark 客户端错误 {resp.status_code}:{resp.text[:200]!r}。")
        try:
            return resp.json()
        except ValueError as exc:
            raise SparseEncodeError("Ark 返回非 JSON。") from exc

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(self._timeout_ms / 1000))
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()


def build_sparse_encoder(settings=None):
    """按 EVAL_SPARSE_* 配置装配稀疏编码器。``provider`` 选 provider,模型/端点/key 全走配置。"""
    if settings is None:
        from linkrag_eval.config import get_settings

        settings = get_settings()
    provider = (settings.sparse_provider or "ark").lower()
    if provider == "ark":
        return ArkSparseEncoder(
            api_key=settings.sparse_api_key,
            model=settings.sparse_model,
            base_url=settings.sparse_base_url,
            top_k=settings.sparse_top_k,
            min_weight=settings.sparse_min_weight,
            timeout_ms=settings.sparse_timeout_ms,
        )
    raise SparseEncodeError(f"未知 sparse provider:{provider!r}(当前内置 'ark')。")
