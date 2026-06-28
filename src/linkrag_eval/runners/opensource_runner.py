"""Track A 开源数据集端到端编排:段落灌 eval 库 → 标注转 doc 粒度 GoldenSample。

一次跑通「开源真实 query + 人工标注 → 可评测黄金集」:先 ``ingest_passages`` 把段落语料写进
eval namespace 并产出 ``source_id↔doc_id`` manifest,再 ``convert_to_golden`` 按该 manifest
把 pid 标注映射到库内 doc_id。``indexer`` 注入(cli 传真 EvalVectorIndexer,测试传 fake),
本模块零 rag。

已灌过库(manifest 已存在)可传 ``skip_ingest=True`` 跳过灌库、仅从 manifest 转换。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from linkrag_eval.golden.corpus_io import ManifestRecord, load_manifest
from linkrag_eval.golden.opensource.convert import (
    ConvertReport,
    convert_to_golden,
    write_golden_jsonl,
)
from linkrag_eval.golden.opensource.datasets import PassageCorpus, QueryJudgment
from linkrag_eval.golden.opensource.ingest import ingest_passages


@dataclass
class OpensourceRunReport:
    ingested_docs: int
    golden_path: str
    manifest_path: str
    convert: ConvertReport

    def summary(self) -> str:
        c = self.convert
        return (
            f"opensource: 灌库 {self.ingested_docs} 段 → 转换 {c.converted}/{c.total_queries} query"
            f"(无正例跳过 {c.skipped_no_positive} / 部分缺失 {c.skipped_partial_missing})\n"
            f"  golden: {self.golden_path}\n  manifest: {self.manifest_path}"
        )


async def run_opensource_golden(
    corpus: PassageCorpus,
    judgments: list[QueryJudgment],
    *,
    dataset_id: int,
    user_id: int,
    dataset_name: str,
    indexer: Any,
    manifest_path: str | Path,
    golden_out: str | Path,
    doc_id_base: int,
    graded: bool = False,
    limit: int | None = None,
    max_samples: int | None = None,
    batch: int = 25,
    skip_ingest: bool = False,
    progress: Callable[[str], None] | None = None,
) -> OpensourceRunReport:
    """灌段落语料(可跳过)→ 转标注 → 写 golden jsonl。返回 :class:`OpensourceRunReport`。"""
    if skip_ingest:
        manifest: list[ManifestRecord] = load_manifest(manifest_path)
        if progress:
            progress(f"跳过灌库,读已有 manifest {len(manifest)} 条")
    else:
        if progress:
            progress(f"灌库 {len(corpus)} 段(dataset_id={dataset_id}, doc_id_base={doc_id_base})...")
        manifest = await ingest_passages(
            corpus, dataset_id=dataset_id, indexer=indexer,
            manifest_path=manifest_path, doc_id_base=doc_id_base,
            limit=limit, batch=batch,
        )

    ingested = sum(1 for r in manifest if r.status == "success")
    samples, report = convert_to_golden(
        judgments, manifest, dataset_name=dataset_name, dataset_id=dataset_id,
        user_id=user_id, graded=graded, max_samples=max_samples,
    )
    if progress:
        progress(f"转换 {report.converted}/{report.total_queries} query → golden")
    write_golden_jsonl(samples, golden_out)

    return OpensourceRunReport(
        ingested_docs=ingested,
        golden_path=str(golden_out),
        manifest_path=str(manifest_path),
        convert=report,
    )
