"""Behavioral checks for cached selective judging and development-only selection."""
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from linkrag_eval.retrieval.learning_to_rank.judge_cost_curve import (
    RoleInputs,
    curve_points,
    evaluate_point,
    route_disagreement,
    select_margin_threshold,
    trigger_variants,
)
from linkrag_eval.retrieval.learning_to_rank.llm_judge import (
    baseline_order,
    evaluate_rankers,
    resort,
)


def fixture():
    stage1 = {"q1": {"a": 1.1, "b": 1., "c": 0.},
              "q2": {"a": 2., "b": 1., "c": 0.}}
    labels = [{"source_query_id": q, "pair_id": "pair", "source_group_id": "group",
               "direction": q, "preferred_chunk_id": p, "other_chunk_id": o,
               "official_label_available": True, "source_split": "validation",
               "role": "development"}
              for q, p, o in (("q1", "b", "a"), ("q2", "a", "b"))]
    candidates = [{"source_query_id": q, "routes": {
        r: [{"chunk_id": "a", "rank": 0}, {"chunk_id": "b", "rank": 1}]
        for r in ("dense", "sparse", "bm25")}} for q in stage1]
    # English E0 deliberately disagrees with stage1 on q2; stage1 is the tie breaker.
    return RoleInputs("development", {"q1": stage1["q1"], "q2": {"a": 0., "b": 2., "c": 1.}},
                      stage1, {"q1": {"a": 1, "b": 4, "c": 0},
                               "q2": {"a": 4, "b": 4, "c": 0}}, labels, candidates)


def plain_report(inputs, k):
    rankers = {"E0": inputs.baseline, "stage1": inputs.stage1, "stage1_judge": {}}
    orders = {name: {q: baseline_order(s) for q, s in scores.items()}
              for name, scores in rankers.items()}
    for q, first in inputs.stage1.items():
        order, scores, _ = resort(first, inputs.judged[q], top_k=k)
        rankers["stage1_judge"][q], orders["stage1_judge"][q] = scores, order
    return evaluate_rankers(inputs.supervision, rankers, orders)[0]


def test_full_k_reproduces_plain_resort_all_metrics():
    inputs = fixture()
    full = curve_points(inputs, [3])[0]
    assert full["evaluation"] == plain_report(inputs, 3)["rankers"]["stage1_judge"]
    assert (full["strict_correct"], full["both_directions_correct"], full["preferred@1"]) == (2, 1, 1.)
    assert full["mean_judged"] == 3


def test_k_zero_preserves_stage1_including_ties():
    inputs = fixture()
    inputs.stage1["q1"]["a"] = 1.
    point = curve_points(inputs, [0])[0]
    assert point["evaluation"] == plain_report(inputs, 3)["rankers"]["stage1"]
    assert (point["model_tie"], point["mean_judged"], point["triggered_fraction"]) == (1, 0., 0.)


@pytest.mark.parametrize("missing", ["absent", None, float("nan")])
def test_missing_scores_counted_and_entire_query_falls_back(missing):
    inputs = fixture()
    if missing == "absent":
        del inputs.judged["q1"]["a"]
    else:
        inputs.judged["q1"]["a"] = missing
    point = curve_points(inputs, [3])[0]
    assert point["strict_correct"] == 1  # available b=4 must not move ahead of a
    assert point["fallback_queries"] == point["missing_judge_candidates"] == 1
    assert point["mean_judged"] == 2.5
    assert point["requested_candidates"] == 6
    assert point["unavailable"] == 0  # final ranking falls back; pair is still evaluable


def test_entire_missing_query_and_unselected_missing_score():
    inputs = fixture()
    del inputs.judged["q1"]
    inputs.judged["q2"]["c"] = None
    point = curve_points(inputs, [2])[0]
    assert point["missing_judge_candidates"] == 2
    assert point["mean_judged"] == 1


def test_margin_selects_cheapest_eligible_threshold_and_fixed_confirmation():
    inputs = fixture()
    selection = select_margin_threshold(inputs, top_k=3)
    eligible = [p for p in selection["sweep"] if p["strict_correct"] >= 1.9]
    chosen = min(eligible, key=lambda p: (p["mean_judged"], p["threshold"]))
    assert selection["threshold"] == chosen["threshold"]
    assert chosen["mean_judged"] == 1.5
    assert chosen["triggered_fraction"] == .5
    assert selection["sweep"][0]["triggered_fraction"] == 0  # strict '<'
    assert selection["sweep"][-1]["triggered_fraction"] == 1
    confirmation = deepcopy(inputs)
    confirmation.role = "confirmation"
    for row in confirmation.supervision:
        row["role"] = "confirmation"
    confirmation.supervision[0]["preferred_chunk_id"] = "a"
    confirmation.supervision[0]["other_chunk_id"] = "b"
    variant = trigger_variants(confirmation, threshold=selection["threshold"], top_k=3)[2]
    assert variant["triggered_fraction"] == .5
    assert variant["threshold"] == selection["threshold"]
    with pytest.raises(ValueError, match="requires development"):
        select_margin_threshold(confirmation)


def test_route_disagreement_uses_rank_not_list_order_or_score():
    inputs = fixture()
    row = inputs.candidates[0]
    row["routes"]["dense"].reverse()
    assert route_disagreement(row) == (False, 0)
    row["routes"]["sparse"][0]["chunk_id"] = "c"
    assert route_disagreement(row) == (True, 0)
    point = trigger_variants(inputs, threshold=0.5, top_k=3)[3]
    assert point["triggered_fraction"] == .5
    assert point["strict_correct"] == 2


def test_missing_routes_and_query_trigger_and_count():
    inputs = fixture()
    inputs.candidates[0]["routes"]["bm25"] = []
    del inputs.candidates[0]["routes"]["dense"]
    inputs.candidates.pop()
    point = trigger_variants(inputs, threshold=0.5, top_k=3)[3]
    assert point["missing_route_queries"] == 2
    assert point["missing_routes"] == 5
    assert point["triggered_fraction"] == 1


def test_cost_uses_all_queries_while_accuracy_excludes_uncovered_pairs():
    inputs = fixture()
    inputs.supervision[1]["preferred_chunk_id"] = "not-recalled"
    point = evaluate_point(inputs, 3)
    assert point["n"] == 1
    assert point["queries"] == 2
    assert point["mean_judged"] == 3
    assert point["eligible_bidirectional_pairs"] == 0


def test_invalid_population_and_test_split_rejected():
    inputs = fixture()
    with pytest.raises(ValueError, match="nonnegative"):
        curve_points(inputs, [-1])
    inputs.supervision[0]["source_split"] = "test"
    with pytest.raises(ValueError, match="validation"):
        inputs.__post_init__()


@pytest.mark.parametrize("field", ["source_split", "role"])
def test_missing_split_metadata_is_not_assumed_to_be_validation(field):
    inputs = fixture()
    del inputs.supervision[0][field]
    with pytest.raises(ValueError, match="validation"):
        inputs.__post_init__()


@pytest.fixture
def script():
    path = Path(__file__).resolve().parents[2] / "scripts/llm_judge_cost_curve.py"
    spec = importlib.util.spec_from_file_location("cost_curve_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cache_files(tmp_path):
    inputs = fixture()
    metadata = {"model": "test-model", "effort": "low", "prompt_version": "judge_prompt_v1"}
    rows = [dict(metadata, source_query_id=q, chunk_id=c, score=s, status="available", level="l2")
            for q, scores in inputs.judged.items() for c, s in scores.items()]
    cache = tmp_path / "pilot/l2s-development-judge"
    cache.mkdir(parents=True)
    (cache / "scores.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (cache / "summary.json").write_text(json.dumps(dict(metadata, items=len(rows))))
    data = {
        "pilot/baseline/development/scores.jsonl": [
            {"source_query_id": q, "scores": [{"chunk_id": c, "score": s} for c, s in scores.items()]}
            for q, scores in inputs.baseline.items()],
        "pilot/items-stage1-top20/development/stage1-development.jsonl": [
            {"source_query_id": q, "scores": [{"chunk_id": c, "score": s} for c, s in scores.items()]}
            for q, scores in inputs.stage1.items()],
        "experiment/prepared/development/supervision.jsonl": inputs.supervision,
        "experiment/candidates/development/inputs.jsonl": inputs.candidates,
    }
    for name, records in data.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r) + "\n" for r in records))
    args = SimpleNamespace(root=tmp_path / "pilot", candidates=tmp_path / "experiment/candidates",
                           out=tmp_path / "output", judge_dir_suffix="")
    return args, cache, metadata


@pytest.mark.parametrize("field,value", [("model", "other-model"), ("effort", "medium"),
                                         ("prompt_version", "other-prompt")])
def test_mixed_cache_metadata_rejected(script, cache_files, field, value):
    args, cache, _ = cache_files
    path = cache / "scores.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0][field] = value
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    with pytest.raises(ValueError, match="metadata/count mismatch"):
        script.load_role(args, "development", "")


def test_partial_cache_counts_missing_but_truncated_file_is_rejected(script, cache_files):
    args, cache, _ = cache_files
    path = cache / "scores.jsonl"
    path.write_text("\n".join(path.read_text().splitlines()[1:]) + "\n")
    with pytest.raises(ValueError, match="metadata/count mismatch"):
        script.load_role(args, "development", "")
    summary_path = cache / "summary.json"
    summary = json.loads(summary_path.read_text())
    summary["items"] -= 1
    summary_path.write_text(json.dumps(summary))
    inputs, _ = script.load_role(args, "development", "")
    point = evaluate_point(inputs, 3)
    assert point["missing_judge_candidates"] == point["fallback_queries"] == 1


def test_role_judge_mismatch_rejected_before_threshold_selection(script, tmp_path, monkeypatch):
    args = SimpleNamespace(out=tmp_path / "output", judge_dir_suffix="")
    monkeypatch.setattr(script, "load_role", lambda args, role, suffix: (
        fixture(), {"judge_metadata": {"model": role, "effort": "low",
                                       "prompt_version": "judge_prompt_v1"}}))
    with pytest.raises(ValueError, match="must use the same judge"):
        script.run(args)
    assert not args.out.exists()
