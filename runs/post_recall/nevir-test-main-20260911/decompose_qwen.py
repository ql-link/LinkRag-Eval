"""Describe saved Qwen K20 decisions; no inference, ranking changes or text output."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[2]
OUTPUT = FOLDER / "qwen-decision-decomposition.json"
BRANCHES = (
    "qwen_different_scores", "qwen_tie_fusion", "preferred_only_in_window",
    "other_only_in_window", "both_outside_window", "whole_query_fallback",
)
OUTCOMES = ("strict_correct", "reverse", "model_tie")


def read_rows(path):
    with path.open() as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def indexed(rows):
    result = {}
    for row in rows:
        key = row["source_query_id"]
        if key in result:
            raise ValueError("duplicate query identifier")
        result[key] = row
    return result


def relation(a, b):
    return "strict_correct" if a > b else "reverse" if a < b else "model_tie"


def classify(stage1, judged, preferred, other, *, top_k=20):
    """First differing key in the actual fallback/window/Qwen/fusion ordering."""
    if preferred == other or not {preferred, other} <= stage1.keys():
        raise ValueError("designated pair missing or identical")
    if type(top_k) is not int or top_k < 1 or any(not math.isfinite(v) for v in stage1.values()):
        raise ValueError("invalid window or fusion score")
    top = set(sorted(stage1, key=lambda cid: (-stage1[cid], cid))[:top_k])
    if set(judged) != top:
        raise ValueError("saved judgments must cover exactly the fusion window")
    if any(v is not None and (type(v) is not int or not 0 <= v <= 4)
           for v in judged.values()):
        raise ValueError("invalid Qwen score")
    fusion = relation(stage1[preferred], stage1[other])
    fallback = any(v is None for v in judged.values())
    p_in, o_in = preferred in top, other in top
    if fallback:
        branch, final = "whole_query_fallback", fusion
    elif p_in and o_in:
        if judged[preferred] == judged[other]:
            branch, final = "qwen_tie_fusion", fusion
        else:
            branch = "qwen_different_scores"
            final = relation(judged[preferred], judged[other])
    elif p_in != o_in:
        branch = "preferred_only_in_window" if p_in else "other_only_in_window"
        final = "strict_correct" if p_in else "reverse"
    else:
        branch, final = "both_outside_window", fusion
    return {
        "branch": branch, "final": final, "fusion": fusion,
        "both_in_window": p_in and o_in,
        "preferred_score": judged.get(preferred), "other_score": judged.get(other),
        "boundary_fusion_tie": p_in != o_in and fusion == "model_tie" and not fallback,
    }


def summarize(rows):
    counts = Counter(row["final"] for row in rows)
    baseline_correct = sum(row["fusion"] == "strict_correct" for row in rows)
    corrected = sum(row["fusion"] != "strict_correct" and row["final"] == "strict_correct"
                    for row in rows)
    damaged = sum(row["fusion"] == "strict_correct" and row["final"] != "strict_correct"
                  for row in rows)
    return {"n": len(rows), **{k: counts[k] for k in OUTCOMES},
            "fusion_correct": baseline_correct, "corrected": corrected,
            "damaged": damaged, "net_correct": corrected - damaged}


def analyze(folder=FOLDER):
    config = json.loads((folder / "frozen-config.json").read_text())
    if config["evaluation"]["K"] != [20]:
        raise ValueError("this analysis describes the frozen K20 experiment")
    sources = {
        "l2_directions": folder / "qwen-evaluation/l2-primary-per-query.jsonl",
        "l1_directions": folder / "qwen-evaluation/l1-primary-per-query.jsonl",
        "fusion_scores": folder / "inputs/stage1-test.jsonl",
        "l2_judgments": folder / "l2-judge/scores.jsonl",
        "supervision": Path(config["snapshot"]) / "prepared/test/supervision.jsonl",
        "evaluation": folder / "qwen-evaluation/results.json",
    }
    l2 = indexed(read_rows(sources["l2_directions"]))
    l1 = indexed(read_rows(sources["l1_directions"]))
    labels = indexed(read_rows(sources["supervision"]))
    if set(l1) != set(l2) or len(l2) != config["population"]["primary_queries"]:
        raise ValueError("saved primary populations differ")
    stage1 = {}
    for row in read_rows(sources["fusion_scores"]):
        scores = {r["chunk_id"]: r["score"] for r in row["scores"]}
        if len(scores) != len(row["scores"]) or row["source_query_id"] in stage1:
            raise ValueError("duplicate fusion score identity")
        stage1[row["source_query_id"]] = scores
    eligible = {qid for qid, label in labels.items()
                if label["official_label_available"] and not label["structural_conflict"]
                and {label["preferred_chunk_id"], label["other_chunk_id"]}
                <= stage1.get(qid, {}).keys()}
    if eligible != set(l2):
        raise ValueError("primary directions differ from saved coverage and exclusion rules")
    judged = defaultdict(dict)
    read_judgments = 0
    for row in read_rows(sources["l2_judgments"]):
        read_judgments += 1
        qid, cid = row["source_query_id"], row["chunk_id"]
        if cid in judged[qid]:
            raise ValueError("duplicate saved judgment")
        if (row["model"] != config["model"]["served_name"] or row["effort"] != "think"
                or row["prompt_version"] != config["judge_arguments"]["prompt_version"]):
            raise ValueError("judgment metadata differs from frozen experiment")
        if ((row["status"] == "available" and row["score"] is None)
                or (row["status"] == "unavailable" and row["score"] is not None)
                or row["status"] not in {"available", "unavailable"}):
            raise ValueError("invalid saved availability")
        judged[qid][cid] = row["score"]
    # Retain only numeric/identity fields in memory after parsing each source row.
    decisions = []
    for qid, saved in l2.items():
        label = labels[qid]
        for field in ("source_group_id", "pair_id", "direction"):
            if saved[field] != label[field] or l1[qid][field] != label[field]:
                raise ValueError("saved direction identity mismatch")
        row = classify(stage1[qid], judged[qid], label["preferred_chunk_id"],
                       label["other_chunk_id"])
        if row["final"] != saved["stage1_judge"] or row["fusion"] != saved["stage1"]:
            raise ValueError("decision reconstruction differs from saved evaluation")
        row["l1"] = l1[qid]["judge"]
        decisions.append(row)
    overall = summarize(decisions)
    original = json.loads(sources["evaluation"].read_text())
    metrics = original["populations"]["l2"]["primary"]["metrics"]
    final = metrics["rankers"]["stage1_judge"]["pairwise"]
    contrast = metrics["contrasts"]["stage1"]["stage1_judge"]
    if any(overall[k] != final[k] for k in ("n", *OUTCOMES)):
        raise ValueError("saved aggregate differs from reconstructed outcomes")
    if any(overall[k] != contrast[k] for k in ("corrected", "damaged")):
        raise ValueError("saved contrast differs from reconstructed transitions")
    branches = {b: summarize([r for r in decisions if r["branch"] == b]) for b in BRANCHES}
    successful_pair = [r for r in decisions if r["both_in_window"]
                       and r["branch"] != "whole_query_fallback"]
    tied = [r for r in decisions if r["branch"] == "qwen_tie_fusion"]
    matrix = {f"{a}:{b}": summarize([r for r in successful_pair
                                   if (r["preferred_score"], r["other_score"]) == (a, b)])
              for a in range(5) for b in range(5)}
    l1_counts = Counter(r["l1"] for r in decisions)
    expected_l1 = original["populations"]["l1"]["primary"]["metrics"]["judge"]
    if any(l1_counts[k] != expected_l1[k] for k in (*OUTCOMES, "unavailable")):
        raise ValueError("saved L1 aggregate mismatch")
    l1_tied = [r for r in decisions if r["l1"] == "model_tie"]
    return {
        "definition": "First decisive key in the frozen composite order; descriptive, not causal attribution.",
        "sources": {k: str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)
                    for k, p in sources.items()},
        "inputs": {"l2_judgment_rows": read_judgments, "fusion_queries": len(stage1),
                   "primary_directions": len(l2), "top_k": 20},
        "overall": overall,
        "branches": {b: {**v, "share_of_all_directions": v["n"] / len(decisions),
                         "correct_share_of_final_correct": v["strict_correct"] / overall["strict_correct"],
                         "correct_contribution_pp": 100 * v["strict_correct"] / len(decisions)}
                     for b, v in branches.items()},
        "qwen_ties_by_score": {str(s): summarize([r for r in tied if r["preferred_score"] == s])
                               for s in range(5)},
        "successful_in_window_score_matrix_preferred_other": matrix,
        "l1_outcomes": {k: l1_counts[k] for k in (*OUTCOMES, "unavailable")},
        "l1_tie_to_l2_branches": {b: summarize([r for r in l1_tied if r["branch"] == b])
                                  for b in BRANCHES},
        "l1_l2_outcome_cross_table": {
            a: dict(Counter(r["final"] for r in decisions if r["l1"] == a))
            for a in (*OUTCOMES, "unavailable")},
        "boundary_fusion_ties": sum(r["boundary_fusion_tie"] for r in decisions),
        "verification": {"saved_direction_mismatches": 0, "original_totals_match": True,
                         "original_contrast_match": True, "original_l1_counts_match": True,
                         "mutually_exclusive_complete_partition": sum(v["n"] for v in branches.values()) == len(l2)},
        "limitations": [
            "Post-hoc numeric analysis of previously evaluated official Test; no parameter selection.",
            "L1 and L2 are separately executed scores and cannot be substituted for each other.",
            "Correct-result shares are not causal contributions; all branches retain the fusion-selected window.",
            "Tied-score levels describe model output, not independently verified semantics or full-pool relevance.",
            "No inference, training, retrieval, original result changes, or new significance testing.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Recompute aggregates without writing")
    args = parser.parse_args()
    started = time.perf_counter()
    analysis = analyze()
    elapsed = time.perf_counter() - started
    if args.check:
        if json.loads(OUTPUT.read_text())["analysis"] != analysis:
            raise ValueError("saved decomposition differs from current source results")
    else:
        payload = {
            "status": "completed", "recorded_at": datetime.now(UTC).isoformat(),
            "code_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "local_code_change": "New decompose_qwen.py; frozen scoring and evaluation code unchanged.",
            "analysis": analysis,
            "execution": {"wall_seconds": elapsed, "timing_scope": "Read saved numeric evidence and validate aggregate decomposition; excludes writing and review",
                          "model_requests": 0, "training_runs": 0, "retrieval_requests": 0,
                          "test_content_handling": "Programmatic IDs, scores and states; no per-item text output or semantic review"},
        }
        with OUTPUT.open("x") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
    print(json.dumps({"checked": args.check, "wall_seconds": elapsed,
                      "overall": analysis["overall"], "branches": analysis["branches"],
                      "qwen_ties_by_score": analysis["qwen_ties_by_score"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
