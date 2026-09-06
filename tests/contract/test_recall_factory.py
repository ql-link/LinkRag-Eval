"""recall_factory 装配:注入 fake 编码器,验证能装出 eval 前缀的 RecallPipeline(不连网络)。

需 toLink-Rag 可 import(facade/retriever/pipeline 是 rag),故标 contract；普通本地环境缺依赖
时跳过，CI 设置 ``LINKRAG_EVAL_REQUIRE_RAG=1`` 后会在收集前直接失败。
"""

from __future__ import annotations

import inspect

import pytest

pytest.importorskip("src.core", reason="需安装 toLink-Rag(pip install -e <path>)")
pytestmark = pytest.mark.contract

from linkrag_eval.config import EvalSettings
from linkrag_eval.retrieval.recall_adapter import execute_candidate_contract_once
from linkrag_eval.retrieval.recall_factory import build_eval_recall_pipeline


@pytest.fixture(autouse=True)
def _disable_qdrant_compatibility_check(monkeypatch):
    from qdrant_client import AsyncQdrantClient

    original_init = AsyncQdrantClient.__init__

    def offline_init(self, *args, **kwargs):
        # 保留真实客户端及装配接口，仅关闭构造时的后台联网检查。
        kwargs["check_compatibility"] = False
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(AsyncQdrantClient, "__init__", offline_init)


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


class _PassAllReadiness:
    async def filter_visible_hits(self, hits, *, user_id):
        del user_id
        return list(hits)


class _FixedRetriever:
    def __init__(self, source, hits):
        self.source = source
        self._hits = list(hits)

    async def recall(self, *args, **kwargs):
        del args, kwargs
        return list(self._hits)


def _settings(prefix="eval_kb_bucket") -> EvalSettings:
    return EvalSettings(
        _env_file=None,
        qdrant_prefix=prefix,
        qdrant_host="http://localhost:36333",
        recall_dense_score_threshold=0.11,
        recall_sparse_score_threshold=0.30,
        user_id=990001,
    )


def test_assembles_two_route_pipeline() -> None:
    settings = _settings()
    settings.sparse_vector_name = "eval_sparse_for_test"
    pipe = build_eval_recall_pipeline(
        settings=settings, dense_encoder=_FakeDense(), sparse_encoder=_FakeSparse()
    )
    from src.core.pipeline.recall.pipeline import RecallPipeline

    assert isinstance(pipe, RecallPipeline)
    # 未启用 BM25，只装配 dense + sparse。
    assert len(pipe._retrievers) == 2
    assert pipe._readiness_gate.__class__.__name__ == "_EvalReadinessGate"
    assert pipe._retrievers[0]._score_threshold == 0.11
    assert pipe._retrievers[0]._backend._embedding_pipeline.__class__ is _FakeDense
    assert pipe._retrievers[1]._score_threshold == 0.30
    assert pipe._retrievers[1]._backend._sparse_vector_service.vector_name == "eval_sparse_for_test"
    assert pipe._retrievers[0]._backend.qdrant_store.collection_name == "eval_kb_bucket_9"


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
    signature = inspect.signature(pipe._retrievers[0].recall)
    assert "dataset_contexts" in signature.parameters


def test_prefix_guard_rejects_non_eval() -> None:
    # 用 SimpleNamespace 绕过 EvalSettings 的 pydantic 校验,直测 recall_factory 自身的护栏
    from types import SimpleNamespace

    bad = SimpleNamespace(qdrant_prefix="kb_bucket", qdrant_host="http://localhost:36333",
                          qdrant_bucket_count=16)
    with pytest.raises(RuntimeError, match="eval"):
        build_eval_recall_pipeline(
            settings=bad, dense_encoder=_FakeDense(), sparse_encoder=_FakeSparse()
        )


async def test_current_candidate_and_route_contract_preserves_untruncated_pool() -> None:
    from src.core.pipeline.recall import RecallPipeline, RecallPipelineConfig
    from src.core.pipeline.recall.models import RecallRequest, RetrieverHit

    def hit(chunk_id, source, score):
        return RetrieverHit(
            chunk_id=chunk_id,
            doc_id=1,
            dataset_id=990131,
            score=score,
            source=source,
        )

    pipe = RecallPipeline(
        [
            _FixedRetriever("dense", [hit("shared", "dense", 0.9), hit("d", "dense", 0.8)]),
            _FixedRetriever("sparse", [hit("shared", "sparse", 0.7), hit("s", "sparse", 0.6)]),
            _FixedRetriever("bm25", []),
        ],
        RecallPipelineConfig(parallel=False, strict=True),
        readiness_gate=_PassAllReadiness(),
    )
    response = await pipe.execute(
        RecallRequest(
            query="固定契约样例",
            user_id=990001,
            dataset_ids=[990131],
            top_k=1,
            bm25_top_k=10,
            sparse_top_k=10,
            dense_top_k=10,
            candidate_contract_version="eval-candidate-contract-v1",
            candidate_profile="contract-test",
            required_sources=["dense", "sparse", "bm25"],
        )
    )

    assert len(response.hits) == 1
    assert {item.chunk_id for item in response.candidate_hits} == {"shared", "d", "s"}
    assert set(response.route_hits) == {"dense", "sparse", "bm25"}
    assert [item.chunk_id for item in response.route_hits["dense"]] == ["shared", "d"]
    assert [item.chunk_id for item in response.route_hits["sparse"]] == ["shared", "s"]
    assert response.route_hits["bm25"] == []
    assert response.per_source_counts == {"dense": 2, "sparse": 2, "bm25": 0}
    assert response.failed_sources == []


async def test_execute_candidate_contract_once_sets_required_research_fields() -> None:
    class _Pipeline:
        def __init__(self):
            self.requests = []

        async def execute(self, request):
            self.requests.append(request)
            return "response"

    pipeline = _Pipeline()
    response = await execute_candidate_contract_once(
        pipeline,
        query="一次性候选契约",
        user_id=990001,
        dataset_ids=[996601],
        top_k=112,
        bm25_top_k=100,
        dense_top_k=150,
        sparse_top_k=50,
        dense_score_threshold=0.3,
        sparse_score_threshold=0.2,
        enabled_sources=["dense", "sparse", "bm25"],
        required_sources=["dense", "sparse", "bm25"],
        fusion_weights={"dense": 0.7, "sparse": 0.15, "bm25": 0.15},
        candidate_contract_version="contract-v1",
        candidate_profile="dev-profile-v1",
    )

    assert response == "response"
    assert len(pipeline.requests) == 1
    request = pipeline.requests[0]
    assert request.strict_override is True
    assert request.required_sources == ["dense", "sparse", "bm25"]
    assert request.candidate_contract_version == "contract-v1"
    assert request.candidate_profile == "dev-profile-v1"
