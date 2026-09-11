"""Evaluate completed #15/#16 runs with the unchanged pilot CLI."""

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PILOT = Path("runs/post_recall/llm-judge-pilot-20260910")


def load(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def evaluate(folder, role, level, scores, top_k=None):
    command = [sys.executable, "scripts/llm_judge_pilot.py", f"evaluate-{level}",
               "--role", role, "--baseline", str(PILOT / f"baseline/{role}/scores.jsonl"),
               "--scores", str(scores), "--out", str(folder)]
    if level == "l2":
        command += ["--stage1", str(PILOT / f"items-stage1-top20/{role}/stage1-{role}.jsonl"),
                    "--top-k", str(top_k)]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    folder.with_suffix(".log").write_text(result.stdout + result.stderr)
    result.check_returncode()
    return command


def compact(path, level):
    result = load(path)
    report = {"source": str(path), "role": result["role"]}
    for population in ("official", "human_v5"):
        if population not in result:
            continue
        if level == "l1":
            report[population] = {name: result[population][name] for name in ("E0", "judge")}
        else:
            report[population] = result[population]["rankers"]
    return report


def score_repetition(old_path, new_path):
    previous, current = rows(old_path), rows(new_path)
    fields = ("source_query_id", "chunk_id", "query", "passage", "level")
    assert len(previous) == len(current)
    assert all(all(a[k] == b[k] for k in fields) for a, b in zip(previous, current, strict=True))
    transitions = Counter()
    for old, new in zip(previous, current, strict=True):
        if old["status"] != new["status"]:
            key = old["status"] + "_to_" + new["status"]
        elif old["status"] == "unavailable":
            key = "both_unavailable"
        else:
            key = "same_available_score" if old["score"] == new["score"] else "changed_available_score"
        transitions[key] += 1
    return {"old_first_scores": str(old_path), "new_scores": str(new_path),
            "rows": len(current), "scope_and_order_match": True, "transitions": dict(transitions),
            "note": "Compare score/status, not free-text reasons. A repetition on exposed data is not an independent test."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("8b", "confirmation"), required=True)
    args = parser.parse_args()
    folder = Path("runs/post_recall/open-judge-qwen3-8b-development-20260911" if args.kind == "8b"
                  else "runs/post_recall/open-judge-confirmation-20260911")
    config = load(folder / ("execution-config.json" if args.kind == "8b" else "frozen-config.json"))
    start, finish = (load(folder / name) for name in ("execution-start.json", "execution-finished.json"))
    assert finish["status"] == "completed"
    assert config["recorded_at"] < start["started_at"] < finish["completed_at"]
    checks, commands = [], []
    for job in config["jobs"]:
        original, saved = rows(Path(job["input"])), rows(Path(job["output"]) / "scores.jsonl")
        assert len(original) == len(saved) == job["items"]
        fields = ("source_query_id", "chunk_id", "pair_id", "query", "passage", "level")
        assert all(all(a[k] == b[k] for k in fields) for a, b in zip(original, saved, strict=True))
        summary = load(Path(job["output"]) / "summary.json")
        assert summary["model"] == config["model"]["served_name"] and summary["effort"] == "think"
        assert summary["cache_hits"] == 0
        assert summary["unique_keys"] == len({x["key"] for x in saved})
        assert summary["unavailable"] == sum(x["status"] == "unavailable" for x in saved)
        assert all((x["status"] == "available" and type(x["score"]) is int and 0 <= x["score"] <= 4)
                   or (x["status"] == "unavailable" and x["score"] is None) for x in saved)
        if config["single_attempt"]:
            batches = list(Path(job["output"]).glob("batch-*/metadata.json"))
            assert summary["batch_count"] == summary["unique_keys"] == len(batches)
            assert all(load(p)["request_attempts"] == 1 for p in batches)
            assert not list(Path(job["output"]).glob("batch-*-retry*"))
        checks.append({"job": job["name"], "items": len(saved), "scope_exact": True,
                       "cache_hits": 0, "unique_keys": summary["unique_keys"],
                       "unavailable": summary["unavailable"], "batches": summary["batch_count"]})

    role = "development" if args.kind == "8b" else "confirmation"
    if args.kind == "8b":
        (folder / "l1").mkdir()
        write(folder / "l1/results.json", load(Path(config["existing_l1_result"])))
        l2_scores = folder / "judge/scores.jsonl"
    else:
        commands.append(evaluate(folder / "l1", role, "l1", folder / "l1-judge/scores.jsonl"))
        l2_scores = folder / "l2-judge/scores.jsonl"
    for top_k in (10, 20):
        commands.append(evaluate(folder / f"l2-k{top_k}", role, "l2", l2_scores, top_k))
    results = {"l1": compact(folder / "l1/results.json", "l1"),
               **{f"l2-k{k}": compact(folder / f"l2-k{k}/results.json", "l2") for k in (10, 20)}}
    if args.kind == "confirmation":
        historical = Path("runs/post_recall/open-judge-confirmation-20260910")
        results["score_repetition"] = {
            "l1": score_repetition(PILOT / "l1-confirmation-judge-qwen3-14b-awq-think/scores.jsonl",
                                   folder / "l1-judge/scores.jsonl"),
            "l2": score_repetition(PILOT / "l2s-confirmation-judge-qwen3-14b-awq-think/scores.jsonl",
                                   l2_scores)}
        results["historical_qwen"] = {
            "l1-first": compact(historical / "l1-first-pass/results.json", "l1"),
            "l1-retry": compact(historical / "l1-retry/results.json", "l1"),
            **{f"l2-k{k}": compact(historical / f"l2-first-pass-k{k}/results.json", "l2") for k in (10, 20)}}
        results["gpt6_low_reference"] = {
            "l1": compact(PILOT / "l1-confirmation-eval/results.json", "l1"),
            **{f"l2-k{k}": compact(PILOT / f"l2s-confirmation-k{k}-v2/results.json", "l2") for k in (10, 20)}}
        for k in (10, 20):
            for baseline in ("E0", "stage1"):
                assert results[f"l2-k{k}"]["official"][baseline] == results[
                    "historical_qwen"][f"l2-k{k}"]["official"][baseline]
    write(folder / "comparison.json", results)
    write(folder / "validation.json", {"recorded_at": datetime.now(UTC).isoformat(),
          "configuration_written_before_execution": True, "commands": commands,
          "input_and_request_checks": checks, "status": "passed", "new_model_calls_in_evaluation": 0})
    print(json.dumps({"kind": args.kind, "status": "passed", "checks": checks}), flush=True)


if __name__ == "__main__":
    main()
