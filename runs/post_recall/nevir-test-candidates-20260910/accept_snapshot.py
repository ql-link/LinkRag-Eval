"""Validate the received Test snapshot; print aggregates only, never rescore models."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from linkrag_eval.retrieval.learning_to_rank.llm_judge import (
    baseline_order,
    read_rows,
    score_maps,
    stage1_scores,
)
from linkrag_eval.retrieval.learning_to_rank.nevir_evaluation import prepare_inputs

ROOT = Path(__file__).resolve().parents[3]
FOLDER = Path(__file__).resolve().parent
RUNTIME_KEYS = (
    "encoders", "route_depths", "route_thresholds", "fusion_weights", "rank_origin",
    "candidate_contract_version", "candidate_profile", "fusion_result_limit",
    "bm25_effective_text_weights", "user_id", "sparse_vector_name",
)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text())


def indexed(rows, key="source_query_id"):
    result = {row[key]: row for row in rows}
    require(len(result) == len(rows), f"duplicate {key}")
    return result


def request_summary(folder):
    events = read_rows(folder / "encoder-requests.jsonl")
    requests = Counter(row["route"] for row in events if row["event"] == "request")
    responses = Counter(
        f"{row['route']}:{row['http_status']}" for row in events if row["event"] == "response"
    )
    state = read_json(folder / "state.json")
    require(dict(requests) == state["encoder_request_counts"], "encoder request ledger differs")
    require(dict(responses) == state["encoder_response_counts"], "encoder response ledger differs")
    require(sum(requests.values()) == state["physical_encoder_attempts"], "attempt total differs")
    failed = [row for row in events if row["event"] == "response" and row["http_status"] >= 400]
    require(failed == state["http_failures"], "HTTP failure ledger differs")
    return {
        "status": state["status"],
        "last_resume_started_utc": state["started_utc"],
        "finished_utc": state["finished_utc"],
        "physical_encoder_attempts": sum(requests.values()),
        "encoder_request_counts": dict(requests),
        "encoder_response_counts": dict(responses),
        "recorded_http_failures": len(failed),
        "requests_without_recorded_response": {
            route: count - sum(n for key, n in responses.items() if key.startswith(route + ":"))
            for route, count in requests.items()
        },
        "limit": state["hard_limit"],
        "notes": "Cumulative attempts include resumptions; unmatched receipts are unknown outcomes.",
    }


def run(args):
    if args.out.exists():
        raise FileExistsError(args.out)
    started_utc, started = datetime.now(UTC).isoformat(), time.perf_counter()
    snapshot = args.snapshot.resolve()
    manifest = read_json(snapshot / "run.json")
    reference = read_json(
        ROOT / "runs/post_recall/nevir-ltr-validation-20260907/"
        "data-preparation/experiment/run.json"
    )["collection_runtime"]
    runtime = manifest["collection_runtime"]
    require(all(runtime[k] == reference[k] for k in RUNTIME_KEYS), "Train/confirmation runtime differs")
    require(manifest["identity"]["dataset_id"] == 995301, "wrong Test dataset")
    require(manifest["identity"]["qdrant_prefix"] == "eval_nevir_test_20260910", "wrong eval prefix")

    # Recreate preparation in a temporary directory and compare the four received files.
    # The existing preparer checks the fixed official source digest before parsing it.
    with tempfile.TemporaryDirectory(prefix="linkrag-test-prepare-check-") as temporary:
        rebuilt = Path(temporary) / "prepared-run"
        subprocess.run(
            [sys.executable, str(FOLDER / "prepare_official_test.py"),
             "--source", str(args.source), "--out", str(rebuilt)],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        for rel in ("corpus.jsonl", "passage-mapping.jsonl", "test/queries.jsonl", "test/supervision.jsonl"):
            require((rebuilt / "prepared" / rel).read_bytes() ==
                    (snapshot / "prepared" / rel).read_bytes(), f"prepared {rel} differs")

    queries = read_rows(snapshot / "prepared/test/queries.jsonl")
    labels = read_rows(snapshot / "prepared/test/supervision.jsonl")
    mapping = read_rows(snapshot / "prepared/passage-mapping.jsonl")
    corpus = indexed(read_rows(snapshot / "prepared/corpus.jsonl"), "source_passage_id")
    inputs = read_rows(snapshot / "candidates/test/inputs.jsonl")
    require(read_rows(snapshot / "candidates/test/queries.jsonl") == queries, "collector query order differs")
    require(len(queries) == len(labels) == len(inputs) == 2766, "Test query denominator differs")
    require(len(mapping) == len(corpus) == 2081, "Test corpus denominator differs")
    prepared = prepare_inputs(queries, labels, inputs, mapping, role="test")
    require(all(item["rank_input_complete"] for item in prepared), "candidate contract incomplete")
    for row in inputs:
        for candidate in row["candidate_rows"]:
            require(candidate["content"] == corpus[candidate["source_passage_id"]]["content"],
                    "candidate text differs from received Test corpus")
    coverage = indexed(read_rows(snapshot / "coverage/test.jsonl"))
    require(set(coverage) == {q["source_query_id"] for q in queries}, "coverage population differs")
    top20_covered, candidate_rows, l2_items = 0, 0, 0
    covered_pairs, primary_pairs, primary_groups = Counter(), Counter(), set()
    for item, row in zip(prepared, inputs, strict=True):
        qid = item["source_query_id"]
        require(qid == row["source_query_id"], "candidate order differs from preparation")
        pair_covered = item["coverage_state"] == "both"
        saved = coverage[qid]
        require(saved["pair_in_union"] == pair_covered, "saved coverage differs")
        require(saved["candidate_count"] == item["candidate_count"], "candidate count differs")
        candidate_rows += item["candidate_count"]
        l2_items += min(20, item["candidate_count"])
        if pair_covered:
            covered_pairs[item["pair_id"]] += 1
            if not item["structural_conflict"]:
                primary_pairs[item["pair_id"]] += 1
                primary_groups.add(item["source_group_id"])
        # Reconstruct only the existing fusion order needed for top20 coverage.
        # No trained ranker or judge is called, and no preference correctness is computed.
        fusion = score_maps(stage1_scores([{"source_query_id": qid, "query": item["query"]}], [row]))[qid]
        targets = {item["preferred_chunk_id"], item["other_chunk_id"]}
        top20_covered += targets <= set(baseline_order(fusion)[:20])
    summary = {
        "queries": len(queries), "pairs": len({r["pair_id"] for r in labels}),
        "source_groups": len({r["source_group_id"] for r in labels}),
        "corpus_passages": len(corpus), "candidate_rows": candidate_rows,
        "ready_queries": sum(r["rank_input_complete"] for r in prepared),
        "both_in_union": sum(covered_pairs.values()), "both_in_fusion_top20": top20_covered,
        "both_directions_covered_pairs": sum(n == 2 for n in covered_pairs.values()),
        "structural_conflict_queries": sum(r["structural_conflict"] for r in labels),
        "primary_covered_nonconflict_queries": sum(primary_pairs.values()),
        "primary_complete_pairs": sum(n == 2 for n in primary_pairs.values()),
        "primary_source_groups": len(primary_groups),
        "l2_logical_items_all_queries": l2_items,
        "route_empty_queries": {
            route: sum(r["route_status"][route] == "empty" for r in inputs)
            for route in ("dense", "sparse", "bm25")
        },
    }
    saved_summary = read_json(snapshot / "coverage/test-summary.json")
    require(summary["both_in_union"] == saved_summary["pair_in_union_queries"], "aggregate coverage differs")
    require(summary["both_directions_covered_pairs"] == saved_summary["paired_both_queries_covered"],
            "paired coverage differs")
    require(summary["route_empty_queries"] == saved_summary["route_empty_counts"], "empty routes differ")

    db_checks = {}
    for name, table in (("corpus", "eval_corpus_chunk"), ("bm25", "bm25_chunk_rows")):
        with sqlite3.connect(f"file:{snapshot}/storage/{name}.sqlite3?mode=ro&immutable=1", uri=True) as db:
            integrity = db.execute("PRAGMA integrity_check").fetchall()
            require(integrity == [("ok",)], f"{name} integrity check failed")
            rows = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            require(rows == 2081, f"{name} row count differs")
            db_checks[name] = {"integrity": "ok", "rows": rows, "access": "read_only_immutable"}
    test_texts = {r["content"] for r in corpus.values()}
    prior_texts = {
        split: {row[k] for row in read_rows(args.source.parent / f"{split}.jsonl") for k in ("doc1", "doc2")}
        for split in ("train", "validation")
    }
    overlap = {split: len(test_texts & texts) for split, texts in prior_texts.items()}
    overlap["either_prior_split"] = len(test_texts & set.union(*prior_texts.values()))
    result = {
        "status": "accepted", "started_utc": started_utc,
        "completed_utc": datetime.now(UTC).isoformat(),
        "wall_seconds": time.perf_counter() - started,
        "code_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "local_changes": "Test input validation role and this receiver; no model or retrieval changes",
        "snapshot": str(snapshot), "preparation_exact_files": 4,
        "runtime_matches_development_confirmation": list(RUNTIME_KEYS), "coverage": summary,
        "sqlite": db_checks, "exact_passage_overlap_retained": overlap,
        "historical_requests": {
            "ingestion": request_summary(snapshot / "ingestion"),
            "test": request_summary(snapshot / "candidates/test"),
        },
        "new_remote_requests": 0, "trained_rankers_scored": False, "judge_scored": False,
        "access": "machine_only; aggregate output; no query, passage or per-query score display",
        "limitations": [
            "Member Test evaluation already exists; this does not make Test globally unseen.",
            "Original logs retain interrupted requests without response receipts; outcomes are unknown.",
            "Remote Qdrant vectors are not included or needed for fixed-candidate offline evaluation.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(result, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=FOLDER / "snapshot")
    parser.add_argument("--source", type=Path, default=ROOT / "data/post_recall/nevir/test.jsonl")
    parser.add_argument("--out", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
