"""单查询探索输入：保留完整三路候选，只关联 eval 已有正文，不消费评价标签。"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

ROUTES = ("dense", "sparse", "bm25")
CandidateKey = tuple[int, str]


def _identity(hit: Any) -> dict[str, Any]:
    return {
        "dataset_id": int(hit.dataset_id),
        "chunk_id": str(hit.chunk_id),
        "doc_id": int(hit.doc_id),
    }


def _key(row: Mapping[str, Any]) -> CandidateKey:
    return int(row["dataset_id"]), str(row["chunk_id"])


async def collect_exploration_input(
    *,
    source_query_id: str,
    query: str,
    dataset_ids: Sequence[int],
    execute_candidates: Callable[..., Awaitable[Any]],
    fetch_candidate_rows: Callable[
        [Sequence[CandidateKey]], Awaitable[Sequence[Mapping[str, Any]]]
    ],
    sample_id: str | None = None,
) -> dict[str, Any]:
    """取得一个来源查询的输入记录；由调用方负责配置绑定、抽样和文件输出。

    ``execute_candidates`` 接收原样 ``query`` 和显式 ``dataset_ids``；调用方可用
    partial 绑定 ``execute_candidate_contract_once`` 的其余参数。响应须提供当前
    ``route_hits/candidate_hits/failed_sources`` 契约，不回退到截断后的 ``hits``。
    ``fetch_candidate_rows`` 按 (dataset_id, chunk_id) 读取已有正文及来源字段。

    routes 的 rank 从 0 开始；candidate_rows 不含分数或评价标签。ready/empty
    表示完整输入，incomplete 表示已保留候选但有缺口，failed 表示请求/契约失败。
    ranking_input_ready 仅表示排序所需三路、正文及运行 ID 完整；来源映射异常
    不参与该判断。因此 overall incomplete 的查询仍可能正常运行排序。
    只记录异常类型，不把可能含凭证或正文的异常消息写入结果。无自动重试。
    """
    if not dataset_ids:
        raise ValueError("探索输入必须显式指定 dataset_ids，不能执行无范围召回")
    scope = list(dict.fromkeys(int(value) for value in dataset_ids))
    result: dict[str, Any] = {
        "sample_id": source_query_id if sample_id is None else sample_id,
        "source_query_id": source_query_id,
        "query": query,
        "dataset_ids": scope,
        "routes": {source: [] for source in ROUTES},
        "candidate_rows": [],
        "source_rows": [],
        "failed_sources": [],
        "route_status": {source: "unavailable" for source in ROUTES},
        "input_issues": [],
        "status": "failed",
        "ranking_input_ready": False,
    }
    issues = result["input_issues"]
    if not isinstance(query, str) or not query.strip():
        issues.append({"code": "empty_query"})
        return result
    try:
        response = await execute_candidates(query=query, dataset_ids=scope)
    except Exception as exc:  # noqa: BLE001 — 注入执行器失败须保留查询，不泄露异常消息。
        issues.append({"code": "candidate_execution_failed", "error_type": type(exc).__name__})
        return result

    candidates: dict[CandidateKey, dict[str, Any]] = {}
    route_keys: set[CandidateKey] = set()
    contract_keys: set[CandidateKey] = set()

    def retain(identity: dict[str, Any]) -> CandidateKey:
        key = _key(identity)
        if key not in candidates:
            candidates[key] = {**identity, "content": None, "source_passage_id": None}
        elif candidates[key]["doc_id"] != identity["doc_id"]:
            issues.append({"code": "candidate_doc_id_conflict", **identity})
        return key

    try:
        result["failed_sources"] = list(response.failed_sources)
        for hit in response.candidate_hits:
            identity = _identity(hit)
            key = retain(identity)
            if key in contract_keys:
                issues.append({"code": "duplicate_candidate", **identity})
            contract_keys.add(key)
        for source in ROUTES:
            if source not in response.route_hits:
                result["route_status"][source] = (
                    "failed" if source in result["failed_sources"] else "missing"
                )
                issues.append({"code": "missing_route", "source": source})
                continue
            seen: set[CandidateKey] = set()
            for rank, hit in enumerate(response.route_hits[source]):
                identity = _identity(hit)
                score = float(hit.score)
                if not math.isfinite(score):
                    raise ValueError("候选原始分数必须有限")
                result["routes"][source].append({**identity, "score": score, "rank": rank})
                key = retain(identity)
                route_keys.add(key)
                if key in seen:
                    issues.append(
                        {"code": "duplicate_route_candidate", "source": source, **identity}
                    )
                seen.add(key)
            result["route_status"][source] = (
                "failed" if source in result["failed_sources"] else "ok" if seen else "empty"
            )
        if set(response.route_hits) - set(ROUTES):
            issues.append(
                {
                    "code": "unexpected_routes",
                    "sources": sorted(set(response.route_hits) - set(ROUTES)),
                }
            )
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        issues.append({"code": "invalid_candidate_contract", "error_type": type(exc).__name__})
        result["candidate_rows"] = list(candidates.values())
        return result

    if result["failed_sources"]:
        issues.append({"code": "route_execution_failed", "sources": result["failed_sources"]})
    if contract_keys != route_keys:
        issues.append(
            {
                "code": "candidate_pool_mismatch",
                "route_only": [list(key) for key in sorted(route_keys - contract_keys)],
                "candidate_only": [list(key) for key in sorted(contract_keys - route_keys)],
            }
        )

    lookup_keys = []
    for key, candidate in candidates.items():
        if key[0] not in scope:
            issues.append({"code": "unexpected_dataset", "dataset_id": key[0], "chunk_id": key[1]})
        else:
            lookup_keys.append(key)
    # 至此所有问题都来自运行候选；后续单独区分正文/运行 ID 与评价映射问题。
    ranking_ready = not issues
    stored: dict[CandidateKey, list[Mapping[str, Any]]] = defaultdict(list)
    source_rows: dict[CandidateKey, list[str | None]] = {key: [None] for key in candidates}
    if lookup_keys:
        try:
            for row in await fetch_candidate_rows(lookup_keys):
                key = _key(row)
                if key not in lookup_keys:
                    ranking_ready = False
                    issues.append(
                        {"code": "unexpected_corpus_row", "dataset_id": key[0], "chunk_id": key[1]}
                    )
                    continue
                missing = {"doc_id", "content"}.difference(row)
                if missing:
                    ranking_ready = False
                    issues.append(
                        {
                            "code": "invalid_corpus_row",
                            "dataset_id": key[0],
                            "chunk_id": key[1],
                            "missing_fields": sorted(missing),
                        }
                    )
                    continue
                stored[key].append(row)
        except Exception as exc:  # noqa: BLE001 — 仓储失败不能使已取得的候选消失。
            ranking_ready = False
            issues.append({"code": "corpus_read_failed", "error_type": type(exc).__name__})

    passage_keys: dict[tuple[int, str], list[CandidateKey]] = defaultdict(list)
    for key in lookup_keys:
        candidate = candidates[key]
        identity = {"dataset_id": key[0], "chunk_id": key[1]}
        rows = stored.get(key, [])
        if not rows:
            ranking_ready = False
            issues.append({"code": "missing_corpus_row", **identity})
            continue
        row = rows[0]
        same_ranking_values = all(
            other["doc_id"] == row["doc_id"] and other["content"] == row["content"]
            for other in rows
        )
        if not same_ranking_values:
            ranking_ready = False
            issues.append({"code": "conflicting_corpus_ranking_values", **identity})
        else:
            candidate["content"] = row["content"]
        if candidate["doc_id"] != row["doc_id"]:
            ranking_ready = False
            issues.append(
                {"code": "corpus_doc_id_mismatch", "stored_doc_id": row["doc_id"], **identity}
            )
        if not isinstance(row["content"], str) or not row["content"].strip():
            ranking_ready = False
            issues.append({"code": "missing_content", **identity})
        if len(rows) != 1:
            issues.append({"code": "conflicting_corpus_rows", **identity})
            source_rows[key] = [None]
            for row in rows:
                pid = row.get("source_passage_id")
                if isinstance(pid, str) and pid and not any(char.isspace() for char in pid):
                    source_rows[key].append(pid)
                elif pid is not None:
                    issues.append(
                        {"code": "invalid_source_passage_id", "source_passage_id": pid, **identity}
                    )
            continue
        missing_source_fields = {"source_passage_id", "ordinal"}.difference(row)
        if missing_source_fields:
            issues.append(
                {
                    "code": "missing_source_fields",
                    "missing_fields": sorted(missing_source_fields),
                    **identity,
                }
            )
        candidate["source_passage_id"] = row.get("source_passage_id")
        candidate["ordinal"] = row.get("ordinal")
        pid = row.get("source_passage_id")
        source_rows[key] = [pid]
        if not isinstance(pid, str) or not pid.strip():
            issues.append({"code": "missing_source_passage_id", **identity})
            candidate["source_passage_id"] = None
            source_rows[key] = [None]
        elif any(char.isspace() for char in pid):
            issues.append(
                {"code": "invalid_source_passage_id", "source_passage_id": pid, **identity}
            )
            candidate["source_passage_id"] = None
            source_rows[key] = [None]
        elif row.get("ordinal") != 0:
            if "ordinal" in row:
                issues.append({"code": "non_passage_chunk", "source_passage_id": pid, **identity})
            candidate["source_passage_id"] = None
            source_rows[key].append(None)
        else:
            passage_keys[(key[0], pid)].append(key)
    for (dataset_id, pid), keys in passage_keys.items():
        if len(keys) > 1:
            issues.append(
                {
                    "code": "source_passage_maps_to_multiple_chunks",
                    "dataset_id": dataset_id,
                    "source_passage_id": pid,
                    "chunk_ids": [key[1] for key in keys],
                }
            )
            for key in keys:
                candidates[key]["source_passage_id"] = None
                source_rows[key].append(None)

    result["candidate_rows"] = list(candidates.values())
    result["source_rows"] = [
        [key[0], key[1], pid] for key, pids in source_rows.items() for pid in pids
    ]
    result["status"] = "incomplete" if issues else "ready" if candidates else "empty"
    result["ranking_input_ready"] = ranking_ready
    return result
