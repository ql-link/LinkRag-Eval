"""HTTP judge runners and offline agreement on saved pointwise scores."""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from itertools import combinations

import httpx
import numpy as np

from .llm_judge import PROMPT_VERSION, SCHEMA, judged_scores, relation


def _runtime(kind, endpoint, model, effort="none"):
    url = httpx.URL(endpoint)
    if url.scheme not in {"http", "https"} or not url.host or url.username or url.password:
        raise ValueError("endpoint must be an HTTP(S) URL without credentials")
    if not model:
        raise ValueError("local judge requires a model")
    return url, {"runner": kind, "endpoint": url.host, "model": model, "effort": effort,
                 "prompt_version": PROMPT_VERSION, "codex_version": None}


def _post(client, url, body):
    try:
        return client.post(url, json=body)
    except httpx.HTTPError as exc:
        # Do not persist request URLs, authorization headers or echoed server errors.
        raise RuntimeError(f"judge HTTP transport failed ({type(exc).__name__})") from None


def _content(response, kind):
    if not response.is_success:
        raise RuntimeError(f"judge HTTP status {response.status_code}")
    value = response.json()
    try:
        content = (value["choices"][0]["message"]["content"] if kind == "openai"
                   else value["message"]["content"])
    except (KeyError, IndexError, TypeError):
        raise ValueError("invalid judge response envelope") from None
    if not isinstance(content, str):
        raise ValueError("judge content must be a string")
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content, count=1, flags=re.IGNORECASE)
        content = re.sub(r"\s*```$", "", content, count=1)
    return json.loads(content)


class OpenAICompatRunner:
    def __init__(self, endpoint, model, api_key=None, *, timeout=600, num_ctx=8192,
                 max_tokens=None, extra_body=None, think=False, transport=None):
        # `think` toggles Qwen3-style reasoning; it gets its own effort label so
        # cache keys never collide with non-thinking runs of the same model.
        self.think = bool(think)
        self.endpoint, self.metadata = _runtime("openai", endpoint, model,
                                                "think" if self.think else "none")
        self.model, self.timeout = model, timeout
        # Generation budget must stay well below the server's context window:
        # prompt tokens + max_tokens > max-model-len is rejected by vLLM.
        self.max_tokens = (4096 if self.think else 1024) if max_tokens is None else max_tokens
        if num_ctx < 1 or self.max_tokens < 1:
            raise ValueError("num_ctx and max_tokens must be positive")
        if self.max_tokens >= num_ctx:
            raise ValueError("max_tokens must be smaller than num_ctx")
        self.extra_body = dict(extra_body or {})
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key is not None else {}
        self._transport = transport

    def run(self, prompt, out):
        body = {**self.extra_body, "model": self.model,
                "messages": [{"role": "user", "content": prompt}], "temperature": 0,
                "max_tokens": self.max_tokens,
                "response_format": {"type": "json_schema", "json_schema": {
                    "name": "judge", "schema": SCHEMA, "strict": True}},
                "chat_template_kwargs": {**self.extra_body.get("chat_template_kwargs", {}),
                                         "enable_thinking": self.think}}
        url = self.endpoint.copy_with(path=self.endpoint.path.rstrip("/") + "/v1/chat/completions")
        with httpx.Client(timeout=self.timeout, headers=self._headers, transport=self._transport) as client:
            response = _post(client, url, body)
            if response.status_code == 400 and "response_format" in response.text.lower():
                body.pop("response_format")
                response = _post(client, url, body)
            return _content(response, "openai")


class OllamaRunner:
    def __init__(self, endpoint, model, num_ctx=8192, *, timeout=600, transport=None):
        self.endpoint, self.metadata = _runtime("ollama", endpoint, model)
        if num_ctx < 1:
            raise ValueError("num_ctx must be positive")
        self.model, self.num_ctx, self.timeout = model, num_ctx, timeout
        self._transport = transport

    def run(self, prompt, out):
        body = {"model": self.model, "messages": [{"role": "user", "content": prompt}],
                "stream": False, "format": SCHEMA, "think": False,
                "options": {"temperature": 0, "num_ctx": self.num_ctx}}
        url = self.endpoint.copy_with(path=self.endpoint.path.rstrip("/") + "/api/chat")
        with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
            return _content(_post(client, url, body), "ollama")


def _correlations(matrix):
    """Average-rank Spearman and tie-corrected Kendall tau-b from a 5x5 table."""
    n = int(matrix.sum())
    if n < 2:
        return None, None
    a, b = matrix.sum(axis=1), matrix.sum(axis=0)
    ranks_a = a.cumsum() - (a - 1) / 2 - (n + 1) / 2
    ranks_b = b.cumsum() - (b - 1) / 2 - (n + 1) / 2
    denominator = math.sqrt(float((a * ranks_a ** 2).sum() * (b * ranks_b ** 2).sum()))
    spearman = float(ranks_a @ matrix @ ranks_b) / denominator if denominator else None
    concordant = sum(int(matrix[i, j]) * int(matrix[i + 1:, j + 1:].sum())
                     for i in range(5) for j in range(5))
    discordant = sum(int(matrix[i, j]) * int(matrix[i + 1:, :j].sum())
                    for i in range(5) for j in range(5))
    pairs = n * (n - 1) // 2
    denominator = math.sqrt((pairs - int((a * (a - 1) // 2).sum())) *
                            (pairs - int((b * (b - 1) // 2).sum())))
    kendall = (concordant - discordant) / denominator if denominator else None
    return spearman, kendall


def agreement_report(rows_a, rows_b):
    """Compare shared (query, chunk) IDs; unavailable scores never count as agreement.

    Pair directions compare all shared unordered candidate pairs within each query
    and pair_id, in chunk-ID order (no gold preference is inferred).
    """
    judged_scores(rows_a)
    judged_scores(rows_b)
    a, b = ({(r["source_query_id"], r["chunk_id"]): r for r in rows}
            for rows in (rows_a, rows_b))
    shared = sorted(a.keys() & b.keys())
    matrix = np.zeros((5, 5), dtype=np.int64)
    groups = defaultdict(list)
    for key in shared:
        if any(a[key].get(field) != b[key].get(field) for field in ("pair_id", "query", "passage")):
            raise ValueError("shared judge item has conflicting pair/text")
        groups[(a[key]["pair_id"], key[0])].append(key)
        x, y = a[key]["score"], b[key]["score"]
        if x is not None and y is not None:
            matrix[x, y] += 1
    n = int(matrix.sum())
    spearman, kendall = _correlations(matrix)
    n_pairs = n_scored_pairs = same_direction = 0
    for keys in groups.values():
        for left, right in combinations(keys, 2):
            n_pairs += 1
            ra = relation(a[left]["score"], a[right]["score"])
            rb = relation(b[left]["score"], b[right]["score"])
            if "unavailable" not in (ra, rb):
                n_scored_pairs += 1
                same_direction += ra == rb
    return {"n_shared": len(shared), "n_scored": n,
            "exact_agreement": int(np.trace(matrix)) / n if n else None,
            "within_1_agreement": sum(int(matrix[i, j]) for i in range(5) for j in range(5)
                                      if abs(i - j) <= 1) / n if n else None,
            "spearman": spearman, "kendall_tau": kendall,
            "confusion_matrix": matrix.tolist(), "n_shared_pairs": n_pairs,
            "n_scored_pairs": n_scored_pairs,
            "pairwise_direction_agreement": same_direction / n_scored_pairs if n_scored_pairs else None}
