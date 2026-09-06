from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

import pytest

from linkrag_eval.retrieval.learning_to_rank.experiment import FEATURE_NAMES, FEATURE_VERSION
from linkrag_eval.retrieval.learning_to_rank.online import (
    WEIGHTED_SCORE_BASELINE,
    ModelManifest,
    RankerMonitor,
    RollbackPolicy,
    WeightedScoreOnlineRanker,
    activate_model,
    feature_signature,
    load_active_ranker,
    rollback_model,
)


def _model_dir(root, version):
    path = root / version
    path.mkdir(parents=True)
    model = path / "model.txt"
    model.write_text("fake-model")
    manifest=ModelManifest(
        model_version=version, feature_version=FEATURE_VERSION,
        feature_signature=feature_signature(), feature_names=list(FEATURE_NAMES),
        training_data_sha256="",
        n_estimators=10, latency_budget_ms=250, timeout_ms=350, lightgbm_version="4.7.0",
        model_file_sha256=hashlib.sha256(model.read_bytes()).hexdigest(),
    )
    (path/"manifest.json").write_text(json.dumps(asdict(manifest)))


def test_feature_signature_rejects_drift() -> None:
    manifest=ModelManifest(
        model_version="v",feature_version=FEATURE_VERSION,feature_signature="wrong",
        feature_names=list(FEATURE_NAMES),training_data_sha256="x",
        n_estimators=1,latency_budget_ms=1,timeout_ms=1,lightgbm_version="4.7.0",
    )
    with pytest.raises(ValueError,match="signature"):
        manifest.validate()


def test_activate_and_rollback_model(tmp_path) -> None:
    _model_dir(tmp_path, "v1")
    _model_dir(tmp_path, "v2")
    activate_model(tmp_path,"v1")
    activate_model(tmp_path,"v2")
    assert rollback_model(tmp_path) == "v1"
    assert json.loads((tmp_path/"active.json").read_text())["active"] == "v1"


def test_first_activation_rolls_back_to_weighted_score_baseline(tmp_path) -> None:
    _model_dir(tmp_path, "v1")
    activate_model(tmp_path, "v1")

    assert rollback_model(tmp_path) == WEIGHTED_SCORE_BASELINE
    assert json.loads((tmp_path / "active.json").read_text())["active"] == WEIGHTED_SCORE_BASELINE
    assert rollback_model(tmp_path) == WEIGHTED_SCORE_BASELINE
    assert json.loads((tmp_path / "active.json").read_text())["active"] == WEIGHTED_SCORE_BASELINE


def test_active_loader_degrades_on_missing_or_invalid_registry(tmp_path) -> None:
    ranker = load_active_ranker(tmp_path)

    assert isinstance(ranker, WeightedScoreOnlineRanker)
    assert ranker.monitor.counters["startup_fallback"] == 1


def test_v3_manifest_rejects_alias_enablement() -> None:
    manifest = ModelManifest(
        model_version="v",
        feature_version=FEATURE_VERSION,
        feature_signature=feature_signature(),
        feature_names=list(FEATURE_NAMES),
        training_data_sha256="x",
        n_estimators=1,
        latency_budget_ms=250,
        timeout_ms=350,
        lightgbm_version="4.7.0",
        alias_enabled=True,
    )
    with pytest.raises(ValueError, match="不支持 Alias"):
        manifest.validate()


@pytest.mark.asyncio
async def test_weighted_fallback_uses_online_only_contract() -> None:
    ranker = WeightedScoreOnlineRanker(reason="test")
    row = {
        "query": "年假规则",
        "routes": {
            "dense": [
                {"chunk_id": "a", "doc_id": 1, "dataset_id": 9, "score": 0.8},
                {"chunk_id": "b", "doc_id": 2, "dataset_id": 9, "score": 0.7},
            ],
            "sparse": [{"chunk_id": "b", "doc_id": 2, "dataset_id": 9, "score": 5.0}],
            "bm25": [{"chunk_id": "b", "doc_id": 2, "dataset_id": 9, "score": 8.0}],
        },
    }

    result = await ranker.rank(row, {"a": "年假申请流程", "b": "年假天数与结转规则"})

    assert result.ranked_chunk_ids == ["a", "b"]
    assert result.mode == "fallback_weighted_score"
    assert result.model_version == WEIGHTED_SCORE_BASELINE


def test_rollback_policy_requires_sample_floor_and_checks_fallback() -> None:
    monitor=RankerMonitor()
    for _ in range(99):
        monitor.record(mode="fallback_timeout",elapsed_ms=30)
    policy=RollbackPolicy(min_requests=100,max_fallback_rate=0.02,max_latency_p95_ms=25)
    assert policy.violations(monitor.snapshot()) == []
    monitor.record(mode="ltr",elapsed_ms=30)
    assert {reason.split("=")[0] for reason in policy.violations(monitor.snapshot())} == {
        "fallback_rate","latency_p95_ms",
    }
