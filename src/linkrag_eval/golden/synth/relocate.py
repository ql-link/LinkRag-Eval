"""换分块策略 → 自动重定位（B11，Track B 的隐藏优势）。

换分块会使所有 chunk 粒度黄金集的 expected_chunk_ids 失效（precheck 检出）。
反向合成/开源只能报废重做；Track B 因锚点持久化，对同一冻结语料重跑分块后
按锚点重新归一化匹配即可重建 expected_chunk_ids，代价从"报废重做"降到
"重跑匹配"。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from linkrag_eval.golden.schema import GoldenSample
from linkrag_eval.golden.synth.facts import FactUnit
from linkrag_eval.golden.synth.locate import locate_facts


@dataclass
class RelocateReport:
    total: int = 0
    relocated: int = 0
    lost: list[str] = field(default_factory=list)   # 新分块下锚点不再可定位的 sample_id

    def summary(self) -> str:
        return (
            f"relocate: {self.relocated}/{self.total} 重建成功"
            + (f"；丢失 {self.lost}" if self.lost else "")
        )


def relocate_samples(
    samples: list[GoldenSample],
    facts_by_id: dict[str, FactUnit],
    new_chunks_by_doc: dict[int, dict[str, str]],
    *,
    fuzzy_threshold: float = 0.85,
) -> tuple[list[GoldenSample], RelocateReport]:
    """对 Track B 样本按锚点在新 chunk 集上重建 expected_chunk_ids。

    samples 须为 Track B 产出（note 含 fact_id=...）；facts_by_id 来自
    锚点持久化文件（facts.load_facts）；new_chunks_by_doc：doc_id →
    {chunk_id: content}（重分块后反查）。
    """
    report = RelocateReport(total=len(samples))
    out: list[GoldenSample] = []
    for sample in samples:
        fact_id = _extract_fact_id(sample.note)
        fact = facts_by_id.get(fact_id) if fact_id else None
        doc_id = sample.expected_doc_ids[0] if sample.expected_doc_ids else None
        chunks = new_chunks_by_doc.get(doc_id, {}) if doc_id is not None else {}
        if fact is None or not chunks:
            report.lost.append(sample.id)
            continue
        locate_report = locate_facts([fact], chunks, fuzzy_threshold=fuzzy_threshold)
        result = locate_report.results[0]
        if not result.located:
            report.lost.append(sample.id)
            continue
        out.append(replace(sample, expected_chunk_ids=list(result.chunk_ids)))
        report.relocated += 1
    return out, report


def _extract_fact_id(note: str) -> str | None:
    for part in note.split(";"):
        part = part.strip()
        if part.startswith("fact_id="):
            return part.removeprefix("fact_id=")
    return None
