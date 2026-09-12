"""Synthetic checks of statistical units, exclusions and the saved-result CLI."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from linkrag_eval.retrieval.learning_to_rank.llm_judge import (
    baseline_order,
    evaluate_rankers,
    score_maps,
)
from linkrag_eval.retrieval.learning_to_rank.nevir_evaluation import _bootstrap_delta
from linkrag_eval.retrieval.learning_to_rank.pair_statistics import (
    bidirectional_delta_ci,
    comparison_table,
    paired_sign_test,
    strict_delta_ci,
)


def row(i, a=True, b=False, group=None):
    return {
        "source_query_id": f"q{i}",
        "source_group_id": group or f"g{i // 4}",
        "pair_id": f"p{i // 2}",
        "direction": f"q{i % 2 + 1}",
        "a": "strict_correct" if a else "reverse",
        "b": "strict_correct" if b else "model_tie",
    }


def test_large_sample_ci_contains_generating_delta():
    rng = np.random.default_rng(61)
    rows = [row(i, rng.random() < 0.7, rng.random() < 0.5) for i in range(8000)]
    stat = strict_delta_ci(rows, "a", "b")
    assert stat["interval"][0] < 0.2 < stat["interval"][1]
    assert stat["estimate"] == pytest.approx(0.2, abs=0.025)


def test_exact_sign_symmetric_one_sided_and_reversal():
    symmetric = [row(i, i < 10, i >= 10) for i in range(20)]
    assert paired_sign_test(symmetric, "a", "b")["p_value"] == 1.0
    one_sided = [row(i) for i in range(20)]
    stat = paired_sign_test(one_sided, "a", "b")
    reverse = paired_sign_test(one_sided, "b", "a")
    assert stat["p_value"] == 2 / 2**20
    assert stat["a_correct_b_not"] == reverse["b_correct_a_not"] == 20
    assert stat["p_value"] == reverse["p_value"]
    # Exact nontrivial tail: 2 * (C(5, 0) + C(5, 1)) / 2**5.
    assert paired_sign_test([row(i, i < 4, i == 4) for i in range(5)], "a", "b")["p_value"] == 0.375


def test_unavailable_dropped_ties_retained_and_counted():
    rows = [
        row(0),
        row(1, False, True),
        row(2, True, True),
        row(3, False, False),
        dict(row(4), a="unavailable"),
        dict(row(5), b="unavailable"),
    ]
    sign = paired_sign_test(rows, "a", "b")
    assert (sign["a_correct_b_not"], sign["b_correct_a_not"], sign["ties"]) == (1, 1, 2)
    assert sign["n"] == 4 and sign["dropped_unavailable"] == 2
    stat = strict_delta_ci(rows, "a", "b")
    assert stat["estimate"] == 0 and stat["n"] == 4
    assert stat["dropped_unavailable"] == 2


def test_empty_single_group_and_no_discordance():
    for rows in ([], [dict(row(0), a="unavailable")]):
        assert strict_delta_ci(rows, "a", "b")["estimate"] is None
        assert paired_sign_test(rows, "a", "b")["p_value"] is None
    stat = strict_delta_ci([row(0)], "a", "b")
    assert stat["interval"] is None
    assert stat["interval_reason"] == "fewer_than_two_source_groups"
    assert paired_sign_test([row(0, True, True)], "a", "b")["p_value"] == 1.0


def test_deterministic_and_exact_n04_micro_average():
    rows = [row(i, i % 3 == 0, i % 5 == 0) for i in range(71)]
    stat = strict_delta_ci(rows, "a", "b", repeats=301)
    assert stat == strict_delta_ci(rows, "a", "b", repeats=301)
    differences = [int(r["a"] == "strict_correct") - int(r["b"] == "strict_correct") for r in rows]
    expected = _bootstrap_delta(
        [r["source_group_id"] for r in rows], differences, seed=20260910, repeats=301
    )
    assert all(stat[key] == value for key, value in expected.items())
    assert stat["estimate"] == sum(differences) / len(rows)


def test_group_resampling_with_one_dominant_group_is_wide():
    rows = [row(i, group="huge") for i in range(1000)]
    rows += [row(1000 + i, False, True, group=f"small{i // 10}") for i in range(90)]
    stat = strict_delta_ci(rows, "a", "b")
    assert stat["estimate"] == 910 / 1090  # Not the source-macro value -0.8.
    assert stat["groups"] == 10
    assert stat["interval"][0] == -1
    assert stat["interval"][1] > 0.9


def test_alpha_changes_percentiles_and_custom_group_key():
    rows = [dict(row(i, i % 2 == 0, i % 3 == 0), cluster=f"c{i // 6}") for i in range(60)]
    wide = strict_delta_ci(rows, "a", "b", group_key="cluster")
    narrow = strict_delta_ci(rows, "a", "b", group_key="cluster", alpha=0.2)
    assert narrow["confidence"] == 0.8 and narrow["groups"] == 10
    assert wide["interval"][0] <= narrow["interval"][0]
    assert wide["interval"][1] >= narrow["interval"][1]


def test_bidirectional_uses_complete_pairs_and_pair_denominator():
    rows = [
        row(0),
        row(1),
        row(2, True, True),
        row(3, False, True),
        row(4),
        row(5),
        row(6),
        dict(row(7), a="unavailable"),
        row(8),
    ]
    stat = bidirectional_delta_ci(rows, "a", "b")
    assert stat["n"] == 3 and stat["estimate"] == 1 / 3
    assert stat["group_sizes"] == {"g0": 2, "g1": 1}
    assert stat["dropped_incomplete_pairs"] == 1
    assert stat["dropped_unavailable_pairs"] == 1
    expected = _bootstrap_delta(["g0", "g0", "g1"], [1, -1, 1], seed=20260910, repeats=2000)
    assert stat["interval"] == expected["interval"]


@pytest.mark.parametrize(
    "rows",
    [
        [row(0), row(0)],
        [row(0), dict(row(1), source_group_id="different")],
        [dict(row(0), direction="q3")],
        [dict(row(0), pair_id=None)],
    ],
)
def test_malformed_pairs_rejected(rows):
    with pytest.raises(ValueError):
        bidirectional_delta_ci(rows, "a", "b")


@pytest.mark.parametrize(
    "kw",
    [
        {"repeats": 0},
        {"repeats": 1.5},
        {"alpha": 1},
        {"alpha": 0},
        {"alpha": float("nan")},
        {"seed": -1},
    ],
)
def test_bad_bootstrap_configuration_rejected(kw):
    with pytest.raises(ValueError):
        strict_delta_ci([row(0)], "a", "b", **kw)


@pytest.mark.parametrize("relation", [None, "typo", 1])
def test_invalid_relations_rejected(relation):
    with pytest.raises(ValueError, match="relation"):
        paired_sign_test([dict(row(0), a=relation)], "a", "b")


def test_comparison_table_accepts_generator_and_serializes():
    table = comparison_table((row(i) for i in range(8)), [("a", "b"), ("b", "a")])
    assert [r["strict"]["estimate"] for r in table] == [1, -1]
    assert json.loads(json.dumps(table)) == table


@pytest.fixture
def script():
    path = Path(__file__).resolve().parents[2] / "scripts/llm_judge_statistics.py"
    spec = importlib.util.spec_from_file_location("judge_statistics_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path, data, *, jsonl=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in data) if jsonl else json.dumps(data))


@pytest.fixture
def pilot(tmp_path):
    root = tmp_path / "pilot"
    for role in ("development", "confirmation"):
        rows = [
            dict(
                row(i),
                source_query_id=f"{role}-{i}",
                E0="reverse",
                judge="strict_correct",
                stage1="model_tie",
                stage1_judge="strict_correct",
                E0_judge="strict_correct",
            )
            for i in range(8)
        ]
        for level in (f"l1-{role}-eval", f"l2s-{role}-k20-v2"):
            write(root / level / "official-per-query.jsonl", rows, jsonl=True)
    return root


def test_script_run_extra_partial_join_and_overwrite(script, pilot, tmp_path, capsys):
    extra = tmp_path / "open.jsonl"
    write(
        extra,
        [
            {"source_query_id": "development-0", "judge": "strict_correct"},
            {"source_query_id": "development-1", "judge": "reverse"},
        ],
        jsonl=True,
    )
    args = SimpleNamespace(
        root=pilot, out=tmp_path / "out", seed=20260910, repeats=31, extra=[f"open={extra}"]
    )
    script.run(args)
    result = json.loads((args.out / "results.json").read_text())
    assert len(result["roles"]["confirmation"]["comparisons"]) == 4
    dev = result["roles"]["development"]
    assert dev["exposed"] and len(dev["comparisons"]) == 6
    assert dev["l3"]["status"] == "missing_inputs"
    assert dev["comparisons"][-1]["strict"]["dropped_unavailable"] == 6
    assert dev["comparisons"][-1]["sign_test"]["a_correct_b_not"] == 1
    assert "已曝光" in capsys.readouterr().out
    before = (args.out / "results.json").read_bytes()
    with pytest.raises(FileExistsError):
        script.run(args)
    assert before == (args.out / "results.json").read_bytes()


def test_script_run_extra_selects_l2_tiebreak_column(script, pilot, tmp_path):
    extra = tmp_path / "l2.jsonl"
    write(
        extra,
        [
            {
                "source_query_id": f"confirmation-{i}",
                "stage1_judge": "strict_correct" if i < 4 else "reverse",
                "E0_judge": "strict_correct" if i < 2 else "reverse",
            }
            for i in range(8)
        ],
        jsonl=True,
    )
    original = extra.read_bytes()
    args = SimpleNamespace(
        root=pilot, out=tmp_path / "out", seed=20260910, repeats=31,
        extra=[f"open_l2:stage1_judge={extra}", f"open_l2_e0:E0_judge={extra}"],
    )
    script.run(args)
    result = json.loads((args.out / "results.json").read_text())
    confirm = result["roles"]["confirmation"]
    assert confirm["extras"]["open_l2"]["relation_column"] == "stage1_judge"
    assert confirm["extras"]["open_l2_e0"]["relation_column"] == "E0_judge"
    comparisons = confirm["comparisons"]
    assert comparisons[1]["strict"]["estimate"] == 1  # Existing GPT comparison is unchanged.
    for comparison in comparisons[4:]:
        expected = 4 if comparison["ranker_a"] == "open_l2" else 2
        assert comparison["strict"]["estimate"] == expected / 8
        assert comparison["strict"]["dropped_unavailable"] == 0
        assert comparison["sign_test"]["a_correct_b_not"] == expected
        assert comparison["bidirectional"]["n"] == 4
    assert len(result["roles"]["development"]["comparisons"]) == 4
    assert extra.read_bytes() == original


@pytest.mark.parametrize("selector", ["open:", "open::judge", ":judge", "open:judge:extra"])
def test_extra_rejects_malformed_column_selector(script, selector):
    with pytest.raises(ValueError, match="ranker\\[:column\\]"):
        script.load_extra([f"{selector}=/not-read.jsonl"])


@pytest.mark.parametrize("relation", [None, "wrong"])
def test_extra_explicit_column_never_falls_back_to_judge(script, tmp_path, relation):
    data = [{"source_query_id": "q0", "judge": "strict_correct"}]
    if relation is not None:
        data[0]["stage1_judge"] = relation
    path = tmp_path / "extra.jsonl"
    write(path, data, jsonl=True)
    with pytest.raises(ValueError, match="valid stage1_judge relations"):
        script.load_extra([f"open:stage1_judge={path}"])


@pytest.mark.parametrize("bad", ["duplicate", "unknown", "identity", "relation"])
def test_extra_rejects_bad_data(script, pilot, tmp_path, bad):
    r = {"source_query_id": "development-0", "judge": "strict_correct"}
    data = [r]
    if bad == "duplicate":
        data.append(r)
    elif bad == "unknown":
        r["source_query_id"] = "outside"
    elif bad == "identity":
        r["pair_id"] = "wrong"
    else:
        r["judge"] = "wrong"
    path = tmp_path / "extra.jsonl"
    write(path, data, jsonl=True)
    out = tmp_path / "out"
    with pytest.raises(ValueError):
        script.run(SimpleNamespace(root=pilot, out=out, seed=1, repeats=10, extra=[f"open={path}"]))
    assert not out.exists()


def test_l3_derivation_reuses_evaluator_and_verifies_saved_metrics(script, tmp_path, monkeypatch):
    monkeypatch.setattr(script, "REPO", tmp_path)
    root, role = tmp_path / "pilot", "confirmation"
    labels = [
        dict(row(i), official_label_available=True, preferred_chunk_id="x", other_chunk_id="y")
        for i in range(8)
    ]
    labels_path = tmp_path / (
        "runs/post_recall/nevir-ltr-validation-20260907/"
        "data-preparation/experiment/prepared/confirmation/supervision.jsonl"
    )
    write(labels_path, labels, jsonl=True)
    base = [
        {
            "source_query_id": r["source_query_id"],
            "scores": [{"chunk_id": "x", "score": 0}, {"chunk_id": "y", "score": 1}],
        }
        for r in labels
    ]
    predicted = [
        dict(r, scores=[{"chunk_id": "x", "score": 2}, {"chunk_id": "y", "score": 1}]) for r in base
    ]
    folder = root / f"l3s-{role}-v2-evaluation"
    base_path, first_path = root / "baseline/scores.jsonl", root / "stage1.jsonl"
    write(base_path, base, jsonl=True)
    write(first_path, base, jsonl=True)
    write(base_path.with_name("summary.json"), {"inputs": {"supervision": str(labels_path)}})
    write(folder / "predictions.jsonl", predicted, jsonl=True)
    rankers = {"E0": score_maps(base), "stage1": score_maps(base), "L3": score_maps(predicted)}
    orders = {k: {q: baseline_order(s) for q, s in scores.items()} for k, scores in rankers.items()}
    report, expected = evaluate_rankers(labels, rankers, orders)
    saved = {
        "role": role,
        "official": report,
        "inputs": {"baseline": str(base_path), "stage1": str(first_path)},
    }
    write(folder / "results.json", saved)
    rows, provenance = script.derive_l3(root, role)
    assert rows == expected and provenance["status"] == "derived_and_verified"
    saved["official"]["rankers"]["L3"]["pairwise"]["strict_correct"] = 0
    write(folder / "results.json", saved)
    with pytest.raises(ValueError, match="differ"):
        script.derive_l3(root, role)
    write(
        base_path.with_name("summary.json"), {"inputs": {"supervision": "/never-read/Test.jsonl"}}
    )
    with pytest.raises(ValueError, match="refusing to read"):
        script.derive_l3(root, role)
