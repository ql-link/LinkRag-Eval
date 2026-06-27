"""eval 自带的 dense 编码客户端(纯 httpx,config 驱动,模型可选)。

实现 :class:`~linkrag_eval.compute.protocol.DenseEncoder`:文本 → 稠密向量。OpenAI 兼容
``/embeddings`` 口径(对齐生产系统 embedder:base + ``/embeddings``,payload ``{model, input:[...]}``,
响应 ``data[i].embedding``),模型/key/端点/维度全走 EVAL_EMBED_* 配置。

写入侧(compute_dense)与召回 query 侧**必须共用本编码器同一实例口径**——否则两侧向量空间
不一致、recall 分数失真(decoupling-plan 风险 C)。零 rag import。
"""

from __future__ import annotations

from typing import Sequence

import httpx


class DenseEncodeError(RuntimeError):
    """dense 编码失败:未配置 key/model、连接/超时/5xx 重试耗尽、响应非法。"""


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
        timeout_ms: int = 60000,
        max_retries: int = 3,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not (api_key or "").strip():
            raise DenseEncodeError("EVAL_EMBED_API_KEY 未配置。")
        if not (model or "").strip():
            raise DenseEncodeError("EVAL_EMBED_MODEL 未配置。")
        if not (base_url or "").strip():
            raise DenseEncodeError("EVAL_EMBED_BASE_URL 未配置。")
        self._api_key = api_key
        self._model = model
        # base 自动补 /embeddings(已带则不重复)
        b = base_url.rstrip("/")
        self._endpoint = b if b.endswith("/embeddings") else f"{b}/embeddings"
        self._dim = dim
        self._batch_size = max(1, batch_size)
        self._timeout_ms = timeout_ms
        self._max_retries = max_retries
        self._client = http_client

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dim(self) -> int:
        return self._dim

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
        """批量编码,返回与输入同序、等长的向量列表(按 batch_size 分批)。"""
        items = list(texts)
        if not items:
            return []
        out: list[list[float]] = []
        for start in range(0, len(items), self._batch_size):
            batch = items[start : start + self._batch_size]
            out.extend(await self._embed_batch(batch))
        return out

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

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        data = await self._post({"model": self._model, "input": batch})
        rows = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list) or len(rows) != len(batch):
            raise DenseEncodeError(
                f"embeddings 响应 data 数量不符:got {len(rows) if isinstance(rows, list) else 'N/A'}, "
                f"expected {len(batch)}。"
            )
        # 按 index 排序回原序(OpenAI 规范返回 index;缺省按返回序)
        rows_sorted = sorted(rows, key=lambda r: r.get("index", 0)) if all(
            isinstance(r, dict) and "index" in r for r in rows
        ) else rows
        vecs: list[list[float]] = []
        for r in rows_sorted:
            emb = r.get("embedding") if isinstance(r, dict) else None
            if not isinstance(emb, list) or not emb:
                raise DenseEncodeError(f"embeddings 项缺少 embedding:{r!r}。")
            vecs.append([float(x) for x in emb])
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

        if resp.status_code >= 500:
            if attempt < self._max_retries:
                import asyncio

                await asyncio.sleep(2 * (attempt + 1))
                return await self._post(payload, attempt + 1)
            raise DenseEncodeError(f"embeddings 服务端错误 {resp.status_code}。")
        if 400 <= resp.status_code < 500:
            raise DenseEncodeError(f"embeddings 客户端错误 {resp.status_code}:{resp.text[:200]!r}。")
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
        timeout_ms=settings.embed_timeout_ms,
    )
