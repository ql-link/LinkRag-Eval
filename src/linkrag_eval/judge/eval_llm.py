"""评测专用 LLM 客户端(judge / 生成 / 分类用)。

**为什么独立于生产 LLM 解析链**:judge 是评测的"测量仪器",不是被测对象。把它绑在
生产的 ``aresolve_user_model → llm_user_config(DB) → provider 工厂 → capability 门禁``
整条链上有三个坏处:(1) 生产改模型解析方式就会拖垮评测(dev 合并把 sparse 改 per-user、
protocol 变必填即是前车之鉴);(2) 仅为调一个 mimo 端点却背上共享 MySQL 依赖与连接池竞争
(1040 Too-many-connections 的来源之一);(3) 每次 judge 调用都往生产 USAGE_REPORT 遥测里
灌噪声。仪器应当独立于被测物。

**边界**:本模块只服务"测量仪器"类调用(judge/生成/分类/重标)。**被测对象**——dense/sparse
编码、召回 pipeline、rerank——必须继续走生产装配(那才是评测正在测量的东西),不在此处。
零 rag import。

**配置**:经 EvalSettings(``EVAL_JUDGE_*``,见 .env.eval)装配,亦可显式传参覆盖:
  - ``EVAL_JUDGE_BASE_URL``    完整 chat completions 端点(如 ``.../v1/chat/completions``)
  - ``EVAL_JUDGE_API_KEY``     端点密钥
  - ``EVAL_JUDGE_MODEL``       模型名(如 ``mimo-v2.5-pro``)
  - ``EVAL_JUDGE_TIMEOUT_S``   单次请求超时秒数(默认 90,推理模型偏慢)
  - ``EVAL_JUDGE_MAX_RETRIES`` 瞬时错误最大重试次数(默认 6)
  - ``EVAL_JUDGE_CONCURRENCY`` 并发上限(默认 6;mimo 端点限流偏低)

调用面:
  ``client = build_eval_chat_client()``        # 从 EvalSettings 装配
  ``result = await client.generate(prompt=, system_prompt=, temperature=, max_tokens=)``
  ``text = result.content``
另提供 ``await client.generate_json(...)``:generate + parse_llm_json,失败返回 None。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx


class EvalLLMConfigError(RuntimeError):
    """judge 端点未配置(缺 base_url / api_key / model)。"""


@dataclass(frozen=True)
class EvalChatResult:
    """对齐生产 GenerateResult 的最小面:脚本只取 ``.content``。"""

    content: str
    model: str
    raw: dict[str, Any]


class EvalChatClient:
    """OpenAI 协议 chat completions 薄客户端:内建重试/退避/限流/超时/JSON 解析。

    mimo、doubao 等评测用端点均为 OpenAI 兼容协议,故无需生产 provider 抽象,
    一个 httpx 封装即可。``base_url`` 当作**完整端点 URL**(与生产 openai provider
    约定一致,不再拼 ``/chat/completions`` 后缀)。
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_s: float = 90.0,
        max_retries: int = 6,
        concurrency: int = 6,
        http_client: httpx.AsyncClient | None = None,
    ):
        if not base_url or not model:
            raise EvalLLMConfigError(
                "EVAL_JUDGE_BASE_URL / EVAL_JUDGE_MODEL 未配置;请在 .env.eval 中补齐。"
            )
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self._sem = asyncio.Semaphore(concurrency)
        self._http: httpx.AsyncClient | None = http_client

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_s),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
        return self._http

    async def aclose(self) -> None:
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()

    async def generate(
        self,
        *,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> EvalChatResult:
        """单轮生成。瞬时错误(429 / 5xx / 超时 / 连接)内部指数退避重试;
        重试耗尽或 4xx(鉴权/请求错误)抛异常,由调用方决定是否容错。

        并发受本客户端的信号量约束——脚本不必再各自管 semaphore。
        """
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_exc: Exception | None = None
        async with self._sem:
            for attempt in range(self.max_retries + 1):
                try:
                    client = await self._client()
                    resp = await client.post(self.base_url, json=payload, headers=headers)
                    if resp.status_code == 429 or resp.status_code >= 500:
                        # 瞬时:限流 / 服务端错误 → 退避重试
                        raise _Transient(f"HTTP {resp.status_code}")
                    resp.raise_for_status()  # 4xx(含 401)→ 硬失败,不重试
                    data = resp.json()
                    content = (
                        (data.get("choices") or [{}])[0].get("message", {}).get("content")
                        or ""
                    )
                    return EvalChatResult(content=content, model=self.model, raw=data)
                except (_Transient, httpx.TimeoutException, httpx.ConnectError) as exc:
                    last_exc = exc
                    if attempt == self.max_retries:
                        break
                    # 3/6/12/24/30/30… 秒,封顶 30s
                    await asyncio.sleep(min(30.0, 3.0 * 2**attempt))
        raise ProviderUnavailable(
            f"eval judge 调用失败(重试 {self.max_retries} 次后):{last_exc}"
        ) from last_exc

    async def generate_json(
        self,
        *,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> dict[str, Any] | None:
        """generate + parse_llm_json:返回解析后的 dict,无法解析或调用失败返回 None。"""
        from linkrag_eval.judge.json_parse import parse_llm_json

        result = await self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return parse_llm_json(result.content or "")


class _Transient(Exception):
    """内部信号:可重试的瞬时错误(429 / 5xx)。"""


class ProviderUnavailable(RuntimeError):
    """重试耗尽,端点仍不可用。"""


def build_eval_chat_client(settings=None) -> EvalChatClient:
    """从 EvalSettings(``EVAL_JUDGE_*``)装配评测 judge 客户端。

    缺 base_url / model 抛 EvalLLMConfigError。
    """
    if settings is None:
        from linkrag_eval.config import get_settings

        settings = get_settings()
    return EvalChatClient(
        base_url=settings.judge_base_url,
        api_key=settings.judge_api_key,
        model=settings.judge_model,
        timeout_s=settings.judge_timeout_s,
        max_retries=settings.judge_max_retries,
        concurrency=settings.judge_concurrency,
    )
