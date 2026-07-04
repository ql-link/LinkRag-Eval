"""召回参数搜索:缓存分路候选,本地网格评估 dense/sparse topK 与阈值。

本模块不直接 import toLink-Rag(``src.*``)。分路 retriever 装配仍经
``retrieval.recall_factory`` 这个允许 adapter 文件;这里仅调用抽象出来的 retriever 对象,
并在纯 Python 中按生产 RRF 公式融合。
"""

from __future__ import annotations

import asyncio
import csv
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from linkrag_eval.golden.schema import GoldenSample
from linkrag_eval.metrics.retrieval import ranked_ids, reference_ids
from linkrag_eval.models import Layer, RankedHit, StageOutput

SOURCE_DENSE = "dense"
SOURCE_SPARSE = "sparse"
ALL_SOURCES = [SOURCE_DENSE, SOURCE_SPARSE]
DEFAULT_FUSION_WEIGHTS = {SOURCE_DENSE: 0.5, SOURCE_SPARSE: 0.3}


@dataclass(frozen=True)
class RouteHit:
    chunk_id: str
    doc_id: int
    dataset_id: int
    score: float
    source: str


@dataclass(frozen=True)
class CachedSample:
    sample: GoldenSample
    dense_hits: list[RouteHit]
    sparse_hits: list[RouteHit]
    failed_sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class TuneConfig:
    dense_top_k: int
    sparse_top_k: int
    dense_threshold: float
    sparse_threshold: float
    final_top_k: int
    rrf_k: int


@dataclass(frozen=True)
class TuneResult:
    dense_top_k: int
    sparse_top_k: int
    dense_threshold: float
    sparse_threshold: float
    final_top_k: int
    rrf_k: int
    recall_at_10: float
    hit_rate_at_10: float
    map: float
    mrr: float
    n: int
    failed_source_samples: int

    @property
    def score_key(self) -> tuple[float, float, float, float, int, int, float, float]:
        """排序准则:先 recall,再 hit/mrr/map;同分偏向更小 sparse topK 与更高 sparse 阈值。"""
        return (
            self.recall_at_10,
            self.hit_rate_at_10,
            self.mrr,
            self.map,
            -self.sparse_top_k,
            -self.dense_top_k,
            self.sparse_threshold,
            self.dense_threshold,
        )


def parse_number_list(value: str, *, cast=float) -> list:
    """解析 ``1,2,3`` 参数,去重但保留排序。"""
    seen = set()
    out = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        item = cast(part)
        if item not in seen:
            seen.add(item)
            out.append(item)
    if not out:
        raise ValueError(f"参数列表为空: {value!r}")
    return out


def _to_route_hit(hit: Any, source: str) -> RouteHit:
    return RouteHit(
        chunk_id=str(hit.chunk_id),
        doc_id=int(hit.doc_id),
        dataset_id=int(hit.dataset_id),
        score=float(hit.score),
        source=source,
    )


async def cache_route_hits(
    samples: list[GoldenSample],
    *,
    settings: Any,
    max_dense_top_k: int,
    max_sparse_top_k: int,
    concurrency: int = 4,
    progress: Any | None = None,
) -> list[CachedSample]:
    """对每条 query 各拉一次 dense/sparse 最大候选池,供后续本地网格复用。"""
    from linkrag_eval.retrieval.recall_factory import build_eval_recall_pipeline

    pipeline = build_eval_recall_pipeline(
        settings=settings,
        dense_score_threshold=0.0,
        sparse_score_threshold=0.0,
    )
    retrievers = {r.source: r for r in pipeline._retrievers}
    sem = asyncio.Semaphore(concurrency)
    done = 0

    async def _one(sample: GoldenSample) -> CachedSample:
        nonlocal done
        async with sem:
            failed: list[str] = []
            route_hits: dict[str, list[RouteHit]] = {SOURCE_DENSE: [], SOURCE_SPARSE: []}
            for source, top_k in (
                (SOURCE_DENSE, max_dense_top_k),
                (SOURCE_SPARSE, max_sparse_top_k),
            ):
                retriever = retrievers[source]
                try:
                    hits = await retriever.recall(
                        sample.query,
                        sample.dataset_ids,
                        None,
                        user_id=sample.user_id,
                        top_k=top_k,
                        score_threshold_override=0.0,
                    )
                except Exception:
                    failed.append(source)
                    hits = []
                route_hits[source] = [_to_route_hit(h, source) for h in hits]
            done += 1
            if progress and (done % 25 == 0 or done == len(samples)):
                progress(f"cached {done}/{len(samples)}")
            return CachedSample(
                sample=sample,
                dense_hits=route_hits[SOURCE_DENSE],
                sparse_hits=route_hits[SOURCE_SPARSE],
                failed_sources=tuple(failed),
            )

    return await asyncio.gather(*[_one(s) for s in samples])


def _filter_route_hits(
    hits: list[RouteHit],
    *,
    top_k: int,
    threshold: float,
) -> list[RouteHit]:
    return [h for h in hits if h.score >= threshold][:top_k]


def _rrf_fuse(
    per_source_hits: dict[str, list[RouteHit]],
    *,
    final_top_k: int,
    rrf_k: int,
) -> list[RankedHit]:
    entries: dict[str, dict[str, Any]] = {}
    for source, hits in per_source_hits.items():
        for rank_zero, hit in enumerate(hits):
            entry = entries.setdefault(
                hit.chunk_id,
                {
                    "chunk_id": hit.chunk_id,
                    "doc_id": hit.doc_id,
                    "dataset_id": hit.dataset_id,
                    "score": 0.0,
                    "sources": set(),
                },
            )
            entry["score"] += 1.0 / (rrf_k + rank_zero + 1)
            entry["sources"].add(source)
    ordered = sorted(entries.values(), key=lambda e: e["score"], reverse=True)
    return [
        RankedHit(
            chunk_id=e["chunk_id"],
            doc_id=e["doc_id"],
            dataset_id=e["dataset_id"],
            rank=i,
            score=e["score"],
            sources=frozenset(e["sources"]),
        )
        for i, e in enumerate(ordered[:final_top_k])
    ]


def _weighted_score_fuse(
    per_source_hits: dict[str, list[RouteHit]],
    *,
    final_top_k: int,
    weights: dict[str, float] | None = None,
) -> list[RankedHit]:
    """按生产 weighted_score 公式融合 dense/sparse 候选。

    生产口径:BM25/sparse 对 raw score 先 log1p,dense 原始分直用;每一路独立
    min-max 归一化;权重按 active sources 归一,chunk 未命中的路贡献为 0。
    """
    weights = weights or DEFAULT_FUSION_WEIGHTS
    active_sources = [source for source, hits in per_source_hits.items() if hits]
    if not active_sources:
        return []
    active_weight_sum = sum(weights.get(source, 0.0) for source in active_sources)
    if active_weight_sum <= 0:
        raise ValueError("active source fusion weight sum must be > 0")

    normalized_by_source: dict[str, dict[str, float]] = {}
    for source in active_sources:
        transformed = [
            (hit.chunk_id, _transform_weighted_score(source, hit.score))
            for hit in per_source_hits[source]
        ]
        values = [score for _chunk_id, score in transformed]
        min_score = min(values)
        max_score = max(values)
        if len(transformed) == 1 or max_score == min_score:
            normalized_by_source[source] = {chunk_id: 1.0 for chunk_id, _score in transformed}
        else:
            score_range = max_score - min_score
            normalized_by_source[source] = {
                chunk_id: (score - min_score) / score_range
                for chunk_id, score in transformed
            }

    entries: dict[str, dict[str, Any]] = {}
    for source in active_sources:
        normalized_weight = weights.get(source, 0.0) / active_weight_sum
        for hit in per_source_hits[source]:
            entry = entries.setdefault(
                hit.chunk_id,
                {
                    "chunk_id": hit.chunk_id,
                    "doc_id": hit.doc_id,
                    "dataset_id": hit.dataset_id,
                    "score": 0.0,
                    "sources": set(),
                },
            )
            entry["score"] += normalized_by_source[source][hit.chunk_id] * normalized_weight
            entry["sources"].add(source)
    ordered = sorted(entries.values(), key=lambda e: (-e["score"], e["chunk_id"]))
    return [
        RankedHit(
            chunk_id=e["chunk_id"],
            doc_id=e["doc_id"],
            dataset_id=e["dataset_id"],
            rank=i,
            score=e["score"],
            sources=frozenset(e["sources"]),
        )
        for i, e in enumerate(ordered[:final_top_k])
    ]


def _transform_weighted_score(source: str, raw_score: float) -> float:
    if not math.isfinite(raw_score):
        raise ValueError(f"{source} score must be finite")
    if source == SOURCE_SPARSE:
        if raw_score < 0:
            raise ValueError(f"{source} score must be >= 0 for weighted_score")
        return math.log1p(raw_score)
    if source == SOURCE_DENSE:
        return raw_score
    raise ValueError(f"unsupported weighted_score source: {source}")


def stage_output_for_config(
    cached: CachedSample,
    config: TuneConfig,
    *,
    fusion_strategy: str = "rrf",
    fusion_weights: dict[str, float] | None = None,
) -> StageOutput:
    dense = _filter_route_hits(
        cached.dense_hits,
        top_k=config.dense_top_k,
        threshold=config.dense_threshold,
    )
    sparse = _filter_route_hits(
        cached.sparse_hits,
        top_k=config.sparse_top_k,
        threshold=config.sparse_threshold,
    )
    per_source = {SOURCE_DENSE: dense, SOURCE_SPARSE: sparse}
    if fusion_strategy == "rrf":
        ranked = _rrf_fuse(
            per_source,
            final_top_k=config.final_top_k,
            rrf_k=config.rrf_k,
        )
    elif fusion_strategy == "weighted_score":
        ranked = _weighted_score_fuse(
            per_source,
            final_top_k=config.final_top_k,
            weights=fusion_weights,
        )
    else:
        raise ValueError(f"unsupported fusion_strategy={fusion_strategy!r}")
    return StageOutput(
        layer=Layer.RETRIEVAL,
        query=cached.sample.query,
        ranked=ranked,
        per_source_counts={SOURCE_DENSE: len(dense), SOURCE_SPARSE: len(sparse)},
        failed_sources=list(cached.failed_sources),
    )


def _metric_values(sample: GoldenSample, output: StageOutput, *, k: int) -> dict[str, float]:
    relevant, granularity = reference_ids(sample)
    if not relevant:
        return {"recall": 0.0, "hit_rate": 0.0, "map": 0.0, "mrr": 0.0}
    ids = ranked_ids(output.ranked, granularity)
    top = ids[:k]
    hit_set = set(top) & relevant
    recall = len(hit_set) / len(relevant)
    hit_rate = 1.0 if hit_set else 0.0

    hits = 0
    precision_sum = 0.0
    rr = 0.0
    for i, item in enumerate(ids, start=1):
        if item in relevant:
            hits += 1
            precision_sum += hits / i
            if rr == 0.0:
                rr = 1.0 / i
    denom = min(len(relevant), len(ids)) if ids else 0
    return {
        "recall": recall,
        "hit_rate": hit_rate,
        "map": precision_sum / denom if denom else 0.0,
        "mrr": rr,
    }


def evaluate_config(
    cached: list[CachedSample],
    config: TuneConfig,
    *,
    fusion_strategy: str = "rrf",
    fusion_weights: dict[str, float] | None = None,
) -> TuneResult:
    sums = {"recall": 0.0, "hit_rate": 0.0, "map": 0.0, "mrr": 0.0}
    for item in cached:
        output = stage_output_for_config(
            item,
            config,
            fusion_strategy=fusion_strategy,
            fusion_weights=fusion_weights,
        )
        values = _metric_values(item.sample, output, k=config.final_top_k)
        for key, value in values.items():
            sums[key] += value
    n = len(cached)
    failed = sum(1 for item in cached if item.failed_sources)
    return TuneResult(
        dense_top_k=config.dense_top_k,
        sparse_top_k=config.sparse_top_k,
        dense_threshold=config.dense_threshold,
        sparse_threshold=config.sparse_threshold,
        final_top_k=config.final_top_k,
        rrf_k=config.rrf_k,
        recall_at_10=sums["recall"] / n,
        hit_rate_at_10=sums["hit_rate"] / n,
        map=sums["map"] / n,
        mrr=sums["mrr"] / n,
        n=n,
        failed_source_samples=failed,
    )


def iter_configs(
    *,
    dense_top_ks: Iterable[int],
    sparse_top_ks: Iterable[int],
    dense_thresholds: Iterable[float],
    sparse_thresholds: Iterable[float],
    final_top_k: int,
    rrf_k: int,
) -> Iterable[TuneConfig]:
    for dense_top_k in dense_top_ks:
        for sparse_top_k in sparse_top_ks:
            for dense_threshold in dense_thresholds:
                for sparse_threshold in sparse_thresholds:
                    yield TuneConfig(
                        dense_top_k=dense_top_k,
                        sparse_top_k=sparse_top_k,
                        dense_threshold=dense_threshold,
                        sparse_threshold=sparse_threshold,
                        final_top_k=final_top_k,
                        rrf_k=rrf_k,
                    )


def run_grid(cached: list[CachedSample], configs: Iterable[TuneConfig]) -> list[TuneResult]:
    return sorted((evaluate_config(cached, cfg) for cfg in configs), key=lambda r: r.score_key, reverse=True)


def write_tuning_outputs(
    *,
    out_dir: str | Path,
    dataset: str,
    results: list[TuneResult],
    cached: list[CachedSample],
    args: dict[str, Any],
) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().isoformat(timespec="seconds")
    stem = f"recall_tuning_{dataset}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    csv_path = out / f"{stem}.csv"
    json_path = out / f"{stem}.json"
    md_path = out / f"{stem}.md"
    html_path = out / f"{stem}.html"

    fieldnames = list(asdict(results[0]).keys()) if results else list(TuneResult.__dataclass_fields__)
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow(asdict(row))

    payload = {
        "dataset": dataset,
        "created_at": ts,
        "args": args,
        "n_samples": len(cached),
        "failed_source_samples": sum(1 for item in cached if item.failed_sources),
        "best": asdict(results[0]) if results else None,
        "top20": [asdict(r) for r in results[:20]],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path.write_text(_markdown_report(payload, results[:20]), encoding="utf-8")
    html_path.write_text(_html_report(payload, results[:20]), encoding="utf-8")
    return {"csv": csv_path, "json": json_path, "md": md_path, "html": html_path}


def _markdown_report(payload: dict[str, Any], top_results: list[TuneResult]) -> str:
    best = payload["best"] or {}
    lines = [
        f"# Recall 参数搜索报告: {payload['dataset']}",
        "",
        f"- 生成时间: `{payload['created_at']}`",
        f"- 样本数: `{payload['n_samples']}`",
        f"- 分路失败样本数: `{payload['failed_source_samples']}`",
        f"- 最优配置: dense_top_k=`{best.get('dense_top_k')}`, sparse_top_k=`{best.get('sparse_top_k')}`, "
        f"dense_threshold=`{best.get('dense_threshold')}`, sparse_threshold=`{best.get('sparse_threshold')}`",
        f"- 最优指标: recall@10=`{best.get('recall_at_10'):.4f}`, "
        f"hit_rate@10=`{best.get('hit_rate_at_10'):.4f}`, map=`{best.get('map'):.4f}`, "
        f"mrr=`{best.get('mrr'):.4f}`",
        "",
        "## 搜索空间",
        "",
        "```json",
        json.dumps(payload["args"], ensure_ascii=False, indent=2),
        "```",
        "",
        "## Top 20",
        "",
        "| rank | dense_top_k | sparse_top_k | dense_th | sparse_th | recall@10 | hit_rate@10 | map | mrr |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for i, result in enumerate(top_results, start=1):
        lines.append(
            f"| {i} | {result.dense_top_k} | {result.sparse_top_k} | "
            f"{result.dense_threshold:.3f} | {result.sparse_threshold:.3f} | "
            f"{result.recall_at_10:.4f} | {result.hit_rate_at_10:.4f} | "
            f"{result.map:.4f} | {result.mrr:.4f} |"
        )
    lines.extend(
        [
            "",
            "## 结论",
            "",
            "按排序准则优先选择 recall@10,再看 hit_rate@10、MRR、MAP;同分时偏向更小 sparse topK 和更高 sparse 阈值,以减少低分 sparse 噪声参与 RRF。",
        ]
    )
    return "\n".join(lines) + "\n"


def _fmt4(value: Any) -> str:
    return f"{float(value):.4f}"


def _html_report(payload: dict[str, Any], top_results: list[TuneResult]) -> str:
    from linkrag_eval.reporters.html_reporter import _CSS, _esc

    best = payload["best"] or {}
    args = payload["args"]
    corpus_chunks = args.get("corpus_chunks")
    corpus_text = f"{corpus_chunks} chunks" if corpus_chunks else "未记录"
    rerank = args.get("rerank") or "none"
    fusion = args.get("fusion") or "RRF"
    config_count = (
        len(args["dense_top_ks"])
        * len(args["sparse_top_ks"])
        * len(args["dense_thresholds"])
        * len(args["sparse_thresholds"])
    )
    cards = [
        ("Recall@10", _fmt4(best.get("recall_at_10", 0.0)), "主指标"),
        ("Hit Rate@10", _fmt4(best.get("hit_rate_at_10", 0.0)), "至少命中一个相关文档"),
        ("MAP", _fmt4(best.get("map", 0.0)), "排序质量"),
        ("MRR", _fmt4(best.get("mrr", 0.0)), "首个正确结果位置"),
        ("样本数", str(payload["n_samples"]), "golden query"),
        ("语料规模", _esc(corpus_text), "正式 eval collection"),
    ]
    card_html = "".join(
        f'<div class="card"><div class="k">{_esc(k)}</div><div class="v">{v}</div><div class="d flat">{_esc(d)}</div></div>'
        for k, v, d in cards
    )
    chips = "".join(
        f'<span class="chip">{label} <b>{value}</b></span>'
        for label, value in [
            ("fusion", _esc(fusion)),
            ("rerank", _esc(rerank)),
            ("rrf_k", _esc(args["rrf_k"])),
            ("final_top_k", _esc(args["final_top_k"])),
            ("configs", _esc(config_count)),
            ("failed sources", _esc(payload["failed_source_samples"])),
        ]
    )
    top_rows = []
    for rank, result in enumerate(top_results, start=1):
        top_rows.append(
            "<tr>"
            f"<td>{rank}</td>"
            f"<td>{result.dense_top_k}</td>"
            f"<td>{result.sparse_top_k}</td>"
            f"<td>{result.dense_threshold:.3f}</td>"
            f"<td>{result.sparse_threshold:.3f}</td>"
            f"<td>{result.recall_at_10:.4f}</td>"
            f"<td>{result.hit_rate_at_10:.4f}</td>"
            f"<td>{result.map:.4f}</td>"
            f"<td>{result.mrr:.4f}</td>"
            "</tr>"
        )
    search_rows = [
        ("dense_top_k", ", ".join(str(x) for x in args["dense_top_ks"])),
        ("sparse_top_k", ", ".join(str(x) for x in args["sparse_top_ks"])),
        ("dense_threshold", ", ".join(str(x) for x in args["dense_thresholds"])),
        ("sparse_threshold", ", ".join(str(x) for x in args["sparse_thresholds"])),
        ("final_top_k / rrf_k", f"{args['final_top_k']} / {args['rrf_k']}"),
        ("融合算法", f"{fusion}(Reciprocal Rank Fusion)"),
        ("rerank", "未启用" if str(rerank).lower() in {"none", "false", "0"} else str(rerank)),
        ("golden", args["golden"]),
    ]
    search_html = "".join(
        f"<tr><td>{_esc(k)}</td><td class=\"gloss-desc\">{_esc(v)}</td></tr>"
        for k, v in search_rows
    )
    timestamp = _esc(payload["created_at"])
    dataset = _esc(payload["dataset"])
    title = f"Recall 参数搜索报告 · {dataset}"
    best_config = (
        f"dense_top_k={best.get('dense_top_k')}, sparse_top_k={best.get('sparse_top_k')}, "
        f"dense_threshold={best.get('dense_threshold')}, sparse_threshold={best.get('sparse_threshold')}"
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="head">
    <div>
      <div class="title">{title}</div>
      <div class="sub">生成时间 <code>{timestamp}</code> · 数据集 <b>{dataset}</b></div>
    </div>
    <div class="verdict v-pass">BEST CONFIG</div>
  </div>
  <div class="chips">{chips}</div>
  <div class="banner warn">本报告是参数搜索报告:融合算法为 <b>{_esc(fusion)}</b>,未启用 rerank;结果来自 {payload["n_samples"]} 条 golden query、{_esc(corpus_text)}、{config_count} 组参数的本地 RRF 复算。</div>
  <div class="cards">{card_html}</div>

  <section>
    <h2>推荐配置 <span class="badge">best</span></h2>
    <p class="h-note">排序准则:优先 recall@10,再看 hit_rate@10、MRR、MAP;同分偏向更小 sparse topK 和更高 sparse 阈值。</p>
    <table>
      <thead><tr><th>参数</th><th>值</th></tr></thead>
      <tbody>
        <tr><td>dense_top_k</td><td>{best.get('dense_top_k')}</td></tr>
        <tr><td>sparse_top_k</td><td>{best.get('sparse_top_k')}</td></tr>
        <tr><td>EVAL_RECALL_DENSE_SCORE_THRESHOLD</td><td>{best.get('dense_threshold')}</td></tr>
        <tr><td>EVAL_RECALL_SPARSE_SCORE_THRESHOLD</td><td>{best.get('sparse_threshold')}</td></tr>
      </tbody>
    </table>
  </section>

  <section>
    <h2>Top 20 参数组合 <span class="badge">720 configs</span></h2>
    <p class="h-note">所有指标均在 RRF 融合后 final_top_k=10 的结果上计算,无 rerank。</p>
    <table>
      <thead><tr><th>rank</th><th>dense_top_k</th><th>sparse_top_k</th><th>dense_th</th><th>sparse_th</th><th>recall@10</th><th>hit_rate@10</th><th>MAP</th><th>MRR</th></tr></thead>
      <tbody>{''.join(top_rows)}</tbody>
    </table>
  </section>

  <section>
    <h2>搜索空间与口径 <span class="badge">method</span></h2>
    <p class="h-note">先缓存 dense/sparse 最大候选池,再在本地按生产 RRF 公式枚举 topK 与阈值组合。</p>
    <table>
      <thead><tr><th>维度</th><th>取值 / 说明</th></tr></thead>
      <tbody>{search_html}</tbody>
    </table>
  </section>

  <div class="foot">
    <b>口径与说明:</b>本报告不是 rerank 评测;融合算法为 RRF(rrf_k={_esc(args['rrf_k'])}),无 rerank;
    final_top_k={_esc(args['final_top_k'])};样本量={payload['n_samples']} 条 golden query;语料规模={_esc(corpus_text)};
    参数组合={config_count} 组;分路失败样本={payload['failed_source_samples']}。
    最优配置为 <code>{_esc(best_config)}</code>。
  </div>
</div>
</body>
</html>
"""
