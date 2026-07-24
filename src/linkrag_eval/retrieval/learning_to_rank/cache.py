"""Resumable live candidate cache for learning-to-rank experiments."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Any

from linkrag_eval.golden.schema import GoldenSample
from linkrag_eval.retrieval.candidate_routing import (
    FROZEN_ROUTING_DEPTHS,
    CandidateDepths,
    classify_candidate_query,
    depths_for_query,
)


ROUTES = ("dense", "sparse", "bm25")


def _load_latest(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    latest: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            latest[str(row["sample_id"])] = row
    return latest


def _scenario(sample: GoldenSample) -> str:
    for part in sample.note.split(";"):
        key, _, value = part.strip().partition("=")
        if key == "type_hint":
            return value.strip()
    return sample.type.value


async def cache_ltr_candidates(
    samples: list[GoldenSample],
    *,
    settings: Any,
    out: Path,
    concurrency: int = 4,
    retries: int = 5,
    use_query_routing: bool = False,
    progress: Any | None = None,
) -> dict[str, Any]:
    """Fetch max route candidates and persist progress after every query."""
    from linkrag_eval.retrieval.recall_factory import build_eval_recall_pipeline

    partial = out.with_suffix(out.suffix + ".partial")
    latest = _load_latest(out)
    latest.update(_load_latest(partial))
    pipeline = build_eval_recall_pipeline(
        settings=settings,
        dense_score_threshold=0.0,
        sparse_score_threshold=0.0,
    )
    retrievers = {retriever.source: retriever for retriever in pipeline._retrievers}
    fallback_depths = CandidateDepths(
        dense=settings.recall_dense_top_k,
        sparse=settings.recall_sparse_top_k,
        bm25=settings.recall_bm25_top_k,
    )

    def sample_depths(sample: GoldenSample) -> CandidateDepths:
        return depths_for_query(sample.query) if use_query_routing else fallback_depths

    def reusable(sample: GoldenSample, row: dict[str, Any]) -> bool:
        if row.get("failed_sources"):
            return False
        expected = sample_depths(sample).as_dict()
        actual = row.get("route_top_ks")
        if actual is None:
            return not use_query_routing and expected == fallback_depths.as_dict()
        return actual == expected

    clean_existing = {
        sample.id: latest[sample.id]
        for sample in samples
        if sample.id in latest and reusable(sample, latest[sample.id])
    }
    pending = [sample for sample in samples if sample.id not in clean_existing]
    sem = asyncio.Semaphore(max(1, concurrency))
    write_lock = asyncio.Lock()
    completed = 0
    partial.parent.mkdir(parents=True, exist_ok=True)

    async def route(
        sample: GoldenSample,
        source: str,
        top_ks: dict[str, int],
    ) -> tuple[list[dict[str, Any]], bool]:
        retriever = retrievers.get(source)
        if retriever is None:
            return [], True
        for attempt in range(max(1, retries)):
            try:
                hits = await retriever.recall(
                    sample.query,
                    sample.dataset_ids,
                    None,
                    user_id=sample.user_id,
                    top_k=top_ks[source],
                    score_threshold_override=0.0,
                )
                return [
                    {
                        "chunk_id": str(hit.chunk_id),
                        "doc_id": int(hit.doc_id),
                        "dataset_id": int(hit.dataset_id),
                        "score": float(hit.score),
                        "rank": rank,
                    }
                    for rank, hit in enumerate(hits)
                ], False
            except Exception:
                if attempt + 1 < max(1, retries):
                    await asyncio.sleep(min(8.0, 0.5 * 2**attempt))
        return [], True

    async def one(sample: GoldenSample) -> dict[str, Any]:
        nonlocal completed
        routing_bucket = classify_candidate_query(sample.query)
        top_ks = sample_depths(sample).as_dict()
        async with sem:
            results = await asyncio.gather(*(route(sample, source, top_ks) for source in ROUTES))
        routes = {source: result[0] for source, result in zip(ROUTES, results)}
        failed = [source for source, result in zip(ROUTES, results) if result[1]]
        row = {
            "sample_id": sample.id,
            "query": sample.query,
            "scenario": _scenario(sample),
            "routing_bucket": routing_bucket,
            "route_top_ks": top_ks,
            "user_id": sample.user_id,
            "dataset_ids": sample.dataset_ids,
            "expected_chunk_ids": sample.expected_chunk_ids,
            "expected_doc_ids": sample.expected_doc_ids,
            "routes": routes,
            "failed_sources": failed,
        }
        async with write_lock:
            with partial.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                handle.flush()
        completed += 1
        if progress and (completed % 10 == 0 or completed == len(pending)):
            progress(f"ltr candidates {completed}/{len(pending)}")
        return row

    fetched = await asyncio.gather(*(one(sample) for sample in pending))
    latest.update({row["sample_id"]: row for row in fetched})
    ordered = [latest[sample.id] for sample in samples if sample.id in latest]
    temp = out.with_suffix(out.suffix + ".tmp")
    temp.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in ordered),
        encoding="utf-8",
    )
    temp.replace(out)
    failed_rows = [row for row in ordered if row.get("failed_sources")]
    report = {
        "samples": len(samples),
        "cached": len(ordered),
        "resumed": len(clean_existing),
        "fetched": len(fetched),
        "failed_samples": len(failed_rows),
        "failed_sample_ids": [row["sample_id"] for row in failed_rows],
        "query_routing": use_query_routing,
        "global_fallback_top_ks": fallback_depths.as_dict(),
        "routing_profiles": (
            {key: value.as_dict() for key, value in FROZEN_ROUTING_DEPTHS.items()}
            if use_query_routing
            else {}
        ),
        "routing_counts": dict(Counter(row.get("routing_bucket", "unknown") for row in ordered)),
        "average_theoretical_candidate_budget": (
            sum(sum(row["route_top_ks"].values()) for row in ordered) / len(ordered)
            if ordered
            else 0.0
        ),
        "output": str(out),
    }
    report_path = out.with_name(out.stem + "_report.json")
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if not failed_rows:
        partial.unlink(missing_ok=True)
    return report
