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


class _FakeTokenized:
    coarse_tokens = "短 query"


class _FakeTokenizer:
    def tokenize(self, text):
        return _FakeTokenized()


def _settings(prefix="eval_kb_bucket") -> EvalSettings:
    return EvalSettings(
        _env_file=None,
        qdrant_prefix=prefix,
        qdrant_host="http://localhost:36333",
        recall_dense_score_threshold=0.11,
        recall_sparse_score_threshold=0.30,
        qdrant_bm25_collection="eval_bm25",
    )


def test_assembles_two_route_pipeline() -> None:
    settings = _settings()
    settings.sparse_vector_name = "eval_sparse_for_test"
    pipe = build_eval_recall_pipeline(
        settings=settings, dense_encoder=_FakeDense(), sparse_encoder=_FakeSparse()
    )
    from src.core.pipeline.recall.pipeline import RecallPipeline

    assert isinstance(pipe, RecallPipeline)
    # dense + sparse 两路(bm25 P1 stub)
    assert len(pipe._retrievers) == 2
    assert pipe._readiness_gate.__class__.__name__ == "_EvalReadinessGate"
    assert pipe._retrievers[0]._score_threshold == 0.11
    assert pipe._retrievers[0]._backend._embedding_pipeline.__class__ is _FakeDense
    assert pipe._retrievers[1]._score_threshold == 0.30
    assert pipe._retrievers[1]._backend._sparse_vector_service.vector_name == "eval_sparse_for_test"


def test_assembles_qdrant_bm25_route_when_enabled() -> None:
    settings = _settings()
    settings.bm25_mode = "qdrant_bm25"
    pipe = build_eval_recall_pipeline(
        settings=settings,
        dense_encoder=_FakeDense(),
        sparse_encoder=_FakeSparse(),
        bm25_tokenizer=_FakeTokenizer(),
    )

    assert [r.source for r in pipe._retrievers] == ["bm25", "dense", "sparse"]


def test_assembles_sqlite_bm25_route_when_enabled(tmp_path) -> None:
    settings = _settings()
    settings.bm25_mode = "sqlite_fts5"
    settings.bm25_sqlite_path = str(tmp_path / "bm25.sqlite3")
    pipe = build_eval_recall_pipeline(
        settings=settings,
        dense_encoder=_FakeDense(),
        sparse_encoder=_FakeSparse(),
        bm25_tokenizer=_FakeTokenizer(),
    )

    assert [r.source for r in pipe._retrievers] == ["bm25", "dense", "sparse"]


def test_prefix_guard_rejects_non_eval() -> None:
    # 用 SimpleNamespace 绕过 EvalSettings 的 pydantic 校验,直测 recall_factory 自身的护栏
    from types import SimpleNamespace

    bad = SimpleNamespace(qdrant_prefix="kb_bucket", qdrant_host="http://localhost:36333",
                          qdrant_bucket_count=16)
    with pytest.raises(RuntimeError, match="eval"):
        build_eval_recall_pipeline(
            settings=bad, dense_encoder=_FakeDense(), sparse_encoder=_FakeSparse()
        )
