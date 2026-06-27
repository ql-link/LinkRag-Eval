"""检索层指标:纯函数计算(确定性、无 IO),输入黄金集 + StageOutput.ranked。

reference 粒度自动选择:样本带 expected_chunk_ids 用 chunk 粒度
(比对 RankedHit.chunk_id);否则降级 doc 粒度(比对 RankedHit.doc_id,
开源数据集来源的常态)。

NDCG 口径:黄金集二值命中 → ndcg_binary;样本带 relevance_grades
(T2Ranking 4 级)→ ndcg_graded。两口径分名、数值不可比、绝不混报。
"""

from __future__ import annotations

import math
from typing import Sequence

from linkrag_eval.contracts.dataset import Sample
from linkrag_eval.contracts.judge import Judge
from linkrag_eval.models import Layer, MetricValue, RankedHit, StageOutput

DEFAULT_K_VALUES = [1, 3, 5, 10]


def reference_ids(sample: Sample) -> tuple[set[str], str]:
    """取该样本的 reference 集合与粒度('chunk' / 'doc')。"""
    if sample.expected_chunk_ids:
        return set(sample.expected_chunk_ids), "chunk"
    if sample.expected_doc_ids:
        return {str(d) for d in sample.expected_doc_ids}, "doc"
    return set(), "chunk"


def ranked_ids(ranked: Sequence[RankedHit], granularity: str) -> list[str]:
    """按粒度取排序后的 id 序列;doc 粒度去重保首位(同 doc 多 chunk 只算一次)。"""
    if granularity == "chunk":
        return [h.chunk_id for h in ranked]
    seen: set[str] = set()
    ids: list[str] = []
    for h in ranked:
        d = str(h.doc_id)
        if d not in seen:
            seen.add(d)
            ids.append(d)
    return ids


class _RetrievalMetricBase:
    """公共骨架:协议要求的属性 + reference 提取。compute 为 async 仅为签名统一。"""

    layer = Layer.RETRIEVAL
    requires_judge = False
    requires_golden_answer = False
    name = ""

    def __init__(self, k_values: Sequence[int] = DEFAULT_K_VALUES):
        self.k_values = list(k_values)


class RecallAtK(_RetrievalMetricBase):
    name = "recall"

    async def compute(
        self, sample: Sample, output: StageOutput, *, judge: Judge | None = None
    ) -> list[MetricValue]:
        relevant, gran = reference_ids(sample)
        if not relevant:
            return []
        ids = ranked_ids(output.ranked, gran)
        return [
            MetricValue(
                name=self.name,
                layer=self.layer,
                value=len(set(ids[:k]) & relevant) / len(relevant),
                k=k,
                detail={"granularity": gran},
            )
            for k in self.k_values
        ]


class HitAtK(_RetrievalMetricBase):
    name = "hit_rate"

    async def compute(
        self, sample: Sample, output: StageOutput, *, judge: Judge | None = None
    ) -> list[MetricValue]:
        relevant, gran = reference_ids(sample)
        if not relevant:
            return []
        ids = ranked_ids(output.ranked, gran)
        return [
            MetricValue(
                name=self.name,
                layer=self.layer,
                value=1.0 if set(ids[:k]) & relevant else 0.0,
                k=k,
                detail={"granularity": gran},
            )
            for k in self.k_values
        ]


class PrecisionAtK(_RetrievalMetricBase):
    name = "precision"

    async def compute(
        self, sample: Sample, output: StageOutput, *, judge: Judge | None = None
    ) -> list[MetricValue]:
        relevant, gran = reference_ids(sample)
        if not relevant:
            return []
        ids = ranked_ids(output.ranked, gran)
        return [
            MetricValue(
                name=self.name,
                layer=self.layer,
                value=len(set(ids[:k]) & relevant) / k,
                k=k,
                detail={"granularity": gran},
            )
            for k in self.k_values
        ]


class MRR(_RetrievalMetricBase):
    name = "mrr"

    async def compute(
        self, sample: Sample, output: StageOutput, *, judge: Judge | None = None
    ) -> list[MetricValue]:
        relevant, gran = reference_ids(sample)
        if not relevant:
            return []
        ids = ranked_ids(output.ranked, gran)
        value = 0.0
        first_rank = None
        for i, cid in enumerate(ids, start=1):
            if cid in relevant:
                value = 1.0 / i
                first_rank = i
                break
        return [
            MetricValue(
                name=self.name,
                layer=self.layer,
                value=value,
                k=None,
                detail={"granularity": gran, "first_relevant_rank": first_rank},
            )
        ]


class NDCGAtK(_RetrievalMetricBase):
    """NDCG:二值口径(ndcg_binary);样本带 relevance_grades 时走分级口径(ndcg_graded)。

    二值:rel(c)=1 if c∈R else 0,gain=rel。
    分级:gain=grade(线性增益,T2Ranking 0-3 级),ideal 序为全体已标注
    grade 降序截断 @k。两口径分名汇报,不互比。
    """

    name = "ndcg"  # 实际产出名为 ndcg_binary / ndcg_graded

    async def compute(
        self, sample: Sample, output: StageOutput, *, judge: Judge | None = None
    ) -> list[MetricValue]:
        relevant, gran = reference_ids(sample)
        grades: dict[str, int] | None = getattr(sample, "relevance_grades", None)
        if not relevant and not grades:
            return []
        ids = ranked_ids(output.ranked, gran)

        if grades:
            name = "ndcg_graded"
            gain = {rid: float(g) for rid, g in grades.items()}
            ideal_gains = sorted(gain.values(), reverse=True)
        else:
            name = "ndcg_binary"
            gain = {rid: 1.0 for rid in relevant}
            ideal_gains = [1.0] * len(relevant)

        values = []
        for k in self.k_values:
            dcg = sum(
                gain.get(cid, 0.0) / math.log2(i + 1)
                for i, cid in enumerate(ids[:k], start=1)
            )
            idcg = sum(g / math.log2(i + 1) for i, g in enumerate(ideal_gains[:k], start=1))
            values.append(
                MetricValue(
                    name=name,
                    layer=self.layer,
                    value=dcg / idcg if idcg > 0 else 0.0,
                    k=k,
                    detail={"granularity": gran},
                )
            )
        return values


class MAP(_RetrievalMetricBase):
    """单 query 的 AP = (Σ_{i: rel(c_i)=1} Precision@i) / min(|R|, n)。

    除以 min(|R|, n) 而非命中数,避免 |R|>n 时虚高;多 query 取均值由聚合层做。
    """

    name = "map"

    async def compute(
        self, sample: Sample, output: StageOutput, *, judge: Judge | None = None
    ) -> list[MetricValue]:
        relevant, gran = reference_ids(sample)
        if not relevant:
            return []
        ids = ranked_ids(output.ranked, gran)
        hits = 0
        precision_sum = 0.0
        for i, cid in enumerate(ids, start=1):
            if cid in relevant:
                hits += 1
                precision_sum += hits / i
        denom = min(len(relevant), len(ids)) if ids else 0
        value = precision_sum / denom if denom else 0.0
        return [
            MetricValue(
                name=self.name, layer=self.layer, value=value, k=None,
                detail={"granularity": gran},
            )
        ]


class SourceOverlap(_RetrievalMetricBase):
    """三路重叠率:读归一化的 RankedHit.sources(不依赖 raw)。

    对每路 s 产出 ``overlap_<s>_only``(该路独有命中占比),另产出
    ``overlap_all_sources``(全部已装配路共有的命中占比)。占比基数为
    ranked 内带非空 sources 的 hit 数;重排后 sources 不可知(空集)则
    不产出(返回空列表)。
    """

    name = "source_overlap"

    async def compute(
        self, sample: Sample, output: StageOutput, *, judge: Judge | None = None
    ) -> list[MetricValue]:
        hits = [h for h in output.ranked if h.sources]
        if not hits:
            return []
        all_sources = sorted({s for h in hits for s in h.sources})
        n = len(hits)
        values = [
            MetricValue(
                name=f"overlap_{src}_only",
                layer=self.layer,
                value=sum(1 for h in hits if h.sources == frozenset({src})) / n,
                k=None,
                detail={"n_hits": n},
            )
            for src in all_sources
        ]
        if len(all_sources) > 1:
            full = frozenset(all_sources)
            values.append(
                MetricValue(
                    name="overlap_all_sources",
                    layer=self.layer,
                    value=sum(1 for h in hits if h.sources == full) / n,
                    k=None,
                    detail={"n_hits": n, "sources": all_sources},
                )
            )
        return values


def default_retrieval_metrics(k_values: Sequence[int] = DEFAULT_K_VALUES) -> list:
    """检索层默认指标组(口径:召回层主看 Recall@k)。"""
    return [
        RecallAtK(k_values),
        HitAtK(k_values),
        PrecisionAtK(k_values),
        MRR(k_values),
        NDCGAtK(k_values),
        MAP(k_values),
        SourceOverlap(k_values),
    ]
