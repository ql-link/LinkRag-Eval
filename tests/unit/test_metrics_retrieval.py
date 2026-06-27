"""检索层指标:纯函数正确性(不需 rag/活栈)。验证搬迁未走样。"""

from __future__ import annotations

from dataclasses import dataclass, field

from linkrag_eval.metrics.registry import metrics_for, register_defaults
from linkrag_eval.metrics.retrieval import NDCGAtK, RecallAtK, SourceOverlap
from linkrag_eval.models import Layer, QuestionType, RankedHit, StageOutput


@dataclass
class _Sample:
    id: str = "q1"
    query: str = "q"
    user_id: int = 990001
    dataset_ids: list[int] = field(default_factory=lambda: [1])
    expected_chunk_ids: list[str] = field(default_factory=list)
    expected_doc_ids: list[int] | None = None
    golden_answer: str | None = None
    type: QuestionType = QuestionType.KEYWORD


def _hit(doc_id: int, rank: int, sources=frozenset()) -> RankedHit:
    return RankedHit(
        chunk_id=f"c{doc_id}", doc_id=doc_id, dataset_id=1, rank=rank, score=1.0 - rank * 0.1,
        sources=sources,
    )


def _output(doc_order: list[int], sources_map=None) -> StageOutput:
    sm = sources_map or {}
    ranked = [_hit(d, i, sm.get(d, frozenset())) for i, d in enumerate(doc_order)]
    return StageOutput(layer=Layer.RETRIEVAL, query="q", ranked=ranked)


async def test_recall_at_k_doc_granularity() -> None:
    sample = _Sample(expected_doc_ids=[1, 2, 3])
    out = _output([1, 4, 2, 5, 3])  # 命中名次:1@1, 2@3, 3@5
    vals = {v.k: v.value for v in await RecallAtK([1, 3, 5]).compute(sample, out)}
    assert vals[1] == 1 / 3
    assert vals[3] == 2 / 3
    assert vals[5] == 1.0


async def test_recall_prefers_chunk_granularity() -> None:
    sample = _Sample(expected_chunk_ids=["c1", "c2"], expected_doc_ids=[1, 2, 3])
    out = _output([1, 9, 2])  # chunk c1@1, c2@3
    vals = {v.k: v.value for v in await RecallAtK([1, 3]).compute(sample, out)}
    assert vals[1] == 0.5  # {c1} 命中 1/2
    assert vals[3] == 1.0


async def test_ndcg_binary_perfect_order() -> None:
    sample = _Sample(expected_doc_ids=[1, 2])
    out = _output([1, 2, 9])  # 两个相关都在最前 → 完美排序
    vals = {v.k: v.value for v in await NDCGAtK([2]).compute(sample, out)}
    assert abs(vals[2] - 1.0) < 1e-9


async def test_source_overlap() -> None:
    sample = _Sample(expected_doc_ids=[1, 2, 3])
    out = _output(
        [1, 2, 3, 4],
        sources_map={
            1: frozenset({"dense"}),
            2: frozenset({"dense", "sparse"}),
            3: frozenset({"sparse"}),
            4: frozenset({"dense", "sparse"}),
        },
    )
    vals = {v.name: v.value for v in await SourceOverlap().compute(sample, out)}
    # 4 个带 sources 的 hit:dense-only=1(doc1),sparse-only=1(doc3),both=2(doc2,4)
    assert vals["overlap_dense_only"] == 0.25
    assert vals["overlap_sparse_only"] == 0.25
    assert vals["overlap_all_sources"] == 0.5


def test_registry_defaults() -> None:
    register_defaults()
    names = {m.name for m in metrics_for(Layer.RETRIEVAL)}
    assert {"recall", "ndcg", "mrr", "map", "source_overlap"} <= names
