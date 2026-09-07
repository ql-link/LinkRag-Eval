from __future__ import annotations

import json

import numpy as np
import pytest

from linkrag_eval.retrieval.learning_to_rank.experiment import FEATURE_NAMES
from linkrag_eval.retrieval.learning_to_rank.online import (
    LambdaMartOnlineRanker,
    export_trained_booster,
    validate_production_bundle,
)


@pytest.fixture
def fitted_booster():
    lightgbm = pytest.importorskip("lightgbm")
    rng = np.random.default_rng(123)
    x = rng.normal(size=(80, len(FEATURE_NAMES))).astype(np.float32)
    y = (x[:, 0].reshape(-1, 2).argsort(axis=1).argsort(axis=1)).reshape(-1)
    params = {"objective": "lambdarank", "metric": "None", "num_leaves": 3,
              "min_data_in_leaf": 2, "verbosity": -1, "num_threads": 1,
              "deterministic": True, "force_col_wise": True}
    booster = lightgbm.train(
        params,
        lightgbm.Dataset(x, label=y, group=[2] * 40, feature_name=list(FEATURE_NAMES)),
        num_boost_round=8,
    )
    assert booster.current_iteration() == 8
    return booster, x, params


def test_export_preserves_selected_prefix_without_refit(tmp_path, monkeypatch, fitted_booster):
    import lightgbm

    booster, x, params = fitted_booster
    expected = booster.predict(x, num_iteration=3, num_threads=1)
    assert not np.array_equal(expected, booster.predict(x, num_iteration=8, num_threads=1))

    def forbidden_fit(*args, **kwargs):
        raise AssertionError("export must not train")

    monkeypatch.setattr(lightgbm, "train", forbidden_fit)
    monkeypatch.setattr(lightgbm.LGBMRanker, "fit", forbidden_fit)
    short_policy = {"version": "test-policy", "max_query_chars": 15,
                    "confidence_threshold": 0.1, "confidence_feature": "ltr_top12_margin",
                    "fallback": "hybrid"}
    out = tmp_path / "model"
    manifest = export_trained_booster(
        booster, out_dir=out, model_version="selected-b", num_iteration=3,
        training_params=params, short_fallback_config=short_policy,
        latency_budget_ms=251, timeout_ms=351,
    )
    loaded = LambdaMartOnlineRanker(out)
    np.testing.assert_array_equal(loaded.model.predict(x, num_threads=1), expected)
    assert manifest.n_estimators == loaded.model.num_trees() == 3
    assert booster.num_trees() == 8
    assert (manifest.latency_budget_ms, manifest.timeout_ms) == (251, 351)
    assert manifest.training_params == params
    assert json.loads((out / "short_fallback.json").read_text()) == short_policy
    assert validate_production_bundle(out)["verified_test_vectors"] == 3


@pytest.mark.parametrize("iteration", [0, -1, 9, True])
def test_export_rejects_invalid_prefix(tmp_path, fitted_booster, iteration):
    booster, _, params = fitted_booster
    with pytest.raises(ValueError, match="tree prefix"):
        export_trained_booster(booster, out_dir=tmp_path / "new", model_version="b",
                               num_iteration=iteration, training_params=params)
    assert not (tmp_path / "new").exists()


def test_export_rejects_feature_order_and_preserves_existing_output(tmp_path, fitted_booster):
    import lightgbm

    booster, _, params = fitted_booster
    text = booster.model_to_string().replace(
        "feature_names=" + " ".join(FEATURE_NAMES),
        "feature_names=" + " ".join(reversed(FEATURE_NAMES)),
    )
    wrong_order = lightgbm.Booster(model_str=text)
    with pytest.raises(ValueError, match="feature count/order"):
        export_trained_booster(wrong_order, out_dir=tmp_path / "wrong", model_version="b",
                               num_iteration=3, training_params=params)
    out = tmp_path / "existing"
    out.mkdir()
    (out / "model.txt").write_text("keep this model")
    with pytest.raises(FileExistsError, match="absent or empty"):
        export_trained_booster(booster, out_dir=out, model_version="b", num_iteration=3,
                               training_params=params)
    assert (out / "model.txt").read_text() == "keep this model"


@pytest.mark.parametrize("change", [
    {"confidence_feature": "entropy"}, {"fallback": "none"},
    {"confidence_threshold": float("nan")}, {"max_query_chars": "15"},
])
def test_export_rejects_unsupported_fallback_before_writing(tmp_path, fitted_booster, change):
    booster, _, params = fitted_booster
    config = {"version": "v1", "max_query_chars": 15, "confidence_threshold": 0.1, **change}
    with pytest.raises(ValueError, match="short fallback policy"):
        export_trained_booster(booster, out_dir=tmp_path / "model", model_version="b",
                               num_iteration=3, training_params=params,
                               short_fallback_config=config)
    assert not (tmp_path / "model").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("threads", [None, 1])
async def test_online_threads_are_explicit_prediction_arguments(
    tmp_path, monkeypatch, fitted_booster, threads,
):
    booster, _, params = fitted_booster
    export_trained_booster(booster, out_dir=tmp_path, model_version="b", num_iteration=3,
                           training_params=params)
    ranker = LambdaMartOnlineRanker(tmp_path, prediction_num_threads=threads)
    original = ranker.model.predict
    calls = []

    def predict(features, **kwargs):
        calls.append(kwargs)
        return original(features, **kwargs)

    monkeypatch.setattr(ranker.model, "predict", predict)
    fixture = json.loads((tmp_path / "test_vectors.json").read_text())["vectors"][0]["input"]
    result = await ranker.rank(
        {"query": fixture["query"], "routes": fixture["routes"]}, fixture["candidate_contents"],
    )
    assert calls == ([{}] if threads is None else [{"num_threads": 1}])
    assert set(result.ranked_chunk_ids) == set(fixture["candidate_contents"])


def test_english_package_binds_rules_and_rejects_legacy_config_and_matrix(tmp_path, fitted_booster):
    from linkrag_eval.retrieval.learning_to_rank.features import (
        ENGLISH_FEATURE_VERSION,
        FEATURE_VERSION,
        FeatureContractError,
        build_online_features,
    )
    from linkrag_eval.retrieval.learning_to_rank.online import feature_signature

    booster, _, params = fitted_booster
    out = tmp_path / "english"
    manifest = export_trained_booster(
        booster, out_dir=out, model_version="en-unit", num_iteration=3,
        training_params=params, feature_version=ENGLISH_FEATURE_VERSION,
    )
    assert manifest.feature_rules_version == "english_basic_v1"
    assert manifest.feature_signature != feature_signature()
    assert feature_signature() == "52a69c3b8ae5e6a5988f62e0a87a775137a4f16ea769bc66829ec664b8782d7b"
    with pytest.raises(FeatureContractError, match="requested feature version"):
        LambdaMartOnlineRanker(out)
    ranker = LambdaMartOnlineRanker(out, feature_version=ENGLISH_FEATURE_VERSION, prediction_num_threads=1)
    vector = json.loads((out / "test_vectors.json").read_text())["vectors"][0]
    _, features = build_online_features(**vector["input"], feature_version=ENGLISH_FEATURE_VERSION)
    np.testing.assert_array_equal(ranker.predict_features(features, feature_version=ENGLISH_FEATURE_VERSION),
                                  vector["expected"]["ltr_scores"])
    with pytest.raises(FeatureContractError, match="matrix version"):
        ranker.predict_features(features, feature_version=FEATURE_VERSION)
    assert validate_production_bundle(out)["verified_test_vectors"] == 3
    old = tmp_path / "legacy"
    export_trained_booster(booster, out_dir=old, model_version="old-unit", num_iteration=3,
                           training_params=params)
    with pytest.raises(FeatureContractError, match="requested feature version"):
        LambdaMartOnlineRanker(old, feature_version=ENGLISH_FEATURE_VERSION)


@pytest.mark.parametrize("field,value", [
    ("feature_rules_version", None), ("feature_rules_version", "future_rules"),
    ("feature_version", "unknown_38"), ("feature_signature", "wrong"),
])
def test_english_manifest_metadata_is_required(tmp_path, fitted_booster, field, value):
    from linkrag_eval.retrieval.learning_to_rank.features import ENGLISH_FEATURE_VERSION
    booster, _, params = fitted_booster
    export_trained_booster(booster, out_dir=tmp_path, model_version="en", num_iteration=3,
                           training_params=params, feature_version=ENGLISH_FEATURE_VERSION)
    p = tmp_path / "manifest.json"
    manifest = json.loads(p.read_text())
    if value is None:
        manifest.pop(field)
    else:
        manifest[field] = value
    p.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        LambdaMartOnlineRanker(tmp_path, feature_version=ENGLISH_FEATURE_VERSION)


def test_only_explicit_legacy_contract_allows_missing_rules_metadata(tmp_path, fitted_booster):
    from linkrag_eval.retrieval.learning_to_rank.online import _write_sha256sums
    booster, _, params = fitted_booster
    export_trained_booster(booster, out_dir=tmp_path, model_version="old", num_iteration=3,
                           training_params=params)
    for filename in ["manifest.json", "feature_contract.json"]:
        p = tmp_path / filename
        item = json.loads(p.read_text())
        item.pop("feature_rules_version")
        p.write_text(json.dumps(item))
    _write_sha256sums(tmp_path)
    assert validate_production_bundle(tmp_path)["verified_test_vectors"] == 3
    p = tmp_path / "manifest.json"
    item = json.loads(p.read_text())
    item.pop("feature_version")
    p.write_text(json.dumps(item))
    with pytest.raises(TypeError):
        LambdaMartOnlineRanker(tmp_path)


@pytest.mark.asyncio
async def test_version_mismatch_is_not_an_online_fallback(tmp_path, fitted_booster):
    from linkrag_eval.retrieval.learning_to_rank.features import (
        ENGLISH_FEATURE_VERSION,
        FeatureContractError,
    )
    from linkrag_eval.retrieval.learning_to_rank.online import load_active_ranker
    booster, _, params = fitted_booster
    export_trained_booster(booster, out_dir=tmp_path / "legacy", model_version="old", num_iteration=3,
                           training_params=params)
    (tmp_path / "active.json").write_text(json.dumps({"active": "legacy"}))
    with pytest.raises(FeatureContractError):
        load_active_ranker(tmp_path, feature_version=ENGLISH_FEATURE_VERSION)
    ranker = LambdaMartOnlineRanker(tmp_path / "legacy")
    with pytest.raises(FeatureContractError, match="request feature version"):
        await ranker.rank({"feature_version": ENGLISH_FEATURE_VERSION}, {})
