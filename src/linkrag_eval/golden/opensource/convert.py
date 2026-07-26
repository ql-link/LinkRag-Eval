"""Track A 标注转换:query→相关段落 标注 + 灌库 manifest → GoldenSample(doc 粒度)。

零人工:开源数据集自带人工标注,转换只做 id 映射与过滤。
- 二值集(DuReader)→ expected_doc_ids,NDCG 走二值口径。
- 分级集(T2Ranking)→ 另填 relevance_grades(str(doc_id)→grade),
  NDCG 走分级口径(ndcg_graded),与二值分名汇报。

**解耦改动**:源版从生产 ``IngestRecord`` 逐条读 ``dataset_id``/``user_id``;eval 一次灌库
即一个 dataset + 一个路由 user(EVAL_USER_ID),故改用 eval 自有的 :class:`ManifestRecord`
(source_id/doc_id/status)并把 ``dataset_id``/``user_id`` 作为显式参数传入——不再依赖废弃的
``ingest_common.IngestRecord``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from pathlib import Path

from linkrag_eval.golden.corpus_io import ManifestRecord
from linkrag_eval.golden.provenance import QueryProvenance
from linkrag_eval.golden.opensource.datasets import QueryJudgment
from linkrag_eval.golden.schema import GoldenSample
from linkrag_eval.models import QuestionType


@dataclass
class ConvertReport:
    total_queries: int = 0
    converted: int = 0
    skipped_no_positive: int = 0       # 正例段落全部未灌入 → 跳过
    skipped_partial_missing: int = 0   # 部分正例缺失但仍可转换(reference 缩水,已计数)
    skipped_no_chunks: int = 0         # chunk 粒度时:正例 doc 已映射,但 eval 库无 chunk
    dropped_pids: list[str] = field(default_factory=list)
    reference_granularity: str = "doc"


def convert_to_golden(
    judgments: list[QueryJudgment],
    manifest: list[ManifestRecord],
    *,
    dataset_name: str,
    dataset_id: int,
    user_id: int,
    graded: bool = False,
    max_samples: int | None = None,
    reference_granularity: Literal["doc", "chunk"] = "doc",
    chunks_by_doc: dict[int, list[str]] | None = None,
) -> tuple[list[GoldenSample], ConvertReport]:
    """按 manifest 把 pid 标注映射到库内 reference,产出 GoldenSample。

    ``dataset_id``/``user_id`` 为本次灌库的 dataset 与路由 user(eval 一次灌库同源)。
    ``reference_granularity="chunk"`` 时,用 ``chunks_by_doc`` 把正例 doc 收缩成
    ``expected_chunk_ids``;doc_id 仍保留作来源追溯,但指标会优先按 chunk 粒度计算。
    """
    if reference_granularity not in {"doc", "chunk"}:
        raise ValueError("reference_granularity 必须是 doc 或 chunk")
    if reference_granularity == "chunk" and chunks_by_doc is None:
        raise ValueError("chunk 粒度转换必须提供 chunks_by_doc")
    doc_by_pid = {r.source_id: r for r in manifest if r.status == "success"}
    report = ConvertReport(
        total_queries=len(judgments),
        reference_granularity=reference_granularity,
    )
    samples: list[GoldenSample] = []

    for j in judgments:
        if max_samples is not None and len(samples) >= max_samples:
            break
        positives = j.positive_pids
        mapped = [(pid, doc_by_pid[pid]) for pid in positives if pid in doc_by_pid]
        missing = [pid for pid in positives if pid not in doc_by_pid]
        if not mapped:
            report.skipped_no_positive += 1
            report.dropped_pids.extend(missing)
            continue
        if missing:
            report.skipped_partial_missing += 1
            report.dropped_pids.extend(missing)

        records = [r for _, r in mapped]
        doc_ids = sorted({r.doc_id for r in records})
        chunk_ids: list[str] = []
        if reference_granularity == "chunk":
            for doc_id in doc_ids:
                chunk_ids.extend((chunks_by_doc or {}).get(doc_id, []))
            chunk_ids = sorted(dict.fromkeys(chunk_ids))
            if not chunk_ids:
                report.skipped_no_chunks += 1
                continue
        grades = None
        if graded:
            if reference_granularity == "chunk":
                grades = {}
                for pid, r in mapped:
                    grade = j.judged[pid]
                    if grade <= 0:
                        continue
                    for chunk_id in (chunks_by_doc or {}).get(r.doc_id, []):
                        grades[str(chunk_id)] = grade
            else:
                grades = {
                    str(r.doc_id): j.judged[pid] for pid, r in mapped if j.judged[pid] > 0
                }
        samples.append(
            GoldenSample(
                id=f"{dataset_name}-{j.qid}",
                query=j.query,
                user_id=user_id,
                dataset_ids=[dataset_id],
                expected_chunk_ids=chunk_ids,
                expected_doc_ids=doc_ids,
                golden_answer=None,
                type=QuestionType.KEYWORD,  # 开源真实 query 不带类型标注,统一入 keyword 桶
                note=f"opensource:{dataset_name} qid={j.qid}"
                + ("; graded" if graded else "")
                + (f"; missing_pids={missing}" if missing else ""),
                relevance_grades=grades,
                provenance=QueryProvenance(
                    source_kind="opensource",
                    source_name=dataset_name,
                    source_record_id=str(j.qid),
                    domain="general",
                    scenario="opensource_retrieval",
                    canonical_query=j.query,
                    dataset_version="c-mteb-main",
                    license="Apache-2.0",
                ),
            )
        )
        report.converted += 1
    return samples, report


def write_golden_jsonl(samples: list[GoldenSample], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for s in samples:
            fh.write(s.to_jsonl_line() + "\n")
    return path
