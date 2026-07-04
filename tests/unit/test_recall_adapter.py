"""RecallEvaluable._to_stage_output:纯 marshalling(不需 rag,注入 fake response)。"""

from __future__ import annotations

from dataclasses import dataclass, field

from linkrag_eval.models import Layer
from linkrag_eval.retrieval.recall_adapter import RecallEvaluable


@dataclass
class _Hit:
    chunk_id: str
    doc_id: int
    dataset_id: int
    fused_score: float
    scores: dict  # source -> score|None


@dataclass
class _Resp:
    hits: list
    elapsed_ms: int = 12
    per_source_counts: dict = field(default_factory=dict)
    failed_sources: list = field(default_factory=list)


def test_to_stage_output_sorts_and_maps_sources() -> None:
    ev = RecallEvaluable(pipeline=None, top_k=10)
    resp = _Resp(
        hits=[
            _Hit("c1", 1, 990131, 0.3, {"dense": 0.3, "sparse": None}),
            _Hit("c2", 2, 990131, 0.9, {"dense": 0.5, "sparse": 0.4}),
        ],
        per_source_counts={"dense": 2, "sparse": 1},
    )
    out = ev._to_stage_output("q", resp, wall_ms=99)

    assert out.layer == Layer.RETRIEVAL
    # 按 fused_score 降序:c2(0.9) 在前
    assert [h.chunk_id for h in out.ranked] == ["c2", "c1"]
    assert out.ranked[0].rank == 0 and out.ranked[0].score == 0.9
    # sources 只取非 None 的路
    assert out.ranked[0].sources == frozenset({"dense", "sparse"})
    assert out.ranked[1].sources == frozenset({"dense"})
    assert out.elapsed_ms == 12  # resp.elapsed_ms 优先于 wall_ms
    assert out.per_source_counts == {"dense": 2, "sparse": 1}


def test_elapsed_falls_back_to_wall_ms() -> None:
    ev = RecallEvaluable(pipeline=None, top_k=5)
    out = ev._to_stage_output("q", _Resp(hits=[], elapsed_ms=0), wall_ms=77)
    assert out.elapsed_ms == 77 and out.ranked == []


class _Pipeline:
    def __init__(self):
        self.request = None
        self.calls = 0

    async def execute(self, request):
        self.request = request
        self.calls += 1
        return _Resp(hits=[], elapsed_ms=1, per_source_counts={"dense": 0, "sparse": 0})


class _FlakyPipeline:
    def __init__(self):
        self.calls = 0

    async def execute(self, request):
        self.calls += 1
        if self.calls == 1:
            return _Resp(
                hits=[_Hit("c1", 1, 990131, 0.3, {"dense": 0.3, "sparse": None})],
                elapsed_ms=1,
                per_source_counts={"dense": 1, "sparse": 0},
                failed_sources=["sparse"],
            )
        return _Resp(
            hits=[_Hit("c2", 2, 990131, 0.9, {"dense": 0.5, "sparse": 0.4})],
            elapsed_ms=1,
            per_source_counts={"dense": 1, "sparse": 1},
            failed_sources=[],
        )


@dataclass
class _Sample:
    query: str = "短 query"
    user_id: int = 990001
    dataset_ids: list[int] = field(default_factory=lambda: [990123])


async def test_run_passes_route_topk_thresholds_and_fusion_overrides() -> None:
    pipeline = _Pipeline()
    ev = RecallEvaluable(
        pipeline=pipeline,
        top_k=10,
        bm25_top_k=40,
        dense_top_k=150,
        sparse_top_k=50,
        dense_score_threshold=0.2,
        sparse_score_threshold=0.4,
        fusion_strategy="weighted_score",
        fusion_weights={"dense": 0.9, "sparse": 0.1, "bm25": 0.0},
        retries=1,
    )

    await ev.run(_Sample())

    req = pipeline.request
    assert req.top_k == 10
    assert req.bm25_top_k == 40
    assert req.dense_top_k == 150
    assert req.sparse_top_k == 50
    assert req.dense_score_threshold_override == 0.2
    assert req.sparse_score_threshold_override == 0.4
    assert req.fusion_strategy_override == "weighted_score"
    assert req.fusion_dense_weight_override == 0.9
    assert req.fusion_sparse_weight_override == 0.1
    assert req.fusion_bm25_weight_override == 0.0


async def test_run_retries_failed_sources_before_returning() -> None:
    pipeline = _FlakyPipeline()
    ev = RecallEvaluable(pipeline=pipeline, top_k=10, retries=2)

    out = await ev.run(_Sample())

    assert pipeline.calls == 2
    assert out.failed_sources == []
    assert [h.chunk_id for h in out.ranked] == ["c2"]
