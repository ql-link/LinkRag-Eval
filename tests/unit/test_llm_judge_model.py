"""Fake-judge L3 training/inference scope and offline model integrity checks."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from linkrag_eval.retrieval.learning_to_rank import llm_judge as judge
from linkrag_eval.retrieval.learning_to_rank import pairwise_training as training
from linkrag_eval.retrieval.learning_to_rank.features import ENGLISH_FEATURE_VERSION, FEATURE_NAMES
from linkrag_eval.retrieval.learning_to_rank.llm_judge_model import (
    OfflineJudgeModel,
    augment,
    augmented_dataset,
    contract,
    save_bundle,
)

from .test_llm_judge import META, FakeRunner, pool
from .test_ltr_pairwise_training import _pair


def test_fake_l3_scores_only_enter_baseline_top_k(tmp_path):
    queries, labels, inputs, predictions = pool()
    items = judge.build_items(queries, labels, inputs, stage1=predictions, level="l3", top_k=2)
    rows, _ = judge.judge_items(items, FakeRunner(), tmp_path / "judge", metadata=META)
    schema = contract(model=META["model"], top_k=2)
    base = np.zeros((3, 38), dtype=np.float32)
    base[:, FEATURE_NAMES.index(judge.STAGE1_FEATURE)] = [3., 2., 1.]
    scores = judge.judged_scores(rows)["q"]
    matrix = augment(base, ["a", "b", "c"], judge.score_maps(predictions)["q"], scores,
                     base_feature_version=ENGLISH_FEATURE_VERSION, feature_contract=schema)
    assert matrix.shape == (3, 40) and list(matrix[:, -2]) == [1, 1, 0]
    assert np.isnan(matrix[2, -1]) and matrix[0, -1] == 0
    for values, version, data in ((dict(scores, unknown=4), ENGLISH_FEATURE_VERSION, base),
                                   (scores, "candidate_difference_v3", base),
                                   (scores, ENGLISH_FEATURE_VERSION, base[:, :37])):
        with pytest.raises(ValueError):
            augment(data, ["a", "b", "c"], judge.score_maps(predictions)["q"], values,
                    base_feature_version=version, feature_contract=schema)


def make_booster(schema):
    import lightgbm as lgb
    x = np.zeros((30, 40), dtype=np.float32)
    x[:, -2] = 1
    x[:, -1] = np.arange(30) % 5
    model = lgb.train({"objective": "regression", "num_threads": 1, "verbosity": -1,
                      "min_data_in_leaf": 2}, lgb.Dataset(x, label=x[:, -1].copy(),
                      feature_name=schema["feature_names"]), num_boost_round=2)
    return model, x


def test_bundle_roundtrip_column_contract_runtime_and_integrity(tmp_path):
    schema = contract(model=META["model"])
    booster, x = make_booster(schema)
    bundle = tmp_path / "model"
    save_bundle(bundle, booster.model_to_string(), feature_contract=schema, fit=META)
    model = OfflineJudgeModel(bundle, expected_contract=schema)
    assert np.array_equal(model.predict(x, feature_contract=schema), booster.predict(x, num_threads=1))
    with pytest.raises(FileExistsError):
        save_bundle(bundle, booster.model_to_string(), feature_contract=schema, fit=META)
    for bad in (x[:, :38], np.ones((2, 41), dtype=np.float32), x.astype(np.float64)):
        with pytest.raises(ValueError):
            model.predict(bad, feature_contract=schema)
    changed = dict(schema, feature_names=list(reversed(schema["feature_names"])))
    with pytest.raises(ValueError, match="contract"):
        model.predict(x, feature_contract=changed)
    with pytest.raises(ValueError, match="contract"):
        OfflineJudgeModel(bundle, expected_contract=contract(model="another-model"))
    with pytest.raises(ValueError, match="contract"):
        save_bundle(tmp_path / "bad", booster.model_to_string(), feature_contract=changed, fit=META)
    invalid = x.copy()
    invalid[0, -2] = 0
    with pytest.raises(ValueError, match="availability"):
        model.predict(invalid, feature_contract=schema)
    invalid[0, -1] = np.nan
    model.predict(invalid, feature_contract=schema)
    (bundle / "model.txt").write_text((bundle / "model.txt").read_text() + "\n")
    with pytest.raises(ValueError, match="integrity"):
        OfflineJudgeModel(bundle, expected_contract=schema)


def test_augmentation_keeps_pairwise_loss_and_source_weights(tmp_path):
    q, labels, inputs = _pair("train")
    dataset = training.prepare_pairwise_dataset(role="train", queries=q, supervision=labels, inputs=inputs,
                                               feature_version=ENGLISH_FEATURE_VERSION)
    baseline = judge.score_maps(judge.stage1_scores(q, inputs))
    predictions = [{"source_query_id": qid, "scores": [{"chunk_id": cid, "score": value}
                    for cid, value in scores.items()]} for qid, scores in baseline.items()]
    items = judge.build_items(q, labels, inputs, stage1=predictions, level="l3", top_k=2)
    rows, _ = judge.judge_items(items, FakeRunner(), tmp_path / "judge", metadata=META)
    result = augmented_dataset(dataset, baseline, judge.judged_scores(rows),
                               feature_contract=contract(model=META["model"], top_k=2))
    assert result.x.shape == (4, 40)
    assert result.groups == dataset.groups
    assert np.array_equal(result.y, dataset.y) and np.array_equal(result.weights, dataset.weights)
    for item in result.queries:
        top = set(judge.baseline_order(baseline[item.query_id])[:2])
        assert all(np.isnan(item.features[i, -1]) for i, cid in enumerate(item.chunk_ids) if cid not in top)


def load_script():
    path = Path(__file__).resolve().parents[2] / "scripts/llm_judge_pilot.py"
    spec = importlib.util.spec_from_file_location("judge_pilot_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_train_and_evaluate_l3_cli_with_fake_judge_and_fit(tmp_path, monkeypatch):
    script = load_script()
    schema = contract(model=META["model"], top_k=2)
    role_inputs, paths, baseline_paths, stage1_paths, score_paths, datasets = {}, {}, {}, {}, {}, {}
    for role in ("train", "development"):
        queries, labels, inputs = _pair(role, role=role)
        role_inputs[role] = (queries, labels, inputs)
        folder = tmp_path / role
        folder.mkdir()
        paths[role] = {name: folder / f"{name}.jsonl" for name in ("queries", "supervision", "inputs")}
        for name, rows in zip(paths[role], role_inputs[role], strict=True):
            judge.write_rows(paths[role][name], rows)
        datasets[role] = training.load_dataset(role=role, feature_version=ENGLISH_FEATURE_VERSION, **paths[role])
        predictions = [{"source_query_id": q.query_id, "scores": [{"chunk_id": cid, "score": float(3 - i)}
                        for i, cid in enumerate(q.chunk_ids)]} for q in datasets[role].queries]
        baseline_paths[role] = folder / "baseline.jsonl"
        judge.write_rows(baseline_paths[role], predictions)
        first = judge.stage1_scores(queries, inputs)
        stage1_paths[role] = folder / "stage1.jsonl"
        judge.write_rows(stage1_paths[role], first)
        items = judge.build_items(queries, labels, inputs, stage1=first, level="l3", top_k=2)
        judge.judge_items(items, FakeRunner(), folder / "judged", metadata=META)
        score_paths[role] = folder / "judged/scores.jsonl"
    config = tmp_path / "config.json"
    judge.write_json(config, {"config_id": "c3", "policy_source": "unused-fake-control",
                             "inputs": {r: {k: str(v) for k, v in p.items()} for r, p in paths.items()}})
    monkeypatch.setattr(script, "SAVED", baseline_paths["development"])
    monkeypatch.setattr(script, "runtime_metadata", lambda *a: META)
    monkeypatch.setattr(script, "role_paths", lambda role: paths[role])
    def report(role, base, judged, summary):
        result, rows = judge.evaluate_pairs(role_inputs[role][1], judge.score_maps(base), judged)
        return {"official": result, "judge_run": summary}, rows
    monkeypatch.setattr(script, "evaluation_report", report)
    monkeypatch.setattr(script, "human_population", lambda *args: ({r["source_query_id"]:
        (r["preferred_chunk_id"], r["other_chunk_id"]) for r in role_inputs["development"][1]}, {"eligible": 2}))
    seen = []
    def fake_e0(train, development, **kwargs):
        assert kwargs["config_id"] == "c3" and train.feature_version == ENGLISH_FEATURE_VERSION
        out = kwargs["out_dir"]
        out.mkdir()
        judge.write_rows(out / "dev-predictions.jsonl", judge.read_rows(baseline_paths["development"]))
        seen.append("E0")
        return {"actual_trees": 2}
    def fake_fit(args, *, timeout_seconds, progress):
        assert seen == ["E0"]
        assert args[0].shape[1] == args[4].shape[1] == 40
        assert args[6] == training.training_parameters(training.GRID[2])
        assert args[7] == schema["feature_names"] and timeout_seconds == training.CANDIDATE_TIMEOUT_SECONDS
        assert np.array_equal(args[3], datasets["train"].weights)
        progress({"iteration": 1})
        return make_booster(schema)[0].model_to_string(), {"best_iteration": 2}
    monkeypatch.setattr(training, "train_and_select", fake_e0)
    monkeypatch.setattr(training, "_bounded_fit", fake_fit)
    out = tmp_path / "trained"
    script.main(["train-l3", "--out", str(out), "--config", str(config), "--top-k", "2",
                 "--train-baseline", str(baseline_paths["train"]), "--dev-baseline", str(baseline_paths["development"]),
                 "--train-scores", str(score_paths["train"]), "--dev-scores", str(score_paths["development"]),
                 "--train-stage1", str(stage1_paths["train"]), "--dev-stage1", str(stage1_paths["development"])])
    inference = tmp_path / "inference"
    script.main(["evaluate-l3", "--out", str(inference), "--role", "development", "--baseline",
                 str(baseline_paths["development"]), "--scores", str(score_paths["development"]),
                 "--bundle", str(out / "judge-model"), "--stage1", str(stage1_paths["development"])])
    judge.check_exact(judge.read_rows(inference / "predictions.jsonl"), judge.read_rows(out / "dev-predictions.jsonl"))
    report = json.loads((inference / "results.json").read_text())
    assert report["official"]["rankers"]["L3"]["pairwise"]["n"] == 2
    assert report["official"]["rankers"]["L3"]["list"]["n"] == 2
    assert report["human_v5"]["rankers"]["L3"]["list"]["n"] == 2
    assert report["judge_feature_splits"]["judge_available"] == 0
    assert report["judge_feature_splits"]["judge_score"] > 0
    assert report["judge_feature_splits"] == json.loads((out / "results.json").read_text())["judge_feature_splits"]


def test_cli_existing_output_rejected_before_runner_or_input_read(tmp_path):
    script = load_script()
    with pytest.raises(FileExistsError):
        script.judge(SimpleNamespace(out=tmp_path))
    with pytest.raises(FileExistsError):
        script.evaluate(SimpleNamespace(out=tmp_path))
    with pytest.raises(FileExistsError):
        script.train_l3(SimpleNamespace(out=tmp_path))


def test_stage1_model_masks_superset_and_rejects_e0_scores_and_old_contract():
    base = np.zeros((3, 38), dtype=np.float32)
    base[:, FEATURE_NAMES.index(judge.STAGE1_FEATURE)] = [0., 4., 3.]
    schema = contract(model=META["model"], top_k=2)
    first, e0 = {"a": 0., "b": 4., "c": 3.}, {"a": 4., "b": 3., "c": 0.}
    scores = {"a": 4, "b": None, "c": 0}
    matrix = augment(base, ["a", "b", "c"], first, scores,
                     base_feature_version=ENGLISH_FEATURE_VERSION, feature_contract=schema)
    assert list(matrix[:, -2]) == [0, 0, 1]
    assert np.isnan(matrix[:2, -1]).all() and matrix[2, -1] == 0
    with pytest.raises(ValueError, match="baseline_score feature"):
        augment(base, ["a", "b", "c"], e0, scores,
                base_feature_version=ENGLISH_FEATURE_VERSION, feature_contract=schema)
    with pytest.raises(ValueError, match="cover stage1"):
        augment(base, ["a", "b", "c"], first, {"a": 4, "b": 1},
                base_feature_version=ENGLISH_FEATURE_VERSION, feature_contract=schema)
    old = dict(schema, feature_version="candidate_difference_v3_en_llm_judge_v1")
    with pytest.raises(ValueError, match="contract"):
        augment(base, ["a", "b", "c"], first, scores,
                base_feature_version=ENGLISH_FEATURE_VERSION, feature_contract=old)
    assert contract(model=META["model"])["top_k"] == 20


def test_stage1_and_items_cli_self_checks_and_no_overwrite(tmp_path, monkeypatch):
    script = load_script()
    queries, labels, inputs, _ = pool()
    paths = {k: tmp_path / f"{k}.jsonl" for k in ("queries", "supervision", "inputs")}
    for k, rows in zip(paths, (queries, labels, inputs), strict=True):
        judge.write_rows(paths[k], rows)
    monkeypatch.setattr(script, "role_paths", lambda role: paths)
    monkeypatch.setattr(script, "runtime_metadata", lambda *a: META)
    monkeypatch.setattr(script, "SCRATCH", tmp_path / "scratch")
    scratch = script.SCRATCH / "development"
    scratch.mkdir(parents=True)
    first = judge.stage1_scores(queries, inputs)
    judge.write_rows(scratch / "stage1-development.jsonl", first)
    expected = judge.build_items(queries, labels, inputs, stage1=first, level="l2", top_k=20)
    judge.write_rows(scratch / "development.jsonl", expected)
    judge.write_json(scratch / "summary.json", {"top_k": 20})
    out = tmp_path / "scores"
    script.main(["stage1-scores", "--role", "development", "--out", str(out)])
    assert judge.read_rows(out / "stage1-development.jsonl") == first
    assert json.loads((out / "summary.json").read_text())["exact_match_with_scratch"]
    items = tmp_path / "items"
    argv = ["items", "--level", "l2", "--role", "development", "--stage1",
            str(out / "stage1-development.jsonl"), "--out", str(items)]
    script.main(argv)
    assert json.loads((items / "summary.json").read_text())["exact_match_with_scratch"]
    with pytest.raises(FileExistsError):
        script.main(argv)
    bad = [{**r, "scores": list(reversed(r["scores"]))} for r in first]
    (scratch / "stage1-development.jsonl").write_text(json.dumps(bad[0]) + "\n")
    with pytest.raises(ValueError, match="differ"):
        script.main(["stage1-scores", "--role", "development", "--out", str(tmp_path / "bad-scores")])


def test_evaluate_l2_cli_with_fake_runner_uses_stage1_superset(tmp_path, monkeypatch):
    script = load_script()
    queries, labels, inputs, base = pool()
    first = [{"source_query_id": "q", "scores": [{"chunk_id": cid, "score": score}
              for cid, score in (("a", 0.), ("b", 4.), ("c", 3.))]}]
    paths = {k: tmp_path / f"{k}.jsonl" for k in ("queries", "supervision", "inputs")}
    for name, rows in zip(paths, (queries, labels, inputs), strict=True):
        judge.write_rows(paths[name], rows)
    judge.write_rows(tmp_path / "base.jsonl", base)
    judge.write_rows(tmp_path / "stage1.jsonl", first)
    items = judge.build_items(queries, labels, inputs, stage1=first, level="l2", top_k=3)
    judge.judge_items(items, FakeRunner(), tmp_path / "judged", metadata=META)
    monkeypatch.setattr(script, "role_paths", lambda role: paths)
    monkeypatch.setattr(script, "SAVED", tmp_path / "base.jsonl")
    monkeypatch.setattr(script, "evaluation_report", lambda *a: ({"baseline_self_check": True}, {}))
    monkeypatch.setattr(script, "human_population", lambda *a: ({"q": ("a", "b")}, {"eligible": 1}))
    for role in ("development", "confirmation"):
        out = tmp_path / role
        script.main(["evaluate-l2", "--role", role, "--baseline", str(tmp_path / "base.jsonl"),
                     "--stage1", str(tmp_path / "stage1.jsonl"), "--scores", str(tmp_path / "judged/scores.jsonl"),
                     "--top-k", "2", "--out", str(out)])
        result = json.loads((out / "results.json").read_text())
        assert set(result["official"]["rankers"]) == {"E0", "stage1", "stage1_judge", "E0_judge"}
        assert result["trigger"]["E0_judge"]["judged_calls_per_query"] == {"q": 2}
        assert ("human_v5" in result) == (role == "development")
        # E0 prefers a, but a is outside stage1 top 2 and must remain in the tail.
        orders = judge.read_rows(out / "orders.jsonl")[0]["orders"]
        assert orders["E0_judge"][-1] == orders["stage1_judge"][-1] == "a"
