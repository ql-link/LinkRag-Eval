from __future__ import annotations

import copy
import json

import numpy as np
import pytest

from linkrag_eval.retrieval.learning_to_rank.features import ENGLISH_FEATURE_VERSION, FEATURE_NAMES
from linkrag_eval.retrieval.learning_to_rank.online import LambdaMartOnlineRanker
from linkrag_eval.retrieval.learning_to_rank.subject_binding import (
    RECORD_RULE_VERSION,
    REPAIRED_RULE_VERSION,
    RULE_VERSION,
)
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


@pytest.mark.parametrize("version", [RULE_VERSION, REPAIRED_RULE_VERSION, RECORD_RULE_VERSION])
def test_offline_model_roundtrip_rejects_version_and_column_mismatch(tmp_path, version):
    import lightgbm as lgb
    schema = contract("E3", rules_version=version)
    x = np.random.default_rng(1).random((30, 41)).astype(np.float32)
    booster = lgb.train({"objective": "regression", "num_threads": 1, "verbosity": -1,
                         "min_data_in_leaf": 2},
                        lgb.Dataset(x, label=x[:, -1].copy(), feature_name=schema["feature_names"]), num_boost_round=2)
    path = tmp_path / "model"
    save_bundle(path, booster.model_to_string(), arm="E3", fit={"purpose": "synthetic unit test"}, rules_version=version)
    model = OfflineBindingModel(path, expected_contract=schema)
    assert np.array_equal(model.predict(x, feature_contract=schema), booster.predict(x, num_threads=1))
    with pytest.raises(ValueError, match="contract"):
        OfflineBindingModel(path, expected_contract=contract("E1"))
    with pytest.raises(ValueError, match="contract"):
        model.predict(x[:, :38], feature_contract=schema)
    other_version = RULE_VERSION if version == REPAIRED_RULE_VERSION else REPAIRED_RULE_VERSION
    with pytest.raises(ValueError, match="contract"):
        OfflineBindingModel(path, expected_contract=contract("E3", rules_version=other_version))
    with pytest.raises(ValueError, match="contract"):
        model.predict(x, feature_contract=contract("E3", rules_version=other_version))
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


def test_score_cache_cannot_cross_extraction_versions():
    base = np.zeros((1, 38), dtype=np.float32)
    row = {"query_structure_supported": 1, "extraction_incomplete": 0,
           "loose": 1., "sentence": .5, "entity": 1.}
    v2 = {**row, "rules_version": REPAIRED_RULE_VERSION}
    for score, version in ((row, REPAIRED_RULE_VERSION), (v2, RULE_VERSION)):
        with pytest.raises(ValueError, match="cache extraction rules mismatch"):
            augment(base, [score], arm="E3", base_feature_version=ENGLISH_FEATURE_VERSION,
                    rules_version=version)
    assert augment(base, [v2], arm="E3", base_feature_version=ENGLISH_FEATURE_VERSION,
                   rules_version=REPAIRED_RULE_VERSION)[0, -1] == 1.


def test_v3_model_cache_requires_both_representation_and_matcher_identity():
    base = np.zeros((1, 38), dtype=np.float32)
    schema = contract("E1", rules_version=RECORD_RULE_VERSION)
    row = {"query_structure_supported": 1, "extraction_incomplete": 0,
           "loose": 1., "sentence": 1., "entity": 1., "rules_version": RECORD_RULE_VERSION}
    for matcher in (None, "unrecorded_semantic_matcher"):
        bad = {**row, "matcher_version": matcher}
        with pytest.raises(ValueError, match="matcher version"):
            augment(base, [bad], arm="E1", base_feature_version=ENGLISH_FEATURE_VERSION,
                    rules_version=RECORD_RULE_VERSION)
    result = augment(base, [{**row, "matcher_version": schema["matcher_version"]}], arm="E1",
                     base_feature_version=ENGLISH_FEATURE_VERSION, rules_version=RECORD_RULE_VERSION)
    assert result.shape == (1, 41) and result[0, -1] == 1
    assert schema["feature_version"] != contract("E1", rules_version=REPAIRED_RULE_VERSION)["feature_version"]
