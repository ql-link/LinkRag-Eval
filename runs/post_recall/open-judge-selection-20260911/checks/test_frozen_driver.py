"""Offline acceptance for fresh jobs and a single HTTP attempt per unique input."""

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from linkrag_eval.retrieval.learning_to_rank import llm_judge as judge


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DRIVER_PATH = Path(__file__).resolve().parents[1] / "run_frozen.py"
REPO = Path(__file__).resolve().parents[4]


@pytest.fixture
def driver():
    return load_module(DRIVER_PATH, "frozen_driver_acceptance")


@pytest.fixture(autouse=True)
def reject_real_http(monkeypatch):
    def reject(self, request):
        raise AssertionError(f"Unexpected real HTTP request: {request.method}")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reject)


def item(qid="q1", cid="a", passage="Supported passage.", level="l1"):
    return {
        "source_query_id": qid,
        "chunk_id": cid,
        "pair_id": "HIDDEN_PAIR_" + qid,
        "query": "Which passage supports the claim?",
        "passage": passage,
        "level": level,
        "preferred_chunk_id": "HIDDEN_GOLD_LABEL",
        "source_group_id": "HIDDEN_SOURCE_GROUP",
        "model": None,
        "effort": None,
        "codex_version": None,
        "prompt_version": judge.PROMPT_VERSION,
    }


def envelope(score=4, *, content=None, finish_reason="stop"):
    if content is None:
        content = json.dumps({"items": [{"id": "i01", "score": score, "reason": "evidence"}]})
    return {
        "model": "fake-qwen",
        "choices": [{"message": {"content": content}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 17, "completion_tokens": 9, "total_tokens": 26},
    }


def read_json(path):
    return json.loads(path.read_text())


@pytest.mark.parametrize("level", ["l1", "l2"])
def test_single_pass_deduplicates_without_label_leak_and_preserves_evaluation_denominators(
        driver, tmp_path, monkeypatch, level):
    items = [
        item(qid=qid, cid=cid, level=level, passage=passage)
        for qid in ("q1", "q2", "q3")
        for cid, passage in (
            ("a", "Supported passage."),
            ("b", "Truncated passage." if qid != "q3" else "Unrelated passage."),
        )
    ]
    prompts = {judge.prompt_for([row]) for row in items}
    calls = []

    def respond(request):
        assert request.method == "POST"
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        calls.append(body)
        assert body["messages"] == [{"role": "user", "content": body["messages"][0]["content"]}]
        assert body["messages"][0]["content"] in prompts
        assert "HIDDEN_" not in json.dumps(body)
        assert body["temperature"] == 0 and body["max_tokens"] == 512
        assert body["chat_template_kwargs"] == {"enable_thinking": True}
        assert body["response_format"]["json_schema"]["schema"] == judge.SCHEMA
        if "Truncated passage." in body["messages"][0]["content"]:
            result = envelope(finish_reason="length")
            result["choices"][0]["message"]["content"] = None
        else:
            score = 0 if "Unrelated passage." in body["messages"][0]["content"] else 4
            result = envelope(score, content="<think>private</think>```json\n" + json.dumps({
                "items": [{"id": "i01", "score": score, "reason": "evidence"}],
            }) + "\n```")
        return httpx.Response(200, json=result)

    runner = driver.SingleRequestRunner(
        "http://judge.invalid:8000", "fake-qwen", think=True, max_tokens=512,
        transport=httpx.MockTransport(respond),
    )
    out = tmp_path / "scores"
    summary = driver.single_pass(items, runner, out, workers=3, seed=20260910)
    saved = judge.read_rows(out / "scores.jsonl")
    assert len(calls) == len({json.dumps(call) for call in calls}) == 3
    assert summary["items"] == len(saved) == 6
    assert summary["unique_keys"] == summary["batch_count"] == summary["cache_misses"] == 3
    assert summary["duplicate_items"] == 3 and summary["cache_hits"] == 0
    assert summary["max_attempts_per_unique_input"] == 1
    assert summary["unavailable"] == 2
    assert [(r["source_query_id"], r["chunk_id"]) for r in saved] == [
        (r["source_query_id"], r["chunk_id"]) for r in items]
    assert all(row["level"] == level and row["model"] == "fake-qwen" for row in saved)
    assert judge.judged_scores(saved) == {
        "q1": {"a": 4, "b": None}, "q2": {"a": 4, "b": None}, "q3": {"a": 4, "b": 0},
    }
    batch_dirs = sorted(out.glob("batch-*"))
    assert len(batch_dirs) == 3
    assert all(read_json(folder / "metadata.json")["request_attempts"] == 1 for folder in batch_dirs)
    assert sorted(read_json(folder / "provider-metadata.json")["finish_reasons"][0]
                  for folder in batch_dirs) == ["length", "stop", "stop"]
    assert all(read_json(folder / "provider-metadata.json")["usage"]["total_tokens"] == 26
               for folder in batch_dirs)
    with pytest.raises(FileExistsError):
        driver.single_pass(items, runner, out, workers=1, seed=20260910)
    assert len(calls) == 3

    # Exercise the real evaluation entry points with synthetic confirmation labels.
    pilot = load_module(REPO / "scripts/llm_judge_pilot.py", "frozen_pilot_acceptance")
    labels = tmp_path / "supervision.jsonl"
    judge.write_rows(labels, [{
        "source_query_id": qid, "source_group_id": "group", "pair_id": qid,
        "direction": "q1", "official_label_available": True,
        "preferred_chunk_id": "a", "other_chunk_id": "b",
    } for qid in ("q1", "q2", "q3")])
    monkeypatch.setattr(pilot, "role_paths", lambda role: {"supervision": labels})
    baseline = tmp_path / "baseline.jsonl"
    judge.write_rows(baseline, [{"source_query_id": qid, "scores": [
        {"chunk_id": "a", "score": 1}, {"chunk_id": "b", "score": 2},
    ]} for qid in ("q1", "q2", "q3")])
    args = SimpleNamespace(role="confirmation", baseline=baseline, stage1=baseline,
                           scores=out / "scores.jsonl", top_k=2, out=tmp_path / "evaluation")
    (pilot.evaluate if level == "l1" else pilot.evaluate_l2)(args)
    report = read_json(args.out / "results.json")
    metric = (report["official"]["judge"] if level == "l1" else
              report["official"]["rankers"]["stage1_judge"]["pairwise"])
    assert metric["n"] == 3 and metric["strict_correct"] == 1
    assert metric["strict_accuracy"] == 1 / 3
    if level == "l1":
        assert metric["unavailable"] == 2
        assert report["status"] == "completed_with_unavailable"
    else:
        assert report["trigger"]["stage1_judge"]["fallback_queries"] == 2
        assert report["status"] == "completed_with_fallback"


@pytest.mark.parametrize("failure", ["schema-rejected", "overload", "non-json", "invalid-score", "timeout"])
def test_single_http_failure_has_no_fallback_or_retry(driver, tmp_path, failure):
    calls = []

    def respond(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("SYNTHETIC_PRIVATE_ERROR", request=request)
        if failure == "schema-rejected":
            return httpx.Response(400, text="response_format unsupported SYNTHETIC_PRIVATE_ERROR")
        if failure == "overload":
            return httpx.Response(429, text="SYNTHETIC_PRIVATE_ERROR")
        if failure == "non-json":
            return httpx.Response(200, text="SYNTHETIC_PRIVATE_ERROR")
        return httpx.Response(200, json=envelope(score=5))

    runner = driver.SingleRequestRunner(
        "http://judge.invalid", "fake-qwen", transport=httpx.MockTransport(respond),
    )
    out = tmp_path / "run"
    summary = driver.single_pass([item()], runner, out, workers=1, seed=1)
    assert len(calls) == summary["batch_count"] == summary["unavailable"] == 1
    row = judge.read_rows(out / "scores.jsonl")[0]
    assert row["score"] is None and row["status"] == "unavailable"
    metadata = read_json(out / "batch-00001/metadata.json")
    assert metadata["request_attempts"] == metadata["failure_number"] == 1
    assert metadata["error"]
    assert "SYNTHETIC_PRIVATE_ERROR" not in json.dumps(metadata)
    if failure != "timeout":
        provider = read_json(out / "batch-00001/provider-metadata.json")
        assert provider["http_status"] in {200, 400, 429}
        assert "SYNTHETIC_PRIVATE_ERROR" not in json.dumps(provider)


def test_malformed_choices_retains_http_metadata_before_parser_failure(driver, tmp_path):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"model": "fake-qwen", "choices": None,
                                         "usage": {"total_tokens": 7}})

    runner = driver.SingleRequestRunner(
        "http://judge.invalid", "fake-qwen", transport=httpx.MockTransport(respond),
    )
    summary = driver.single_pass([item()], runner, tmp_path / "run", workers=1, seed=1)
    assert len(calls) == 1 and summary["unavailable"] == 1
    provider = read_json(tmp_path / "run/batch-00001/provider-metadata.json")
    assert provider["http_status"] == 200 and provider["usage"] == {"total_tokens": 7}
    assert provider["finish_reasons"] == []


@pytest.mark.parametrize("single_attempt,fail,attempts", [(True, False, 1), (False, False, 1), (False, True, 3)])
def test_main_uses_fresh_independent_jobs_and_bounded_development_attempts(
        driver, tmp_path, monkeypatch, single_attempt, fail, attempts):
    calls, judge_kwargs = [], []

    def respond(request):
        calls.append(request)
        if request.method == "GET":
            assert request.url.path == "/v1/models"
            return httpx.Response(200, json={"data": [{"id": "fake-qwen"}]})
        assert request.method == "POST" and request.url.path == "/v1/chat/completions"
        return httpx.Response(200, json=envelope(content="malformed" if fail else None))

    original_client, original_judge = httpx.Client, driver.judge_items
    transport = httpx.MockTransport(respond)

    def client(*args, **kwargs):
        return original_client(*args, **dict(kwargs, transport=transport))

    def judge_spy(*args, **kwargs):
        judge_kwargs.append(kwargs)
        return original_judge(*args, **kwargs)

    monkeypatch.setattr(driver.httpx, "Client", client)
    monkeypatch.setattr(driver, "judge_items", judge_spy)
    monkeypatch.chdir(tmp_path)
    jobs = []
    for level in ("l1", "l2"):
        source = tmp_path / f"{level}.jsonl"
        judge.write_rows(source, [item(level=level)])
        jobs.append({"name": level, "input": str(source), "output": str(tmp_path / level),
                     "items": 1, "level": level})
    # A matching old score must not be read by either mode or shared across jobs.
    old = tmp_path / "historical/judge-cache"
    old.mkdir(parents=True)
    metadata = driver.OpenAICompatRunner("http://judge.invalid", "fake-qwen", think=True).metadata
    judge.write_rows(old / "cache.jsonl", [{
        **metadata, "key": judge.cache_key(item(), metadata), "score": 0,
        "reason": "historical score must not be used", "status": "available",
    }])
    config = tmp_path / "frozen-config.json"
    judge.write_json(config, {
        "repository_root": str(tmp_path), "cache_policy": "fresh; no historical or cross-job caches",
        "single_attempt": single_attempt, "model": {"served_name": "fake-qwen"}, "jobs": jobs,
        "judge_arguments": {"endpoint": "http://judge.invalid", "max_tokens": 512,
                            "num_ctx": 8192, "timeout_seconds": 2, "workers": 1,
                            "batch_shuffle_seed": 20260910},
    })
    monkeypatch.setattr(sys, "argv", [str(DRIVER_PATH), "--config", str(config)])
    driver.main()
    assert len([request for request in calls if request.method == "GET"]) == 1
    assert len([request for request in calls if request.method == "POST"]) == 2 * attempts
    assert len(judge_kwargs) == (0 if single_attempt else 2)
    assert all(kwargs["cache_dirs"] == () and kwargs["batch_size"] == 1 for kwargs in judge_kwargs)
    for job in jobs:
        out = Path(job["output"])
        summary = read_json(out / "summary.json")
        assert summary["cache_hits"] == 0 and summary["cache_misses"] == 1
        assert summary["batch_count"] == attempts and summary["unavailable"] == int(fail)
        assert judge.read_rows(out / "scores.jsonl")[0]["score"] == (None if fail else 4)
    assert read_json(tmp_path / "execution-finished.json")["status"] == "completed"
