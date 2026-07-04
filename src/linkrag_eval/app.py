"""端到端编排:灌库(ingest)与召回评测(eval)。

组件全部注入(computer/indexer/corpus_repo/evaluable/metrics/store),便于 fake 单测;
真实装配在 cli.py。本模块零 rag import——只编排抽象。
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Awaitable, Callable

from linkrag_eval.golden.corpus_io import load_manifest, read_tsv_collection
from linkrag_eval.golden.loader import load_golden, precheck
from linkrag_eval.metrics.retrieval import DEFAULT_K_VALUES
from linkrag_eval.models import EvalResult, Layer, Snapshot
from linkrag_eval.runners import RunContext, run_stage
from linkrag_eval.store.indexer import EvalPassage


async def run_ingest(
    dataset_id: int,
    collection_path: str,
    manifest_path: str,
    *,
    indexer: Any,
    corpus_repo: Any,
    catalog: dict[str, Any] | None = None,
    batch: int = 25,
    retries: int = 4,
    limit: int | None = None,
    progress: Callable[[str], None] | None = None,
) -> int:
    """读 manifest(success)+ collection → EvalPassage → 编目 + 分批灌库。返回写入 chunk 数。

    分批 + 批级重试(远端 Qdrant/embedding 偶发 502/限流;uuid5 幂等,重试与重跑均安全)。
    """
    import asyncio
    records = [r for r in load_manifest(manifest_path) if r.status == "success"]
    records.sort(key=lambda r: r.doc_id)
    corpus = read_tsv_collection(collection_path)

    passages: list[EvalPassage] = []
    missing = 0
    for r in records:
        text = corpus.get(r.source_id)
        if not text:
            missing += 1
            continue
        passages.append(EvalPassage(source_passage_id=r.source_id, content=text, doc_id=r.doc_id))
    if limit:
        passages = passages[:limit]
    if progress:
        progress(f"manifest success={len(records)} collection={len(corpus)} "
                 f"待灌={len(passages)}(缺正文 {missing} 跳过)")
    if not passages:
        return 0

    if catalog:
        await corpus_repo.register_dataset(dataset_id, **catalog)

    total = 0
    failed = 0
    n_batches = (len(passages) + batch - 1) // batch
    for start in range(0, len(passages), batch):
        chunk = passages[start : start + batch]
        idx = start // batch + 1
        for attempt in range(1, retries + 1):
            try:
                got = await indexer.index_passages(dataset_id, chunk)
                total += got
                if progress:
                    progress(f"  批 {idx}/{n_batches}: +{got}(累计 {total}/{len(passages)})")
                break
            except Exception as exc:
                if attempt == retries:
                    failed += len(chunk)
                    if progress:
                        progress(f"  批 {idx}: 重试 {retries} 次仍失败,跳过 — "
                                 f"{type(exc).__name__}: {str(exc)[:100]}")
                    break
                await asyncio.sleep(2 * attempt)
    if failed and progress:
        progress(f"注意:{failed} 条最终失败(uuid5 幂等,重跑本命令补齐)")
    return total


def _minimal_snapshot(run_id: str, top_k: int, *, settings: Any | None = None) -> Snapshot:
    """据 eval 配置构最小快照(检索层用;生成层字段留空)。"""
    sparse_provider = "unknown"
    dense_threshold = 0.0
    sparse_threshold = 0.0
    dense_top_k = top_k
    sparse_top_k = top_k
    bm25_top_k = top_k
    fusion_strategy = "rrf"
    fusion_weights: dict[str, float] = {}
    if settings is not None:
        sparse_provider = f"{getattr(settings, 'sparse_provider', '')}:{getattr(settings, 'sparse_model', '')}"
        dense_threshold = getattr(settings, "recall_dense_score_threshold", 0.0)
        sparse_threshold = getattr(settings, "recall_sparse_score_threshold", 0.0)
        dense_top_k = getattr(settings, "recall_dense_top_k", top_k)
        sparse_top_k = getattr(settings, "recall_sparse_top_k", top_k)
        bm25_top_k = getattr(settings, "recall_bm25_top_k", top_k)
        fusion_strategy = getattr(settings, "recall_fusion_strategy", "rrf")
        fusion_weights = {
            "dense": getattr(settings, "recall_dense_weight", 0.5),
            "sparse": getattr(settings, "recall_sparse_weight", 0.3),
            "bm25": getattr(settings, "recall_bm25_weight", 0.0),
        }
    enabled_sources = ["dense", "sparse"]
    if getattr(settings, "bm25_mode", "stub") == "qdrant_bm25":
        enabled_sources = ["bm25", "dense", "sparse"]
    return Snapshot(
        run_id=run_id, git_sha="", sparse_vector_provider=sparse_provider, top_k=top_k,
        score_threshold=sparse_threshold, enabled_sources=enabled_sources, rrf_k=60, rerank_top_n=None,
        chat_model="", judge_model="", generator_model="", token_budget=0, prompt_version="v1",
        route_score_thresholds={"dense": dense_threshold, "sparse": sparse_threshold},
        route_top_ks={"bm25": bm25_top_k, "dense": dense_top_k, "sparse": sparse_top_k},
        fusion_strategy=fusion_strategy,
        fusion_weights=fusion_weights,
    )


async def run_eval(
    golden_path: str,
    *,
    top_k: int,
    run_id: str,
    evaluable: Any,
    metrics: list,
    store: Any,
    settings: Any | None = None,
    domain_of: Callable[[Any], str | None] | None = None,
    fetch_status: Callable[[list[str]], Awaitable[dict[str, str]]] | None = None,
    k_values: list[int] | None = None,
    progress: Callable[[str], None] | None = None,
) -> EvalResult:
    """加载 golden →(可选 precheck)→ run_stage → 返回 EvalResult。"""
    golden = load_golden(golden_path)
    if fetch_status is not None:
        report = await precheck(golden, fetch_status)
        if progress:
            progress(report.summary())
        if not report.ok:
            raise RuntimeError(f"golden precheck 失败:{len(report.invalid_sample_ids)} 条 reference 失效")

    snapshot = _minimal_snapshot(run_id, top_k, settings=settings)
    ctx = RunContext(
        run_id=run_id, snapshot=snapshot, store=store, top_k=top_k,
        k_values=list(k_values or DEFAULT_K_VALUES),
    )
    if progress:
        progress(f"评测 {len(golden)} 条 query(top_k={top_k})...")
    return await run_stage(golden, evaluable, metrics, ctx, domain_of=domain_of)


def format_retrieval_summary(result: EvalResult) -> str:
    """把检索层聚合指标拍成可读文本(主看 recall@k)。"""
    lines = [f"run_id={result.run_id}  样本={len(result.per_sample)}"]
    failed_counter: Counter[str] = Counter()
    failed_samples = 0
    zero_ranked = 0
    for row in result.per_sample:
        failed = list(row.get("failed_sources") or [])
        if failed:
            failed_samples += 1
            failed_counter.update(failed)
        if row.get("n_ranked") == 0:
            zero_ranked += 1
    quality = "clean" if failed_samples == 0 and zero_ranked == 0 else "non-clean"
    lines.append(
        f"  run_quality = {quality}  "
        f"(failed_samples={failed_samples}, failed_sources={dict(failed_counter)}, zero_ranked={zero_ranked})"
    )
    retr = [m for m in result.metrics if m.layer == Layer.RETRIEVAL]
    for m in sorted(retr, key=lambda x: (x.name, x.k if x.k is not None else -1)):
        k = f"@{m.k}" if m.k is not None else ""
        lines.append(f"  {m.name}{k:<4} = {m.mean:.4f}  (n={m.n})")
    return "\n".join(lines)
