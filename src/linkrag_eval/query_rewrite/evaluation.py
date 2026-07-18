"""Paired original-vs-rewritten multi-route retrieval evaluation."""

from __future__ import annotations

import asyncio
import html
import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

from linkrag_eval.golden.schema import GoldenSample
from linkrag_eval.models import Layer, RankedHit, StageOutput
from linkrag_eval.query_rewrite.schema import DEFAULT_WEIGHTS, ROUTES, QueryRewritePlan
from linkrag_eval.retrieval.tuning import RouteHit, weighted_score_fuse


def load_rewrite_plans(path: str | Path) -> dict[str, QueryRewritePlan]:
    plans: dict[str, QueryRewritePlan] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        plan = QueryRewritePlan.from_dict(json.loads(line))
        if plan.sample_id in plans:
            raise ValueError(f"duplicate rewrite plan:{plan.sample_id}")
        plans[plan.sample_id] = plan
    return plans


def _merge_route_hits(groups: Iterable[list[RouteHit]]) -> list[RouteHit]:
    by_chunk: dict[str, RouteHit] = {}
    for hits in groups:
        for hit in hits:
            current = by_chunk.get(hit.chunk_id)
            if current is None or hit.score > current.score:
                by_chunk[hit.chunk_id] = hit
    return sorted(by_chunk.values(), key=lambda hit: (-hit.score, hit.chunk_id))


def protect_candidates(
    ranked: list[RankedHit],
    per_source: dict[str, list[RouteHit]],
    protected: dict[str, int],
    *,
    final_top_k: int,
    extra_protected: Iterable[str] = (),
) -> list[RankedHit]:
    """Ensure selected route heads survive final truncation, then retain fused order."""
    if final_top_k <= 0:
        return []
    full_rank = {hit.chunk_id: index for index, hit in enumerate(ranked)}
    selected = [hit.chunk_id for hit in ranked[:final_top_k]]
    required: list[str] = list(dict.fromkeys(extra_protected))
    for source in ROUTES:
        for hit in per_source.get(source, [])[: max(0, protected.get(source, 0))]:
            if hit.chunk_id not in required:
                required.append(hit.chunk_id)
    required = required[:final_top_k]
    required_set = set(required)
    for chunk_id in required:
        if chunk_id in selected:
            continue
        if len(selected) < final_top_k:
            selected.append(chunk_id)
            continue
        replace_at = next(
            (
                index
                for index in range(len(selected) - 1, -1, -1)
                if selected[index] not in required_set
            ),
            None,
        )
        if replace_at is None:
            break
        selected[replace_at] = chunk_id
    chosen = {chunk_id for chunk_id in selected}
    ordered = [hit for hit in ranked if hit.chunk_id in chosen]
    ordered.sort(key=lambda hit: full_rank[hit.chunk_id])
    return [replace(hit, rank=index) for index, hit in enumerate(ordered[:final_top_k])]


class PairedRewriteEvaluator:
    def __init__(
        self,
        *,
        settings: Any,
        final_top_k: int = 10,
        include_original: bool = True,
        retries: int = 3,
        use_plan_weights: bool = True,
        use_candidate_protection: bool = True,
        original_protected_top_k: int = 5,
    ) -> None:
        from linkrag_eval.retrieval.recall_factory import build_eval_recall_pipeline

        self.settings = settings
        self.final_top_k = final_top_k
        self.include_original = include_original
        self.retries = max(1, retries)
        self.use_plan_weights = use_plan_weights
        self.use_candidate_protection = use_candidate_protection
        self.original_protected_top_k = min(final_top_k, max(0, original_protected_top_k))
        pipeline = build_eval_recall_pipeline(
            settings=settings,
            dense_score_threshold=0.0,
            sparse_score_threshold=0.0,
        )
        self.retrievers = {retriever.source: retriever for retriever in pipeline._retrievers}
        self.top_ks = {
            "dense": settings.recall_dense_top_k,
            "sparse": settings.recall_sparse_top_k,
            "bm25": settings.recall_bm25_top_k,
        }
        self.thresholds = {
            "dense": settings.recall_dense_score_threshold,
            "sparse": settings.recall_sparse_score_threshold,
            "bm25": 0.0,
        }

    async def _route(
        self,
        sample: GoldenSample,
        *,
        source: str,
        query: str,
    ) -> tuple[list[RouteHit], bool]:
        retriever = self.retrievers.get(source)
        if retriever is None:
            return [], True
        for attempt in range(self.retries):
            try:
                hits = await retriever.recall(
                    query,
                    sample.dataset_ids,
                    None,
                    user_id=sample.user_id,
                    top_k=self.top_ks[source],
                    score_threshold_override=self.thresholds[source],
                )
                return [
                    RouteHit(
                        chunk_id=str(hit.chunk_id),
                        doc_id=int(hit.doc_id),
                        dataset_id=int(hit.dataset_id),
                        score=float(hit.score),
                        source=source,
                    )
                    for hit in hits
                ], False
            except Exception:
                if attempt + 1 == self.retries:
                    return [], True
                await asyncio.sleep(0.5 * (attempt + 1))
        return [], True

    async def _fetch_queries(
        self,
        sample: GoldenSample,
        route_queries: dict[str, list[str]],
    ) -> tuple[dict[str, list[RouteHit]], list[str], int]:
        started = time.monotonic()
        per_source: dict[str, list[RouteHit]] = {}
        failed: list[str] = []

        async def _source(source: str) -> tuple[str, list[RouteHit], bool]:
            unique_queries = list(
                dict.fromkeys(q.strip() for q in route_queries[source] if q.strip())
            )
            results = await asyncio.gather(
                *(self._route(sample, source=source, query=query) for query in unique_queries)
            )
            route_failed = any(failed_call for _hits, failed_call in results)
            return source, _merge_route_hits(hits for hits, _failed in results), route_failed

        for source, hits, route_failed in await asyncio.gather(
            *[_source(route) for route in ROUTES]
        ):
            per_source[source] = hits
            if route_failed:
                failed.append(source)
        return per_source, failed, int((time.monotonic() - started) * 1000)

    def _build_output(
        self,
        sample: GoldenSample,
        per_source: dict[str, list[RouteHit]],
        *,
        failed: list[str],
        elapsed_ms: int,
        route_queries: dict[str, list[str]],
        weights: dict[str, float],
        protected: dict[str, int],
        extra_protected: Iterable[str] = (),
    ) -> StageOutput:
        full = weighted_score_fuse(
            per_source,
            final_top_k=sum(self.top_ks.values()),
            weights=weights,
        )
        ranked = protect_candidates(
            full,
            per_source,
            protected,
            final_top_k=self.final_top_k,
            extra_protected=extra_protected,
        )
        return StageOutput(
            layer=Layer.RETRIEVAL,
            query=sample.query,
            ranked=ranked,
            elapsed_ms=elapsed_ms,
            per_source_counts={source: len(hits) for source, hits in per_source.items()},
            failed_sources=failed,
            raw={"route_queries": route_queries},
        )

    async def run_pair(
        self,
        sample: GoldenSample,
        plan: QueryRewritePlan,
    ) -> tuple[StageOutput, StageOutput]:
        original_queries = {route: [sample.query] for route in ROUTES}
        rewritten_only_queries = {
            route: (
                [plan.route_query(route)]
                if plan.route_query(route).strip() != sample.query.strip()
                else []
            )
            for route in ROUTES
        }
        original_hits, original_failed, original_elapsed = await self._fetch_queries(
            sample,
            original_queries,
        )
        rewritten_hits, rewritten_failed, rewritten_elapsed = await self._fetch_queries(
            sample,
            rewritten_only_queries,
        )
        combined_hits = {
            route: _merge_route_hits(
                (
                    [original_hits[route], rewritten_hits[route]]
                    if self.include_original
                    else [rewritten_hits[route] or original_hits[route]]
                )
            )
            for route in ROUTES
        }
        rewritten_route_queries = {
            route: (
                [sample.query, plan.route_query(route)]
                if self.include_original
                else [plan.route_query(route)]
            )
            for route in ROUTES
        }
        original = self._build_output(
            sample,
            original_hits,
            failed=original_failed,
            elapsed_ms=original_elapsed,
            route_queries=original_queries,
            weights=dict(DEFAULT_WEIGHTS),
            protected={route: 0 for route in ROUTES},
        )
        rewritten = self._build_output(
            sample,
            combined_hits,
            failed=sorted(set(original_failed) | set(rewritten_failed)),
            elapsed_ms=original_elapsed + rewritten_elapsed,
            route_queries=rewritten_route_queries,
            weights=plan.weights if self.use_plan_weights else dict(DEFAULT_WEIGHTS),
            protected=(
                plan.protected_candidates
                if self.use_candidate_protection
                else {route: 0 for route in ROUTES}
            ),
            extra_protected=[
                hit.chunk_id for hit in original.ranked[: self.original_protected_top_k]
            ],
        )
        return original, rewritten


def _sample_metrics(sample: GoldenSample, output: StageOutput, top_k: int) -> dict[str, float]:
    relevant = set(sample.expected_chunk_ids)
    ranked = [hit.chunk_id for hit in output.ranked[:top_k]]
    hits = [chunk_id for chunk_id in ranked if chunk_id in relevant]
    first_rank = next(
        (index for index, chunk_id in enumerate(ranked, 1) if chunk_id in relevant), None
    )
    return {
        "recall_at_10": len(set(hits)) / len(relevant) if relevant else 0.0,
        "hit_at_10": 1.0 if hits else 0.0,
        "mrr": 1.0 / first_rank if first_rank else 0.0,
    }


async def evaluate_rewrite_pairs(
    samples: Iterable[GoldenSample],
    *,
    plans: dict[str, QueryRewritePlan],
    evaluator: PairedRewriteEvaluator,
    out_dir: Path,
    progress: Any | None = None,
) -> dict[str, Any]:
    items = list(samples)
    rows: list[dict[str, Any]] = []
    for index, sample in enumerate(items, 1):
        plan = plans.get(sample.id)
        if plan is None:
            raise ValueError(f"missing rewrite plan:{sample.id}")
        if plan.original_query != sample.query:
            raise ValueError(f"original query mismatch:{sample.id}")
        original, rewritten = await evaluator.run_pair(sample, plan)
        original_metrics = _sample_metrics(sample, original, evaluator.final_top_k)
        rewritten_metrics = _sample_metrics(sample, rewritten, evaluator.final_top_k)
        rows.append(
            {
                "sample_id": sample.id,
                "query_type": plan.query_type,
                "original_query": sample.query,
                "queries": {route: plan.route_query(route) for route in ROUTES},
                "weights": plan.weights,
                "protected_candidates": plan.protected_candidates,
                "original": original_metrics,
                "rewritten": rewritten_metrics,
                "transition": (
                    "gained"
                    if not original_metrics["hit_at_10"] and rewritten_metrics["hit_at_10"]
                    else "lost"
                    if original_metrics["hit_at_10"] and not rewritten_metrics["hit_at_10"]
                    else "kept_hit"
                    if original_metrics["hit_at_10"]
                    else "kept_miss"
                ),
                "original_failed_sources": original.failed_sources,
                "rewritten_failed_sources": rewritten.failed_sources,
                "original_elapsed_ms": original.elapsed_ms,
                "rewritten_elapsed_ms": rewritten.elapsed_ms,
            }
        )
        if progress and (index % 10 == 0 or index == len(items)):
            progress(f"paired rewrite eval {index}/{len(items)}")

    def aggregate(selected: list[dict[str, Any]]) -> dict[str, Any]:
        def mean(side: str, metric: str) -> float:
            return sum(row[side][metric] for row in selected) / len(selected) if selected else 0.0

        original = {
            metric: mean("original", metric) for metric in ("recall_at_10", "hit_at_10", "mrr")
        }
        rewritten = {
            metric: mean("rewritten", metric) for metric in ("recall_at_10", "hit_at_10", "mrr")
        }
        return {
            "samples": len(selected),
            "original": original,
            "rewritten": rewritten,
            "delta": {
                metric: rewritten[metric] - original[metric]
                for metric in ("recall_at_10", "hit_at_10", "mrr")
            },
            "transitions": {
                name: sum(row["transition"] == name for row in selected)
                for name in ("gained", "lost", "kept_hit", "kept_miss")
            },
        }

    aggregate_all = aggregate(rows)
    clean_rows = [
        row
        for row in rows
        if not row["original_failed_sources"] and not row["rewritten_failed_sources"]
    ]
    failed_original = sum(bool(row["original_failed_sources"]) for row in rows)
    failed_rewritten = sum(bool(row["rewritten_failed_sources"]) for row in rows)
    payload = {
        "samples": len(rows),
        "include_original": evaluator.include_original,
        "parameters": {
            "final_top_k": evaluator.final_top_k,
            "route_top_ks": evaluator.top_ks,
            "route_thresholds": evaluator.thresholds,
            "default_weights": DEFAULT_WEIGHTS,
            "use_plan_weights": evaluator.use_plan_weights,
            "use_candidate_protection": evaluator.use_candidate_protection,
            "original_protected_top_k": evaluator.original_protected_top_k,
        },
        "quality": {
            "clean": failed_original == 0 and failed_rewritten == 0,
            "original_failed_samples": failed_original,
            "rewritten_failed_samples": failed_rewritten,
        },
        "original": aggregate_all["original"],
        "rewritten": aggregate_all["rewritten"],
        "delta": aggregate_all["delta"],
        "transitions": aggregate_all["transitions"],
        "clean_subset": aggregate(clean_rows),
        "rows": rows,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "query_rewrite_pair_report.json"
    html_path = out_dir / "query_rewrite_pair_report.html"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    html_path.write_text(_render_html(payload), encoding="utf-8")
    return payload


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _render_html(payload: dict[str, Any]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(row['sample_id'])}</td>"
        f"<td>{html.escape(row['query_type'])}</td>"
        f"<td>{html.escape(row['transition'])}</td>"
        f"<td>{_pct(row['original']['hit_at_10'])}</td>"
        f"<td>{_pct(row['rewritten']['hit_at_10'])}</td>"
        f"<td>{html.escape(row['original_query'])}</td>"
        "</tr>"
        for row in payload["rows"]
    )
    quality = "clean" if payload["quality"]["clean"] else "non-clean"
    clean_subset = payload["clean_subset"]
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Query Rewrite Pair Report</title><style>
body{{font:15px/1.6 system-ui;margin:0;background:#f6f8fa;color:#17212b}}
main{{max-width:1180px;margin:24px auto;background:#fff;padding:30px;border:1px solid #d0d7de}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}.card{{border:1px solid #d0d7de;padding:12px}}
strong{{display:block;font-size:24px}}table{{width:100%;border-collapse:collapse;margin-top:16px}}
th,td{{border:1px solid #d0d7de;padding:8px;text-align:left}}th{{background:#eef3f7}}
.warn{{background:#fff8c5;padding:10px}}@media(max-width:760px){{main{{margin:0;border:0}}.grid{{grid-template-columns:1fr}}}}
</style></head><body><main><h1>Query 重写配对评测</h1>
<p class="warn">运行质量：<b>{quality}</b>。只有 original/rewritten 均无分路失败时才可采信净提升。</p>
<div class="grid"><div class="card">Original Hit@10<strong>{_pct(payload["original"]["hit_at_10"])}</strong></div>
<div class="card">Rewritten Hit@10<strong>{_pct(payload["rewritten"]["hit_at_10"])}</strong></div>
<div class="card">净变化<strong>{_pct(payload["delta"]["hit_at_10"])}</strong></div></div>
<p>新增命中 {payload["transitions"]["gained"]}；丢失命中 {payload["transitions"]["lost"]}；
保持命中 {payload["transitions"]["kept_hit"]}；保持未命中 {payload["transitions"]["kept_miss"]}。</p>
<h2>无分路失败子集</h2><p>n={clean_subset["samples"]}；
Original Hit@10={_pct(clean_subset["original"]["hit_at_10"])}；
Rewritten Hit@10={_pct(clean_subset["rewritten"]["hit_at_10"])}；
净变化={_pct(clean_subset["delta"]["hit_at_10"])}；
新增命中={clean_subset["transitions"]["gained"]}，丢失命中={clean_subset["transitions"]["lost"]}。</p>
<table><thead><tr><th>ID</th><th>类型</th><th>变化</th><th>原始</th><th>重写</th><th>原始Query</th></tr></thead>
<tbody>{rows}</tbody></table></main></body></html>"""
