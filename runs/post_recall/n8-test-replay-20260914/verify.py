"""Independently verify saved N8 Test scores; never invoke a model or print Test rows."""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

TOLERANCE = 1e-12
RANKERS = ("E0", "fusion", "background_n8")
SECTIONS = ("coverage", "results", "mcnemar_primary_e0_vs_background_n8")


def read_rows(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def read_scores(path):
    result = {}
    for row in read_rows(path):
        qid = row["source_query_id"]
        if qid in result:
            raise ValueError("duplicate query in saved scores")
        candidates = {}
        for entry in row["scores"]:
            cid, score = entry["chunk_id"], entry["score"]
            if cid in candidates or type(score) not in (int, float) or not math.isfinite(score):
                raise ValueError("invalid or duplicate saved candidate score")
            candidates[cid] = score
        result[qid] = candidates
    return result


def interval(correct, total):
    """Two-sided 95% Wilson score interval, calculated directly."""
    z = 1.959963984540054
    denominator = total + z * z
    center = (correct + z * z / 2) / denominator
    radius = z * math.sqrt(correct * (total - correct) / total + z * z / 4) / denominator
    return [center - radius, center + radius]


def summarize(labels, scores, population):
    correct = {}
    preferred_ranks, other_ranks = [], []
    wrong = ties = both_top10 = 0
    pairs = defaultdict(list)
    for qid in population:
        label, values = labels[qid], scores[qid]
        preferred, other = label["preferred_chunk_id"], label["other_chunk_id"]
        correct[qid] = values[preferred] > values[other]
        wrong += values[preferred] < values[other]
        ties += values[preferred] == values[other]
        order = sorted(values, key=lambda cid: (-values[cid], cid))
        preferred_rank, other_rank = order.index(preferred) + 1, order.index(other) + 1
        preferred_ranks.append(preferred_rank)
        other_ranks.append(other_rank)
        both_top10 += preferred_rank <= 10 and other_rank <= 10
        pairs[label["pair_id"]].append(correct[qid])
    count = len(population)
    complete = [outcomes for outcomes in pairs.values() if len(outcomes) == 2]
    if not count or not complete or any(len(outcomes) > 2 for outcomes in pairs.values()):
        raise ValueError("unexpected empty population or pair cardinality")
    successes = sum(correct.values())
    both_correct = sum(all(outcomes) for outcomes in complete)
    designated = sorted(preferred_ranks + other_ranks)
    result = {
        "queries": count,
        "strict_correct": successes,
        "strict_wrong": wrong,
        "strict_tie": ties,
        "strict_accuracy": successes / count,
        "strict_accuracy_wilson_95ci": interval(successes, count),
        "complete_pairs": len(complete),
        "both_directions_correct": both_correct,
        "both_directions_accuracy": both_correct / len(complete),
        "preferred_at_1": sum(rank == 1 for rank in preferred_ranks) / count,
        "preferred_at_3": sum(rank <= 3 for rank in preferred_ranks) / count,
        "preferred_mrr": math.fsum(1 / rank for rank in preferred_ranks) / count,
        "preferred_mean_rank": sum(preferred_ranks) / count,
        "other_mean_rank": sum(other_ranks) / count,
        "designated_median_rank": (designated[count - 1] + designated[count]) / 2,
        "both_designated_in_top10": both_top10,
    }
    if successes + wrong + ties != count:
        raise ValueError("pairwise outcome counts do not sum to the population")
    return result, correct


def aggregate(supervision, predictions):
    labels = {row["source_query_id"]: row for row in supervision}
    if len(labels) != len(supervision) or not labels:
        raise ValueError("duplicate or empty supervision population")
    if set(predictions) != set(RANKERS):
        raise ValueError("exactly the three fixed rankers are required")
    if any(set(scores) != set(labels) for scores in predictions.values()):
        raise ValueError("saved score queries do not match supervision")
    covered, top20 = [], 0
    for qid, label in labels.items():
        union = set(predictions["E0"][qid])
        if any(set(predictions[name][qid]) != union for name in RANKERS):
            raise ValueError("saved rankers do not share the same full candidate pool")
        designated = {label["preferred_chunk_id"], label["other_chunk_id"]}
        if len(designated) != 2:
            raise ValueError("designated candidates must be distinct")
        if designated <= union:
            covered.append(qid)
        fusion = predictions["fusion"][qid]
        order = sorted(fusion, key=lambda cid: (-fusion[cid], cid))
        top20 += designated <= set(order[:20])
    official = [qid for qid in covered if labels[qid]["official_label_available"]]
    primary = [qid for qid in official if not labels[qid]["structural_conflict"]]
    populations = {"primary_no_structural_conflict": primary, "including_conflict": official}
    results, primary_correct = {}, {}
    for population_name, population in populations.items():
        results[population_name] = {}
        for name in RANKERS:
            result, correct = summarize(labels, predictions[name], population)
            results[population_name][name] = result
            if population_name == "primary_no_structural_conflict":
                primary_correct[name] = correct
    improved = sum(not primary_correct["E0"][qid] and primary_correct["background_n8"][qid]
                   for qid in primary)
    regressed = sum(primary_correct["E0"][qid] and not primary_correct["background_n8"][qid]
                    for qid in primary)
    discordant = improved + regressed
    numerator = 2 * sum(math.comb(discordant, k) for k in range(min(improved, regressed) + 1))
    return {
        "coverage": {
            "all_queries": len(labels),
            "both_designated_in_candidate_union": len(covered),
            "both_designated_in_fusion_top20": top20,
            "official_and_covered": len(official),
            "primary_no_structural_conflict": len(primary),
        },
        "results": results,
        "mcnemar_primary_e0_vs_background_n8": {
            "e0_wrong_n8_correct": improved,
            "e0_correct_n8_wrong": regressed,
            "discordant": discordant,
            "exact_two_sided_p": min(1.0, numerator / (1 << discordant)),
        },
    }


def compare(actual, expected):
    """Check aggregate leaves only; counts require exact type/value agreement."""
    failures, checked = [], 0

    def visit(left, right, path):
        nonlocal checked
        if isinstance(left, dict) and isinstance(right, dict):
            if left.keys() != right.keys():
                failures.append({"metric": path, "reason": "aggregate field set differs"})
            for key in sorted(left.keys() & right.keys()):
                visit(left[key], right[key], f"{path}.{key}".lstrip("."))
            return
        if isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
            for index, (a, b) in enumerate(zip(left, right, strict=True)):
                visit(a, b, f"{path}[{index}]")
            return
        checked += 1
        if type(left) is float and type(right) is float:
            equal = math.isfinite(left) and math.isfinite(right) and abs(left - right) <= TOLERANCE
        else:
            equal = type(left) is type(right) and left == right
        if not equal:
            failures.append({"metric": path, "actual": left, "expected": right})

    visit(actual, expected, "")
    return {"all_aggregates_match": not failures, "checked_values": checked, "mismatches": failures}


def verify(data_root, run_dir):
    data_root, run_dir = Path(data_root).resolve(), Path(run_dir).resolve()
    output = run_dir / "verification.json"
    if output.exists():
        raise FileExistsError("verification output already exists")
    started = time.perf_counter()
    runs = data_root / "runs/post_recall"
    paths = {
        "supervision": runs / "nevir-test-candidates-20260910/snapshot/prepared/test/supervision.jsonl",
        "E0": runs / "nevir-test-main-20260911/baseline/scores.jsonl",
        "fusion": runs / "nevir-test-main-20260911/inputs/stage1-test.jsonl",
        "background_n8": run_dir / "scores.jsonl",
        "replay_results": run_dir / "results.json",
        "member_results": runs / "nevir-test-final-20260911/results.json",
    }
    actual = aggregate(read_rows(paths["supervision"]), {
        name: read_scores(paths[name]) for name in RANKERS
    })
    checks = {}
    for name in ("replay_results", "member_results"):
        reference = json.loads(paths[name].read_text(encoding="utf-8"))
        checks[name] = compare(actual, {section: reference[section] for section in SECTIONS})
    matched = all(check["all_aggregates_match"] for check in checks.values())
    record = {
        "issue": 49,
        "status": "verified_match" if matched else "verified_mismatch",
        "verified_at": datetime.now(UTC).isoformat(),
        "implementation": "Independent standard-library recomputation; no replay or historical metric imports",
        "inputs": {name: str(path) for name, path in paths.items()},
        "float_absolute_tolerance": TOLERANCE,
        "integer_comparison": "exact type and value",
        "ranking_rule": "Full saved candidate pool ordered by (-score, chunk_id); ranks start at 1",
        "pairwise_rule": "Direct preferred/other score comparison; a tie is never strict correctness",
        "checks": checks,
        "recomputed": actual,
        "wall_seconds": time.perf_counter() - started,
        "scoring": False, "training": False, "retrieval": False,
        "limitation": "Aggregate agreement does not establish identity with unavailable member per-query scores",
    }
    with output.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": record["status"], "coverage": actual["coverage"],
                      "checks": {name: {"all_aggregates_match": check["all_aggregates_match"],
                                        "checked_values": check["checked_values"],
                                        "mismatch_count": len(check["mismatches"])}
                                 for name, check in checks.items()}}), flush=True)
    return matched


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        matched = verify(args.data_root, args.run_dir)
    except Exception as exc:  # noqa: BLE001 -- Never expose Test row contents in a traceback.
        print(json.dumps({"status": "verification_failed", "error_type": type(exc).__name__}), flush=True)
        raise SystemExit(1) from None
    raise SystemExit(0 if matched else 1)


if __name__ == "__main__":
    main()
