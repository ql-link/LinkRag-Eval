"""Golden V2 规模化扩容计划生成。

本模块只生成可审计的批次计划、命令草稿和成本估算,不连接生产或 eval 活栈。
实际生成语料仍由离线 Spark agent 完成,实际入库仍走现有 ingest / backfill CLI。
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ScaleBatch:
    batch_index: int
    dataset_id: int
    target_chunks: int
    bundle_dir: str
    chunks_path: str
    collection_path: str
    manifest_path: str
    commands: list[str]


@dataclass(frozen=True)
class ScaleEstimate:
    target_chunks: int
    existing_chunks: int
    missing_chunks: int
    batch_count: int
    avg_chars_per_chunk: int
    estimated_corpus_chars: int
    estimated_corpus_tokens: int
    query_seed_target: int
    expected_candidates_per_query: int
    estimated_judge_items: int
    estimated_judge_input_tokens: int
    estimated_judge_output_tokens: int
    estimated_alt_embedding_items: int
    estimated_alt_embedding_batches: int


@dataclass(frozen=True)
class ScalePlanReport:
    stage: str
    target_chunks: int
    batch_chunks: int
    dataset_id_start: int
    dataset_ids: list[int]
    batches: list[ScaleBatch]
    estimate: ScaleEstimate
    plan_path: str
    markdown_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["batches"] = [asdict(batch) for batch in self.batches]
        data["estimate"] = asdict(self.estimate)
        return data

    def summary(self) -> str:
        return (
            f"Golden V2 扩容计划: stage={self.stage} target_chunks={self.target_chunks} "
            f"missing={self.estimate.missing_chunks} batches={len(self.batches)} "
            f"judge_items≈{self.estimate.estimated_judge_items}"
        )


def build_scale_plan(
    *,
    stage: str,
    target_chunks: int,
    out_dir: str | Path,
    dataset_id_start: int,
    batch_chunks: int = 5000,
    existing_chunks: int = 0,
    query_seed_target: int = 1000,
    route_top_n: int = 50,
    random_n: int = 20,
    max_candidates_per_query: int | None = None,
    avg_chars_per_chunk: int = 900,
    chars_per_token: float = 2.0,
    judge_input_tokens_per_candidate: int = 900,
    judge_output_tokens_per_candidate: int = 120,
    alt_embedding_batch: int = 100,
    include_alt_embedding: bool = True,
    write_markdown: bool = True,
) -> ScalePlanReport:
    if target_chunks <= 0:
        raise ValueError("target_chunks 必须大于 0")
    if batch_chunks <= 0:
        raise ValueError("batch_chunks 必须大于 0")
    if dataset_id_start <= 0:
        raise ValueError("dataset_id_start 必须大于 0")
    if existing_chunks < 0:
        raise ValueError("existing_chunks 不能为负数")
    if avg_chars_per_chunk <= 0:
        raise ValueError("avg_chars_per_chunk 必须大于 0")
    if chars_per_token <= 0:
        raise ValueError("chars_per_token 必须大于 0")
    if query_seed_target <= 0:
        raise ValueError("query_seed_target 必须大于 0")

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    missing = max(0, target_chunks - existing_chunks)
    batch_count = math.ceil(missing / batch_chunks) if missing else 0
    stage_slug = _slug(stage)
    batches: list[ScaleBatch] = []
    dataset_ids: list[int] = []
    for index in range(batch_count):
        dataset_id = dataset_id_start + index
        dataset_ids.append(dataset_id)
        target = min(batch_chunks, missing - index * batch_chunks)
        batch_dir = out / f"{stage_slug}_batch_{index + 1:04d}_ds{dataset_id}"
        bundle_dir = batch_dir / "spark_bundle"
        chunks_path = batch_dir / "chunk_records.jsonl"
        collection_path = batch_dir / "collection.tsv"
        manifest_path = batch_dir / "manifest.jsonl"
        commands = _batch_commands(
            dataset_id=dataset_id,
            batch_dir=batch_dir,
            bundle_dir=bundle_dir,
            chunks_path=chunks_path,
            collection_path=collection_path,
            manifest_path=manifest_path,
        )
        batches.append(
            ScaleBatch(
                batch_index=index + 1,
                dataset_id=dataset_id,
                target_chunks=target,
                bundle_dir=str(bundle_dir),
                chunks_path=str(chunks_path),
                collection_path=str(collection_path),
                manifest_path=str(manifest_path),
                commands=commands,
            )
        )

    expected_candidates = _expected_candidates_per_query(
        route_top_n=route_top_n,
        random_n=random_n,
        include_alt_embedding=include_alt_embedding,
        cap=max_candidates_per_query,
    )
    judge_items = query_seed_target * expected_candidates
    corpus_chars = target_chunks * avg_chars_per_chunk
    estimate = ScaleEstimate(
        target_chunks=target_chunks,
        existing_chunks=existing_chunks,
        missing_chunks=missing,
        batch_count=batch_count,
        avg_chars_per_chunk=avg_chars_per_chunk,
        estimated_corpus_chars=corpus_chars,
        estimated_corpus_tokens=math.ceil(corpus_chars / chars_per_token),
        query_seed_target=query_seed_target,
        expected_candidates_per_query=expected_candidates,
        estimated_judge_items=judge_items,
        estimated_judge_input_tokens=judge_items * judge_input_tokens_per_candidate,
        estimated_judge_output_tokens=judge_items * judge_output_tokens_per_candidate,
        estimated_alt_embedding_items=target_chunks if include_alt_embedding else 0,
        estimated_alt_embedding_batches=(
            math.ceil(target_chunks / max(1, alt_embedding_batch)) if include_alt_embedding else 0
        ),
    )
    report = ScalePlanReport(
        stage=stage,
        target_chunks=target_chunks,
        batch_chunks=batch_chunks,
        dataset_id_start=dataset_id_start,
        dataset_ids=dataset_ids,
        batches=batches,
        estimate=estimate,
        plan_path=str(out / "scale_plan.json"),
        markdown_path=str(out / "scale_plan.md") if write_markdown else None,
    )
    Path(report.plan_path).write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if report.markdown_path:
        Path(report.markdown_path).write_text(_to_markdown(report), encoding="utf-8")
    _write_batch_specs(out / "batch_specs.jsonl", batches)
    return report


def count_jsonl(path: str | Path) -> int:
    total = 0
    with Path(path).open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                total += 1
    return total


def _expected_candidates_per_query(
    *,
    route_top_n: int,
    random_n: int,
    include_alt_embedding: bool,
    cap: int | None,
) -> int:
    route_count = 4 if include_alt_embedding else 3
    raw = route_count * max(0, route_top_n) + max(0, random_n)
    if cap is not None:
        raw = min(raw, max(0, cap))
    return raw


def _batch_commands(
    *,
    dataset_id: int,
    batch_dir: Path,
    bundle_dir: Path,
    chunks_path: Path,
    collection_path: Path,
    manifest_path: Path,
) -> list[str]:
    return [
        (
            "linkrag-eval golden-v2 spark-import "
            f"--bundle {bundle_dir / 'bundle_manifest.json'} "
            f"--out {batch_dir / 'query_seeds.jsonl'} "
            f"--hard-out {batch_dir / 'hard_case_seeds.jsonl'} "
            f"--rewrite-out {batch_dir / 'rewrite_seeds.jsonl'} "
            f"--corpus-out {batch_dir / 'corpus_blueprints.jsonl'} "
            f"--chunks-out {chunks_path} "
            f"--report-out {batch_dir / 'spark_import_report.json'}"
        ),
        (
            "linkrag-eval golden-v2 spark-corpus-export "
            f"--chunks {chunks_path} "
            f"--collection {collection_path} "
            f"--manifest {manifest_path} "
            f"--dataset-id {dataset_id} "
            f"--report-out {batch_dir / 'corpus_export_report.json'}"
        ),
        (
            "linkrag-eval ingest "
            f"--dataset-id {dataset_id} "
            f"--collection {collection_path} "
            f"--manifest {manifest_path} "
            f"--name golden_v2_scale_{dataset_id} "
            "--source-type synth --batch 50"
        ),
        (
            "linkrag-eval bm25-backfill "
            f"--dataset-ids {dataset_id} --batch 1000"
        ),
        (
            "linkrag-eval golden-v2 alt-embed-backfill "
            f"--dataset-ids {dataset_id} --batch 100"
        ),
    ]


def _write_batch_specs(path: Path, batches: list[ScaleBatch]) -> None:
    rows = [
        {
            "batch_index": batch.batch_index,
            "dataset_id": batch.dataset_id,
            "target_chunks": batch.target_chunks,
            "bundle_dir": batch.bundle_dir,
            "notes": (
                "由 Spark 子 Agent 按 target_chunks 生成 corpus_blueprints/chunk_records/"
                "query_seeds/hard_case_seeds/rewrite_seeds,禁止从目标 chunk 直接反推 query。"
            ),
        }
        for batch in batches
    ]
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _to_markdown(report: ScalePlanReport) -> str:
    estimate = report.estimate
    dataset_ids = ",".join(str(x) for x in report.dataset_ids) or "(无新增)"
    lines = [
        "# Golden V2 Scale Plan",
        "",
        f"- stage: `{report.stage}`",
        f"- target_chunks: {report.target_chunks}",
        f"- existing_chunks: {estimate.existing_chunks}",
        f"- missing_chunks: {estimate.missing_chunks}",
        f"- batch_chunks: {report.batch_chunks}",
        f"- batch_count: {estimate.batch_count}",
        f"- dataset_ids: `{dataset_ids}`",
        "",
        "## Estimate",
        "",
        f"- corpus chars: {estimate.estimated_corpus_chars}",
        f"- corpus tokens: {estimate.estimated_corpus_tokens}",
        f"- query seeds: {estimate.query_seed_target}",
        f"- candidates/query: {estimate.expected_candidates_per_query}",
        f"- judge items: {estimate.estimated_judge_items}",
        f"- judge input tokens: {estimate.estimated_judge_input_tokens}",
        f"- judge output tokens: {estimate.estimated_judge_output_tokens}",
        f"- alt embedding items: {estimate.estimated_alt_embedding_items}",
        f"- alt embedding batches: {estimate.estimated_alt_embedding_batches}",
        "",
        "## Batch Commands",
        "",
    ]
    for batch in report.batches:
        lines.extend(
            [
                f"### Batch {batch.batch_index} / dataset {batch.dataset_id}",
                "",
                f"- target_chunks: {batch.target_chunks}",
                "",
                "```bash",
                *batch.commands,
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def _slug(value: str) -> str:
    text = "".join(ch.lower() if ch.isalnum() else "_" for ch in value.strip())
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_") or "scale"
