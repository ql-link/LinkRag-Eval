"""Execute the declared jobs from a prewritten config without historical caches.

The strict mode makes one HTTP request per unique input and keeps failures.
Prompt construction, response validation and all downstream evaluation remain
the existing project functions. This is an experiment driver, not a new ranker.
"""

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import httpx

from linkrag_eval.retrieval.learning_to_rank.llm_judge import (
    SCHEMA,
    cache_key,
    judge_items,
    plan_batches,
    prompt_for,
    read_rows,
    validate_response,
    write_json,
    write_rows,
)
from linkrag_eval.retrieval.learning_to_rank.llm_judge_local import (
    OpenAICompatRunner,
    _content,
)


def utcnow():
    return datetime.now(UTC).isoformat()


def progress(out, value):
    temporary = out / "progress.tmp"
    temporary.write_text(json.dumps(value, ensure_ascii=False) + "\n")
    temporary.replace(out / "progress.json")


class SingleRequestRunner(OpenAICompatRunner):
    """Use the existing HTTP payload and parser, with no fallback or retry."""

    def run(self, prompt, out):
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "judge", "schema": SCHEMA, "strict": True}},
            "chat_template_kwargs": {"enable_thinking": self.think},
        }
        url = self.endpoint.copy_with(path="/v1/chat/completions")
        with httpx.Client(timeout=self.timeout, trust_env=False,
                          transport=self._transport) as client:
            response = client.post(url, json=body)
        observed = {"http_status": response.status_code}
        try:
            envelope = response.json()
        except ValueError:
            envelope = {}
        if isinstance(envelope, dict):
            choices = envelope.get("choices")
            observed.update(usage=envelope.get("usage"), model=envelope.get("model"),
                            finish_reasons=[x.get("finish_reason") for x in
                                            (choices if isinstance(choices, list) else [])
                                            if isinstance(x, dict)])
        write_json(out / "provider-metadata.json", observed)
        return _content(response, "openai")


def single_pass(items, runner, out, *, workers, seed):
    out.mkdir(parents=True, exist_ok=False)
    started, started_at = time.perf_counter(), utcnow()
    metadata = runner.metadata
    unique = {cache_key(item, metadata): item for item in items}
    batches = plan_batches(list(unique.values()), batch_size=1, seed=seed)
    cache_out = out / "judge-cache"
    cache_out.mkdir()
    progress(out, {"status": "running", "completed": 0, "total": len(batches)})

    def execute(index, batch):
        folder = out / f"batch-{index:05d}"
        folder.mkdir()
        item = batch[0]
        key = cache_key(item, metadata)
        prompt = prompt_for(batch)
        (folder / "prompt.txt").write_text(prompt)
        write_json(folder / "schema.json", SCHEMA)
        write_rows(folder / "mapping.jsonl", [dict(metadata, id="i01", key=key,
                   source_query_id=item["source_query_id"], chunk_id=item["chunk_id"],
                   pair_id=item["pair_id"])])
        tick, request_started_at = time.perf_counter(), utcnow()
        error = None
        try:
            raw = runner.run(prompt, folder)
            write_json(folder / "out.json", raw)
            value = validate_response(raw, 1)[0]
        except (ValueError, TypeError, KeyError, OSError, RuntimeError, httpx.HTTPError) as exc:
            # No free-form network exception, endpoint credentials or server body is logged.
            error = type(exc).__name__
            value = {"score": None, "reason": "", "status": "unavailable"}
        write_json(folder / "metadata.json", dict(metadata,
                   started_at=request_started_at, completed_at=utcnow(),
                   wall_seconds=time.perf_counter() - tick, item_count=1,
                   failure_number=int(error is not None), error=error, request_attempts=1))
        row = dict(metadata, key=key, score=value["score"], reason=value["reason"],
                   status=value.get("status", "available"))
        write_rows(cache_out / f"batch-{index:05d}.jsonl", [row])
        return key, row

    cache = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(execute, i, batch) for i, batch in enumerate(batches, 1)]
        for future in as_completed(futures):
            key, row = future.result()
            cache[key] = row
            if len(cache) % 50 == 0 or len(cache) == len(batches):
                state = {"status": "running", "completed": len(cache), "total": len(batches),
                         "unavailable_unique": sum(x["status"] == "unavailable" for x in cache.values()),
                         "wall_seconds": time.perf_counter() - started}
                progress(out, state)
                print(json.dumps(state), flush=True)
    results = [dict(item, **cache[cache_key(item, metadata)]) for item in items]
    write_rows(out / "scores.jsonl", results)
    summary = dict(metadata, items=len(items), unique_keys=len(unique), cache_hits=0,
                   cache_misses=len(unique), duplicate_items=len(items) - len(unique),
                   planned_batches=len(batches), batch_count=len(batches), workers=workers,
                   batch_size=1, seed=seed, unavailable=sum(x["status"] == "unavailable" for x in results),
                   wall_seconds=time.perf_counter() - started, started_at=started_at,
                   completed_at=utcnow(), max_attempts_per_unique_input=1)
    write_json(out / "summary.json", summary)
    progress(out, {"status": "completed", "completed": len(cache), "total": len(batches)})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    root = Path(config["repository_root"])
    os.chdir(root)
    settings = config["judge_arguments"]
    if config["cache_policy"] != "fresh; no historical or cross-job caches":
        raise ValueError("This driver requires fresh, isolated jobs")
    with httpx.Client(timeout=15, trust_env=False) as client:
        response = client.get(settings["endpoint"].rstrip("/") + "/v1/models")
        response.raise_for_status()
        served = {x["id"] for x in response.json()["data"]}
    if config["model"]["served_name"] not in served:
        raise ValueError("Unexpected model served by endpoint")
    record = args.config.parent / "execution-start.json"
    write_json(record, {"started_at": utcnow(), "pid": os.getpid(), "config": str(args.config)})
    summaries = []
    for job in config["jobs"]:
        out = Path(job["output"])
        items = read_rows(job["input"])
        if len(items) != job["items"] or any(x["level"] != job["level"] for x in items):
            raise ValueError("Input count/level differs from frozen job")
        runner_type = SingleRequestRunner if config["single_attempt"] else OpenAICompatRunner
        runner = runner_type(settings["endpoint"], config["model"]["served_name"],
                             think=True, max_tokens=settings["max_tokens"],
                             num_ctx=settings["num_ctx"], timeout=settings["timeout_seconds"])
        print(json.dumps({"job": job["name"], "started_at": utcnow()}), flush=True)
        if config["single_attempt"]:
            summary = single_pass(items, runner, out, workers=settings["workers"],
                                  seed=settings["batch_shuffle_seed"])
        else:
            _, summary = judge_items(items, runner, out, metadata=runner.metadata, cache_dirs=(),
                                     batch_size=1, workers=settings["workers"],
                                     seed=settings["batch_shuffle_seed"])
        summaries.append(summary)
        print(json.dumps({"job": job["name"], "summary": summary}), flush=True)
    write_json(args.config.parent / "execution-finished.json",
               {"completed_at": utcnow(), "status": "completed", "summaries": summaries})


if __name__ == "__main__":
    main()
