"""Run the existing judge CLI, preserving first attempts and raw retry evidence.

No inference is permitted until probe.py freeze has accepted real human reviews.
The stock CLI controls prompts, requests, caching, batching and retries; local
wrappers only record transport output. Primary analysis reads first attempts.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import time
from collections import Counter
from copy import copy
from urllib.parse import urlsplit

import httpx
from probe import (
    HERE,
    ROOT,
    approved_reviews,
    code_identity,
    digest,
    load_scenes,
    read_rows,
    scene_digest,
    utcnow,
    write_json,
    write_rows,
)

from linkrag_eval.retrieval.learning_to_rank.llm_judge import cache_key, validate_response


class RecordingTransport(httpx.BaseTransport):
    def __init__(self, out, inner=None):
        self.out = out
        self.inner = inner or httpx.HTTPTransport(retries=0)
        self.count = 0

    def handle_request(self, request):
        self.count += 1
        folder = self.out / f"http-{self.count:02d}"
        folder.mkdir(exist_ok=False)
        # Only the JSON body is saved: never headers or credential-bearing URLs.
        write_json(folder / "request.json", json.loads(request.read()))
        start = time.perf_counter()
        receipt = {"started_at": utcnow(), "http_status": None}
        try:
            response = self.inner.handle_request(request)
            data = response.read()
            receipt["http_status"] = response.status_code
            if response.is_success:
                (folder / "response-body.txt").write_bytes(data)
                try:
                    envelope = json.loads(data)
                    receipt["usage"] = envelope.get("usage") if isinstance(envelope, dict) else None
                except ValueError:
                    receipt["usage"] = None
            else:
                receipt["note"] = "Error body omitted to avoid echoing endpoint credentials."
            return response
        except Exception as exc:
            receipt["error_type"] = type(exc).__name__
            raise
        finally:
            receipt.update(completed_at=utcnow(), wall_seconds=time.perf_counter() - start)
            write_json(folder / "receipt.json", receipt)

    def close(self):
        self.inner.close()


def load_cli():
    spec = importlib.util.spec_from_file_location(
        "issue22_existing_judge_cli", ROOT / "scripts/llm_judge_pilot.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    base_openai, base_codex = cli.OpenAICompatRunner, cli.CodexRunner

    class RecordingOpenAI(base_openai):
        def run(self, prompt, out):
            # judge_items shares this runner across worker threads. Each call
            # needs its own recorder and HTTP client lifetime.
            local = copy(self)
            local._transport = RecordingTransport(out)
            return base_openai.run(local, prompt, out)

    class RecordingCodex(base_codex):
        def run(self, prompt, out):
            started = time.perf_counter()
            receipt = {
                "started_at": utcnow(),
                "subprocesses": 1,
                "exit_code": None,
                "provider_requests": None,
                "usage": None,
            }
            try:
                result = super().run(prompt, out)
                receipt["exit_code"] = 0
                return result
            except Exception as exc:
                receipt["error_type"] = type(exc).__name__
                raise
            finally:
                receipt.update(completed_at=utcnow(), wall_seconds=time.perf_counter() - started)
                write_json(out / "codex-process.json", receipt)

    cli.OpenAICompatRunner, cli.CodexRunner = RecordingOpenAI, RecordingCodex
    return cli


def extract_first_pass(items, metadata, raw):
    first = {}
    for folder in sorted(raw.glob("batch-*")):
        if not folder.is_dir() or re.fullmatch(r"batch-\d+", folder.name) is None:
            continue  # retries and splits are supplementary evidence only
        mapping = read_rows(folder / "mapping.jsonl") if (folder / "mapping.jsonl").exists() else []
        if len(mapping) != 1:
            raise ValueError("single-item batch required for this probe")
        key = mapping[0]["key"]
        if key in first:
            raise ValueError("multiple primary attempts for the same unique input")
        record = {
            "score": None,
            "reason": "",
            "status": "unavailable",
            "first_pass_batch": folder.name,
            "attempt_state": "interrupted_after_dispatch",
        }
        if (folder / "metadata.json").exists():
            batch_meta = json.loads((folder / "metadata.json").read_text())
            record["attempt_state"] = "first_attempt_failed"
            if not batch_meta.get("error"):
                values = validate_response(json.loads((folder / "out.json").read_text()), 1)
                record.update(
                    score=values[0]["score"],
                    reason=values[0]["reason"],
                    status="available",
                    attempt_state="first_attempt_succeeded",
                )
        first[key] = record
    scores = []
    for item in items:
        key = cache_key(item, metadata)
        record = first.get(
            key,
            {
                "score": None,
                "reason": "",
                "status": "unavailable",
                "first_pass_batch": None,
                "attempt_state": "not_dispatched",
            },
        )
        scores.append({**item, **metadata, "key": key, **record})
    return scores


def execute(model, endpoint=None, api_key_env=None, directory=HERE):
    config = json.loads((directory / "execution-config.json").read_text())
    scenes, _ = load_scenes(directory)
    reviews = approved_reviews(scenes, directory)
    if (
        config["status"] != "frozen_before_inference"
        or code_identity(directory) != config["code_files"]
    ):
        raise ValueError("frozen code changed; preserve evidence and resolve before inference")
    if (
        config["scene_digests"] != {s["version_id"]: scene_digest(s) for s in scenes}
        or digest(reviews) != config["review_decisions_digest"]
    ):
        raise ValueError("scenes or human decisions changed after freezing")
    items_path = directory / config["items_file"]
    items = read_rows(items_path)
    if digest(items) != config["items_digest"]:
        raise ValueError("frozen items changed")
    settings = config["models"][model]
    metadata = {
        "model": settings["model"],
        "effort": "think" if model == "qwen" else "low",
        "prompt_version": config["prompt_version"],
    }
    if model == "qwen":
        parsed = urlsplit(endpoint or "")
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or any((parsed.username, parsed.password, parsed.query, parsed.fragment))
        ):
            raise ValueError("plain server endpoint required; credentials only via --api-key-env")
    cli = load_cli()
    keys = {cache_key(item, metadata) for item in items}
    cache_files = [p for d in cli.RUN.rglob("judge-cache") for p in d.glob("*.jsonl")]
    for path in cache_files:
        if any(r.get("key") in keys and r.get("status") == "available" for r in read_rows(path)):
            raise ValueError(
                "historical cache matches these inputs; do not reuse it as a new first round"
            )
    out = directory / "inference" / model
    out.mkdir(parents=True, exist_ok=False)
    argv = [
        "judge",
        "--items",
        str(items_path),
        "--out",
        str(out / "raw"),
        "--runner",
        settings["runner"],
        "--model",
        settings["model"],
        "--batch-size",
        "1",
        "--workers",
        str(config["workers"][model]),
        "--seed",
        str(config["seed"]),
    ]
    if model == "qwen":
        argv += ["--endpoint", endpoint, "--think", "--max-tokens", "6144", "--num-ctx", "8192"]
        if api_key_env:
            argv += ["--api-key-env", api_key_env]
    else:
        argv += ["--effort", "low", "--isolated-state"]
    write_json(
        out / "invocation.json",
        {
            "argv": argv,
            "historical_cache_files_checked": len(cache_files),
            "historical_cache_matches": 0,
            "frozen_at": config["frozen_at"],
        },
    )
    started, started_at, failure = time.perf_counter(), utcnow(), None
    try:
        cli.main(argv)
    except BaseException as exc:
        failure = type(exc).__name__
        raise
    finally:
        raw = out / "raw"
        scores = extract_first_pass(items, metadata, raw)
        write_rows(out / "first-pass-scores.jsonl", scores)
        receipts = [json.loads(p.read_text()) for p in raw.glob("batch-*/http-*/receipt.json")]
        processes = [json.loads(p.read_text()) for p in raw.glob("batch-*/codex-process.json")]
        observed_usage = [r["usage"] for r in receipts if isinstance(r.get("usage"), dict)]
        tokens = {
            key: sum(u[key] for u in observed_usage if type(u.get(key)) is int)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        }
        stock = (
            json.loads((raw / "summary.json").read_text())
            if (raw / "summary.json").exists()
            else None
        )
        batch_dirs = [p for p in raw.glob("batch-*") if p.is_dir()]
        summary = {
            "status": "completed" if failure is None else "interrupted_or_failed",
            "error_type": failure,
            "started_at": started_at,
            "completed_at": utcnow(),
            "wall_seconds": time.perf_counter() - started,
            "logical_items": len(items),
            "unique_inputs": len(keys),
            "duplicate_items": len(items) - len(keys),
            "historical_cache_hits": 0,
            "first_attempt_batches": len(
                [p for p in batch_dirs if re.fullmatch(r"batch-\d+", p.name)]
            ),
            "retry_or_split_batches": len(
                [p for p in batch_dirs if re.fullmatch(r"batch-\d+", p.name) is None]
            ),
            "recorded_http_attempt_starts": len(list(raw.glob("batch-*/http-*/request.json"))),
            "completed_http_receipts": len(receipts),
            "codex_processes": len(processes),
            "observed_http_tokens": tokens if observed_usage else None,
            "http_receipts_without_usage": len(receipts) - len(observed_usage),
            "gpt_provider_tokens": None,
            "monetary_cost": None,
            "cost_note": "Missing usage/billing and provider-internal requests remain unknown; "
            "raw Codex stdout/stderr and Qwen envelopes are retained for later reconciliation.",
            "primary_availability": dict(Counter(r["status"] for r in scores)),
            "primary_attempt_states": dict(Counter(r["attempt_state"] for r in scores)),
            "stock_cli_summary_including_retries": stock,
        }
        write_json(out / "execution-summary.json", summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("qwen", "gpt"), required=True)
    parser.add_argument("--endpoint")
    parser.add_argument("--api-key-env")
    args = parser.parse_args()
    execute(args.model, args.endpoint, args.api_key_env)


if __name__ == "__main__":
    main()
