"""No-network checks for pointwise judging, constrained batches and strict metrics."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from linkrag_eval.retrieval.learning_to_rank import llm_judge as judge

META = {"model": "fake-model", "effort": "low", "codex_version": "fake-cli",
        "prompt_version": judge.PROMPT_VERSION}


class FakeRunner:
    def __init__(self, failures=0):
        self.calls = []
        self.failures = failures

    def run(self, prompt, out):
        self.calls.append(prompt)
        if len(self.calls) <= self.failures:
            return {"items": []}
        return {"items": [{"id": identity, "score": i % 5, "reason": "synthetic support"}
                          for i, identity in enumerate(re.findall(r"^ITEM id=(\w+)$", prompt, re.MULTILINE))]}


def sample_items(n=12):
    return [{"source_query_id": f"query-{i}", "chunk_id": f"chunk-{i}", "pair_id": f"private-pair-{i // 4}",
             "query": f"query text {i}", "passage": f"passage text {i}", "level": "l1"} for i in range(n)]


def pool():
    queries = [{"source_query_id": "q", "query": "Which door is open?"}]
    candidates = [{"chunk_id": cid, "dataset_id": 1, "doc_id": i,
                   "source_passage_id": cid, "content": f"Door {cid} is open."}
                  for i, cid in enumerate(("a", "b", "c"), 1)]
    labels = [{"source_query_id": "q", "pair_id": "hidden-pair", "source_group_id": "hidden-source",
               "direction": "q1", "official_label_available": True, "preferred_chunk_id": "b",
               "other_chunk_id": "a"}]
    inputs = [{**queries[0], "ranking_input_ready": True, "failed_sources": [], "status": "ready",
               "dataset_ids": [1], "candidate_rows": candidates,
               "routes": {"dense": [dict(c, rank=i, score=3 - i) for i, c in enumerate(candidates)],
                          "sparse": [], "bm25": []},
               "route_status": {"dense": "ok", "sparse": "empty", "bm25": "empty"}}]
    predictions = [{"source_query_id": "q", "scores": [{"chunk_id": c, "score": s}
                     for c, s in (("a", 3), ("b", 2), ("c", 1))]}]
    return queries, labels, inputs, predictions


def test_batch_constraint_capacity_determinism_and_prompt_boundary():
    items = sample_items(148)
    batches = judge.plan_batches(items)
    assert list(map(len, batches)) == [37] * 4
    assert batches == judge.plan_batches(items)
    assert Counter(r["chunk_id"] for b in batches for r in b) == Counter(r["chunk_id"] for r in items)
    assert all(len({r["pair_id"] for r in b}) == len(b) for b in batches)
    for size in (1, 2, 10, 40, 100):
        assert all(len(b) <= size for b in judge.plan_batches(items, batch_size=size))
    prompt = judge.prompt_for(batches[0])
    assert prompt.startswith(judge.JUDGE_PROMPT + "\n\n")
    assert "private-pair" not in prompt and "chunk-" not in prompt
    assert "source_query_id" not in prompt and "ITEM id=i01\nQUERY:" in prompt
    with pytest.raises(ValueError):
        judge.plan_batches(items, batch_size=0)


@pytest.mark.parametrize("bad", [None, {}, {"items": []}, {"items": [{"id": "i01", "score": True, "reason": "ok"}]},
    {"items": [{"id": "i01", "score": 5, "reason": "ok"}]},
    {"items": [{"id": "i01", "score": 2.0, "reason": "ok"}]},
    {"items": [{"id": "unknown", "score": 2, "reason": "ok"}]},
    {"items": [{"id": "i01", "score": 2, "reason": "ok"}] * 2}])
def test_response_rejects_malformed(bad):
    with pytest.raises(ValueError):
        judge.validate_response(bad, 1)


def test_response_reordered_ids_are_mapped():
    values = judge.validate_response({"items": [{"id": "i02", "score": 0, "reason": "no"},
                                              {"id": "i01", "score": 4, "reason": "yes"}]}, 2)
    assert [r["score"] for r in values] == [4, 0]


def test_cache_hits_dedup_and_conflicting_metadata(tmp_path):
    items = sample_items()
    items.append(dict(items[0], source_query_id="duplicate"))
    runner = FakeRunner()
    first, summary = judge.judge_items(items, runner, tmp_path / "first", metadata=META, workers=1)
    assert summary["duplicate_items"] == 1 and summary["batch_count"] == 4
    again = FakeRunner()
    second, cached = judge.judge_items(items, again, tmp_path / "second", metadata=META,
                                      cache_dirs=[tmp_path / "first/judge-cache"])
    assert second == first and cached["cache_hits"] == 12 and not again.calls
    with pytest.raises(FileExistsError):
        judge.judge_items(items, again, tmp_path / "second", metadata=META)
    assert judge.cache_key(items[0], META) != judge.cache_key(items[0], dict(META, effort="medium"))


def test_retry_once_then_split_and_terminal_failure(tmp_path):
    items = [sample_items(12)[i] for i in (0, 4, 8)]
    runner = FakeRunner(failures=2)
    _, summary = judge.judge_items(items, runner, tmp_path / "split", metadata=META, workers=1)
    assert summary["batch_count"] == 4 and summary["unavailable"] == 0
    failed = FakeRunner(failures=100)
    results, summary = judge.judge_items(items, failed, tmp_path / "failed", metadata=META, workers=1)
    assert summary["batch_count"] == 4 and summary["unavailable"] == 3
    assert all(r["score"] is None and r["status"] == "unavailable" for r in results)
    assert all(sum(item["query"] in prompt for prompt in failed.calls) == 3 for item in items)
    retried = FakeRunner()
    results, summary = judge.judge_items(items, retried, tmp_path / "retried", metadata=META,
                                         cache_dirs=[tmp_path / "failed/judge-cache"], workers=1)
    assert retried.calls and summary["unavailable"] == 0 and summary["cache_hits"] == 0
    assert all(r["status"] == "available" for r in results)


def test_build_l1_l2_l3_and_fake_runner_resort(tmp_path):
    queries, labels, inputs, predictions = pool()
    l1 = judge.build_items(queries, labels, inputs, predictions)
    assert [r["chunk_id"] for r in l1] == ["b", "a"]
    for level in ("l2", "l3"):
        rows = judge.build_items(queries, labels, inputs, stage1=predictions, level=level, top_k=2)
        assert [r["chunk_id"] for r in rows] == ["a", "b"]
        result, _ = judge.judge_items(rows, FakeRunner(), tmp_path / level, metadata=META)
        assert len(result) == 2
    labels[0]["other_chunk_id"] = "missing"
    assert not judge.build_items(queries, labels, inputs, predictions)
    assert len(judge.build_items(queries, labels, inputs, stage1=predictions, level="l2")) == 3
    order, scores, stats = judge.resort({"a": 3., "b": 2., "c": 1.}, {"a": 0, "b": 4}, top_k=2)
    assert order == ["b", "a", "c"] and scores["b"] > scores["a"] > scores["c"]
    assert stats["triggered"] and stats["moved_candidates"] == 2
    order, _, _ = judge.resort({"a": 3., "b": 2., "c": 1.}, {"a": 4, "b": 4}, top_k=2)
    assert order == ["a", "b", "c"]
    _, scores, _ = judge.resort({"a": 2., "b": 2.}, {"a": 4, "b": 4}, top_k=2)
    assert judge.relation(scores["a"], scores["b"]) == "model_tie"
    order, scores, stats = judge.resort({"a": 2., "b": 2.}, {"a": 4}, top_k=2)
    assert scores["a"] == scores["b"] and stats["fallback"]


def test_strict_metrics_denominators_macro_pairs_and_corrections():
    rows = [{"source_query_id": str(i), "source_group_id": "s1" if i < 2 else "s2",
             "pair_id": "p1" if i < 2 else "p2", "direction": "q1" if i % 2 == 0 else "q2",
             "E0": baseline, "judge": actual}
            for i, (baseline, actual) in enumerate((("reverse", "strict_correct"),
                ("strict_correct", "strict_correct"), ("strict_correct", "model_tie"),
                ("reverse", "unavailable"), ("reverse", "reverse")))]
    metric = judge.metrics(rows, "judge")
    assert metric["strict_correct"] == 2 and metric["n"] == 5
    assert metric["reverse"] == metric["model_tie"] == metric["unavailable"] == 1
    assert metric["strict_accuracy"] == .4 and metric["source_macro_accuracy"] == .5
    assert metric["eligible_bidirectional_pairs"] == metric["both_directions_correct"] == 1
    assert judge.contrast(rows) == {"n": 5, "common_correct": 1, "corrected": 1,
                                    "damaged": 1, "common_not_correct": 2, "net": 0}
    _, labels, _, predictions = pool()
    report, _ = judge.evaluate_pairs(labels, judge.score_maps(predictions), {"q": {"a": 1, "b": 4}})
    assert report["judge"]["strict_correct"] == report["contrast"]["corrected"] == 1
    human, _ = judge.evaluate_pairs(labels, judge.score_maps(predictions), {"q": {"a": 1, "b": 4}},
                                    human={"q": ("a", "b")})
    assert human["judge"]["reverse"] == 1


def test_baseline_exactness_rejects_order_and_value_changes():
    queries, _, inputs, _ = pool()
    class Booster:
        def predict(self, matrix, *, num_threads):
            assert num_threads == 1 and matrix.shape == (3, 38)
            return np.array([.5, .25, -.5])
    rows = judge.baseline_scores(queries, inputs, Booster())
    judge.check_exact(rows, rows)
    changed = json.loads(json.dumps(rows))
    changed[0]["scores"].reverse()
    with pytest.raises(ValueError, match="differ"):
        judge.check_exact(rows, changed)
    changed = json.loads(json.dumps(rows))
    changed[0]["scores"][0]["score"] += 1e-15
    with pytest.raises(ValueError, match="differ"):
        judge.check_exact(rows, changed)


def test_codex_command_uses_isolated_cwd_and_only_prompt(monkeypatch, tmp_path):
    monkeypatch.setattr(judge, "runtime_metadata", lambda *args: META)
    def run(command, **kwargs):
        cwd = kwargs["cwd"]
        assert Path(__file__).resolve().parents[2] not in cwd.parents
        assert sorted(p.name for p in cwd.iterdir()) == ["prompt.txt", "schema.json"]
        assert command == ["codex", "exec", "--ephemeral", "--skip-git-repo-check", "-s", "read-only",
            "--color", "never", "-c", "model_reasoning_effort=low",
            "--output-schema", "schema.json", "-o", "out.json", "-"]
        response = {"items": [{"id": "i01", "score": 4, "reason": "supported"}]}
        (cwd / "out.json").write_text(json.dumps(response))
        return SimpleNamespace(returncode=0, stdout="event\n", stderr="model: fake-model\n")
    monkeypatch.setattr(judge.subprocess, "run", run)
    runner = judge.CodexRunner()
    rows, summary = judge.judge_items(sample_items(1), runner, tmp_path / "run", metadata=META)
    assert rows[0]["score"] == 4 and summary["batch_count"] == 1
    assert (tmp_path / "run/batch-001/events.jsonl").exists()


def test_stage1_column_and_explicit_item_selection():
    from linkrag_eval.retrieval.learning_to_rank.features import (
        FEATURE_NAMES,
        build_online_features,
    )
    from linkrag_eval.retrieval.learning_to_rank.pairwise_training import _method_view
    queries, labels, inputs, baseline = pool()
    first = judge.stage1_scores(queries, inputs)
    ids, matrix = build_online_features(**_method_view(inputs[0], queries[0]["query"]),
                                       feature_version=judge.ENGLISH_FEATURE_VERSION)
    assert first[0]["scores"] == [{"chunk_id": cid, "score": float(s)} for cid, s in
                                 zip(ids, matrix[:, FEATURE_NAMES.index("baseline_score")], strict=True)]
    first = [{"source_query_id": "q", "scores": [{"chunk_id": cid, "score": score}
              for cid, score in (("a", 0), ("b", 4), ("c", 4))]}]
    for level in ("l2", "l3"):
        rows = judge.build_items(queries, labels, inputs, stage1=first, level=level, top_k=2)
        assert [r["chunk_id"] for r in rows] == ["b", "c"]
        with pytest.raises(ValueError, match="stage1"):
            judge.build_items(queries, labels, inputs, baseline, level=level)


def test_l2_four_rankers_superset_fallback_list_arithmetic_and_contrasts():
    first = {q: {"a": 4., "b": 3., "c": 2., "d": 1.} for q in ("q1", "q2")}
    base = {"q1": {"a": 0., "b": 4., "c": 3., "d": 2.}, "q2": first["q2"]}
    judged = {"q1": {"a": 4, "b": 4, "c": None}, "q2": {"a": 1, "b": 4, "c": None}}
    labels = [{"source_query_id": q, "pair_id": "pair", "source_group_id": "source", "direction": q,
               "official_label_available": True, "preferred_chunk_id": p, "other_chunk_id": o}
              for q, p, o in (("q1", "a", "b"), ("q2", "b", "a"))]
    rankers, orders, trigger = judge.l2_rankers(base, first, judged, top_k=2)
    assert orders["stage1_judge"] == {"q1": ["a", "b", "c", "d"], "q2": ["b", "a", "c", "d"]}
    assert orders["E0_judge"] == {q: ["b", "a", "c", "d"] for q in first}
    assert trigger["stage1_judge"]["fallback_queries"] == 0
    assert trigger["stage1_judge"]["changed_queries"] == 1
    assert trigger["E0_judge"]["changed_queries"] == 2
    assert trigger["E0_judge"]["judged_calls_per_query"] == {"q1": 2, "q2": 2}
    report, _ = judge.evaluate_rankers(labels, rankers, orders)
    assert {n: r["pairwise"]["strict_correct"] for n, r in report["rankers"].items()} == {
        "E0": 0, "stage1": 1, "stage1_judge": 2, "E0_judge": 1}
    assert report["rankers"]["E0"]["list"] == {"n": 2, "preferred@1": 0., "preferred@3": .5,
        "preferred_mrr": .375, "mean_rank_preferred": 3., "mean_rank_other": 1.}
    assert report["rankers"]["stage1_judge"]["list"]["preferred_mrr"] == 1.
    assert report["rankers"]["stage1_judge"]["pairwise"]["both_directions_correct"] == 1
    assert report["contrasts"]["E0"]["stage1_judge"]["corrected"] == 2
    assert report["contrasts"]["stage1"]["stage1_judge"]["corrected"] == 1
    human, _ = judge.evaluate_rankers(labels, rankers, orders, human={"q1": ("b", "a")})
    assert human["rankers"]["E0"]["list"]["preferred@1"] == 1.
    assert human["rankers"]["stage1_judge"]["pairwise"]["reverse"] == 1
    rankers, orders, trigger = judge.l2_rankers(base, first, judged, top_k=3)
    assert trigger["E0_judge"]["fallback_queries"] == 2
    assert rankers["E0_judge"] == rankers["stage1_judge"] == first
    assert orders["E0_judge"] == orders["stage1"]
    with pytest.raises(ValueError, match="cover stage1"):
        judge.l2_rankers(base, first, judged, top_k=4)
    bad = {**judged, "q1": {**judged["q1"], "foreign": 4}}
    with pytest.raises(ValueError, match="saved pool"):
        judge.l2_rankers(base, first, bad, top_k=2)


def test_list_positions_break_ties_but_pairwise_does_not_and_missing_pair_excluded():
    labels = [{"source_query_id": "q", "pair_id": "pair", "source_group_id": "source", "direction": "q1",
               "official_label_available": True, "preferred_chunk_id": "a", "other_chunk_id": "b"},
              {"source_query_id": "missing", "pair_id": "other-pair", "source_group_id": "source", "direction": "q1",
               "official_label_available": True, "preferred_chunk_id": "a", "other_chunk_id": "b"}]
    base = {"q": {"a": 1., "b": 1.}, "missing": {"a": 1.}}
    rankers = {"E0": base, "stage1": base}
    orders = {name: {"q": ["a", "b"], "missing": ["a"]} for name in rankers}
    report, _ = judge.evaluate_rankers(labels, rankers, orders)
    assert report["rankers"]["E0"]["pairwise"]["model_tie"] == 1
    assert report["rankers"]["E0"]["list"]["preferred@1"] == 1.
    assert report["rankers"]["E0"]["list"]["n"] == 1
    orders["stage1"]["q"] = ["a", "a"]
    with pytest.raises(ValueError, match="population"):
        judge.evaluate_rankers(labels, rankers, orders)


def test_long_reason_is_accepted_after_manager_change():
    value = {"id": "i01", "score": 4, "reason": "word " * 40}
    assert judge.validate_response({"items": [value]}, 1) == [value]
