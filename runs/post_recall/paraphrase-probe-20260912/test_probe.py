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

META = {
    "model": "synthetic-test-only",
    "effort": "low",
    "prompt_version": "judge_prompt_v1",
    "generation": {"interface": "synthetic"},
}


class FakeRunner:
    def run(self, prompt, out):
        return {"items": [{"id": "i01", "score": 2, "reason": "synthetic"}]}


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


def fake_review(scene, original):
    return {
        "version_id": scene["version_id"],
        **probe.review_binding(scene, original),
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
    row = fake_review(scene, scene)
    probe.validate_review(row, scene, scene)
    changed = copy.deepcopy(scene)
    changed["paragraphs"][0] += " Additional condition."
    with pytest.raises(ValueError, match="digest mismatch"):
        probe.validate_review(row, changed, changed)
    with pytest.raises(ValueError, match="actual reviewer"):
        probe.validate_review({**row, "human_confirmed": False}, scene, scene)
    with pytest.raises(ValueError, match="all three"):
        probe.validate_review({**row, "equivalence_checked": False}, scene, scene)
    without_reference = {k: v for k, v in row.items() if not k.startswith("reference_original_")}
    with pytest.raises(ValueError, match="original reference mismatch"):
        probe.validate_review(without_reference, scene, scene)


def test_original_revision_requires_fresh_rewrite_reviews(copied):
    scenes, _ = probe.load_scenes(copied)
    originals = {s["source_scene_id"]: s for s in scenes if s["rewrite_type"] == "original"}
    submitted = [fake_review(s, originals[s["source_scene_id"]]) for s in scenes]
    initial_submission = copied / "synthetic-initial-review.jsonl"
    probe.write_rows(initial_submission, submitted)
    probe.receive(initial_submission, copied)
    assert len(probe.approved_reviews(scenes, copied)) == 36
    history = copied / "human-review.jsonl"
    initial_history = history.read_bytes()
    receipts = {p: p.read_bytes() for p in copied.glob("review-submissions/*/original.jsonl")}
    source = copied / "source/control-scenes.json"
    source_bytes = source.read_bytes()

    original = scenes[0]
    revised = {
        **original,
        "version_id": original["version_id"] + "-revision2",
        "revision": 2,
        "supersedes": original["version_id"],
        "paragraphs": [p.replace("boats", "cars") for p in original["paragraphs"]],
        "queries": [q.replace("boats", "cars") for q in original["queries"]],
    }
    with (copied / "scenes-original.jsonl").open("a") as stream:
        stream.write(json.dumps(revised) + "\n")
    revision_submission = copied / "synthetic-original-revision-review.jsonl"
    probe.write_rows(revision_submission, [fake_review(revised, revised)])
    probe.receive(revision_submission, copied)
    with pytest.raises(ValueError, match="2 versions need approval or revision"):
        probe.freeze(copied / "nonexistent-runtime.json", copied)
    assert not (copied / "frozen").exists()

    shutil.copyfile(probe.HERE / "review-template.html", copied / "review-template.html")
    probe.prepare(copied)
    template = probe.read_rows(copied / "human-review-template.jsonl")
    html = (copied / "review.html").read_text()
    payload = json.loads(
        html.split('<script id="scene-data" type="application/json">', 1)[1]
        .split("</script>", 1)[0]
    )
    for rows in (template, payload):
        for index, row in enumerate(rows[1:3], 1):
            assert row["input_digest"] == submitted[index]["input_digest"]
            assert row["reference_original_version_id"] == revised["version_id"]
            assert row["reference_original_digest"] == probe.scene_digest(revised)

    stale_submission = copied / "synthetic-stale-rewrite-review.jsonl"
    probe.write_rows(stale_submission, submitted[1:3])
    before_stale = history.read_bytes()
    with pytest.raises(ValueError, match="original reference mismatch"):
        probe.receive(stale_submission, copied)
    assert history.read_bytes() == before_stale

    fresh_submission = copied / "synthetic-fresh-rewrite-review.jsonl"
    probe.write_rows(fresh_submission, [fake_review(s, revised) for s in scenes[1:3]])
    assert probe.receive(fresh_submission, copied)["new_decisions"] == 2
    active, _ = probe.load_scenes(copied)
    approved = probe.approved_reviews(active, copied)
    assert len(approved) == 36
    assert all(r["reference_original_version_id"] == revised["version_id"] for r in approved[:3])
    assert history.read_bytes().startswith(initial_history)
    assert all(p.read_bytes() == data for p, data in receipts.items())
    assert source.read_bytes() == source_bytes


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


@pytest.mark.parametrize("keep_summary", [True, False], ids=["summary", "interrupted-mapping"])
def test_first_pass_uses_actual_generation_with_legacy_metadata(tmp_path, scenes, keep_summary):
    items = probe.build_items(scenes[:1])
    raw = tmp_path / "raw"
    actual = {**META, "codex_version": "synthetic", "runner": "fake", "endpoint": "local"}
    judge_items(items, FakeRunner(), raw, metadata=actual, batch_size=1, workers=1)
    if not keep_summary:
        (raw / "summary.json").unlink()
    legacy_meta = {key: value for key, value in META.items() if key != "generation"}
    first = extract_first_pass(items, legacy_meta, raw)
    assert all(row["attempt_state"] == "first_attempt_succeeded" for row in first)
    assert all(row["score"] == 2 for row in first)
    assert all(row["generation"] == actual["generation"] for row in first)
    assert all(all(row[key] == value for key, value in actual.items()) for row in first)
    assert all("items" not in row and "batch_count" not in row and "id" not in row for row in first)


@pytest.mark.parametrize("keep_summary", [True, False], ids=["summary", "interrupted-mapping"])
def test_first_pass_reads_pre_generation_artifacts(tmp_path, scenes, keep_summary):
    items = probe.build_items(scenes[:1])
    legacy_meta = {key: value for key, value in META.items() if key != "generation"}
    for index, item in enumerate(items, 1):
        folder = tmp_path / f"batch-{index:03d}"
        folder.mkdir()
        probe.write_rows(folder / "mapping.jsonl", [{
            **legacy_meta, "id": "i01", "key": cache_key(item, legacy_meta),
            "source_query_id": item["source_query_id"], "chunk_id": item["chunk_id"],
            "pair_id": item["pair_id"],
        }])
        probe.write_json(folder / "metadata.json", {**legacy_meta, "error": None})
        probe.write_json(folder / "out.json", FakeRunner().run("synthetic", folder))
    if keep_summary:
        probe.write_json(tmp_path / "summary.json", {**legacy_meta, "items": len(items)})
    first = extract_first_pass(items, legacy_meta, tmp_path)
    assert all(row["attempt_state"] == "first_attempt_succeeded" for row in first)
    assert all(row["score"] == 2 and "generation" not in row for row in first)
    assert [row["key"] for row in first] == [cache_key(item, legacy_meta) for item in items]


@pytest.mark.parametrize("field", ["model", "effort", "prompt_version"])
@pytest.mark.parametrize("source", ["summary", "mapping"])
def test_first_pass_rejects_mismatched_actual_metadata(tmp_path, scenes, field, source):
    actual = {**META, field: "different-run"}
    if source == "summary":
        probe.write_json(tmp_path / "summary.json", actual)
    else:
        folder = tmp_path / "batch-001"
        folder.mkdir()
        probe.write_rows(folder / "mapping.jsonl", [{**actual, "key": "unused"}])
    with pytest.raises(ValueError, match="actual judge metadata differs"):
        extract_first_pass(probe.build_items(scenes[:1]), META, tmp_path)


def test_missing_and_inflight_results_remain_distinct(tmp_path, scenes):
    items = probe.build_items(scenes[:1])
    folder = tmp_path / "batch-001"
    folder.mkdir()
    probe.write_rows(folder / "mapping.jsonl", [{"key": cache_key(items[0], META)}])
    rows = extract_first_pass(items, META, tmp_path)
    assert rows[0]["attempt_state"] == "interrupted_after_dispatch"
    assert all(r["attempt_state"] == "not_dispatched" for r in rows[1:])


def test_no_dispatch_falls_back_to_caller_metadata(tmp_path, scenes):
    rows = extract_first_pass(probe.build_items(scenes[:1]), META, tmp_path / "absent-raw")
    assert all(row["attempt_state"] == "not_dispatched" for row in rows)
    assert all(row["generation"] == META["generation"] for row in rows)


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


@pytest.fixture
def frozen_probe(copied, monkeypatch):
    """Freeze synthetic inputs and install a no-network judge CLI for execution checks."""
    scenes, _ = probe.load_scenes(copied)
    originals = {s["source_scene_id"]: s for s in scenes if s["rewrite_type"] == "original"}
    submission = copied / "synthetic-submission.jsonl"
    probe.write_rows(
        submission,
        [fake_review(s, originals[s["source_scene_id"]]) for s in scenes],
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

            judge_items(
                probe.read_rows(args["--items"]),
                FakeRunner(),
                args["--out"],
                metadata=meta,
                batch_size=1,
                workers=1,
            )

    config = json.loads((copied / "execution-config.json").read_text())
    items = probe.read_rows(copied / config["items_file"])
    monkeypatch.setattr(run_model, "load_cli", lambda: FakeCLI)
    return SimpleNamespace(
        directory=copied, items=items, cli=FakeCLI,
        metadata={**META, "model": config["models"]["qwen"]["model"], "effort": "think"},
    )


def test_full_synthetic_freeze_run_and_report(frozen_probe):
    """Exercise handoff end-to-end, with temporary self-declared test records only."""
    copied = frozen_probe.directory
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


@pytest.mark.parametrize("legacy", [True, False], ids=["legacy-key", "generation-key"])
@pytest.mark.parametrize("identities", ["absent", "different"])
def test_historical_cache_matches_content_without_sibling_mapping(frozen_probe, legacy, identities):
    metadata = dict(frozen_probe.metadata)
    if legacy:
        del metadata["generation"]
    else:
        metadata["generation"] = {"max_tokens": 2048, "think": True}
    item = {**frozen_probe.items[0], "source_query_id": "previous-query", "chunk_id": "previous-chunk"}
    record = {
        **metadata, "key": cache_key(item, metadata), "status": "available",
        "score": 2, "reason": "synthetic history",
    }
    if identities == "different":
        record.update(source_query_id=item["source_query_id"], chunk_id=item["chunk_id"])
    cache = frozen_probe.cli.RUN / "copied-cache-only/judge-cache"
    cache.mkdir(parents=True)
    probe.write_rows(cache / "cache.jsonl", [record])
    with pytest.raises(ValueError, match="historical cache matches these inputs"):
        run_model.execute("qwen", "http://synthetic.invalid", directory=frozen_probe.directory)
    assert not (frozen_probe.directory / "inference").exists()


@pytest.mark.parametrize("field", ["model", "effort", "prompt_version", "status", "passage"])
def test_historical_cache_does_not_block_other_contracts_or_inputs(frozen_probe, monkeypatch, field):
    metadata = dict(frozen_probe.metadata)
    item = dict(frozen_probe.items[0])
    if field in {"model", "effort", "prompt_version"}:
        metadata[field] = "different-run"
    elif field == "passage":
        item["passage"] = "Different synthetic evidence."
    record = {
        **metadata, "key": cache_key(item, metadata),
        "status": "unavailable" if field == "status" else "available",
        "score": None if field == "status" else 2, "reason": "synthetic history",
    }
    cache = frozen_probe.cli.RUN / "other-run/judge-cache"
    cache.mkdir(parents=True)
    probe.write_rows(cache / "cache.jsonl", [record])
    calls = []
    monkeypatch.setattr(frozen_probe.cli, "main", lambda argv: calls.append(argv))
    run_model.execute("qwen", "http://synthetic.invalid", directory=frozen_probe.directory)
    assert len(calls) == 1
    invocation = json.loads((frozen_probe.directory / "inference/qwen/invocation.json").read_text())
    assert invocation["historical_cache_files_checked"] == 1
