"""Actual tiny Boosters verify paths; no research data or research-model fits."""

from __future__ import annotations

import json
from copy import deepcopy

import numpy as np
import pytest

from linkrag_eval.retrieval.learning_to_rank.diagnostic_trees import TreeAuditError, audit_pair
from linkrag_eval.retrieval.learning_to_rank.experiment import FEATURE_NAMES

lgb = pytest.importorskip("lightgbm")


@pytest.fixture(scope="module")
def boosters():
    result = {}
    for mode in ("ordinary", "nan", "zero", "constant"):
        values = [-4.0, -2.0, -1.0, 1.0, 2.0, 4.0]
        labels = [0, 0, 0, 1, 1, 1]
        if mode == "nan":
            values[-1] = np.nan
        elif mode == "zero":
            values[2], labels[2] = 0.0, 1
        x = np.zeros((24, len(FEATURE_NAMES)), dtype=np.float64)
        x[:, 0] = np.tile(values, 4)
        if mode == "constant":
            x[:] = 0
        dataset = lgb.Dataset(x, label=np.tile(labels, 4), group=[6] * 4,
                              feature_name=FEATURE_NAMES)
        result[mode] = lgb.train({
            "objective": "lambdarank", "metric": "None", "verbosity": -1,
            "num_threads": 1, "num_leaves": 3, "min_data_in_leaf": 1,
            "min_data_in_bin": 1, "learning_rate": 0.17,
            "zero_as_missing": mode == "zero", "deterministic": True,
            "force_col_wise": True, "seed": 7,
        }, dataset, num_boost_round=6)
    return result


def row(value):
    result = np.zeros(len(FEATURE_NAMES), dtype=np.float64)
    result[0] = value
    return result


def audit(booster, preferred, other, **kwargs):
    scores = booster.predict(np.stack([preferred, other]), raw_score=True,
                             num_iteration=-1, start_iteration=0, num_threads=1)
    return audit_pair(booster=booster, preferred_features=preferred, other_features=other,
                      feature_names=FEATURE_NAMES, preferred_score=scores[0],
                      other_score=scores[1], **kwargs)


def test_all_existing_trees_reconstruct_scores_without_double_shrinkage(boosters, monkeypatch):
    booster = boosters["ordinary"]
    monkeypatch.setattr(booster, "best_iteration", 1)
    result = audit(booster, row(4), row(-4))
    assert result["tree_count"] == booster.num_trees() == 6
    assert result["different_leaf_count"] == 6
    assert not result["full_features_exactly_equal"]
    assert result["raw_delta"] > 0
    assert result["strict_direction"] == "preferred"
    assert result["verification"]["passed"]
    assert result["verification"]["atol"] == 1e-10
    assert result["verification"]["rtol"] == 0
    assert result["verification"]["max_abs_score_error"] <= 1e-10
    assert result["verification"]["max_abs_delta_error"] <= 1e-10
    assert result["top_positive_trees"] and not result["top_negative_trees"]
    assert all("path" in tree["preferred"] for tree in result["top_positive_trees"])
    assert any(tree["shrinkage"] == 0.17 for tree in result["trees"])
    wrongly_shrunk = sum(tree["delta"] * tree["shrinkage"] for tree in result["trees"])
    assert abs(wrongly_shrunk - result["raw_delta"]) > 1e-4
    for tree in result["trees"]:
        for side in ("preferred", "other"):
            leaf = tree[side]
            assert leaf["leaf_index"] == leaf["pred_leaf_index"]
            assert leaf["leaf_output"] == leaf["get_leaf_output"]
    json.dumps(result, allow_nan=False)


def test_threshold_equality_takes_left_and_next_float_takes_right(boosters):
    root = boosters["ordinary"].dump_model()["tree_info"][0]["tree_structure"]
    threshold = root["threshold"]
    result = audit(boosters["ordinary"], row(threshold), row(np.nextafter(threshold, np.inf)))
    paths = result["trees"][0]
    assert paths["preferred"]["path"][0]["branch"] == "left"
    assert paths["other"]["path"][0]["branch"] == "right"
    assert paths["preferred"]["path"][0]["feature_value"] == threshold


@pytest.mark.parametrize("mode,value", [("nan", np.nan), ("zero", 0.0),
                                        ("zero", np.nan), ("zero", 1e-36)])
def test_native_missing_branch_semantics_and_json_safe_paths(boosters, mode, value):
    result = audit(boosters[mode], row(value), row(-4))
    missing = [node for tree in result["trees"] for node in tree["preferred"]["path"]
               if node["is_missing"]]
    assert missing
    for node in missing:
        assert node["branch"] == ("left" if node["default_left"] else "right")
        assert node["missing_type"] == ("NaN" if mode == "nan" else "Zero")
    json.dumps(result, allow_nan=False)


def test_nan_with_no_nan_missing_type_is_compared_as_zero(boosters):
    result = audit(boosters["ordinary"], row(np.nan), row(0))
    node = result["trees"][0]["preferred"]["path"][0]
    assert node["missing_type"] == "None"
    assert node["comparison_value"] == 0.0
    assert node["feature_value"] is None and node["value_is_nan"]
    assert not node["is_missing"]
    assert result["different_leaf_count"] == 0
    assert result["strict_direction"] == "tie"


def test_exact_feature_equality_is_not_leaf_equality_or_a_distance_threshold(boosters):
    same = audit(boosters["ordinary"], row(2), row(2))
    assert same["full_features_exactly_equal"] and same["different_leaf_count"] == 0
    assert same["raw_delta"] == same["reconstructed_delta"] == 0
    assert not same["top_positive_trees"] and not same["top_negative_trees"]
    slightly_different = audit(boosters["ordinary"], row(2), row(np.nextafter(2.0, np.inf)))
    assert not slightly_different["full_features_exactly_equal"]
    assert slightly_different["different_leaf_count"] == 0
    both_nan = audit(boosters["nan"], row(np.nan), row(np.nan))
    assert both_nan["full_features_exactly_equal"]


def test_negative_direction_keeps_label_source_and_negative_paths(boosters):
    result = audit(boosters["ordinary"], row(-4), row(4), label_basis="human_adjudicated")
    assert result["label_basis"] == "human_adjudicated"
    assert result["strict_direction"] == "other"
    assert result["top_negative_trees"] and not result["top_positive_trees"]


def test_constant_tree_omitted_leaf_index_is_verified_as_native_zero(boosters):
    result = audit(boosters["constant"], row(1), row(2))
    assert result["tree_count"] == 1
    assert result["trees"][0]["preferred"]["path"] == []
    assert result["trees"][0]["preferred"]["leaf_index"] == 0
    assert result["different_leaf_count"] == 0


def test_legacy_column_names_are_positional_but_arbitrary_names_are_rejected(boosters):
    original = boosters["ordinary"].model_to_string()
    legacy = original.replace("feature_names=" + " ".join(FEATURE_NAMES),
                              "feature_names=" + " ".join(f"Column_{i}" for i in range(38)))
    result = audit(lgb.Booster(model_str=legacy), row(4), row(-4))
    assert result["trees"][0]["preferred"]["path"][0]["feature_name"] == "dense_score"
    bad = legacy.replace("Column_0 ", "wrong_column ", 1)
    with pytest.raises(TreeAuditError, match="column order"):
        audit(lgb.Booster(model_str=bad), row(4), row(-4))


@pytest.mark.parametrize("problem,match", [
    ("categorical", "decision type"), ("missing", "missing type"),
    ("threshold", "finite number"), ("linear", "linear leaves"),
    ("leaf_value", "dump versus get_leaf_output"), ("tree_count", "tree count"),
    ("average_output", "scalar additive"),
])
def test_bad_or_unsupported_dump_fails_closed(boosters, monkeypatch, problem, match):
    booster = boosters["ordinary"]
    dump = deepcopy(booster.dump_model(num_iteration=-1))
    root = dump["tree_info"][0]["tree_structure"]
    if problem == "categorical":
        root["decision_type"] = "=="
    elif problem == "missing":
        root["missing_type"] = "unknown"
    elif problem == "threshold":
        root["threshold"] = "1||2"
    elif problem in {"linear", "leaf_value"}:
        leaf = root
        while "left_child" in leaf:
            leaf = leaf["left_child"]
        if problem == "linear":
            leaf["leaf_coeff"] = [1]
        else:
            leaf["leaf_value"] += 1
    elif problem == "tree_count":
        dump["tree_info"].pop()
    else:
        dump["average_output"] = True
    monkeypatch.setattr(booster, "dump_model", lambda **_: dump)
    with pytest.raises(TreeAuditError, match=match):
        audit(booster, row(4), row(-4))


def test_wrong_native_leaf_and_wrong_supplied_score_stop_explanation(boosters, monkeypatch):
    booster = boosters["ordinary"]
    original_predict = booster.predict

    def wrong_leaf(*args, **kwargs):
        output = original_predict(*args, **kwargs)
        return output + 1 if kwargs.get("pred_leaf") else output

    monkeypatch.setattr(booster, "predict", wrong_leaf)
    with pytest.raises(TreeAuditError, match="differs from pred_leaf"):
        audit(booster, row(4), row(-4))
    monkeypatch.setattr(booster, "predict", original_predict)
    scores = original_predict(np.stack([row(4), row(-4)]), raw_score=True, num_threads=1)
    with pytest.raises(TreeAuditError, match="Supplied versus native raw score"):
        audit_pair(booster=booster, preferred_features=row(4), other_features=row(-4),
                   feature_names=FEATURE_NAMES, preferred_score=scores[0] + 1e-6,
                   other_score=scores[1])


def test_tolerance_does_not_turn_a_nonzero_native_margin_into_a_tie(boosters):
    booster = lgb.Booster(model_str=boosters["ordinary"].model_to_string(num_iteration=1))
    native = booster.predict(np.stack([row(4), row(-4)]), pred_leaf=True, num_threads=1)
    booster.set_leaf_output(0, int(native[0, 0]), 1e-12)
    booster.set_leaf_output(0, int(native[1, 0]), 0)
    result = audit(booster, row(4), row(-4))
    assert result["raw_delta"] == 1e-12
    assert result["strict_direction"] == "preferred"
    with pytest.raises(TreeAuditError, match="different strict preference"):
        audit_pair(booster=booster, preferred_features=row(4), other_features=row(-4),
                   feature_names=FEATURE_NAMES, preferred_score=0, other_score=0)


def test_opposing_tree_outputs_cancel_but_keep_the_small_strict_remainder(boosters):
    booster = lgb.Booster(model_str=boosters["ordinary"].model_to_string())
    leaves = booster.predict(np.stack([row(4), row(-4)]), pred_leaf=True, num_threads=1)
    contributions = [1.0, -1.0, 1e-12, 0.0, 0.0, 0.0]
    for index, delta in enumerate(contributions):
        booster.set_leaf_output(index, int(leaves[0, index]), delta)
        booster.set_leaf_output(index, int(leaves[1, index]), 0.0)
    result = audit(booster, row(4), row(-4))
    assert result["raw_delta"] == result["reconstructed_delta"] == 1e-12
    assert result["strict_direction"] == "preferred"
    assert result["different_leaf_count"] == 6
    assert [t["tree_index"] for t in result["top_positive_trees"]] == [0, 2]
    assert [t["tree_index"] for t in result["top_negative_trees"]] == [1]


def test_input_shape_dtype_and_schema_are_explicit(boosters):
    kwargs = {"booster": boosters["ordinary"], "preferred_features": row(4),
              "other_features": row(-4), "feature_names": FEATURE_NAMES,
              "preferred_score": 1, "other_score": 0}
    for override, match in [({"feature_names": list(reversed(FEATURE_NAMES))}, "38-column order"),
                            ({"preferred_features": np.zeros(37)}, "38-value"),
                            ({"preferred_features": row(4).astype(np.int64)}, "38-value"),
                            ({"preferred_features": row(np.inf)}, "infinite")]:
        with pytest.raises(TreeAuditError, match=match):
            audit_pair(**{**kwargs, **override})
