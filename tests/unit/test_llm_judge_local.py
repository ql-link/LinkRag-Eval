"""Local judge HTTP contracts and saved-output comparisons; no real judging."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from linkrag_eval.retrieval.learning_to_rank import llm_judge as judge
from linkrag_eval.retrieval.learning_to_rank.llm_judge_local import (
    OllamaRunner,
    OpenAICompatRunner,
    agreement_report,
)

VALUE = {"items": [{"id": "i01", "score": 4, "reason": "supported"}]}
ITEM = {"source_query_id": "q", "chunk_id": "a", "pair_id": "pair",
        "query": "Which door is open?", "passage": "Door A is open.", "level": "l1"}


def envelope(kind, content):
    message = {"content": content}
    return {"choices": [{"message": message}]} if kind == "openai" else {"message": message}


@pytest.mark.parametrize("kind,runner_type", [("openai", OpenAICompatRunner), ("ollama", OllamaRunner)])
def test_http_happy_path_and_shared_pipeline(kind, runner_type, tmp_path):
    prompt = judge.prompt_for([ITEM])
    def respond(request):
        assert request.method == "POST"
        assert request.url.path == ("/v1/chat/completions" if kind == "openai" else "/api/chat")
        assert "authorization" not in request.headers
        body = json.loads(request.content)
        assert body["model"] == "qwen3"
        assert body["messages"] == [{"role": "user", "content": prompt}]
        if kind == "openai":
            assert body["temperature"] == 0 and body["max_tokens"] == 1024
            assert body["chat_template_kwargs"] == {"enable_thinking": False}
            assert body["response_format"] == {"type": "json_schema", "json_schema": {
                "name": "judge", "schema": judge.SCHEMA, "strict": True}}
        else:
            assert body["stream"] is False and body["think"] is False
            assert body["format"] == judge.SCHEMA
            assert body["options"] == {"temperature": 0, "num_ctx": 4096}
        return httpx.Response(200, json=envelope(kind, json.dumps(VALUE)))
    runner = runner_type("http://localhost:8000/?private=query#fragment", "qwen3", num_ctx=4096,
                         transport=httpx.MockTransport(respond))
    assert runner.metadata == {"runner": kind, "endpoint": "localhost", "model": "qwen3",
                               "effort": "none", "prompt_version": judge.PROMPT_VERSION,
                               "codex_version": None}
    rows, summary = judge.judge_items([ITEM], runner, tmp_path / "run", metadata=runner.metadata)
    assert rows[0]["score"] == 4 and summary["batch_count"] == 1
    assert json.loads((tmp_path / "run/batch-001/out.json").read_text()) == VALUE
    assert "private=query" not in json.dumps(summary)


def test_openai_fallback_auth_and_extra_body(tmp_path):
    calls = []
    def respond(request):
        body = json.loads(request.content)
        calls.append(body)
        assert request.headers["authorization"] == "Bearer synthetic-test-token"
        assert body["max_tokens"] == 256 and body["top_p"] == .9
        assert body["chat_template_kwargs"] == {"enable_thinking": False, "custom": True}
        if len(calls) == 1:
            assert "response_format" in body
            return httpx.Response(400, json={"error": "response_format is unsupported"})
        assert "response_format" not in body
        return httpx.Response(200, json=envelope("openai", "<think>private reasoning\n</think>\n```json\n"
                                                + json.dumps(VALUE) + "\n```"))
    runner = OpenAICompatRunner("http://localhost", "qwen3", api_key="synthetic-test-token",
                               max_tokens=256, extra_body={"top_p": .9, "chat_template_kwargs": {
                                   "enable_thinking": True, "custom": True}},
                               transport=httpx.MockTransport(respond))
    assert runner.run("prompt", tmp_path) == VALUE and len(calls) == 2
    assert "synthetic-test-token" not in json.dumps(runner.metadata)


@pytest.mark.parametrize("kind,runner_type", [("openai", OpenAICompatRunner), ("ollama", OllamaRunner)])
def test_think_and_fence_stripping(kind, runner_type, tmp_path):
    content = "<think>first\nthought</think> <think>second</think>```JSON\n" + json.dumps(VALUE) + "\n```"
    runner = runner_type("http://localhost", "qwen3", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=envelope(kind, content))))
    assert runner.run("prompt", tmp_path) == VALUE


@pytest.mark.parametrize("kind,runner_type", [("openai", OpenAICompatRunner), ("ollama", OllamaRunner)])
def test_bad_json_uses_existing_retry_split_unavailable_path(kind, runner_type, tmp_path):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=envelope(kind, "not JSON"))
    runner = runner_type("http://localhost", "qwen3", transport=httpx.MockTransport(respond))
    rows, summary = judge.judge_items([ITEM], runner, tmp_path / "failed", metadata=runner.metadata)
    assert len(calls) == summary["batch_count"] == 3
    assert summary["unavailable"] == 1 and rows[0]["score"] is None
    error = json.loads((tmp_path / "failed/batch-001/metadata.json").read_text())["error"]
    assert error.startswith("JSONDecodeError:")


@pytest.mark.parametrize("status,message,expected_calls", [
    (400, "invalid model", 1), (401, "response_format rejected", 1),
    (400, "response_format unsupported", 2),
])
def test_fallback_is_limited_and_http_errors_are_sanitized(status, message, expected_calls, tmp_path):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(status, text=message + " synthetic-secret")
    runner = OpenAICompatRunner("http://localhost/?token=synthetic-secret", "qwen3",
                               transport=httpx.MockTransport(respond))
    with pytest.raises(RuntimeError, match=f"^judge HTTP status {status}$"):
        runner.run("prompt", tmp_path)
    assert len(calls) == expected_calls


def test_transport_error_and_empty_choices_use_pipeline_error_types(tmp_path):
    def fail(request):
        raise httpx.ReadTimeout("synthetic-secret", request=request)
    runner = OpenAICompatRunner("http://localhost", "qwen3", transport=httpx.MockTransport(fail))
    with pytest.raises(RuntimeError, match=r"^judge HTTP transport failed \(ReadTimeout\)$"):
        runner.run("prompt", tmp_path)
    runner = OpenAICompatRunner("http://localhost", "qwen3", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"choices": []})))
    with pytest.raises(ValueError, match="invalid judge response envelope"):
        runner.run("prompt", tmp_path)


def test_cache_key_distinguishes_local_from_codex(tmp_path, monkeypatch):
    meta = {"prompt_version": judge.PROMPT_VERSION, "model": "qwen3", "effort": "low", "codex_version": "fake"}
    monkeypatch.setattr(judge, "runtime_metadata", lambda *args: meta)
    codex = judge.CodexRunner()
    for runner_type in (OpenAICompatRunner, OllamaRunner):
        runner = runner_type("http://localhost", "qwen3")
        assert judge.cache_key(ITEM, runner.metadata) != judge.cache_key(ITEM, codex.metadata)


def load_script():
    path = Path(__file__).resolve().parents[2] / "scripts/llm_judge_pilot.py"
    spec = importlib.util.spec_from_file_location("judge_pilot_local_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scored(values):
    return [dict(ITEM, source_query_id=f"q{i // 2}", chunk_id=f"c{i}", score=value,
                 status="unavailable" if value is None else "available") for i, value in enumerate(values)]


def test_agreement_cli_ties_shared_ids_and_no_overwrite(tmp_path):
    script = load_script()
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    judge.write_rows(a / "scores.jsonl", scored([0, 1, 2, 3, 4, None, 4]))
    judge.write_rows(b / "scores.jsonl", list(reversed(scored([0, 2, 1, 3, 3, 4]))))
    output = tmp_path / "agreement.json"
    script.main(["agreement", "--a", str(a), "--b", str(b), "--output", str(output)])
    result = json.loads(output.read_text())
    assert result["n_shared"] == 6 and result["n_scored"] == 5
    assert result["exact_agreement"] == .4 and result["within_1_agreement"] == 1.
    # Centered average ranks: [-2, -1, 0, 1, 2] and [-2, 0, -1, 1.5, 1.5].
    assert result["spearman"] == pytest.approx(8.5 / (95 ** .5))
    assert result["kendall_tau"] == pytest.approx(7 / (90 ** .5))
    assert result["confusion_matrix"] == [[1, 0, 0, 0, 0], [0, 0, 1, 0, 0],
                                           [0, 1, 0, 0, 0], [0, 0, 0, 1, 0], [0, 0, 0, 1, 0]]
    assert result["n_shared_pairs"] == 3 and result["n_scored_pairs"] == 2
    assert result["pairwise_direction_agreement"] == 1.
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        script.main(["agreement", "--a", str(a), "--b", str(b), "--output", str(output)])
    assert output.read_bytes() == original


@pytest.mark.parametrize("a,b,expected", [([0, 4], [4, 0], 0.), ([2, 2], [3, 3], 1.),
                                        ([2, 2], [2, 3], 0.)])
def test_pair_direction_includes_ties(a, b, expected):
    result = agreement_report(scored(a), scored(b))
    assert result["n_scored_pairs"] == 1 and result["pairwise_direction_agreement"] == expected
    if a == [0, 4]:
        assert result["spearman"] == result["kendall_tau"] == -1.
    else:
        assert result["spearman"] is result["kendall_tau"] is None


@pytest.mark.parametrize("a,b", [([], []), ([None], [4]), ([2], [3])])
def test_agreement_undefined_statistics_are_json_null(a, b):
    result = agreement_report(scored(a), scored(b))
    assert result["spearman"] is result["kendall_tau"] is result["pairwise_direction_agreement"] is None
    json.dumps(result, allow_nan=False)


def test_agreement_rejects_duplicate_or_conflicting_items():
    rows = scored([1, 2])
    with pytest.raises(ValueError, match="duplicate"):
        agreement_report(rows + rows, rows)
    with pytest.raises(ValueError, match="conflicting"):
        agreement_report(rows, [dict(r, pair_id="different") for r in rows])


@pytest.mark.parametrize("kind,explicit_size", [("codex", None), ("ollama", None), ("openai", None),
                                              ("codex", 7), ("openai", 8)])
def test_judge_cli_defaults_and_explicit_batch_size(kind, explicit_size, tmp_path, monkeypatch, capsys):
    script = load_script()
    seen = {}
    class FakeRunner:
        def __init__(self, *args, **kwargs):
            seen.update(args=args, kwargs=kwargs)
            self.metadata = {"model": "fake", "effort": "low" if kind == "codex" else "none"}
    monkeypatch.setattr(script, {"codex": "CodexRunner", "ollama": "OllamaRunner",
                                "openai": "OpenAICompatRunner"}[kind], FakeRunner)
    monkeypatch.setattr(script, "RUN", tmp_path / "no-caches")
    def fake_judge(rows, runner, out, **kwargs):
        seen.update(run=kwargs)
        return [], {"unavailable": 0}
    monkeypatch.setattr(script, "judge_items", fake_judge)
    monkeypatch.setenv("EVAL_JUDGE_TEST_KEY", "synthetic-test-token")
    items = tmp_path / "items.jsonl"
    judge.write_rows(items, [ITEM])
    argv = ["judge", "--items", str(items), "--out", str(tmp_path / "out"), "--workers", "12"]
    if kind != "codex":
        argv += ["--runner", kind, "--endpoint", "http://localhost:8000", "--model", "qwen3"]
    if kind == "openai":
        argv += ["--api-key-env", "EVAL_JUDGE_TEST_KEY"]
    if explicit_size is not None:
        argv += ["--batch-size", str(explicit_size)]
    script.main(argv)
    assert seen["run"]["batch_size"] == (explicit_size or (40 if kind == "codex" else 1))
    assert seen["run"]["workers"] == 12
    if kind != "codex":
        assert seen["kwargs"]["num_ctx"] == 8192
    if kind == "openai":
        assert seen["kwargs"]["api_key"] == "synthetic-test-token"
    assert "synthetic-test-token" not in capsys.readouterr().out


def test_openai_think_mode_sets_label_and_budget(tmp_path):
    def handler(request):
        body = json.loads(request.content)
        assert body["chat_template_kwargs"]["enable_thinking"] is True
        assert body["max_tokens"] == 4096
        return httpx.Response(200, json=envelope("openai", "<think>x</think>" + json.dumps(VALUE)))
    runner = OpenAICompatRunner("http://localhost:8000", "qwen3", think=True,
                                transport=httpx.MockTransport(handler))
    assert runner.metadata["effort"] == "think"
    assert runner.run("prompt", tmp_path / "out.json") == VALUE
    plain = OpenAICompatRunner("http://localhost:8000", "qwen3", transport=httpx.MockTransport(handler))
    assert plain.metadata["effort"] == "none"
