"""recall_factory 装配:注入 fake 编码器,验证能装出 eval 前缀的 RecallPipeline(不连网络)。

需 toLink-Rag 可 import(facade/retriever/pipeline 是 rag),故标 contract;rag 不在则跳过。
"""

from __future__ import annotations

import pytest

pytest.importorskip("src", reason="需安装 toLink-Rag(pip install -e <path>)")

from linkrag_eval.config import EvalSettings  # noqa: E402
from linkrag_eval.retrieval.recall_factory import build_eval_recall_pipeline  # noqa: E402


class _FakeDense:
    dim = 1024
    model_name = "fake-dense"

    async def aembed(self, texts):
        return [[0.1] * self.dim for _ in texts]

    async def aembed_query_detailed(self, text):
        return [0.1] * self.dim, None


class _FakeSparse:
    model_name = "fake-sparse"

    async def aencode(self, texts):
        from linkrag_eval.compute.protocol import SparseVec

        return [SparseVec([1], [0.5]) for _ in texts]


def _settings(prefix="eval_kb_bucket") -> EvalSettings:
    return EvalSettings(
        qdrant_prefix=prefix,
        qdrant_host="http://localhost:36333",
        recall_dense_score_threshold=0.11,
        recall_sparse_score_threshold=0.30,
    )


def test_assembles_two_route_pipeline() -> None:
    pipe = build_eval_recall_pipeline(
        settings=_settings(), dense_encoder=_FakeDense(), sparse_encoder=_FakeSparse()
    )
    from src.core.pipeline.recall.pipeline import RecallPipeline

    assert isinstance(pipe, RecallPipeline)
    # dense + sparse 两路(bm25 P1 stub)
    assert len(pipe._retrievers) == 2
    assert pipe._retrievers[0]._score_threshold == 0.11
    assert pipe._retrievers[1]._score_threshold == 0.30


def test_prefix_guard_rejects_non_eval() -> None:
    # 用 SimpleNamespace 绕过 EvalSettings 的 pydantic 校验,直测 recall_factory 自身的护栏
    from types import SimpleNamespace

    bad = SimpleNamespace(qdrant_prefix="kb_bucket", qdrant_host="http://localhost:36333",
                          qdrant_bucket_count=16)
    with pytest.raises(RuntimeError, match="eval"):
        build_eval_recall_pipeline(
            settings=bad, dense_encoder=_FakeDense(), sparse_encoder=_FakeSparse()
        )
