"""探索输入的文件编排与离线覆盖报告；不选择研究方法或生成评价标签。"""

from __future__ import annotations

import json
import random
from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from functools import partial
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROUTES = ("dense", "sparse", "bm25")


def select_queries(queries: Mapping[str, str], *, sample_size: int, seed: int) -> dict[str, str]:
    """按完整查询清单随机抽取；抽样过程不接收 qrels 或排序结果。"""
    if not 0 < sample_size <= len(queries):
        raise ValueError("sample_size 必须大于 0 且不超过查询总体")
    selected = random.Random(seed).sample(list(queries), sample_size)
    return {qid: queries[qid] for qid in selected}


def _write_json(path: Path, data: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


async def write_exploration_inputs(
    *,
    queries: Mapping[str, str],
    dataset_id: int,
    out_dir: Path,
    collect_input: Callable[..., Any],
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """逐查询写出完整记录；已有输出目录拒绝覆盖，异常保留先前记录。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    _write_json(out_dir / "run.json", dict(metadata))
    with (out_dir / "queries.jsonl").open("x", encoding="utf-8") as stream:
        for qid, query in queries.items():
            stream.write(json.dumps({"source_query_id": qid, "query": query}, ensure_ascii=False))
            stream.write("\n")
    status_counts: Counter[str] = Counter()
    with (out_dir / "inputs.jsonl").open("x", encoding="utf-8") as stream:
        for qid, query in queries.items():
            row = await collect_input(
                source_query_id=qid, query=query, dataset_ids=[dataset_id], sample_id=qid
            )
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
            status_counts[row["status"]] += 1
    summary = {"query_count": len(queries), "input_status_counts": dict(status_counts)}
    _write_json(out_dir / "summary.json", summary)
    return summary


async def prepare_exploration_candidates(
    *,
    queries_path: Path,
    collection_path: Path,
    dataset_id: int,
    sample_size: int,
    seed: int,
    out_dir: Path,
    settings: Any,
    corpus_run: Path | None = None,
) -> dict[str, Any]:
    """使用现有 eval 配置采集；原始 collection 仅标明语料来源，不自动入库。"""
    from linkrag_eval.app import _git_state
    from linkrag_eval.golden.opensource.datasets import read_t2_queries
    from linkrag_eval.retrieval.recall_adapter import execute_candidate_contract_once
    from linkrag_eval.retrieval.recall_factory import open_eval_recall_pipeline
    from linkrag_eval.runners.exploration_input import collect_exploration_input
    from linkrag_eval.store.corpus_repo import EvalCorpusRepo
    from linkrag_eval.store.vector_store import resolve_eval_qdrant_collection

    if settings.bm25_mode != "sqlite_fts5":
        raise ValueError("三路探索要求 EVAL_BM25_MODE=sqlite_fts5")
    if not Path(collection_path).is_file():
        raise ValueError("原始 collection 文件不存在")
    if dataset_id <= 0:
        raise ValueError("dataset_id 必须为正整数")
    queries = select_queries(read_t2_queries(queries_path), sample_size=sample_size, seed=seed)
    depths = {source: getattr(settings, f"recall_{source}_top_k") for source in ROUTES}
    if any(depth <= 0 for depth in depths.values()):
        raise ValueError("三路召回深度均须大于 0")
    thresholds = {
        "dense": settings.recall_dense_score_threshold,
        "sparse": settings.recall_sparse_score_threshold,
    }
    weights = {source: getattr(settings, f"recall_{source}_weight") for source in ROUTES}
    contract_version = "eval-candidate-contract-v1"
    profile = "post-recall-exploration"
    repo = EvalCorpusRepo(url=settings.database_url())
    code_revision, dirty = _git_state()
    database_path = settings.database_url().removeprefix("sqlite+aiosqlite:///")
    qdrant = urlsplit(
        settings.qdrant_host if "://" in settings.qdrant_host else "http://" + settings.qdrant_host
    )
    metadata = {
        "queries_path": str(Path(queries_path).resolve()),
        "collection_path": str(Path(collection_path).resolve()),
        "dataset_id": dataset_id,
        "user_id": settings.user_id,
        "sample_size": sample_size,
        "seed": seed,
        "use": "development_exploration",
        "code_revision": code_revision,
        "worktree_dirty": dirty,
        "route_depths": depths,
        "route_thresholds": thresholds,
        "fusion_weights": weights,
        "candidate_contract_version": contract_version,
        "candidate_profile": profile,
        "fusion_result_limit": sum(depths.values()),
        "dense": {
            "model": settings.embed_model,
            "dim": settings.embed_dim,
            "input_length_policy": settings.embed_input_length_policy,
        },
        "sparse": {
            "provider": settings.sparse_provider,
            "model": settings.sparse_model,
            "top_k": settings.sparse_top_k,
            "min_weight": settings.sparse_min_weight,
            "vector_name": settings.sparse_vector_name,
            "input_length_policy": settings.sparse_input_length_policy,
        },
        "bm25_mode": settings.bm25_mode,
        "bm25_weights": {
            "coarse": settings.bm25_sqlite_coarse_weight,
            "fine": settings.bm25_sqlite_fine_weight,
        },
        "storage": {
            "corpus_sqlite_path": database_path
            if database_path == ":memory:"
            else str(Path(database_path).resolve()),
            "bm25_sqlite_path": str(Path(settings.bm25_sqlite_path).resolve()),
            "qdrant_endpoint": {"host": qdrant.hostname, "port": qdrant.port},
            "qdrant_collection": resolve_eval_qdrant_collection(
                prefix=settings.qdrant_prefix,
                bucket_count=settings.qdrant_bucket_count,
                user_id=settings.user_id,
            ),
        },
        "corpus_run": str(Path(corpus_run).resolve()) if corpus_run is not None else None,
        "collection_coverage": "completed_corpus_run"
        if corpus_run is not None
        else "not_established_by_candidate_collection",
    }
    async with open_eval_recall_pipeline(settings=settings) as pipeline:
        execute = partial(
            execute_candidate_contract_once,
            pipeline,
            user_id=settings.user_id,
            top_k=sum(depths.values()),
            bm25_top_k=depths["bm25"],
            dense_top_k=depths["dense"],
            sparse_top_k=depths["sparse"],
            dense_score_threshold=thresholds["dense"],
            sparse_score_threshold=thresholds["sparse"],
            enabled_sources=list(ROUTES),
            required_sources=list(ROUTES),
            fusion_weights=weights,
            candidate_contract_version=contract_version,
            candidate_profile=profile,
        )
        collect = partial(
            collect_exploration_input,
            execute_candidates=execute,
            fetch_candidate_rows=repo.fetch_candidate_rows,
        )
        return await write_exploration_inputs(
            queries=queries,
            dataset_id=dataset_id,
            out_dir=out_dir,
            collect_input=collect,
            metadata=metadata,
        )


def _candidate_keys(row: Mapping[str, Any]) -> list[tuple[int, str]]:
    keys: dict[tuple[int, str], None] = {}
    routes = row["routes"]
    if set(routes) != set(ROUTES):
        raise ValueError("输入必须显式保留 dense/sparse/bm25 三路，包括空列表")
    for source in ROUTES:
        for hit in routes[source]:
            keys[(int(hit["dataset_id"]), str(hit["chunk_id"]))] = None
    # 契约与逐路并集不一致时，runner 会标输入异常；覆盖仍保留所有已观测候选。
    for candidate in row["candidate_rows"]:
        keys[(int(candidate["dataset_id"]), str(candidate["chunk_id"]))] = None
    return list(keys)


def _read_input_rows(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    with Path(path).open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if line.strip():
                yield line_number, json.loads(line)


async def build_exploration_coverage(
    *,
    inputs_path: Path,
    queries_path: Path,
    qrels_path: Path,
    ranker: Any | None = None,
    k: int | None = None,
) -> dict[str, Any]:
    """观测候选覆盖与可用基线的覆盖分别汇总，输入失败不被伪装为空池。"""
    from linkrag_eval.golden.opensource.coverage import (
        join_candidate_qrels,
        summarize_label_coverage,
    )
    from linkrag_eval.golden.opensource.datasets import read_t2_qrels, read_t2_queries

    if (ranker is None) != (k is None) or (k is not None and k <= 0):
        raise ValueError("baseline ranker 和正整数 k 必须同时提供")
    queries = read_t2_queries(queries_path)
    qrels = read_t2_qrels(qrels_path)
    unknown_qids = (
        {qid for qid, _ in qrels.grades} | {qid for qid, _ in qrels.conflicts}
    ) - queries.keys()
    if unknown_qids:
        raise ValueError("qrels 含所用完整 queries 文件之外的查询 ID")
    selection_path = Path(inputs_path).with_name("queries.jsonl")
    selected = {}
    for line_number, item in _read_input_rows(selection_path):
        qid = item["source_query_id"]
        if qid in selected or qid not in queries or item["query"] != queries[qid]:
            raise ValueError(f"queries.jsonl:{line_number} 抽样查询重复或与原始查询不一致")
        selected[qid] = item["query"]
    if not selected:
        raise ValueError("queries.jsonl 中没有抽样查询")
    joined_queries = []
    baseline_queries = []
    baseline_orders = {}
    unavailable = []
    baseline_runs = []
    input_states = []
    seen = set()
    for line_number, row in _read_input_rows(inputs_path):
        qid = row["source_query_id"]
        if qid not in queries or row["query"] != queries[qid]:
            raise ValueError(f"inputs:{line_number} 查询与原始查询清单不一致")
        if qid not in selected:
            raise ValueError(f"inputs:{line_number} 查询不在本次抽样清单中")
        if qid in seen:
            raise ValueError(f"inputs:{line_number} 重复 source_query_id")
        seen.add(qid)
        keys = _candidate_keys(row)
        source_rows = [tuple(mapping) for mapping in row["source_rows"]]
        joined = join_candidate_qrels(
            source_query_id=qid, candidate_keys=keys, source_rows=source_rows, qrels=qrels
        )
        joined_queries.append(joined)
        state = {
            "source_query_id": qid,
            "status": row["status"],
            "ranking_input_ready": row["ranking_input_ready"],
            "failed_sources": row["failed_sources"],
            "input_issues": row["input_issues"],
        }
        input_states.append(state)
        if ranker is None:
            continue
        if not row["ranking_input_ready"]:
            unavailable.append({"source_query_id": qid, "reason": "incomplete_input"})
            continue
        if len({cid for _, cid in keys}) != len(keys):
            unavailable.append({"source_query_id": qid, "reason": "chunk_id_collision"})
            continue
        if not keys:
            baseline_orders[qid] = []
            baseline_queries.append(joined)
            baseline_runs.append({"source_query_id": qid, "mode": "empty"})
            continue
        contents = {
            str(r["chunk_id"]): r["content"]
            for r in row["candidate_rows"]
            if isinstance(r.get("content"), str) and r["content"].strip()
        }
        if set(contents) != {cid for _, cid in keys}:
            unavailable.append({"source_query_id": qid, "reason": "content_missing"})
            continue
        # 显式构造只含已有方法输入的视图，source IDs 和标签不会传入排序器。
        method_routes = {
            source: [
                {key: hit[key] for key in ("dataset_id", "chunk_id", "doc_id", "score", "rank")}
                for hit in row["routes"][source]
            ]
            for source in ROUTES
        }
        try:
            result = await ranker.rank({"query": row["query"], "routes": method_routes}, contents)
            by_chunk = {cid: key for key in keys for cid in [key[1]]}
            ranked = result.ranked_chunk_ids
            if (
                len(ranked) != len(keys)
                or len(set(ranked)) != len(keys)
                or set(ranked) != set(by_chunk)
            ):
                raise ValueError("baseline 未返回完整候选的排列")
            baseline_orders[qid] = [by_chunk[cid] for cid in ranked]
            baseline_queries.append(joined)
            baseline_runs.append(
                {
                    "source_query_id": qid,
                    "mode": result.mode,
                    "model_version": result.model_version,
                    "elapsed_ms": result.elapsed_ms,
                    "reason": result.reason,
                }
            )
        except Exception as exc:  # noqa: BLE001 — 保留查询，且不输出可能含服务信息的异常文本。
            unavailable.append({"source_query_id": qid, "reason": type(exc).__name__})
    # 采集中断不改变抽样总体；未执行不是成功空池，也不能参与基线覆盖。
    for qid in selected:
        if qid in seen:
            continue
        joined_queries.append(
            join_candidate_qrels(
                source_query_id=qid,
                candidate_keys=[],
                source_rows=[],
                qrels=qrels,
            )
        )
        input_states.append(
            {
                "source_query_id": qid,
                "status": "not_executed",
                "ranking_input_ready": False,
                "failed_sources": [],
                "input_issues": [{"code": "missing_input_row"}],
            }
        )
        if ranker is not None:
            unavailable.append({"source_query_id": qid, "reason": "incomplete_input"})
    return {
        "inputs_path": str(Path(inputs_path).resolve()),
        "selection_path": str(selection_path.resolve()),
        "selected_query_count": len(selected),
        "queries_path": str(Path(queries_path).resolve()),
        "qrels_path": str(Path(qrels_path).resolve()),
        "qrels_rows": qrels.row_count,
        "qrels_duplicate_rows": qrels.duplicate_rows,
        "qrels_conflicting_pairs": len(qrels.conflicts),
        "input_status_counts": dict(Counter(state["status"] for state in input_states)),
        "input_states": input_states,
        "observed_candidate_coverage": summarize_label_coverage(joined_queries),
        "baseline_coverage": (
            summarize_label_coverage(baseline_queries, baseline_orders=baseline_orders, k=k)
            if ranker is not None
            else None
        ),
        "baseline_unavailable": unavailable,
        "baseline_runs": baseline_runs,
        "scope": "已有返回候选的标签覆盖；输入完整性另列，不是排序质量或自然错误率",
    }


async def write_exploration_coverage(
    *,
    inputs_path: Path,
    queries_path: Path,
    qrels_path: Path,
    out: Path,
    model_dir: Path | None = None,
    k: int | None = None,
) -> dict[str, Any]:
    if Path(out).exists():
        raise FileExistsError(out)
    if (model_dir is None) != (k is None):
        raise ValueError("model_dir 与 k 必须同时提供，或均不提供")
    ranker = None
    if model_dir is not None:
        from linkrag_eval.retrieval.learning_to_rank.online import LambdaMartOnlineRanker

        ranker = LambdaMartOnlineRanker(model_dir)
    report = await build_exploration_coverage(
        inputs_path=inputs_path,
        queries_path=queries_path,
        qrels_path=qrels_path,
        ranker=ranker,
        k=k,
    )
    report["baseline_model_dir"] = str(Path(model_dir).resolve()) if model_dir else None
    report["baseline_policy"] = "existing_online_policy_including_fallbacks" if ranker else None
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    _write_json(Path(out), report)
    return report
