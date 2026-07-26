"""Track A 灌库:开源数据集段落 → eval 评测租户(走 eval 灌库承重墙)。

**解耦改动**:源版经废弃 ``ingest_common.CorpusIngestor``(全栈 ParseTaskPipeline + 生产
ORM/MinIO/MQ)灌库;这里改走 :class:`~linkrag_eval.store.indexer.EvalVectorIndexer`——
段落=一个 chunk(开源按 **doc 粒度** 评测,无需再切分),算 dense/sparse → eval 前缀 Qdrant
+ 独立库 MySQL,零生产写依赖。

粒度对齐:**以段落为 ingestion 单元**(一个段落 → 一个 doc_id),doc 粒度用
``expected_doc_ids`` 评测。段落→doc_id 映射写 manifest 并校验一一对应,供
``opensource.convert`` 消费。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from linkrag_eval.golden.corpus_io import ManifestRecord, write_manifest
from linkrag_eval.golden.opensource.datasets import PassageCorpus
from linkrag_eval.store.indexer import EvalPassage


async def ingest_passages(
    corpus: PassageCorpus,
    *,
    dataset_id: int,
    indexer: Any,
    manifest_path: str | Path,
    doc_id_base: int,
    limit: int | None = None,
    batch: int = 25,
    retries: int = 4,
) -> list[ManifestRecord]:
    """逐段落灌库(段落=一个 chunk),写 manifest 并校验 doc 粒度映射唯一。

    ``doc_id_base``:本数据集 doc_id 起点(第 i 段 → doc_id_base+i);与其他数据集号段不重叠。
    分批 + 批级重试(远端偶发 502/限流;chunk_id 由 dataset/doc/ordinal 决定,重试/重灌幂等)。
    """
    items = list(corpus.passages.items())
    if limit is not None:
        items = items[:limit]

    # 段落 → doc_id 一一映射(去重/合并会破坏 doc 粒度 reference)
    passages: list[EvalPassage] = []
    pid_doc: list[tuple[str, int]] = []
    for i, (pid, text) in enumerate(items):
        doc_id = doc_id_base + i
        passages.append(
            EvalPassage(source_passage_id=pid, content=text, doc_id=doc_id, ordinal=0)
        )
        pid_doc.append((pid, doc_id))

    records: list[ManifestRecord] = []
    ok_doc_ids: list[int] = []
    for start in range(0, len(passages), batch):
        chunk = passages[start : start + batch]
        pairs = pid_doc[start : start + batch]
        for attempt in range(1, retries + 1):
            try:
                await indexer.index_passages(dataset_id, chunk)
                records.extend(ManifestRecord(pid, did, "success") for pid, did in pairs)
                ok_doc_ids.extend(did for _, did in pairs)
                break
            except Exception:
                if attempt == retries:
                    records.extend(ManifestRecord(pid, -1, "failed") for pid, _ in pairs)
                    break
                await asyncio.sleep(2 * attempt)

    if len(set(ok_doc_ids)) != len(ok_doc_ids):
        raise RuntimeError("段落→doc_id 映射出现重复,doc 粒度 reference 将失真")

    write_manifest(records, manifest_path)
    return records
