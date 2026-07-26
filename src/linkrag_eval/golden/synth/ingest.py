"""Track B 灌库 + 回定位编排:渲染件经真实 parse→chunk→index,入库后按锚点定位 chunk。

必须走真实 **解析 + 分块**(否则失去 Track B 测 parser/chunker 的意义)。

**解耦改动**:源版经废弃 ``ingest_common.CorpusIngestor`` + 直查生产 ``ChunkRecordDB``;
这里全部依赖注入、零 rag import:
- ``parse_fn``:渲染件→文本(被测 parser),默认 :func:`linkrag_eval.cleaning.adapter.parse_rendered`
  (生产 ParserFactory 收在那个已白名单文件里);
- ``computer``::class:`~linkrag_eval.compute.protocol.ProductComputer`,用 ``compute_chunks``
  做被测分块;
- ``indexer``::class:`~linkrag_eval.store.indexer.EvalVectorIndexer` 写 eval 前缀 Qdrant + 独立库。

刚算出的 chunk 及其确定性 chunk_id(``eval_chunk_id``)直接在内存里组 ``{chunk_id: content}``
喂回定位,无需回查 DB。
"""

from __future__ import annotations

import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from linkrag_eval.golden.corpus_io import ManifestRecord
from linkrag_eval.golden.synth.compose import ComposeResult
from linkrag_eval.golden.synth.locate import LocateReport, locate_facts
from linkrag_eval.golden.synth.render import render
from linkrag_eval.store.ids import eval_chunk_id
from linkrag_eval.store.indexer import EvalPassage

ParseFn = Callable[[Path, str, "str | None"], str]


@dataclass
class SynthDocResult:
    record: ManifestRecord
    locate_report: LocateReport
    bucket: str
    chunks: dict[str, str] = field(default_factory=dict)


def _default_parse_fn(path: Path, fmt: str, pdf_backend: str | None) -> str:
    from linkrag_eval.cleaning.adapter import parse_rendered

    return parse_rendered(path, fmt, pdf_backend)


async def ingest_and_locate(
    composed: ComposeResult,
    *,
    dataset_id: int,
    doc_id: int,
    indexer: Any,
    computer: Any,
    parse_fn: ParseFn | None = None,
    topic: str = "synthetic",
) -> SynthDocResult:
    """渲染 → 解析 → 分块 → 灌库 → 按锚点回定位该 doc 的 chunk。

    ``doc_id``:本合成文档分配的 doc_id(与其他文档号段不重叠)。失败(渲染依赖缺失/解析空)
    记 ``status=failed`` 不抛,回定位空。
    """
    parse_fn = parse_fn or _default_parse_fn
    spec = composed.spec
    bucket = f"{spec.fmt}×{spec.pdf_backend}" if spec.pdf_backend else spec.fmt
    name = f"synth-{spec.key}-{uuid.uuid4().hex[:8]}"

    report = LocateReport()
    chunks: dict[str, str] = {}
    try:
        content, suffix = render(spec.fmt, composed.markdown, title=topic)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as fh:
            fh.write(content)
            fh.flush()
            produced = parse_fn(Path(fh.name), spec.fmt, spec.pdf_backend)
        eval_chunks = await computer.compute_chunks(produced)
        passages = [
            EvalPassage(
                source_passage_id=f"{name}#{c.ordinal}",
                content=c.content,
                doc_id=doc_id,
                ordinal=c.ordinal,
            )
            for c in eval_chunks
        ]
        await indexer.index_passages(dataset_id, passages)
        chunks = {
            eval_chunk_id(dataset_id, doc_id, c.ordinal): c.content for c in eval_chunks
        }
    except Exception:
        return SynthDocResult(
            record=ManifestRecord(name, -1, "failed"),
            locate_report=report,
            bucket=bucket,
            chunks={},
        )

    # 只对编织成功(锚点在 markdown 中)的事实回定位;compose 失败的另计
    locate_facts(composed.planted_facts, chunks, bucket=bucket, report=report)
    return SynthDocResult(
        record=ManifestRecord(name, doc_id, "success"),
        locate_report=report,
        bucket=bucket,
        chunks=chunks,
    )
