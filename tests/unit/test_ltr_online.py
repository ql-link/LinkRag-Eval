from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

import pytest

from linkrag_eval.retrieval.learning_to_rank.experiment import FEATURE_NAMES, FEATURE_VERSION
from linkrag_eval.retrieval.learning_to_rank.online import (
    ModelManifest,
    RankerMonitor,
    RollbackPolicy,
    activate_model,
    feature_signature,
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
        training_data_sha256="a"*64, alias_registry_version="aliases-v1",
        n_estimators=10, latency_budget_ms=25, timeout_ms=40,
        model_file_sha256=hashlib.sha256(model.read_bytes()).hexdigest(),
    )
    (path/"manifest.json").write_text(json.dumps(asdict(manifest)))


def test_feature_signature_rejects_drift() -> None:
    manifest=ModelManifest(
        model_version="v",feature_version=FEATURE_VERSION,feature_signature="wrong",
        feature_names=list(FEATURE_NAMES),training_data_sha256="x",alias_registry_version="a",
        n_estimators=1,latency_budget_ms=1,timeout_ms=1,
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
