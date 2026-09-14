"""Synthetic-only checks for the fixed-model Test replay acceptance driver."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "issue49_replay", ROOT / "runs/post_recall/n8-test-replay-20260914/replay.py"
)
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


@pytest.fixture
def population():
    labels, rows = [], []
    cases = [
        ("q1", "pair1", "q1", "a", False, True, {"a": 1., "b": 1.}),
        ("q2", "pair1", "q2", "b", False, True, {"a": 2., "b": 3.}),
        ("q3", "pair2", "q1", "b", False, True,
         {"a": 1., "b": 0., **{f"background-{i:02}": 2. for i in range(20)}}),
        ("q4", "pair2", "q2", "a", False, True, {"a": 2.}),
        ("q5", "pair3", "q1", "a", True, True, {"a": 3., "b": 2.}),
        ("q6", "pair3", "q2", "b", True, True, {"a": 2., "b": 3.}),
        ("q7", "pair4", "q1", "b", False, False, {"a": 0., "b": 1.}),
    ]
    for qid, pair, direction, preferred, conflict, official, scores in cases:
        labels.append({
            "source_query_id": qid, "source_group_id": pair, "pair_id": pair,
            "direction": direction, "preferred_chunk_id": preferred,
            "other_chunk_id": "b" if preferred == "a" else "a",
            "structural_conflict": conflict, "official_label_available": official,
        })
        rows.append({"source_query_id": qid, "scores": [
            {"chunk_id": cid, "score": score} for cid, score in scores.items()
        ]})
    return labels, {name: copy.deepcopy(rows) for name in ("E0", "fusion", "background_n8")}


def test_aggregate_preserves_populations_ties_incomplete_pairs_and_full_pool(population):
    labels, predictions = population
    actual = replay.aggregate(labels, predictions)
    assert actual["coverage"] == {
        "all_queries": 7, "both_designated_in_candidate_union": 6,
        "both_designated_in_fusion_top20": 5, "official_and_covered": 5,
        "primary_no_structural_conflict": 3,
    }
    primary = actual["results"]["primary_no_structural_conflict"]["background_n8"]
    assert primary["queries"] == 3
    assert primary["strict_correct"] == primary["strict_wrong"] == primary["strict_tie"] == 1
    assert primary["strict_accuracy"] == 1 / 3
    assert primary["complete_pairs"] == 1
    assert primary["both_directions_correct"] == primary["both_directions_accuracy"] == 0
    # The score tie ranks preferred "a" first, but does not become a strict win.
    assert primary["preferred_at_1"] == primary["preferred_at_3"] == 2 / 3
    # q3's preferred candidate is still ranked 22nd, beyond every reported cutoff.
    assert primary["preferred_mrr"] == pytest.approx((1 + 1 + 1 / 22) / 3, abs=1e-15)
    assert primary["preferred_mean_rank"] == 8
    assert primary["both_designated_in_top10"] == 2
    sensitivity = actual["results"]["including_conflict"]["background_n8"]
    assert sensitivity["queries"] == 5
    assert sensitivity["strict_correct"] == 3
    assert sensitivity["complete_pairs"] == 2
    assert sensitivity["both_directions_correct"] == 1
    assert sensitivity["both_directions_accuracy"] == .5
    assert sensitivity["both_designated_in_top10"] == 4
    assert actual["mcnemar_primary_e0_vs_background_n8"]["discordant"] == 0


def test_aggregate_aligns_reordered_query_and_candidate_ids(population):
    labels, predictions = population
    expected = replay.aggregate(labels, predictions)
    predictions["background_n8"].reverse()
    for row in predictions["background_n8"]:
        row["scores"].reverse()
    assert replay.aggregate(labels, predictions) == expected


@pytest.mark.parametrize("problem, message", [
    ("missing_ranker", "three original rankers"),
    ("extra_ranker", "three original rankers"),
    ("missing_query", "query population"),
    ("foreign_query", "query population"),
    ("missing_candidate", "identical full candidate pools"),
    ("extra_candidate", "identical full candidate pools"),
    ("duplicate_query", "duplicate source_query_id"),
    ("duplicate_label", "duplicate source_query_id"),
    ("duplicate_candidate", "invalid/duplicate prediction score"),
    ("nonfinite_score", "invalid/duplicate prediction score"),
])
def test_aggregate_rejects_changed_rankers_and_populations(population, problem, message):
    labels, predictions = population
    rows = predictions["background_n8"]
    if problem == "missing_ranker":
        del predictions["fusion"]
    elif problem == "extra_ranker":
        predictions["new_model"] = copy.deepcopy(rows)
    elif problem == "missing_query":
        rows.pop()
    elif problem == "foreign_query":
        rows[-1]["source_query_id"] = "foreign"
    elif problem == "missing_candidate":
        rows[0]["scores"].pop()
    elif problem == "extra_candidate":
        rows[0]["scores"].append({"chunk_id": "foreign", "score": 0.})
    elif problem == "duplicate_query":
        rows.append(copy.deepcopy(rows[0]))
    elif problem == "duplicate_label":
        labels.append(copy.deepcopy(labels[0]))
    elif problem == "duplicate_candidate":
        rows[0]["scores"].append(copy.deepcopy(rows[0]["scores"][0]))
    else:
        rows[0]["scores"][0]["score"] = float("nan")
    with pytest.raises(ValueError, match=message):
        replay.aggregate(labels, predictions)


@pytest.mark.parametrize("actual, expected, matches", [
    (2736, 2736, True), (2737, 2736, False), (2736., 2736, False),
    (True, 1, False), (1e-12, 0., True), (2e-12, 0., False),
    (1_000_000. + 1e-7, 1_000_000., False), (float("nan"), 0., False),
])
def test_differences_uses_exact_integer_counts_and_absolute_float_tolerance(actual, expected, matches):
    differences = replay.differences({"metric": actual}, {"metric": expected})
    assert (differences == []) is matches
    if differences:
        assert differences[0]["metric"] == "metric"


def test_differences_checks_nested_intervals_and_schema():
    assert replay.differences({"ci": [0., 1.]}, {"ci": [0., 1.]}) == []
    assert replay.differences({"ci": [0., .9]}, {"ci": [0., 1.]}) == [
        {"metric": "ci[1]", "actual": .9, "expected": 1.}
    ]
    assert replay.differences({"ci": [0.]}, {"ci": [0., 1.]})
    assert replay.differences({"missing": 1}, {"count": 1})
    assert replay.differences({"count": 1, "extra": 0}, {"count": 1})


@pytest.mark.parametrize("filename", ["run.json", "scores.jsonl", "results.json"])
def test_reserve_output_refuses_existing_artifacts_without_writing(tmp_path, filename):
    out = tmp_path / "existing"
    out.mkdir()
    artifact = out / filename
    artifact.write_bytes(b"preserved historical bytes\n")
    with pytest.raises(FileExistsError, match="already exist"):
        replay.reserve_output(out)
    assert list(out.iterdir()) == [artifact]
    assert artifact.read_bytes() == b"preserved historical bytes\n"


def test_reserve_output_marks_started_and_cannot_be_reused(tmp_path):
    out = tmp_path / "new" / "run"
    replay.reserve_output(out)
    original = (out / "run.json").read_bytes()
    assert json.loads(original)["status"] == "started"
    with pytest.raises(FileExistsError):
        replay.reserve_output(out)
    assert (out / "run.json").read_bytes() == original


def test_run_prediction_failure_records_failure_and_preserves_historical_inputs(tmp_path, monkeypatch):
    data_root, out = tmp_path / "historical", tmp_path / "new-replay"
    runs = data_root / "runs/post_recall"
    snapshot = runs / "nevir-test-candidates-20260910/snapshot"
    model_dir = runs / "list-collapse-20260910/background-n8-training/model-b"
    member_dir = runs / "nevir-test-final-20260911"
    e0_dir = runs / "nevir-test-main-20260911/baseline"
    sources = {
        snapshot.parent / "run.json": {"status": "accepted", "snapshot": str(snapshot)},
        model_dir / "manifest.json": {
            "model_file_sha256": "synthetic-n8", "feature_version": replay.ENGLISH_FEATURE_VERSION,
            "feature_names": replay.FEATURE_NAMES, "n_estimators": 69,
        },
        member_dir / "frozen-config.json": {
            "rankers": {"background_n8": {"sha256": "synthetic-n8"}, "E0": {"sha256": "synthetic-e0"}}
        },
        member_dir / "results.json": {"historical_results": "preserve"},
        e0_dir / "summary.json": {
            "status": "completed", "source": str(snapshot), "model": {"sha256": "synthetic-e0"}
        },
    }
    for path, value in sources.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value) + "\n")
    candidate_input = snapshot / "candidates/test/inputs.jsonl"
    candidate_input.parent.mkdir(parents=True)
    candidate_input.write_text('{"synthetic_historical_candidate": true}\n')
    before = {path.relative_to(data_root): path.read_bytes()
              for path in data_root.rglob("*") if path.is_file()}

    monkeypatch.setattr(replay, "validate_production_bundle", lambda _: {"synthetic": True})
    monkeypatch.setattr(replay, "version", lambda _: "synthetic-version")
    monkeypatch.setattr(replay, "subprocess", SimpleNamespace(
        check_output=lambda *a, **kw: "synthetic-revision\n"
    ))
    monkeypatch.setattr(replay, "read_rows", lambda _: [{"source_query_id": "synthetic"}] * 2766)
    monkeypatch.setattr(replay.lgb, "Booster", lambda **kw: SimpleNamespace(
        num_trees=lambda: 69, num_feature=lambda: len(replay.FEATURE_NAMES)
    ))

    def fail_prediction(*args):
        raise RuntimeError("synthetic prediction failure")

    monkeypatch.setattr(replay, "baseline_scores", fail_prediction)
    with pytest.raises(RuntimeError, match="synthetic prediction failure"):
        replay.run(data_root, out)
    after = {path.relative_to(data_root): path.read_bytes()
             for path in data_root.rglob("*") if path.is_file()}
    assert after == before
    record = json.loads((out / "run.json").read_text())
    assert record["status"] == "failed" and record["error_type"] == "RuntimeError"
    assert "synthetic prediction failure" in (out / "failure.txt").read_text()
    assert not (out / "scores.jsonl").exists()
    assert not (out / "results.json").exists()
