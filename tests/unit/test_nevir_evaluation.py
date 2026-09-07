"""NevIR 独立评价的有限边界测试：合成候选、fake 模型，零活栈。"""

from __future__ import annotations

import copy
import json
import sys
from dataclasses import asdict, replace
from types import SimpleNamespace

import numpy as np
import pytest

from linkrag_eval.retrieval.learning_to_rank import nevir_evaluation as evaluation
from linkrag_eval.retrieval.learning_to_rank.experiment import FEATURE_NAMES, FEATURE_VERSION
from linkrag_eval.retrieval.learning_to_rank.online import ModelManifest, feature_signature


def _fixture(pair_count=1, *, groups=None):
    """每条查询含两段目标及一段未标注背景；不借正文或 ID 编码标签。"""
    queries, supervision, inputs, mapping = [], [], [], []
    for pair in range(pair_count):
        group = groups[pair] if groups else f"group-{pair}"
        chunks = [f"chunk-{pair}-{index}" for index in range(3)]
        passages = [f"passage-{pair}-{index}" for index in range(3)]
        identities = [
            {
                "source_passage_id": passages[index],
                "dataset_id": 123,
                "doc_id": pair * 3 + index + 1,
                "chunk_id": chunk,
            }
            for index, chunk in enumerate(chunks)
        ]
        mapping.extend(identities)
        for direction in range(2):
            qid = f"pair-{pair}-q{direction + 1}"
            query = f"Synthetic query {pair * 2 + direction}"
            queries.append({"source_query_id": qid, "query": query})
            supervision.append(
                {
                    "source_query_id": qid,
                    "role": "development",
                    "source_group_id": group,
                    "pair_id": f"pair-{pair}",
                    "direction": f"q{direction + 1}",
                    "preferred_chunk_id": chunks[direction],
                    "other_chunk_id": chunks[1 - direction],
                    "preferred_passage_id": passages[direction],
                    "other_passage_id": passages[1 - direction],
                    "official_label_available": True,
                    "structural_conflict": False,
                    "semantic_uncertain": False,
                    "semantic_review_status": "not_reviewed",
                    "label_basis": "official",
                    "issue_reasons": [],
                }
            )
            hits = [
                {
                    "dataset_id": item["dataset_id"],
                    "doc_id": item["doc_id"],
                    "chunk_id": item["chunk_id"],
                    "score": float(10 * (pair * 2 + direction + 1) + index),
                    "rank": index,
                }
                for index, item in enumerate(identities)
            ]
            inputs.append(
                {
                    "source_query_id": qid,
                    "sample_id": qid,
                    "query": query,
                    "dataset_ids": [123],
                    "status": "ready",
                    "ranking_input_ready": True,
                    "routes": {"dense": hits, "sparse": [], "bm25": []},
                    "route_status": {"dense": "ok", "sparse": "empty", "bm25": "empty"},
                    "candidate_rows": [
                        {**item, "content": f"  Candidate content {item['doc_id']}\t  "}
                        for item in identities
                    ],
                    "failed_sources": [],
                    "input_issues": [],
                }
            )
    return queries, supervision, inputs, mapping


def _prepare(fixture):
    return evaluation.prepare_inputs(*fixture, role="development")


class _Predictor:
    def __init__(self, score_table, *, failure=None):
        self.score_table = score_table
        self.failure = failure
        self.calls = []
        self.prediction_threads = []

    def predict(self, features, *, num_threads):
        assert num_threads == 1
        self.prediction_threads.append(num_threads)
        self.calls.append(np.array(features, copy=True))
        scores = np.array([self.score_table[value] for value in features[:, 0]])
        if self.failure == "nan":
            return np.full(len(scores), np.nan)
        if self.failure == "shape":
            return scores[:, None]
        if self.failure == "exception":
            raise RuntimeError("synthetic prediction failure")
        if self.failure == "replay" and len(self.calls) % 2 == 0:
            return scores + 1.0
        return scores


class _Ranker:
    def __init__(self, fixture, relations, *, online_relations=None, failure=None, log=None, name=""):
        _, supervision, inputs, _ = fixture
        self.calls = []
        self.log = log
        self.name = name
        self.online_error = False
        self.online_mode = "ltr"
        self.orders = {}
        score_table = {}
        for label, row, relation in zip(supervision, inputs, relations, strict=True):
            preferred, other = label["preferred_chunk_id"], label["other_chunk_id"]
            scores = {
                "correct": {preferred: 1.0, other: 0.0},
                "wrong": {preferred: 0.0, other: 1.0},
                "tie": {preferred: 1.0, other: 1.0},
                "tiny_correct": {preferred: np.nextafter(1.0, 2.0), other: 1.0},
                "unavailable": {preferred: np.nan, other: 0.0},
            }[relation]
            for hit in row["routes"]["dense"]:
                score_table[hit["score"]] = scores.get(hit["chunk_id"], -1.0)
            online_relation = (
                online_relations[len(self.orders)] if online_relations else "correct"
            )
            first = [preferred, other] if online_relation == "correct" else [other, preferred]
            self.orders[row["query"]] = first + [
                hit["chunk_id"] for hit in row["routes"]["dense"]
                if hit["chunk_id"] not in first
            ]
        self.model = _Predictor(score_table, failure=failure)

    async def rank(self, row, contents):
        self.calls.append((copy.deepcopy(row), dict(contents)))
        if self.log is not None:
            self.log.append((row["query"], self.name))
        if self.online_error:
            raise RuntimeError("synthetic online failure")
        return SimpleNamespace(
            ranked_chunk_ids=self.orders[row["query"]],
            mode=self.online_mode,
            elapsed_ms=0.5,
            model_version=self.name or "fake",
            reason=None,
        )


async def _evaluate(fixture, a_relations, b_relations, **kwargs):
    a = _Ranker(fixture, a_relations)
    b = _Ranker(fixture, b_relations)
    results = await evaluation.evaluate_ab(
        _prepare(fixture), rankers={"A": a, "B": b}, warmup=False, **kwargs
    )
    return results, a, b


def test_prepare_distinguishes_missing_failed_empty_and_unrecalled_queries():
    fixture = _fixture(3)
    queries, supervision, inputs, mapping = fixture
    del inputs[0]
    inputs[0].update(status="incomplete", ranking_input_ready=False, failed_sources=["sparse"])
    inputs[0]["route_status"]["sparse"] = "failed"
    inputs[1].update(status="empty", candidate_rows=[])
    inputs[1]["routes"]["dense"] = []
    inputs[1]["route_status"]["dense"] = "empty"
    preferred = supervision[3]["preferred_chunk_id"]
    inputs[2]["routes"]["dense"] = [
        {**hit, "rank": 0} for hit in inputs[2]["routes"]["dense"]
        if hit["chunk_id"] == preferred
    ]
    inputs[2]["candidate_rows"] = [
        row for row in inputs[2]["candidate_rows"] if row["chunk_id"] == preferred
    ]

    prepared = evaluation.prepare_inputs(queries, supervision, inputs, mapping, role="development")

    assert len(prepared) == 6
    assert [row["coverage_state"] for row in prepared] == [
        "unknown", "unknown", "missing_target", "missing_target", "both", "both"
    ]
    assert [row["source_query_id"] for row in prepared] == [q["source_query_id"] for q in queries]


@pytest.mark.asyncio
async def test_missing_background_row_or_content_keeps_common_denominator():
    fixture = _fixture()
    fixture[2][0]["candidate_rows"].pop()
    fixture[2][1]["candidate_rows"][-1]["content"] = None
    prepared = _prepare(fixture)
    assert [row["coverage_state"] for row in prepared] == ["both", "both"]
    assert not any(row["rank_input_complete"] for row in prepared)

    results, a, b = await _evaluate(fixture, ["correct"] * 2, ["correct"] * 2)
    summary, _ = evaluation.summarize(results, bootstrap_repeats=10)
    metrics = summary["official"]["raw"]["single_query"]
    assert metrics["denominator"] == 2
    assert metrics["A"]["value"] is None
    assert metrics["A"]["bounds"] == [0.0, 1.0]
    assert metrics["A"]["unknown"] == 2
    assert not a.calls and not b.calls and not a.model.calls and not b.model.calls


@pytest.mark.asyncio
async def test_complete_background_and_same_label_free_input_reach_both_models():
    fixture = _fixture()
    for row in fixture[2]:
        row["pair_id"] = "evaluation-only"
        row["preferred_chunk_id"] = "evaluation-only"
        for hit in row["routes"]["dense"]:
            hit["official_label_available"] = True
    log = []
    a = _Ranker(fixture, ["correct"] * 2, log=log, name="A")
    b = _Ranker(fixture, ["correct"] * 2, log=log, name="B")
    results = await evaluation.evaluate_ab(_prepare(fixture), rankers={"A": a, "B": b}, warmup=False)

    assert [name for _, name in log] == ["A", "B", "B", "A"]
    assert a.calls == b.calls
    for row, contents in a.calls:
        assert set(row) == {"query", "routes"}
        assert len(contents) == 3
        assert all(text.startswith("  ") and text.endswith("\t  ") for text in contents.values())
        assert all(
            set(hit) == {"dataset_id", "doc_id", "chunk_id", "score", "rank"}
            for hit in row["routes"]["dense"]
        )
    assert len(FEATURE_NAMES) == 38
    assert all(matrix.shape == (3, 38) for matrix in a.model.calls + b.model.calls)
    assert a.model.prediction_threads == b.model.prediction_threads == [1, 1, 1, 1]
    summary, _ = evaluation.summarize(results, bootstrap_repeats=10)
    for mode in ("raw", "online"):
        assert summary["official"][mode]["single_query"]["delta"]["value"] == 0.0
        assert summary["official"][mode]["paired"]["delta"]["value"] == 0.0


@pytest.mark.asyncio
async def test_strict_query_transitions_and_difference_have_fixed_common_denominator():
    fixture = _fixture(4)
    a_relations = ["wrong", "tie", "correct", "correct", "correct", "wrong", "tie", "wrong"]
    b_relations = ["correct", "correct", "wrong", "correct", "correct", "tie", "wrong", "wrong"]
    results, _, _ = await _evaluate(fixture, a_relations, b_relations)
    summary, _ = evaluation.summarize(results, bootstrap_repeats=100)
    metrics = summary["official"]["raw"]["single_query"]
    transitions = metrics["transitions"]

    assert metrics["denominator"] == 8
    assert metrics["A"]["numerator"] == 3
    assert metrics["B"]["numerator"] == 4
    assert metrics["delta"]["value"] == 1 / 8
    assert [transitions[key] for key in (
        "corrected", "regressed", "both_correct", "both_not_correct", "unavailable"
    )] == [2, 1, 2, 3, 0]
    assert sum(transitions[key] for key in (
        "corrected", "regressed", "both_correct", "both_not_correct", "unavailable"
    )) == 8
    assert transitions["matrix"]["tie"]["correct"] == 1
    assert transitions["matrix"]["wrong"]["tie"] == 1
    assert transitions["matrix"]["tie"]["wrong"] == 1
    assert metrics["delta"]["value"] == (
        transitions["corrected"] - transitions["regressed"]
    ) / metrics["denominator"]


@pytest.mark.asyncio
async def test_raw_exact_tie_and_tiny_difference_are_separate_from_online_fallback():
    fixture = _fixture()
    a = _Ranker(fixture, ["tiny_correct", "tie"])
    b = _Ranker(fixture, ["wrong", "wrong"])
    b.online_mode = "fallback_timeout"
    results = await evaluation.evaluate_ab(_prepare(fixture), rankers={"A": a, "B": b}, warmup=False)

    assert [row["models"]["A"]["raw"]["relation"] for row in results] == ["correct", "tie"]
    assert [row["models"]["B"]["raw"]["relation"] for row in results] == ["wrong", "wrong"]
    assert [row["models"]["B"]["online"]["relation"] for row in results] == ["correct", "correct"]
    assert all(row["models"]["B"]["online"]["mode"] == "fallback_timeout" for row in results)
    assert all(row["models"]["A"]["raw"]["replay_equal"] for row in results)
    summary, _ = evaluation.summarize(results, bootstrap_repeats=10)
    assert summary["official"]["raw"]["single_query"]["A"]["value"] == 0.5
    assert summary["official"]["online"]["single_query"]["A"]["value"] == 1.0


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["nan", "shape", "exception", "replay", "load"])
async def test_one_sided_model_failure_keeps_denominator_and_unknown_bounds(failure):
    fixture = _fixture()
    a = _Ranker(fixture, ["correct"] * 2)
    b = _Ranker(fixture, ["correct"] * 2, failure=failure)
    rankers = {"A": a, "B": b}
    load_errors = None
    if failure == "load":
        rankers["B"] = None
        load_errors = {"B": "synthetic model load failure"}
    results = await evaluation.evaluate_ab(
        _prepare(fixture), rankers=rankers, load_errors=load_errors, warmup=False
    )
    summary, _ = evaluation.summarize(results, bootstrap_repeats=10)
    metrics = summary["official"]["raw"]["single_query"]

    assert metrics["denominator"] == 2
    assert metrics["A"]["value"] == 1.0
    assert metrics["B"]["value"] is None
    assert metrics["B"]["unknown"] == 2
    assert metrics["B"]["bounds"] == [0.0, 1.0]
    assert metrics["delta"]["value"] is None
    assert metrics["delta"]["bounds"] == [-1.0, 0.0]
    assert metrics["delta"]["interval"] is None
    assert metrics["transitions"]["unavailable"] == 2
    assert all(row["models"]["B"]["raw"]["relation"] == "unavailable" for row in results)
    if failure != "load":
        assert all(row["models"]["B"]["online"]["relation"] == "correct" for row in results)


@pytest.mark.asyncio
async def test_pair_wrong_and_unavailable_is_known_zero_but_correct_and_unavailable_is_unknown():
    fixture = _fixture(2)
    results, _, _ = await _evaluate(
        fixture, ["correct", "unavailable", "wrong", "unavailable"], ["correct"] * 4
    )
    summary, pairs = evaluation.summarize(results, bootstrap_repeats=10)
    metrics = summary["official"]["raw"]["paired"]
    by_id = {row["pair_id"]: row for row in pairs}

    assert metrics["denominator"] == 2
    assert metrics["A"]["numerator"] == 0
    assert metrics["A"]["unknown"] == 1
    assert metrics["A"]["value"] is None
    assert metrics["A"]["bounds"] == [0.0, 0.5]
    assert metrics["B"]["value"] == 1.0
    assert metrics["delta"]["bounds"] == [0.5, 1.0]
    assert by_id["pair-0"]["models"]["A"]["raw"]["bounds"] == [0, 1]
    assert by_id["pair-1"]["models"]["A"]["raw"]["bounds"] == [0, 0]
    assert all(row["models"]["A"]["raw"]["contains_unavailable"] for row in pairs)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["exception", "missing_candidate", "duplicate_candidate"])
async def test_invalid_online_result_does_not_erase_successful_raw_prediction(failure):
    fixture = _fixture()
    a = _Ranker(fixture, ["correct"] * 2)
    b = _Ranker(fixture, ["correct"] * 2)
    if failure == "exception":
        b.online_error = True
    else:
        for order in b.orders.values():
            if failure == "missing_candidate":
                order.pop()
            else:
                order[-1] = order[0]
    results = await evaluation.evaluate_ab(_prepare(fixture), rankers={"A": a, "B": b}, warmup=False)
    summary, _ = evaluation.summarize(results, bootstrap_repeats=10)

    assert summary["official"]["raw"]["single_query"]["delta"]["value"] == 0.0
    online = summary["official"]["online"]["single_query"]
    assert online["denominator"] == 2
    assert online["B"]["unknown"] == 2
    assert online["delta"]["bounds"] == [-1.0, 0.0]


@pytest.mark.parametrize("mutation", [
    "duplicate_query", "duplicate_input", "query_changed", "duplicate_direction",
    "group_disagrees", "supervision_identity", "unknown_supervision",
])
def test_duplicate_and_inconsistent_input_contracts_are_rejected(mutation):
    fixture = _fixture()
    queries, supervision, inputs, _ = fixture
    if mutation == "duplicate_query":
        queries.append(copy.deepcopy(queries[0]))
    elif mutation == "duplicate_input":
        inputs.append(copy.deepcopy(inputs[0]))
    elif mutation == "query_changed":
        inputs[0]["query"] = "A different query"
    elif mutation == "duplicate_direction":
        supervision[1]["direction"] = "q1"
    elif mutation == "group_disagrees":
        supervision[1]["source_group_id"] = "another-group"
    elif mutation == "supervision_identity":
        supervision[0]["preferred_passage_id"] = supervision[0]["other_passage_id"]
    else:
        supervision[0]["source_query_id"] = "unknown-query"

    with pytest.raises(ValueError):
        _prepare(fixture)


@pytest.mark.asyncio
async def test_prespecified_sensitivity_mask_does_not_replace_official_results():
    fixture = _fixture(2)
    fixture[1][0]["semantic_uncertain"] = True
    fixture[1][0]["issue_reasons"] = ["prespecified synthetic semantic ambiguity"]
    results, _, _ = await _evaluate(fixture, ["wrong"] * 4, ["correct", "wrong", "wrong", "wrong"])
    summary, _ = evaluation.summarize(results, bootstrap_repeats=10)

    official = summary["official"]
    assert official["query_count"] == 4
    assert official["pair_count"] == 2
    assert official["raw"]["single_query"]["denominator"] == 4
    assert official["raw"]["single_query"]["delta"]["value"] == 0.25
    assert summary["sensitivity"]["applied"] is True
    assert summary["sensitivity"]["excluded_query_count"] == 1
    assert summary["sensitivity"]["excluded_pair_count"] == 1
    sensitivity = summary["sensitivity"]["results"]
    assert sensitivity["query_count"] == 3
    assert sensitivity["raw"]["single_query"]["denominator"] == 3
    assert sensitivity["raw"]["paired"]["denominator"] == 1
    assert sensitivity["raw"]["single_query"]["delta"]["value"] == 0.0
    assert len(results) == 4


@pytest.mark.asyncio
async def test_unavailable_official_label_is_unknown_and_not_a_failed_or_dropped_query():
    fixture = _fixture()
    fixture[1][0]["official_label_available"] = False
    fixture[1][0]["label_basis"] = "unresolved"
    results, _, _ = await _evaluate(fixture, ["correct"] * 2, ["correct"] * 2)
    summary, _ = evaluation.summarize(results, bootstrap_repeats=10)
    metrics = summary["official"]["raw"]["single_query"]

    assert all(row["coverage_state"] == "both" for row in results)
    assert metrics["denominator"] == 2
    assert metrics["A"]["numerator"] == 1
    assert metrics["A"]["unknown"] == 1
    assert metrics["A"]["bounds"] == [0.5, 1.0]
    assert metrics["A"]["value"] is None
    assert metrics["delta"]["value"] is None
    assert metrics["delta"]["interval"] is None


@pytest.mark.asyncio
async def test_source_group_bootstrap_uses_member_weights_and_handles_one_or_zero_groups(monkeypatch):
    fixture = _fixture(3, groups=["small", "large", "large"])
    # The small group contributes 2 corrections; the large group has 4 unchanged queries.
    results, _, _ = await _evaluate(fixture, ["wrong"] * 6, ["correct"] * 2 + ["wrong"] * 4)
    seeds = []

    class FixedDraws:
        def integers(self, low, high, *, size):
            assert (low, high, size) == (0, 2, (4, 2))
            return np.array([[0, 0], [0, 1], [1, 0], [1, 1]])

    def fixed_rng(seed):
        seeds.append(seed)
        return FixedDraws()

    monkeypatch.setattr(evaluation.np.random, "default_rng", fixed_rng)
    summary, _ = evaluation.summarize(results, bootstrap_repeats=4, bootstrap_seed=20260907)
    for endpoint, denominator in (("single_query", 6), ("paired", 3)):
        metrics = summary["official"]["raw"][endpoint]
        delta = metrics["delta"]
        assert metrics["denominator"] == denominator
        assert delta["value"] == pytest.approx(1 / 3)
        assert delta["groups"] == 2
        # Whole-group resampling yields 0, 1/3, 1/3, 1, whose linear percentiles are hand-known.
        assert delta["interval"] == pytest.approx([0.025, 0.95])
    assert summary["official"]["raw"]["single_query"]["delta"]["group_sizes"] == {
        "large": 4, "small": 2
    }
    assert seeds and set(seeds) == {20260907}

    # A shared source group cannot supply a between-group resampling interval.
    for row in results:
        row["source_group_id"] = "single-source"
    single_group, _ = evaluation.summarize(results, bootstrap_repeats=4)
    delta = single_group["official"]["raw"]["single_query"]["delta"]
    assert delta["value"] == pytest.approx(1 / 3)
    assert delta["interval"] is None
    assert delta["interval_reason"] == "fewer_than_two_source_groups"

    # Fully observed empty pools have zero coverage and no rank accuracy denominator.
    empty_fixture = _fixture()
    for row in empty_fixture[2]:
        row.update(status="empty", candidate_rows=[])
        row["routes"]["dense"] = []
        row["route_status"]["dense"] = "empty"
    empty_results, _, _ = await _evaluate(empty_fixture, ["correct"] * 2, ["correct"] * 2)
    empty, _ = evaluation.summarize(empty_results, bootstrap_repeats=4)
    assert empty["official"]["coverage"]["query"]["counts"] == {
        "both": 0, "missing_target": 2, "unknown": 0
    }
    for endpoint in ("single_query", "paired"):
        metrics = empty["official"]["raw"][endpoint]
        assert metrics["denominator"] == 0
        assert metrics["A"]["value"] is None
        assert metrics["A"]["bounds"] is None
        assert metrics["delta"]["interval"] is None
        assert metrics["delta"]["interval_reason"] == "empty_denominator"


def _synthetic_packages(tmp_path, monkeypatch):
    paths = {name: tmp_path / name for name in ("A", "B")}
    manifests = {
        name: ModelManifest(
            model_version=f"synthetic-{name}",
            feature_version=FEATURE_VERSION,
            feature_signature=feature_signature(),
            feature_names=list(FEATURE_NAMES),
            training_data_sha256="",
            n_estimators=1,
            latency_budget_ms=250,
            timeout_ms=350,
            lightgbm_version="synthetic-test",
        )
        for name in paths
    }
    manifests["A"] = replace(
        manifests["A"], model_version=evaluation.FROZEN_A_VERSION,
        model_file_sha256=evaluation.FROZEN_A_MODEL_SHA256,
    )
    for name, path in paths.items():
        path.mkdir()
        (path / "manifest.json").write_text(json.dumps(asdict(manifests[name])))
        (path / "feature_contract.json").write_text(json.dumps({
            "feature_version": FEATURE_VERSION,
            "feature_signature": feature_signature(),
            "feature_names": FEATURE_NAMES,
            "alias_enabled": False,
            "fallback": {
                "type": "weighted-score-baseline",
                "weights": {"dense": 0.70, "sparse": 0.15, "bm25": 0.15},
                "thresholds": {"dense": 0.30, "sparse": 0.20, "bm25": 0.0},
            },
        }))
    monkeypatch.setattr(evaluation, "_load_manifest", lambda path: manifests[path.name])
    monkeypatch.setattr(evaluation, "_load_short_fallback", lambda path, manifest: None)
    return paths, manifests


@pytest.mark.parametrize("mismatch", ["explicit_error", "feature_order", "baseline", "latency"])
def test_package_contract_errors_propagate_before_any_ranker_is_constructed(
    tmp_path, monkeypatch, mismatch
):
    paths, manifests = _synthetic_packages(tmp_path, monkeypatch)
    constructions = []

    def forbidden_constructor(path, *, prediction_num_threads):
        assert prediction_num_threads == 1
        constructions.append(path)
        raise AssertionError("incompatible packages must be rejected before model loading")

    monkeypatch.setattr(evaluation, "LambdaMartOnlineRanker", forbidden_constructor)
    if mismatch == "explicit_error":
        def load_manifest(path):
            if path.name == "B":
                raise evaluation.EvaluationContractError("synthetic explicit contract failure")
            return manifests[path.name]
        monkeypatch.setattr(evaluation, "_load_manifest", load_manifest)
    elif mismatch == "latency":
        manifests["B"] = replace(manifests["B"], latency_budget_ms=251)
        (paths["B"] / "manifest.json").write_text(json.dumps(asdict(manifests["B"])))
    else:
        path = paths["B"] / "feature_contract.json"
        feature = json.loads(path.read_text())
        if mismatch == "feature_order":
            feature["feature_names"] = list(reversed(FEATURE_NAMES))
        else:
            feature["fallback"]["weights"]["dense"] = 0.5
        path.write_text(json.dumps(feature))

    with pytest.raises(evaluation.EvaluationContractError):
        evaluation.load_rankers(paths["A"], paths["B"])
    assert constructions == []


@pytest.mark.parametrize("schema, accepted", [
    ("named", True),
    ("frozen_a", True),
    ("a_wrong_version", False),
    ("a_wrong_checksum", False),
    ("b_generic", False),
    ("b_claims_frozen_a", False),
    ("wrong_count", False),
    ("wrong_order", False),
])
def test_loaded_booster_schema_only_allows_the_identified_frozen_a_positional_exception(
    tmp_path, monkeypatch, schema, accepted
):
    paths, manifests = _synthetic_packages(tmp_path, monkeypatch)
    names = {name: list(FEATURE_NAMES) for name in paths}
    counts = {"A": 38, "B": 38}
    generic = [f"Column_{index}" for index in range(38)]
    if schema in {"frozen_a", "a_wrong_version", "a_wrong_checksum"}:
        names["A"] = generic
        manifests["A"] = replace(
            manifests["A"],
            model_version=evaluation.FROZEN_A_VERSION,
            model_file_sha256=evaluation.FROZEN_A_MODEL_SHA256,
        )
        if schema == "a_wrong_version":
            manifests["A"] = replace(manifests["A"], model_version="another-baseline")
        if schema == "a_wrong_checksum":
            manifests["A"] = replace(manifests["A"], model_file_sha256="0" * 64)
    elif schema in {"b_generic", "b_claims_frozen_a"}:
        names["B"] = generic
        if schema == "b_claims_frozen_a":
            manifests["B"] = replace(
                manifests["B"],
                model_version=evaluation.FROZEN_A_VERSION,
                model_file_sha256=evaluation.FROZEN_A_MODEL_SHA256,
            )
    elif schema == "wrong_count":
        counts["B"] = 37
    elif schema == "wrong_order":
        names["B"] = list(reversed(FEATURE_NAMES))
    for name, path in paths.items():
        (path / "manifest.json").write_text(json.dumps(asdict(manifests[name])))

    serialized_threads = {"A": 8, "B": 1}
    constructor_threads = {}

    def fake_constructor(path, *, prediction_num_threads):
        name = path.name
        assert prediction_num_threads == 1
        constructor_threads[name] = prediction_num_threads
        return SimpleNamespace(
            manifest=manifests[name], short_fallback=None,
            model=SimpleNamespace(
                feature_name=lambda: names[name], num_feature=lambda: counts[name],
                params={"num_threads": serialized_threads[name]},
            ),
        )

    monkeypatch.setattr(evaluation, "LambdaMartOnlineRanker", fake_constructor)
    if not accepted:
        match = None if schema in {"a_wrong_version", "a_wrong_checksum"} else "Booster feature count/order"
        with pytest.raises(evaluation.EvaluationContractError, match=match):
            evaluation.load_rankers(paths["A"], paths["B"])
    else:
        rankers, errors, contracts = evaluation.load_rankers(paths["A"], paths["B"])
        assert not errors
        assert all(rankers[name] is not None for name in paths)
        assert constructor_threads == {"A": 1, "B": 1}
        assert contracts["A"]["booster_feature_names"] == names["A"]
        assert contracts["B"]["booster_feature_names"] == FEATURE_NAMES
        for name in paths:
            assert rankers[name].model.params == {"num_threads": serialized_threads[name]}
            assert contracts[name]["serialized_num_threads"] == serialized_threads[name]
            assert contracts[name]["explicit_prediction_num_threads"] == 1


@pytest.mark.asyncio
async def test_run_evaluation_persists_unavailable_completion_for_unresolved_official_label(
    tmp_path, monkeypatch
):
    fixture = _fixture()
    fixture[1][0].update(official_label_available=False, label_basis="unresolved")
    experiment = tmp_path / "synthetic-experiment"
    files = {
        "prepared/development/queries.jsonl": fixture[0],
        "prepared/development/supervision.jsonl": fixture[1],
        "prepared/passage-mapping.jsonl": fixture[3],
        "candidates/development/inputs.jsonl": fixture[2],
    }
    for relative, rows in files.items():
        path = experiment / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    (experiment / "run.json").write_text(json.dumps({"origin": "synthetic unit test"}))

    class WarmableRanker(_Ranker):
        async def rank(self, row, contents):
            if row["query"] == "Synthetic warmup for fixed candidate ranking":
                return SimpleNamespace(
                    ranked_chunk_ids=["warmup"], mode="ltr", elapsed_ms=0.1,
                    model_version="fake", reason=None,
                )
            return await super().rank(row, contents)

    rankers = {name: WarmableRanker(fixture, ["correct"] * 2) for name in ("A", "B")}
    monkeypatch.setattr(evaluation, "load_rankers", lambda a, b: (rankers, {}, {}))
    monkeypatch.setattr(evaluation, "_code_metadata", lambda: {"code_revision": "synthetic"})
    monkeypatch.setitem(sys.modules, "lightgbm", SimpleNamespace(__version__="synthetic-test"))
    out = tmp_path / "evaluation-output"

    metadata = await evaluation.run_evaluation(
        experiment_dir=experiment, role="development",
        model_a=tmp_path / "A", model_b=tmp_path / "B", out=out,
    )

    assert metadata["status"] == "completed_with_unavailable"
    assert json.loads((out / "metadata.json").read_text())["status"] == "completed_with_unavailable"
    summary = json.loads((out / "summary.json").read_text())["official"]
    assert summary["query_count"] == 2 and summary["pair_count"] == 1
    assert summary["label_unavailable_count"] == 1
    for kind in ("raw", "online"):
        metrics = summary[kind]["single_query"]
        assert metrics["denominator"] == 2
        assert metrics["A"]["numerator"] == 1
        assert metrics["A"]["unknown"] == 1
        assert metrics["A"]["value"] is None
        assert metrics["delta"]["value"] is None
    results = [json.loads(line) for line in (out / "queries.jsonl").read_text().splitlines()]
    assert len(results) == 2
    assert all(row["warmup_errors"] == {"A": None, "B": None} for row in results)
