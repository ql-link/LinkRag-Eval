"""eval 自持的标准 rerank HTTP 客户端。

接口兼容 Jina/Cohere/SiliconFlow 等 ``POST /rerank``：输入 query 与 documents，返回每个
输入文档的原始下标和相关性分数。它只读取 ``EVAL_RERANK_*``，不解析生产用户模型配置，
也不访问生产数据库。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Sequence

import httpx


class RerankError(RuntimeError):
    """rerank 未配置、调用失败或响应不符合标准协议。"""


@dataclass(frozen=True)
class RerankScore:
    """一个输入候选的 rerank 分数。``index`` 对应传入 documents 的下标。"""

    index: int
    score: float


class StandardRerankClient:
    """标准 ``/rerank`` 协议客户端，保留所有返回项以便本地统一截断。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        provider: str = "standard",
        timeout_ms: int = 60000,
        max_document_chars: int = 1200,
        max_retries: int = 2,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not (base_url or "").strip():
            raise RerankError("EVAL_RERANK_BASE_URL 未配置。")
        if not (api_key or "").strip():
            raise RerankError("EVAL_RERANK_API_KEY 未配置。")
        if not (model or "").strip():
            raise RerankError("EVAL_RERANK_MODEL 未配置。")
        self._provider = provider.strip().lower()
        if self._provider not in {"dashscope", "standard"}:
            raise RerankError(f"未知 rerank provider:{provider!r}。")
        base = base_url.rstrip("/")
        # 通用 Jina/Cohere 协议通常为 /rerank；百炼 qwen3-rerank 是 /reranks。
        # 允许在 EVAL_RERANK_BASE_URL 中写完整路径，避免隐式猜测 WorkspaceId 路由。
        self._endpoint = base if self._provider == "dashscope" else (
            base if base.endswith(("/rerank", "/reranks")) else f"{base}/rerank"
        )
        self._api_key = api_key
        self._model = model
        self._timeout_ms = timeout_ms
        self._max_document_chars = max(1, max_document_chars)
        self._max_retries = max(0, max_retries)
        self._client = http_client

    @property
    def model_name(self) -> str:
        return self._model

    async def rerank(self, query: str, documents: Sequence[str]) -> list[RerankScore]:
        """为全部 documents 打分，排序与候选 K 截断由上游统一掌控。"""
        docs = [str(document)[:self._max_document_chars] for document in documents]
        if not docs:
            return []
        payload = self._payload(query, docs)
        data = await self._post(payload)
        raw = self._results(data)
        if not isinstance(raw, list):
            raise RerankError("rerank 响应缺少 results 数组。")
        by_index: dict[int, float] = {}
        for item in raw:
            if not isinstance(item, dict):
                raise RerankError(f"rerank results 项格式非法:{item!r}。")
            index = item.get("index")
            score = item.get("relevance_score", item.get("score"))
            if not isinstance(index, int) or not 0 <= index < len(docs):
                raise RerankError(f"rerank 返回非法 index:{index!r}。")
            try:
                by_index[index] = float(score)
            except (TypeError, ValueError) as exc:
                raise RerankError(f"rerank 返回非法 score:{score!r}。") from exc
        if len(by_index) != len(docs):
            raise RerankError(
                f"rerank 返回项不完整:got {len(by_index)}, expected {len(docs)}。"
            )
        return [RerankScore(index=index, score=score) for index, score in by_index.items()]

    def _payload(self, query: str, documents: list[str]) -> dict[str, Any]:
        if self._provider == "dashscope":
            return {
                "model": self._model,
                "input": {"query": query, "documents": documents},
                "parameters": {"return_documents": False},
            }
        return {
            "model": self._model,
            "query": query,
            "documents": documents,
            "return_documents": False,
        }

    def _results(self, data: Any) -> Any:
        if not isinstance(data, dict):
            return None
        if self._provider == "dashscope":
            output = data.get("output")
            return output.get("results") if isinstance(output, dict) else data.get("results")
        return data.get("results")

    async def _post(self, payload: dict[str, Any], attempt: int = 0) -> dict[str, Any]:
        client = await self._get_client()
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        try:
            response = await client.post(self._endpoint, json=payload, headers=headers)
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            if attempt < self._max_retries:
                await asyncio.sleep(1 + attempt)
                return await self._post(payload, attempt + 1)
            raise RerankError(f"rerank 连接失败:{type(exc).__name__}。") from exc
        if response.status_code >= 500:
            if attempt < self._max_retries:
                await asyncio.sleep(1 + attempt)
                return await self._post(payload, attempt + 1)
            raise RerankError(f"rerank 服务端错误 {response.status_code}。")
        if response.status_code >= 400:
            raise RerankError(f"rerank 客户端错误 {response.status_code}:{response.text[:200]!r}。")
        try:
            data = response.json()
        except ValueError as exc:
            raise RerankError("rerank 返回非 JSON。") from exc
        if not isinstance(data, dict):
            raise RerankError("rerank 响应根节点必须为对象。")
        return data

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(self._timeout_ms / 1000))
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()


def build_rerank_client(settings=None) -> StandardRerankClient:
    """从 eval 独立配置构造 rerank 客户端。"""
    if settings is None:
        from linkrag_eval.config import get_settings

        settings = get_settings()
    return StandardRerankClient(
        base_url=settings.rerank_base_url,
        api_key=settings.rerank_api_key,
        model=settings.rerank_model,
        provider=settings.rerank_provider,
        timeout_ms=settings.rerank_timeout_ms,
        max_document_chars=settings.rerank_max_document_chars,
    )
