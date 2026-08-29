from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

import linkrag_eval.robust_fusion.internal_v6_route_evidence as route_evidence
from linkrag_eval.compute.protocol import SparseVec
from linkrag_eval.config import EvalSettings
from linkrag_eval.robust_fusion.internal_v6_route_evidence import (
    EXECUTION_CONFIRMATION,
    EXPECTED_RELEASE_MANIFEST_SHA256,
    build_identity_maps,
    build_views,
    ensure_method_view_safe,
    execute_run,
    prepare_run,
    serialize_candidate_response,
    verify_dev_release,
    verify_prepared_plan,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_RELATIVE = Path(
    "data/robust_fusion/internal_stress_v6/dev/releases/adjudicated_synthetic_v1"
)


def _settings() -> EvalSettings:
    return EvalSettings(
        _env_file=None,
        qdrant_host="http://qdrant.invalid:6333",
        qdrant_prefix="eval_test",
        qdrant_bucket_count=1,
        qdrant_bm25_collection="eval_bm25_test",
        embed_base_url="https://dense.invalid/v1",
        embed_api_key="DENSE_SECRET_FOR_TEST",
        embed_model="text-embedding-v4",
        embed_dim=1024,
        sparse_provider="ark",
        sparse_base_url="https://sparse.invalid/v1",
        sparse_api_key="SPARSE_SECRET_FOR_TEST",
        sparse_model="doubao-embedding-vision-251215",
        bm25_mode="sqlite_fts5",
    )


def _copy_release(tmp_path: Path) -> tuple[Path, Path]:
    repo_root = tmp_path / "repo"
    release_root = repo_root / RELEASE_RELATIVE
    release_root.parent.mkdir(parents=True)
    shutil.copytree(REPO_ROOT / RELEASE_RELATIVE, release_root)
    return repo_root, release_root


def test_verify_release_and_identity_maps_are_closed_and_opaque() -> None:
    release = verify_dev_release(REPO_ROOT / RELEASE_RELATIVE)
    assert release.manifest_sha256 == EXPECTED_RELEASE_MANIFEST_SHA256
    assert (len(release.queries), len(release.documents), len(release.evidence)) == (28, 112, 112)

    query_map, chunk_map = build_identity_maps(release, dataset_id=996_601)
    assert len(set(query_map.values())) == 28
    assert len({row["chunk_id"] for row in chunk_map.values()}) == 112
    assert all("RF-V6D" not in query_uid for query_uid in query_map.values())
    assert all("RF-V6D" not in row["chunk_id"] for row in chunk_map.values())


def test_prepare_plan_is_redacted_and_single_use(tmp_path: Path) -> None:
    repo_root, release_root = _copy_release(tmp_path)
    output_root = repo_root / "runs" / "route-v1"
    result = prepare_run(
        repo_root=repo_root,
        release_root=release_root,
        output_root=output_root,
        run_id="route-v1",
        dataset_id=996_601,
        settings=_settings(),
    )

    assert result["status"] == "PREPARED"
    plan_text = (output_root / "plan.json").read_text(encoding="utf-8")
    assert "DENSE_SECRET_FOR_TEST" not in plan_text
    assert "SPARSE_SECRET_FOR_TEST" not in plan_text
    assert "https://dense.invalid" not in plan_text
    assert "https://sparse.invalid" not in plan_text
    plan, resolved_output = verify_prepared_plan(repo_root, output_root / "plan.json")
    assert resolved_output == output_root.resolve()
    assert plan["cost_envelope"]["judge_llm_requests"] == 0
    assert plan["scope"]["formal_p4_02_snapshot"] is False
    assert plan["scope"]["gate_eligibility"] == "NOT_ELIGIBLE"
    assert (output_root / "storage").is_dir()
    assert list((output_root / "storage").iterdir()) == []

    with pytest.raises(RuntimeError, match="拒绝覆盖"):
        prepare_run(
            repo_root=repo_root,
            release_root=release_root,
            output_root=output_root,
            run_id="route-v1",
            dataset_id=996_601,
            settings=_settings(),
        )


async def test_first_remote_probe_failure_consumes_the_prepared_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root, release_root = _copy_release(tmp_path)
    output_root = repo_root / "runs" / "route-v1"
    prepare_run(
        repo_root=repo_root,
        release_root=release_root,
        output_root=output_root,
        run_id="route-v1",
        dataset_id=996_601,
        settings=_settings(),
    )

    async def fail_probe(settings: EvalSettings, collection: str) -> bool:
        del settings, collection
        raise RuntimeError("remote probe failed")

    monkeypatch.setattr(route_evidence, "_qdrant_collection_exists", fail_probe)
    with pytest.raises(RuntimeError, match="remote probe failed"):
        await execute_run(
            repo_root=repo_root,
            plan_path=output_root / "plan.json",
            confirmation=EXECUTION_CONFIRMATION,
            settings=_settings(),
        )

    state = json.loads((output_root / "run_state.json").read_text(encoding="utf-8"))
    assert state["state"] == "FAILED_NO_AUTORETRY"
    assert state["execution_attempts"] == 1
    with pytest.raises(RuntimeError, match="拒绝原地重试"):
        verify_prepared_plan(repo_root, output_root / "plan.json")


async def test_execute_completes_with_local_sqlite_and_fake_remote_services(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from linkrag_eval.retrieval import recall_adapter, recall_factory
    from linkrag_eval.store import vector_store

    class _FakeDense:
        dim = 1024
        model_name = "fake-dense"

        async def aembed(self, texts):
            return [[0.1] * self.dim for _ in texts]

        async def aclose(self) -> None:
            return None

    class _FakeSparse:
        model_name = "fake-sparse"

        async def aencode(self, texts):
            return [SparseVec([1], [0.5]) for _ in texts]

        async def aclose(self) -> None:
            return None

    class _FakeIndexStore:
        def __init__(self) -> None:
            self.dense_points = []
            self.sparse_points = []
            self.vector_size = None
            self.sparse_vector_name = None

        async def ensure_collection(self, *, vector_size) -> None:
            self.vector_size = vector_size

        async def upsert_points(self, *, points) -> None:
            self.dense_points.extend(points)

        async def ensure_sparse_vector_schema(self, *, vector_name) -> None:
            self.sparse_vector_name = vector_name

        async def upsert_sparse_vectors(self, *, points) -> None:
            self.sparse_points.extend(points)

    async def no_collection(settings: EvalSettings, collection: str) -> bool:
        del settings, collection
        return False

    async def fake_candidate_response(*args, **kwargs):
        del args, kwargs
        return SimpleNamespace(
            failed_sources=[],
            route_hits={"dense": [], "sparse": [], "bm25": []},
            candidate_hits=[],
            elapsed_ms=1,
        )

    repo_root, release_root = _copy_release(tmp_path)
    output_root = repo_root / "runs" / "route-v1"
    prepare_run(
        repo_root=repo_root,
        release_root=release_root,
        output_root=output_root,
        run_id="route-v1",
        dataset_id=996_601,
        settings=_settings(),
    )
    fake_index_store = _FakeIndexStore()

    def build_fake_vector_store(*, settings):
        return vector_store.EvalVectorStore(
            prefix=settings.qdrant_prefix,
            bucket_count=settings.qdrant_bucket_count,
            user_id=settings.user_id,
            index_store=fake_index_store,
            sparse_vector_name=settings.sparse_vector_name,
            bm25_mode=settings.bm25_mode,
            bm25_sqlite_path=settings.bm25_sqlite_path,
            bm25_sqlite_coarse_weight=settings.bm25_sqlite_coarse_weight,
            bm25_sqlite_fine_weight=settings.bm25_sqlite_fine_weight,
        )

    monkeypatch.setattr(route_evidence, "_qdrant_collection_exists", no_collection)
    monkeypatch.setattr(
        route_evidence,
        "_build_zero_retry_encoders",
        lambda settings: (_FakeDense(), _FakeSparse()),
    )
    monkeypatch.setattr(vector_store, "build_eval_vector_store", build_fake_vector_store)
    monkeypatch.setattr(
        recall_factory, "build_eval_recall_pipeline", lambda **kwargs: object()
    )
    monkeypatch.setattr(
        recall_adapter, "execute_candidate_contract_once", fake_candidate_response
    )

    result = await execute_run(
        repo_root=repo_root,
        plan_path=output_root / "plan.json",
        confirmation=EXECUTION_CONFIRMATION,
        settings=_settings(),
    )

    assert result["status"] == "COMPLETED_DEV_ONLY"
    assert fake_index_store.vector_size == 1024
    assert fake_index_store.sparse_vector_name == "sparse_text"
    assert len(fake_index_store.dense_points) == 112
    assert len(fake_index_store.sparse_points) == 112
    assert (output_root / "storage" / "metadata.sqlite3").is_file()
    assert (output_root / "storage" / "bm25.sqlite3").is_file()
    state = json.loads((output_root / "run_state.json").read_text(encoding="utf-8"))
    assert state["state"] == "COMPLETED"
    assert state["execution_attempts"] == 1
    manifest = json.loads((output_root / "manifest.json").read_text(encoding="utf-8"))
    assert state["manifest_sha256"] == route_evidence.sha256_file(
        output_root / "manifest.json"
    )
    assert state["content_root_sha256"] == manifest["content_root_sha256"]
    assert route_evidence._manifest_files(output_root) == manifest["files"]
    assert not any(
        item["path"].endswith(("-shm", "-wal", "-journal"))
        for item in manifest["files"]
    )
    assert manifest["summary"]["query_count"] == 28
    assert manifest["summary"]["indexed_chunk_count"] == 112
    assert manifest["summary"]["candidate_row_count"] == 0
    assert manifest["gate_eligibility"] == "NOT_ELIGIBLE"


def test_serialize_candidate_response_preserves_route_rank_and_score() -> None:
    dense_hit = SimpleNamespace(chunk_id="chunk-a", doc_id=1, dataset_id=9, score=0.8)
    sparse_hit = SimpleNamespace(chunk_id="chunk-a", doc_id=1, dataset_id=9, score=1.2)
    candidate = SimpleNamespace(
        chunk_id="chunk-a", doc_id=1, dataset_id=9, fused_score=0.77
    )
    response = SimpleNamespace(
        failed_sources=[],
        route_hits={"dense": [dense_hit], "sparse": [sparse_hit], "bm25": []},
        candidate_hits=[candidate],
        elapsed_ms=12,
    )

    rows, summary = serialize_candidate_response(
        query_uid="query-a", response=response, expected_chunk_ids={"chunk-a"}
    )

    assert rows == [
        {
            "query_uid": "query-a",
            "candidate_rank": 1,
            "chunk_id": "chunk-a",
            "doc_id": 1,
            "dataset_id": 9,
            "fused_score": 0.77,
            "route_evidence": {
                "dense": {"retrieved": True, "rank": 1, "raw_score": 0.8},
                "sparse": {"retrieved": True, "rank": 1, "raw_score": 1.2},
                "bm25": {"retrieved": False, "rank": None, "raw_score": None},
            },
        }
    ]
    assert summary["per_source_counts"] == {"dense": 1, "sparse": 1, "bm25": 0}


def test_views_physically_separate_method_and_evaluation_fields() -> None:
    release = verify_dev_release(REPO_ROOT / RELEASE_RELATIVE)
    views = build_views(release=release, dataset_id=996_601, candidate_rows=[])

    serialized_method = json.dumps(
        {
            "queries": views["method_queries"],
            "chunks": views["method_chunks"],
            "candidates": views["method_candidates"],
        },
        ensure_ascii=False,
    )
    assert "target_relation" not in serialized_method
    assert "conflict_type" not in serialized_method
    assert "source_chunk_id" not in serialized_method
    assert len(views["evaluation_relations"]) == 112
    assert all(not row["candidate_pool_member"] for row in views["evaluation_relations"])

    with pytest.raises(RuntimeError, match="禁止字段"):
        ensure_method_view_safe([{"target_relation": "equivalent"}])
