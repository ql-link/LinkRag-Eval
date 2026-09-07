"""Partial preference supervision must not turn unlabelled candidates into negatives."""

from __future__ import annotations

import json
import multiprocessing
import shutil
import time
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from linkrag_eval.retrieval.learning_to_rank import pairwise_training
from linkrag_eval.retrieval.learning_to_rank.experiment import (
    FEATURE_NAMES,
    build_online_features,
)
from linkrag_eval.retrieval.learning_to_rank.pairwise_training import (
    GRID,
    _bounded_fit,
    _fit_candidate,
    _layout,
    assert_disjoint_roles,
    development_metrics,
    make_development_metric,
    prepare_pairwise_dataset,
    select_best_candidate,
    train_and_select,
    training_parameters,
)


def test_feature_versions_recompute_raw_candidates_without_cross_version_cache():
    from linkrag_eval.retrieval.learning_to_rank.features import (
        ENGLISH_FEATURE_VERSION,
        FEATURE_VERSION,
    )
    queries, labels, inputs = _pair("version-check")
    for q, row in zip(queries, inputs, strict=True):
        q["query"] = row["query"] = "Which door is not open?" + q["source_query_id"]
        row["features"] = [[999.0] * 38]
        row["feature_version"] = "untrusted-cache"
    data = {"role": "train", "queries": queries, "supervision": labels, "inputs": inputs}
    legacy = prepare_pairwise_dataset(**data)
    english = prepare_pairwise_dataset(**data, feature_version=ENGLISH_FEATURE_VERSION)
    again = prepare_pairwise_dataset(**data)
    assert legacy.feature_version == FEATURE_VERSION and english.feature_version == ENGLISH_FEATURE_VERSION
    assert english.summary["feature_rules_version"] == "english_basic_v1"
    assert not np.array_equal(legacy.x, english.x)
    np.testing.assert_array_equal(legacy.x, again.x)
    np.testing.assert_array_equal(legacy.y, english.y)
    np.testing.assert_array_equal(legacy.weights, english.weights)
    assert np.max(english.x) < 999


def _pair(
    pair_id: str,
    *,
    role: str = "train",
    source_group_id: str | None = None,
    same_query: bool = False,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Two official directions, distinct anonymous documents, and one background hit."""
    group = source_group_id or f"source-{pair_id}"
    chunk_ids = [f"{pair_id}-left", f"{pair_id}-right", f"{pair_id}-background"]
    contents = ["The blue door is open.", "The blue door is closed.", "The green window."]
    candidates = [
        {
            "chunk_id": chunk_id,
            "dataset_id": 992000,
            "doc_id": index + 1,
            "source_passage_id": f"passage-{chunk_id}",
            "content": content,
            "ordinal": 0,
        }
        for index, (chunk_id, content) in enumerate(zip(chunk_ids, contents, strict=True))
    ]
    queries, supervision, inputs = [], [], []
    for index, direction in enumerate(("q1", "q2")):
        query_id = f"{pair_id}-{direction}"
        query = f"{pair_id}: Which door is {'open' if same_query or index == 0 else 'closed'}?"
        preferred, other = chunk_ids[index], chunk_ids[1 - index]
        queries.append({"source_query_id": query_id, "query": query})
        supervision.append(
            {
                "source_query_id": query_id,
                "role": role,
                "source_group_id": group,
                "pair_id": pair_id,
                "direction": direction,
                "preferred_chunk_id": preferred,
                "other_chunk_id": other,
                "preferred_passage_id": f"passage-{preferred}",
                "other_passage_id": f"passage-{other}",
                "official_label_available": True,
                "structural_conflict": False,
                "semantic_uncertain": False,
                "label_basis": "official_pair_preference",
                "issue_reasons": [],
            }
        )
        inputs.append(
            {
                "source_query_id": query_id,
                "sample_id": query_id,
                "query": query,
                "dataset_ids": [992000],
                "routes": {
                    "dense": [
                        {
                            "chunk_id": row["chunk_id"],
                            "dataset_id": row["dataset_id"],
                            "doc_id": row["doc_id"],
                            "score": score,
                            "rank": rank,
                        }
                        for rank, (row, score) in enumerate(
                            zip(candidates, (0.6, 0.4, 0.0), strict=True)
                        )
                    ],
                    "sparse": [],
                    "bm25": [],
                },
                "candidate_rows": deepcopy(candidates),
                "source_rows": [
                    {
                        "dataset_id": row["dataset_id"],
                        "chunk_id": row["chunk_id"],
                        "source_passage_id": row["source_passage_id"],
                    }
                    for row in candidates
                ],
                "failed_sources": [],
                "route_status": {"dense": "ok", "sparse": "empty", "bm25": "empty"},
                "input_issues": [],
                "status": "ready",
                "ranking_input_ready": True,
            }
        )
    return queries, supervision, inputs


def _prepare(*pairs: tuple[list[dict], list[dict], list[dict]], role: str = "train"):
    return prepare_pairwise_dataset(
        role=role,
        queries=[row for pair in pairs for row in pair[0]],
        supervision=[row for pair in pairs for row in pair[1]],
        inputs=[row for pair in pairs for row in pair[2]],
    )


def _drop_candidate(row: dict, chunk_id: str) -> None:
    for hits in row["routes"].values():
        hits[:] = [hit for hit in hits if hit["chunk_id"] != chunk_id]
        for rank, hit in enumerate(hits):
            hit["rank"] = rank
    row["candidate_rows"] = [
        candidate for candidate in row["candidate_rows"] if candidate["chunk_id"] != chunk_id
    ]
    row["source_rows"] = [
        candidate for candidate in row["source_rows"] if candidate["chunk_id"] != chunk_id
    ]


def _scores_for_outcomes(dataset, outcomes: list[str]) -> np.ndarray:
    assert len(outcomes) == len(dataset.blocks)
    scores = np.zeros(len(dataset.y), dtype=float)
    for index, outcome in enumerate(outcomes):
        if outcome != "tie":
            labels = dataset.y[index * 2 : index * 2 + 2]
            scores[index * 2 : index * 2 + 2] = labels if outcome == "correct" else 1 - labels
    return scores


def test_features_use_full_pool_before_selecting_only_the_supervised_rows() -> None:
    pair = _pair("pool")
    dataset = _prepare(pair)
    assert dataset.x.shape == (4, 38)
    assert dataset.x.dtype == np.float32
    assert dataset.y.tolist() == [1, 0, 0, 1]
    assert list(dataset.groups) == [2, 2]

    block = dataset.blocks[0]
    assert set(block.chunk_ids) == {"pool-left", "pool-right", "pool-background"}
    assert block.features.shape == (3, 38)
    assert set(block.method_view) == {"query", "routes", "candidate_contents"}
    full_ids, full_features = build_online_features(**block.method_view)
    np.testing.assert_array_equal(block.features, full_features)
    np.testing.assert_array_equal(
        dataset.x[:2], full_features[[full_ids.index("pool-left"), full_ids.index("pool-right")]]
    )
    assert block.selected_indices == [full_ids.index("pool-left"), full_ids.index("pool-right")]

    reduced = deepcopy(pair)
    for row in reduced[2]:
        _drop_candidate(row, "pool-background")
    reduced_dataset = _prepare(reduced)
    dense_norm = FEATURE_NAMES.index("dense_norm")
    assert dataset.x[1, dense_norm] == pytest.approx(2 / 3)
    assert reduced_dataset.x[1, dense_norm] == 0
    same_doc_count = FEATURE_NAMES.index("same_doc_candidate_count")
    assert dataset.x[:, same_doc_count].tolist() == [0, 0, 0, 0]


def test_query_ranking_groups_remain_separate_and_source_weights_balance_total_contribution() -> (
    None
):
    dataset = _prepare(
        _pair("large-1", source_group_id="large"),
        _pair("large-2", source_group_id="large"),
        _pair("small", source_group_id="small"),
    )
    assert list(dataset.groups) == [2] * 6
    assert len({block.query_id for block in dataset.blocks}) == 6
    by_source: dict[str, float] = {}
    for index, block in enumerate(dataset.blocks):
        weights = dataset.weights[index * 2 : index * 2 + 2]
        source = block.supervision["source_group_id"]
        np.testing.assert_array_equal(weights, [0.75, 0.75] if source == "large" else [1.5, 1.5])
        by_source[source] = by_source.get(source, 0.0) + float(weights.sum())
    assert by_source["large"] == by_source["small"]
    assert dataset.weights.mean() == 1.0


def test_missing_direction_does_not_remove_the_other_valid_training_query() -> None:
    pair = _pair("one-direction")
    pair[2].pop()
    dataset = _prepare(pair)
    assert len(dataset.queries) == 2
    assert list(dataset.groups) == [2]
    assert dataset.blocks[0].query_id == "one-direction-q1"
    missing = next(query for query in dataset.queries if query.query_id.endswith("q2"))
    assert missing.exclusion_reasons
    assert not missing.selected_indices


def test_development_coverage_keeps_planned_queries_and_preference_denominator_is_fixed() -> None:
    complete = _pair("complete", role="development")
    unavailable = _pair("unavailable", role="development")
    unavailable[2].pop()
    _drop_candidate(unavailable[2][0], "unavailable-right")
    dataset = _prepare(complete, unavailable, role="development")
    assert len(dataset.queries) == 4
    assert len(dataset.blocks) == 2
    assert sum(bool(query.exclusion_reasons) for query in dataset.queries) == 2
    assert dataset.summary["planned_query_count"] == 4
    metrics = development_metrics(dataset, dataset.y.astype(float))
    assert metrics["query_count"] == 2
    assert metrics["correct"] == 2
    assert metrics["source_macro_query_accuracy"] == 1.0
    assert metrics["pair_count"] == 1
    assert metrics["pair_correct"] == 1
    with pytest.raises(ValueError):
        development_metrics(dataset, np.array([1.0, 0.0]))


@pytest.mark.parametrize("flag_first_direction", [False, True])
def test_contradictory_query_pair_excludes_both_training_directions_but_not_its_source(
    flag_first_direction: bool,
) -> None:
    conflict = _pair("conflict", source_group_id="shared-source", same_query=True)
    conflict[1][0]["structural_conflict"] = flag_first_direction
    ordinary = _pair("ordinary", source_group_id="shared-source")
    dataset = _prepare(conflict, ordinary)
    assert {block.query_id for block in dataset.blocks} == {"ordinary-q1", "ordinary-q2"}
    assert len(dataset.queries) == 4
    excluded = [query for query in dataset.queries if query.query_id.startswith("conflict-")]
    assert all(query.exclusion_reasons for query in excluded)


def test_development_retains_official_conflict_directions_and_semantic_uncertainty() -> None:
    conflict = _pair("conflict", role="development", same_query=True)
    for row in conflict[1]:
        row["structural_conflict"] = True
        row["semantic_uncertain"] = True
    dataset = _prepare(conflict, role="development")
    assert len(dataset.blocks) == 2
    # Identical query/features receive consistent raw scores, opposite official preferences.
    metrics = development_metrics(dataset, np.array([1.0, 0.0, 1.0, 0.0]))
    assert metrics["correct"] == 1
    assert metrics["wrong"] == 1
    assert metrics["source_macro_query_accuracy"] == 0.5
    assert metrics["pair_count"] == 1
    assert metrics["pair_correct"] == 0


def test_semantic_uncertainty_alone_does_not_remove_official_training_preferences() -> None:
    pair = _pair("uncertain")
    for row in pair[1]:
        row["semantic_uncertain"] = True
        row["issue_reasons"] = ["semantic_review_uncertain"]
    dataset = _prepare(pair)
    assert len(dataset.blocks) == 2
    assert dataset.y.tolist() == [1, 0, 0, 1]


def test_source_macro_metrics_differ_from_query_micro_and_exact_ties_are_not_correct() -> None:
    dataset = _prepare(
        _pair("large-1", role="development", source_group_id="large"),
        _pair("large-2", role="development", source_group_id="large"),
        _pair("small", role="development", source_group_id="small"),
        role="development",
    )
    metrics = development_metrics(
        dataset,
        _scores_for_outcomes(dataset, ["tie", "wrong", "wrong", "wrong", "correct", "correct"]),
    )
    assert metrics["query_count"] == 6
    assert metrics["correct"] == 2
    assert metrics["wrong"] == 3
    assert metrics["tie"] == 1
    assert metrics["source_macro_query_accuracy"] == 0.5
    assert metrics["correct"] / metrics["query_count"] == pytest.approx(1 / 3)
    assert metrics["pair_count"] == 3
    assert metrics["pair_correct"] == 1
    assert metrics["source_macro_pair_accuracy"] == 0.5


def test_pair_metric_is_unavailable_when_no_official_pair_has_both_scored_directions() -> None:
    pair = _pair("single", role="development")
    pair[2].pop()
    dataset = _prepare(pair, role="development")
    metrics = development_metrics(dataset, np.array([1.0, 0.0]))
    assert metrics["query_count"] == 1
    assert metrics["pair_count"] == 0
    assert metrics["source_macro_pair_accuracy"] is None


def test_custom_metric_checks_label_and_group_order_without_adding_ndcg() -> None:
    dataset = _prepare(_pair("metric", role="development"), role="development")
    metric = make_development_metric(dataset)
    scores = dataset.y.astype(float)
    assert metric(dataset.y, scores, None, np.array(dataset.groups)) == (
        "source_macro_query_accuracy",
        1.0,
        True,
    )
    with pytest.raises(ValueError):
        metric(1 - dataset.y, scores, None, np.array(dataset.groups))
    with pytest.raises(ValueError):
        metric(dataset.y, scores, None, np.array([4]))


@pytest.mark.parametrize("invalid_score", [np.nan, np.inf, -np.inf])
def test_nonfinite_predictions_fail_instead_of_dropping_queries(invalid_score: float) -> None:
    dataset = _prepare(_pair("finite", role="development"), role="development")
    scores = np.array([1.0, 0.0, invalid_score, 0.0])
    with pytest.raises(ValueError):
        development_metrics(dataset, scores)
    with pytest.raises(ValueError):
        make_development_metric(dataset)(dataset.y, scores, None, np.array(dataset.groups))


def test_source_groups_and_query_ids_cannot_cross_train_development_roles() -> None:
    train = _prepare(_pair("train", source_group_id="train-source"))
    dev = _prepare(_pair("dev", role="development"), role="development")
    assert_disjoint_roles(train, dev)
    same_source = _prepare(
        _pair("other", role="development", source_group_id="train-source"), role="development"
    )
    with pytest.raises(ValueError):
        assert_disjoint_roles(train, same_source)
    shared_id = _pair("dev", role="development")
    for row in (shared_id[0][0], shared_id[1][0], shared_id[2][0]):
        row["source_query_id"] = "train-q1"
    shared_id[2][0]["sample_id"] = "train-q1"
    with pytest.raises(ValueError):
        assert_disjoint_roles(train, _prepare(shared_id, role="development"))
    with pytest.raises(ValueError):
        assert_disjoint_roles(dev, train)


def _reports() -> list[dict]:
    return [
        {
            "config_id": f"c{index}",
            "status": "complete",
            "dev_metrics": {
                "source_macro_query_accuracy": 0.5,
                "source_macro_pair_accuracy": 0.25,
                "query_count": 8,
                "correct": 4,
                "wrong": 4,
                "tie": 0,
                "pair_count": 4,
                "pair_correct": 1,
            },
            "actual_trees": 20,
            "num_leaves": 7,
            "reg_lambda": 1.0,
        }
        for index in range(1, 7)
    ]


@pytest.mark.parametrize(
    ("field", "value", "metric"),
    [
        ("source_macro_query_accuracy", 0.75, True),
        ("source_macro_pair_accuracy", 0.5, True),
        ("actual_trees", 10, False),
        ("num_leaves", 3, False),
        ("reg_lambda", 10.0, False),
    ],
)
def test_selection_uses_each_prespecified_tiebreak(field: str, value: float, metric: bool) -> None:
    reports = _reports()
    target = reports[-1]["dev_metrics"] if metric else reports[-1]
    target[field] = value
    assert select_best_candidate(reports)["config_id"] == "c6"


def test_selection_respects_metric_priority_then_stable_config_id() -> None:
    reports = _reports()
    reports[0]["dev_metrics"]["source_macro_query_accuracy"] = 0.6
    reports[-1]["dev_metrics"]["source_macro_pair_accuracy"] = 1.0
    reports[-1]["actual_trees"] = 1
    assert select_best_candidate(reports)["config_id"] == "c1"
    reports = _reports()
    reports[0]["dev_metrics"]["source_macro_pair_accuracy"] = 0.5
    reports[-1]["actual_trees"] = 1
    assert select_best_candidate(reports)["config_id"] == "c1"
    assert select_best_candidate(list(reversed(_reports())))["config_id"] == "c1"
    reports = _reports()
    for report in reports:
        report["dev_metrics"]["source_macro_pair_accuracy"] = None
        report["dev_metrics"]["pair_count"] = 0
    reports[-1]["actual_trees"] = 1
    assert select_best_candidate(reports)["config_id"] == "c6"


def test_incomplete_grid_cannot_be_silently_selected() -> None:
    reports = _reports()
    reports[-1]["status"] = "failed"
    with pytest.raises(ValueError):
        select_best_candidate(reports)


def _signal_pair(pair_id: str, *, role: str):
    pair = _pair(pair_id, role=role)
    q2_hits = pair[2][1]["routes"]["dense"]
    q2_hits[:2] = q2_hits[1::-1]
    for rank, (hit, score) in enumerate(zip(q2_hits, (0.6, 0.4, 0.0), strict=True)):
        hit.update(rank=rank, score=score)
    return pair


def test_lightgbm_selects_earliest_best_iteration_and_returns_that_exact_tree_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lgb = pytest.importorskip("lightgbm")
    train = _prepare(*[_signal_pair(f"train-{i}", role="train") for i in range(20)])
    dev = _prepare(
        *[_signal_pair(f"dev-{i}", role="development") for i in range(4)], role="development"
    )
    assert_disjoint_roles(train, dev)
    params = training_parameters(GRID[0])
    assert params["n_estimators"] == 300
    assert params["metric"] == "None"
    assert {
        params[name]
        for name in ("random_state", "feature_fraction_seed", "bagging_seed", "data_random_seed")
    } == {20260907}
    original_ranker = lgb.LGBMRanker
    rankers = []

    def record_ranker(**kwargs):
        ranker = original_ranker(**kwargs)
        rankers.append(ranker)
        return ranker

    monkeypatch.setattr(lgb, "LGBMRanker", record_ranker)
    history = []
    prefix, report = _fit_candidate(
        train.x,
        train.y,
        train.groups,
        train.weights,
        dev.x,
        _layout(dev),
        params,
        progress=history.append,
    )
    assert len(rankers) == 1
    assert 40 < len(history) <= 300
    assert all(
        set(row) == {"iteration", "source_macro_query_accuracy", "elapsed_seconds"}
        for row in history
    )
    best_value = max(row["source_macro_query_accuracy"] for row in history)
    first_best = next(
        row["iteration"] for row in history if row["source_macro_query_accuracy"] == best_value
    )
    assert report["best_iteration"] == first_best
    assert report["dev_metrics"]["source_macro_query_accuracy"] == best_value == 1.0
    saved = lgb.Booster(model_str=prefix)
    assert saved.feature_name() == FEATURE_NAMES
    assert saved.num_trees() == report["actual_trees"] == first_best
    scores = saved.predict(dev.x, num_threads=1)
    np.testing.assert_allclose(
        scores,
        rankers[0].booster_.predict(dev.x, num_iteration=first_best, num_threads=1),
        rtol=0,
        atol=0,
    )
    assert development_metrics(dev, scores) == report["dev_metrics"]
    full_pool_scores = saved.predict(dev.blocks[0].features, num_threads=1)
    np.testing.assert_array_equal(full_pool_scores[dev.blocks[0].selected_indices], scores[:2])


@pytest.mark.parametrize("use_total_deadline", [False, True])
def test_hard_fit_timeout_terminates_the_worker_without_leaving_a_child_process(
    use_total_deadline: bool,
) -> None:
    train = _prepare(_signal_pair("train-timeout", role="train"))
    dev = _prepare(_signal_pair("dev-timeout", role="development"), role="development")
    args = (
        train.x,
        train.y,
        train.groups,
        train.weights,
        dev.x,
        _layout(dev),
        training_parameters(GRID[0]),
    )
    previous_children = {child.pid for child in multiprocessing.active_children()}
    history = []
    with pytest.raises(TimeoutError):
        _bounded_fit(
            args,
            timeout_seconds=10.0 if use_total_deadline else 0.001,
            total_deadline=time.monotonic() + 0.001 if use_total_deadline else None,
            progress=history.append,
        )
    assert {child.pid for child in multiprocessing.active_children()} <= previous_children


@pytest.fixture(scope="module")
def spawned_synthetic_fit():
    """One actual c1 fit is reused by orchestration tests; it is not six grid fits."""
    pytest.importorskip("lightgbm")
    train = _prepare(*[_signal_pair(f"train-{i}", role="train") for i in range(20)])
    missing = _pair("dev-not-executed", role="development")
    missing[2].clear()
    dev = _prepare(
        *[_signal_pair(f"dev-{i}", role="development") for i in range(4)],
        missing,
        role="development",
    )
    history = []
    previous_children = {child.pid for child in multiprocessing.active_children()}
    prefix, report = _bounded_fit(
        (
            train.x,
            train.y,
            train.groups,
            train.weights,
            dev.x,
            _layout(dev),
            training_parameters(GRID[0]),
        ),
        timeout_seconds=10.0,
        total_deadline=time.monotonic() + 10.0,
        progress=history.append,
    )
    assert {child.pid for child in multiprocessing.active_children()} <= previous_children
    return train, dev, prefix, report, history


@pytest.fixture
def frozen_policy_source() -> Path:
    pytest.importorskip("lightgbm")
    root = Path(__file__).resolve().parents[2]
    path = root / "models" / "chinese-baseline"
    if not path.is_dir():
        pytest.skip("the locally frozen final33 model bundle is unavailable")
    return path


def test_spawned_worker_returns_early_stopped_model_and_iteration_records(spawned_synthetic_fit):
    import lightgbm as lgb

    _train, dev, prefix, report, history = spawned_synthetic_fit
    assert len(history) > report["best_iteration"]
    assert [row["iteration"] for row in history] == list(range(1, len(history) + 1))
    saved = lgb.Booster(model_str=prefix)
    assert saved.feature_name() == FEATURE_NAMES
    assert saved.num_trees() == report["actual_trees"] == report["best_iteration"]
    assert development_metrics(dev, saved.predict(dev.x, num_threads=1)) == report["dev_metrics"]


def test_selection_orchestration_exports_once_and_keeps_missing_development_queries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    spawned_synthetic_fit,
    frozen_policy_source: Path,
) -> None:
    """Only routing/recording/export are under test; all six replies reuse one c1 fit."""
    import lightgbm as lgb

    from linkrag_eval.retrieval.learning_to_rank.online import LambdaMartOnlineRanker

    train, dev, prefix, actual_report, actual_history = spawned_synthetic_fit
    calls = []

    def reuse_one_fitted_model(args, *, timeout_seconds, progress, total_deadline):
        calls.append(deepcopy(args[-1]))
        assert 0 < timeout_seconds <= 600
        assert total_deadline > time.monotonic()
        for row in actual_history:
            progress(deepcopy(row))
        return prefix, deepcopy(actual_report)

    monkeypatch.setattr(pairwise_training, "_bounded_fit", reuse_one_fitted_model)
    forbidden_refit = Mock(side_effect=AssertionError("export must not fit another model"))
    monkeypatch.setattr(lgb.LGBMRanker, "fit", forbidden_refit)
    out_dir = tmp_path / "synthetic-selection"
    input_paths = {"fixture": "in-memory synthetic preferences; one c1 fit reused six times"}
    result = train_and_select(
        train,
        dev,
        out_dir=out_dir,
        policy_source=frozen_policy_source,
        input_paths=input_paths,
        model_version="synthetic-pairwise-b",
    )
    assert calls == [training_parameters(config) for config in GRID]
    forbidden_refit.assert_not_called()
    assert result["status"] == "complete"
    assert result["refit"] is False
    assert result["selected_config_id"] == "c2"
    assert result["input_paths"] == input_paths
    assert json.loads((out_dir / "selection.json").read_text()) == json.loads(json.dumps(result))
    for row, config in zip(result["grid"], GRID, strict=True):
        assert row["config_id"] == config["config_id"]
        assert row["status"] == "complete"
        assert row["params"] == training_parameters(config)
        assert row["history"] == actual_history
        # Preserve the real worker's c1 parameters rather than inventing six actual fits.
        assert row["booster_params"] == actual_report["booster_params"]
    baseline = LambdaMartOnlineRanker(frozen_policy_source)
    exported = LambdaMartOnlineRanker(out_dir / "model-b")
    assert (
        exported.manifest.n_estimators
        == exported.model.num_trees()
        == actual_report["actual_trees"]
    )
    assert exported.manifest.n_estimators == result["actual_trees"]
    assert exported.manifest.training_params == training_parameters(GRID[1])
    assert asdict(exported.short_fallback) == asdict(baseline.short_fallback)
    for key in ("latency_budget_ms", "timeout_ms", "fallback_policy", "alias_enabled"):
        assert getattr(exported.manifest, key) == getattr(baseline.manifest, key)
    rows = [
        json.loads(line) for line in (out_dir / "dev-predictions.jsonl").read_text().splitlines()
    ]
    assert [row["source_query_id"] for row in rows] == [query.query_id for query in dev.queries]
    missing = [row for row in rows if row["source_query_id"].startswith("dev-not-executed-")]
    assert len(missing) == 2
    assert all(
        row["preference_relation"] == "unavailable"
        and row["scores"] is None
        and row["order"] is None
        and row["exclusion_reasons"]
        for row in missing
    )
    assert not (out_dir / "active.json").exists()


def test_corrupted_frozen_policy_is_rejected_before_first_fit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    frozen_policy_source: Path,
) -> None:
    copied = tmp_path / "corrupt-a"
    shutil.copytree(frozen_policy_source, copied)
    short = copied / "short_fallback.json"
    short.write_bytes(short.read_bytes() + b" ")
    forbidden_fit = Mock(side_effect=AssertionError("invalid A must fail before fit"))
    monkeypatch.setattr(pairwise_training, "_bounded_fit", forbidden_fit)
    train = _prepare(_signal_pair("train-corrupt", role="train"))
    dev = _prepare(_signal_pair("dev-corrupt", role="development"), role="development")
    out_dir = tmp_path / "rejected-selection"
    with pytest.raises(ValueError, match="short fallback checksum mismatch"):
        train_and_select(
            train,
            dev,
            out_dir=out_dir,
            policy_source=copied,
            input_paths={},
            model_version="must-not-exist",
        )
    forbidden_fit.assert_not_called()
    assert not out_dir.exists()


def test_second_fit_timeout_records_remaining_grid_and_prevents_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    spawned_synthetic_fit,
    frozen_policy_source: Path,
) -> None:
    train, dev, prefix, actual_report, actual_history = spawned_synthetic_fit
    calls = []

    def timeout_on_second_fit(args, *, timeout_seconds, progress, total_deadline):
        calls.append(args[-1])
        if len(calls) == 2:
            progress(deepcopy(actual_history[0]))
            raise TimeoutError("synthetic second-fit timeout")
        for row in actual_history:
            progress(deepcopy(row))
        return prefix, deepcopy(actual_report)

    monkeypatch.setattr(pairwise_training, "_bounded_fit", timeout_on_second_fit)
    out_dir = tmp_path / "timed-out-selection"
    with pytest.raises(TimeoutError):
        train_and_select(
            train,
            dev,
            out_dir=out_dir,
            policy_source=frozen_policy_source,
            input_paths={"fixture": "synthetic timeout"},
            model_version="not-exported",
        )
    assert len(calls) == 2
    selection = json.loads((out_dir / "selection.json").read_text())
    assert selection["status"] == "timeout"
    assert selection["selected_config_id"] is None
    assert [row["status"] for row in selection["grid"]] == [
        "complete",
        "timeout",
        "not_started",
        "not_started",
        "not_started",
        "not_started",
    ]
    assert selection["grid"][1]["history"] == actual_history[:1]
    assert not (out_dir / "model-b").exists()
    assert not (out_dir / "dev-predictions.jsonl").exists()


def test_finished_worker_pipe_is_drained_after_a_poll_without_ready_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The worker exits between the first poll and is_alive; its reply still matters."""
    reply = ("serialized-model", {"actual_trees": 1})
    receiver = SimpleNamespace(
        poll=Mock(side_effect=[False, True]),
        recv=Mock(return_value=("complete", reply)),
        close=Mock(),
    )
    sender = SimpleNamespace(close=Mock())
    process = SimpleNamespace(
        start=Mock(),
        join=Mock(),
        is_alive=Mock(return_value=False),
        close=Mock(),
        terminate=Mock(),
        kill=Mock(),
    )
    context = SimpleNamespace(
        Pipe=Mock(return_value=(receiver, sender)), Process=Mock(return_value=process)
    )
    monkeypatch.setattr(pairwise_training.multiprocessing, "get_context", lambda method: context)
    assert _bounded_fit((), timeout_seconds=10.0, progress=Mock()) == reply
    assert receiver.poll.call_count == 2
    receiver.recv.assert_called_once()
    process.terminate.assert_not_called()
    process.close.assert_called_once()


@pytest.mark.parametrize("invalid_grid", ["missing", "duplicate"])
def test_selection_requires_each_predeclared_configuration_exactly_once(invalid_grid: str) -> None:
    reports = _reports()
    if invalid_grid == "missing":
        reports.pop()
    else:
        reports[-1]["config_id"] = reports[0]["config_id"]
    with pytest.raises(ValueError):
        select_best_candidate(reports)


def test_explicit_configuration_fits_once_and_exports_without_grid_selection(
    tmp_path, monkeypatch, spawned_synthetic_fit, frozen_policy_source,
):
    train, dev, prefix, report, history = spawned_synthetic_fit
    calls = []

    def reuse_fit(args, *, timeout_seconds, progress, total_deadline):
        calls.append(args[-1])
        for row in history:
            progress(deepcopy(row))
        return prefix, deepcopy(report)

    monkeypatch.setattr(pairwise_training, "_bounded_fit", reuse_fit)
    monkeypatch.setattr(pairwise_training, "select_best_candidate", Mock(
        side_effect=AssertionError("fixed configuration must not select across a grid"),
    ))
    result = train_and_select(
        train, dev, out_dir=tmp_path / "fixed", policy_source=frozen_policy_source,
        input_paths={}, model_version="synthetic-fixed", config_id="c3",
    )
    assert calls == [training_parameters(GRID[2])]
    assert result["status"] == "complete" and result["selected_config_id"] == "c3"
    assert result["maximum_fits"] == len(result["grid"]) == 1
    assert result["actual_trees"] == report["actual_trees"]
    assert result["development_prediction_and_order_seconds"] > 0


@pytest.mark.parametrize("case", ["mixed_versions", "english_grid", "unknown_config"])
def test_invalid_version_or_configuration_stops_before_fitting(
    case, tmp_path, monkeypatch, spawned_synthetic_fit,
):
    from linkrag_eval.retrieval.learning_to_rank.features import ENGLISH_FEATURE_VERSION

    train, dev = deepcopy(spawned_synthetic_fit[:2])
    if case != "unknown_config":
        train.feature_version = ENGLISH_FEATURE_VERSION
    if case == "english_grid":
        dev.feature_version = ENGLISH_FEATURE_VERSION
    forbidden = Mock(side_effect=AssertionError("fit must not start"))
    monkeypatch.setattr(pairwise_training, "_bounded_fit", forbidden)
    with pytest.raises(ValueError):
        train_and_select(
            train, dev, out_dir=tmp_path / "invalid", policy_source=tmp_path / "absent",
            input_paths={}, model_version="invalid", config_id="c99" if case == "unknown_config" else None,
        )
    forbidden.assert_not_called()
    assert not (tmp_path / "invalid").exists()
