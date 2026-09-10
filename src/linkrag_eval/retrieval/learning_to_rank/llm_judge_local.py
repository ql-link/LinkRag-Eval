"""HTTP judge runners and offline agreement on saved pointwise scores."""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from itertools import combinations

import httpx
import numpy as np

from .llm_judge import PROMPT_VERSION, SCHEMA, judged_scores, relation


def probe_items(fixture: dict) -> list[dict]:
    """Expand probe pools into L1 items; labels stay outside the judge prompt."""
    items = []
    query_ids, pair_ids, document_ids = set(), set(), set()

    def documents(rows, id_field):
        docs = {}
        for row in rows:
            cid = row[id_field]
            if not isinstance(cid, str) or not cid or cid in document_ids:
                raise ValueError("empty or duplicate probe document ID")
            document_ids.add(cid)
            docs[cid] = row["text"]
        if len(docs) < 2:
            raise ValueError("probe pool requires at least two documents")
        return docs

    def expand(query, docs, pair_id, probe_set, kind):
        qid = query["id"]
        if not isinstance(qid, str) or not qid or qid in query_ids:
            raise ValueError("empty or duplicate probe query ID")
        query_ids.add(qid)
        if query["expected_doc_id"] not in docs:
            raise ValueError("expected probe document is outside its pool")
        for cid, text in docs.items():
            items.append({"source_query_id": qid, "chunk_id": cid, "pair_id": pair_id,
                          "query": query["query"], "passage": text, "level": "l1",
                          "prompt_version": PROMPT_VERSION, "model": None, "effort": None,
                          "codex_version": None, "expected": cid == query["expected_doc_id"],
                          "probe_set": probe_set, "kind": kind})

    english = fixture["english"]
    docs = documents(english["docs"], "id")
    if not english["queries"]:
        raise ValueError("English probe requires queries")
    for query in english["queries"]:
        expand(query, docs, query["id"], "english", query["kind"])
    for pair in fixture["chinese"]["pairs"]:
        pid = pair["pair_id"]
        if not isinstance(pid, str) or not pid or pid in pair_ids:
            raise ValueError("empty or duplicate Chinese pair ID")
        pair_ids.add(pid)
        if len(pair["queries"]) != 2 or len(pair["passages"]) != 2:
            raise ValueError("Chinese pair requires two queries and two passages")
        docs = documents(pair["passages"], "doc_id")
        for query in pair["queries"]:
            expand(query, docs, pid + "-" + query["id"], "chinese", pair["kind"])
    _probe_groups(items)
    return items


def _probe_groups(items):
    groups, pairs = defaultdict(list), defaultdict(list)
    keys = set()
    for item in items:
        key = (item["source_query_id"], item["chunk_id"])
        if key in keys:
            raise ValueError("duplicate probe item")
        keys.add(key)
        if (item["probe_set"] not in {"english", "chinese"}
                or item["level"] != "l1" or type(item["expected"]) is not bool
                or any(not isinstance(item[k], str) or not item[k].strip() for k in
                       ("source_query_id", "chunk_id", "pair_id", "query", "passage", "kind"))):
            raise ValueError("invalid probe item metadata")
        groups[key[0]].append(item)
    if not groups:
        raise ValueError("empty probe items")
    english_pool = None
    for qid, rows in groups.items():
        first = rows[0]
        if (len(rows) < 2 or sum(r["expected"] for r in rows) != 1
                or any(r[k] != first[k] for r in rows for k in
                       ("query", "pair_id", "probe_set", "kind"))):
            raise ValueError("probe query requires one target and a consistent candidate pool")
        pool = {r["chunk_id"]: r["passage"] for r in rows}
        if first["probe_set"] == "english":
            if first["pair_id"] != qid or (english_pool is not None and pool != english_pool):
                raise ValueError("English probe requires query pair IDs and a shared pool")
            english_pool = pool
        else:
            suffix = "-" + qid
            if len(rows) != 2 or not first["pair_id"].endswith(suffix):
                raise ValueError("invalid Chinese directional pair ID or pool")
            pid = first["pair_id"][:-len(suffix)]
            if not pid:
                raise ValueError("empty Chinese pair ID")
            pairs[pid].append(qid)
    for qids in pairs.values():
        if len(qids) != 2:
            raise ValueError("Chinese pair requires both query directions")
        a, b = (groups[qid] for qid in qids)
        if (a[0]["kind"] != b[0]["kind"]
                or {r["chunk_id"]: r["passage"] for r in a}
                != {r["chunk_id"]: r["passage"] for r in b}
                or next(r["chunk_id"] for r in a if r["expected"])
                == next(r["chunk_id"] for r in b if r["expected"])):
            raise ValueError("Chinese directions require the same pool and opposite targets")
    return groups, pairs


def probe_evaluate(items: list[dict], scores: list[dict]) -> dict:
    """Evaluate exact saved pools; ties and unavailable queries are never wins.

    Rank is competition rank (1 + candidates scoring higher); rank_worst also
    counts candidates tied with the target. Incomplete scores yield null ranks.
    Accuracy denominators include unavailable queries/pairs, reported separately.
    """
    groups, pairs = _probe_groups(items)
    judged_scores(scores)
    indexed = {(r["source_query_id"], r["chunk_id"]): r for r in scores}
    if set(indexed) != {(r["source_query_id"], r["chunk_id"]) for r in items}:
        raise ValueError("probe scores must cover exactly the items, including unavailable rows")
    for item in items:
        saved = indexed[(item["source_query_id"], item["chunk_id"])]
        if any(saved.get(k) != item[k] for k in
               ("pair_id", "query", "passage", "level", "expected", "probe_set", "kind")):
            raise ValueError("probe scores contain conflicting item text or metadata")
    queries = []
    for qid, rows in groups.items():
        target = next(r for r in rows if r["expected"])
        values = {r["chunk_id"]: indexed[(qid, r["chunk_id"])]["score"] for r in rows}
        value = values[target["chunk_id"]]
        missing = sum(v is None for v in values.values())
        rank = worst = None
        outcome = "unavailable"
        if not missing:
            rank = 1 + sum(v > value for v in values.values())
            worst = sum(v >= value for v in values.values())
            outcome = "reverse" if rank > 1 else "tie" if worst > 1 else "strict"
        queries.append({"source_query_id": qid, "pair_id": target["pair_id"],
                        "probe_set": target["probe_set"], "kind": target["kind"],
                        "expected_doc_id": target["chunk_id"], "candidate_count": len(rows),
                        "expected_score": value, "expected_rank": rank,
                        "expected_rank_worst": worst, "outcome": outcome,
                        "strict_correct": outcome == "strict", "n_unavailable": missing})
    by_query = {r["source_query_id"]: r for r in queries}
    pair_results = []
    for pid, qids in pairs.items():
        directions = [by_query[qid] for qid in qids]
        pair_results.append({"pair_id": pid, "probe_set": "chinese",
                             "kind": directions[0]["kind"], "source_query_ids": qids,
                             "available": all(r["outcome"] != "unavailable" for r in directions),
                             "both_directions_correct": all(r["strict_correct"] for r in directions)})

    def aggregate(rows, pair_rows):
        counts = Counter(r["outcome"] for r in rows)
        both = sum(r["both_directions_correct"] for r in pair_rows)
        return {"n_queries": len(rows), "n_scored_queries": len(rows) - counts["unavailable"],
                **{k: counts[k] for k in ("strict", "reverse", "tie", "unavailable")},
                "strict_accuracy": counts["strict"] / len(rows),
                "n_pairs": len(pair_rows), "n_scored_pairs": sum(r["available"] for r in pair_rows),
                "both_directions_correct": both,
                "both_directions_accuracy": both / len(pair_rows) if pair_rows else None}

    def breakdown(field):
        return {key: aggregate([r for r in queries if r[field] == key],
                               [r for r in pair_results if r[field] == key])
                for key in sorted({r[field] for r in queries})}

    return {"queries": queries, "pairs": pair_results,
            "by_probe_set": breakdown("probe_set"), "by_kind": breakdown("kind"),
            "policy": {"rank": "competition rank; rank_worst includes ties with the target",
                       "unavailable": "null ranks; not correct; retained in accuracy denominators",
                       "strict": "expected score is greater than every other candidate score"}}


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
    if not isinstance(content, str):  # non-string content is an invalid envelope
        content = None
    if content is None:
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
