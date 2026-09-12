"""Synthetic checks only; no human decisions or real model calls are generated."""

import copy
import json
import shutil
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace

import httpx
import probe
import pytest
import run_model
from run_model import RecordingTransport, extract_first_pass

from linkrag_eval.retrieval.learning_to_rank.llm_judge import (
    cache_key,
    judge_items,
    prompt_for,
)

META = {"model": "synthetic-test-only", "effort": "low", "prompt_version": "judge_prompt_v1"}


@pytest.fixture
def scenes(copied):
    return probe.load_scenes(copied)[0]


@pytest.fixture
def copied(tmp_path):
    """Create unrelated synthetic inputs so a clean clone needs no research data."""
    sources, versions = [], []
    for index in range(12):
        sid = f"synthetic-only-{index}"
        name, other = f"PersonAlpha{index}", f"PersonBeta{index}"
        paragraphs = [
            f"{name} builds boats. {name} cannot run. {other} can run.",
            f"{name} builds boats. {other} cannot run. {name} can run.",
        ]
        queries = ["Who builds boats but cannot run?", "Who builds boats and can run?"]
        sources.append(
            {
                "probe_id": sid,
                "paragraphs": paragraphs,
                "queries": queries,
                "intended_entity_preferences": [0, 1],
            }
        )
        core = {
            "source_scene_id": sid,
            "category": "synthetic_test_only",
            "content_family": f"synthetic-family-{index}",
            "language": "en",
            "revision": 1,
            "supersedes": None,
            "expected_preferences": [0, 1],
            "paragraphs": paragraphs,
            "queries": queries,
        }
        renamed = [p.replace(name, f"PersonGamma{index}") for p in paragraphs]
        for kind in probe.TYPES:
            row = {**core, "version_id": f"{sid}--{kind}-v1", "rewrite_type": kind}
            if kind == "synonym":
                row["paragraphs"] = [p.replace("builds", "constructs") for p in paragraphs]
                row["queries"] = [q.replace("builds", "constructs") for q in queries]
            elif kind == "entity_rename":
                row.update(paragraphs=renamed, entity_mapping={name: f"PersonGamma{index}"})
            versions.append(row)
    (tmp_path / "source").mkdir()
    probe.write_json(tmp_path / "source/control-scenes.json", sources)
    probe.write_rows(
        tmp_path / "scenes-original.jsonl", [s for s in versions if s["rewrite_type"] == "original"]
    )
    probe.write_rows(
        tmp_path / "scenes-paraphrased.jsonl",
        [s for s in versions if s["rewrite_type"] != "original"],
    )
    (tmp_path / "human-review.jsonl").touch()
    return tmp_path


def test_prepare_refreshes_blank_template_without_replacing_history(copied):
    shutil.copyfile(probe.HERE / "review-template.html", copied / "review-template.html")
    probe.prepare(copied)
    path = copied / "scenes-paraphrased.jsonl"
    rows = probe.read_rows(path)
    newer = {
        **rows[0],
        "version_id": rows[0]["version_id"] + "-revision2",
        "revision": 2,
        "supersedes": rows[0]["version_id"],
    }
    path.unlink()
    probe.write_rows(path, [*rows, newer])
    history = copied / "human-review.jsonl"
    original_history = history.read_bytes()
    probe.prepare(copied)
    template = probe.read_rows(copied / "human-review-template.jsonl")
    assert newer["version_id"] in {r["version_id"] for r in template}
    assert rows[0]["version_id"] not in {r["version_id"] for r in template}
    assert history.read_bytes() == original_history


def fake_scores(items, outcomes=None):
    outcomes = outcomes or {}
    rows = []
    for item in items:
        status = outcomes.get(item["source_query_id"], "strict")
        target = item["expected"]
        score = 4 if target else 1
        if status == "reverse":
            score = 1 if target else 4
        elif status == "tie":
            score = 2
        elif status == "unavailable" and target:
            score = None
        rows.append(
            {
                **item,
                **META,
                "score": score,
                "reason": "synthetic test only",
                "status": "unavailable" if score is None else "available",
            }
        )
    return rows


def test_exact_scene_scope_and_no_label_prompt(scenes):
    items = probe.build_items(scenes)
    assert len(items) == 144
    assert len({r["source_query_id"] for r in items}) == 72
    assert Counter(r["version_id"] for r in items) == Counter({s["version_id"]: 4 for s in scenes})
    for item in items:
        prompt = prompt_for([item])
        assert prompt.count("ITEM id=") == 1
        assert item["query"] in prompt and item["passage"] in prompt
        assert "expected_preferences" not in prompt and "expected_doc_id" not in prompt
        assert item["version_id"] not in prompt and item["source_scene_id"] not in prompt
        assert item["probe_set"] == "english"


def test_originals_and_name_only_variant_preserve_intended_scope(scenes):
    original = {s["source_scene_id"]: s for s in scenes if s["rewrite_type"] == "original"}
    for s in scenes:
        if s["rewrite_type"] != "entity_rename":
            continue
        old = original[s["source_scene_id"]]
        assert s["queries"] == old["queries"]
        for a, b in zip(old["paragraphs"], s["paragraphs"], strict=True):
            for before, after in s["entity_mapping"].items():
                a = a.replace(before, after)
            assert a == b


def test_all_wrong_is_consistent_but_never_correct(scenes):
    items = probe.build_items(scenes)
    scores = fake_scores(items, {r["source_query_id"]: "reverse" for r in items})
    result = probe.summarize(scenes, items, scores)
    assert all(r["strict_accuracy"] == 0 for r in result["by_type"].values())
    for c in result["consistency"].values():
        assert c["strict_direction_agreement"] == 1
        assert c["both_reverse"] == 24
        assert c["both_correct"] == 0


def test_tie_unavailable_denominators(scenes):
    items = probe.build_items(scenes)
    original, synonym, renamed = scenes[:3]
    outcomes = {
        original["version_id"] + "--q0": "tie",
        synonym["version_id"] + "--q0": "tie",
        renamed["version_id"] + "--q0": "reverse",
        synonym["version_id"] + "--q1": "unavailable",
    }
    result = probe.summarize(scenes, items, fake_scores(items, outcomes))
    a = result["by_type"]["synonym"]
    assert (a["n_queries"], a["strict"], a["tie"], a["unavailable"]) == (24, 22, 1, 1)
    assert a["strict_accuracy"] == 22 / 24
    c = result["consistency"]["synonym"]
    assert (c["jointly_available"], c["excluded_unavailable"], c["both_tie"]) == (23, 1, 1)
    assert c["strict_non_tie_denominator"] == 22
    assert result["consistency"]["entity_rename"]["one_side_tie"] == 1


@pytest.mark.parametrize("corrupt", ["duplicate", "missing", "text", "wrong_score", "wrong_type"])
def test_reject_bad_score_inputs(scenes, corrupt):
    items = probe.build_items(scenes)
    scores = fake_scores(items)
    if corrupt == "duplicate":
        scores.append(scores[0])
    elif corrupt == "missing":
        scores.pop()
    elif corrupt == "text":
        scores[0]["passage"] += " Changed."
    elif corrupt == "wrong_type":
        scores[0]["score"] = True
    else:
        scores[0]["score"] = 9
    with pytest.raises(ValueError):
        probe.summarize(scenes, items, scores)


def test_no_human_approvals_cannot_freeze(copied):
    with pytest.raises(ValueError, match="human review incomplete"):
        probe.freeze(copied / "nonexistent-runtime.json", copied)
    assert not (copied / "execution-config.json").exists()
    assert not (copied / "frozen").exists()


def test_stale_and_unconfirmed_review_rejected(scenes):
    scene = scenes[0]
    row = {
        "input_digest": probe.scene_digest(scene),
        "status": "approved",
        "reviewer": "SYNTHETIC TEST ONLY",
        "reviewed_at": "2026-09-12",
        "reason": "test",
        "assistance": "test fixture",
        "human_confirmed": True,
        "conditions_checked": True,
        "preferences_checked": True,
        "equivalence_checked": True,
    }
    probe.validate_review(row, scene)
    changed = copy.deepcopy(scene)
    changed["paragraphs"][0] += " Additional condition."
    with pytest.raises(ValueError, match="digest mismatch"):
        probe.validate_review(row, changed)
    with pytest.raises(ValueError, match="actual reviewer"):
        probe.validate_review({**row, "human_confirmed": False}, scene)
    with pytest.raises(ValueError, match="all three"):
        probe.validate_review({**row, "equivalence_checked": False}, scene)


def test_first_failure_never_replaced_by_successful_retry(tmp_path, scenes):
    items = probe.build_items(scenes[:1])

    class FakeRunner:
        calls = 0

        def run(self, prompt, out):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("synthetic first failure")
            return {"items": [{"id": "i01", "score": 4, "reason": "synthetic retry"}]}

    final, summary = judge_items(
        items, FakeRunner(), tmp_path / "raw", metadata=META, batch_size=1, workers=1
    )
    first = extract_first_pass(items, META, tmp_path / "raw")
    assert summary["batch_count"] == 5
    assert all(r["status"] == "available" for r in final)
    assert sum(r["status"] == "unavailable" for r in first) == 1
    assert sum(r["attempt_state"] == "first_attempt_failed" for r in first) == 1


def test_missing_and_inflight_results_remain_distinct(tmp_path, scenes):
    items = probe.build_items(scenes[:1])
    folder = tmp_path / "batch-001"
    folder.mkdir()
    probe.write_rows(folder / "mapping.jsonl", [{"key": cache_key(items[0], META)}])
    rows = extract_first_pass(items, META, tmp_path)
    assert rows[0]["attempt_state"] == "interrupted_after_dispatch"
    assert all(r["attempt_state"] == "not_dispatched" for r in rows[1:])


def test_transport_records_usage_without_authorization_header(tmp_path):
    inner = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"choices": [], "usage": {"total_tokens": 12}})
    )
    transport = RecordingTransport(tmp_path, inner=inner)
    with httpx.Client(
        transport=transport, headers={"Authorization": "Bearer FAKE_SECRET"}
    ) as client:
        response = client.post(
            "http://synthetic.invalid/v1/chat/completions", json={"model": "fake"}
        )
    assert response.status_code == 200
    receipt = json.loads((tmp_path / "http-01/receipt.json").read_text())
    assert receipt["usage"]["total_tokens"] == 12
    assert "FAKE_SECRET" not in "".join(p.read_text() for p in tmp_path.rglob("*") if p.is_file())


def test_source_corruption_is_rejected(copied):
    path = copied / "scenes-original.jsonl"
    rows = probe.read_rows(path)
    rows[0]["queries"][0] = "A different query?"
    path.unlink()
    probe.write_rows(path, rows)
    with pytest.raises(ValueError, match="differs from the supplied source"):
        probe.load_scenes(copied)


def test_parallel_requests_keep_independent_recorders(tmp_path, monkeypatch):
    cli = run_model.load_cli()
    barrier = Barrier(2)
    monkeypatch.setattr(run_model, "RecordingTransport", lambda out: SimpleNamespace(out=out))

    def simultaneous_run(self, prompt, out):
        barrier.wait(timeout=5)
        assert self._transport.out == out
        return out

    monkeypatch.setattr(cli.OpenAICompatRunner.__mro__[1], "run", simultaneous_run)
    runner = cli.OpenAICompatRunner("http://synthetic.invalid", "fake")
    paths = [tmp_path / "batch-001", tmp_path / "batch-002"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda out: runner.run("test", out), paths)) == paths
    assert runner._transport is None


def test_evaluate_rejects_changed_frozen_scene(copied):
    scenes, _ = probe.load_scenes(copied)
    items = probe.build_items(scenes)
    probe.write_json(
        copied / "execution-config.json",
        {
            "scene_digests": {s["version_id"]: probe.scene_digest(s) for s in scenes},
            "items_file": "frozen/items.jsonl",
            "items_digest": probe.digest(items),
        },
    )
    (copied / "frozen").mkdir()
    scenes[0]["expected_preferences"] = [1, 0]
    probe.write_rows(copied / "frozen/scenes.jsonl", scenes)
    probe.write_rows(copied / "frozen/items.jsonl", items)
    with pytest.raises(ValueError, match="frozen scenes changed"):
        probe.evaluate(copied)
    assert not (copied / "report.md").exists()


def test_full_synthetic_freeze_run_and_report(copied, monkeypatch):
    """Exercise handoff end-to-end, with temporary self-declared test records only."""
    scenes, _ = probe.load_scenes(copied)
    submission = copied / "synthetic-submission.jsonl"
    probe.write_rows(
        submission,
        [
            {
                "version_id": s["version_id"],
                "input_digest": probe.scene_digest(s),
                "status": "approved",
                "reviewer": "SYNTHETIC TEST FIXTURE — NOT A PERSON",
                "reviewed_at": "2026-09-12",
                "reason": "synthetic control, not a semantic judgment",
                "assistance": "test only",
                "human_confirmed": True,
                "conditions_checked": True,
                "preferences_checked": True,
                "equivalence_checked": True,
            }
            for s in scenes
        ],
    )
    assert probe.receive(submission, copied)["new_decisions"] == 36
    monkeypatch.setattr(probe, "code_identity", lambda directory: {"test": "synthetic"})
    monkeypatch.setattr(run_model, "code_identity", lambda directory: {"test": "synthetic"})
    monkeypatch.setattr(probe.subprocess, "check_output", lambda *a, **kw: "synthetic-test-version")
    runtime = copied / "runtime.json"
    probe.write_json(
        runtime,
        {
            "qwen_revision": probe.QWEN_REVISION,
            "qwen_server_environment": "synthetic",
            "qwen_deployment_evidence": "synthetic",
            "gpu": "none — synthetic",
            "gpt_access": "none — synthetic",
            "operator_confirmed": True,
        },
    )
    probe.freeze(runtime, copied)

    class FakeCLI:
        RUN = copied / "empty-historical-cache"

        @staticmethod
        def main(argv):
            args = {argv[i]: argv[i + 1] for i in range(len(argv) - 1) if argv[i].startswith("--")}
            model = args["--model"]
            meta = {**META, "model": model, "effort": "think" if "Qwen" in model else "low"}

            class Runner:
                def run(self, prompt, out):
                    return {"items": [{"id": "i01", "score": 2, "reason": "synthetic"}]}

            judge_items(
                probe.read_rows(args["--items"]),
                Runner(),
                args["--out"],
                metadata=meta,
                batch_size=1,
                workers=1,
            )

    monkeypatch.setattr(run_model, "load_cli", lambda: FakeCLI)
    run_model.execute("qwen", "http://synthetic.invalid", directory=copied)
    run_model.execute("gpt", directory=copied)
    probe.evaluate(copied)
    result = json.loads((copied / "results.json").read_text())
    assert set(result["models"]) == {"qwen", "gpt"}
    for model in result["models"].values():
        assert all(c["tie"] == 24 for c in model["by_type"].values())
        assert all(c["both_tie"] == 24 for c in model["consistency"].values())
        assert model["execution"]["recorded_http_attempt_starts"] == 0
    assert (copied / "report.md").exists()
    with pytest.raises(FileExistsError):
        probe.evaluate(copied)
