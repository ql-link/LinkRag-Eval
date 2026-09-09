from __future__ import annotations

import copy
import json

import numpy as np
import pytest

from linkrag_eval.retrieval.learning_to_rank.features import ENGLISH_FEATURE_VERSION, FEATURE_NAMES
from linkrag_eval.retrieval.learning_to_rank.online import LambdaMartOnlineRanker
from linkrag_eval.retrieval.learning_to_rank.subject_binding_model import (
    OfflineBindingModel,
    augment,
    contract,
    save_bundle,
)


def test_arms_share_status_columns_and_missing_not_zero():
    base = np.zeros((2, len(FEATURE_NAMES)), dtype=np.float32)
    rows = [{"query_structure_supported": 0, "extraction_incomplete": 1,
             "loose": None, "sentence": None, "entity": None},
            {"query_structure_supported": 1, "extraction_incomplete": 0,
             "loose": 1., "sentence": .5, "entity": 1.}]
    matrices = [augment(base, rows, arm=arm, base_feature_version=ENGLISH_FEATURE_VERSION)
                for arm in ("EM", "E1", "E2", "E3")]
    assert all(np.array_equal(x[:, :40], matrices[0][:, :40]) for x in matrices)
    assert matrices[0][0, -1] == 0
    assert all(np.isnan(x[0, -1]) for x in matrices[1:])
    assert (matrices[1][1, -1], matrices[2][1, -1], matrices[3][1, -1]) == (1., .5, 1.)
    with pytest.raises(ValueError):
        augment(np.zeros((2, 41)), rows, arm="E3", base_feature_version=ENGLISH_FEATURE_VERSION)
    with pytest.raises(ValueError, match="English"):
        augment(base, rows, arm="E3", base_feature_version="candidate_difference_v3")


def test_offline_model_roundtrip_rejects_version_and_column_mismatch(tmp_path):
    import lightgbm as lgb
    schema = contract("E3")
    x = np.random.default_rng(1).random((30, 41)).astype(np.float32)
    booster = lgb.train({"objective": "regression", "num_threads": 1, "verbosity": -1,
                         "min_data_in_leaf": 2},
                        lgb.Dataset(x, label=x[:, -1].copy(), feature_name=schema["feature_names"]), num_boost_round=2)
    path = tmp_path / "model"
    save_bundle(path, booster.model_to_string(), arm="E3", fit={"purpose": "synthetic unit test"})
    model = OfflineBindingModel(path, expected_contract=schema)
    assert np.array_equal(model.predict(x, feature_contract=schema), booster.predict(x, num_threads=1))
    with pytest.raises(ValueError, match="contract"):
        OfflineBindingModel(path, expected_contract=contract("E1"))
    with pytest.raises(ValueError, match="contract"):
        model.predict(x[:, :38], feature_contract=schema)
    changed = copy.deepcopy(schema)
    changed["feature_names"].reverse()
    with pytest.raises(ValueError, match="contract"):
        model.predict(x, feature_contract=changed)
    with pytest.raises((ValueError, TypeError)):
        LambdaMartOnlineRanker(path)
    manifest = json.loads((path / "manifest.json").read_text())
    manifest["contract"]["parser"]["extraction_rules"] = "unknown"
    (path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="contract"):
        OfflineBindingModel(path, expected_contract=schema)
