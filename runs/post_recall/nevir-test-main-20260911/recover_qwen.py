"""Recover the interrupted fixed Test job without repeating any started input."""

from __future__ import annotations

import argparse
import importlib.util
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import httpx

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[2]
spec = importlib.util.spec_from_file_location(
    "frozen_driver", ROOT / "runs/post_recall/open-judge-selection-20260911/run_frozen.py",
)
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def check_row(row, metadata):
    if any(row.get(k) != v for k, v in metadata.items()):
        raise ValueError("Cached model metadata differs")
    if (row.get("status") not in {"available", "unavailable"}
            or (row["status"] == "unavailable" and row.get("score") is not None)
            or (row["status"] == "available" and
                (type(row.get("score")) is not int or not 0 <= row["score"] <= 4))):
        raise ValueError("Invalid cached availability or score")


def inspect_original(items, original, metadata, seed):
    unique = {driver.cache_key(item, metadata): item for item in items}
    batches = driver.plan_batches(list(unique.values()), batch_size=1, seed=seed)
    completed, interrupted, pending = [], [], []
    for index, batch in enumerate(batches, 1):
        item = batch[0]
        key = driver.cache_key(item, metadata)
        folder = original / f"batch-{index:05d}"
        cache = original / "judge-cache" / f"batch-{index:05d}.jsonl"
        record = {"index": index, "key": key, "item": item}
        if not folder.exists():
            if cache.exists():
                raise ValueError("Cache without original request directory")
            pending.append(record)
            continue
        mapping = driver.read_rows(folder / "mapping.jsonl")
        if (len(mapping) != 1 or mapping[0]["key"] != key
                or (folder / "prompt.txt").read_text() != driver.prompt_for(batch)
                or json.loads((folder / "schema.json").read_text()) != driver.SCHEMA):
            raise ValueError("Original request differs from the fixed plan")
        if not cache.exists():
            interrupted.append(record)
            continue
        rows = driver.read_rows(cache)
        if len(rows) != 1 or rows[0]["key"] != key:
            raise ValueError("Original cache identity differs")
        check_row(rows[0], metadata)
        receipt = json.loads((folder / "metadata.json").read_text())
        if receipt["request_attempts"] != 1:
            raise ValueError("Original request was not single-attempt")
        completed.append(key)
    if len(list((original / "judge-cache").glob("*.jsonl"))) != len(completed):
        raise ValueError("Unexpected original cache files")
    if len(list(original.glob("batch-*"))) != len(completed) + len(interrupted):
        raise ValueError("Unexpected original request directories")
    return completed, interrupted, pending


def continue_unstarted(pending, runner, original, output, *, workers):
    """Use original batch indices/order and the unchanged single-HTTP runner."""
    for record in pending:
        if (original / f"batch-{record['index']:05d}").exists():
            raise ValueError("A continuation input already has an original request")
        if driver.cache_key(record["item"], runner.metadata) != record["key"]:
            raise ValueError("Continuation key differs from the fixed input")
    if len({r["key"] for r in pending}) != len(pending):
        raise ValueError("Duplicate continuation input")
    output.mkdir(exist_ok=False)
    cache_out = output / "judge-cache"
    cache_out.mkdir()
    started = time.perf_counter()
    started_at = datetime.now(UTC).isoformat()
    driver.write_json(output / "execution-start.json", {
        "started_at": started_at, "planned_requests": len(pending),
        "scope": "Only never-started original batches; no retries or order changes",
    })

    def execute(record):
        folder = output / f"batch-{record['index']:05d}"
        folder.mkdir()
        item, key = record["item"], record["key"]
        prompt = driver.prompt_for([item])
        (folder / "prompt.txt").write_text(prompt)
        driver.write_json(folder / "schema.json", driver.SCHEMA)
        driver.write_rows(folder / "mapping.jsonl", [dict(
            runner.metadata, id="i01", key=key, source_query_id=item["source_query_id"],
            chunk_id=item["chunk_id"], pair_id=item["pair_id"],
        )])
        tick, request_started_at = time.perf_counter(), datetime.now(UTC).isoformat()
        error = None
        try:
            raw = runner.run(prompt, folder)
            driver.write_json(folder / "out.json", raw)
            value = driver.validate_response(raw, 1)[0]
        except (ValueError, TypeError, KeyError, OSError, RuntimeError, httpx.HTTPError) as exc:
            error = type(exc).__name__
            value = {"score": None, "reason": "", "status": "unavailable"}
        driver.write_json(folder / "metadata.json", dict(
            runner.metadata, started_at=request_started_at,
            completed_at=datetime.now(UTC).isoformat(),
            wall_seconds=time.perf_counter() - tick, item_count=1,
            failure_number=int(error is not None), error=error, request_attempts=1,
        ))
        row = dict(runner.metadata, key=key, score=value["score"], reason=value["reason"],
                   status=value.get("status", "available"))
        driver.write_rows(cache_out / f"batch-{record['index']:05d}.jsonl", [row])
        return row

    rows = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(execute, record) for record in pending]
        for future in as_completed(futures):
            rows.append(future.result())
            if len(rows) % 25 == 0 or len(rows) == len(pending):
                state = {"status": "running", "completed": len(rows), "total": len(pending),
                         "unavailable": sum(r["status"] == "unavailable" for r in rows)}
                driver.progress(output, state)
                print(json.dumps(state), flush=True)
    summary = {"status": "completed", "items": len(rows), "started_at": started_at,
               "completed_at": datetime.now(UTC).isoformat(),
               "wall_seconds": time.perf_counter() - started,
               "unavailable": sum(r["status"] == "unavailable" for r in rows),
               "request_attempts_per_input": 1}
    driver.write_json(output / "summary.json", summary)
    driver.progress(output, {"status": "completed", "completed": len(rows), "total": len(pending)})
    return summary


def assemble(items, original, continuation, interrupted, metadata):
    cache = {}
    for folder, provenance in [(original, "original_receipt"), (continuation, "continuation_receipt")]:
        for path in sorted((folder / "judge-cache").glob("*.jsonl")):
            rows = driver.read_rows(path)
            if len(rows) != 1 or rows[0]["key"] in cache:
                raise ValueError("Duplicate or invalid result across execution segments")
            row = rows[0]
            check_row(row, metadata)
            cache[row["key"]] = dict(row, recovery_provenance=provenance)
    for record in interrupted:
        if record["key"] in cache:
            raise ValueError("Interrupted input was repeated or already has a result")
        cache[record["key"]] = dict(
            metadata, key=record["key"], score=None, reason="", status="unavailable",
            recovery_provenance="interrupted_without_receipt",
        )
    expected = {driver.cache_key(item, metadata) for item in items}
    if set(cache) != expected:
        raise ValueError("Recovered output does not cover exactly the fixed population")
    return [dict(item, **cache[driver.cache_key(item, metadata)]) for item in items]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["audit", "run", "assemble"])
    args = parser.parse_args()
    config = json.loads((FOLDER / "frozen-config.json").read_text())
    recovery = json.loads((FOLDER / "recovery-config.json").read_text())
    opts = config["judge_arguments"]
    runner = driver.SingleRequestRunner(
        opts["endpoint"], config["model"]["served_name"], think=opts["think"],
        max_tokens=opts["max_tokens"], num_ctx=opts["num_ctx"], timeout=opts["timeout_seconds"],
    )
    original = FOLDER / "l2-judge"
    continuation = FOLDER / recovery["continuation_directory"]
    plan = FOLDER / recovery["plan_directory"]
    items = driver.read_rows(FOLDER / "inputs/l2-test.jsonl")
    if args.phase != "audit":
        audit = json.loads((plan / "audit.json").read_text())
        if audit["configuration"] != config or audit["recovery_configuration"] != recovery:
            raise ValueError("Configuration changed after recovery audit")
    if args.phase == "audit":
        if plan.exists():
            raise FileExistsError("Recovery plan already exists")
        completed, interrupted, pending = inspect_original(
            items, original, runner.metadata, opts["batch_shuffle_seed"],
        )
        counts = {"completed": len(completed), "interrupted": len(interrupted),
                  "pending": len(pending), "logical_items": len(items)}
        if counts != recovery["expected_counts"]:
            raise ValueError("Recovery inventory differs from the recorded incident")
        plan.mkdir()
        driver.write_rows(plan / "pending.jsonl", pending)
        driver.write_rows(plan / "interrupted.jsonl", interrupted)
        driver.write_json(plan / "audit.json", dict(
            counts, audited_at=datetime.now(UTC).isoformat(), configuration=config,
            recovery_configuration=recovery,
        ))
        print(json.dumps(counts))
    elif args.phase == "run":
        with httpx.Client(timeout=15, trust_env=False) as client:
            response = client.get(opts["endpoint"].rstrip("/") + "/v1/models")
            response.raise_for_status()
            if config["model"]["served_name"] not in {r["id"] for r in response.json()["data"]}:
                raise ValueError("Unexpected served model")
        pending = driver.read_rows(plan / "pending.jsonl")
        if len(pending) != recovery["expected_counts"]["pending"]:
            raise ValueError("Pending population differs")
        continue_unstarted(pending, runner, original, continuation, workers=opts["workers"])
    else:
        if json.loads((continuation / "summary.json").read_text())["status"] != "completed":
            raise ValueError("Continuation has not completed")
        rows = assemble(items, original, continuation,
                        driver.read_rows(plan / "interrupted.jsonl"), runner.metadata)
        driver.write_rows(original / "scores.jsonl", rows)
        driver.write_json(original / "recovery-summary.json", {
            "status": "assembled_after_interruption", "items": len(rows),
            "unique_inputs": len({r["key"] for r in rows}),
            "unavailable": sum(r["status"] == "unavailable" for r in rows),
            "interrupted_unique_inputs": recovery["expected_counts"]["interrupted"],
            "continued_unique_inputs": recovery["expected_counts"]["pending"],
            "original_exit_status": "not_recorded_due_to_shutdown", "issue": recovery["issue"],
            "completed_at": datetime.now(UTC).isoformat(),
        })
        print(json.dumps({"assembled_items": len(rows)}))


if __name__ == "__main__":
    main()
