"""Prepare the owner-fixed Test jobs from the accepted snapshot; no model calls."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from linkrag_eval.retrieval.learning_to_rank.llm_judge import (
    build_items,
    cache_key,
    read_rows,
    stage1_scores,
    write_json,
    write_rows,
)
from linkrag_eval.retrieval.learning_to_rank.llm_judge_local import OpenAICompatRunner

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[2]
RUNS = ROOT / "runs/post_recall"


def main():
    started = time.perf_counter()
    if any((FOLDER / name).exists() for name in ("inputs", "frozen-config.json", "bge")):
        raise FileExistsError("refusing to overwrite prepared Test jobs")
    accepted = json.loads((RUNS / "nevir-test-candidates-20260910/run.json").read_text())
    if accepted["status"] != "accepted":
        raise ValueError("Test snapshot must pass acceptance first")
    snapshot = Path(accepted["snapshot"])
    queries = read_rows(snapshot / "prepared/test/queries.jsonl")
    labels = read_rows(snapshot / "prepared/test/supervision.jsonl")
    candidates = read_rows(snapshot / "candidates/test/inputs.jsonl")
    fusion = stage1_scores(queries, candidates)
    # L1 uses these real fusion scores only to check pool identities. Its two
    # designated passages come from supervision, independently of fusion order.
    l1 = build_items(queries, labels, candidates, predictions=fusion, level="l1")
    l2 = build_items(queries, labels, candidates, stage1=fusion, level="l2", top_k=20)
    if len(l1) != 5476 or len(l2) != 55320:
        raise ValueError("Test item counts differ from accepted coverage")
    out = FOLDER / "inputs"
    out.mkdir()
    write_rows(out / "stage1-test.jsonl", fusion)
    write_rows(out / "l1-test.jsonl", l1)
    write_rows(out / "l2-test.jsonl", l2)

    old = json.loads((RUNS / "open-judge-confirmation-20260911/frozen-config.json").read_text())
    config = copy.deepcopy(old)
    code = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    config.update(
        record_kind="pre-inference fixed Test configuration",
        recorded_at=datetime.now(UTC).isoformat(), code_commit=code,
        application_source_changes=True, issue=20,
        purpose="Owner-fixed Qwen K20 Test evaluation; no selection on Test results",
        snapshot=str(snapshot), snapshot_acceptance=str(RUNS / "nevir-test-candidates-20260910/run.json"),
        historical_record="runs/post_recall/open-judge-confirmation-20260911/frozen-config.json",
        test_exposure="Issue #23 member E0/fusion/N8 aggregates already observed; no Qwen Test outputs yet",
        population={
            "all_queries": 2766, "both_covered": 2738,
            "primary": "official label available, both designated passages covered, no structural conflict",
            "primary_queries": 2736, "primary_source_groups": 699, "primary_complete_pairs": 1363,
            "sensitivity": "Also report all 2738 covered queries including the structural-conflict pair",
            "cross_split_duplicate_passages": "4 exact shared passages retained; no deletion",
        },
        statistics={
            "implementation": "linkrag_eval.retrieval.learning_to_rank.pair_statistics",
            "seed": 20260910, "repeats": 2000, "alpha": 0.05,
            "primary_contrast": "Qwen stage1_judge minus fixed fusion stage1",
            "sign_test": "directional exact test; no group or multiplicity correction",
        },
        inference_status="not_started",
        version_control_status="not_committed; issue #20 requires this config committed before inference",
    )
    model = ROOT / "models/english-baseline/model.txt"
    with model.open("rb") as stream:
        config["baseline"] = {"path": str(model.relative_to(ROOT)),
                              "sha256": hashlib.file_digest(stream, "sha256").hexdigest()}
    config["evaluation"]["K"] = [20]
    config["evaluation"]["auxiliary"] = ["E0", "stage1", "E0_judge", "BGE same K20"]
    config["constraints"] = [
        "English NevIR fixed Test candidates; no recall, training, prompt or label changes",
        "Exactly the declared L1 and K20 L2 jobs; no K/trigger/model selection on Test",
        "Fresh independent jobs; one request per unique input within each job, no retries",
        "Member Test results retained separately; never overwrite the Issue #23 folder",
        "Only aggregate results are displayed; raw Test rows remain local experiment artifacts",
    ]
    config["server"]["launch_script"] = "runs/post_recall/open-judge-confirmation-20260911/serve.sh"
    config["jobs"] = []
    runner = OpenAICompatRunner(
        config["judge_arguments"]["endpoint"], config["model"]["served_name"],
        think=True, max_tokens=6144, num_ctx=8192,
    )  # Construct metadata only; this does not connect to a server.
    for level, items in (("l1", l1), ("l2", l2)):
        config["jobs"].append({
            "name": f"{level}-test", "level": level,
            "input": str((out / f"{level}-test.jsonl").relative_to(ROOT)),
            "items": len(items), "queries": len({r["source_query_id"] for r in items}),
            "unique_requests": len({cache_key(r, runner.metadata) for r in items}),
            "output": str((FOLDER / f"{level}-judge").relative_to(ROOT)),
        })

    bge_root = FOLDER / "bge"
    bge_root.mkdir()
    union = {}
    for level, items in (("l1", l1), ("l2", l2)):
        for item in items:
            key = item["source_query_id"], item["chunk_id"]
            row = union.setdefault(key, dict(item, role="test", levels=[]))
            if row["query"] != item["query"] or row["passage"] != item["passage"]:
                raise ValueError("L1/L2 text differs for the same item")
            row["levels"].append(level)
    write_rows(bge_root / "items.jsonl", list(union.values()))
    bge = json.loads((RUNS / "open-judge-bge-reranker-v2-m3-20260911/execution-config.json").read_text())
    bge.update(
        recorded_at=config["recorded_at"], issue=20, code_commit=code,
        purpose="Fixed BGE Test reference, same previously selected model and runtime",
        unique_role_query_passage_items=len(union),
        inputs={"test": {"l1": config["jobs"][0]["input"], "l2": config["jobs"][1]["input"],
                         "l1_items": len(l1), "l2_items": len(l2)}},
        data_use=config["test_exposure"], constraints=config["constraints"],
    )
    bge["evaluation"]["l1"] = "Raw continuous logits; official Test primary/sensitivity populations"
    bge["constraints"] = list(config["constraints"])
    bge["constraints"][2] = "One fresh score per unique Test query/passage item; the L1/L2 union shares that score"
    bge["evaluation"]["l2_K"] = [20]
    bge["runtime"]["schedule"] = "Run after Qwen Test completes, with the existing runtime contract"
    write_json(bge_root / "execution-config.json", bge)
    config["bge_config"] = str((bge_root / "execution-config.json").relative_to(ROOT))
    config["configuration_completed_at"] = datetime.now(UTC).isoformat()
    write_json(FOLDER / "frozen-config.json", config)
    result = {
        "status": "prepared_not_scored", "completed_at": datetime.now(UTC).isoformat(),
        "wall_seconds": time.perf_counter() - started, "code_revision": code,
        "jobs": config["jobs"], "bge_items": len(union),
        "new_remote_requests": 0, "trained_ranker_predictions": 0,
        "fusion": "Existing fixed score reconstructed solely for selection; no accuracy computed",
    }
    write_json(FOLDER / "preparation.json", result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
