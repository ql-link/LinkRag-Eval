"""Fixed Test baseline and evaluation commands; inference requires committed configs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shlex
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from linkrag_eval.retrieval.learning_to_rank.llm_judge import (
    baseline_scores,
    evaluate_pairs,
    evaluate_rankers,
    judged_scores,
    l2_rankers,
    read_rows,
    score_maps,
    write_json,
    write_rows,
)
from linkrag_eval.retrieval.learning_to_rank.pair_statistics import comparison_table

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[2]


def read_config():
    return json.loads((FOLDER / "frozen-config.json").read_text())


def require_committed_configs():
    for path in (FOLDER / "frozen-config.json", FOLDER / "bge/execution-config.json"):
        saved = subprocess.run(
            ["git", "show", f"HEAD:{path.relative_to(ROOT)}"], cwd=ROOT,
            capture_output=True, check=False,
        )
        if saved.returncode or saved.stdout != path.read_bytes():
            raise RuntimeError("Issue #20 requires both frozen configs committed unchanged before inference")


def prepare_baseline():
    require_committed_configs()
    started, started_at = time.perf_counter(), datetime.now(UTC).isoformat()
    config = read_config()
    output = FOLDER / "baseline"
    if output.exists():
        raise FileExistsError(output)
    model = ROOT / config["baseline"]["path"]
    with model.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != config["baseline"]["sha256"]:
            raise ValueError("English baseline differs from frozen model")
    import lightgbm as lgb
    snapshot = Path(config["snapshot"])
    rows = baseline_scores(
        read_rows(snapshot / "prepared/test/queries.jsonl"),
        read_rows(snapshot / "candidates/test/inputs.jsonl"),
        lgb.Booster(model_file=str(model)),
    )
    output.mkdir()
    write_rows(output / "scores.jsonl", rows)
    write_json(output / "summary.json", {
        "status": "completed", "role": "test", "queries": len(rows),
        "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "started_at": started_at, "completed_at": datetime.now(UTC).isoformat(),
        "wall_seconds": time.perf_counter() - started,
        "timing_scope": "Model verification, loading, feature computation, prediction and score output",
        "model": config["baseline"], "source": str(snapshot),
        "scope": "Fixed baseline only; no method selection or per-query display",
    })
    print(json.dumps({"baseline_queries": len(rows)}))


def qwen_worker(code_commit):
    """Run once on the remote host; record completion even when the driver fails."""
    config = read_config()
    started = datetime.now(UTC).isoformat()
    write_json(FOLDER / "worker-start.json", {"started_at": started, "code_commit": code_commit})
    result = subprocess.run(
        [sys.executable, str(ROOT / config["experiment_driver"]),
         "--config", str(FOLDER / "frozen-config.json")], cwd=ROOT, check=False,
    )
    write_json(FOLDER / "process-exit.json", {
        "started_at": started, "completed_at": datetime.now(UTC).isoformat(),
        "code_commit": code_commit, "returncode": result.returncode,
        "status": "completed" if result.returncode == 0 else "failed_no_retry",
    })
    return result.returncode


def launch_qwen():
    require_committed_configs()
    config = read_config()
    server = config["server"]
    code_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    remote = Path(config["repository_root"]) / FOLDER.relative_to(ROOT)
    # Compare the deployed config to the committed local bytes before launching.
    # The detached worker and exclusive start records prevent accidental repeats.
    bootstrap = """import json,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
folder=Path(sys.argv[1])
expected=sys.stdin.buffer.read()
if (folder/'frozen-config.json').read_bytes()!=expected:
    raise RuntimeError('Remote configuration differs from committed local config')
with (folder/'launch.json').open('x') as record, (folder/'execution.log').open('x') as log:
    child=subprocess.Popen([sys.executable,str(folder/'workflow.py'),'qwen-worker',
                            '--code-commit',sys.argv[2]],stdin=subprocess.DEVNULL,
                           stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    data={'pid':child.pid,'started_at':datetime.now(timezone.utc).isoformat(),
          'code_commit':sys.argv[2],'scope':'Single remote worker; no automatic restart'}
    json.dump(data,record,indent=2)
print(json.dumps(data))
"""
    remote_command = shlex.join([config["execution"]["driver_python"], "-c", bootstrap,
                                 str(remote), code_commit])
    subprocess.run([
        "ssh", "-p", str(server["ssh_port"]), "-o", "BatchMode=yes", "-o", "ControlMaster=auto",
        "-o", "ControlPath=/tmp/linkrag-eval-seeta-%C", "-o", "ConnectTimeout=20",
        f"{server['ssh_user']}@{server['ssh_host']}", remote_command,
    ], input=(FOLDER / "frozen-config.json").read_bytes(), check=True)


def select_bge_scores(items, raw, config):
    expected = {(r["source_query_id"], r["chunk_id"]) for r in items}
    index = {(r["source_query_id"], r["chunk_id"]): r for r in raw}
    if len(index) != len(raw) or not expected <= index.keys():
        raise ValueError("BGE score identities differ from prepared items")
    selected = {}
    for qid, cid in expected:
        row = index[qid, cid]
        if (row["role"] != "test" or row["model"] != config["model"]["repository"]
                or row["revision"] != config["model"]["revision"]
                or row["status"] != "available"
                or type(row["score"]) not in (int, float) or not math.isfinite(row["score"])):
            raise ValueError("BGE model or continuous score differs from frozen contract")
        selected.setdefault(qid, {})[cid] = row["score"]
    return selected


def evaluate(arm):
    started, started_at = time.perf_counter(), datetime.now(UTC).isoformat()
    config = read_config()
    base = score_maps(read_rows(FOLDER / "baseline/scores.jsonl"))
    stage1 = score_maps(read_rows(FOLDER / "inputs/stage1-test.jsonl"))
    labels = read_rows(Path(config["snapshot"]) / "prepared/test/supervision.jsonl")
    populations = {
        "primary": [r for r in labels if not r["structural_conflict"]],
        "including_conflict": labels,
    }
    output = FOLDER / f"{arm}-evaluation"
    if output.exists():
        raise FileExistsError(output)
    bge = json.loads((FOLDER / "bge/execution-config.json").read_text())
    raw_bge = read_rows(FOLDER / "bge/scores.jsonl") if arm == "bge" else []
    if arm == "bge":
        union = read_rows(FOLDER / "bge/items.jsonl")
        if ({(r["source_query_id"], r["chunk_id"]) for r in raw_bge} !=
                {(r["source_query_id"], r["chunk_id"]) for r in union}
                or len(raw_bge) != bge["unique_role_query_passage_items"]):
            raise ValueError("BGE full output population differs")
    complete = {}
    for level in ("l1", "l2"):
        items = read_rows(FOLDER / f"inputs/{level}-test.jsonl")
        if arm == "qwen":
            raw = read_rows(FOLDER / f"{level}-judge/scores.jsonl")
            expected = {(r["source_query_id"], r["chunk_id"]) for r in items}
            actual = {(r["source_query_id"], r["chunk_id"]) for r in raw}
            if expected != actual or len(raw) != len(items):
                raise ValueError("Qwen score identities differ from prepared items")
            if any(r["model"] != config["model"]["served_name"] or
                   r["prompt_version"] != config["judge_arguments"]["prompt_version"] for r in raw):
                raise ValueError("Qwen model/prompt differs from frozen config")
            scores = judged_scores(raw)
        else:
            scores = select_bge_scores(items, raw_bge, bge)
        if level == "l2":
            rankers, orders, triggers = l2_rankers(base, stage1, scores, top_k=20)
        complete[level] = {}
        for population, supervision in populations.items():
            if level == "l1":
                report, per_query = evaluate_pairs(supervision, base, scores)
                pairs = [("judge", "E0")]
            else:
                report, per_query = evaluate_rankers(supervision, rankers, orders)
                pairs = [("stage1_judge", "stage1"), ("stage1_judge", "E0"), ("E0_judge", "E0")]
            expected_n = 2736 if population == "primary" else 2738
            if len(per_query) != expected_n:
                raise ValueError("Test evaluation denominator differs from frozen config")
            statistics = comparison_table(per_query, pairs, seed=20260910, repeats=2000)
            complete[level][population] = (report, per_query, statistics)
    output.mkdir()
    result = {"arm": arm, "role": "test", "K": 20, "populations": {}}
    for level, records in complete.items():
        result["populations"][level] = {}
        for population, (report, rows, statistics) in records.items():
            result["populations"][level][population] = {"metrics": report, "statistics": statistics}
            write_rows(output / f"{level}-{population}-per-query.jsonl", rows)
    result["l2_fallback_queries"] = triggers["stage1_judge"]["fallback_queries"]
    result.update(started_at=started_at, completed_at=datetime.now(UTC).isoformat(),
                  wall_seconds=time.perf_counter() - started,
                  timing_scope="Input loading, evaluation, source-group statistics and per-query output")
    result["limitations"] = [
        "Primary population excludes structural conflict; sensitivity includes it.",
        "L1 unavailable remains in accuracy denominator; paired CI/test uses jointly available rows.",
        "L2 retains unavailable judgments through whole-query fusion fallback.",
        "Source-group CI; directional sign test is not group/multiplicity adjusted.",
        "No full-pool relevance labels, answer evaluation or Test model selection.",
    ]
    write_json(output / "results.json", result)
    print(json.dumps({"arm": arm, "status": "evaluated", "output": str(output)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check-ready", "baseline", "qwen", "qwen-worker", "evaluate"))
    parser.add_argument("--arm", choices=("qwen", "bge"), default="qwen")
    parser.add_argument("--code-commit", help="Committed source revision for the remote worker")
    args = parser.parse_args()
    if args.command == "check-ready":
        require_committed_configs()
        print("Frozen configuration bytes are committed.")
    elif args.command == "baseline":
        prepare_baseline()
    elif args.command == "qwen":
        launch_qwen()
    elif args.command == "qwen-worker":
        if not args.code_commit:
            parser.error("the internal remote worker requires --code-commit")
        raise SystemExit(qwen_worker(args.code_commit))
    else:
        evaluate(args.arm)


if __name__ == "__main__":
    main()
